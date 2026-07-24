"""
"Current Plan" page: lets the athlete set/update their overall goals and see
the resulting plan synced to Garmin Connect.

This action follows this pattern:
  1. Load the week's EXISTING sessions from the database (so we know what's
     currently pushed to Garmin, including each session's "garmin_workout_id").
  2. Ask the plan generator for a new set of sessions.
  3. Call garmin_client.sync_workouts(), which deletes the old plan's future
     workouts from the Garmin calendar and pushes the new plan's - this is
     what stops you ending up with both an old (e.g. pre-injury) and new
     plan sitting on your watch's calendar at once.
  4. Save the result (now including fresh "garmin_workout_id" values) back
     to the database, so the NEXT replan can clean these up in turn.
"""
import sys
import os
from datetime import date, timedelta

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core import db  # noqa: E402
from core.plan_generator import generate_week_plan, format_goal_aesthetically
from core.garmin_client import get_client, fetch_week_summary, sync_workouts

st.title("📋 Current Plan & Adjustments")

# --- 1. FETCH SAVED DATA ---
current = db.get_athlete_profile() or {}
saved_raw_notes = current.get("goal_text") or current.get("goal") or ""
saved_formatted_summary = current.get("constraints_text") or current.get("constraints") or ""

def most_recent_monday(d: date) -> date:
    """Returns the Monday on or before `d` - our convention for a week's `week_start`."""
    return d - timedelta(days=d.weekday())

week_start = most_recent_monday(date.today())

# --- 2. ACTIVE PLAN SUMMARY DISPLAY ---
if saved_formatted_summary:
    st.subheader("📌 Current Active Plan Summary")
    with st.container(border=True):
        st.markdown(saved_formatted_summary)
elif saved_raw_notes:
    st.subheader("📌 Current Active Plan Summary")
    with st.container(border=True):
        st.markdown(saved_raw_notes)

st.markdown("---")

# --- 3. OVERALL PLAN GOALS & PREFERENCES ---
st.subheader("🎯 Update Long-Term Goals & Schedule")
st.caption("Change target races, target times, weekly run availability, or overall training strategy.")

user_details = st.text_area(
    "Overall Plan Details & Goals",
    value=saved_raw_notes,
    placeholder=(
        "e.g. Training for a Half Marathon in November aiming for sub 1:45. "
        "Available to run 4 days a week: Tuesdays (intervals), Thursdays (tempo), "
        "Saturdays (easy), and Sundays (long run)."
    ),
    height=180,
)

if st.button("✨ Save Goals & Regenerate Full Block", use_container_width=True):
    if not user_details.strip():
        st.warning("Please provide your goal details before saving.")
    else:
        with st.spinner("Refining goals with Claude, regenerating training plan, and syncing to Garmin..."):
            try:
                formatted_summary = format_goal_aesthetically(user_details)

                db.update_athlete_profile(
                    user_details,
                    formatted_summary
                )

                # Load what's currently saved/pushed for this week BEFORE we
                # overwrite it - same reason as the quick-adjustment flow
                # above: sync_workouts needs the old plan's workout ids.
                existing_plan = db.get_plan(week_start) or {}
                existing_sessions = existing_plan.get("sessions", [])

                updated_profile = db.get_athlete_profile() or {}
                garmin_client = get_client()
                recent_summary = fetch_week_summary(garmin_client, week_start - timedelta(days=14), week_start)
                recent_plans = [db.get_plan(week_start - timedelta(days=7))]
                recent_feedback = [db.get_feedback(week_start - timedelta(days=7))]

                plan_data = generate_week_plan(
                    week_start=week_start,
                    profile=updated_profile,
                    recent_plans=[p for p in recent_plans if p],
                    recent_feedback=[f for f in recent_feedback if f],
                    garmin_summary=recent_summary
                )
                new_sessions = plan_data.get("sessions", [])

                # Same delete-old-then-push-new swap as the quick adjustment
                # above, so a full block regeneration can't leave duplicate
                # workouts on the watch either.
                new_sessions = sync_workouts(
                    garmin_client,
                    old_sessions=existing_sessions,
                    new_sessions=new_sessions,
                    from_date=date.today(),
                )
                pushed_count = sum(1 for s in new_sessions if s.get("garmin_workout_id"))

                db.save_plan(
                    week_start,
                    new_sessions,
                    plan_data.get("rationale", "")
                )

                st.success(f"✅ Goals saved! Training plan regenerated and synced {pushed_count} workouts to Garmin.")
                st.rerun()

            except Exception as e:
                st.error(f"Error processing update: {e}")
