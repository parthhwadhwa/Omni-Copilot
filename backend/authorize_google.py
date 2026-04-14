#!/usr/bin/env python3
"""Run once to authorize Google Drive, Calendar, and Forms access."""

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(BACKEND_DIR, "..")
sys.path.insert(0, BACKEND_DIR)

env_file = os.path.join(ROOT_DIR, ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

CREDS_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
if CREDS_FILE and not os.path.isabs(CREDS_FILE):
    CREDS_FILE = os.path.join(ROOT_DIR, CREDS_FILE)

TOKEN_FILE = os.path.join(BACKEND_DIR, "google_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]

if not CREDS_FILE or not os.path.exists(CREDS_FILE):
    print(f"ERROR: credentials file not found: {CREDS_FILE!r}")
    sys.exit(1)

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
except ImportError:
    print("ERROR: run:  pip install google-auth-oauthlib google-auth-httplib2")
    sys.exit(1)

creds = None
if os.path.exists(TOKEN_FILE):
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

if creds and creds.valid:
    print("Already authorized:", creds.token[:20], "...")
    sys.exit(0)

if creds and creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print("Token refreshed.")
    sys.exit(0)

print("Opening browser for Google authorization (Drive + Calendar + Forms)...")
flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
creds = flow.run_local_server(port=0, open_browser=True)

with open(TOKEN_FILE, "w") as f:
    f.write(creds.to_json())

print(f"Authorization successful. Token saved to {TOKEN_FILE}")
