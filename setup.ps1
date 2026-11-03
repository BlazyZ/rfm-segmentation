$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += (& py -0p 2>$null | ForEach-Object {
            if ($_ -match '3\.12') {
                if ($_ -match '(?:\s)([A-Z]:\\.+python.exe)\s*$') { $Matches[1] }
            }
        })
    }
    $uvPythonRoot = Join-Path $env:APPDATA 'uv\python'
    if (Test-Path -LiteralPath $uvPythonRoot) {
        $candidates += Get-ChildItem -LiteralPath $uvPythonRoot -Directory -Filter 'cpython-3.12*' | ForEach-Object { Join-Path $_.FullName 'python.exe' }
    }
    $selectedPython = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $selectedPython) { throw 'Python 3.12 not found. Install Python 3.12 (python.org), then run setup.ps1 again.' }
    & $selectedPython -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed.' }
}
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $projectPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Get-ChildItem -LiteralPath runtime -Directory -Filter 'mysql-*-winx64' -ErrorAction SilentlyContinue)) {
    & $projectPython scripts/fetch_assets.py
    if ($LASTEXITCODE -ne 0) { throw 'MySQL download failed.' }
}
if (-not (Test-Path -LiteralPath 'rfm\static\vendor\echarts.min.js')) {
    throw 'ECharts asset missing. Run python scripts/fetch_assets.py.'
}
& $projectPython scripts/setup_mysql.py
if ($LASTEXITCODE -ne 0) { throw 'MySQL setup failed.' }
Write-Host 'Setup completed. Double-click start.bat to start the system.'
