"""
Performance & Health Dashboard (Mobile-First 2x3 & 2x2 Grid Layouts)
A compact, mobile-friendly Streamlit dashboard pulling live data 
from Garmin Connect with structured health and activity rows.
"""

import datetime as dt
from datetime import timedelta

import pandas as pd
import streamlit as st
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# --------------------------------------------------------------------------
# PAGE CONFIG + MOBILE STYLE
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Garmin Dashboard",
    page_icon="📈",
    layout="centered",  
    initial_sidebar_state="collapsed",  
)

ACCENT = "#2DD4BF"
MUTED = "#8792A6"

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght=500;600;700&family=Inter:wght=400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}

/* Shrink the main header font size by half for mobile viewports */
h1 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.5rem !important; 
    font-weight: 700 !important;
    margin-bottom: 0.25rem !important;
}}

h2, h3, .metric-label {{
    font-family: 'Space Grotesk', sans-serif !important;
}}

.block-container {{
    padding-top: 1rem !important;
    padding-bottom: 2rem !important;
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
}}

/* Ultra-compact cards for mobile rows */
.kpi-card {{
    background: #131C2E;
    border: 1px solid #1E2A40;
    border-radius: 6px;
    padding: 8px 10px;
    margin-bottom: 6px;
    height: 100%;
}}
.kpi-label {{
    color: {MUTED};
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.kpi-value {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.15rem;
    font-weight: 600;
    color: #E8ECF3;
    line-height: 1.1;
}}
.kpi-sub {{
    color: {MUTED};
    font-size: 0.68rem;
    margin-top: 1px;
    line-height: 1.1;
}}
.section-title {{
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 0.98rem;
    color: #E8ECF3;
    border-left: 3px solid {ACCENT};
    padding-left: 8px;
    margin: 16px 0 10px 0;
}}

/* Compact 2x2 grid card styles for specific mobile activities */
.activity-card {{
    background: #18253D;
    border: 1px solid #253552;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
}}
.activity-date {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.75rem;
    color: {ACCENT};
    font-weight: 600;
    margin-bottom: 4px;
}}
.activity-metrics {{
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
    color: #E8ECF3;
}}
.activity-pace {{
    font-size: 0.7rem;
    color: {MUTED};
    margin-top: 2px;
}}

.stTabs [data-baseweb="tab-list"] {{
    gap: 4px;
}}
.stTabs [data-baseweb="tab"] {{
    padding-left: 12px !important;
    padding-right: 12px !important;
    font-size: 0.85rem !important;
}}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# GARMIN CONNECTION
# --------------------------------------------------------------------------
@st.cache_resource(ttl=3600, show_spinner=False)
def get_garmin_client():
    email = st.secrets.get("GARMIN_EMAIL")
    password = st.secrets.get("GARMIN_PASSWORD")
    if not email or not password:
        return None, "Missing GARMIN_EMAIL / GARMIN_PASSWORD in secrets."
    try:
        client = Garmin(email, password)
        client.login()
        return client, None
    except GarminConnectAuthenticationError:
        return None, "Login failed - check your Garmin credentials."
    except GarminConnectTooManyRequestsError:
        return None, "Garmin rate limit active. Try again shortly."
    except GarminConnectConnectionError:
        return None, "Could not reach Garmin Connect."
    except Exception as exc:  # noqa: BLE001
        return None, f"Error: {exc}"


@st.cache_data(ttl=900, show_spinner=False)
def fetch_activities(_client, start, limit):
    return _client.get_activities(start, limit)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_day_stats(_client, date_str):
    try:
        return _client.get_stats(date_str)
    except Exception:  # noqa: BLE001
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_hrv(_client, date_str):
    try:
        return _client.get_hrv_data(date_str)
    except Exception:  # noqa: BLE001
        return None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_sleep(_client, date_str):
    try:
        return _client.get_sleep_data(date_str)
    except Exception:  # noqa: BLE001
        return None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_body_battery(_client, start_date, end_date):
    try:
        return _client.get_body_battery(start_date, end_date)
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=900, show_spinner=False)
def fetch_training_status(_client, date_str):
    try:
        return _client.get_training_status(date_str)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------
def m_to_km(m):
    return round((m or 0) / 1000, 2)


def sec_to_hms(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    mn, s = divmod(rem, 60)
    return f"{h}:{mn:02d}:{s:02d}" if h else f"{mn}:{s:02d}"


def pace_min_per_km(distance_m, duration_s):
    if not distance_m:
        return "-"
    km = distance_m / 1000
    if km == 0:
        return "-"
    pace_s = duration_s / km
    mn, s = divmod(int(pace_s), 60)
    return f"{mn}:{s:02d}/km"


def kpi_card(label, value, sub=""):
    st.markdown(
        f"""<div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-sub">{sub}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def sport_tab(df, sport_key, start_of_week, end_of_week):
    sport_df = df[df["sport"] == sport_key].copy()
    
    # Filter strictly down to this calendar week slice
    this_week_df = sport_df[(sport_df["date"] >= start_of_week) & (sport_df["date"] <= end_of_week)].copy()
    
    total_dist = this_week_df["distance_km"].sum() if not this_week_df.empty else 0.0
    total_time = this_week_df["duration_s"].sum() if not this_week_df.empty else 0
    avg_hr_series = this_week_df["avg_hr"].dropna() if not this_week_df.empty else pd.Series()
    avg_hr = round(avg_hr_series.mean(), 0) if not avg_hr_series.empty else "-"
    best_dist = this_week_df["distance_km"].max() if not this_week_df.empty else 0.0

    # 2x2 Grid for Activity Totals
    c1, c2 = st.columns(2)
    with c1:
        kpi_card("Total Distance", f"{total_dist:.1f} km", f"{len(this_week_df)} sessions")
        kpi_card("Avg Heart Rate", f"{avg_hr} bpm" if avg_hr != "-" else "-")
    with c2:
        kpi_card("Total Time", sec_to_hms(total_time))
        kpi_card("Longest Session", f"{best_dist:.1f} km")

    st.markdown('<div class="section-title">This Week: Activities</div>', unsafe_allow_html=True)
    
    if not this_week_df.empty:
        sorted_week_df = this_week_df.sort_values("date", ascending=False)
        
        # Build strict 2x2 mobile grid chunking for listing the logs
        for i in range(0, len(sorted_week_df), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(sorted_week_df):
                    row = sorted_week_df.iloc[i + j]
                    date_label = row["date"].strftime("%a, %b %d")
                    pace_line = f'<div class="activity-pace">Pace: {row["pace"]}</div>' if row["pace"] != "-" else ""
                    
                    cols[j].markdown(
                        f"""
                        <div class="activity-card">
                            <div class="activity-date">{date_label}</div>
                            <div class="activity-metrics">
                                <strong>{row['distance_km']:.2f} km</strong>
                                <span>{row['duration_hms']}</span>
                            </div>
                            {pace_line}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
    else:
        st.caption("No activities recorded yet for this calendar week.")


# --------------------------------------------------------------------------
# SIDEBAR
# --------------------------------------------------------------------------
st.sidebar.markdown("### Settings")
days_back = st.sidebar.slider("History Window (days)", 7, 90, 28)
if st.sidebar.button("Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# --------------------------------------------------------------------------
# CONNECT & CALENDAR CALCULATIONS
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

# Static week parameters for data parsing
start_of_week = today - timedelta(days=today.weekday())  # Mon
end_of_week = start_of_week + timedelta(days=6)          # Sun

stats = fetch_day_stats(client, today_str)
hrv = fetch_hrv(client, today_str)
sleep = fetch_sleep(client, today_str)
training_status = fetch_training_status(client, today_str)
body_battery_raw = fetch_body_battery(client, (today - timedelta(days=6)).strftime("%Y-%m-%d"), today_str)
raw_activities = fetch_activities(client, 0, 150)

# Process activities
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
    if a_date < start_date:
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
            "pace": pace_min_per_km(distance_m, duration_s) if sport != "cycling" else "-",
        }
    )

df = pd.DataFrame(records)

# --------------------------------------------------------------------------
# MAIN UI
# --------------------------------------------------------------------------
st.title("Performance & Health Dashboard")
st.caption(f"Last synchronized: {dt.datetime.now().strftime('%H:%M')}")

# Parse Data Fields
vo2_max_val = "-"
status_label = "Unknown"
if isinstance(training_status, dict):
    vo2_max_val = training_status.get("vo2Max", "-")
    recent_status = training_status.get("mostRecentTrainingStatus") or {}
    status_data = recent_status.get("latestTrainingStatusData") or {}
    status_label = status_data.get("trainingStatus", "Unknown")

rhr = stats.get("restingHeartRate", "-")

hrv_val = "-"
if isinstance(hrv, dict):
    hrv_val = hrv.get("hrvSummary", {}).get("lastNightAvg", "-")

sleep_string = "-"
sleep_score = "-"
if isinstance(sleep, dict):
    dto = sleep.get("dailySleepDTO", {})
    sleep_secs = dto.get("sleepTimeSeconds")
    sleep_score = dto.get("sleepScore", "-")
    if sleep_secs:
        sleep_string = sec_to_hms(sleep_secs)

bb_val = "-"
if body_battery_raw:
    try:
        levels = body_battery_raw[-1].get("bodyBatteryValuesArray", [])
        if levels:
            bb_val = levels[-1][1]
    except Exception:  # noqa: BLE001
        pass

load_val = "-"
if isinstance(training_status, dict):
    load_balance = training_status.get("mostRecentTrainingLoadBalance") or {}
    metrics_status = load_balance.get("metricsTrainingStatus") or {}
    load_val = metrics_status.get("trainingLoad", "-")

# --------------------------------------------------------------------------
# TODAY'S SNAPSHOT (STRICT 2x3 LAYOUT MATRIX)
# --------------------------------------------------------------------------
st.markdown('<div class="section-title">Today\'s Snapshot</div>', unsafe_allow_html=True)

# Row 1: VO2 Max, Rest Heart Rate, HRV
r1_c1, r1_c2, r1_c3 = st.columns(3)
with r1_c1:
    kpi_card("VO2 Max", f"{vo2_max_val}", status_label)
with r1_c2:
    kpi_card("Rest Heart Rate", f"{rhr} bpm" if rhr != "-" else "-")
with r1_c3:
    kpi_card("HRV (Night)", f"{hrv_val} ms" if hrv_val != "-" else "-")

# Row 2: Body Battery, Sleep Duration/Score, Training Load
r2_c1, r2_c2, r2_c3 = st.columns(3)
with r2_c1:
    kpi_card("Body Battery", f"{bb_val}" if bb_val != "-" else "-")
with r2_c2:
    kpi_card("Sleep", f"{sleep_string}", f"Score: {sleep_score}")
with r2_c3:
    kpi_card("Training Load", f"{load_val}" if load_val != "-" else "-")


# --------------------------------------------------------------------------
# ACTIVITY PROGRESS SECTION (2x2 ACTIVITY LOGGER DETAILED UNDER EACH TAB)
# --------------------------------------------------------------------------
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