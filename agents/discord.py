import json
import urllib.request
from .base import BaseAgent, load_data, save_data


class DiscordAgent(BaseAgent):
    name = "discord"
    description = "Send messages to Discord via free Webhook (no bot token needed)"
    tools = [
        {
            "action": "send_message",
            "description": "Send a message to a Discord channel via webhook",
            "params": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Message text"},
                    "username": {"type": "string", "description": "Display name override (optional)"},
                },
                "required": ["content"],
            },
        },
        {
            "action": "status",
            "description": "Check Discord webhook connection status",
            "params": {"type": "object", "properties": {}},
        },
    ]

    def action_send_message(self, content: str, username: str = "Omni Copilot") -> dict:
        from config import DISCORD_WEBHOOK_URL

        webhook_sent = False
        webhook_error = None

        if DISCORD_WEBHOOK_URL:
            try:
                payload = json.dumps({
                    "content": content,
                    "username": username,
                }).encode("utf-8")
                req = urllib.request.Request(
                    DISCORD_WEBHOOK_URL,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "DiscordBot (OmniCopilot, 1.0)",
                    },
                )
                urllib.request.urlopen(req, timeout=5)
                webhook_sent = True
            except Exception as e:
                webhook_error = str(e)
        else:
            webhook_error = "DISCORD_WEBHOOK_URL not set in .env"

        # Store locally
        messages = load_data("discord.json") if self._history_file_exists() else []
        msg = {"content": content, "username": username, "ts": self._now()}
        messages.append(msg)
        save_data("discord.json", messages)

        return {
            "content": content,
            "webhook_sent": webhook_sent,
            "webhook_error": webhook_error,
            "status": "sent" if webhook_sent else "not_configured",
            "setup": "" if webhook_sent else "Add DISCORD_WEBHOOK_URL to .env — free from Discord channel settings → Integrations → Webhooks",
        }

    def action_status(self) -> dict:
        from config import DISCORD_WEBHOOK_URL
        connected = bool(DISCORD_WEBHOOK_URL)
        return {
            "connected": connected,
            "method": "Webhook" if connected else "not configured",
            "setup": "Add DISCORD_WEBHOOK_URL to .env — free from Discord channel settings → Integrations → Webhooks",
        }

    def _history_file_exists(self) -> bool:
        import os
        from .base import DATA_DIR
        return os.path.exists(os.path.join(DATA_DIR, "discord.json"))
