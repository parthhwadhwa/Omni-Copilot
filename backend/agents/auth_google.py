import os

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
TOKEN_FILE = os.path.join(BACKEND_DIR, "google_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]


def get_access_token() -> str | None:
    from config import GOOGLE_SERVICE_ACCOUNT_FILE
    creds_file = GOOGLE_SERVICE_ACCOUNT_FILE
    if not creds_file:
        return None
    if not os.path.isabs(creds_file):
        creds_file = os.path.join(BACKEND_DIR, "..", creds_file)
    if not os.path.exists(creds_file):
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if creds and creds.valid:
            return creds.token

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save(creds)
            return creds.token

        flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        _save(creds)
        return creds.token

    except ImportError:
        return None
    except Exception:
        return None


def _save(creds) -> None:
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
