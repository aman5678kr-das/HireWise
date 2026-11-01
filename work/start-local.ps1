$ErrorActionPreference = "Stop"
$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$nodeDir = Join-Path $PSScriptRoot "runtimes\node\node-v22.23.4-win-x64"
$node = Join-Path $nodeDir "node.exe"
$npm = Join-Path $nodeDir "npm.cmd"
$python = Join-Path $project "backend\.venv\Scripts\python.exe"
$dbFile = Join-Path $PSScriptRoot "hirewise-local.sqlite"
$logs = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force $logs | Out-Null
if (!(Test-Path $node) -or !(Test-Path $npm)) { throw "Portable Node.js is missing under work/runtimes. Install Node.js 20+ and run npm install in frontend." }
if (!(Test-Path $python)) { throw "Backend environment is not installed. Run backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt." }
$env:Path = $nodeDir + ";" + $env:Path
$env:VITE_API_URL = "http://localhost:8000"
$env:DATABASE_URL = "sqlite:///" + ($dbFile -replace "\\", "/")
$env:JWT_SECRET = "local-development-only-change-before-deployment"
$env:UPLOAD_DIR = Join-Path $PSScriptRoot "uploads"
$env:CORS_ORIGINS = "http://localhost:5173"
New-Item -ItemType Directory -Force $env:UPLOAD_DIR | Out-Null
$listener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if (!$listener) {
    Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory (Join-Path $project "backend") -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "backend.log") -RedirectStandardError (Join-Path $logs "backend-error.log")
}
$listener = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue
if (!$listener) {
    Start-Process -FilePath $node -ArgumentList @("node_modules/vite/bin/vite.js", "--host", "0.0.0.0") -WorkingDirectory (Join-Path $project "frontend") -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "frontend.log") -RedirectStandardError (Join-Path $logs "frontend-error.log")
}
$healthy = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 1000
    try {
        $apiStatus = Invoke-RestMethod "http://localhost:8000/api/health" -TimeoutSec 2
        $webStatus = Invoke-WebRequest "http://localhost:5173/" -TimeoutSec 2
        if ($apiStatus.status -eq "ok" -and $webStatus.StatusCode -eq 200) { $healthy = $true; break }
    } catch {}
}
if (!$healthy) {
    Get-Content (Join-Path $logs "backend-error.log") -Tail 40 -ErrorAction SilentlyContinue
    Get-Content (Join-Path $logs "frontend-error.log") -Tail 40 -ErrorAction SilentlyContinue
    throw "Local services did not become ready. See work/logs."
}
Write-Host "Hirewise frontend: http://localhost:5173"
Write-Host "Hirewise backend:  http://localhost:8000 (SQLite local developer database)"
