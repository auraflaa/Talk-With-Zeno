# Start Talk With Zeno Locally
# This script starts both backend and frontend servers

Write-Host "`n=== Starting Talk With Zeno Locally ===`n" -ForegroundColor Cyan

# Get local IP address
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" } | Select-Object -First 1).IPAddress

if (-not $localIP) {
    $localIP = "localhost"
}

Write-Host "Local IP: $localIP" -ForegroundColor Yellow
Write-Host "`nStarting servers...`n" -ForegroundColor Green

# Check if .env.local exists
if (-not (Test-Path ".env.local")) {
    Write-Host "Warning: .env.local not found!" -ForegroundColor Yellow
    Write-Host "Please create .env.local from .env.example`n" -ForegroundColor Yellow
}

# Start backend in new window
Write-Host "Starting Backend on http://0.0.0.0:5000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; Write-Host 'Backend Server' -ForegroundColor Cyan; Write-Host 'Local: http://localhost:5000' -ForegroundColor Green; Write-Host 'Network: http://$localIP:5000' -ForegroundColor Yellow; Write-Host ''; python backend/run.py"

# Wait for backend to start
Start-Sleep -Seconds 3

# Start frontend in new window
Write-Host "Starting Frontend on http://0.0.0.0:3000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; Write-Host 'Frontend Server' -ForegroundColor Cyan; Write-Host 'Local: http://localhost:3000' -ForegroundColor Green; Write-Host 'Network: http://$localIP:3000' -ForegroundColor Yellow; Write-Host ''; npm run dev"

# Wait a bit
Start-Sleep -Seconds 2

Write-Host "`n=== Servers Started ===`n" -ForegroundColor Green
Write-Host "Frontend URLs:" -ForegroundColor Cyan
Write-Host "  Local:  http://localhost:3000" -ForegroundColor White
Write-Host "  Network: http://$localIP:3000" -ForegroundColor Yellow
Write-Host "`nBackend URLs:" -ForegroundColor Cyan
Write-Host "  Local:  http://localhost:5000" -ForegroundColor White
Write-Host "  Network: http://$localIP:5000" -ForegroundColor Yellow
Write-Host "`nShare the Network URL with others on your local network!`n" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop servers`n" -ForegroundColor Gray

