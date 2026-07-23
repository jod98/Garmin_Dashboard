import sys
import os
from datetime import date, timedelta

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core import db  # noqa: E402
from core.plan_generator import generate_week_plan, regenerate_partial_week, format_goal_aesthetically
from core.garmin_client import get_client, fetch_week_summary, push_workout

st.title("📋 Current Plan & Adjustments")

# --- 1. FETCH SAVED DATA ---
current = db.get_athlete_profile() or {}
saved_raw_notes = current.get("goal_text") or current.get("goal") or ""
saved_formatted_summary = current.get("constraints_text") or current.get("constraints") or ""

def most_recent_monday(d: date) -> date:
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

# --- 3. QUICK MID-WEEK ADJUSTMENTS ---
st.subheader("🩹 Quick Adjustment (Mid-Week Issue)")
st.caption("Need to adjust your current week due to an injury, sickness, or unexpected schedule conflict? Tell Claude what happened and your plan will update immediately.")

with st.form("quick_adjustment_form"):
    adj_reason = st.selectbox(
        "Reason for adjustment",
        ["injury", "time_off", "other"],
        format_func=lambda x: {
            "injury": "🩹 Injury / Niggle / Pain",
            "time_off": "✈️ Time Off / Vacation / Busy",
            "other": "⚡ General Adjustment"
        }[x]
    )
    
    col_dates1, col_dates2 = st.columns(2)
    with col_dates1:
        affected_start = st.date_input("Start date affected", value=date.today())
    with col_dates2:
        affected_end = st.date_input("End date affected", value=date.today() + timedelta(days=2))
        
    adj_notes = st.text_area(
        "Notes for your coach",
        placeholder="e.g. Left Achilles pain after yesterday's run. Need to rest or cross-train until Thursday."
    )
    
    btn_adjust = st.form_submit_button("🚨 Regenerate Current Week", type="primary", use_container_width=True)

if btn_adjust:
    if not adj_notes.strip():
        st.warning("Please enter a short note describing the issue.")
    else:
        with st.spinner("Adjusting your current week and syncing to Garmin..."):
            try:
                existing_plan = db.get_plan(week_start) or {}
                existing_sessions = existing_plan.get("sessions", [])

                adjusted_data = regenerate_partial_week(
                    profile=current,
                    existing_sessions=existing_sessions,
                    reason=adj_reason,
                    affected_start=affected_start.isoformat(),
                    affected_end=affected_end.isoformat(),
                    notes=adj_notes
                )

                db.save_plan(
                    week_start,
                    adjusted_data.get("sessions", []),
                    adjusted_data.get("rationale", "")
                )

                # Sync updated sessions to Garmin
                garmin_client = get_client()
                pushed_count = 0
                for session in adjusted_data.get("sessions", []):
                    s_date = date.fromisoformat(session["date"])
                    if session.get("sport") == "run" and session.get("structure"):
                        try:
                            push_workout(garmin_client, session, s_date)
                            pushed_count += 1
                        except Exception:
                            pass

                st.success(f"✅ Current week updated! Synced {pushed_count} workouts to Garmin.")
                st.rerun()
            except Exception as e:
                st.error(f"Error adjusting plan: {e}")

st.markdown("---")

# --- 4. OVERALL PLAN GOALS & PREFERENCES ---
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

                db.save_plan(
                    week_start, 
                    plan_data.get("sessions", []), 
                    plan_data.get("rationale", "")
                )

                pushed_count = 0
                for session in plan_data.get("sessions", []):
                    s_date = date.fromisoformat(session["date"])
                    if session.get("sport") == "run" and session.get("structure"):
                        try:
                            push_workout(garmin_client, session, s_date)
                            pushed_count += 1
                        except Exception:
                            pass

                st.success(f"✅ Goals saved! Training plan regenerated and synced {pushed_count} workouts to Garmin.")
                st.rerun()

            except Exception as e:
                st.error(f"Error processing update: {e}")