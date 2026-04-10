import uuid
import random
import string
from .base import BaseAgent, load_data, save_data


def _generate_link(platform: str, meeting_id: str) -> str:
    """Generate a realistic meeting link based on platform."""
    if platform == "zoom":
        num = "".join(random.choices(string.digits, k=11))
        return f"https://zoom.us/j/{num}"
    if platform == "google_meet":
        parts = [
            "".join(random.choices(string.ascii_lowercase, k=3)),
            "".join(random.choices(string.ascii_lowercase, k=4)),
            "".join(random.choices(string.ascii_lowercase, k=3)),
        ]
        return f"https://meet.google.com/{'-'.join(parts)}"
    # local / fallback
    return f"https://meet.omni.local/{meeting_id}"


class MeetingAgent(BaseAgent):
    name = "meeting"
    description = "Schedule meetings with unique shareable links"
    tools = [
        {
            "action": "schedule",
            "description": "Schedule a meeting, generate unique link, persist to meetings.json",
            "params": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime"},
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

    def action_schedule(
        self, title: str, start: str, duration_minutes: int = 30,
        platform: str = "google_meet", attendees: list = None,
    ) -> dict:
        platform = platform if platform in ("google_meet", "zoom") else "google_meet"
        meeting_id = uuid.uuid4().hex[:10]
        link = _generate_link(platform, meeting_id)

        meetings = load_data("meetings.json")
        new_meeting = {
            "meeting_id": meeting_id,
            "title": title,
            "start": start,
            "duration_minutes": duration_minutes,
            "platform": platform,
            "link": link,
            "attendees": attendees or [],
            "created_at": self._now(),
        }
        meetings.append(new_meeting)
        save_data("meetings.json", meetings)

        return {
            "meeting_id": meeting_id,
            "title": title,
            "start": start,
            "duration_minutes": duration_minutes,
            "platform": platform,
            "link": link,
            "attendees": attendees or [],
            "status": "scheduled",
        }

    def action_list(self, limit: int = 10) -> list:
        meetings = load_data("meetings.json")
        meetings.sort(key=lambda m: m.get("start", ""))
        return meetings[-limit:]
