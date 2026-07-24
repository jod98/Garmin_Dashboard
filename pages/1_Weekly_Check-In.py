"""
"Weekly Check-In" page: a short subjective feedback form (energy, soreness,
injury, missed sessions, notes) for the week that just finished. Submitted
feedback is saved via core.db.save_feedback() and picked up as context the
next time a plan is generated (see core/plan_generator.py), so an injury
flagged here can influence next week's plan even before any explicit
mid-week adjustment is made on the Current Plan page.

The form only unlocks after Sunday 6pm each week, so the AI coach reviews a
(mostly) complete week before the next one is planned.
"""
import sys
import os
from datetime import date, datetime, timedelta

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core import db  # noqa: E402

st.title("Weekly Check-In")

# Optional: this page reads a `?week=2026-07-20` query param so you can link
# directly to a specific week's check-in if you ever want to (e.g. to review
# a week you skipped). There's no automated email that sends this link -
# plans are only ever generated when you ask for one on the Current Plan page.
week_param = st.query_params.get("week")
try:
    week_start = (
        datetime.strptime(week_param, "%Y-%m-%d").date()
        if week_param
        else date.today() - timedelta(days=date.today().weekday())
    )
except ValueError:
    week_start = date.today() - timedelta(days=date.today().weekday())

week_end = week_start + timedelta(days=6)

unlock_time = datetime.combine(
    week_end,
    datetime.min.time()
).replace(hour=18)

st.info(
    f"""
### Weekly Training Review

You're reviewing your training completed between **Monday {week_start.strftime('%d %B %Y')}**
and **Sunday {week_end.strftime('%d %B %Y')}**.

Your feedback is used to personalise your next training plan.

- ✅ If everything went well, your progression will continue as planned.
- ⚠️ If you experienced fatigue, illness, injury, or missed sessions, your next plan will be adjusted accordingly.

This doesn't generate anything by itself - it's just saved so it's available as context the next time you ask for a new or adjusted plan on the **Current Plan** page.
"""
)

# Lock editing until Sunday 6pm
if datetime.now() < unlock_time:
    st.warning(
        f"""
Weekly Check-In becomes available every **Sunday at 6:00 PM**.

Your next check-in opens on:

**{unlock_time.strftime('%A %d %B %Y at %I:%M %p')}**

This allows your AI coach to review the completed training week before you generate your next plan.
"""
    )
    st.stop()

existing = db.get_feedback(week_start)

if existing:
    st.info(
        "You've already submitted this week's check-in. "
        "Submitting again will replace your previous feedback."
    )

energy = st.slider(
    "Energy level this week",
    1,
    5,
    existing["energy_level"] if existing else 3,
    help="1 = Completely exhausted • 5 = Felt great all week",
)

soreness = st.slider(
    "Soreness / fatigue",
    1,
    5,
    existing["soreness_level"] if existing else 2,
    help="1 = Fully recovered • 5 = Very sore or fatigued",
)

injury = st.checkbox(
    "I picked up an injury or niggle this week",
    value=existing["injury_flag"] if existing else False,
)

injury_notes = ""
if injury:
    injury_notes = st.text_area(
        "Describe the injury (location, severity, when it started)",
        value=existing["injury_notes"] if existing else "",
    )

missed = st.text_input(
    "Did you miss or shorten any sessions?",
    value=existing["missed_sessions"] if existing else "",
)

notes = st.text_area(
    "Anything else your coach should know before generating next week's plan?",
    value=existing["notes"] if existing else "",
)

if st.button("Submit Weekly Check-In", type="primary"):
    db.save_feedback(
        week_start,
        energy,
        soreness,
        injury,
        injury_notes,
        missed,
        notes,
    )

    st.success(
        "Thanks! Your feedback has been saved and will be used when generating your next training plan."
    )