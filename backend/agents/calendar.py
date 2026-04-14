"""
Calendar agent — Google Calendar API v3 with local fallback.
Uses shared OAuth token from auth_google.py.
"""

import json
import uuid
import urllib.request
from .base import BaseAgent, load_data, save_data
from .auth_google import get_access_token

GCAL_API = "https://www.googleapis.com/calendar/v3"


def _gcal(method: str, path: str, token: str, body: dict = None) -> dict:
    url = f"{GCAL_API}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}


class CalendarAgent(BaseAgent):
    name = "calendar"
    description = "Create, update, list, and delete Google Calendar events"
    tools = [
        {
            "action": "create_event",
            "description": "Create a calendar event",
            "params": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime e.g. 2026-04-13T10:00:00"},
                    "end": {"type": "string", "description": "ISO datetime"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "start"],
            },
        },
        {
            "action": "list_events",
            "description": "List upcoming calendar events",
            "params": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD filter"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
        {
            "action": "update_event",
            "description": "Update an existing calendar event",
            "params": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["event_id"],
            },
        },
        {
            "action": "delete_event",
            "description": "Delete a calendar event",
            "params": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                },
                "required": ["event_id"],
            },
        },
        {
            "action": "status",
            "description": "Check Google Calendar connection status",
            "params": {"type": "object", "properties": {}},
        },
    ]

    # ── Status ────────────────────────────────────────────────────────────────

    def action_status(self) -> dict:
        token = get_access_token()
        if not token:
            return {"connected": False, "method": "Google Calendar",
                    "setup": "Run authorize_drive.py to authorize Google access"}
        try:
            # calendar.events scope covers listing events but not calendar metadata
            import datetime
            now = datetime.datetime.utcnow().isoformat() + "Z"
            _gcal("GET", f"/calendars/primary/events?maxResults=1&timeMin={now}", token)
            return {"connected": True, "method": "Google Calendar (primary)"}
        except Exception as e:
            return {"connected": False, "method": "Google Calendar", "error": str(e)}

    # ── Create ────────────────────────────────────────────────────────────────

    def action_create_event(self, title: str, start: str, end: str = None,
                            attendees: list = None, location: str = None,
                            description: str = None) -> dict:
        token = get_access_token()
        if not token:
            return self._local_create(title, start, end, attendees, location)

        # Build ISO datetime with timezone
        def _iso(dt: str) -> dict:
            if "T" in dt:
                return {"dateTime": dt if "+" in dt or dt.endswith("Z") else dt + "+05:30",
                        "timeZone": "Asia/Kolkata"}
            return {"date": dt}

        body = {
            "summary": title,
            "start": _iso(start),
            "end": _iso(end or start),
        }
        if location:
            body["location"] = location
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
            body["guestsCanSeeOtherGuests"] = True

        try:
            result = _gcal("POST", "/calendars/primary/events?sendUpdates=all", token, body)
            event_id = result.get("id", "")
            link = result.get("htmlLink", "")

            # Save locally too
            self._local_save({
                "event_id": event_id, "title": title, "start": start,
                "end": end or start, "attendees": attendees or [],
                "location": location or "", "link": link,
                "created_at": self._now(),
            })

            return {
                "event_id": event_id,
                "title": title,
                "start": start,
                "end": end or start,
                "attendees": attendees or [],
                "location": location or "",
                "link": link,
                "status": "created",
                "storage": "google_calendar",
            }
        except Exception as e:
            result = self._local_create(title, start, end, attendees, location)
            result["gcal_error"] = str(e)
            return result

    # ── List ──────────────────────────────────────────────────────────────────

    def action_list_events(self, date: str = None, limit: int = 10) -> list:
        token = get_access_token()
        if not token:
            return self._local_list(date, limit)

        try:
            import datetime
            now = datetime.datetime.utcnow().isoformat() + "Z"
            params = f"calendarId=primary&maxResults={limit}&singleEvents=true&orderBy=startTime&timeMin={now}"
            if date:
                time_min = f"{date}T00:00:00Z"
                time_max = f"{date}T23:59:59Z"
                params = f"calendarId=primary&maxResults={limit}&singleEvents=true&orderBy=startTime&timeMin={time_min}&timeMax={time_max}"

            result = _gcal("GET", f"/calendars/primary/events?{params}", token)
            events = []
            for e in result.get("items", []):
                start = e.get("start", {})
                end = e.get("end", {})
                events.append({
                    "event_id": e.get("id", ""),
                    "title": e.get("summary", "(no title)"),
                    "start": start.get("dateTime", start.get("date", "")),
                    "end": end.get("dateTime", end.get("date", "")),
                    "location": e.get("location", ""),
                    "link": e.get("htmlLink", ""),
                    "attendees": [a.get("email", "") for a in e.get("attendees", [])],
                })
            return events
        except Exception:
            return self._local_list(date, limit)

    # ── Update ────────────────────────────────────────────────────────────────

    def action_update_event(self, event_id: str, title: str = None,
                            start: str = None, end: str = None,
                            location: str = None) -> dict:
        token = get_access_token()
        if not token:
            return self._local_update(event_id, title=title, start=start,
                                      end=end, location=location)
        try:
            existing = _gcal("GET", f"/calendars/primary/events/{event_id}", token)
            if title:
                existing["summary"] = title
            if location:
                existing["location"] = location

            def _iso(dt: str) -> dict:
                if "T" in dt:
                    return {"dateTime": dt if "+" in dt or dt.endswith("Z") else dt + "+05:30",
                            "timeZone": "Asia/Kolkata"}
                return {"date": dt}

            if start:
                existing["start"] = _iso(start)
            if end:
                existing["end"] = _iso(end)

            result = _gcal("PUT", f"/calendars/primary/events/{event_id}", token, existing)
            return {"event_id": event_id, "status": "updated", "link": result.get("htmlLink", "")}
        except Exception as e:
            return {"event_id": event_id, "status": "error", "error": str(e)}

    # ── Delete ────────────────────────────────────────────────────────────────

    def action_delete_event(self, event_id: str) -> dict:
        token = get_access_token()
        if not token:
            return self._local_delete(event_id)
        try:
            _gcal("DELETE", f"/calendars/primary/events/{event_id}", token)
            self._local_delete(event_id)
            return {"event_id": event_id, "status": "deleted"}
        except Exception as e:
            return {"event_id": event_id, "status": "error", "error": str(e)}

    # ── Local fallbacks ───────────────────────────────────────────────────────

    def _local_create(self, title, start, end=None, attendees=None, location=None) -> dict:
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        meet_link = f"https://meet.google.com/{uuid.uuid4().hex[:10]}"
        record = {
            "event_id": event_id, "title": title,
            "start": start, "end": end or start,
            "attendees": attendees or [], "location": location or meet_link,
            "link": meet_link, "created_at": self._now(),
        }
        self._local_save(record)
        return {**record, "status": "created", "storage": "local"}

    def _local_save(self, record: dict) -> None:
        events = load_data("calendar.json")
        events = [e for e in events if e.get("event_id") != record.get("event_id")]
        events.append(record)
        save_data("calendar.json", events)

    def _local_list(self, date: str = None, limit: int = 10) -> list:
        events = load_data("calendar.json")
        if date:
            events = [e for e in events if e.get("start", "").startswith(date)]
        events.sort(key=lambda e: e.get("start", ""))
        return [{"event_id": e["event_id"], "title": e["title"], "start": e["start"],
                 "end": e.get("end", ""), "attendees": e.get("attendees", []),
                 "location": e.get("location", ""), "link": e.get("link", "")}
                for e in events[:limit]]

    def _local_update(self, event_id: str, **updates) -> dict:
        events = load_data("calendar.json")
        for e in events:
            if e["event_id"] == event_id:
                e.update({k: v for k, v in updates.items() if v is not None})
                e["updated_at"] = self._now()
                save_data("calendar.json", events)
                return {"event_id": event_id, "status": "updated"}
        return {"event_id": event_id, "status": "not_found"}

    def _local_delete(self, event_id: str) -> dict:
        events = load_data("calendar.json")
        before = len(events)
        events = [e for e in events if e["event_id"] != event_id]
        save_data("calendar.json", events)
        return {"event_id": event_id,
                "status": "deleted" if len(events) < before else "not_found"}
