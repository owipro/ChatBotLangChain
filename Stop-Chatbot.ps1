$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stateDir = Join-Path $projectRoot ".streamlit"
$stopFile = Join-Path $stateDir "chatbot.stop"
$pidFile = Join-Path $stateDir "chatbot.pid"

if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}

Set-Content -Path $stopFile -Value ([DateTime]::UtcNow.ToString("o"))

if (Test-Path $pidFile) {
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}

Write-Host "Stop request written. The chatbot will exit on its own within a second or two."
