"""
Turns (goal, recent plans, recent feedback, recent Garmin metrics) into 
structured training plans via the Claude API.
"""
import os
import json
from datetime import date

import anthropic

MODEL = "claude-sonnet-4-6"

FORMATTER_SYSTEM_PROMPT = """You are an elite endurance coach. Your job is to take raw, unformatted user notes about their training goals, constraints, schedule, and injury history, and rewrite them into a clean, structured, and aesthetic Markdown summary.

Use bullet points, bold text, and appropriate emojis. Keep it concise, organized, and encouraging.
Respond with ONLY the formatted Markdown block (no extra introductory or concluding conversational text).
"""

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


def format_goal_aesthetically(raw_text: str) -> str:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=FORMATTER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Please reformat these athlete goals into an aesthetic summary:\n\n{raw_text}"}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


def generate_week_plan(week_start: date, profile: dict, recent_plans: list,
                        recent_feedback: list, garmin_summary: dict,
                        num_weeks: int = 1, user_prompt: str = "") -> dict:
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

    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


ADJUSTMENT_SYSTEM_PROMPT = """You are an adjustment agent modifying a weekly schedule mid-week. Keep session titles concise and punchy in the exact format: '8 x 400m @ 4:00/km with 90 sec rest' or '6km easy @ Zone 2'.

Respond with ONLY valid JSON:
{
  "rationale": "Short explanation of adjustment.",
  "sessions": [ ... same session shape ... ]
}
"""


def regenerate_partial_week(profile: dict, existing_sessions: list, reason: str,
                             affected_start: str, affected_end: str, notes: str) -> dict:
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
    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)