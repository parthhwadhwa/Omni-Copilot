"""Strict JSON planner via Groq. No chat, no free text — only structured plans."""

import json
from groq import Groq
from config import GROQ_API_KEY
from agents import ALL_AGENTS

MODEL = "llama-3.3-70b-versatile"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def _tool_summary() -> str:
    lines = []
    for name, cls in ALL_AGENTS.items():
        agent = cls()
        for tool in agent.tools:
            props = tool["params"].get("properties", {})
            req = tool["params"].get("required", [])
            p = ", ".join(f"{k}{'*' if k in req else ''}" for k in props)
            lines.append(f"  {name}.{tool['action']}({p})")
    return "\n".join(lines)


SYSTEM_PROMPT = f"""You are a strict task planner. You do NOT chat. You do NOT explain. You ONLY output a JSON plan.

Available tools:
{_tool_summary()}

Allowed intents: schedule_meeting | send_email | send_slack | send_discord | list_meetings | list_calendar | read_email | create_doc | write_doc | search | update_meeting | create_form | read_file | write_file | list_notion | write_notion | unknown

Output format (JSON only, no markdown, no extra text):
{{"intent":"<intent>","steps":[{{"agent":"<name>","action":"<action>","params":{{...}}}}]}}

Rules:
- Output ONLY the JSON object. Nothing else.
- intent must be one of the allowed intents.
- If unclear or no tool applies: {{"intent":"unknown","steps":[]}}
- Extract ALL params from the user message.
- Dates/times must be ISO 8601 (e.g. 2026-04-12T14:00:00).
- For multi-step tasks include all steps in order.
- Leave mail body empty when following a meeting step — system fills it.
- Never use placeholder values in params.
- CRITICAL: action must EXACTLY match one of the action names listed in Available tools above. Never invent action names.
- "send meeting details to slack" = only slack.send_message step (no new meeting.schedule step).
- "send meeting details to discord" = only discord.send_message step (no new meeting.schedule step).
"""


def _parse_raw(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    # Extract first JSON object if surrounded by extra text
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]
    return json.loads(raw)


def call_llm(prompt: str) -> dict:
    """Single strict planning call. Returns {intent, steps} only — no chat."""
    client = _get_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    kwargs = dict(model=MODEL, messages=messages, temperature=0, max_tokens=512)

    try:
        raw = client.chat.completions.create(**kwargs).choices[0].message.content
        return _parse_raw(raw)
    except json.JSONDecodeError:
        # Retry once on bad JSON
        try:
            raw = client.chat.completions.create(**kwargs).choices[0].message.content
            return _parse_raw(raw)
        except Exception:
            return {"intent": "unknown", "steps": []}
    except Exception:
        return {"intent": "unknown", "steps": []}
