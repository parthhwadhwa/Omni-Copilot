import os

_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")


def _load_env():
    if not os.path.exists(_ENV_FILE):
        return
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if val and key not in os.environ:
                os.environ[key] = val


_load_env()

EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")


def _derive_sender_name(email_user: str) -> str:
    """Turn parthwadhwa15@gmail.com → 'Parth Wadhwa'."""
    if not email_user:
        return ""
    local = email_user.split("@")[0]
    # Strip trailing digits, split on separators, title-case
    import re
    local = re.sub(r"\d+$", "", local)
    parts = re.split(r"[._\-+]", local)
    return " ".join(p.capitalize() for p in parts if p)


SENDER_NAME = os.environ.get("SENDER_NAME") or _derive_sender_name(EMAIL_USER)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
ZOOM_ACCOUNT_ID = os.environ.get("ZOOM_ACCOUNT_ID", "")
ZOOM_CLIENT_ID = os.environ.get("ZOOM_CLIENT_ID", "")
ZOOM_CLIENT_SECRET = os.environ.get("ZOOM_CLIENT_SECRET", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
