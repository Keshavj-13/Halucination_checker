@echo off
echo ------------------------------------------
echo 🔍 Hallucination Audit System Startup
echo ------------------------------------------

REM Start backend
echo 🚀 Starting FastAPI backend on http://localhost:8000
cd backend

REM Check for requirements.txt and install
if exist requirements.txt (
    echo 📦 Checking Python dependencies...
    python -m pip install -r requirements.txt
)

REM Start uvicorn in background
start /B python -m uvicorn main:app --host 0.0.0.0 --port 8000

REM Start frontend
echo 🚀 Starting Vite frontend...
cd ../frontend

REM Check if node_modules exists
if not exist node_modules (
    echo 📦 node_modules not found. Running npm install...
    call npm install
)

REM Start npm run dev in background
start /B cmd /C "npm run dev"

echo.
echo ✅ Both services are running!
echo    - Backend: http://localhost:8000
echo    - Frontend: Check terminal output for Vite URL
echo Press Ctrl+C in the respective windows to stop services.
echo ------------------------------------------
pause