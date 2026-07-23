"""
Run every Monday morning (see .github/workflows/weekly_plan.yml).
Generates this week's plan from the latest feedback + Garmin data, saves it,
pushes structured sessions to the Garmin watch, and emails the human-readable plan.
"""
import sys
import os
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core import db, garmin_client, plan_generator, email_sender  # noqa: E402


def next_monday(d: date) -> date:
    days_ahead = (7 - d.weekday()) % 7 or 7
    return d + timedelta(days=days_ahead)


def main():
    week_start = next_monday(date.today())
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)

    profile = db.get_athlete_profile()
    recent_plans = db.get_recent_plans(limit=4)
    recent_feedback = db.get_recent_feedback(limit=4)

    client = garmin_client.get_client()
    garmin_summary = garmin_client.fetch_week_summary(client, prev_week_start, prev_week_end)

    plan = plan_generator.generate_week_plan(
        week_start, profile, recent_plans, recent_feedback, garmin_summary
    )

    for session in plan["sessions"]:
        if session["sport"] in ("run", "bike", "swim", "walk"):
            try:
                workout_id = garmin_client.push_workout(
                    client, session, date.fromisoformat(session["date"])
                )
                session["garmin_workout_id"] = workout_id
            except Exception as e:
                print(f"Could not push workout for {session['date']}: {e}")

    db.save_plan(week_start, plan["sessions"], plan.get("rationale", ""))
    db.mark_plan_pushed(week_start)
    email_sender.send_weekly_plan_email(week_start, plan)
    print(f"Weekly plan for {week_start} generated, pushed, and emailed.")


if __name__ == "__main__":
    main()
