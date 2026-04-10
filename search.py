"""
Unified search across all demo data sources: emails, calendar, docs.
"""

from __future__ import annotations
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_json(name: str) -> list[dict]:
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def search_all_sources(query: str) -> dict:
    """Search emails, calendar, and docs for matching content."""
    q = query.lower()
    results = {"emails": [], "calendar": [], "docs": []}

    for email in _load_json("emails.json"):
        searchable = f"{email.get('subject', '')} {email.get('body', '')} {email.get('from', '')}".lower()
        if q in searchable:
            results["emails"].append({
                "id": email["id"],
                "from": email["from"],
                "subject": email["subject"],
                "snippet": email["body"][:100],
                "date": email["date"],
            })

    for event in _load_json("calendar.json"):
        searchable = f"{event.get('title', '')} {' '.join(event.get('attendees', []))}".lower()
        if q in searchable:
            results["calendar"].append({
                "event_id": event["event_id"],
                "title": event["title"],
                "start": event["start"],
                "attendees": event["attendees"],
            })

    for doc in _load_json("docs.json"):
        searchable = f"{doc.get('title', '')} {doc.get('content', '')}".lower()
        if q in searchable:
            results["docs"].append({
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "snippet": doc["content"][:120],
                "last_modified": doc["last_modified"],
            })

    total = sum(len(v) for v in results.values())
    return {"query": query, "total_results": total, **results}
