"""
"This Week" page: today's health snapshot (VO2 max, resting HR, HRV, Body
Battery, sleep, steps), this week's planned running sessions pulled live
from the Garmin Connect calendar (with completion status), and this week's
run/bike/swim activity totals and logs.

This is the default/landing page - see app.py for the st.navigation() entry
that wires this file up alongside pages/2_Current_Plan.py and
pages/1_Weekly_Check-In.py as the app's three pages. All Garmin Connect
fetch functions and formatting/rendering helpers used below live in
core/dashboard_data.py.
"""
import sys
import os
import datetime as dt
from datetime import timedelta

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core.dashboard_data import (  # noqa: E402
    get_garmin_client,
    fetch_activities,
    fetch_day_stats,
    fetch_hrv,
    get_sync_timestamp,
    fetch_latest_sleep,
    fetch_sleep_history,
    fetch_body_battery,
    fetch_training_status,
    fetch_user_profile,
    fetch_max_metrics_with_lookback,
    fetch_planned_sessions_live,
    m_to_km,
    sec_to_hms,
    sec_to_hr_min,
    pace_min_per_km,
    build_kpi_html,
    find_vo2,
    find_sleep_score,
    interpret_hrv,
    interpret_body_battery,
    sport_tab,
    render_planned_sessions,
)

# --------------------------------------------------------------------------
# SIDEBAR CONTROLS
# --------------------------------------------------------------------------
st.sidebar.markdown("### Settings")
days_back = st.sidebar.slider("History Window (days)", 7, 90, 28)
if st.sidebar.button("Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


# --------------------------------------------------------------------------
# DATA RETRIEVAL & PROCESSING PIPELINE
# --------------------------------------------------------------------------
client, error = get_garmin_client()
if error:
    st.error(f"Connection issue: {error}")
    st.stop()

st.session_state.client = client

today = dt.date.today()
history_days = max(days_back, today.weekday() + 1)
start_date = today - timedelta(days=history_days)
today_str = today.strftime("%Y-%m-%d")

start_of_week = today - timedelta(days=today.weekday())
end_of_week = start_of_week + timedelta(days=6)

# Execute API queries
stats = fetch_day_stats(client, today_str)
hrv = fetch_hrv(client, today_str)
sleep_date, sleep = fetch_latest_sleep(client)
sleep_history = fetch_sleep_history(client, 7)
training_status = fetch_training_status(client, today_str)
user_profile = fetch_user_profile(client)
max_metrics = fetch_max_metrics_with_lookback(client)
body_battery_raw = fetch_body_battery(client, (today - timedelta(days=6)).strftime("%Y-%m-%d"), today_str)
raw_activities = fetch_activities(client, 0, 50)

# Parse historical activities list
records = []
for a in raw_activities:
    a_type = (a.get("activityType", {}) or {}).get("typeKey", "")
    if any(k in a_type for k in ["running", "run"]):
        sport = "running"
    elif any(k in a_type for k in ["cycling", "biking", "bike"]):
        sport = "cycling"
    elif "swim" in a_type:
        sport = "swimming"
    else:
        continue

    start_str = a.get("startTimeLocal", "")
    try:
        a_date = dt.datetime.strptime(start_str[:10], "%Y-%m-%d").date()
    except ValueError:
        continue

    distance_m = a.get("distance", 0) or 0
    duration_s = a.get("duration", 0) or 0
    records.append(
        {
            "sport": sport,
            "date": a_date,
            "distance_km": m_to_km(distance_m),
            "duration_s": duration_s,
            "duration_hms": sec_to_hms(duration_s),
            "avg_hr": a.get("averageHR"),
            "vo2": a.get("vo2MaxValue") or a.get("vO2MaxValue") or a.get("vO2maxValue"),
            "pace": pace_min_per_km(distance_m, duration_s) if sport != "cycling" else "-",
        }
    )

df = pd.DataFrame(records)


# --------------------------------------------------------------------------
# DEEP INSPECTION & METRIC RESOLUTION
# --------------------------------------------------------------------------
vo2_max_val = "-"
status_label = "Active"

# Priority 1: Search training status dictionary
found_vo2_target = find_vo2(training_status)

# Priority 2: Search max metrics 30-day loop dump
if not found_vo2_target:
    found_vo2_target = find_vo2(max_metrics)

# Priority 3: Search User Profile data structure
if not found_vo2_target:
    found_vo2_target = find_vo2(user_profile)

# Priority 4: Look for embedded values directly within historical activity objects
if not found_vo2_target and not df.empty:
    valid_activity_vo2 = df[df["vo2"].notna() & (df["vo2"] != "-")].copy()
    if not valid_activity_vo2.empty:
        found_vo2_target = valid_activity_vo2.sort_values("date", ascending=False).iloc[0]["vo2"]

# Convert and cast final VO2 data safely
if found_vo2_target is not None:
    try:
        vo2_max_val = int(round(float(found_vo2_target)))
    except Exception:  # noqa: BLE001
        pass

# Format Training Status label
if isinstance(training_status, dict) and training_status:
    recent_status = training_status.get("mostRecentTrainingStatus", {})
    if isinstance(recent_status, dict):
        status_data = recent_status.get("latestTrainingStatusData", {})
        if isinstance(status_data, dict):
            status_label = status_data.get("trainingStatus") or status_label
else:
    status_label = "Productive" if vo2_max_val != "-" else "No Data"

status_label = str(status_label).replace("_", " ").title()

# Parse daily vital statistics safely
rhr = stats.get("restingHeartRate", "-") if isinstance(stats, dict) else "-"
hrv_val = hrv.get("hrvSummary", {}).get("lastNightAvg", "-") if isinstance(hrv, dict) else "-"

sleep_string = "-"
sleep_score = "-"
sleep_date_used = "-"

if sleep:
    sleep_date_used = sleep_date
    dto = sleep.get("dailySleepDTO", {})

    if isinstance(dto, dict):
        secs = dto.get("sleepTimeSeconds")
        if secs:
            sleep_string = sec_to_hr_min(secs)

    score = find_sleep_score(sleep)
    if score is not None:
        sleep_score = score

avg_sleep_str = sec_to_hr_min(sum(sleep_history) / len(sleep_history)) if sleep_history else "-"

bb_val = "-"
if body_battery_raw and isinstance(body_battery_raw, list):
    try:
        levels = body_battery_raw[-1].get("bodyBatteryValuesArray", [])
        if levels:
            bb_val = levels[-1][1]
    except Exception:  # noqa: BLE001
        pass

steps_val = stats.get("totalSteps", "-") if isinstance(stats, dict) else "-"


# --------------------------------------------------------------------------
# MAIN DASHBOARD UI LAYOUT
# --------------------------------------------------------------------------
st.title("Performance & Health Dashboard")
st.caption(f"Last synchronized: {get_sync_timestamp().strftime('%H:%M')}")

# Snapshot Metrics Grid
st.markdown('<div class="section-title">Today\'s Snapshot</div>', unsafe_allow_html=True)

hrv_note = interpret_hrv(hrv, hrv_val)
bb_note = interpret_body_battery(bb_val)

c1 = build_kpi_html("VO2 Max", f"{vo2_max_val}", status_label)
c2 = build_kpi_html("Rest Heart Rate", f"{rhr} bpm" if rhr != "-" else "-", "")
c3 = build_kpi_html("HRV (Night)", f"{hrv_val} ms" if hrv_val != "-" else "-", hrv_note)
c4 = build_kpi_html("Body Battery", f"{bb_val}" if bb_val != "-" else "-", bb_note)
sleep_sub_display = (
    f"Score: {sleep_score}<br>7d Avg: {avg_sleep_str}" if sleep_date_used != "-" else "No Data"
)

c5 = build_kpi_html("Sleep", sleep_string, sleep_sub_display)
c6 = build_kpi_html(
    "Steps",
    f"{steps_val:,}" if isinstance(steps_val, (int, float)) else "-",
    "Target: 7,500-10,000"
)

snapshot_html = f'<div class="snapshot-grid">{c1}{c2}{c3}{c4}{c5}{c6}</div>'
st.markdown(snapshot_html, unsafe_allow_html=True)

# Planned Sessions Section
st.markdown('<div class="section-title">This Week: Planned Sessions</div>', unsafe_allow_html=True)

planned_sessions = fetch_planned_sessions_live(client, start_of_week, end_of_week)

# Extract dates of recorded activities to cross-verify completion
completed_dates = set(df["date"]) if not df.empty else set()

render_planned_sessions(planned_sessions, completed_dates=completed_dates)

# Sport Tabs & Progress Section
st.markdown('<div class="section-title">This Week: Progress</div>', unsafe_allow_html=True)

if df.empty:
    st.info("No activities tracked inside your current history range.")
else:
    tab_run, tab_bike, tab_swim = st.tabs(["🏃 Run", "🚴 Bike", "🏊 Swim"])
    with tab_run:
        sport_tab(df, "running", start_of_week, end_of_week)
    with tab_bike:
        sport_tab(df, "cycling", start_of_week, end_of_week)
    with tab_swim:
        sport_tab(df, "swimming", start_of_week, end_of_week)

st.divider()

