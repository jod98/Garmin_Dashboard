"""
Performance & Health Dashboard
------------------------------
Entry point / router for a Streamlit multi-page app that pulls live data
from Garmin Connect (via the garminconnect library) and houses the AI
Training Plan Coach pages.

This file only sets up page config, global mobile-friendly CSS, and the
3-page navigation - it does not render any dashboard content itself. Each
page is its own file under pages/, so the code on disk matches the three
pages shown in the app:
    pages/0_This_Week.py        -> "This Week"   (health snapshot, planned
                                    sessions, activity logs; shared fetch/
                                    render helpers live in core/dashboard_data.py)
    pages/2_Current_Plan.py     -> "Current Plan" (AI coach: goals + adjustments)
    pages/1_Weekly_Check-In.py  -> "Weekly Check-In" (AI coach: weekly feedback)
"""

import streamlit as st

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
# MULTI-PAGE NAVIGATION
# --------------------------------------------------------------------------
this_week_page = st.Page(
    "pages/0_This_Week.py",
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
