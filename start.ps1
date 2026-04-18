# Set execution policy for this session
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force

# Function to kill background jobs on exit
function Cleanup {
    Write-Host ""
    Write-Host "🛑 Shutting down services..."
    Get-Job | Stop-Job
    Get-Job | Remove-Job
    exit
}

# Trap Ctrl+C
$Host.UI.RawUI.WindowTitle = "Hallucination Audit System"

Write-Host "------------------------------------------"
Write-Host "🔍 Hallucination Audit System Startup"
Write-Host "------------------------------------------"

# Start backend
Write-Host "🚀 Starting FastAPI backend on http://localhost:8000"
Set-Location backend

# Check for venv or just install requirements
if (Test-Path "requirements.txt") {
    Write-Host "📦 Checking Python dependencies..."
    py -m pip install -r requirements.txt
}

# Start uvicorn in background
Start-Job -ScriptBlock {
    py -m uvicorn main:app --host 0.0.0.0 --port 8000
} | Out-Null

# Start frontend
Write-Host "🚀 Starting Vite frontend..."
Set-Location ../frontend

# Check if node_modules exists, if not run npm install
if (-not (Test-Path "node_modules")) {
    Write-Host "📦 node_modules not found. Running npm install..."
    cmd.exe /c "npm install"
}

# Start npm run dev in background
Start-Job -ScriptBlock {
    cmd.exe /c "npm run dev"
} | Out-Null

Write-Host ""
Write-Host "✅ Both services are running!"
Write-Host "   - Backend: http://localhost:8000"
Write-Host "   - Frontend: Check terminal output for Vite URL"
Write-Host "Press Ctrl+C to stop both services."
Write-Host "------------------------------------------"

# Wait for Ctrl+C
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Cleanup
}