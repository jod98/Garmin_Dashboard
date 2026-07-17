"""
Performance & Health Dashboard
A Streamlit dashboard that pulls live data from Garmin Connect
(via the garminconnect library) for a Garmin Forerunner 165 or any
Garmin device: running / cycling / swimming activities plus
general health metrics (HRV, sleep, training load, Body Battery).
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
# PAGE CONFIG + STYLE
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Performance & Health Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
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

/* KPI cards */
.kpi-card {{
    background: #131C2E;
    border: 1px solid #1E2A40;
    border-radius: 10px;
    padding: 18px 20px;
    height: 100%;
}}
.kpi-label {{
    color: {MUTED};
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
}}
.kpi-value {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.9rem;
    font-weight: 600;
    color: #E8ECF3;
    line-height: 1.1;
}}
.kpi-sub {{
    color: {MUTED};
    font-size: 0.8rem;
    margin-top: 4px;
}}
.section-title {{
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 1.15rem;
    color: #E8ECF3;
    border-left: 3px solid {ACCENT};
    padding-left: 10px;
    margin: 22px 0 12px 0;
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


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_activity_hr_series(_client, activity_id):
    try:
        details = _client.get_activity_details(activity_id)
        metrics = details.get("activityDetailMetrics", [])
        descriptors = {
            d["key"]: i for i, d in enumerate(details.get("metricDescriptors", []))
        }
        hr_idx = descriptors.get("directHeartRate")
        time_idx = descriptors.get("sumDuration")
        if hr_idx is None:
            return pd.DataFrame()
        rows = []
        for m in metrics:
            vals = m.get("metrics", [])
            rows.append(
                {
                    "seconds": vals[time_idx] if time_idx is not None else None,
                    "heart_rate": vals[hr_idx],
                }
            )
        return pd.DataFrame(rows)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


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
    return f"{mn}:{s:02d} /km"


def kpi_card(label, value, sub=""):
    st.markdown(
        f"""<div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-sub">{sub}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def sport_tab(df, sport_key, sport_label):
    sport_df = df[df["sport"] == sport_key].copy()
    if sport_df.empty:
        st.info(f"No {sport_label.lower()} activities found in the selected range.")
        return

    total_dist = sport_df["distance_km"].sum()
    total_time = sport_df["duration_s"].sum()
    avg_hr_series = sport_df["avg_hr"].dropna()
    avg_hr = round(avg_hr_series.mean(), 0) if not avg_hr_series.empty else "-"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Distance", f"{total_dist:.1f} km", f"{len(sport_df)} sessions")
    with c2:
        kpi_card("Total Time", sec_to_hms(total_time))
    with c3:
        kpi_card("Avg Heart Rate", f"{avg_hr} bpm" if avg_hr != "-" else "-")
    with c4:
        best_dist = sport_df["distance_km"].max()
        kpi_card("Longest Session", f"{best_dist:.1f} km")

    st.markdown('<div class="section-title">Distance Trend (Week-to-Week Breakdown)</div>', unsafe_allow_html=True)
    trend = sport_df.sort_values("date")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=trend["date"],
            y=trend["distance_km"],
            marker_color=SPORT_COLORS[sport_key],
            name="Distance (km)",
        )
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        height=280,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-title">Last 10 Completed Activities</div>', unsafe_allow_html=True)
    show_cols = ["date", "name", "distance_km", "duration_hms", "avg_hr", "max_hr", "pace"]
    st.dataframe(
        sport_df.sort_values("date", ascending=False).head(10)[show_cols],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown('<div class="section-title">Heart Rate Graph - Most Recent Session</div>', unsafe_allow_html=True)
    latest = sport_df.sort_values("date", ascending=False).iloc[0]
    hr_series = fetch_activity_hr_series(st.session_state.client, latest["activity_id"])
    if not hr_series.empty:
        fig2 = go.Figure()
        fig2.add_trace(
            go.Scatter(
                x=hr_series["seconds"],
                y=hr_series["heart_rate"],
                mode="lines",
                line=dict(color=ACCENT_2, width=2),
                name="Heart Rate",
            )
        )
        fig2.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Elapsed time (s)",
            yaxis_title="bpm",
            margin=dict(l=10, r=10, t=10, b=10),
            height=280,
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.caption("No second-by-second heart rate data available for this session.")


# --------------------------------------------------------------------------
# SIDEBAR
# --------------------------------------------------------------------------
st.sidebar.markdown("### Dashboard Filters")
days_back = st.sidebar.slider("Historical Activity Window (days)", 7, 90, 28)
weekly_goal = st.sidebar.number_input("Weekly Running Goal (km)", min_value=5, max_value=150, value=40, step=5)

if st.sidebar.button("Refresh now", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption("Data auto-refreshes every 15 minutes.")

# --------------------------------------------------------------------------
# CONNECT
# --------------------------------------------------------------------------
client, error = get_garmin_client()
if error:
    st.error(f"Garmin connection issue: {error}")
    st.stop()

st.session_state.client = client
st.sidebar.success("Connected to Garmin ✓")

today = dt.date.today()
start_date = today - timedelta(days=days_back)

# --------------------------------------------------------------------------
# LOAD HEALTH & ACTIVITY DATA
# --------------------------------------------------------------------------
today_str = today.strftime("%Y-%m-%d")
stats = fetch_day_stats(client, today_str)
hrv = fetch_hrv(client, today_str)
sleep = fetch_sleep(client, today_str)
training_status = fetch_training_status(client, today_str)
body_battery_raw = fetch_body_battery(client, (today - timedelta(days=6)).strftime("%Y-%m-%d"), today_str)
raw_activities = fetch_activities(client, 0, 200)

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
# HEADER SECTION
# --------------------------------------------------------------------------
st.title("Performance & Health Dashboard")
st.caption(f"Last synced {dt.datetime.now().strftime('%d %b %Y, %H:%M')}")

# --------------------------------------------------------------------------
# TOP HEALTH SNAPSHOT
# --------------------------------------------------------------------------
st.markdown('<div class="section-title">Today\'s Snapshot</div>', unsafe_allow_html=True)
h1, h2, h3, h4, h5 = st.columns(5)

with h1:
    vo2_max_val = "-"
    status_label = "Unknown"
    if isinstance(training_status, dict):
        vo2_max_val = training_status.get("vo2Max", "-")
        recent_status = training_status.get("mostRecentTrainingStatus") or {}
        status_data = recent_status.get("latestTrainingStatusData") or {}
        status_label = status_data.get("trainingStatus", "Unknown")
    kpi_card("VO2 Max", f"{vo2_max_val}", f"Status: {status_label}")

with h2:
    rhr = stats.get("restingHeartRate", "-")
    kpi_card("Resting HR", f"{rhr} bpm" if rhr != "-" else "-")

with h3:
    hrv_val = "-"
    if isinstance(hrv, dict):
        hrv_val = hrv.get("hrvSummary", {}).get("lastNightAvg", "-")
    kpi_card("HRV (Overnight Avg)", f"{hrv_val} ms" if hrv_val != "-" else "-")

with h4:
    sleep_string = "-"
    sleep_score = "-"
    if isinstance(sleep, dict):
        dto = sleep.get("dailySleepDTO", {})
        sleep_secs = dto.get("sleepTimeSeconds")
        sleep_score = dto.get("sleepScore", "-")
        if sleep_secs:
            sleep_string = sec_to_hms(sleep_secs)
    kpi_card("Sleep", f"{sleep_string}", f"Score: {sleep_score}")

with h5:
    bb_val = "-"
    if body_battery_raw:
        try:
            last_reading = body_battery_raw[-1]
            levels = last_reading.get("bodyBatteryValuesArray", [])
            if levels:
                bb_val = levels[-1][1]
        except Exception:  # noqa: BLE001
            pass
    kpi_card("Body Battery", f"{bb_val}" if bb_val != "-" else "-")

# --------------------------------------------------------------------------
# STRICT MONDAY-SUNDAY WEEKLY VOLUME TARGET TRACKER + TRAINING LOAD
# --------------------------------------------------------------------------
st.markdown('<div class="section-title">Weekly Tracker &amp; Load Status</div>', unsafe_allow_html=True)
w1, w2, w3 = st.columns(3)

# Calculate runs in the current strict Monday - Sunday calendar block
start_of_week = today - timedelta(days=today.weekday())  # Mon
end_of_week = start_of_week + timedelta(days=6)          # Sun

if not df.empty:
    weekly_runs = df[(df["sport"] == "running") & (df["date"] >= start_of_week) & (df["date"] <= end_of_week)]
    current_weekly_km = weekly_runs["distance_km"].sum()
else:
    current_weekly_km = 0.0

kms_left = max(0.0, weekly_goal - current_weekly_km)

with w1:
    kpi_card(
        "Current Week Volume", 
        f"{current_weekly_km:.1f} / {weekly_goal} km", 
        f"Mon {start_of_week.strftime('%b %d')} - Sun {end_of_week.strftime('%b %d')}"
    )
with w2:
    status_msg = "Goal achieved! 🎉" if kms_left == 0 else f"{kms_left:.1f} km left to hit target"
    kpi_card("Distance Remaining", f"{kms_left:.1f} km", status_msg)
with w3:
    load_val = "-"
    if isinstance(training_status, dict):
        load_balance = training_status.get("mostRecentTrainingLoadBalance") or {}
        metrics_status = load_balance.get("metricsTrainingStatus") or {}
        load_val = metrics_status.get("trainingLoad", "-")
    kpi_card("Training Load", f"{load_val}" if load_val != "-" else "-")

# --------------------------------------------------------------------------
# SPORTS TABS OVERVIEW
# --------------------------------------------------------------------------
if df.empty:
    st.info("No running, cycling, or swimming activities found in your history window.")
else:
    tab_run, tab_bike, tab_swim = st.tabs(["🏃 Running", "🚴 Cycling", "🏊 Swimming"])
    with tab_run:
        sport_tab(df, "running", "Running")
    with tab_bike:
        sport_tab(df, "cycling", "Cycling")
    with tab_swim:
        sport_tab(df, "swimming", "Swimming")

st.divider()
st.caption("Built with Streamlit + garminconnect. Data automatically pulls directly from your Garmin profile.")