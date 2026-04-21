# Omni Copilot

A multi-agent AI productivity assistant that connects your tools — Gmail, Google Calendar, Drive, Forms, Meet, Zoom, Slack, Discord, Notion, GitHub, and your local codebase — into a single chat interface.

## Architecture

```
OmniCopilot/
├── backend/          # FastAPI server + agents
│   ├── agents/       # One agent per integration
│   ├── server.py     # API entrypoint
│   ├── orchestrator.py
│   ├── llm.py
│   ├── config.py
│   ├── memory.py
│   ├── search.py
│   └── authorize_google.py
├── frontend/         # React + Vite UI
├── .env              # Your credentials (never committed)
└── .env.example      # Template
```

## Integrations

| Service | Capability |
|---|---|
| Gmail | Read inbox, send emails |
| Google Calendar | Create, list, update, delete events |
| Google Drive | Upload, list, read files |
| Google Forms | Create forms, read responses |
| Google Meet | Real meeting links via Calendar API, invite emails with Join + Add to Calendar buttons |
| Zoom | Real meeting links via Zoom API |
| Slack | Send messages via webhook |
| Discord | Send messages via webhook |
| Notion | List and create pages |
| GitHub | Repos, issues, PRs, commits, code search |
| Code | Read, write, search local code files |

## Setup

### 1. Clone and install

```bash
git clone https://github.com/parthhwadhwa/OmniCopilot.git
cd OmniCopilot

python3 -m venv venv
./venv/bin/pip install -r backend/requirements.txt

cd frontend
npm install
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Fill in `.env` with your credentials (see `.env.example` for all required keys).

### 3. Authorize Google (Drive + Calendar + Forms)

```bash
cd backend
../venv/bin/python authorize_google.py
```

### 4. Run

```bash
# Backend
cd backend
../venv/bin/uvicorn server:app --reload --port 8001

# Frontend (separate terminal)
cd frontend
npm run dev
```

Open http://localhost:5173

## Environment Variables

See `.env.example` for the full list. Key credentials:

- `GROQ_API_KEY` — from console.groq.com
- `EMAIL_USER` / `EMAIL_PASS` — Gmail + App Password
- `GOOGLE_SERVICE_ACCOUNT_FILE` — OAuth2 Desktop app JSON from Google Cloud Console
- `SLACK_WEBHOOK_URL` — from api.slack.com/apps
- `DISCORD_WEBHOOK_URL` — from Discord server settings
- `NOTION_TOKEN` — from notion.so/my-integrations
- `ZOOM_ACCOUNT_ID` / `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET` — from marketplace.zoom.us
- `GITHUB_TOKEN` — Personal access token from github.com/settings/tokens
