"""
Persistent memory layer. Stores past queries, extracted entities, and key context.
Enables resolving references like "same time tomorrow" or "email Alice again".
"""

from __future__ import annotations
import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")


def _load() -> list[dict]:
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE) as f:
        return json.load(f)


def _save(entries: list[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MEMORY_FILE, "w") as f:
        json.dump(entries, f, indent=2, default=str)


def save_memory(query: str, entities: dict, results: list[dict]):
    """Save a query + extracted context to memory."""
    entries = _load()
    entries.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "query": query,
        "entities": entities,
        "result_summary": _summarize_results(results),
    })
    # Keep last 50 entries
    _save(entries[-50:])


def retrieve_memory(query: str = "", limit: int = 5) -> list[dict]:
    """Retrieve recent memory entries, optionally filtered by keyword."""
    entries = _load()
    if query:
        q = query.lower()
        entries = [e for e in entries if q in e.get("query", "").lower()
                   or q in json.dumps(e.get("entities", {})).lower()]
    return entries[-limit:]


def get_last_context() -> dict:
    """Get the most recent memory entry for context resolution."""
    entries = _load()
    return entries[-1] if entries else {}


def resolve_references(user_input: str) -> dict:
    """
    Resolve contextual references using memory.
    "same time" → reuse last event time
    "again" → reuse last action params
    "tomorrow" with context → shift date
    """
    hints = {}
    lower = user_input.lower()
    last = get_last_context()

    if not last:
        return hints

    entities = last.get("entities", {})

    if "same time" in lower or "same slot" in lower:
        if "start" in entities:
            hints["start"] = entities["start"]
        if "time" in entities:
            hints["start"] = entities["time"]

    if "again" in lower:
        hints["reuse_last"] = True
        hints.update(entities)

    if "same people" in lower or "same attendees" in lower:
        if "attendees" in entities:
            hints["attendees"] = entities["attendees"]

    return hints


def extract_entities(user_input: str, results: list[dict]) -> dict:
    """Extract key entities from query + results for future reference."""
    import re
    entities = {}

    # Extract emails
    emails = re.findall(r"\S+@\S+\.\S+", user_input)
    if emails:
        entities["emails"] = emails

    # Extract times
    if m := re.search(r"(\d{1,2}:\d{2})", user_input):
        entities["time"] = m.group(1)

    # Extract quoted strings
    quotes = re.findall(r'"([^"]+)"', user_input)
    if quotes:
        entities["quoted"] = quotes

    # Extract from results
    for r in results:
        if not r.get("ok"):
            continue
        res = r.get("result", {})
        if isinstance(res, dict):
            for key in ("event_id", "meeting_id", "doc_id", "message_id", "form_id"):
                if key in res:
                    entities[key] = res[key]
            if "start" in res:
                entities["start"] = res["start"]
            if "title" in res:
                entities["last_title"] = res["title"]
            if "attendees" in res:
                entities["attendees"] = res["attendees"]
            if "link" in res:
                entities["last_link"] = res["link"]

    return entities


def _summarize_results(results: list[dict]) -> str:
    """One-line summary of results for memory."""
    parts = []
    for r in results:
        agent = r.get("_agent", "?")
        action = r.get("_action", "?")
        ok = "ok" if r.get("ok") else "fail"
        parts.append(f"{agent}.{action}={ok}")
    return ", ".join(parts)
