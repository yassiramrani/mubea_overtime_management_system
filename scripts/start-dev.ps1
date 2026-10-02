$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'

$pythonCandidates = @(
    (Join-Path $backendRoot '.venv\Scripts\python.exe'),
    (Join-Path $backendRoot 'venv\Scripts\python.exe')
)
$pythonPath = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $pythonPath) {
    $pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
    Write-Host 'Creating backend virtual environment...'
    & py -3.12 -m venv $pythonPath.Replace('\Scripts\python.exe', '')
    & $pythonPath -m pip install -r (Join-Path $backendRoot 'requirements.txt')
}

if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
    Write-Host 'Installing frontend dependencies...'
    Push-Location $frontendRoot
    try { npm ci } finally { Pop-Location }
}

Write-Host 'Applying database migrations...'
& $pythonPath (Join-Path $backendRoot 'manage.py') migrate --noinput

$managePath = Join-Path $backendRoot 'manage.py'
$backendCommand = "& '$pythonPath' '$managePath' runserver 127.0.0.1:8000"
$frontendCommand = "npm run dev -- --host 127.0.0.1 --strictPort"

Start-Process -FilePath 'powershell.exe' `
    -WorkingDirectory $backendRoot `
    -ArgumentList @('-NoProfile', '-NoExit', '-Command', $backendCommand) | Out-Null

Start-Process -FilePath 'powershell.exe' `
    -WorkingDirectory $frontendRoot `
    -ArgumentList @('-NoProfile', '-NoExit', '-Command', $frontendCommand) | Out-Null

Write-Host ''
Write-Host 'Backend:  http://127.0.0.1:8000'
Write-Host 'Frontend: http://127.0.0.1:3000'
Write-Host 'Two terminal windows were opened. Close them to stop the servers.'
