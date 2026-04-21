"""
LLM planning layer — strict, deterministic, zero randomness.

Contract:
- One call per request, temperature=0
- Output is always {intent: str, steps: list[{agent, action, params}]}
- Every output field is validated before returning
- Retry uses an explicit correction prompt, not a duplicate call
- Tool list and intents are derived from registered agents at call time (never stale)
"""

import json
import re
from groq import Groq
from config import GROQ_API_KEY
from agents import ALL_AGENTS

MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 1024
TEMPERATURE = 0  # strict — no randomness

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Tool catalogue — built fresh each call so it always reflects live agents
# ---------------------------------------------------------------------------

def _build_tool_catalogue() -> tuple[str, dict[str, set[str]]]:
    """
    Returns:
      tool_text  — human-readable list for the system prompt
      valid_map  — {agent_name: {valid_action, ...}} for post-call validation
    """
    lines = []
    valid_map: dict[str, set[str]] = {}
    for name, cls in ALL_AGENTS.items():
        valid_map[name] = set()
        for tool in cls().tools:
            props = tool["params"].get("properties", {})
            req = tool["params"].get("required", [])
            p = ", ".join(f"{k}{'*' if k in req else ''}" for k in props)
            lines.append(f"  {name}.{tool['action']}({p})")
            valid_map[name].add(tool["action"])
    return "\n".join(lines), valid_map


def _allowed_intents() -> frozenset[str]:
    """Derive allowed intents dynamically from all registered agent actions."""
    intents = {"status", "unknown"}
    for cls in ALL_AGENTS.values():
        for tool in cls().tools:
            intents.add(tool["action"])
    # Also add common compound intents the LLM may produce
    extras = {
        "schedule_meeting", "send_email", "send_slack", "send_discord",
        "list_meetings", "list_calendar", "read_email",
        "create_doc", "write_doc", "search",
        "update_meeting", "create_form",
        "read_file", "write_file",
        "list_notion", "write_notion",
        "create_drive_doc", "save_to_drive", "read_drive_file", "list_drive",
        "list_repos", "list_github", "list_files", "read_github_file",
        "list_issues", "create_issue", "list_prs", "list_commits",
        "search_code", "get_repo", "summarize_file", "search_in_files",
        "create_event", "list_events", "update_event", "delete_event",
        "create", "list_forms", "get_responses", "submit_response",
        "upload_file", "create_doc", "list_albums", "list_photos",
        "schedule", "list",
    }
    intents.update(extras)
    return frozenset(intents)


# ---------------------------------------------------------------------------
# System prompt — built fresh each call
# ---------------------------------------------------------------------------

def _system_prompt(tool_text: str) -> str:
    intents = " | ".join(sorted(_allowed_intents()))
    return (
        "You are a strict task planner. Output ONLY valid JSON — no prose, no markdown, no explanation.\n\n"
        f"Available tools:\n{tool_text}\n\n"
        f"Allowed intents: {intents}\n\n"
        "Output schema (follow exactly):\n"
        '{"intent":"<intent>","steps":[{"agent":"<agent>","action":"<action>","params":{...}}]}\n\n'
        "Rules — all mandatory:\n"
        "1. intent MUST be one of the allowed intents. Unknown/unclear → {\"intent\":\"unknown\",\"steps\":[]}\n"
        "2. agent MUST be one of the agent names in Available tools.\n"
        "3. action MUST exactly match the action name shown in Available tools for that agent.\n"
        "4. Extract param values only from user input or provided context. Never invent values.\n"
        "5. Dates/times → ISO 8601 string (e.g. 2026-04-12T14:00:00).\n"
        "6. Leave body/text/content empty — the execution layer fills from context.\n"
        "7. MULTI-STEP: if the user asks for two or more actions in one sentence (e.g. \"schedule X and email them\", "
        "\"create a doc and share on slack\", \"schedule meeting and send invite\"), output ONE STEP PER ACTION in order. "
        "The execution layer chains context (e.g. meeting link → email body) automatically.\n"
        "8. Multiple platforms in one request → one step per platform.\n"
        "9. params must be a JSON object. Never null, never a string.\n"
        "10. Output ONLY the JSON object. Nothing before or after it.\n\n"
        "Examples of multi-step plans:\n"
        "- \"schedule meeting tomorrow 3pm with a@b.com and email the invite\" → "
        "[{agent:meeting,action:schedule,...},{agent:mail,action:send,params:{to:\"a@b.com\",subject:\"\",body:\"\"}}]\n"
        "- \"create a doc called notes and share on slack #general\" → "
        "[{agent:docs,action:write_doc,...},{agent:slack,action:send_message,params:{channel:\"#general\",text:\"\"}}]"
    )


# ---------------------------------------------------------------------------
# Output parser + validator
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> str:
    """Pull the first complete JSON object out of raw text."""
    raw = raw.strip()
    # Strip markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    # Find outermost { }
    depth, start = 0, -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return raw[start:i + 1]
    return ""


def _sanitize_params(params) -> dict:
    """Ensure params is a clean dict with only string/number/bool/list values."""
    if not isinstance(params, dict):
        return {}
    clean = {}
    for k, v in params.items():
        if v is None or v == "" or v == [] or v == {}:
            continue  # drop empty — execution layer fills from context
        if isinstance(v, (str, int, float, bool, list)):
            clean[k] = v
        elif isinstance(v, dict):
            clean[k] = v  # nested objects allowed (e.g. questions list for forms)
    return clean


def _validate_plan(plan: dict, valid_map: dict[str, set[str]]) -> dict:
    """
    Enforce structure and correctness of the plan.
    - intent must be in ALLOWED_INTENTS
    - each step must have agent, action (matching registered tools), and dict params
    - strips any extra fields
    Returns a clean, guaranteed-shape plan.
    """
    allowed = _allowed_intents()

    intent = plan.get("intent", "unknown")
    if intent not in allowed:
        intent = "unknown"  # normalise label but keep steps below

    raw_steps = plan.get("steps", [])
    if not isinstance(raw_steps, list):
        return {"intent": "unknown", "steps": []}

    steps = []
    for s in raw_steps:
        if not isinstance(s, dict):
            continue

        agent = s.get("agent", "")
        action = s.get("action", "")
        params = _sanitize_params(s.get("params", {}))

        # Strip "agent." prefix LLM sometimes puts in action
        if "." in action:
            action = action.rsplit(".", 1)[1]

        # If agent encoded as "agent.action", split it
        if "." in agent and agent not in valid_map:
            parts = agent.rsplit(".", 1)
            agent = parts[0]
            if not action:
                action = parts[1]

        # Agent must be registered
        if agent not in valid_map:
            continue

        # Action must be valid for this agent; fuzzy-match if off
        declared = valid_map[agent]
        if action not in declared:
            action = next(
                (a for a in declared if a in action or action in a),
                next(iter(declared)),  # fallback to first declared action
            )

        steps.append({"agent": agent, "action": action, "params": params})

    return {"intent": intent, "steps": steps}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def call_llm(prompt: str) -> dict:
    """
    Single planning call.
    Returns a validated {intent, steps} plan — always well-formed, never raises.
    """
    client = _get_client()
    tool_text, valid_map = _build_tool_catalogue()
    sys = _system_prompt(tool_text)

    def _call(messages: list[dict]) -> dict:
        raw = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        ).choices[0].message.content
        blob = _extract_json(raw)
        if not blob:
            raise ValueError(f"No JSON found in output: {raw[:120]}")
        plan = json.loads(blob)
        return _validate_plan(plan, valid_map)

    messages = [
        {"role": "system", "content": sys},
        {"role": "user", "content": prompt},
    ]

    try:
        return _call(messages)
    except (json.JSONDecodeError, ValueError) as first_err:
        # Retry with an explicit correction — different prompt, not a duplicate
        try:
            correction_messages = messages + [
                {"role": "assistant", "content": str(first_err)},
                {"role": "user", "content":
                    "Your previous response was not valid JSON. "
                    "Output ONLY the JSON object. No explanation. No markdown."},
            ]
            return _call(correction_messages)
        except Exception:
            return {"intent": "unknown", "steps": []}
    except Exception:
        return {"intent": "unknown", "steps": []}
