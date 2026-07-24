"""
The AI coach itself: turns (goal, recent plans, recent feedback, recent
Garmin metrics) into structured training plans via the Claude API.

Two entry points are used by the rest of the app:
  - generate_week_plan(): builds a plan from scratch (new week, or a full
    "regenerate my whole block" request) using broad context.
  - regenerate_partial_week(): a lighter-weight adjustment agent for
    mid-week changes (injury, time off, etc.) that only needs the current
    week's existing sessions plus a reason/notes, not the full history.

Neither function talks to Garmin or the database directly - callers are
responsible for saving the returned sessions (core/db.py) and syncing them
to Garmin Connect (core/garmin_client.py's sync_workouts, which also handles
deleting old workouts so a replan doesn't leave duplicates on the watch).
"""
import json
from datetime import date

import anthropic

MODEL = "claude-sonnet-4-6"

# Used only by format_goal_aesthetically(): a lightweight "make this readable"
# pass over the athlete's raw goal notes, purely for nicer display in the UI.
# It does NOT reason about training - the coaching logic lives in SYSTEM_PROMPT.
FORMATTER_SYSTEM_PROMPT = """You are an elite endurance coach. Your job is to take raw, unformatted user notes about their training goals, constraints, schedule, and injury history, and rewrite them into a clean, structured, and aesthetic Markdown summary.

Use bullet points, bold text, and appropriate emojis. Keep it concise, organized, and encouraging.
Respond with ONLY the formatted Markdown block (no extra introductory or concluding conversational text).
"""

# The main coaching system prompt used by generate_week_plan(). Defines both
# the coaching principles the model should follow AND the exact JSON shape
# it must reply with - core/garmin_client.py's _build_steps() only knows how
# to interpret the "structure" shapes described here (warmup/interval/cooldown),
# so if you change this prompt's structure shapes, update _build_steps() too.
SYSTEM_PROMPT = """You are an experienced endurance/strength coach acting as an \
athlete's training-plan agent. You will be given: the athlete's goal and \
constraints, their last few weeks of plans, their subjective feedback for \
those weeks (energy, soreness, injury flags, notes), objective Garmin \
data (body battery, sleep score, activity training load), the duration in weeks \
to plan, and optional custom instructions/desires.

Core principles:
- Keep the session `title` extremely clean, concise, and direct (e.g. "8 x 400m @ 4:00/km with 90 sec rest", "6km easy @ Zone 2", "8km tempo @ 4:45/km", "14km long run @ Zone 2"). Do NOT make long wordy titles.
- Keep the `description` field brief (1-2 sentences max on key warm-up/cool-down or focus).
- Progress load gradually (~10% or less week-over-week).
- Only 'run', 'bike', 'swim', and 'walk' sessions carry a structured interval breakdown for watch sync.

Respond with ONLY valid JSON (no markdown fences, no commentary), matching \
exactly this shape:

{
  "rationale": "1-2 short sentences summarizing the focus of this week's plan.",
  "sessions": [
    {
      "date": "YYYY-MM-DD",
      "sport": "run|bike|swim|walk|strength|rest",
      "title": "8 x 400m @ 4:00/km with 90 sec rest",
      "duration_min": 45,
      "intensity": "easy|moderate|hard",
      "description": "Warm-up 10 min easy. 8x400m intervals on track. Cool-down 10 min.",
      "structure": [
        {"type": "warmup", "duration_sec": 600},
        {"type": "interval", "duration_sec": 240, "reps": 8, "recovery_sec": 90},
        {"type": "cooldown", "duration_sec": 600}
      ]
    }
  ]
}

Omit "structure" for strength or rest sessions. Include exactly one entry per day for all weeks requested, in chronological date order starting from `week_start`.
"""

# System prompt for regenerate_partial_week(): a narrower agent that only
# adjusts an already-existing week's sessions in response to a specific
# event (injury, time off, etc.), rather than planning a whole new block.
ADJUSTMENT_SYSTEM_PROMPT = """You are an adjustment agent modifying a weekly schedule mid-week. Keep session titles concise and punchy in the exact format: '8 x 400m @ 4:00/km with 90 sec rest' or '6km easy @ Zone 2'.

Respond with ONLY valid JSON:
{
  "rationale": "Short explanation of adjustment.",
  "sessions": [ ... same session shape ... ]
}
"""


def _extract_text(response) -> str:
    """
    Concatenates all text blocks from a Claude API response into one string.

    Claude's response `content` is a list of blocks (text, tool_use, etc.) -
    for these plain single-turn prompts we only ever expect text blocks, but
    filtering by `block.type == "text"` keeps this safe even if that changes.
    """
    return "".join(block.text for block in response.content if block.type == "text")


def _strip_json_fences(text: str) -> str:
    """
    Removes accidental ```json / ``` markdown code-fences from a model reply.

    The prompts above explicitly ask for "ONLY valid JSON, no markdown
    fences", but models occasionally wrap the JSON in fences anyway - this
    is a defensive cleanup so json.loads() doesn't choke on those cases.
    """
    return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def format_goal_aesthetically(raw_text: str) -> str:
    """
    Rewrites the athlete's raw, unstructured goal/constraints notes into a
    nicely formatted Markdown summary, purely for display in the "Current
    Plan Summary" section of the UI. Does not affect training logic.

    Args:
        raw_text: The athlete's free-text goal/constraints notes as typed
            into the "Overall Plan Details & Goals" box.

    Returns:
        str: A Markdown-formatted summary of `raw_text`.
    """
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=FORMATTER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Please reformat these athlete goals into an aesthetic summary:\n\n{raw_text}"}],
    )
    return _extract_text(response).strip()


def generate_week_plan(week_start: date, profile: dict, recent_plans: list,
                        recent_feedback: list, garmin_summary: dict,
                        num_weeks: int = 1, user_prompt: str = "") -> dict:
    """
    Generates a brand-new training plan starting from `week_start`, using
    the athlete's goal/constraints plus recent history (plans, feedback,
    Garmin metrics) as context. Used both for the very first plan and for a
    full "regenerate my whole block" request.

    Args:
        week_start: The Monday the new plan should start from.
        profile: {"goal": str, "constraints": str} - see db.get_athlete_profile().
        recent_plans: Recent `weekly_plans` rows, for progression context.
        recent_feedback: Recent `weekly_feedback` rows, for fatigue/injury context.
        garmin_summary: Output of garmin_client.fetch_week_summary() - objective
            body battery / sleep / training load data.
        num_weeks: How many weeks of sessions to generate in one go.
        user_prompt: Optional free-text custom instructions for this plan
            (e.g. "focus more on hills this block").

    Returns:
        dict: {"rationale": str, "sessions": [ ... ]} - see SYSTEM_PROMPT for
        the exact session shape. This is NOT saved or pushed to Garmin here -
        the caller must call db.save_plan() and garmin_client.sync_workouts().
    """
    client = anthropic.Anthropic()

    user_payload = {
        "week_start": week_start.isoformat(),
        "num_weeks": num_weeks,
        "custom_instructions": user_prompt or "Standard balanced training block.",
        "goal": profile.get("goal"),
        "constraints": profile.get("constraints"),
        "recent_plans": recent_plans,
        "recent_feedback": recent_feedback,
        "recent_garmin_data": garmin_summary,
    }

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(user_payload, default=str)}],
    )

    return json.loads(_strip_json_fences(_extract_text(response)))


def regenerate_partial_week(profile: dict, existing_sessions: list, reason: str,
                             affected_start: str, affected_end: str, notes: str) -> dict:
    """
    Adjusts an already-planned week in response to a specific mid-week event
    (injury, time off, a schedule conflict, etc.) rather than planning a
    whole new block from scratch.

    Note: the model is given the FULL current week's `existing_sessions` and
    is expected to return the FULL week back (unaffected days included, not
    just the affected date range) - the caller replaces the whole week's
    saved plan with whatever comes back, so days outside
    [affected_start, affected_end] should come back materially unchanged.

    Args:
        profile: {"goal": str, "constraints": str} - see db.get_athlete_profile().
        existing_sessions: The current week's sessions as already saved/pushed
            (each may carry a "garmin_workout_id" from a previous push -
            that's fine, the model doesn't need to touch that field).
        reason: Short category for the adjustment, e.g. "injury", "time_off", "other".
        affected_start: ISO date string - first day the issue affects.
        affected_end: ISO date string - last day the issue affects.
        notes: Free-text description of what happened, for the model to reason about.

    Returns:
        dict: {"rationale": str, "sessions": [ ... ]}, the full replacement
        week. As with generate_week_plan(), the caller must save this and
        sync it to Garmin (via garmin_client.sync_workouts(), which deletes
        the old future workouts before pushing these new ones).
    """
    client = anthropic.Anthropic()
    payload = {
        "goal": profile.get("goal"),
        "constraints": profile.get("constraints"),
        "existing_sessions": existing_sessions,
        "reason": reason,
        "affected_start": affected_start,
        "affected_end": affected_end,
        "notes": notes,
    }
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=ADJUSTMENT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
    )
    return json.loads(_strip_json_fences(_extract_text(response)))
