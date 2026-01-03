# Talk With Zeno - Complete Startup Script
# This script sets up and starts both backend and frontend servers

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Talk With Zeno - Starting Application" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

# Check Python installation
Write-Host "Checking Python installation..." -ForegroundColor Yellow
$pythonCheck = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCheck) {
    $pythonVersion = python --version 2>&1
    Write-Host "  [OK] Python found: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Python not found. Please install Python 3.8+ from https://www.python.org/" -ForegroundColor Red
    exit 1
}

# Check Node.js installation
Write-Host ""
Write-Host "Checking Node.js installation..." -ForegroundColor Yellow
$nodeCheck = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCheck) {
    $nodeVersion = node --version 2>&1
    Write-Host "  [OK] Node.js found: $nodeVersion" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Node.js not found. Please install Node.js from https://nodejs.org/" -ForegroundColor Red
    exit 1
}

# Setup Backend
Write-Host ""
Write-Host "=== Setting up Backend ===" -ForegroundColor Green

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "  [OK] Virtual environment already exists" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Install backend dependencies
Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
pip install -q -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Failed to install backend dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Backend dependencies installed" -ForegroundColor Green

# Check for .env.local file
if (-not (Test-Path ".\.env.local")) {
    Write-Host ""
    Write-Host "[WARNING] .env.local file not found!" -ForegroundColor Yellow
    Write-Host "  Create a .env.local file with the following variables:" -ForegroundColor Yellow
    Write-Host "    GEMINI_API_KEY=your_gemini_api_key" -ForegroundColor Gray
    Write-Host "    GROQ_API_KEY=your_groq_api_key" -ForegroundColor Gray
    Write-Host "    GOOGLE_APPLICATION_CREDENTIALS=path/to/your/google-credentials.json" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Continuing anyway, but some features may not work..." -ForegroundColor Yellow
    Write-Host ""
}

# Setup Frontend
Write-Host "=== Setting up Frontend ===" -ForegroundColor Green

# Install frontend dependencies if node_modules doesn't exist
if (-not (Test-Path ".\node_modules")) {
    Write-Host "Installing frontend dependencies (this may take a minute)..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to install frontend dependencies" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Frontend dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  [OK] Frontend dependencies already installed" -ForegroundColor Green
}

# Start Backend Server
Write-Host ""
Write-Host "=== Starting Backend Server ===" -ForegroundColor Green
$backendScript = @"
cd '$scriptDir'
Write-Host '=== Backend Server ===' -ForegroundColor Green
Write-Host 'Running on http://localhost:5000' -ForegroundColor Cyan
Write-Host 'Press Ctrl+C to stop' -ForegroundColor Gray
Write-Host ''
& '.\venv\Scripts\Activate.ps1'
python backend/run.py
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendScript

# Wait a moment for backend to start
Start-Sleep -Seconds 3

# Start Frontend Server
Write-Host "=== Starting Frontend Server ===" -ForegroundColor Green
$frontendScript = @"
cd '$scriptDir'
Write-Host '=== Frontend Server ===' -ForegroundColor Green
Write-Host 'Running on http://localhost:5173' -ForegroundColor Cyan
Write-Host 'Press Ctrl+C to stop' -ForegroundColor Gray
Write-Host ''
npm run dev
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendScript

# Wait for servers to start
Write-Host ""
Write-Host "Waiting for servers to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

# Check server status
Write-Host ""
Write-Host "=== Checking Server Status ===" -ForegroundColor Cyan

$backendRunning = $false
$frontendRunning = $false

# Check backend
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/api/health" -Method GET -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    $backendRunning = $true
    $content = $response.Content | ConvertFrom-Json
    Write-Host "[OK] Backend is running on http://localhost:5000" -ForegroundColor Green
    Write-Host "  Status: $($content.status)" -ForegroundColor White
} catch {
    Write-Host "[WARNING] Backend not responding yet (may still be starting)" -ForegroundColor Yellow
    Write-Host "  Check the backend PowerShell window for errors" -ForegroundColor Gray
}

# Check frontend
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5173" -Method GET -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    $frontendRunning = $true
    Write-Host "[OK] Frontend is running on http://localhost:5173" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Frontend not responding yet (may still be starting)" -ForegroundColor Yellow
    Write-Host "  Check the frontend PowerShell window for errors" -ForegroundColor Gray
}

# Final message
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Application Startup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($backendRunning -and $frontendRunning) {
    Write-Host "[OK] Both servers are running successfully!" -ForegroundColor Green
} elseif ($backendRunning) {
    Write-Host "[WARNING] Backend is running, but frontend is still starting..." -ForegroundColor Yellow
} elseif ($frontendRunning) {
    Write-Host "[WARNING] Frontend is running, but backend is still starting..." -ForegroundColor Yellow
} else {
    Write-Host "[WARNING] Servers are starting but not ready yet. Please wait a few more seconds." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Open your browser and go to:" -ForegroundColor Cyan
Write-Host "  http://localhost:5173" -ForegroundColor White
Write-Host ""

Write-Host "Both servers are running in separate PowerShell windows." -ForegroundColor Gray
Write-Host "Close those windows to stop the servers." -ForegroundColor Gray
Write-Host ""

Write-Host "Press any key to exit this script (servers will continue running)..." -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
