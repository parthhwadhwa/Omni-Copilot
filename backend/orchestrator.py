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

_PRONOUNS = {"her", "him", "them", "she", "he", "they", "this person", "the person"}


class ConversationState:
    def __init__(self):
        self.intent: str | None = None
        self.steps: list[dict] = []
        self.context: dict = {}  # accumulated structured data
        self.memory: dict = {}   # persists across ALL turns (emails, names, etc.)

    def is_followup(self, text: str) -> bool:
        if not self.intent:
            return False
        lower = text.lower().strip()

        # Slash commands are always new requests, never follow-ups
        if lower.startswith("/"):
            self.clear()
            return False

        # Explicit greetings / resets
        if lower in {"hi", "hello", "hey", "thanks", "thank you", "bye", "help", "quit"}:
            self.clear()
            return False

        # Short message with no action-starting verb = follow-up
        words = lower.split()
        starters = {"send", "schedule", "create", "show", "list", "read",
                    "write", "check", "search", "find", "book", "open", "get",
                    "email", "mail", "share", "post", "message", "reply",
                    "invite", "forward", "remind", "add", "delete", "update",
                    "replace", "change", "rename", "move", "copy"}
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
            params = step.get("params", {})
            self.context.update({k: v for k, v in params.items() if v})
            # Persist emails into cross-turn memory
            for key in ("to", "email"):
                val = params.get(key, "")
                if val and "@" in str(val):
                    self.memory["last_email"] = str(val)
            attendees = params.get("attendees", [])
            if isinstance(attendees, list):
                emails = [a for a in attendees if "@" in str(a)]
                if emails:
                    self.memory["last_email"] = emails[0]

    def clear(self):
        self.intent = None
        self.steps = []
        self.context = {}


# ---------------------------------------------------------------------------
# Meeting invite body builder — produces plain + HTML version
# ---------------------------------------------------------------------------

def _build_meeting_invite(src: dict) -> tuple[str, str]:
    """Return (plain_text, html) body for a meeting invite email."""
    from config import EMAIL_USER
    title = src.get("title", "Meeting")
    link = src.get("link", "")
    start_raw = src.get("start", "")
    platform = src.get("platform", "").replace("_", " ").title() or "Google Meet"
    duration = src.get("duration_minutes", 30)

    date_str, time_str = "", ""
    if start_raw and "T" in start_raw:
        d, t = start_raw.split("T", 1)
        date_str = d
        try:
            time_str = datetime.strptime(t.split("+")[0].split("Z")[0][:8],
                                          "%H:%M:%S").strftime("%I:%M %p").lstrip("0")
        except ValueError:
            time_str = t
    elif start_raw:
        date_str = start_raw

    from config import SENDER_NAME
    sender = SENDER_NAME or ((EMAIL_USER or "").split("@")[0].title() if EMAIL_USER else "")

    plain_lines = [
        "Hi,",
        "",
        f"You're invited to a meeting: {title}.",
        "",
    ]
    if date_str:
        plain_lines.append(f"📅 Date: {date_str}")
    if time_str:
        plain_lines.append(f"⏰ Time: {time_str} (IST)")
    plain_lines.append(f"⏱  Duration: {duration} minutes")
    plain_lines.append(f"📍 Platform: {platform}")
    if link:
        plain_lines.append(f"🔗 Join: {link}")
    plain_lines.extend(["", "See you there!", "", f"Regards,", sender or "—"])
    plain = "\n".join(plain_lines)

    link_block = (
        f'<a href="{link}" style="display:inline-block;background:#1a73e8;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:600;font-size:14px;">Join meeting</a>'
        f'<p style="margin:20px 0 0;font-size:13px;color:#5f6368;word-break:break-all;">Or paste this link: <a href="{link}" style="color:#1a73e8;">{link}</a></p>'
    ) if link else (
        '<p style="margin:20px 0 0;font-size:13px;color:#5f6368;">The meeting link will be shared separately.</p>'
    )

    html = f"""<!DOCTYPE html><html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#202124;margin:0;padding:24px;background:#f6f8fa;">
<div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
<div style="background:#1a73e8;color:#fff;padding:20px 24px;">
<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.85;">Meeting Invitation</div>
<div style="font-size:22px;font-weight:600;margin-top:4px;">{title}</div>
</div>
<div style="padding:24px;">
<p style="margin:0 0 16px;font-size:15px;">Hi,</p>
<p style="margin:0 0 20px;font-size:15px;line-height:1.5;">You're invited to join a meeting. Details below:</p>
<table style="border-collapse:collapse;width:100%;margin-bottom:20px;font-size:14px;">
<tr><td style="padding:8px 0;color:#5f6368;width:110px;">📅 Date</td><td style="padding:8px 0;font-weight:500;">{date_str or '—'}</td></tr>
<tr><td style="padding:8px 0;color:#5f6368;">⏰ Time</td><td style="padding:8px 0;font-weight:500;">{time_str or '—'} (IST)</td></tr>
<tr><td style="padding:8px 0;color:#5f6368;">⏱ Duration</td><td style="padding:8px 0;font-weight:500;">{duration} minutes</td></tr>
<tr><td style="padding:8px 0;color:#5f6368;">📍 Platform</td><td style="padding:8px 0;font-weight:500;">{platform}</td></tr>
</table>
{link_block}
<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
<p style="margin:0;font-size:14px;color:#5f6368;">Regards,<br><strong style="color:#202124;">{sender or 'OmniCopilot'}</strong></p>
</div></div></body></html>"""
    return plain, html


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

    # Fill text/body from context — ONLY for mail.send, not docs/drive/etc.
    is_mail_send = (agent_name == "mail" and action == "send")
    text_keys = [k for k in ("body", "text", "content") if k in keys and not params.get(k)]

    # Only use meeting context from the CURRENT step's chain (context), never from
    # last_meeting alone — that would bleed into unrelated standalone email sends.
    chain_src = context if (context.get("title") and context.get("start")) else {}
    is_meeting_invite = is_mail_send and bool(chain_src.get("title") and chain_src.get("start"))

    if text_keys and is_mail_send:
        if is_meeting_invite:
            plain, html = _build_meeting_invite(chain_src)
            params[text_keys[0]] = plain
            if "html" in keys and not params.get("html"):
                params["html"] = html
        else:
            # Simple email: body was already in params (from LLM), or use a plain fallback
            fallback = params.get("subject") or "Hello"
            params[text_keys[0]] = fallback

    if is_mail_send and "subject" in keys and not params.get("subject"):
        if chain_src.get("title"):
            params["subject"] = f"Meeting invite: {chain_src['title']}"

    # Slack / Discord chat — auto-build a share message from upstream context
    is_chat_send = (
        (agent_name == "slack" and action == "send_message") or
        (agent_name == "discord" and action in ("send_message", "send"))
    )
    if is_chat_send and text_keys:
        ctx_title = context.get("title") or context.get("subject") or ""
        ctx_link = context.get("link") or context.get("html_url") or context.get("url") or ""
        ctx_path = context.get("file_path") or context.get("filename") or ""
        if ctx_title and ctx_link:
            params[text_keys[0]] = f"{ctx_title} — {ctx_link}"
        elif ctx_title and ctx_path:
            params[text_keys[0]] = f"{ctx_title} (saved at {ctx_path})"
        elif ctx_title:
            params[text_keys[0]] = ctx_title
        else:
            params[text_keys[0]] = "Shared from OmniCopilot"

    # Default empty content for docs/notes agents so they never block on missing content
    if agent_name in ("docs", "drive", "notion") and "content" in keys and not params.get("content"):
        params["content"] = ""

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

    # Resolve pronouns in "to" — replace "her"/"him"/"them" with last known email
    if "to" in keys and str(params.get("to", "")).lower().strip() in _PRONOUNS:
        params["to"] = context.get("last_email", "")

    # Fill "to" for mail steps: prefer meeting attendee over sender's own email
    if "to" in keys and not params.get("to"):
        # Try last known email from cross-turn memory
        if context.get("last_email"):
            params["to"] = context["last_email"]
        else:
            attendees = (
                context.get("attendees")
                or (last_meeting or {}).get("attendees")
            )
            if attendees and isinstance(attendees, list) and attendees[0]:
                params["to"] = attendees[0]
            elif attendees and isinstance(attendees, str) and attendees:
                params["to"] = attendees
            else:
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
                          "read", "last_edited", "created_at",
                          "gcal_error", "zoom_error", "storage", "calendar_link",
                          "meeting_id", "duration_minutes", "ics", "html",
                          "file_id", "doc_id", "page_id", "form_id", "event_id",
                          "message_id", "message_ts", "channel", "name",
                          "timestamp", "to", "subject", "url", "attendees",
                          "webhook_error", "setup",
                          "conflict", "existing", "proposed", "message"})

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
    # Render URLs as clickable markdown links
    if isinstance(val, str) and val.startswith(("http://", "https://")):
        return f"[Open ↗]({val})"
    return str(val)


def _success_header(res: dict) -> str:
    """Return a one-line success headline based on what keys are in the result."""
    if res.get("channel") and res.get("message_ts"):
        return f"Posted to #{res['channel']}."
    if res.get("smtp_sent") or res.get("message_id"):
        return "Email sent."
    if res.get("link") and res.get("platform"):
        platform = str(res["platform"]).replace("_", " ").title()
        return f"{platform} meeting scheduled."
    if res.get("link") and "calendar" in str(res.get("storage", "")):
        return "Meeting scheduled."
    if res.get("file_id") or (res.get("name") and res.get("link")):
        return f"Created **{res.get('name') or res.get('title') or 'document'}**."
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
            # Meeting conflict — render as a gentle notice, let frontend handle UI
            if res.get("conflict"):
                existing = res.get("existing", {}) or {}
                when = _format_value("start", existing.get("start", ""))
                title = existing.get("title", "a meeting")
                parts.append(
                    f"You already have **{title}** scheduled on {when}. "
                    f"Would you like to replace it with the new meeting?"
                )
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
                (k for k in ("title", "name", "repo", "full_name", "subject", "from", "path") if first.get(k)),
                None,
            )
            bullets = []
            for item in res:
                if isinstance(item, dict):
                    primary = item.get(label_key, "") if label_key else ""
                    secondary = ""
                    for sk in ("start", "date", "snippet", "url", "link", "html_url"):
                        if item.get(sk):
                            secondary = f" — {_format_value(sk, item[sk])}"
                            break
                    # Fallback: join first two string values if no label found
                    if not primary:
                        vals = [str(v) for v in item.values() if v and isinstance(v, str)]
                        primary = vals[0] if vals else "—"
                    bullets.append(f"- {primary}{secondary}")
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

        replace_plan = self._maybe_replace_plan(user_input)
        if replace_plan is not None:
            self._patch_dates(replace_plan, user_input)
            self.state.save(replace_plan)
            return self._execute(replace_plan, user_input, log)

        if self.state.is_followup(user_input):
            log.add("followup", "merging")
            plan = self.state.merge(user_input)
            return self._execute(plan, user_input, log)

        if GROQ_API_KEY:
            plan = self._plan(user_input, log)
        else:
            plan = {"intent": "unknown", "steps": []}

        self._patch_dates(plan, user_input)
        self.state.save(plan)
        return self._execute(plan, user_input, log)

    def process_stream(self, user_input: str):
        """Generator: yields SSE events as each agent step executes in real time."""
        import json

        def evt(obj: dict) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        AGENT_ICONS = {
            "mail": "📧", "calendar": "📅", "meeting": "📹",
            "drive": "📁", "docs": "📄", "forms": "📋",
            "slack": "💬", "discord": "🎮", "notion": "📓",
            "github": "🐙", "code": "💻", "file": "📂", "search": "🔍",
        }
        ACTION_LABELS = {
            "send": "Sending email", "read": "Reading inbox",
            "schedule": "Scheduling meeting", "list": "Fetching list",
            "write_doc": "Creating document", "search": "Searching",
            "send_message": "Posting to Slack", "create": "Creating",
            "read_messages": "Reading messages", "list_files": "Listing files",
        }

        log = ExecutionLog()
        log.add("input", user_input)
        yield evt({"type": "planning"})

        try:
            replace_plan = self._maybe_replace_plan(user_input)
            if replace_plan is not None:
                plan = replace_plan
            elif self.state.is_followup(user_input):
                plan = self.state.merge(user_input)
            elif GROQ_API_KEY:
                plan = self._plan(user_input, log)
            else:
                plan = {"intent": "unknown", "steps": []}

            self._patch_dates(plan, user_input)
            self.state.save(plan)

            steps = plan.get("steps", [])
            intent = plan.get("intent", "unknown")
            total = len(steps)

            if not steps:
                reply = self._capability_list() if intent == "unknown" else "How can I help you?"
                yield evt({"type": "done", "plan": [], "results": [], "log": log.entries, "reply": reply})
                return

            display_plan = [
                {"step": i + 1, "agent": s.get("agent", "?"), "action": s.get("action", "?"),
                 "label": f"{s.get('agent','?')}.{s.get('action','?')}"}
                for i, s in enumerate(steps)
            ]

            context = {**self.state.memory, **self.state.context}
            last_meeting = self._last_stored("meetings.json")
            results = []

            for i, step in enumerate(steps):
                try:
                    agent_name, action, params = self._normalise_step(step)
                except Exception as e:
                    results.append({"ok": False, "error": f"Invalid step: {e}", "status": "failed", "retries": 0})
                    continue

                action_label = ACTION_LABELS.get(action, action.replace("_", " ").title())
                icon = AGENT_ICONS.get(agent_name, "⚙️")

                yield evt({
                    "type": "step",
                    "index": i,
                    "total": total,
                    "agent": agent_name,
                    "label": f"{action_label}…",
                    "icon": icon,
                })

                label = f"{agent_name}.{action}"
                log.add("step", label)

                if agent_name == "search":
                    try:
                        res = search_all_sources(params.get("query", user_input))
                        results.append({"ok": True, "result": res, "status": "success", "retries": 0})
                        if isinstance(res, dict):
                            context.update(res)
                    except Exception as e:
                        results.append({"ok": False, "error": f"Search failed: {e}", "status": "failed", "retries": 0})
                    continue

                agent = self.agents.get(agent_name)
                if not agent:
                    results.append({"ok": False, "error": f"Unknown agent: {agent_name}", "status": "failed", "retries": 0})
                    if not self.auto_mode:
                        break
                    continue

                try:
                    missing = _validate_and_fill(params, agent_name, action, context, last_meeting)
                except Exception as e:
                    results.append({"ok": False, "error": f"Validation failed: {e}", "status": "failed", "retries": 0})
                    continue

                if missing:
                    results.append({"ok": False, "error": f"Please provide: {', '.join(missing)}", "status": "skipped", "retries": 0})
                    continue

                try:
                    result = agent.handle(action, params)
                except Exception as e:
                    result = {"ok": False, "error": str(e)}

                results.append({**result, "status": "success" if result.get("ok") else "failed", "retries": 0})

                if result.get("ok"):
                    res = result.get("result", {})
                    if isinstance(res, dict):
                        if res.get("conflict"):
                            log.add("conflict", label)
                            break
                        context.update({k: v for k, v in res.items() if v})
                    log.add("ok", label)
                else:
                    log.add("fail", f"{label}: {result.get('error','?')}")
                    if not self.auto_mode:
                        break

            reply = _build_reply(results)
            try:
                save_memory(user_input, extract_entities(user_input, results), results)
            except Exception:
                pass  # memory save is non-critical
            yield evt({"type": "done", "plan": display_plan, "results": results, "log": log.entries, "reply": reply})
        except Exception as e:
            # Top-level catch: guarantees the stream always closes with a done event
            yield evt({
                "type": "done",
                "plan": [],
                "results": [{"ok": False, "error": f"Server error: {type(e).__name__}: {e}"}],
                "log": log.entries,
                "reply": "Something went wrong on the server. Please try again.",
            })

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

        # Last known contact — lets LLM resolve pronouns like "her", "him", "them"
        if self.state.memory.get("last_email"):
            ctx_parts.append(f"Last contact: {self.state.memory['last_email']}")

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
        # Seed with current plan params + persistent cross-turn memory (emails, etc.)
        context = {**self.state.memory, **self.state.context}

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
                results.append({"ok": False,
                                 "error": f"Please provide: {', '.join(missing)}",
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
                    if res.get("conflict"):
                        log.add("conflict", label)
                        break
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

    def _maybe_replace_plan(self, user_input: str) -> dict | None:
        """
        Handle "/replace <meeting_id>" — rebuild the pending meeting step with
        replace_existing_id set so the agent deletes the conflict first.
        Returns None if the input isn't a replace command.
        """
        text = user_input.strip()
        if not text.startswith("/replace"):
            return None
        parts = text.split(None, 1)
        meeting_id = parts[1].strip() if len(parts) > 1 else ""
        if not meeting_id:
            return None

        # Find the pending meeting.schedule step saved in state
        for step in self.state.steps:
            if step.get("agent") == "meeting" and step.get("action") == "schedule":
                params = dict(step.get("params") or {})
                params["replace_existing_id"] = meeting_id
                return {
                    "intent": "schedule",
                    "steps": [{"agent": "meeting", "action": "schedule", "params": params}],
                }
        return None

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
