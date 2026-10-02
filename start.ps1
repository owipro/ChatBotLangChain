$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$stateDir = Join-Path $projectRoot ".streamlit"
$pidFile = Join-Path $stateDir "chatbot.pid"
$stopFile = Join-Path $stateDir "chatbot.stop"

if (-not (Test-Path $venvPython)) {
    python -m venv .venv
}

if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}

Remove-Item $stopFile -ErrorAction SilentlyContinue

& $venvPython -m pip install -r requirements.txt

if (Test-Path $pidFile) {
    $existingPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($existingPid) {
        $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existingProcess) {
            Write-Host "Chatbot is already running with PID $existingPid. Open http://localhost:8501."
            return
        }
    }
}

$process = Start-Process -PassThru -FilePath $venvPython -WorkingDirectory $projectRoot -ArgumentList @(
    "-m",
    "streamlit",
    "run",
    "chatbot.py",
    "--server.headless",
    "true",
    "--browser.gatherUsageStats",
    "false"
)

Set-Content -Path $pidFile -Value $process.Id
Write-Host "Streamlit is starting in a separate process. Open http://localhost:8501 in your browser."
