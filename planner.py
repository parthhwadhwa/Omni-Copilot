"""
Advanced Planner v3: decompose queries into ordered steps with dependencies.
Supports sub-step decomposition, composite workflows, and slash commands.
"""

from __future__ import annotations
import re

# ---------------------------------------------------------------------------
# Sub-step decomposition: complex tasks auto-expand into atomic steps
# ---------------------------------------------------------------------------
SUB_STEPS: dict[str, list[dict]] = {
    "prepare_meeting": [
        {"agent": "calendar", "action": "create_event", "label": "Create calendar event", "depends_on": []},
        {"agent": "docs", "action": "write_doc", "label": "Generate meeting agenda", "depends_on": [0]},
        {"agent": "mail", "action": "send", "label": "Send invite with agenda", "depends_on": [0, 1]},
    ],
    "onboard_project": [
        {"agent": "docs", "action": "write_doc", "label": "Create project doc", "depends_on": []},
        {"agent": "slack", "action": "send_message", "label": "Announce in Slack", "depends_on": [0]},
        {"agent": "calendar", "action": "create_event", "label": "Schedule kickoff", "depends_on": [0]},
        {"agent": "mail", "action": "send", "label": "Send welcome email", "depends_on": [0, 2]},
    ],
    "daily_briefing": [
        {"agent": "mail", "action": "read", "label": "Check inbox", "depends_on": []},
        {"agent": "calendar", "action": "list_events", "label": "List today's events", "depends_on": []},
        {"agent": "slack", "action": "read_messages", "label": "Check Slack", "depends_on": []},
        {"agent": "docs", "action": "write_doc", "label": "Compile briefing", "depends_on": [0, 1, 2]},
    ],
    "summarize_and_share": [
        {"agent": "search", "action": "search_all", "label": "Search all sources", "depends_on": []},
        {"agent": "docs", "action": "write_doc", "label": "Write summary doc", "depends_on": [0]},
        {"agent": "mail", "action": "send", "label": "Email summary", "depends_on": [1]},
    ],
    "schedule_and_notify": [
        {"agent": "meeting", "action": "schedule", "label": "Schedule meeting", "depends_on": []},
        {"agent": "calendar", "action": "create_event", "label": "Add to calendar", "depends_on": [0]},
        {"agent": "mail", "action": "send", "label": "Send notification", "depends_on": [0]},
        {"agent": "slack", "action": "send_message", "label": "Notify on Slack", "depends_on": [0]},
    ],
}

# Composite trigger patterns → sub-step key
COMPOSITE_TRIGGERS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"prepare\s+(a\s+)?meeting|set\s*up\s+(a\s+)?meeting\s+with", re.I), "prepare_meeting"),
    (re.compile(r"onboard|kick\s*off|start\s+(a\s+)?project", re.I), "onboard_project"),
    (re.compile(r"daily\s+briefing|morning\s+summary|brief\s+me|catch\s+me\s+up", re.I), "daily_briefing"),
    (re.compile(r"summarize.+(?:and|then)\s+(?:share|email|send|mail)", re.I), "summarize_and_share"),
    (re.compile(r"schedule.+(?:and|then)\s+(?:notify|tell|send|slack|email)", re.I), "schedule_and_notify"),
    (re.compile(r"schedule\s+(?:a\s+)?meeting.+(?:and|then)\s+(?:send|notify|email|slack)", re.I), "schedule_and_notify"),
]

# ---------------------------------------------------------------------------
# Single-step intent patterns (unchanged from v2, but now with depends_on)
# ---------------------------------------------------------------------------
SINGLE_INTENTS: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"send\s+(an?\s+)?email|email\s+\S+", re.I),
     {"agent": "mail", "action": "send", "label": "Send email"}),
    (re.compile(r"read\s+(my\s+)?emails?|check\s+(my\s+)?inbox|show\s+(my\s+)?emails?", re.I),
     {"agent": "mail", "action": "read", "label": "Read emails"}),
    (re.compile(r"create\s+(a\s+)?(calendar\s+)?event|add\s+(to\s+)?(my\s+)?calendar|schedule\s+(an?\s+)?event", re.I),
     {"agent": "calendar", "action": "create_event", "label": "Create event"}),
    (re.compile(r"(show|list|what).*(calendar|events|schedule)", re.I),
     {"agent": "calendar", "action": "list_events", "label": "List events"}),
    (re.compile(r"update\s+(the\s+)?event|reschedule", re.I),
     {"agent": "calendar", "action": "update_event", "label": "Update event"}),
    (re.compile(r"read\s+(the\s+)?doc|open\s+doc", re.I),
     {"agent": "docs", "action": "read_doc", "label": "Read document"}),
    (re.compile(r"(write|create|update)\s+(a\s+)?doc", re.I),
     {"agent": "docs", "action": "write_doc", "label": "Write document"}),
    (re.compile(r"list\s+(my\s+)?(drive\s+)?files|show\s+drive", re.I),
     {"agent": "docs", "action": "list_files", "label": "List files"}),
    (re.compile(r"send\s+(a\s+)?(slack|message\s+on\s+slack)", re.I),
     {"agent": "slack", "action": "send_message", "label": "Send Slack message"}),
    (re.compile(r"(read|show|check)\s+(slack|messages)", re.I),
     {"agent": "slack", "action": "read_messages", "label": "Read Slack messages"}),
    (re.compile(r"(read|open)\s+(the\s+)?notion", re.I),
     {"agent": "notion", "action": "read_page", "label": "Read Notion page"}),
    (re.compile(r"(write|create|update)\s+(a\s+)?notion", re.I),
     {"agent": "notion", "action": "write_page", "label": "Write Notion page"}),
    (re.compile(r"schedule\s+(a\s+)?meeting|set\s+up\s+(a\s+)?call|(create|book)\s+(a\s+)?(zoom|meet)", re.I),
     {"agent": "meeting", "action": "schedule", "label": "Schedule meeting"}),
    (re.compile(r"read\s+(the\s+)?file", re.I),
     {"agent": "file", "action": "read", "label": "Read file"}),
    (re.compile(r"write\s+(to\s+)?(the\s+)?file|save\s+file", re.I),
     {"agent": "file", "action": "write", "label": "Write file"}),
    (re.compile(r"list\s+(the\s+)?dir|show\s+files", re.I),
     {"agent": "file", "action": "list_dir", "label": "List directory"}),
    (re.compile(r"create\s+(a\s+)?(google\s+)?form", re.I),
     {"agent": "forms", "action": "create", "label": "Create form"}),
    (re.compile(r"(get|show|read)\s+(form\s+)?responses", re.I),
     {"agent": "forms", "action": "get_responses", "label": "Get form responses"}),
    (re.compile(r"(search|find|look\s+for|summarize)", re.I),
     {"agent": "search", "action": "search_all", "label": "Search all sources"}),
]

# Slash commands
COMMANDS: dict[str, str] = {
    "/schedule": "schedule_and_notify",
    "/email": None,  # single-step
    "/summarize": "summarize_and_share",
    "/inbox": None,
    "/calendar": None,
    "/meet": "schedule_and_notify",
    "/briefing": "daily_briefing",
    "/prepare": "prepare_meeting",
}

COMMAND_SINGLES: dict[str, dict] = {
    "/email": {"agent": "mail", "action": "send", "label": "Send email"},
    "/inbox": {"agent": "mail", "action": "read", "label": "Read inbox"},
    "/calendar": {"agent": "calendar", "action": "list_events", "label": "List events"},
}


def _build_steps(sub_key: str) -> list[dict]:
    """Build a plan from a sub-step template, adding step numbers."""
    template = SUB_STEPS.get(sub_key, [])
    return [{"step": i + 1, **s} for i, s in enumerate(template)]


def generate_plan(user_input: str) -> list[dict]:
    """Convert user query into ordered execution steps with dependencies."""
    stripped = user_input.strip()

    # 1. Slash commands
    if stripped.startswith("/"):
        cmd_key = stripped.split()[0].lower()
        if cmd_key in COMMANDS:
            sub_key = COMMANDS[cmd_key]
            if sub_key:
                return _build_steps(sub_key)
            elif cmd_key in COMMAND_SINGLES:
                s = COMMAND_SINGLES[cmd_key]
                return [{"step": 1, "depends_on": [], **s}]

    # 2. Composite workflows (multi-step decomposition)
    for pattern, sub_key in COMPOSITE_TRIGGERS:
        if pattern.search(user_input):
            return _build_steps(sub_key)

    # 3. Detect "X and Y" / "X then Y" patterns for dynamic multi-step
    and_parts = re.split(r"\s+(?:and|then|also|after\s+that)\s+", user_input, flags=re.I)
    if len(and_parts) > 1:
        plan = []
        for i, part in enumerate(and_parts):
            for pattern, step_def in SINGLE_INTENTS:
                if pattern.search(part):
                    dep = [i - 1] if i > 0 else []
                    plan.append({"step": len(plan) + 1, "depends_on": dep, **step_def})
                    break
        if plan:
            return plan

    # 4. Single intents
    plan = []
    seen = set()
    for pattern, step_def in SINGLE_INTENTS:
        if pattern.search(user_input):
            key = (step_def["agent"], step_def["action"])
            if key not in seen:
                seen.add(key)
                plan.append({"step": len(plan) + 1, "depends_on": [], **step_def})
    return plan
