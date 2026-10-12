#!/bin/bash
# Start backend and frontend

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting backend..."
cd "$ROOT_DIR/backend"
"$ROOT_DIR/venv/bin/uvicorn" server:app --reload --port 8001 &
BACKEND_PID=$!

echo "Starting frontend..."
cd "$ROOT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo "Backend:  http://localhost:8001"
echo "Frontend: http://localhost:5173"
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
