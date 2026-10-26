$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
New-Item -ItemType Directory -Path (Join-Path $taskRoot 'tmp') -Force | Out-Null
$env:PYTHONDONTWRITEBYTECODE = '1'
& (Join-Path $taskRoot '.venv\Scripts\python.exe') -B -X utf8 -m pytest -q --basetemp tmp/pytest --junitxml=reports/pytest.xml
exit $LASTEXITCODE
