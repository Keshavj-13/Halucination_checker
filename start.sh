#!/bin/bash

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    echo ""
    echo "Stopping backend..."
    if [ -n "${BACKEND_PID:-}" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    exit
}

trap cleanup SIGINT SIGTERM

echo "------------------------------------------"
echo "Hallucination Audit System Startup"
echo "------------------------------------------"

echo "Starting FastAPI backend on http://127.0.0.1:8000"
cd "$ROOT_DIR/backend"
if [ -f "requirements.txt" ]; then
    echo "Checking Python dependencies..."
    pip install -r requirements.txt
fi

echo "Building frontend for backend-hosted local app..."
cd "$ROOT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    echo "node_modules not found. Running npm install..."
    npm install
fi

npm run build

cd "$ROOT_DIR"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo ""
echo "The local app is running."
echo "  Backend: http://127.0.0.1:8000"
echo "  Website: http://127.0.0.1:8000"
echo "Press Ctrl+C to stop the backend."
echo "------------------------------------------"

wait "$BACKEND_PID"
