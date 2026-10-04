$ErrorActionPreference = 'Stop'
$concordeLocal = Join-Path $PSScriptRoot 'local-settings.ps1'
if (Test-Path -LiteralPath $concordeLocal) { . $concordeLocal }
$concordePort = if ($env:CONCORDE_PORT) { [int]$env:CONCORDE_PORT } else { 8766 }
if ($concordePort -lt 1024 -or $concordePort -gt 65535) { throw 'CONCORDE_PORT doit être compris entre 1024 et 65535.' }
$concordeListeners = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $concordePort -State Listen -ErrorAction SilentlyContinue
foreach ($concordeListener in $concordeListeners) {
    $concordeTarget = Get-CimInstance Win32_Process -Filter "ProcessId = $($concordeListener.OwningProcess)"
    if ($concordeTarget.CommandLine -match 'uvicorn\s+l2c_app\.server:app' -and $concordeTarget.CommandLine -match "--port\s+$concordePort(?:\s|$)") {
        Stop-Process -Id $concordeTarget.ProcessId
        Write-Host 'Concorde arrêté. Les fichiers et le cache sont conservés.'
    } else {
        throw "Le port $concordePort appartient à une autre application ; aucun processus arrêté."
    }
}
