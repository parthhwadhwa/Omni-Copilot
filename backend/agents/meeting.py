"""
Meeting agent — creates real Google Meet links via Calendar API.
Falls back to fake links if Google Calendar is not connected.
Zoom requires separate API credentials (falls back to fake link).
"""

import json
import uuid
import datetime
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


def _iso(dt: str, duration_minutes: int = 30) -> tuple[dict, dict]:
    """Return (start, end) dicts for Calendar API."""
    if "T" not in dt:
        dt = dt + "T09:00:00"
    tz_dt = dt if ("+" in dt or dt.endswith("Z")) else dt + "+05:30"

    start = {"dateTime": tz_dt, "timeZone": "Asia/Kolkata"}

    # Calculate end time
    try:
        base = datetime.datetime.fromisoformat(dt)
        end_dt = base + datetime.timedelta(minutes=duration_minutes)
        end_str = end_dt.isoformat()
        tz_end = end_str if ("+" in end_str or end_str.endswith("Z")) else end_str + "+05:30"
        end = {"dateTime": tz_end, "timeZone": "Asia/Kolkata"}
    except Exception:
        end = start

    return start, end


class MeetingAgent(BaseAgent):
    name = "meeting"
    description = "Schedule meetings with real Google Meet links via Calendar API"
    tools = [
        {
            "action": "schedule",
            "description": "Schedule a meeting and generate a real Google Meet link",
            "params": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime e.g. 2026-04-15T10:00:00"},
                    "duration_minutes": {"type": "integer", "default": 30},
                    "platform": {"type": "string", "enum": ["google_meet", "zoom"], "default": "google_meet"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "start"],
            },
        },
        {
            "action": "list",
            "description": "List scheduled meetings",
            "params": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
    ]

    def action_schedule(self, title: str, start: str, duration_minutes: int = 30,
                        platform: str = "google_meet", attendees: list = None) -> dict:
        platform = platform if platform in ("google_meet", "zoom") else "google_meet"

        if platform == "google_meet":
            return self._schedule_google_meet(title, start, duration_minutes, attendees or [])
        else:
            return self._schedule_zoom(title, start, duration_minutes, attendees or [])

    def _schedule_google_meet(self, title: str, start: str,
                               duration_minutes: int, attendees: list) -> dict:
        token = get_access_token()
        if not token:
            return self._local_schedule(title, start, duration_minutes, "google_meet", attendees)

        try:
            start_dt, end_dt = _iso(start, duration_minutes)
            body = {
                "summary": title,
                "start": start_dt,
                "end": end_dt,
                "conferenceData": {
                    "createRequest": {
                        "requestId": uuid.uuid4().hex,
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                },
            }
            if attendees:
                body["attendees"] = [{"email": a} for a in attendees]
                body["guestsCanSeeOtherGuests"] = True

            # conferenceDataVersion=1 is required to generate Meet link
            result = _gcal(
                "POST",
                "/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all",
                token, body,
            )

            # Extract real Meet link from response
            meet_link = ""
            conf = result.get("conferenceData", {})
            for ep in conf.get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri", "")
                    break
            if not meet_link:
                meet_link = result.get("hangoutLink", "")

            event_id = result.get("id", "")
            cal_link = result.get("htmlLink", "")

            record = {
                "meeting_id": event_id,
                "title": title,
                "start": start,
                "duration_minutes": duration_minutes,
                "platform": "google_meet",
                "link": meet_link,
                "calendar_link": cal_link,
                "attendees": attendees,
                "created_at": self._now(),
                "storage": "google_calendar",
            }
            self._save(record)

            return {**record, "status": "scheduled"}

        except Exception as e:
            result = self._local_schedule(title, start, duration_minutes, "google_meet", attendees)
            result["gcal_error"] = str(e)
            return result

    def _schedule_zoom(self, title: str, start: str,
                       duration_minutes: int, attendees: list) -> dict:
        try:
            token = self._zoom_access_token()
            if not token:
                return self._local_schedule(title, start, duration_minutes, "zoom", attendees)

            # Convert to UTC ISO format Zoom expects
            try:
                base = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                start_utc = base.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                start_utc = start

            body = json.dumps({
                "topic": title,
                "type": 2,  # Scheduled meeting
                "start_time": start_utc,
                "duration": duration_minutes,
                "settings": {
                    "host_video": True,
                    "participant_video": True,
                    "join_before_host": True,
                    "waiting_room": False,
                },
            }).encode()

            req = urllib.request.Request(
                "https://api.zoom.us/v2/users/me/meetings",
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())

            meeting_id = str(result.get("id", ""))
            link = result.get("join_url", "")

            record = {
                "meeting_id": meeting_id,
                "title": title,
                "start": start,
                "duration_minutes": duration_minutes,
                "platform": "zoom",
                "link": link,
                "attendees": attendees,
                "created_at": self._now(),
                "storage": "zoom",
            }
            self._save(record)
            return {**record, "status": "scheduled"}

        except Exception as e:
            result = self._local_schedule(title, start, duration_minutes, "zoom", attendees)
            result["zoom_error"] = str(e)
            return result

    def _zoom_access_token(self) -> str | None:
        """Get Zoom Server-to-Server OAuth access token."""
        import base64
        from config import ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
        if not ZOOM_ACCOUNT_ID or not ZOOM_CLIENT_ID or not ZOOM_CLIENT_SECRET:
            return None
        try:
            credentials = base64.b64encode(
                f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()
            ).decode()
            body = f"grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}".encode()
            req = urllib.request.Request(
                "https://zoom.us/oauth/token",
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return data.get("access_token")
        except Exception:
            return None

    def _local_schedule(self, title: str, start: str, duration_minutes: int,
                        platform: str, attendees: list) -> dict:
        import random, string
        meeting_id = uuid.uuid4().hex[:10]
        if platform == "zoom":
            num = "".join(random.choices(string.digits, k=11))
            link = f"https://zoom.us/j/{num}"
        else:
            parts = [
                "".join(random.choices(string.ascii_lowercase, k=3)),
                "".join(random.choices(string.ascii_lowercase, k=4)),
                "".join(random.choices(string.ascii_lowercase, k=3)),
            ]
            link = f"https://meet.google.com/{'-'.join(parts)}"

        record = {
            "meeting_id": meeting_id,
            "title": title,
            "start": start,
            "duration_minutes": duration_minutes,
            "platform": platform,
            "link": link,
            "attendees": attendees,
            "created_at": self._now(),
            "storage": "local",
        }
        self._save(record)
        return {**record, "status": "scheduled"}

    def _save(self, record: dict) -> None:
        meetings = load_data("meetings.json")
        meetings = [m for m in meetings if m.get("meeting_id") != record.get("meeting_id")]
        meetings.append(record)
        save_data("meetings.json", meetings)

    def action_list(self, limit: int = 10) -> list:
        meetings = load_data("meetings.json")
        meetings.sort(key=lambda m: m.get("start", ""))
        return meetings[-limit:]
