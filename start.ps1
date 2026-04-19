# Set execution policy for this session
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force

# Ensure we're in the script's directory
Set-Location $PSScriptRoot

$rootDir = $PSScriptRoot
$pythonExe = "C:\Users\HP\AppData\Local\Programs\Python\Python311\python.exe"
$backendHost = "127.0.0.1"
$backendPort = 8000
$backendUrl = "http://${backendHost}:${backendPort}/health"
$appUrl = "http://${backendHost}:${backendPort}"
$logDir = Join-Path $rootDir ".run-logs"
$backendOutLog = Join-Path $logDir "backend.out.log"
$backendErrLog = Join-Path $logDir "backend.err.log"

$script:backendProcess = $null

function Stop-TrackedProcess {
    param (
        [System.Diagnostics.Process]$Process
    )

    if ($null -eq $Process) {
        return
    }

    try {
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {
        # Ignore cleanup errors.
    }
}

function Show-LogTail {
    param (
        [string[]]$Paths
    )

    foreach ($path in $Paths) {
        if (-not (Test-Path $path)) {
            continue
        }

        Write-Host ""
        Write-Host "Recent log output from $path"
        Get-Content $path -Tail 20 | ForEach-Object { Write-Host $_ }
    }
}

function Wait-ForHttp {
    param (
        [string]$Url,
        [int]$TimeoutSeconds = 20
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    return $false
}

function Test-FrontendServed {
    param (
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        $contentType = ""
        if ($response.Headers.ContainsKey("Content-Type")) {
            $contentType = $response.Headers["Content-Type"]
        }

        return $response.StatusCode -eq 200 -and (
            $contentType -like "text/html*" -or
            $response.Content -match "(?i)<html|<!doctype html"
        )
    } catch {
        return $false
    }
}

function Get-PortOwnerSummary {
    param (
        [int]$Port
    )

    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    $ownerIds = @()
    if ($null -ne $connections) {
        $ownerIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
    }

    if ($ownerIds.Count -eq 0) {
        $netstatLines = @(netstat -ano -p tcp | Select-String ":$Port\s+.*LISTENING")
        foreach ($line in $netstatLines) {
            $parts = @($line.ToString() -split "\s+" | Where-Object { $_ })
            if ($parts.Count -ge 5) {
                $ownerIds += [int]$parts[4]
            }
        }

        $ownerIds = @($ownerIds | Select-Object -Unique)
    }

    $owners = @()
    foreach ($ownerId in $ownerIds) {
        $processName = "unknown"
        try {
            $process = Get-Process -Id $ownerId -ErrorAction Stop
            $processName = $process.ProcessName
        } catch {
            # The process may have exited between the TCP lookup and process lookup.
        }

        $owners += [PSCustomObject]@{
            ProcessId = $ownerId
            ProcessName = $processName
        }
    }

    return $owners
}

function Cleanup {
    Write-Host ""
    Write-Host "Shutting down services..."
    Stop-TrackedProcess $script:backendProcess
}

$Host.UI.RawUI.WindowTitle = "Hallucination Audit System"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

Write-Host "------------------------------------------"
Write-Host "Hallucination Audit System Startup"
Write-Host "------------------------------------------"

Write-Host "Starting FastAPI backend on $appUrl"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Python was not found at $pythonExe"
    exit 1
}

Push-Location (Join-Path $rootDir "backend")
try {
    if (Test-Path "requirements.txt") {
        Write-Host "Checking Python dependencies..."
        & $pythonExe -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Python dependency installation failed."
            exit $LASTEXITCODE
        }
    }
} finally {
    Pop-Location
}

Write-Host "Building frontend for backend-hosted local app..."
Push-Location (Join-Path $rootDir "frontend")
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "node_modules not found. Running npm install..."
        cmd.exe /c "npm install"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "npm install failed."
            exit $LASTEXITCODE
        }
    }

    cmd.exe /c "npm run build"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Frontend build failed."
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

$usingExistingBackend = $false

if ((Wait-ForHttp -Url $backendUrl -TimeoutSeconds 2) -and (Test-FrontendServed -Url $appUrl)) {
    $usingExistingBackend = $true
    Write-Host "A compatible website is already running at $appUrl. Reusing it."
} else {
    $portOwners = @(Get-PortOwnerSummary -Port $backendPort)
    if ($portOwners.Count -gt 0) {
        Write-Host "Port $backendPort is already in use, but it is not serving the built website."
        Write-Host "Stop the process using the port, then run this script again:"
        foreach ($owner in $portOwners) {
            Write-Host "  PID $($owner.ProcessId) ($($owner.ProcessName))"
        }
        Write-Host "Example: taskkill /PID <pid> /F"
        exit 1
    }

    $script:backendProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", $backendHost, "--port", "$backendPort") `
        -WorkingDirectory $rootDir `
        -RedirectStandardOutput $backendOutLog `
        -RedirectStandardError $backendErrLog `
        -PassThru

    if (-not (Wait-ForHttp -Url $backendUrl -TimeoutSeconds 20)) {
        Write-Host "Backend failed to start."
        Show-LogTail @($backendOutLog, $backendErrLog)
        Cleanup
        exit 1
    }

    Start-Sleep -Milliseconds 250
    if ($script:backendProcess.HasExited) {
        Write-Host "Backend exited while starting."
        Show-LogTail @($backendOutLog, $backendErrLog)
        Cleanup
        exit 1
    }
}

Write-Host ""
Write-Host "The local app is running."
Write-Host "  Backend: $backendUrl"
Write-Host "  Website: $appUrl"
Write-Host "  Backend logs: $backendOutLog and $backendErrLog"
if ($usingExistingBackend) {
    Write-Host "Press Ctrl+C to close this launcher. The existing backend will keep running."
} else {
    Write-Host "Press Ctrl+C to stop the backend."
}
Write-Host "------------------------------------------"

try {
    while ($true) {
        if ($null -ne $script:backendProcess -and $script:backendProcess.HasExited) {
            Write-Host "Backend exited unexpectedly."
            Show-LogTail @($backendOutLog, $backendErrLog)
            break
        }

        Start-Sleep -Seconds 1
    }
} finally {
    Cleanup
}
