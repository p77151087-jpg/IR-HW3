$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskRecord = Join-Path $taskRoot 'reports\server\process.json'
if (-not (Test-Path -LiteralPath $taskRecord)) { Write-Host 'No recorded HW3 background server.'; exit 0 }
$taskServer = Get-Content -LiteralPath $taskRecord -Raw | ConvertFrom-Json
$taskRunning = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$taskServer.pid)" -ErrorAction SilentlyContinue
if (-not $taskRunning) { Write-Host 'The recorded HW3 server has already stopped.'; exit 0 }
$taskExpectedApp = Join-Path $taskRoot 'app.py'
if ($taskRunning.Name -ne 'python.exe' -or $taskRunning.CommandLine -notmatch [regex]::Escape($taskExpectedApp) -or
    $taskRunning.CommandLine -notmatch 'streamlit\s+run') {
    throw 'The recorded process does not match this HW3 server. No process was stopped.'
}
Stop-Process -Id ([int]$taskServer.pid)
Write-Host 'HW3 background server stopped. HW2 was not touched.'
