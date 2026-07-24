"""
Garmin Connect integration layer.

Wraps python-garminconnect (https://github.com/cyberjunky/python-garminconnect).
Handles two directions of data flow:
  1. READING your recent metrics (body battery, sleep, activities) so the
     plan generator has real data to reason about fatigue/load.
  2. WRITING structured workouts onto your Garmin Connect calendar, which
     Garmin then syncs down to your watch so you can follow/track them live.

Auth note: garminconnect uses the `garth` library under the hood, which persists
a long-lived (~1 year) session token to disk after your first login, so you are
NOT logging in with your password on every scheduled run - only the very first
time (or after the token expires / you change your password).

Replan / injury note: whenever the AI coach regenerates a plan (either a full
block or a quick mid-week adjustment), the OLD workouts that are still sitting
in the future on your Garmin calendar must be deleted before the NEW ones are
pushed - otherwise your watch ends up showing both the old and new plan at
once, which is confusing and means you could sync/complete the wrong workout.
`sync_workouts()` below is the single function that does this delete-then-push
swap; every call site in this project should go through it rather than calling
`push_workout` directly, so this behaviour stays consistent everywhere.
"""
import os
from datetime import date, timedelta

import garminconnect
from garminconnect.workout import (
    RunningWorkout,
    WorkoutSegment,
    create_warmup_step,
    create_cooldown_step,
    create_interval_step,
    create_repeat_group,
)

# Where garth's persisted login session/token lives on disk. Override with the
# GARMINTOKENS env var if you want it stored somewhere other than the default.
TOKEN_DIR = os.environ.get("GARMINTOKENS", os.path.expanduser("~/.garminconnect"))

# Maps our internal "sport" string (as used in plan_generator.py's session
# JSON) to the (garminconnect sport name, Workout class, sportType payload)
# needed to build a structured workout upload.
#
# Currently RESTRICTED TO RUNNING ONLY: garminconnect's workout builder only
# ships a RunningWorkout class today, so bike/swim/walk sessions in a plan are
# simply not pushed to Garmin (they still show up in the dashboard/DB, just
# not on the watch). Extending this to other sports means adding the matching
# Workout subclass here once garminconnect (or your own payload) supports it.
_SPORT_MAP = {
    "run": ("running", RunningWorkout, {"sportTypeId": 1, "sportTypeKey": "running"}),
}


def get_client() -> garminconnect.Garmin:
    """
    Returns a logged-in Garmin Connect client.

    Tries the cached/persisted garth token in TOKEN_DIR first (no password
    needed - this is what every scheduled/cron run should hit). If that
    fails (first-ever run, or the token expired/was revoked), falls back to
    a fresh email/password login using GARMIN_EMAIL / GARMIN_PASSWORD env
    vars, which also (re)writes the token to TOKEN_DIR for next time.
    """
    try:
        client = garminconnect.Garmin()
        client.login(TOKEN_DIR)
        return client
    except Exception:
        # No valid cached token - fall back to a full credential login.
        client = garminconnect.Garmin(
            email=os.environ["GARMIN_EMAIL"],
            password=os.environ["GARMIN_PASSWORD"],
        )
        client.login(TOKEN_DIR)
        return client


def fetch_week_summary(client: garminconnect.Garmin, start: date, end: date) -> dict:
    """
    Pulls the metrics the plan generator needs to reason about fatigue/load
    for every day in [start, end] (inclusive): body battery, sleep score, and
    completed activities (with duration/distance/HR/training load).

    Any single day/field that fails to fetch is left as None/empty rather
    than raising, so one bad Garmin API call doesn't block the whole plan
    generation.

    Args:
        client: Authenticated Garmin client (see get_client()).
        start: First day to include.
        end: Last day to include (inclusive).

    Returns:
        dict shaped like:
            {
                "days": [{"date": "YYYY-MM-DD", "body_battery": ..., "sleep_score": ...}, ...],
                "activities": [{"name": ..., "type": ..., "duration_min": ..., ...}, ...],
            }
    """
    summary = {"days": []}
    d = start
    while d <= end:
        iso = d.isoformat()
        day = {"date": iso}
        try:
            day["body_battery"] = client.get_body_battery(iso, iso)
        except Exception:
            day["body_battery"] = None
        try:
            sleep = client.get_sleep_data(iso)
            day["sleep_score"] = sleep.get("dailySleepDTO", {}).get("sleepScores", {}).get(
                "overall", {}
            ).get("value")
        except Exception:
            day["sleep_score"] = None
        summary["days"].append(day)
        d += timedelta(days=1)

    try:
        activities = client.get_activities_by_date(start.isoformat(), end.isoformat())
        summary["activities"] = [
            {
                "name": a.get("activityName"),
                "type": a.get("activityType", {}).get("typeKey"),
                "duration_min": round((a.get("duration") or 0) / 60, 1),
                "distance_km": round((a.get("distance") or 0) / 1000, 2),
                "avg_hr": a.get("averageHR"),
                "training_load": a.get("activityTrainingLoad"),
            }
            for a in activities
        ]
    except Exception:
        summary["activities"] = []

    return summary


def _build_steps(session: dict):
    """
    Translates a plan session's simple `structure` list into the list of
    garminconnect WorkoutStep objects a RunningWorkout needs.

    `session["structure"]` is a simple list like:
      [{"type": "warmup", "duration_sec": 600},
       {"type": "interval", "duration_sec": 240, "reps": 6, "recovery_sec": 90},
       {"type": "cooldown", "duration_sec": 600}]
    Kept intentionally simple - the plan generator's system prompt is written
    to only ever produce these shapes, so this function doesn't need to
    handle arbitrary/nested structures.

    Args:
        session: A single plan session dict (see plan_generator.py for the
            full shape). Only the optional "structure" and "duration_min"
            keys are read here.

    Returns:
        list: Ordered garminconnect workout step/repeat-group objects, ready
        to hand to a WorkoutSegment.
    """
    steps = []
    step_order = 1
    for step in session.get("structure", []):
        if step["type"] == "warmup":
            steps.append(create_warmup_step(step_order, step["duration_sec"]))
            step_order += 1
        elif step["type"] == "cooldown":
            steps.append(create_cooldown_step(step_order, step["duration_sec"]))
            step_order += 1
        elif step["type"] == "interval":
            reps = step.get("reps", 1)
            # One "repeat group" = the hard interval, optionally followed by
            # its recovery, repeated `reps` times (e.g. 6x [4min hard, 90s easy]).
            group_steps = [create_interval_step(1, step["duration_sec"])]

            if step.get("recovery_sec"):
                group_steps.append(create_interval_step(2, step["recovery_sec"]))

            # Signature: (iterations: int, workout_steps: list, step_order: int)
            steps.append(create_repeat_group(reps, group_steps, step_order))
            step_order += 1
        else:
            # Unknown step type (or a plain steady-state session with no
            # explicit structure) - treat it as one flat interval step.
            steps.append(create_interval_step(step_order, step.get("duration_sec", 1200)))
            step_order += 1

    if not steps:
        # No structure at all was provided - fall back to a single plain
        # step covering the whole planned session duration, so we always
        # upload *something* runnable rather than an empty workout.
        steps.append(create_interval_step(1, session.get("duration_min", 30) * 60))

    return steps


def push_workout(client: garminconnect.Garmin, session: dict, on_date: date) -> str:
    """
    Uploads a single structured workout to Garmin Connect and schedules it
    on the user's calendar for `on_date`, which is what makes it sync down
    to the watch.

    Args:
        client: Authenticated Garmin client.
        session: {
            "sport": "run",
            "title": "Easy Run",
            "duration_min": 30,
            "structure": [...]   # optional, see _build_steps
        }
        on_date: Calendar date to schedule the workout on.

    Returns:
        str: The new Garmin workout id. Save this (e.g. onto the session
        dict as "garmin_workout_id") so a future replan can delete it via
        remove_workout() / sync_workouts() - without it, an old workout is
        orphaned on the calendar forever.

    Raises:
        ValueError: If `session["sport"]` isn't a supported/structured sport
            (see _SPORT_MAP - currently running only).
    """
    sport = session["sport"].lower()
    if sport not in _SPORT_MAP:
        raise ValueError(f"Sport '{sport}' has no structured Garmin workout mapping")

    _, WorkoutClass, sport_type = _SPORT_MAP[sport]
    workout = WorkoutClass(
        workoutName=session["title"],
        estimatedDurationInSecs=session.get("duration_min", 30) * 60,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType=sport_type,
                workoutSteps=_build_steps(session),
            )
        ],
    )
    upload_fn = getattr(client, f"upload_{_SPORT_MAP[sport][0]}_workout")
    result = upload_fn(workout)
    client.schedule_workout(result["workoutId"], on_date.isoformat())
    return result["workoutId"]


def remove_workout(client: garminconnect.Garmin, workout_id: str):
    """
    Deletes a previously pushed workout from Garmin Connect, which also
    removes it from the watch's calendar/sync queue.

    Swallows/logs errors instead of raising: this is normally called in a
    loop while cleaning up several old workouts before pushing a new plan,
    and one already-deleted or not-found workout id shouldn't stop the rest
    of the cleanup (or the new plan) from going through.

    Args:
        client: Authenticated Garmin client.
        workout_id: The Garmin workout id returned by an earlier push_workout() call.
    """
    try:
        client.delete_workout(workout_id)
    except Exception as e:
        print(f"Could not remove workout {workout_id}: {e}")


def sync_workouts(
    client: garminconnect.Garmin,
    old_sessions: list,
    new_sessions: list,
    from_date: date,
) -> list:
    """
    Replaces the future Garmin Connect workouts for a week with a new set of
    sessions - this is the function that makes replanning (e.g. after an
    injury) safe, by making sure the OLD plan's future workouts are removed
    from the calendar before the NEW plan's workouts are pushed.

    Why this matters: without this step, regenerating a plan just pushes new
    workouts on top of whatever is already scheduled. The watch then shows
    both the abandoned old plan AND the new plan on the same days, which is
    exactly the confusing double-booked-calendar situation you want to avoid.

    What it does, in order:
      1. Deletes every session in `old_sessions` that (a) has a
         "garmin_workout_id" recorded from a previous push, AND (b) falls on
         or after `from_date`. Sessions before `from_date` (already run /
         already in the past) are left untouched - there's nothing to "fix"
         about a workout that's already happened.
      2. Pushes every runnable session (currently: sport == "run" with a
         "structure") in `new_sessions` that falls on or after `from_date`,
         and stamps the Garmin workout id it gets back onto that session
         dict under "garmin_workout_id".

    Note on simplicity: this always deletes-then-recreates rather than
    trying to detect "this session didn't actually change, leave it alone".
    That trade-off is intentional - diffing two workout structures to decide
    if they're "the same" is fiddly and error-prone, whereas delete-then-push
    is simple, always correct, and Garmin workout uploads are cheap/fast.

    Args:
        client: Authenticated Garmin client.
        old_sessions: The sessions list for this week as it was BEFORE the
            replan (i.e. what's currently pushed to Garmin, if anything -
            each session may or may not have a "garmin_workout_id").
        new_sessions: The freshly (re)generated sessions list for this week.
            Mutated in place: any pushed session gets "garmin_workout_id" set.
        from_date: Only sessions on/after this date are touched on Garmin.
            Pass date.today() for a mid-week adjustment so past days are left
            alone; pass the week's Monday for a brand new week that hasn't
            started yet.

    Returns:
        list: `new_sessions`, with "garmin_workout_id" filled in on whichever
        sessions were successfully pushed. ALWAYS save this back to the
        database (see db.save_plan) - it's how the next replan knows which
        workout ids exist on the watch and need deleting.
    """
    # --- Step 1: clear out the old plan's future workouts first, so the
    # watch is never left showing both the old and new plan at once. ---
    for old_session in old_sessions:
        workout_id = old_session.get("garmin_workout_id")
        if not workout_id:
            continue  # This session was never pushed to Garmin - nothing to remove.
        try:
            session_date = date.fromisoformat(old_session["date"])
        except (KeyError, ValueError):
            continue
        if session_date >= from_date:
            remove_workout(client, workout_id)

    # --- Step 2: push the new plan's future, runnable sessions. ---
    for session in new_sessions:
        try:
            session_date = date.fromisoformat(session["date"])
        except (KeyError, ValueError):
            continue
        if session_date < from_date:
            continue  # Don't rewrite history for days that have already happened.
        if session.get("sport") == "run" and session.get("structure"):
            try:
                session["garmin_workout_id"] = push_workout(client, session, session_date)
            except Exception as e:
                print(f"Could not push workout for {session['date']}: {e}")

    return new_sessions
