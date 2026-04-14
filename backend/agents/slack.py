import json
import urllib.request
from .base import BaseAgent, load_data, save_data


class SlackAgent(BaseAgent):
    name = "slack"
    description = "Send messages to Slack via Incoming Webhook (free, no paid plan needed)"
    tools = [
        {
            "action": "send_message",
            "description": "Send a message to a Slack channel via webhook",
            "params": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name", "default": "general"},
                    "text": {"type": "string"},
                },
                "required": ["channel", "text"],
            },
        },
        {
            "action": "read_messages",
            "description": "Read locally stored Slack messages",
            "params": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["channel"],
            },
        },
        {
            "action": "status",
            "description": "Check Slack webhook connection status",
            "params": {"type": "object", "properties": {}},
        },
    ]

    def _channels(self) -> dict:
        data = load_data("slack.json")
        return data if isinstance(data, dict) else {}

    def action_send_message(self, channel: str, text: str) -> dict:
        from config import SLACK_WEBHOOK_URL
        ch = channel.lstrip("#")

        webhook_sent = False
        webhook_error = None

        if SLACK_WEBHOOK_URL:
            try:
                payload = json.dumps({
                    "text": text,
                    "username": "Omni Copilot",
                    "icon_emoji": ":robot_face:",
                }).encode("utf-8")
                req = urllib.request.Request(
                    SLACK_WEBHOOK_URL,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=5)
                webhook_sent = True
            except Exception as e:
                webhook_error = str(e)

        # Store locally regardless
        channels = self._channels()
        if ch not in channels:
            channels[ch] = []
        msg = {"user": "me", "text": text, "ts": self._now()}
        channels[ch].append(msg)
        save_data("slack.json", channels)

        return {
            "channel": ch,
            "message_ts": msg["ts"],
            "webhook_sent": webhook_sent,
            "webhook_error": webhook_error,
            "status": "sent" if webhook_sent else "saved_locally",
        }

    def action_read_messages(self, channel: str, limit: int = 10) -> list:
        ch = channel.lstrip("#")
        channels = self._channels()
        messages = channels.get(ch, [])
        return messages[-limit:]

    def action_status(self) -> dict:
        from config import SLACK_WEBHOOK_URL
        connected = bool(SLACK_WEBHOOK_URL)
        return {
            "connected": connected,
            "method": "Incoming Webhook" if connected else "not configured",
            "setup": "Add SLACK_WEBHOOK_URL to .env — get it free from api.slack.com/apps → Incoming Webhooks",
        }
