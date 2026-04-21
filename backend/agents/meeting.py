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


def build_ics(title: str, start: str, duration_minutes: int,
              link: str, attendees: list, organizer: str = "") -> str:
    """Build RFC 5545 iCalendar content. Gmail detects this for 'Add to Calendar'."""
    try:
        if "T" in start:
            base = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
        else:
            base = datetime.datetime.fromisoformat(f"{start}T09:00:00")
    except Exception:
        base = datetime.datetime.now()

    if base.tzinfo is None:
        base = base.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))

    end = base + datetime.timedelta(minutes=duration_minutes)
    utc = datetime.timezone.utc
    dtstart = base.astimezone(utc).strftime("%Y%m%dT%H%M%SZ")
    dtend = end.astimezone(utc).strftime("%Y%m%dT%H%M%SZ")
    dtstamp = datetime.datetime.now(utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"{uuid.uuid4().hex}@omnicopilot"

    def _escape(s: str) -> str:
        return (s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OmniCopilot//Meeting Invite//EN",
        "METHOD:REQUEST",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{_escape(title)}",
        f"DESCRIPTION:Join the meeting: {_escape(link)}",
        f"LOCATION:{_escape(link)}",
    ]
    if organizer:
        lines.append(f"ORGANIZER;CN={_escape(organizer)}:mailto:{organizer}")
    for a in attendees or []:
        lines.append(f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{a}")
    lines.extend([
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "END:VEVENT",
        "END:VCALENDAR",
    ])
    return "\r\n".join(lines)


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
                    "replace_existing_id": {"type": "string", "description": "If set, delete this meeting_id before scheduling (used to resolve conflicts)"},
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
                        platform: str = "google_meet", attendees: list = None,
                        replace_existing_id: str = "") -> dict:
        platform = platform if platform in ("google_meet", "zoom") else "google_meet"
        # Normalise attendees — LLM sometimes passes a comma-separated string
        if isinstance(attendees, str):
            attendees = [a.strip() for a in attendees.split(",") if a.strip()]

        if replace_existing_id:
            self._delete_by_id(replace_existing_id)

        conflict = self._check_conflict(start, duration_minutes)
        if conflict:
            return {
                "conflict": True,
                "existing": {
                    "meeting_id": conflict.get("meeting_id", ""),
                    "title": conflict.get("title", ""),
                    "start": conflict.get("start", ""),
                    "duration_minutes": conflict.get("duration_minutes", 30),
                    "platform": conflict.get("platform", ""),
                },
                "proposed": {
                    "title": title,
                    "start": start,
                    "duration_minutes": duration_minutes,
                    "platform": platform,
                    "attendees": attendees or [],
                },
                "message": f"You already have \"{conflict.get('title', '')}\" scheduled at that time.",
            }

        if platform == "google_meet":
            return self._schedule_google_meet(title, start, duration_minutes, attendees or [])
        else:
            return self._schedule_zoom(title, start, duration_minutes, attendees or [])

    def _delete_by_id(self, meeting_id: str) -> None:
        if not meeting_id:
            return
        meetings = load_data("meetings.json")
        meetings = [m for m in meetings if m.get("meeting_id") != meeting_id]
        save_data("meetings.json", meetings)

    def _check_conflict(self, start: str, duration_minutes: int) -> dict | None:
        """Return the conflicting meeting dict if the new slot overlaps an existing one."""
        try:
            new_start = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
            if new_start.tzinfo is None:
                new_start = new_start.replace(
                    tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))
                )
        except Exception:
            return None

        new_end = new_start + datetime.timedelta(minutes=duration_minutes)
        meetings = load_data("meetings.json")

        for m in meetings:
            try:
                ms = m.get("start", "")
                if not ms:
                    continue
                ex_start = datetime.datetime.fromisoformat(ms.replace("Z", "+00:00"))
                if ex_start.tzinfo is None:
                    ex_start = ex_start.replace(
                        tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))
                    )
                ex_end = ex_start + datetime.timedelta(
                    minutes=int(m.get("duration_minutes", 30))
                )
                # Overlap if intervals intersect
                if new_start < ex_end and new_end > ex_start:
                    return m
            except Exception:
                continue
        return None

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

            from config import EMAIL_USER
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
                "ics": build_ics(title, start, duration_minutes, meet_link, attendees, EMAIL_USER),
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

            from config import EMAIL_USER
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
                "ics": build_ics(title, start, duration_minutes, link, attendees, EMAIL_USER),
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
        meeting_id = uuid.uuid4().hex[:10]
        setup_hint = ("Connect Google Calendar to generate real Meet links"
                      if platform == "google_meet"
                      else "Add ZOOM_* credentials in .env to generate real Zoom links")
        record = {
            "meeting_id": meeting_id,
            "title": title,
            "start": start,
            "duration_minutes": duration_minutes,
            "platform": platform,
            "link": "",
            "attendees": attendees,
            "created_at": self._now(),
            "storage": "local",
            "setup": setup_hint,
        }
        self._save(record)
        return {**record, "status": "saved_locally"}

    def _save(self, record: dict) -> None:
        meetings = load_data("meetings.json")
        meetings = [m for m in meetings if m.get("meeting_id") != record.get("meeting_id")]
        meetings.append(record)
        save_data("meetings.json", meetings)

    def action_status(self) -> dict:
        from .auth_google import get_access_token
        from config import ZOOM_CLIENT_ID
        token = get_access_token()
        methods = []
        if token:
            methods.append("Google Meet")
        if ZOOM_CLIENT_ID:
            methods.append("Zoom")
        if methods:
            return {"connected": True, "method": ", ".join(methods)}
        return {"connected": False, "setup": "Add Google OAuth or Zoom credentials to .env"}

    def action_list(self, limit: int = 10) -> list:
        meetings = load_data("meetings.json")
        meetings.sort(key=lambda m: m.get("start", ""))
        return meetings[-limit:]
