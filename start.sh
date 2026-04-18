#!/bin/bash

# Function to kill background processes on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $(jobs -p)
    exit
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

echo "------------------------------------------"
echo "🔍 Hallucination Audit System Startup"
echo "------------------------------------------"

# Start backend
echo "🚀 Starting FastAPI backend on http://localhost:8000"
cd backend

# Check for venv or just install requirements
if [ -f "requirements.txt" ]; then
    echo "📦 Checking Python dependencies..."
    pip install -r requirements.txt
fi

uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "🚀 Starting Vite frontend..."
cd ../frontend

# Check if node_modules exists, if not run npm install
if [ ! -d "node_modules" ]; then
    echo "📦 node_modules not found. Running npm install..."
    npm install
fi

npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Both services are running!"
echo "   - Backend: http://localhost:8000"
echo "   - Frontend: Check terminal output for Vite URL"
echo "Press Ctrl+C to stop both services."
echo "------------------------------------------"

# Wait for all background processes
wait
