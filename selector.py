"""
Dynamic Agent Selector: chooses the right agent for a task description.
Uses keyword scoring — no hardcoded routing tables.
"""

from __future__ import annotations
from agents import ALL_AGENTS

# Keyword → agent affinity scores
AGENT_KEYWORDS: dict[str, list[str]] = {
    "mail": ["email", "mail", "send", "inbox", "reply", "forward", "draft", "subject", "recipient", "cc", "bcc"],
    "calendar": ["calendar", "event", "schedule", "appointment", "date", "time", "recurring", "reminder", "reschedule"],
    "docs": ["doc", "document", "drive", "write", "read", "file", "google doc", "content", "edit", "draft", "summary", "notes"],
    "slack": ["slack", "channel", "message", "chat", "dm", "thread", "notify", "ping"],
    "notion": ["notion", "page", "wiki", "workspace", "database", "block", "template"],
    "meeting": ["meeting", "zoom", "meet", "call", "video", "conference", "standup", "sync", "huddle"],
    "file": ["file", "code", "read file", "write file", "directory", "folder", "path", "save"],
    "forms": ["form", "survey", "quiz", "response", "question", "feedback", "poll"],
    "search": ["search", "find", "look for", "lookup", "query", "where", "locate"],
}


def select_agent(task_description: str) -> tuple[str, float]:
    """
    Score each agent against the task description.
    Returns (agent_name, confidence) where confidence is 0.0–1.0.
    """
    desc = task_description.lower()
    scores: dict[str, float] = {}

    for agent_name, keywords in AGENT_KEYWORDS.items():
        score = 0.0
        for kw in keywords:
            if kw in desc:
                # Longer keyword matches are worth more
                score += len(kw) / 10.0
        scores[agent_name] = score

    if not scores or max(scores.values()) == 0:
        return ("search", 0.0)  # fallback: search everything

    best = max(scores, key=scores.get)
    max_score = scores[best]

    # Normalize confidence to 0–1
    confidence = min(max_score / 3.0, 1.0)

    return (best, round(confidence, 2))


def select_agent_and_action(task_description: str) -> tuple[str, str, float]:
    """
    Select the best agent AND infer the most likely action.
    Returns (agent_name, action, confidence).
    """
    agent_name, confidence = select_agent(task_description)
    desc = task_description.lower()

    # If it's the search pseudo-agent
    if agent_name == "search":
        return ("search", "search_all", confidence)

    # Get the agent's available actions
    agent_cls = ALL_AGENTS.get(agent_name)
    if not agent_cls:
        return (agent_name, "unknown", confidence)

    agent = agent_cls()
    actions = [t["action"] for t in agent.tools]

    if len(actions) == 1:
        return (agent_name, actions[0], confidence)

    # Score actions by keyword proximity
    ACTION_HINTS = {
        "send": ["send", "email", "notify", "draft", "forward", "reply"],
        "read": ["read", "check", "show", "inbox", "view", "open", "get"],
        "create_event": ["create", "new", "add", "schedule", "book"],
        "list_events": ["list", "show", "what", "upcoming", "today"],
        "update_event": ["update", "change", "modify", "reschedule", "move"],
        "read_doc": ["read", "open", "view", "get"],
        "write_doc": ["write", "create", "draft", "new", "summary", "generate"],
        "list_files": ["list", "show", "files", "drive"],
        "send_message": ["send", "post", "write", "tell", "notify", "ping"],
        "read_messages": ["read", "check", "show", "messages", "history"],
        "read_page": ["read", "open", "view", "get"],
        "write_page": ["write", "create", "new", "update"],
        "schedule": ["schedule", "book", "set up", "create"],
        "write": ["write", "save", "create"],
        "list_dir": ["list", "show", "directory"],
        "create": ["create", "new", "build", "make"],
        "get_responses": ["get", "read", "show", "responses", "results"],
    }

    best_action = actions[0]
    best_score = 0
    for action in actions:
        hints = ACTION_HINTS.get(action, [])
        score = sum(1 for h in hints if h in desc)
        if score > best_score:
            best_score = score
            best_action = action

    return (agent_name, best_action, confidence)
