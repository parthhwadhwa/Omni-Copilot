"""
Orchestrator v5: Groq-powered, token-optimized.
- Single LLM call per request (planner only)
- Rule-based follow-up handling (no LLM)
- Query+plan caching
- Graceful fallback if no API key
"""

from __future__ import annotations
import re
from datetime import datetime, timedelta
from agents import ALL_AGENTS
from config import GROQ_API_KEY
from memory import save_memory, retrieve_memory, resolve_references, extract_entities
from search import search_all_sources


# ---------------------------------------------------------------------------
# Rule-based date/time parser (no LLM needed)
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
    for day_name, offset in [("monday", 0), ("tuesday", 1), ("wednesday", 2),
                              ("thursday", 3), ("friday", 4), ("saturday", 5), ("sunday", 6)]:
        if day_name in lower:
            current = today.weekday()
            diff = (offset - current) % 7
            if diff == 0:
                diff = 7
            return (today + timedelta(days=diff)).isoformat()
    if m := re.search(r"(\d{4}-\d{2}-\d{2})", text):
        return m.group(1)
    return None


def _parse_time(text: str) -> str | None:
    if m := re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", text, re.I):
        h, mi, ap = int(m.group(1)), m.group(2), (m.group(3) or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mi}:00"
    if m := re.search(r"(\d{1,2})\s*(am|pm)", text, re.I):
        h, ap = int(m.group(1)), m.group(2).lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return f"{h:02d}:00:00"
    return None


# ---------------------------------------------------------------------------
# Follow-up state: accumulate fragments without LLM
# ---------------------------------------------------------------------------
class ConversationState:
    """Tracks partial task state for follow-up resolution."""

    def __init__(self):
        self.pending_intent: str | None = None
        self.pending_agent: str | None = None
        self.pending_action: str | None = None
        self.pending_params: dict = {}
        self.last_query: str = ""
        self.last_plan: dict | None = None  # cache

    def is_followup(self, text: str) -> bool:
        """Check if this looks like a follow-up to a pending task."""
        if not self.pending_intent:
            return False
        lower = text.lower().strip()
        words = lower.split()

        # Greetings → clear state, not a follow-up
        chat_words = {"hey", "hi", "hello", "whats up", "what's up", "how are you",
                      "help", "thanks", "thank you", "bye", "quit"}
        if lower in chat_words or any(lower.startswith(w) for w in chat_words):
            self.clear()
            return False

        # Long messages (>6 words) with action verbs = new request
        action_verbs = {"send", "schedule", "create", "show", "list", "read",
                        "write", "check", "open", "search", "find", "book"}
        if len(words) > 6:
            return False
        if len(words) > 3 and any(w in action_verbs for w in words):
            return False

        # Any short message (≤6 words) without action verbs is treated as follow-up
        # — covers "title is X", "call it X", "3pm", "tomorrow noon", "zoom", etc.
        return True

    def merge(self, text: str, use_llm: bool = False) -> dict:
        """Merge follow-up into pending params. Date/time via rules; everything else via LLM."""
        valid_keys = _get_param_keys(self.pending_agent, self.pending_action)
        date = _parse_date(text)
        time = _parse_time(text)

        # Date/time: always rule-based (fast, reliable)
        if date and "start" in valid_keys:
            if "start" in self.pending_params:
                old = self.pending_params["start"]
                self.pending_params["start"] = f"{date}T{old.split('T')[1]}" if "T" in old else f"{date}T10:00:00"
            else:
                self.pending_params["start"] = f"{date}T10:00:00"
        if date and "date" in valid_keys:
            self.pending_params["date"] = date
        if time and "start" in valid_keys:
            if "start" in self.pending_params:
                old = self.pending_params["start"]
                self.pending_params["start"] = f"{old.split('T')[0]}T{time}"
            elif date:
                self.pending_params["start"] = f"{date}T{time}"
            else:
                today = datetime.now().date().isoformat()
                self.pending_params["start"] = f"{today}T{time}"

        # Quoted text → title/subject directly
        if m := re.search(r'"([^"]+)"', text):
            val = m.group(1)
            for key in ("title", "subject", "text", "content"):
                if key in valid_keys:
                    self.pending_params[key] = val
                    break

        # Non-date/time text → ask LLM to extract only the param value
        elif not date and not time and use_llm:
            from groq import Groq
            from config import GROQ_API_KEY
            client = Groq(api_key=GROQ_API_KEY)
            _DEFAULT_TITLES = {"meeting", "untitled", "new meeting", "new event", "event", ""}
            prompt = (
                f"The user is completing a '{self.pending_agent}.{self.pending_action}' request.\n"
                f"Current params: {self.pending_params}\n"
                f"Valid param names: {sorted(valid_keys)}\n"
                f"User just said: \"{text}\"\n\n"
                f"Extract ONLY the param updates implied by what the user said.\n"
                f"Output ONLY a flat JSON object like: {{\"title\": \"value\"}} — nothing else."
            )
            try:
                raw = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=128,
                ).choices[0].message.content.strip()
                # Extract JSON
                s, e = raw.find("{"), raw.rfind("}") + 1
                updates = __import__("json").loads(raw[s:e]) if s != -1 and e > s else {}
                for k, v in updates.items():
                    if k in valid_keys and v:
                        # Don't let LLM overwrite a real value with a generic default
                        current = str(self.pending_params.get(k, "")).lower()
                        if k == "title" and current not in _DEFAULT_TITLES:
                            continue
                        self.pending_params[k] = v
            except Exception:
                pass

        return {
            "intent": self.pending_intent,
            "steps": [{
                "agent": self.pending_agent,
                "action": self.pending_action,
                "params": self.pending_params,
            }],
        }

    def save(self, plan: dict):
        """Cache a plan and extract pending state."""
        self.last_plan = plan
        steps = plan.get("steps", [])
        if steps:
            s = steps[0]
            self.pending_intent = plan.get("intent", "")
            self.pending_agent = s.get("agent")
            self.pending_action = s.get("action")
            self.pending_params = dict(s.get("params", {}))
        else:
            self.clear()

    def clear(self):
        self.pending_intent = None
        self.pending_agent = None
        self.pending_action = None
        self.pending_params = {}
        self.last_plan = None

    def has_cache(self, query: str) -> bool:
        """Check if query is similar enough to reuse cached plan."""
        if not self.last_plan or not self.last_query:
            return False
        return query.strip().lower() == self.last_query.strip().lower()


def _get_param_keys(agent_name: str | None, action: str | None) -> set:
    """Get valid param keys for an agent action."""
    if not agent_name or not action:
        return set()
    cls = ALL_AGENTS.get(agent_name)
    if not cls:
        return set()
    agent = cls()
    for tool in agent.tools:
        if tool["action"] == action:
            return set(tool["params"].get("properties", {}).keys())
    return set()


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

        # 1. Check follow-up — date/time via rules, everything else via LLM
        if self.state.is_followup(user_input):
            log.add("followup", "Merging into pending task")
            plan = self.state.merge(user_input, use_llm=bool(GROQ_API_KEY))
            return self._execute(plan, user_input, log)

        # 2. Check cache
        if self.state.has_cache(user_input):
            log.add("cache_hit", "Reusing cached plan")
            return self._execute(self.state.last_plan, user_input, log)

        # 3. LLM planning (single call) or fallback
        if GROQ_API_KEY:
            plan = self._plan_with_llm(user_input, log)
        else:
            plan = self._plan_fallback(user_input, log)

        # 4. Inject rule-based date/time if LLM missed them
        self._patch_dates(plan, user_input)

        # 5. Save state + execute
        self.state.last_query = user_input
        self.state.save(plan)
        return self._execute(plan, user_input, log)

    def _plan_with_llm(self, user_input: str, log: ExecutionLog) -> dict:
        """Single strict planning call — returns {intent, steps} only."""
        from llm import call_llm
        today = datetime.now().date().isoformat()
        prompt = f"[Today: {today}] {user_input}"
        log.add("llm_call", "Planning with Groq")
        plan = call_llm(prompt)
        # Strip any rogue 'reply' field — planner never generates chat
        plan.pop("reply", None)
        log.add("llm_result", f"intent={plan.get('intent', '?')}, steps={len(plan.get('steps', []))}")
        return plan

    def _plan_fallback(self, user_input: str, log: ExecutionLog) -> dict:
        """Rule-based planning (no LLM)."""
        from planner import generate_plan
        from selector import select_agent_and_action

        steps = generate_plan(user_input)
        if not steps:
            agent_name, action, confidence = select_agent_and_action(user_input)
            if confidence > 0:
                steps = [{"step": 1, "agent": agent_name, "action": action,
                          "label": f"{agent_name}.{action}", "depends_on": []}]

        if not steps:
            return {"intent": "unknown", "steps": [],
                    "reply": "I didn't understand that. Try 'send an email', 'schedule a meeting', or 'show my calendar'."}

        # Convert planner format to orchestrator format
        converted = []
        for s in steps:
            params = self._extract_params_fallback(user_input, s["agent"], s["action"])
            converted.append({"agent": s["agent"], "action": s["action"], "params": params})

        log.add("fallback_plan", f"{len(converted)} step(s)")
        return {"intent": "task", "steps": converted}

    def _patch_dates(self, plan: dict, user_input: str):
        """Inject parsed dates/times into plan steps. Rule-based parser wins over LLM."""
        date = _parse_date(user_input)
        time = _parse_time(user_input)
        date_actions = {"create_event", "update_event", "schedule", "list_events"}
        start_actions = {"create_event", "update_event", "schedule"}
        for step in plan.get("steps", []):
            action = step.get("action", "")
            params = step.get("params", {})
            if action not in date_actions:
                continue
            if date and action == "list_events":
                params["date"] = date
            if action in start_actions:
                existing = str(params.get("start", ""))
                if date and time:
                    # Always use rule-based time — more reliable than LLM
                    params["start"] = f"{date}T{time}"
                elif date and existing and "T" in existing:
                    # Keep LLM time but fix date
                    params["start"] = f"{date}T{existing.split('T')[1]}"
                elif date and not existing:
                    params["start"] = f"{date}T10:00:00"

    # Static responses for intents with no steps
    _UNKNOWN_REPLY = (
        "I can help you with:\n"
        "• Schedule a meeting\n"
        "• Send an email\n"
        "• Send a Slack message\n"
        "• Show calendar / meetings\n"
        "• Create or write a doc\n"
        "• Search across your data\n\n"
        "Try: \"Schedule a meeting with Alice tomorrow at 3pm\""
    )

    def _execute(self, plan: dict, user_input: str, log: ExecutionLog) -> dict:
        """Execute plan steps. No LLM calls here."""
        steps = plan.get("steps", [])
        intent = plan.get("intent", "unknown")

        # No tools — return static guidance
        if not steps:
            reply = self._UNKNOWN_REPLY if intent == "unknown" else plan.get("reply", "How can I help you?")
            return {"plan": [], "results": [], "log": log.entries, "reply": reply}

        # Build display plan
        display_plan = []
        for i, s in enumerate(steps):
            display_plan.append({
                "step": i + 1,
                "agent": s.get("agent", "?"),
                "action": s.get("action", "?"),
                "label": f"{s.get('agent', '?')}.{s.get('action', '?')}",
                "depends_on": list(range(i)) if i > 0 else [],
            })

        # Execute
        results = []
        prev_result = None
        for i, step in enumerate(steps):
            agent_name = step.get("agent", "")
            action = step.get("action", "")
            params = step.get("params", {})
            # Handle LLM returning "agent.action" in agent field
            if "." in agent_name and agent_name not in self.agents:
                parts = agent_name.rsplit(".", 1)
                agent_name = parts[0]
                if not action:
                    action = parts[1]

            # Strip agent prefix from action if LLM put "agent.action" in action field
            if "." in action:
                action = action.rsplit(".", 1)[1]

            # Auto-correct common LLM action name hallucinations
            _ACTION_ALIASES = {
                "meeting": {"schedule_meeting": "schedule", "create_meeting": "schedule",
                            "create": "schedule", "list_meetings": "list"},
                "calendar": {"create": "create_event", "list": "list_events",
                             "schedule": "create_event", "schedule_event": "create_event"},
                "mail": {"send_email": "send", "send_mail": "send",
                         "read_email": "read", "read_mail": "read"},
                "slack": {"send": "send_message", "post": "send_message"},
                "discord": {"send": "send_message", "post": "send_message"},
                "docs": {"create": "write_doc", "save": "write_doc",
                         "read": "read_doc", "list": "list_docs"},
                "notion": {"create": "write_page", "list": "list_pages",
                           "read": "read_page"},
            }
            if agent_name in _ACTION_ALIASES and action in _ACTION_ALIASES[agent_name]:
                action = _ACTION_ALIASES[agent_name][action]

            label = f"{agent_name}.{action}"
            log.add("step_start", f"Step {i + 1}: {label}")

            # Search pseudo-agent
            if agent_name == "search":
                query = params.get("query", user_input)
                sr = {"ok": True, "result": search_all_sources(query)}
                results.append({**sr, "status": "success", "retries": 0})
                prev_result = sr.get("result")
                continue

            agent = self.agents.get(agent_name)
            if not agent:
                results.append({"ok": False, "error": f"Unknown agent: {agent_name}", "status": "failed", "retries": 0})
                log.add("step_fail", f"Unknown agent: {agent_name}")
                if not self.auto_mode:
                    break
                continue

            # Inject previous result / last meeting context into params
            self._inject_prev_result(params, prev_result or {}, agent_name, action)

            try:
                result = agent.handle(action, params)
            except Exception as e:
                result = {"ok": False, "error": str(e)}

            results.append({
                **result,
                "status": "success" if result.get("ok") else "failed",
                "retries": 0,
            })
            prev_result = result.get("result", result)

            if result.get("ok"):
                log.add("step_done", f"{label}: success")
            else:
                log.add("step_fail", f"{label}: {result.get('error', '?')}")
                if not self.auto_mode:
                    break

        # Build reply from results (no LLM call)
        reply = self._build_reply(results)

        # Save memory
        entities = extract_entities(user_input, results)
        save_memory(user_input, entities, results)

        return {"plan": display_plan, "results": results, "log": log.entries, "reply": reply}

    def _last_meeting(self) -> dict:
        """Return the most recently scheduled meeting from storage."""
        from agents.base import load_data
        meetings = load_data("meetings.json")
        if not meetings:
            return {}
        return sorted(meetings, key=lambda m: m.get("created_at", ""))[-1]

    def _inject_prev_result(self, params: dict, prev: dict, agent_name: str, action: str):
        """Build contextual content from previous step results."""
        # If sending mail standalone with empty body, fall back to last meeting
        if agent_name == "mail" and action == "send" and not params.get("body"):
            if not (prev.get("title") or prev.get("link")):
                prev = self._last_meeting()

        title = prev.get("title", "")
        link = prev.get("link", "")
        start = prev.get("start", "")
        platform = prev.get("platform", "")

        # Parse date and time from ISO start
        date_str, time_str = "", ""
        if start and "T" in start:
            date_str, time_str = start.split("T", 1)
            # Format time nicely
            try:
                t = datetime.strptime(time_str, "%H:%M:%S")
                time_str = t.strftime("%I:%M %p").lstrip("0")
            except ValueError:
                pass

        # Sanitize any raw placeholder text in params
        for key, val in params.items():
            if isinstance(val, str) and ("{{" in val or "{PREV_RESULT}" in val):
                params[key] = ""

        # Build professional email body if sending mail after a meeting/calendar step
        if agent_name == "mail" and action == "send" and (title or link):
            body = "Hi,\n\nYour meeting has been scheduled successfully.\n"
            if title:
                body += f"\nTitle: {title}"
            if date_str:
                body += f"\nDate: {date_str}"
            if time_str:
                body += f"\nTime: {time_str}"
            if platform:
                body += f"\nPlatform: {platform.replace('_', ' ').title()}"
            if link:
                body += f"\n\nYou can join using the link below:\n{link}"
            body += "\n\nRegards,\nOmni Copilot"
            params["body"] = body
            if not params.get("subject"):
                params["subject"] = f"Meeting Scheduled: {title}" if title else "Meeting Scheduled"

        # Slack: append link if relevant
        elif agent_name == "slack" and action == "send_message" and link:
            text = params.get("text", "")
            if link not in text:
                params["text"] = f"{text}\n\nMeeting link: {link}".strip()

        # Discord: append link if relevant
        elif agent_name == "discord" and action == "send_message" and link:
            content = params.get("content", "")
            if link not in content:
                params["content"] = f"{content}\n\nMeeting link: {link}".strip()

        # Generic: append link to content/body fields
        elif link:
            for key in ("body", "text", "content"):
                if key in params and link not in params[key]:
                    params[key] += f"\n\nLink: {link}"

    def _build_reply(self, results: list[dict]) -> str:
        """Generate a single clean reply summarizing all results."""
        ok_count = sum(1 for r in results if r.get("ok"))
        total = len(results)

        if total == 0:
            return "Done."

        if ok_count == 0:
            errors = [r.get("error", "unknown") for r in results if not r.get("ok")]
            return f"Something went wrong: {'; '.join(errors)}"

        actions_done = []   # for action confirmations  (e.g. "meeting scheduled")
        list_lines = []     # for list results           (e.g. bullet rows)
        list_header = ""    # header for list results
        detail_lines = []   # sub-details for actions   (title, date, link …)

        for r in results:
            res = r.get("result", {})

            # ── Action result (dict) ──────────────────────────────────────────
            if isinstance(res, dict):
                if "meeting_id" in res:
                    title = res.get("title", "Meeting")
                    start = res.get("start", "")
                    link = res.get("link", "")
                    platform = res.get("platform", "")
                    actions_done.append("meeting scheduled")
                    detail_lines.append(f"  Title: {title}")
                    if start and "T" in start:
                        d, t = start.split("T", 1)
                        try:
                            t = datetime.strptime(t, "%H:%M:%S").strftime("%I:%M %p").lstrip("0")
                        except ValueError:
                            pass
                        detail_lines.append(f"  Date: {d}")
                        detail_lines.append(f"  Time: {t}")
                    if platform:
                        detail_lines.append(f"  Platform: {platform.replace('_', ' ').title()}")
                    if link:
                        detail_lines.append(f"  Link: {link}")
                elif "channel" in res and "webhook_sent" not in res:
                    # Slack message (has channel but not webhook_sent)
                    actions_done.append(f"message sent to #{res.get('channel', '')}")
                elif "webhook_sent" in res and "content" in res:
                    # Discord message
                    status = res.get("status", "")
                    if status == "sent":
                        actions_done.append("Discord message sent")
                    else:
                        err = res.get("webhook_error", "webhook not configured")
                        actions_done.append(f"Discord message saved locally ({err})")
                elif "webhook_sent" in res and "channel" in res:
                    # Slack with webhook info
                    if res.get("webhook_sent"):
                        actions_done.append(f"Slack message sent to #{res.get('channel', '')}")
                    else:
                        actions_done.append(f"Slack message saved locally (webhook not configured)")
                elif res.get("message_id") or res.get("smtp_sent"):
                    actions_done.append("email sent")
                elif "event_id" in res:
                    actions_done.append(f"event created: {res.get('title', '')}")
                elif "doc_id" in res:
                    actions_done.append(f"document saved: {res.get('title', '')}")
                elif "form_id" in res:
                    actions_done.append(f"form created: {res.get('title', '')}")
                elif "page_id" in res and res.get("status") == "created":
                    actions_done.append(f"Notion page created: {res.get('title', '')}")
                    if res.get("url"):
                        detail_lines.append(f"  URL: {res.get('url')}")
                elif "connected" in res:
                    # Status check response
                    name = res.get("method", "Integration")
                    if res.get("connected"):
                        actions_done.append(f"{name} connected")
                    else:
                        err = res.get("error", res.get("setup", "not configured"))
                        actions_done.append(f"Not connected: {err}")

            # ── List result ───────────────────────────────────────────────────
            elif isinstance(res, list):
                if not res:
                    list_header = "Nothing found."
                    continue
                first = res[0] if isinstance(res[0], dict) else {}

                if "meeting_id" in first or ("link" in first and "meeting" in str(first.get("link", ""))):
                    list_header = f"Here are your {len(res)} meeting(s):"
                    for m in res:
                        line = f"• {m.get('title', 'Untitled')}"
                        start = m.get("start", "")
                        if start and "T" in start:
                            d, t = start.split("T", 1)
                            try:
                                t = datetime.strptime(t, "%H:%M:%S").strftime("%I:%M %p").lstrip("0")
                            except ValueError:
                                pass
                            line += f" — {d} at {t}"
                        link = m.get("link", "")
                        if link:
                            line += f"\n  {link}"
                        list_lines.append(line)

                elif "event_id" in first:
                    list_header = f"Here are your {len(res)} event(s):"
                    for e in res:
                        line = f"• {e.get('title', 'Untitled')}"
                        start = e.get("start", "")
                        if start and "T" in start:
                            d, t = start.split("T", 1)
                            try:
                                t = datetime.strptime(t, "%H:%M:%S").strftime("%I:%M %p").lstrip("0")
                            except ValueError:
                                pass
                            line += f" — {d} at {t}"
                        attendees = e.get("attendees", [])
                        if attendees:
                            line += f"\n  Attendees: {', '.join(attendees)}"
                        list_lines.append(line)

                elif "message_id" in first or "from" in first:
                    list_header = f"Here are your {len(res)} email(s):"
                    for e in res:
                        list_lines.append(f"• From: {e.get('from', '?')}  |  {e.get('subject', '')}")

                elif "page_id" in first:
                    list_header = f"Here are your {len(res)} Notion page(s):"
                    for p in res:
                        line = f"• {p.get('title', 'Untitled')}"
                        if p.get("url"):
                            line += f"\n  {p.get('url')}"
                        list_lines.append(line)

                elif "doc_id" in first:
                    list_header = f"Here are your {len(res)} doc(s):"
                    for d in res:
                        list_lines.append(f"• {d.get('title', 'Untitled')}")

                elif "form_id" in first:
                    list_header = f"Here are your {len(res)} form(s):"
                    for f in res:
                        list_lines.append(f"• {f.get('title', 'Untitled')}")

                else:
                    list_header = f"Found {len(res)} item(s):"
                    for item in res:
                        if isinstance(item, dict):
                            label = item.get("title") or item.get("name") or item.get("path") or str(item)
                        else:
                            label = str(item)
                        list_lines.append(f"• {label}")

        # ── Assemble reply ────────────────────────────────────────────────────
        # Pure list response (empty)
        if not list_lines and list_header == "Nothing found.":
            return "Nothing here yet."
        # Pure list response
        if list_lines and not actions_done:
            summary = list_header + "\n\n" + "\n".join(list_lines)
        # Pure action response
        elif actions_done and not list_lines:
            summary = " and ".join(dict.fromkeys(actions_done)) + " successfully."
            summary = summary[0].upper() + summary[1:]
            if detail_lines:
                summary += "\n\n" + "\n".join(detail_lines)
        # Mixed (e.g. listed then acted)
        elif actions_done and list_lines:
            action_part = " and ".join(dict.fromkeys(actions_done)) + " successfully."
            action_part = action_part[0].upper() + action_part[1:]
            if detail_lines:
                action_part += "\n\n" + "\n".join(detail_lines)
            summary = action_part + "\n\n" + list_header + "\n" + "\n".join(list_lines)
        else:
            return "Done!"

        if ok_count < total:
            failed = [r.get("error", "?") for r in results if not r.get("ok")]
            summary += f"\n\n(Some steps had issues: {'; '.join(failed)})"

        return summary

    def _extract_params_fallback(self, user_input: str, agent_name: str, action: str) -> dict:
        """Rule-based param extraction for fallback mode."""
        params = {}
        lower = user_input.lower()
        date = _parse_date(user_input) or datetime.now().date().isoformat()
        time = _parse_time(user_input)

        hints = resolve_references(user_input)
        for k, v in hints.items():
            if k != "reuse_last":
                params[k] = v

        if agent_name == "mail" and action == "send":
            if m := re.search(r"to\s+(\S+@\S+)", user_input):
                params["to"] = m.group(1)
            if m := re.search(r'subject\s+"([^"]+)"', user_input, re.I):
                params["subject"] = m.group(1)
            elif m := re.search(r"about\s+(.+?)(?:\s+body|\s+saying|\s+and\s|$)", user_input, re.I):
                params["subject"] = m.group(1).strip()
            if m := re.search(r'(?:body|saying|message)\s+"([^"]+)"', user_input, re.I):
                params["body"] = m.group(1)
            params.setdefault("to", "recipient@example.com")
            params.setdefault("subject", "No Subject")
            params.setdefault("body", "Sent from Omni Copilot")

        elif agent_name == "calendar":
            if action == "list_events":
                params.setdefault("date", date)
            elif action == "create_event":
                if m := re.search(r'(?:titled?|called)\s+"([^"]+)"', user_input, re.I):
                    params["title"] = m.group(1)
                else:
                    params.setdefault("title", "New Event")
                params.setdefault("start", f"{date}T{time or '10:00:00'}")

        elif agent_name == "slack":
            if m := re.search(r"(?:to|in|on)\s+#?(\w+)", user_input, re.I):
                params["channel"] = m.group(1)
            else:
                params.setdefault("channel", "general")
            if action == "send_message":
                if m := re.search(r'(?:saying|message)\s+"([^"]+)"', user_input, re.I):
                    params["text"] = m.group(1)
                else:
                    params.setdefault("text", user_input)

        elif agent_name == "discord":
            if action == "send_message":
                if m := re.search(r'(?:saying|message)\s+"([^"]+)"', user_input, re.I):
                    params["content"] = m.group(1)
                else:
                    params.setdefault("content", user_input)

        elif agent_name == "meeting":
            if m := re.search(r'(?:titled?|called)\s+"([^"]+)"', user_input, re.I):
                params["title"] = m.group(1)
            else:
                params.setdefault("title", "Meeting")
            params.setdefault("start", f"{date}T{time or '15:00:00'}")
            if "zoom" in lower:
                params["platform"] = "zoom"

        elif agent_name == "docs":
            if action == "read_doc":
                params.setdefault("doc_id", "doc_00001")
            elif action == "write_doc":
                if m := re.search(r'titled?\s+"([^"]+)"', user_input, re.I):
                    params["title"] = m.group(1)
                else:
                    params.setdefault("title", "Untitled")
                params.setdefault("content", "Content from Omni Copilot")

        elif agent_name == "notion":
            if action == "read_page":
                params.setdefault("page_id", "page_001")
            elif action == "write_page":
                if m := re.search(r'titled?\s+"([^"]+)"', user_input, re.I):
                    params["title"] = m.group(1)
                else:
                    params.setdefault("title", "Untitled")
                params.setdefault("content", "Content from Omni Copilot")

        elif agent_name == "forms":
            if action == "create":
                params.setdefault("title", "Feedback Form")
                params.setdefault("questions", [{"text": "How was your experience?", "type": "multiple_choice", "options": ["Great", "Good", "Okay", "Poor"]}])
            elif action == "get_responses":
                params.setdefault("form_id", "form_00001")

        elif agent_name == "file":
            if m := re.search(r'file\s+"?([^\s"]+)"?', user_input, re.I):
                params["path"] = m.group(1)
            else:
                params.setdefault("path", ".")
            if action == "write":
                params.setdefault("content", "Hello from Omni Copilot")

        return params

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
