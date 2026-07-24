"""
Shared data-fetch and rendering helpers for the "This Week" dashboard page.

Split out of what used to be a single app.py so that the code on disk
mirrors the three pages actually shown in the app ("This Week", "Current
Plan", "Weekly Check-In") - see pages/0_This_Week.py, pages/2_Current_Plan.py,
and pages/1_Weekly_Check-In.py. This module holds every Garmin Connect fetch
function (all st.cache_* wrapped) and every pure formatting/rendering helper
that pages/0_This_Week.py needs; it does not itself run any page UI.
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
    Fetches scheduled running workouts directly from Garmin Connect's calendar
    (rather than from our own database) and extracts each one's completion
    status, so the dashboard reflects the live state of the watch/calendar
    even if it drifts from what's saved locally.

    Args:
        _client (Garmin): Authenticated Garmin API client.
        start_date (datetime.date): First day of the window to display.
        end_date (datetime.date): Last day of the window to display (inclusive).

    Returns:
        list[dict]: Sessions sorted by date, each shaped like
            {"date": date, "title": str, "is_completed": bool}.
    """
    months_to_fetch = {(start_date.year, start_date.month), (end_date.year, end_date.month)}
    items = []

    for yr, mo in months_to_fetch:
        try:
            month_index = mo - 1
            endpoint = f"/calendar-service/year/{yr}/month/{month_index}"
            cal_data = _client.connectapi(endpoint)
            
            if isinstance(cal_data, dict):
                month_items = cal_data.get("calendarItems", []) or cal_data.get("items", [])
            elif isinstance(cal_data, list):
                month_items = cal_data
            else:
                month_items = []
                
            items.extend(month_items)
        except Exception as e:
            st.warning(f"Garmin Calendar Fetch Warning ({yr}-{mo}): {e}")
            continue

    sessions = []
    for item in items:
        if not isinstance(item, dict):
            continue

        item_type = str(item.get("itemType") or item.get("eventType") or "").lower()
        is_workout = "workout" in item_type or item.get("workoutScheduleId") is not None

        if not is_workout:
            continue

        date_str = (
            item.get("calendarDate")
            or item.get("date")
            or (item.get("startDateLocal") or item.get("startTimeLocal") or "")[:10]
        )
        if not date_str:
            continue

        try:
            item_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        if not (start_date <= item_date <= end_date):
            continue

        title = (
            item.get("title")
            or item.get("workoutName")
            or item.get("name")
            or "Scheduled Run"
        )

        # Garmin flags indicating completion
        is_completed = (
            bool(item.get("completed"))
            or bool(item.get("isCompleted"))
            or str(item.get("completionStatus", "")).upper() == "COMPLETED"
            or item.get("activityId") is not None
        )

        sessions.append({
            "date": item_date,
            "title": title,
            "is_completed": is_completed,
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


def render_planned_sessions(sessions, completed_dates=None):
    """
    Renders this week's planned running sessions with status symbols:
    - Green Tick (✓) for completed workouts
    - Red Cross (✗) for missed past workouts
    - Hourglass (⏳) for upcoming workouts

    Args:
        sessions (list[dict]): Output of fetch_planned_sessions_live().
        completed_dates (set[datetime.date] | None): Dates that have a
            recorded activity (from the activities dataframe), used as a
            second signal alongside each session's own "is_completed" flag -
            in case Garmin's calendar item wasn't itself marked complete.
    """
    if not sessions:
        st.caption("No running sessions planned this calendar week.")
        return

    today = dt.date.today()
    completed_set = completed_dates or set()

    logs_html = '<div class="activity-totals-grid">'
    for s in sessions:
        date_label = s["date"].strftime("%a, %b %d")
        
        # Checked via Garmin calendar flag OR matching recorded activity date
        is_done = s.get("is_completed") or (s["date"] in completed_set)

        if is_done:
            status_icon = '<span style="color: #22c55e; font-size: 1.1rem; font-weight: bold;">✓</span>'
        elif s["date"] < today:
            # Past date and not completed
            status_icon = '<span style="color: #ef4444; font-size: 1.1rem; font-weight: bold;">✗</span>'
        else:
            # Scheduled for today/future
            status_icon = '<span style="color: #8792A6; font-size: 0.9rem;">⏳</span>'

        logs_html += (
            f'<div class="activity-card">'
            f'<div class="activity-date">{date_label}</div>'
            f'<div class="activity-metrics"><strong>{s["title"]}</strong>{status_icon}</div>'
            f'</div>'
        )
    logs_html += "</div>"
    st.markdown(logs_html, unsafe_allow_html=True)

