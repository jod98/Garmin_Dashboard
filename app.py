"""
Performance & Health Dashboard (Mobile Optimized)
A compact, mobile-friendly Streamlit dashboard pulling live data 
from Garmin Connect for running, cycling, and swimming.
"""

import datetime as dt
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
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
    page_title="Garmin Pulse",
    page_icon="📈",
    layout="centered",  # Better for single-column mobile viewports
    initial_sidebar_state="collapsed",  # Keep sidebar out of the way on mobile
)

ACCENT = "#2DD4BF"
ACCENT_2 = "#F5A623"
MUTED = "#8792A6"
SPORT_COLORS = {"running": "#2DD4BF", "cycling": "#F5A623", "swimming": "#7C9CF5"}

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght=500;600;700&family=Inter:wght=400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}
h1, h2, h3, .metric-label {{
    font-family: 'Space Grotesk', sans-serif !important;
}}

/* Tighten mobile padding */
.block-container {{
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}}

/* Compact KPI cards for small screens */
.kpi-card {{
    background: #131C2E;
    border: 1px solid #1E2A40;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 8px;
    height: 100%;
}}
.kpi-label {{
    color: {MUTED};
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 2px;
}}
.kpi-value {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.4rem;
    font-weight: 600;
    color: #E8ECF3;
    line-height: 1.1;
}}
.kpi-sub {{
    color: {MUTED};
    font-size: 0.75rem;
    margin-top: 2px;
}}
.section-title {{
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 1.05rem;
    color: #E8ECF3;
    border-left: 3px solid {ACCENT};
    padding-left: 8px;
    margin: 18px 0 10px 0;
}}

/* Ensure tabs stretch full mobile width nicely */
.stTabs [data-baseweb="tab-list"] {{
    gap: 8px;
}}
.stTabs [data-baseweb="tab"] {{
    padding-left: 8px !important;
    padding-right: 8px !important;
    font-size: 0.9rem !important;
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
        return None, "Login failed - check your Garmin email/password in secrets."
    except GarminConnectTooManyRequestsError:
        return None, "Garmin is rate-limiting logins right now. Try again shortly."
    except GarminConnectConnectionError:
        return None, "Could not reach Garmin Connect. Try again shortly."
    except Exception as exc:  # noqa: BLE001
        return None, f"Unexpected error connecting to Garmin: {exc}"


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
# MOBILITY & RENDERING HELPERS
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


def render_mobile_grid(items):
    """
    Splits a list of KPI item dicts into rows of 2 columns max.
    Streamlit handles 2 side-by-side items decently on modern smartphones.
    """
    for i in range(0, len(items), 2):
        row_items = items[i:i+2]
        cols = st.columns(len(row_items))
        for idx, item in enumerate(row_items):
            with cols[idx]:
                kpi_card(item["label"], item["value"], item.get("sub", ""))


def sport_tab(df, sport_key, sport_label):
    sport_df = df[df["sport"] == sport_key].copy()
    if sport_df.empty:
        st.info(f"No {sport_label.lower()} activities found.")
        return

    total_dist = sport_df["distance_km"].sum()
    total_time = sport_df["duration_s"].sum()
    avg_hr_series = sport_df["avg_hr"].dropna()
    avg_hr = round(avg_hr_series.mean(), 0) if not avg_hr_series.empty else "-"
    best_dist = sport_df["distance_km"].max()

    # Mobile optimized 2x2 summary layout
    sport_metrics = [
        {"label": "Total Distance", "value": f"{total_dist:.1f} km", "sub": f"{len(sport_df)} sessions"},
        {"label": "Total Time", "value": sec_to_hms(total_time)},
        {"label": "Avg Heart Rate", "value": f"{avg_hr} bpm" if avg_hr != "-" else "-"},
        {"label": "Longest Session", "value": f"{best_dist:.1f} km"}
    ]
    render_mobile_grid(sport_metrics)

    st.markdown('<div class="section-title">Distance Trend</div>', unsafe_allow_html=True)
    trend = sport_df.sort_values("date")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=trend["date"],
            y=trend["distance_km"],
            marker_color=SPORT_COLORS[sport_key],
            name="KM",
        )
    )
    # Reduced height and minimal margins for tiny mobile screens
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=5, r=5, t=5, b=5),
        height=180,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Last 5 Activities</div>', unsafe_allow_html=True)
    
    # Pruned down table columns to prevent tiny horizontal scroll chains on mobile
    show_cols = ["date", "distance_km", "duration_hms", "pace"]
    df_display = sport_df.sort_values("date", ascending=False).head(5)[show_cols].copy()
    df_display.columns = ["Date", "Dist (km)", "Time", "Pace"]
    
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
    )


# --------------------------------------------------------------------------
# SIDEBAR (FILTERS COLLAPSED BY DEFAULT ON MOBILE)
# --------------------------------------------------------------------------
st.sidebar.markdown("### Settings")
days_back = st.sidebar.slider("History Window (days)", 7, 90, 28)
if st.sidebar.button("Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# --------------------------------------------------------------------------
# CONNECT & FETCH
# --------------------------------------------------------------------------
client, error = get_garmin_client()
if error:
    st.error(f"Connection issue: {error}")
    st.stop()

st.session_state.client = client

today = dt.date.today()
start_date = today - timedelta(days=days_back)
today_str = today.strftime("%Y-%m-%d")

stats = fetch_day_stats(client, today_str)
hrv = fetch_hrv(client, today_str)
sleep = fetch_sleep(client, today_str)
training_status = fetch_training_status(client, today_str)
body_battery_raw = fetch_body_battery(client, (today - timedelta(days=6)).strftime("%Y-%m-%d"), today_str)
raw_activities = fetch_activities(client, 0, 150)

# Process raw fields
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
            "activity_id": a.get("activityId"),
            "sport": sport,
            "date": a_date,
            "name": a.get("activityName", "Untitled"),
            "distance_km": m_to_km(distance_m),
            "duration_s": duration_s,
            "duration_hms": sec_to_hms(duration_s),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "pace": pace_min_per_km(distance_m, duration_s) if sport != "cycling" else "-",
        }
    )

df = pd.DataFrame(records)

# --------------------------------------------------------------------------
# RENDER UI
# --------------------------------------------------------------------------
st.title("Garmin Pulse")
st.caption(f"Synced: {dt.datetime.now().strftime('%H:%M')}")

# Extract Health Stats
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

# Render Health Dashboard to clean mobile grid
st.markdown('<div class="section-title">Today\'s Snapshot</div>', unsafe_allow_html=True)
health_metrics = [
    {"label": "VO2 Max", "value": f"{vo2_max_val}", "sub": status_label},
    {"label": "Resting HR", "value": f"{rhr} bpm" if rhr != "-" else "-"},
    {"label": "HRV (Overnight)", "value": f"{hrv_val} ms" if hrv_val != "-" else "-"},
    {"label": "Body Battery", "value": f"{bb_val}" if bb_val != "-" else "-"},
    {"label": "Sleep Duration", "value": f"{sleep_string}", "sub": f"Score: {sleep_score}"}
]
render_mobile_grid(health_metrics)

# Sports Overview Tabs
st.markdown('<div class="section-title">Activity Progress</div>', unsafe_allow_html=True)
if df.empty:
    st.info("No recorded running, cycling, or swimming found.")
else:
    tab_run, tab_bike, tab_swim = st.tabs(["🏃 Run", "🚴 Bike", "🏊 Swim"])
    with tab_run:
        sport_tab(df, "running", "Running")
    with tab_bike:
        sport_tab(df, "cycling", "Cycling")
    with tab_swim:
        sport_tab(df, "swimming", "Swimming")

st.divider()