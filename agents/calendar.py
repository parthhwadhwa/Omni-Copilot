import uuid
from .base import BaseAgent, load_data, save_data


class CalendarAgent(BaseAgent):
    name = "calendar"
    description = "Create, update, and list calendar events"
    tools = [
        {
            "action": "create_event",
            "description": "Create a calendar event (persisted to calendar.json)",
            "params": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime"},
                    "end": {"type": "string", "description": "ISO datetime"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string"},
                },
                "required": ["title", "start"],
            },
        },
        {
            "action": "list_events",
            "description": "List upcoming events from calendar.json",
            "params": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
        {
            "action": "update_event",
            "description": "Update an existing event in calendar.json",
            "params": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["event_id"],
            },
        },
        {
            "action": "delete_event",
            "description": "Delete an event from calendar.json",
            "params": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                },
                "required": ["event_id"],
            },
        },
    ]

    def action_create_event(self, title: str, start: str, end: str = None,
                            attendees: list = None, location: str = None) -> dict:
        events = load_data("calendar.json")
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        meet_link = f"https://meet.omni.local/{uuid.uuid4().hex[:10]}"
        new_event = {
            "event_id": event_id,
            "title": title,
            "start": start,
            "end": end or start,
            "attendees": attendees or [],
            "location": location or meet_link,
            "link": meet_link,
            "recurring": False,
            "created_at": self._now(),
        }
        events.append(new_event)
        save_data("calendar.json", events)
        return {**new_event, "status": "created"}

    def action_list_events(self, date: str = None, limit: int = 10) -> list:
        events = load_data("calendar.json")
        if date:
            events = [e for e in events if e.get("start", "").startswith(date)]
        events.sort(key=lambda e: e.get("start", ""))
        return [
            {"event_id": e["event_id"], "title": e["title"], "start": e["start"],
             "end": e.get("end", ""), "attendees": e.get("attendees", []),
             "location": e.get("location", ""), "link": e.get("link", "")}
            for e in events[:limit]
        ]

    def action_update_event(self, event_id: str, **updates) -> dict:
        events = load_data("calendar.json")
        for e in events:
            if e["event_id"] == event_id:
                e.update(updates)
                e["updated_at"] = self._now()
                save_data("calendar.json", events)
                return {"event_id": event_id, "updated_fields": list(updates.keys()), "status": "updated"}
        return {"event_id": event_id, "status": "not_found"}

    def action_delete_event(self, event_id: str) -> dict:
        events = load_data("calendar.json")
        before = len(events)
        events = [e for e in events if e["event_id"] != event_id]
        save_data("calendar.json", events)
        return {"event_id": event_id, "status": "deleted" if len(events) < before else "not_found"}
