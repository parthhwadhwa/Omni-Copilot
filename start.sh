#!/bin/bash
# Start both backend and frontend dev servers

trap 'kill 0' EXIT

echo "Starting Omni Copilot..."
echo ""

# Backend
cd "$(dirname "$0")"
./venv/bin/uvicorn server:app --reload --port 8000 &
echo "[backend]  http://localhost:8000"

# Frontend
cd frontend
npm run dev -- --port 5173 &
echo "[frontend] http://localhost:5173"

echo ""
echo "Ready."

wait
