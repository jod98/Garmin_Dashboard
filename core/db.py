"""
Thin data-access layer over the Supabase (Postgres) database.
All functions open a short-lived connection - fine at this volume (a few calls/week).
"""
import os
import json
from datetime import date
import psycopg2
from psycopg2.extras import RealDictCursor


def _connect():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def get_athlete_profile():
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select goal, constraints from athlete_profile where id = 1;")
        return cur.fetchone()


def update_athlete_profile(goal: str, constraints: str):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "update athlete_profile set goal = %s, constraints = %s, updated_at = now() "
            "where id = 1;",
            (goal, constraints),
        )
        conn.commit()


def save_plan(week_start: date, sessions: list, rationale: str = ""):
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
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select * from weekly_plans where week_start = %s;", (week_start,))
        return cur.fetchone()


def mark_plan_pushed(week_start: date):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "update weekly_plans set garmin_pushed = true where week_start = %s;",
            (week_start,),
        )
        conn.commit()


def get_recent_plans(limit: int = 4):
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "select * from weekly_plans order by week_start desc limit %s;", (limit,)
        )
        return cur.fetchall()


def save_feedback(week_start: date, energy_level, soreness_level, injury_flag,
                   injury_notes, missed_sessions, notes):
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
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select * from weekly_feedback where week_start = %s;", (week_start,))
        return cur.fetchone()


def get_recent_feedback(limit: int = 4):
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "select * from weekly_feedback order by week_start desc limit %s;", (limit,)
        )
        return cur.fetchall()
