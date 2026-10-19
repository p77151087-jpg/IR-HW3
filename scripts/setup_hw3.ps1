$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
Set-Location -LiteralPath $taskRoot
New-Item -ItemType Directory -Path (Join-Path $taskRoot 'tmp') -Force | Out-Null
if (-not (Test-Path -LiteralPath $taskPython)) {
    $runtimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $runtimePython) {
        & $runtimePython -m venv (Join-Path $taskRoot '.venv')
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $taskRoot '.venv')
    } else {
        & python -m venv (Join-Path $taskRoot '.venv')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the HW3 environment (Python >= 3.12 required).' }
}
$taskRequirements = Join-Path $taskRoot 'requirements-lock.txt'
if (-not (Test-Path -LiteralPath $taskRequirements)) { $taskRequirements = Join-Path $taskRoot 'requirements.txt' }
& $taskPython -m pip install --disable-pip-version-check -r $taskRequirements
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $taskPython -B -X utf8 -m ir_hw3.cli verify
if ($LASTEXITCODE -ne 0) { throw 'Corpus verification failed.' }
Write-Host 'Ready. Double-click start_hw3.cmd and open http://127.0.0.1:8503.'
