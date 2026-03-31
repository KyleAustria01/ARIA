# ARIA AI Interview System — Windows Setup Script
# This script will install Python 3.11, Node.js, set up the backend venv, and install all dependencies.
# Run this script in PowerShell from the project root.

Write-Host "[1/8] Checking for Python 3.11..." -ForegroundColor Cyan
$python = Get-Command python -ErrorAction SilentlyContinue
$pythonVersion = if ($python) { python --version 2>&1 } else { "" }
if (-not $pythonVersion -or ($pythonVersion -notmatch "3\.11")) {
    Write-Host "Python 3.11 not found. Installing with winget..." -ForegroundColor Yellow
    winget install -e --id Python.Python.3.11 --silent
    Write-Host "Waiting for Python to finish installing..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
} else {
    Write-Host "Python 3.11 is already installed." -ForegroundColor Green
}

Write-Host "[2/8] Refreshing environment variables for new Python..." -ForegroundColor Cyan
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "[3/8] Creating Python virtual environment in backend/venv..." -ForegroundColor Cyan
python -m venv backend/venv

Write-Host "[4/8] Activating virtual environment..." -ForegroundColor Cyan
. backend/venv/Scripts/Activate.ps1

Write-Host "[5/8] Installing backend dependencies..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

Write-Host "[6/8] Checking for Node.js..." -ForegroundColor Cyan
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "Node.js not found. Installing with winget..." -ForegroundColor Yellow
    winget install -e --id OpenJS.NodeJS --silent
    Write-Host "Waiting for Node.js to finish installing..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
} else {
    Write-Host "Node.js is already installed." -ForegroundColor Green
}

Write-Host "[7/8] Installing frontend dependencies..." -ForegroundColor Cyan
Push-Location frontend
npm install
Pop-Location

Write-Host "[8/8] Setup complete!" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Magenta
Write-Host "1. Activate the Python virtual environment:" -ForegroundColor Magenta
Write-Host "   . backend/venv/Scripts/Activate.ps1" -ForegroundColor White
Write-Host "2. Run the backend server:" -ForegroundColor Magenta
Write-Host "   uvicorn main:app --reload --app-dir backend" -ForegroundColor White
Write-Host "3. In a new terminal, run the frontend:" -ForegroundColor Magenta
Write-Host "   cd frontend" -ForegroundColor White
Write-Host "   npm run dev" -ForegroundColor White
Write-Host "" -ForegroundColor Green
Write-Host "Setup is finished. You are ready to run ARIA!" -ForegroundColor Green
