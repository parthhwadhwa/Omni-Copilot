"""
Orchestrator v7 — strict, deterministic, zero hardcoded values.

Design principles:
- 1 LLM call per request (planning only)
- Follow-ups handled by rule-based state merge (no LLM)
- Validation layer fills missing params before execution
- Execution is 100% deterministic — no LLM, no guessing
- Reply is built from structured result data — no LLM
- All runtime values come from: user input | context chain | safe defaults
"""

from __future__ import annotations
import re
from datetime import datetime, timedelta
from agents import ALL_AGENTS
from config import GROQ_API_KEY
from memory import save_memory, retrieve_memory, extract_entities
from search import search_all_sources

# ---------------------------------------------------------------------------
# Safe defaults — only structural, never user content
# ---------------------------------------------------------------------------
DEFAULTS = {
    "platform": "google_meet",
    "title": "Meeting",
    "time": "10:00:00",
}

# ---------------------------------------------------------------------------
# Rule-based date/time extraction (faster + more reliable than LLM)
# ---------------------------------------------------------------------------

def _parse_date(text: str) -> str | None:
    lower = text.lower()
    today = datetime.now().date()
    if "today" in lower:
        return today.isoformat()
    if "tomorrow" in lower:
        return (today + timedelta(days=1)).isoformat()
    if "yesterday" in lower:
        return (today - timedelta(days=1)).isoformat()
    for name, offset in [("monday", 0), ("tuesday", 1), ("wednesday", 2),
                          ("thursday", 3), ("friday", 4), ("saturday", 5), ("sunday", 6)]:
        if name in lower:
            diff = (offset - today.weekday()) % 7 or 7
            return (today + timedelta(days=diff)).isoformat()
    if m := re.search(r"(\d{4}-\d{2}-\d{2})", text):
        return m.group(1)
    return None


def _parse_time(text: str) -> str | None:
    if m := re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", text, re.I):
        h, mi, ap = int(m.group(1)), m.group(2), (m.group(3) or "").lower()
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        return f"{h:02d}:{mi}:00"
    if m := re.search(r"(\d{1,2})\s*(am|pm)", text, re.I):
        h, ap = int(m.group(1)), m.group(2).lower()
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        return f"{h:02d}:00:00"
    return None


def _get_param_schema(agent_name: str, action: str) -> dict:
    """Return the full param schema for an agent action."""
    cls = ALL_AGENTS.get(agent_name)
    if not cls:
        return {}
    for tool in cls().tools:
        if tool["action"] == action:
            return tool["params"]
    return {}


def _get_param_keys(agent_name: str, action: str) -> set:
    return set(_get_param_schema(agent_name, action).get("properties", {}).keys())


def _get_required_keys(agent_name: str, action: str) -> set:
    return set(_get_param_schema(agent_name, action).get("required", []))


# ---------------------------------------------------------------------------
# Structured data extractor — pulls typed values from raw user text
# ---------------------------------------------------------------------------

def _extract_structured(text: str) -> dict:
    """
    Pull typed fields from text. Returns only what is actually found.
    Values come entirely from user input — no defaults injected here.
    """
    found: dict = {}

    date = _parse_date(text)
    time = _parse_time(text)
    if date:
        found["date"] = date
    if time:
        found["time"] = time
    if date and time:
        found["start"] = f"{date}T{time}"
    elif date:
        found["start"] = f"{date}T{DEFAULTS['time']}"

    # Email address
    if m := re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]+", text):
        found["email"] = m.group(0)
        found["to"] = m.group(0)

    # Platform
    lower = text.lower()
    if "zoom" in lower:
        found["platform"] = "zoom"
    elif "google meet" in lower or "gmeet" in lower or "meet" in lower:
        found["platform"] = "google_meet"
    elif "teams" in lower:
        found["platform"] = "teams"

    # Quoted title
    if m := re.search(r'"([^"]+)"', text):
        found["title"] = m.group(1)
        found["subject"] = m.group(1)

    return found


# ---------------------------------------------------------------------------
# Conversation state — follow-up merging without LLM
# ---------------------------------------------------------------------------

class ConversationState:
    def __init__(self):
        self.intent: str | None = None
        self.steps: list[dict] = []
        self.context: dict = {}  # accumulated structured data

    def is_followup(self, text: str) -> bool:
        if not self.intent:
            return False
        lower = text.lower().strip()

        # Explicit greetings / resets
        if lower in {"hi", "hello", "hey", "thanks", "thank you", "bye", "help", "quit"}:
            self.clear()
            return False

        # Short message with no action-starting verb = follow-up
        words = lower.split()
        starters = {"send", "schedule", "create", "show", "list", "read",
                    "write", "check", "search", "find", "book", "open", "get"}
        if len(words) <= 6 and not any(w in starters for w in words):
            return True
        return False

    def merge(self, text: str) -> dict:
        """
        Merge follow-up text into pending steps.
        Date/time → rule-based.
        Other text → match against declared param keys, strip assignment prefix.
        No LLM call.
        """
        new = _extract_structured(text)
        self.context.update(new)

        _DEFAULT_VALUES = {"meeting", "untitled", "new event", "event", ""}

        for step in self.steps:
            agent_name = step.get("agent", "")
            action = step.get("action", "")
            params = step.setdefault("params", {})
            keys = _get_param_keys(agent_name, action)

            # Apply date/time updates
            if "start" in keys and new.get("start"):
                params["start"] = new["start"]
            if "date" in keys and new.get("date"):
                params["date"] = new["date"]

            # Text follow-up: extract value intelligently
            if not new.get("date") and not new.get("time"):
                stripped = text.strip().strip('"')

                # Check if user said "<param_name> is <value>" using declared param keys
                # e.g. "title is Engineering Sync" → key=title, value="Engineering Sync"
                matched = False
                for key in keys:
                    m = re.match(rf"^{re.escape(key)}\s+(?:is\s+|:\s*)?(.+)$", stripped, re.I)
                    if m:
                        val = m.group(1).strip().strip('"\'')
                        if str(params.get(key, "")).lower() in _DEFAULT_VALUES:
                            params[key] = val
                        matched = True
                        break

                # Also handle "call it X", "name it X", "named X", "called X"
                if not matched:
                    m = re.match(r"^(?:call(?:ed)?|name[d]?)\s+(?:it\s+)?[\"']?(.+?)[\"']?$",
                                 stripped, re.I)
                    if m:
                        val = m.group(1).strip()
                        for key in ("title", "subject"):
                            if key in keys and str(params.get(key, "")).lower() in _DEFAULT_VALUES:
                                params[key] = val
                                matched = True
                                break

                # Fallback: assign bare text to first empty text param
                if not matched:
                    for key in ("title", "subject", "content", "text"):
                        if key in keys and str(params.get(key, "")).lower() in _DEFAULT_VALUES:
                            params[key] = stripped
                            break

        return {"intent": self.intent, "steps": self.steps}

    def save(self, plan: dict):
        self.intent = plan.get("intent")
        self.steps = [dict(s) for s in plan.get("steps", [])]
        # Reset context for fresh request — only keep structured data from this plan's params
        self.context = {}
        for step in self.steps:
            self.context.update({k: v for k, v in step.get("params", {}).items() if v})

    def clear(self):
        self.intent = None
        self.steps = []
        self.context = {}


# ---------------------------------------------------------------------------
# Validation + filling layer
# ---------------------------------------------------------------------------

def _validate_and_fill(params: dict, agent_name: str, action: str,
                        context: dict, last_meeting: dict | None = None) -> list[str]:
    """
    Fill missing params from context chain, then apply safe defaults.
    last_meeting is only used for messaging steps (text/body/content).
    Returns list of still-missing required fields.
    Mutates params in place.
    """
    keys = _get_param_keys(agent_name, action)
    required = _get_required_keys(agent_name, action)

    # Sanitize placeholders
    for k in list(params):
        if isinstance(params.get(k), str) and ("{{" in params[k] or "PREV_RESULT" in params[k]):
            params[k] = ""

    # Fill from step-chain context by exact key name
    for key in keys:
        if not params.get(key) and key in context:
            params[key] = context[key]

    # Fill text/body/content from context (step chain first, then last meeting fallback)
    text_keys = [k for k in ("body", "text", "content") if k in keys and not params.get(k)]
    if text_keys:
        src = context if (context.get("link") or context.get("title")) else (last_meeting or {})
        if src.get("link") or src.get("title"):
            lines = []
            if src.get("title"):
                lines.append(f"Meeting: {src['title']}")
            start = src.get("start", "")
            if start and "T" in start:
                d, t = start.split("T", 1)
                try:
                    t = datetime.strptime(t, "%H:%M:%S").strftime("%I:%M %p").lstrip("0")
                except ValueError:
                    pass
                lines.append(f"When: {d} at {t}")
            if src.get("platform"):
                lines.append(f"Platform: {src['platform'].replace('_', ' ').title()}")
            if src.get("link"):
                lines.append(f"Link: {src['link']}")
            params[text_keys[0]] = "\n".join(lines)

    if "subject" in keys and not params.get("subject") and context.get("title"):
        params["subject"] = f"Meeting: {context['title']}"

    # Apply defaults: schema-declared defaults first, then DEFAULTS dict
    schema_props = _get_param_schema(agent_name, action).get("properties", {})
    for key in keys:
        if not params.get(key) and "default" in schema_props.get(key, {}):
            params[key] = schema_props[key]["default"]

    # Structural safe defaults for common fields
    if "platform" in keys and not params.get("platform"):
        params["platform"] = DEFAULTS["platform"]
    if "title" in keys and not params.get("title"):
        params["title"] = DEFAULTS["title"]
    if "start" in keys and not params.get("start"):
        params["start"] = f"{datetime.now().date().isoformat()}T{DEFAULTS['time']}"

    # Default "to" for mail/send to the user's own email when not specified
    if "to" in keys and not params.get("to"):
        from config import EMAIL_USER
        if EMAIL_USER:
            params["to"] = EMAIL_USER

    return [k for k in required if not params.get(k)]


# ---------------------------------------------------------------------------
# Reply builder — deterministic, generic, no field-name assumptions
# ---------------------------------------------------------------------------

# Fields to hide from the reply (internal / redundant)
_REPLY_SKIP = frozenset({"ok", "status", "retries", "webhook_sent", "webhook_error",
                          "smtp_sent", "smtp_error", "setup", "note", "folder",
                          "read", "last_edited", "created_at"})

# Human-friendly field labels
_FIELD_LABELS = {
    "title": "Title", "subject": "Subject", "start": "When",
    "date": "Date", "link": "Link", "url": "URL",
    "platform": "Platform", "channel": "Channel",
    "from": "From", "to": "To", "snippet": "Preview",
    "connected": "Connected", "method": "Method",
    "page_id": "Page ID", "doc_id": "Doc ID",
    "meeting_id": "Meeting ID", "event_id": "Event ID",
    "form_id": "Form ID", "message_id": "Message ID",
}


def _format_value(key: str, val) -> str:
    if key == "start" and isinstance(val, str) and "T" in val:
        d, t = val.split("T", 1)
        try:
            t = datetime.strptime(t, "%H:%M:%S").strftime("%I:%M %p").lstrip("0")
        except ValueError:
            pass
        return f"{d} at {t}"
    if key == "platform" and isinstance(val, str):
        return val.replace("_", " ").title()
    return str(val)


def _success_header(res: dict) -> str:
    """Return a one-line success headline based on what keys are in the result."""
    if res.get("smtp_sent"):
        return "Email sent successfully."
    if res.get("status") == "sent":
        return "Email sent."
    if res.get("link") and res.get("platform"):
        platform = str(res["platform"]).replace("_", " ").title()
        return f"{platform} meeting scheduled."
    if res.get("link") and "calendar" in str(res.get("storage", "")):
        return "Meeting scheduled."
    if res.get("status") in ("created", "written"):
        return f"{str(res.get('status', '')).capitalize()}."
    if res.get("status") == "scheduled":
        return "Meeting scheduled."
    return ""


def _build_reply(results: list[dict]) -> str:
    ok = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]

    if not results:
        return "Done."
    if not ok:
        return "Something went wrong: " + "; ".join(r.get("error", "?") for r in failed)

    parts = []
    for r in ok:
        res = r.get("result", {})

        if isinstance(res, dict):
            if not res:
                continue
            # Connection status response
            if "connected" in res:
                method = res.get("method", "")
                state = "connected" if res.get("connected") else "not connected"
                parts.append(f"{method} {state}." if method else state.capitalize() + ".")
                if not res.get("connected") and res.get("setup"):
                    parts.append(f"Setup: {res['setup']}")
                continue

            # Build key-value lines using markdown line breaks (two trailing spaces)
            header = _success_header(res)
            lines = []
            for k, v in res.items():
                if k in _REPLY_SKIP or not v or str(v).startswith("saved_locally"):
                    continue
                label = _FIELD_LABELS.get(k, k.replace("_", " ").title())
                lines.append(f"- **{label}:** {_format_value(k, v)}")
            if lines:
                block = "\n".join(lines)
                parts.append(f"{header}\n\n{block}" if header else block)
            elif header:
                parts.append(header)

        elif isinstance(res, list):
            if not res:
                parts.append("Nothing found.")
                continue
            first = res[0] if isinstance(res[0], dict) else {}
            label_key = next(
                (k for k in ("title", "name", "subject", "from", "path") if first.get(k)),
                None,
            )
            bullets = []
            for item in res:
                if isinstance(item, dict):
                    primary = item.get(label_key, "") if label_key else ""
                    secondary = ""
                    for sk in ("start", "date", "snippet", "url", "link"):
                        if item.get(sk):
                            secondary = f" — {_format_value(sk, item[sk])}"
                            break
                    bullets.append(f"- {primary or str(item)}{secondary}")
                else:
                    bullets.append(f"- {item}")
            parts.append(f"**{len(res)} result(s)**\n\n" + "\n".join(bullets))

    if failed:
        parts.append(f"*{len(failed)} step(s) failed: " +
                     "; ".join(r.get("error", "?") for r in failed) + "*")

    return "\n\n".join(parts) if parts else "Done."


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    def __init__(self, auto_mode: bool = False):
        self.agents = {name: cls() for name, cls in ALL_AGENTS.items()}
        self.auto_mode = auto_mode
        self.state = ConversationState()

    def process(self, user_input: str) -> dict:
        log = ExecutionLog()
        log.add("input", user_input)

        # --- Follow-up: merge into pending task, no LLM ---
        if self.state.is_followup(user_input):
            log.add("followup", "merging")
            plan = self.state.merge(user_input)
            return self._execute(plan, user_input, log)

        # --- LLM planning (single call) ---
        if GROQ_API_KEY:
            plan = self._plan(user_input, log)
        else:
            plan = {"intent": "unknown", "steps": []}

        # --- Patch dates with rule-based parser (overrides LLM) ---
        self._patch_dates(plan, user_input)

        self.state.save(plan)
        return self._execute(plan, user_input, log)

    # ── Planning ──────────────────────────────────────────────────────────────

    def _plan(self, user_input: str, log: ExecutionLog) -> dict:
        from llm import call_llm
        today = datetime.now().date().isoformat()

        ctx_parts = [f"Today: {today}"]

        # Last meeting — always inject so LLM can reference it
        last = self._last_stored("meetings.json")
        if last:
            ctx_parts.append(
                f"Last meeting: title={last.get('title','')}, "
                f"start={last.get('start','')}, "
                f"link={last.get('link','')}, "
                f"platform={last.get('platform','')}"
            )

        # Previous turn intent
        if self.state.intent:
            ctx_parts.append(f"Previous intent: {self.state.intent}")

        prompt = f"[{' | '.join(ctx_parts)}] {user_input}"
        log.add("llm_call", prompt[:140])
        plan = call_llm(prompt)
        log.add("llm_result", f"intent={plan.get('intent','?')} steps={len(plan.get('steps',[]))}")
        return plan

    def _patch_dates(self, plan: dict, user_input: str):
        """Override LLM date/time with rule-based parser for any step that has start/date params."""
        date = _parse_date(user_input)
        time = _parse_time(user_input)
        if not date and not time:
            return
        for step in plan.get("steps", []):
            keys = _get_param_keys(step.get("agent", ""), step.get("action", ""))
            params = step.setdefault("params", {})
            if "start" in keys:
                existing = str(params.get("start", ""))
                if date and time:
                    params["start"] = f"{date}T{time}"
                elif date and "T" in existing:
                    params["start"] = f"{date}T{existing.split('T')[1]}"
                elif date and not existing:
                    params["start"] = f"{date}T{DEFAULTS['time']}"
            if "date" in keys and date:
                params["date"] = date

    # ── Execution ─────────────────────────────────────────────────────────────

    def _execute(self, plan: dict, user_input: str, log: ExecutionLog) -> dict:
        steps = plan.get("steps", [])
        intent = plan.get("intent", "unknown")

        if not steps:
            reply = self._capability_list() if intent == "unknown" else "How can I help you?"
            return {"plan": [], "results": [], "log": log.entries, "reply": reply}

        display_plan = [
            {
                "step": i + 1,
                "agent": s.get("agent", "?"),
                "action": s.get("action", "?"),
                "label": f"{s.get('agent','?')}.{s.get('action','?')}",
                "depends_on": list(range(i)) if i > 0 else [],
            }
            for i, s in enumerate(steps)
        ]

        # Context chain — accumulates data from step results to pass downstream
        # Start with only the current request's extracted params (no bleed from prior requests)
        context = dict(self.state.context)

        # Last meeting available as fallback ONLY for messaging params
        last_meeting = self._last_stored("meetings.json")

        results = []
        for i, step in enumerate(steps):
            agent_name, action, params = self._normalise_step(step)
            label = f"{agent_name}.{action}"
            log.add("step", label)

            # Search pseudo-agent
            if agent_name == "search":
                res = search_all_sources(params.get("query", user_input))
                results.append({"ok": True, "result": res, "status": "success", "retries": 0})
                if isinstance(res, dict):
                    context.update(res)
                continue

            agent = self.agents.get(agent_name)
            if not agent:
                results.append({"ok": False, "error": f"Unknown agent: {agent_name}",
                                 "status": "failed", "retries": 0})
                log.add("fail", f"unknown agent: {agent_name}")
                if not self.auto_mode:
                    break
                continue

            # Validation + filling before execution
            missing = _validate_and_fill(params, agent_name, action, context, last_meeting)
            if missing:
                log.add("skip", f"{label} missing: {missing}")
                # Skip email steps if no recipient — don't fail the whole plan
                if "to" in missing:
                    results.append({"ok": False, "error": f"Skipped: no recipient for {label}",
                                     "status": "skipped", "retries": 0})
                    continue

            try:
                result = agent.handle(action, params)
            except Exception as e:
                result = {"ok": False, "error": str(e)}

            results.append({**result, "status": "success" if result.get("ok") else "failed", "retries": 0})

            # Propagate result into context for downstream steps
            if result.get("ok"):
                res = result.get("result", {})
                if isinstance(res, dict):
                    context.update({k: v for k, v in res.items() if v})
                log.add("ok", label)
            else:
                log.add("fail", f"{label}: {result.get('error','?')}")
                if not self.auto_mode:
                    break

        reply = _build_reply(results)
        save_memory(user_input, extract_entities(user_input, results), results)
        return {"plan": display_plan, "results": results, "log": log.entries, "reply": reply}

    def _normalise_step(self, step: dict) -> tuple[str, str, dict]:
        """Clean up agent/action names that LLM may have mangled."""
        agent_name = step.get("agent", "")
        action = step.get("action", "")
        params = dict(step.get("params") or {})

        # "agent.action" in agent field
        if "." in agent_name and agent_name not in self.agents:
            parts = agent_name.rsplit(".", 1)
            agent_name = parts[0]
            if not action:
                action = parts[1]

        # "agent.action" in action field
        if "." in action:
            action = action.rsplit(".", 1)[1]

        # Fuzzy-match action to declared actions — no alias table
        cls = ALL_AGENTS.get(agent_name)
        if cls:
            declared = [t["action"] for t in cls().tools]
            if action not in declared:
                action = next(
                    (a for a in declared if a in action or action in a),
                    declared[0] if declared else action,
                )

        return agent_name, action, params

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _last_stored(self, filename: str) -> dict:
        from agents.base import load_data
        records = load_data(filename)
        if not records:
            return {}
        return sorted(records, key=lambda r: r.get("created_at", r.get("last_edited", "")))[-1]

    def _capability_list(self) -> str:
        """Build capability list dynamically from registered agents."""
        lines = ["I can help you with:"]
        seen = set()
        for agent in self.agents.values():
            for tool in agent.tools:
                if tool["action"] == "status":
                    continue
                desc = tool["description"]
                if desc not in seen:
                    lines.append(f"• {desc}")
                    seen.add(desc)
        lines.append('\nTry: "Schedule a meeting with Alice tomorrow at 3pm"')
        return "\n".join(lines)

    def set_auto_mode(self, enabled: bool):
        self.auto_mode = enabled

    def get_all_tools(self) -> list[dict]:
        tools = []
        for agent in self.agents.values():
            tools.extend(agent.tool_definitions())
        return tools

    def get_memory(self, query: str = "", limit: int = 5) -> list[dict]:
        return retrieve_memory(query, limit)


class ExecutionLog:
    def __init__(self):
        self.entries: list[dict] = []

    def add(self, event: str, detail: str):
        self.entries.append({
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
            "detail": detail,
        })
