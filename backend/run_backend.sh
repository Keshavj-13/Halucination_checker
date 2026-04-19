#!/bin/bash

set -euo pipefail

if [ -f ".env" ]; then
    set -a
    source .env
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

    if [[ "$cmd" == *"uvicorn"*"main:app"* ]] || [[ "$cmd" == *"samsa_checker/backend"* ]]; then
        return 0
    fi
    return 1
}

find_free_port() {
    local base="$1"
    local tries=50
    local p
    for ((i=0; i<tries; i++)); do
        p=$((base + i))
        if [ -z "$(get_pid_on_port "$p")" ]; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

CPU_COUNT=$(python - <<'PY'
import os
print(os.cpu_count() or 4)
PY
)
CPU_WORKERS=${CPU_WORKERS:-$((CPU_COUNT>1?CPU_COUNT-1:1))}
MAX_CLAIMS_IN_FLIGHT=${MAX_CLAIMS_IN_FLIGHT:-$((CPU_WORKERS*3))}
SCRAPE_CONCURRENCY=${SCRAPE_CONCURRENCY:-$((CPU_WORKERS*2))}

PORT=${PORT:-${BACKEND_PORT:-${BACKEND_PORT_START:-}}}
if [ -z "${PORT}" ]; then
    echo "❌ Missing backend port. Set PORT or BACKEND_PORT or BACKEND_PORT_START in backend/.env"
    exit 1
fi
FALLBACK_PORT_START=${BACKEND_PORT_FALLBACK_START:-$((PORT + 1))}
PID=$(get_pid_on_port "$PORT")

if [ -n "$PID" ]; then
    if is_our_backend_pid "$PID"; then
        echo "♻️  Port ${PORT} occupied by previous backend instance (PID ${PID}). Stopping it..."
        kill "$PID" 2>/dev/null || true
        sleep 1
        STILL=$(get_pid_on_port "$PORT")
        if [ -n "$STILL" ]; then
            echo "⚠️  Port ${PORT} still busy after stop attempt (PID ${STILL}). Choosing new port..."
            PORT=$(find_free_port "$FALLBACK_PORT_START")
            if [ -z "${PORT:-}" ]; then
                echo "❌ Could not find free port for backend."
                exit 1
            fi
            echo "➡️  Using port ${PORT}."
        fi
    else
        echo "⚠️  Port ${PORT} occupied by another process (PID ${PID})."
        PORT=$(find_free_port "$FALLBACK_PORT_START")
        if [ -z "${PORT:-}" ]; then
            echo "❌ Could not find free port for backend."
            exit 1
        fi
        echo "➡️  Using port ${PORT}."
    fi
fi

echo "🚀 Starting backend at http://127.0.0.1:${PORT}"
echo "   CPU_WORKERS=${CPU_WORKERS} MAX_CLAIMS_IN_FLIGHT=${MAX_CLAIMS_IN_FLIGHT} SCRAPE_CONCURRENCY=${SCRAPE_CONCURRENCY}"

export CPU_WORKERS MAX_CLAIMS_IN_FLIGHT SCRAPE_CONCURRENCY VOTER_CPU_WORKERS OLLAMA_NUM_GPU OLLAMA_NUM_THREAD EMBEDDING_BATCH_SIZE EMBEDDING_MAX_IN_FLIGHT
exec uvicorn main:app --host 127.0.0.1 --port "${PORT}"
