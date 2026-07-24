"""
Data-access layer over the Supabase (Postgres) database - see schema.sql for
the three tables this module reads/writes: `athlete_profile`, `weekly_plans`,
and `weekly_feedback`.

All functions open their own short-lived connection and close it again via
the `with` block. That's inefficient compared to a shared connection pool,
but perfectly fine at this app's volume (a handful of calls per week from a
single user), and it keeps every function simple/self-contained.

Note on `sessions` (weekly_plans.sessions, jsonb): each session dict can carry
whatever keys the rest of the app needs - in particular "garmin_workout_id",
which core/garmin_client.py's sync_workouts() stamps onto a session once it's
been pushed to Garmin Connect. That id is what lets a future replan find and
delete the right workout, so always pass the FULL, up-to-date sessions list
(including any "garmin_workout_id" values) into save_plan() - saving a plan
without them effectively "forgets" what's on the Garmin calendar.
"""
import os
import json
from datetime import date
import psycopg2
from psycopg2.extras import RealDictCursor


def _connect():
    """Opens a fresh connection to the database using DATABASE_URL from the environment."""
    return psycopg2.connect(os.environ["DATABASE_URL"])


def get_athlete_profile():
    """
    Fetches the single athlete profile row (goal + constraints).

    Returns:
        dict or None: {"goal": str, "constraints": str}, or None if the
        `athlete_profile` table is somehow empty (shouldn't happen after
        running schema.sql, which seeds row id=1).
    """
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select goal, constraints from athlete_profile where id = 1;")
        return cur.fetchone()


def update_athlete_profile(goal: str, constraints: str):
    """
    Overwrites the athlete's goal/constraints text (there's only ever one
    profile row, id=1) and bumps `updated_at`.

    Args:
        goal: Free-text training goal, e.g. "sub-50 10k by October".
        constraints: Free-text scheduling/availability constraints.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "update athlete_profile set goal = %s, constraints = %s, updated_at = now() "
            "where id = 1;",
            (goal, constraints),
        )
        conn.commit()


def save_plan(week_start: date, sessions: list, rationale: str = ""):
    """
    Saves (or overwrites, if one already exists) the plan for a given week.

    This is an upsert keyed on `week_start`, so calling it twice for the same
    week fully replaces that week's sessions - which is exactly what a
    mid-week adjustment or a "regenerate this week" action needs. Always
    include any "garmin_workout_id" values already present on `sessions`
    (see the module docstring) so a subsequent replan can find and clean up
    what's currently on the Garmin calendar.

    Args:
        week_start: The Monday that starts this plan's week.
        sessions: List of session dicts (see plan_generator.py for the shape).
        rationale: Short human-readable explanation of this week's plan, as
            returned by the plan generator.

    Returns:
        int: The `weekly_plans.id` of the inserted/updated row.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into weekly_plans (week_start, sessions, rationale)
            values (%s, %s, %s)
            on conflict (week_start) do update
                set sessions = excluded.sessions, rationale = excluded.rationale
            returning id;
            """,
            (week_start, json.dumps(sessions), rationale),
        )
        conn.commit()
        return cur.fetchone()[0]


def get_plan(week_start: date):
    """
    Fetches the saved plan (sessions + rationale + metadata) for one week.

    Args:
        week_start: The Monday that starts the week to look up.

    Returns:
        dict or None: The full `weekly_plans` row (including "sessions" as a
        parsed list of dicts), or None if no plan has been saved for that week.
    """
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select * from weekly_plans where week_start = %s;", (week_start,))
        return cur.fetchone()


def get_recent_plans(limit: int = 4):
    """
    Fetches the most recent saved weekly plans, newest first - used as
    context for the plan generator so it can see recent training load/progression.

    Args:
        limit: Maximum number of most-recent weeks to return.

    Returns:
        list[dict]: Weekly plan rows, most recent `week_start` first.
    """
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "select * from weekly_plans order by week_start desc limit %s;", (limit,)
        )
        return cur.fetchall()


def save_feedback(week_start: date, energy_level, soreness_level, injury_flag,
                   injury_notes, missed_sessions, notes):
    """
    Saves (or overwrites) the athlete's weekly check-in feedback for one week.

    Upsert keyed on `week_start`, so resubmitting the same week's check-in
    form replaces the previous answers and refreshes `submitted_at`.

    Args:
        week_start: The Monday that starts the week being reported on.
        energy_level: Self-rated energy, 1-5.
        soreness_level: Self-rated soreness/fatigue, 1-5.
        injury_flag: Whether an injury/niggle was picked up this week.
        injury_notes: Free-text description of the injury, if any.
        missed_sessions: Free-text note on any sessions missed/shortened.
        notes: Any other free-text notes for the coach.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into weekly_feedback
                (week_start, energy_level, soreness_level, injury_flag,
                 injury_notes, missed_sessions, notes)
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (week_start) do update set
                energy_level = excluded.energy_level,
                soreness_level = excluded.soreness_level,
                injury_flag = excluded.injury_flag,
                injury_notes = excluded.injury_notes,
                missed_sessions = excluded.missed_sessions,
                notes = excluded.notes,
                submitted_at = now();
            """,
            (week_start, energy_level, soreness_level, injury_flag,
             injury_notes, missed_sessions, notes),
        )
        conn.commit()


def get_feedback(week_start: date):
    """
    Fetches the saved weekly check-in feedback for one week.

    Args:
        week_start: The Monday that starts the week to look up.

    Returns:
        dict or None: The feedback row, or None if nothing was submitted for that week.
    """
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select * from weekly_feedback where week_start = %s;", (week_start,))
        return cur.fetchone()


def get_recent_feedback(limit: int = 4):
    """
    Fetches the most recent weekly check-in feedback entries, newest first -
    used as context for the plan generator.

    Args:
        limit: Maximum number of most-recent weeks of feedback to return.

    Returns:
        list[dict]: Feedback rows, most recent `week_start` first.
    """
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "select * from weekly_feedback order by week_start desc limit %s;", (limit,)
        )
        return cur.fetchall()
