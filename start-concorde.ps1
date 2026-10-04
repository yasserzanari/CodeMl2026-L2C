$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$concordeLocal = Join-Path $PSScriptRoot 'local-settings.ps1'
if (Test-Path -LiteralPath $concordeLocal) { . $concordeLocal }
$concordePython = if ($env:CONCORDE_PYTHON) { $env:CONCORDE_PYTHON } else { Join-Path $PSScriptRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $concordePython)) { throw 'Lancez install-concorde.ps1 avant de démarrer.' }
$concordePort = if ($env:CONCORDE_PORT) { [int]$env:CONCORDE_PORT } else { 8766 }
if ($concordePort -lt 1024 -or $concordePort -gt 65535) { throw 'CONCORDE_PORT doit être compris entre 1024 et 65535.' }
try {
    $concordeResponse = Invoke-RestMethod "http://127.0.0.1:$concordePort/api/overview" -TimeoutSec 2
    if ($concordeResponse.application -eq 'concorde') { Start-Process "http://127.0.0.1:$concordePort"; exit }
} catch { }
$concordeLogs = Join-Path $PSScriptRoot 'data\l2c\app'
New-Item -ItemType Directory -Path $concordeLogs -Force | Out-Null
$concordeProcess = Start-Process -FilePath $concordePython -ArgumentList '-m','uvicorn','l2c_app.server:app','--host','127.0.0.1','--port',"$concordePort" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $concordeLogs 'server.log') -RedirectStandardError (Join-Path $concordeLogs 'server-errors.log')
$concordeProcess.Id | Set-Content (Join-Path $concordeLogs 'server.pid')
for ($concordeAttempt=0; $concordeAttempt -lt 30; $concordeAttempt++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-RestMethod "http://127.0.0.1:$concordePort/api/overview" -TimeoutSec 2 | Out-Null; Start-Process "http://127.0.0.1:$concordePort"; exit } catch { }
    if ($concordeProcess.HasExited) { throw "Le serveur a quitté. Consultez $concordeLogs\server-errors.log" }
}
throw "Le service met du temps à démarrer. Consultez $concordeLogs\server-errors.log"
