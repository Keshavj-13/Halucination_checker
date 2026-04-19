#!/bin/bash

set -euo pipefail

# Function to kill background processes on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $(jobs -p)
    exit
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

if [ -f "backend/.env" ]; then
    set -a
    source backend/.env
    set +a
fi

get_pid_on_port() {
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -n1 || true
        return
    fi

    if command -v ss >/dev/null 2>&1; then
        ss -ltnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | head -n1 || true
        return
    fi

    echo ""
}

is_our_backend_pid() {
    local pid="$1"
    [ -z "$pid" ] && return 1
    [ ! -r "/proc/${pid}/cmdline" ] && return 1

    local cmd
    cmd=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)

    # Treat only this project's backend process as reclaimable.
    if [[ "$cmd" == *"uvicorn"*"main:app"* ]] || [[ "$cmd" == *"samsa_checker/backend"* ]]; then
        return 0
    fi
    return 1
}

find_free_port() {
    local base="$1"
    local max_tries=50
    local p
    for ((i=0; i<max_tries; i++)); do
        p=$((base + i))
        if [ -z "$(get_pid_on_port "$p")" ]; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

echo "------------------------------------------"
echo "🔍 Hallucination Audit System Startup"
echo "------------------------------------------"

# Start backend
BACKEND_PORT=${BACKEND_PORT:-${BACKEND_PORT_START:-}}
if [ -z "${BACKEND_PORT}" ]; then
    echo "❌ Missing backend port. Set BACKEND_PORT or BACKEND_PORT_START in backend/.env"
    exit 1
fi
FALLBACK_PORT_START=${BACKEND_PORT_FALLBACK_START:-$((BACKEND_PORT + 1))}
EXISTING_PID=$(get_pid_on_port "$BACKEND_PORT")

if [ -n "$EXISTING_PID" ]; then
    if is_our_backend_pid "$EXISTING_PID"; then
        echo "♻️  Port ${BACKEND_PORT} is used by previous backend instance (PID ${EXISTING_PID}). Stopping it..."
        kill "$EXISTING_PID" 2>/dev/null || true
        sleep 1
        STILL_PID=$(get_pid_on_port "$BACKEND_PORT")
        if [ -n "$STILL_PID" ]; then
            echo "⚠️  Port ${BACKEND_PORT} is still busy (PID ${STILL_PID}). Selecting a fallback port..."
            BACKEND_PORT=$(find_free_port "$FALLBACK_PORT_START")
            if [ -z "${BACKEND_PORT:-}" ]; then
                echo "❌ Could not find a free port for backend."
                exit 1
            fi
            echo "➡️  Using backend port ${BACKEND_PORT} instead."
        fi
    else
        echo "⚠️  Port ${BACKEND_PORT} is used by another process (PID ${EXISTING_PID})."
        BACKEND_PORT=$(find_free_port "$FALLBACK_PORT_START")
        if [ -z "${BACKEND_PORT:-}" ]; then
            echo "❌ Could not find a free port for backend."
            exit 1
        fi
        echo "➡️  Using backend port ${BACKEND_PORT} instead."
    fi
fi

echo "🚀 Starting FastAPI backend on http://localhost:${BACKEND_PORT}"
cd backend

# Check for venv or just install requirements
if [ -f "requirements.txt" ]; then
    echo "📦 Checking Python dependencies..."
    pip install -r requirements.txt
fi

uvicorn main:app --host 0.0.0.0 --port "${BACKEND_PORT}" &
BACKEND_PID=$!

# Start frontend
echo "🚀 Starting Vite frontend..."
cd ../frontend

# Check if node_modules exists, if not run npm install
if [ ! -d "node_modules" ]; then
    echo "📦 node_modules not found. Running npm install..."
    npm install
fi

export VITE_API_BASE="http://localhost:${BACKEND_PORT}"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Both services are running!"
echo "   - Backend: http://localhost:${BACKEND_PORT}"
echo "   - Frontend API base: ${VITE_API_BASE}"
echo "   - Frontend: Check terminal output for Vite URL"
echo "Press Ctrl+C to stop both services."
echo "------------------------------------------"

# Wait for all background processes
wait
