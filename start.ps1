param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$venvPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $venvPython) { $projectPython = $venvPython }
elseif (Test-Path -LiteralPath $bundledPython) { $projectPython = $bundledPython }
else { $projectPython = 'python' }
& $projectPython -c 'import docx'
if ($LASTEXITCODE -ne 0) { throw 'Missing python-docx. Install requirements.txt in a Python virtual environment.' }
Write-Host "Open http://127.0.0.1:$Port in your browser. Press Ctrl+C to stop."
& $projectPython -m app.server --port $Port
