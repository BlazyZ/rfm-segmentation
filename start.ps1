$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Project environment is missing. Run setup.ps1 first.'
}
& $projectPython scripts/setup_mysql.py
if ($LASTEXITCODE -ne 0) { throw 'MySQL setup failed. Check runtime/mysql-error.log.' }
Write-Host 'Open http://127.0.0.1:5000 in your browser. Keep this window open. Ctrl+C stops the web server.'
& $projectPython -u app.py
