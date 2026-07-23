"""
Wraps python-garminconnect (https://github.com/cyberjunky/python-garminconnect).
Handles both reading your recent metrics and pushing structured running workouts that
sync to your watch via Garmin Connect's calendar.

Auth note: garminconnect uses the `garth` library under the hood, which persists
a long-lived (~1 year) session token to disk after your first login, so you are
NOT logging in with your password on every scheduled run - only the very first
time (or after the token expires / you change your password).
"""
import os
import json
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

TOKEN_DIR = os.environ.get("GARMINTOKENS", os.path.expanduser("~/.garminconnect"))

# Restricted to running only
_SPORT_MAP = {
    "run": ("running", RunningWorkout, {"sportTypeId": 1, "sportTypeKey": "running"}),
}


def get_client() -> garminconnect.Garmin:
    """
    Logs in using cached tokens if present, otherwise a fresh email/password login.
    Passing TOKEN_DIR to login() makes the library save/refresh tokens there itself -
    no separate manual save step needed.
    """
    try:
        client = garminconnect.Garmin()
        client.login(TOKEN_DIR)
        return client
    except Exception:
        client = garminconnect.Garmin(
            email=os.environ["GARMIN_EMAIL"],
            password=os.environ["GARMIN_PASSWORD"],
        )
        client.login(TOKEN_DIR)
        return client


def fetch_week_summary(client: garminconnect.Garmin, start: date, end: date) -> dict:
    """Pulls the metrics the plan generator needs to reason about fatigue/load."""
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
    session["structure"] is a simple list like:
      [{"type": "warmup", "duration_sec": 600},
       {"type": "interval", "duration_sec": 240, "reps": 6, "recovery_sec": 90},
       {"type": "cooldown", "duration_sec": 600}]
    Kept intentionally simple - the plan generator is prompted to only use these shapes.
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
            group_steps = [create_interval_step(1, step["duration_sec"])]
            
            if step.get("recovery_sec"):
                group_steps.append(create_interval_step(2, step["recovery_sec"]))
            
            # Signature: (iterations: int, workout_steps: list, step_order: int)
            steps.append(create_repeat_group(reps, group_steps, step_order))
            step_order += 1
        else:
            steps.append(create_interval_step(step_order, step.get("duration_sec", 1200)))
            step_order += 1

    if not steps:
        # Fall back to a single plain step covering the whole planned duration
        steps.append(create_interval_step(1, session.get("duration_min", 30) * 60))

    return steps


def push_workout(client: garminconnect.Garmin, session: dict, on_date: date) -> str:
    """
    session = {
        "sport": "run",
        "title": "Easy Run",
        "duration_min": 30,
        "structure": [...]   # optional, see _build_steps
    }
    Returns the Garmin workout id. Raises for non-running sports.
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
    """Deletes a previously pushed workout (removes it from the watch's calendar)."""
    try:
        client.delete_workout(workout_id)
    except Exception as e:
        print(f"Could not remove workout {workout_id}: {e}")