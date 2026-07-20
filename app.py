"""
Performance & Health Dashboard
A Streamlit dashboard that pulls live data from Garmin Connect
(via the garminconnect library) for a Garmin Forerunner 165 or any
Garmin device: running / cycling / swimming activities plus
general health metrics (HRV, sleep, training load, Body Battery).
"""

import datetime as dt
from datetime import date, timedelta

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
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}

/* Adjusted to ensure title has breathing room and doesn't overlap */
h1 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.2rem !important; 
    font-weight: 700 !important;
    margin-bottom: 0.25rem !important;
    line-height: 1.2 !important;
    white-space: normal !important;
}}

/* Added padding-top to shift everything down slightly from the browser header */
.block-container {{
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
    padding-left: 0.6rem !important;
    padding-right: 0.6rem !important;
}}

/* Custom Fixed Grid Overrides for Mobile Viewports */
.snapshot-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
    margin-bottom: 12px;
}}

.activity-totals-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
    margin-bottom: 12px;
}}

.kpi-card {{
    background: #131C2E;
    border: 1px solid #1E2A40;
    border-radius: 6px;
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 72px;
    box-sizing: border-box;
}}

.kpi-label {{
    color: {MUTED};
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.kpi-value {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.05rem;
    font-weight: 600;
    color: #E8ECF3;
    line-height: 1.1;
    margin: 2px 0;
}}
.kpi-sub {{
    color: {MUTED};
    font-size: 0.62rem;
    line-height: 1.1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.section-title {{
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 0.95rem;
    color: #E8ECF3;
    border-left: 3px solid {ACCENT};
    padding-left: 8px;
    margin: 14px 0 8px 0;
}}

.activity-card {{
    background: #18253D;
    border: 1px solid #253552;
    border-radius: 6px;
    padding: 8px;
    box-sizing: border-box;
}}
.activity-date {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.7rem;
    color: {ACCENT};
    font-weight: 600;
    margin-bottom: 2px;
}}
.activity-metrics {{
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: #E8ECF3;
}}
.activity-pace {{
    font-size: 0.65rem;
    color: {MUTED};
    margin-top: 2px;
}}

.stTabs [data-baseweb="tab-list"] {{
    gap: 4px;
}}
.stTabs [data-baseweb="tab"] {{
    padding-left: 10px !important;
    padding-right: 10px !important;
    font-size: 0.8rem !important;
}}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# GARMIN CONNECTION & CACHING
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
def fetch_latest_sleep(_client):
    """
    Searches backwards for the most recent sleep record.
    Returns:
        (date_string, sleep_json)
    """

    for i in range(30):

        d = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")

        try:

            sleep = _client.get_sleep_data(d)

            if not sleep:
                continue

            dto = sleep.get("dailySleepDTO", {})

            if dto.get("sleepTimeSeconds"):

                return d, sleep

        except Exception:
            continue

    return None, None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_body_battery(_client, start_date, end_date):
    try:
        return _client.get_body_battery(start_date, end_date)
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=900, show_spinner=False)
def fetch_training_status(_client, date_str):
    try:
        return _client.get_training_status(date_str) or {}
    except Exception:  # noqa: BLE001
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_user_profile(_client):
    try:
        return _client.get_user_profile() or {}
    except Exception:  # noqa: BLE001
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_max_metrics_with_lookback(_client):
    for i in range(30):
        d = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            data = _client.get_max_metrics(d)
            if data:
                return data
        except Exception:  # noqa: BLE001
            pass
    return {}


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


def build_kpi_html(label, value, sub=""):
    return f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>'


def find_vo2(obj):
    """Recursively searches for any key/value match containing 'vo2'."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "vo2" in str(k).lower() and v and v != "-":
                if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.', '', 1).isdigit()):
                    return v
            result = find_vo2(v)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_vo2(item)
            if result is not None:
                return result
    return None



def find_sleep_score(obj):
    """
    Searches recursively for the Garmin Sleep Score in nested dictionaries.
    Handles 'sleepScores' -> 'overall' -> 'value' structure.
    """
    if isinstance(obj, dict):
        # Direct check for Garmin's common sleepScores -> overall -> value layout
        if "sleepScores" in obj and isinstance(obj["sleepScores"], dict):
            overall = obj["sleepScores"].get("overall")
            if isinstance(overall, dict) and "value" in overall:
                return overall["value"]
            if isinstance(overall, (int, float)):
                return int(overall)

        # Check for simple top-level keys
        if "sleepScore" in obj:
            val = obj["sleepScore"]
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, dict) and "overallScore" in val:
                return val["overallScore"]

        # Recurse through all keys
        for key, value in obj.items():
            if key in ("overallScore", "sleepScore"):
                if isinstance(value, (int, float)):
                    return int(value)
            res = find_sleep_score(value)
            if res is not None:
                return res

    elif isinstance(obj, list):
        for item in obj:
            res = find_sleep_score(item)
            if res is not None:
                return res

    return None


def sport_tab(df, sport_key, start_of_week, end_of_week):
    sport_df = df[df["sport"] == sport_key].copy()
    this_week_df = sport_df[(sport_df["date"] >= start_of_week) & (sport_df["date"] <= end_of_week)].copy()
    
    total_dist = this_week_df["distance_km"].sum() if not this_week_df.empty else 0.0
    total_time = this_week_df["duration_s"].sum() if not this_week_df.empty else 0
    avg_hr_series = this_week_df["avg_hr"].dropna() if not this_week_df.empty else pd.Series()
    avg_hr = round(avg_hr_series.mean(), 0) if not avg_hr_series.empty else "-"
    best_dist = this_week_df["distance_km"].max() if not this_week_df.empty else 0.0

    card1 = build_kpi_html("Total Distance", f"{total_dist:.1f} km", f"{len(this_week_df)} sessions")
    card2 = build_kpi_html("Total Time", sec_to_hms(total_time))
    card3 = build_kpi_html("Avg Heart Rate", f"{avg_hr} bpm" if avg_hr != "-" else "-")
    card4 = build_kpi_html("Longest Session", f"{best_dist:.1f} km")
    
    grid_html = f'<div class="activity-totals-grid">{card1}{card2}{card3}{card4}</div>'
    st.markdown(grid_html, unsafe_allow_html=True)

    st.markdown('<div class="section-title">This Week: Activities</div>', unsafe_allow_html=True)
    
    if not this_week_df.empty:
        sorted_week_df = this_week_df.sort_values("date", ascending=False)
        
        logs_html = '<div class="activity-totals-grid">'
        for _, row in sorted_week_df.iterrows():
            date_label = row["date"].strftime("%a, %b %d")
            pace_line = f'<div class="activity-pace">Pace: {row["pace"]}</div>' if row["pace"] != "-" else ""
            logs_html += f'<div class="activity-card"><div class="activity-date">{date_label}</div><div class="activity-metrics"><strong>{row["distance_km"]:.2f} km</strong><span>{row["duration_hms"]}</span></div>{pace_line}</div>'
        logs_html += "</div>"
        st.markdown(logs_html, unsafe_allow_html=True)
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
# CONNECT & DATA RETRIEVAL
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
training_status = fetch_training_status(client, today_str)
user_profile = fetch_user_profile(client)
max_metrics = fetch_max_metrics_with_lookback(client)
body_battery_raw = fetch_body_battery(client, (today - timedelta(days=6)).strftime("%Y-%m-%d"), today_str)
raw_activities = fetch_activities(client, 0, 50)

# Parse historical activities
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
# THE RECURSIVE DEEP INSPECTION LAYER
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

# Convert and cast final data safely
if found_vo2_target is not None:
    try:
        vo2_max_val = int(round(float(found_vo2_target)))
    except Exception:  # noqa: BLE001
        pass

# Resilient Training Status text formatting
if isinstance(training_status, dict) and training_status:
    recent_status = training_status.get("mostRecentTrainingStatus", {})
    if isinstance(recent_status, dict):
        status_data = recent_status.get("latestTrainingStatusData", {})
        if isinstance(status_data, dict):
            status_label = status_data.get("trainingStatus") or status_label
else:
    status_label = "Productive" if vo2_max_val != "-" else "No Data"

status_label = str(status_label).replace("_", " ").title()

# Parse remaining daily vital stats safely
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
            sleep_string = sec_to_hms(secs)

    score = find_sleep_score(sleep)

    if score is not None:
        sleep_score = score

with st.expander("Sleep Debug", expanded=True):

    st.write("Sleep record date:", sleep_date_used)

    st.write("Sleep score found:", sleep_score)

    st.json(sleep)

bb_val = "-"
if body_battery_raw and isinstance(body_battery_raw, list):
    try:
        levels = body_battery_raw[-1].get("bodyBatteryValuesArray", [])
        if levels:
            bb_val = levels[-1][1]
    except Exception:  # noqa: BLE001
        pass

load_val = "-"
if isinstance(training_status, dict):
    load_balance = training_status.get("mostRecentTrainingLoadBalance", {})
    if isinstance(load_balance, dict):
        metrics_status = load_balance.get("metricsTrainingStatus", {})
        if isinstance(metrics_status, dict):
            load_val = metrics_status.get("trainingLoad", "-")


# --------------------------------------------------------------------------
# MAIN DASHBOARD INTERFACE
# --------------------------------------------------------------------------
st.title("Performance & Health Dashboard")
st.caption(f"Last synchronized: {dt.datetime.now().strftime('%H:%M')}")

# Render Mobile-Safe 2x3 Grid Container
st.markdown('<div class="section-title">Today\'s Snapshot</div>', unsafe_allow_html=True)

c1 = build_kpi_html("VO2 Max", f"{vo2_max_val}", status_label)
c2 = build_kpi_html("Rest Heart Rate", f"{rhr} bpm" if rhr != "-" else "-", "")
c3 = build_kpi_html("HRV (Night)", f"{hrv_val} ms" if hrv_val != "-" else "-", "")
c4 = build_kpi_html("Body Battery", f"{bb_val}" if bb_val != "-" else "-", "")
c5 = build_kpi_html(
    "Sleep",
    sleep_string,
    f"Score: {sleep_score} • {sleep_date_used}"
)
c6 = build_kpi_html("Training Load", f"{load_val}" if load_val != "-" else "-", "")

snapshot_html = f'<div class="snapshot-grid">{c1}{c2}{c3}{c4}{c5}{c6}</div>'
st.markdown(snapshot_html, unsafe_allow_html=True)

# Render Activity Progress Sections
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