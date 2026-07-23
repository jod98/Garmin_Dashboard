"""
Performance & Health Dashboard
------------------------------
A Streamlit multi-page app that pulls live data from Garmin Connect
(via the garminconnect library) for Garmin wearables, and houses the AI
Training Plan Coach pages. The "This Week" page displays running,
cycling, and swimming activities along with general health metrics (HRV,
sleep, steps, Body Battery) plus this week's planned running sessions;
"Current Plan" and "Weekly Check-In" are the AI coach pages.
"""

import sys
import os
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

sys.path.append(os.path.dirname(__file__))
from core import db  # noqa: E402

# --------------------------------------------------------------------------
# PAGE CONFIG & MOBILE STYLING
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Garmin Dashboard",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="expanded",
)

ACCENT = "#2DD4BF"
MUTED = "#8792A6"

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}

h1 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.2rem !important; 
    font-weight: 700 !important;
    margin-bottom: 0.25rem !important;
    line-height: 1.2 !important;
    white-space: normal !important;
}}

.block-container {{
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
    padding-left: 0.6rem !important;
    padding-right: 0.6rem !important;
}}

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
    min-height: 82px;
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
    line-height: 1.35;
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
# GARMIN CONNECTION & API CLIENT CACHING
# --------------------------------------------------------------------------
@st.cache_resource(ttl=3600, show_spinner=False)
def get_garmin_client():
    """
    Initializes and authenticates the Garmin Connect API client using Streamlit secrets.

    Returns:
        tuple: (Garmin client instance or None, error message string or None)
    """
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
    """
    Retrieves a list of user activities from Garmin Connect.

    Args:
        _client (Garmin): Authenticated Garmin API client.
        start (int): Starting index for pagination.
        limit (int): Maximum number of activities to retrieve.

    Returns:
        list[dict]: List of raw activity dictionary objects.
    """
    return _client.get_activities(start, limit)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_day_stats(_client, date_str):
    """
    Fetches daily summary statistics for a given date.

    Args:
        _client (Garmin): Authenticated Garmin API client.
        date_str (str): Date string in 'YYYY-MM-DD' format.

    Returns:
        dict: Daily summary statistics dictionary.
    """
    try:
        return _client.get_stats(date_str)
    except Exception:  # noqa: BLE001
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_hrv(_client, date_str):
    """
    Fetches Heart Rate Variability (HRV) metrics for a given date.

    Args:
        _client (Garmin): Authenticated Garmin API client.
        date_str (str): Date string in 'YYYY-MM-DD' format.

    Returns:
        dict or None: HRV metrics payload if available, else None.
    """
    try:
        return _client.get_hrv_data(date_str)
    except Exception:  # noqa: BLE001
        return None


@st.cache_data(ttl=900, show_spinner=False)
def get_sync_timestamp():
    """
    Returns the timestamp of the most recent data fetch.

    This is cached with the same 15-minute TTL as the data fetches below,
    so it only advances when the underlying Garmin data is actually
    re-pulled (or the user hits Refresh) - not on every page render/rerun.

    Returns:
        datetime: Time this cache entry was last (re)computed.
    """
    return dt.datetime.now()


@st.cache_data(ttl=900, show_spinner=False)
def fetch_latest_sleep(_client):
    """
    Fetches sleep data strictly for last night.

    Garmin files a sleep session under the date the sleeper woke up
    (today), not the date they went to bed (yesterday) — so we query
    today's calendar date to get last night's sleep.

    Args:
        _client (Garmin): Authenticated Garmin API client.

    Returns:
        tuple: (date_string, sleep_json) if available, else (None, None).
    """
    today = date.today().strftime("%Y-%m-%d")

    try:
        sleep = _client.get_sleep_data(today)
        if not sleep:
            return None, None
            
        dto = sleep.get("dailySleepDTO", {})
        if dto and dto.get("sleepTimeSeconds"):
            return today, sleep
    except Exception:  # noqa: BLE001
        pass

    return None, None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_sleep_history(_client, num_nights):
    """
    Fetches sleep duration for each of the last N nights, to support a
    rolling average. Sleep is filed under the wake-up date, so the last
    N calendar days (today back to today - N + 1) covers the last N nights.

    Args:
        _client (Garmin): Authenticated Garmin API client.
        num_nights (int): How many most-recent nights to pull.

    Returns:
        list[int]: Sleep duration in seconds, one entry per night that had data.
    """
    durations = []
    for i in range(num_nights):
        day_str = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            sleep = _client.get_sleep_data(day_str)
        except Exception:  # noqa: BLE001
            continue
        if not sleep:
            continue
        dto = sleep.get("dailySleepDTO", {})
        if isinstance(dto, dict):
            secs = dto.get("sleepTimeSeconds")
            if secs:
                durations.append(secs)
    return durations


@st.cache_data(ttl=900, show_spinner=False)
def fetch_body_battery(_client, start_date, end_date):
    """
    Fetches Body Battery metrics across a date range.

    Args:
        _client (Garmin): Authenticated Garmin API client.
        start_date (str): Range start date ('YYYY-MM-DD').
        end_date (str): Range end date ('YYYY-MM-DD').

    Returns:
        list[dict]: List of daily Body Battery records.
    """
    try:
        return _client.get_body_battery(start_date, end_date)
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=900, show_spinner=False)
def fetch_training_status(_client, date_str):
    """
    Fetches training status details for a given date.

    Args:
        _client (Garmin): Authenticated Garmin API client.
        date_str (str): Date string in 'YYYY-MM-DD' format.

    Returns:
        dict: Training status payload if available, else empty dict.
    """
    try:
        return _client.get_training_status(date_str) or {}
    except Exception:  # noqa: BLE001
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_user_profile(_client):
    """
    Fetches user profile details from Garmin Connect.

    Args:
        _client (Garmin): Authenticated Garmin API client.

    Returns:
        dict: User profile data payload.
    """
    try:
        return _client.get_user_profile() or {}
    except Exception:  # noqa: BLE001
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_max_metrics_with_lookback(_client):
    """
    Performs a 30-day lookback search for maximal fitness metrics (e.g., VO2 Max).

    Args:
        _client (Garmin): Authenticated Garmin API client.

    Returns:
        dict: Max metrics data payload if found, else empty dict.
    """
    for i in range(30):
        d = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            data = _client.get_max_metrics(d)
            if data:
                return data
        except Exception:  # noqa: BLE001
            pass
    return {}

@st.cache_data(ttl=900, show_spinner=False)
def fetch_planned_sessions_live(_client, start_date, end_date):
    """
    Fetches this week's scheduled running workouts directly from Garmin
    Connect's calendar (populated by core.garmin_client.push_workout, which
    schedules each generated workout onto a specific date via
    client.schedule_workout).

    Only calendar entries of itemType "workout" within [start_date, end_date]
    are included - these are exactly the structured workouts this app
    schedules (the AI coach only ever pushes running sessions), so no extra
    sport-name matching is needed, and nothing falls back to "today" if a
    date can't be read - it's just skipped.

    Args:
        _client (Garmin): Authenticated Garmin API client.
        start_date (datetime.date): Monday of the week to look up.
        end_date (datetime.date): Sunday of the week to look up.

    Returns:
        list[dict]: Each with "date" (datetime.date), "title" (str), and
            "duration_min" (int or None), sorted by date.
    """
    # Pull whichever calendar month(s) the requested week spans.
    months_to_fetch = {(start_date.year, start_date.month), (end_date.year, end_date.month)}
    items = []
    for yr, mo in months_to_fetch:
        try:
            cal_data = _client.get_calendar(yr, mo)
            st.write(cal_data)
        except Exception:  # noqa: BLE001
            continue
        month_items = cal_data.get("calendarItems", []) if isinstance(cal_data, dict) else (cal_data or [])
        items.extend(month_items)

    # Look up each scheduled workout's planned duration (in minutes) from the
    # workout library, keyed by workout id.
    duration_by_workout_id = {}
    try:
        for w in (_client.get_workouts() or []):
            if isinstance(w, dict) and w.get("workoutId") is not None and w.get("estimatedDurationInSecs"):
                duration_by_workout_id[w["workoutId"]] = round(w["estimatedDurationInSecs"] / 60)
    except Exception:  # noqa: BLE001
        pass

    sessions = []
    for item in items:
        if not isinstance(item, dict) or str(item.get("itemType", "")).lower() != "workout":
            continue

        date_str = item.get("date") or (item.get("startDateLocal") or item.get("startTimeLocal") or "")[:10]
        if not date_str:
            continue
        try:
            item_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        if not (start_date <= item_date <= end_date):
            continue

        workout_id = item.get("workoutId") or item.get("id")
        sessions.append({
            "date": item_date,
            "title": item.get("title") or item.get("workoutName") or "Scheduled Run",
            "duration_min": duration_by_workout_id.get(workout_id),
        })

    sessions.sort(key=lambda s: s["date"])
    return sessions

# --------------------------------------------------------------------------
# PARSING & FORMATTING HELPERS
# --------------------------------------------------------------------------
def m_to_km(m):
    """
    Converts meters to kilometers rounded to two decimal places.

    Args:
        m (float/int): Distance in meters.

    Returns:
        float: Distance in kilometers.
    """
    return round((m or 0) / 1000, 2)


def sec_to_hms(seconds):
    """
    Converts a duration in seconds into an HMS string format (H:MM:SS or M:SS).

    Args:
        seconds (float/int): Duration in seconds.

    Returns:
        str: Formatted time string.
    """
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    mn, s = divmod(rem, 60)
    return f"{h}:{mn:02d}:{s:02d}" if h else f"{mn}:{s:02d}"


def sec_to_hr_min(seconds):
    """
    Converts a duration in seconds into an 'Xhr Ymin' style string (no
    trailing 's'). Used for sleep duration/average display, where this
    reads more compactly than the H:MM:SS clock format used elsewhere.

    Args:
        seconds (float/int): Duration in seconds.

    Returns:
        str: Formatted string, e.g. "7hr 15min".
    """
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    mn = rem // 60
    return f"{h}hr {mn}min"


def pace_min_per_km(distance_m, duration_s):
    """
    Calculates running/swimming pace in minutes per kilometer.

    Args:
        distance_m (float/int): Distance in meters.
        duration_s (float/int): Duration in seconds.

    Returns:
        str: Formatted pace string (e.g., '5:30/km') or '-' if invalid.
    """
    if not distance_m:
        return "-"
    km = distance_m / 1000
    if km == 0:
        return "-"
    pace_s = duration_s / km
    mn, s = divmod(int(pace_s), 60)
    return f"{mn}:{s:02d}/km"


def build_kpi_html(label, value, sub=""):
    """
    Constructs an HTML card string for mobile-friendly KPI dashboard rendering.

    Args:
        label (str): Top metric header label.
        value (str): Primary value text display.
        sub (str): Subtext descriptor.

    Returns:
        str: Renderable HTML markup.
    """
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f'</div>'
    )


def find_vo2(obj):
    """
    Recursively inspects nested dictionaries/lists to find a VO2 Max value.

    Args:
        obj (dict | list): The target payload object to inspect.

    Returns:
        float/int/str or None: Extracted VO2 value if present, else None.
    """
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
    Recursively inspects nested structures to extract Garmin's Sleep Score.
    Handles 'sleepScores' -> 'overall' -> 'value' as well as flat key formats.

    Args:
        obj (dict | list): Sleep payload structure.

    Returns:
        int or None: Extracted integer sleep score if found, else None.
    """
    if isinstance(obj, dict):
        if "sleepScores" in obj and isinstance(obj["sleepScores"], dict):
            overall = obj["sleepScores"].get("overall")
            if isinstance(overall, dict) and "value" in overall:
                return overall["value"]
            if isinstance(overall, (int, float)):
                return int(overall)

        if "sleepScore" in obj:
            val = obj["sleepScore"]
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, dict) and "overallScore" in val:
                return val["overallScore"]

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


def interpret_hrv(hrv_payload, current_value):
    """
    Builds a one-word read on a nightly HRV value: "Normal" or "Irregular".

    Uses Garmin's own 'status' field from the HRV payload when available
    (this is personalized to the user's own history), and falls back to a
    simple comparison against the weekly average otherwise.

    Args:
        hrv_payload (dict): Raw HRV API payload.
        current_value: The lastNightAvg value being displayed (int/float/str).

    Returns:
        str: "Normal", "Irregular", or "" if nothing usable is available.
    """
    if not isinstance(hrv_payload, dict) or current_value in (None, "-"):
        return ""

    summary = hrv_payload.get("hrvSummary", {})
    if not isinstance(summary, dict):
        return ""

    status = summary.get("status")
    if status:
        return "Normal" if str(status).upper() == "BALANCED" else "Irregular"

    weekly_avg = summary.get("weeklyAvg")
    try:
        if weekly_avg and (float(current_value) < float(weekly_avg) * 0.9 or float(current_value) > float(weekly_avg) * 1.1):
            return "Irregular"
        if weekly_avg:
            return "Normal"
    except (TypeError, ValueError):
        pass

    return ""


def interpret_body_battery(current_value):
    """
    Bands a current Body Battery reading (0-100) into a single word:
    Excellent / Good / Low / Very Low.

    Args:
        current_value: The current Body Battery level (int/float/str).

    Returns:
        str: Short descriptive label, or "" if the value isn't usable.
    """
    try:
        value = float(current_value)
    except (TypeError, ValueError):
        return ""

    if value >= 76:
        return "Excellent"
    if value >= 51:
        return "Good"
    if value >= 26:
        return "Low"
    return "Very Low"


def sport_tab(df, sport_key, start_of_week, end_of_week):
    """
    Renders the metric overview and logs within a specific activity tab.

    Args:
        df (pd.DataFrame): Processed activities dataframe.
        sport_key (str): Filter key ('running', 'cycling', or 'swimming').
        start_of_week (datetime.date): Start date boundary for current week calculations.
        end_of_week (datetime.date): End date boundary for current week calculations.
    """
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
            logs_html += (
                f'<div class="activity-card">'
                f'<div class="activity-date">{date_label}</div>'
                f'<div class="activity-metrics"><strong>{row["distance_km"]:.2f} km</strong><span>{row["duration_hms"]}</span></div>'
                f'{pace_line}'
                f'</div>'
            )
        logs_html += "</div>"
        st.markdown(logs_html, unsafe_allow_html=True)
    else:
        st.caption("No activities recorded yet for this calendar week.")


def render_planned_sessions(sessions):
    """
    Renders this week's planned running sessions (already fetched and
    week-filtered by fetch_planned_sessions_live) as activity-style cards,
    matching the look of "This Week: Progress".

    Args:
        sessions (list[dict]): Each with "date", "title", "duration_min".
    """
    if not sessions:
        st.caption("No running sessions planned this calendar week.")
        return

    logs_html = '<div class="activity-totals-grid">'
    for s in sessions:
        date_label = s["date"].strftime("%a, %b %d")
        duration_span = f'<span>{s["duration_min"]} min</span>' if s.get("duration_min") else ""
        logs_html += (
            f'<div class="activity-card">'
            f'<div class="activity-date">{date_label}</div>'
            f'<div class="activity-metrics"><strong>{s["title"]}</strong>{duration_span}</div>'
            f'</div>'
        )
    logs_html += "</div>"
    st.markdown(logs_html, unsafe_allow_html=True)


def main_page():
    """
    Renders the full "This Week" dashboard page: sidebar controls, today's
    snapshot, this week's completed activity progress, and this week's
    planned running sessions pulled from the AI coach's saved plan.
    """
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

    # Planned Sessions Section (Direct from Garmin Connect API)
    st.markdown('<div class="section-title">This Week: Planned Sessions</div>', unsafe_allow_html=True)

    planned_sessions = fetch_planned_sessions_live(client, start_of_week, end_of_week)
    render_planned_sessions(planned_sessions)

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


# --------------------------------------------------------------------------
# MULTI-PAGE NAVIGATION
# --------------------------------------------------------------------------
this_week_page = st.Page(
    main_page,
    title="This Week",
    icon="📈",
    default=True,
)

current_plan_page = st.Page(
    "pages/2_Current_Plan.py",
    title="Current Plan",
    icon="📋",
)

feedback_page = st.Page(
    "pages/1_Weekly_Check-In.py",
    title="Weekly Check-In",
    icon="💬",
)

pg = st.navigation([
    this_week_page,
    current_plan_page,
    feedback_page,
])

pg.run()