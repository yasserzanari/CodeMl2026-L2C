$ErrorActionPreference = 'Stop'
$concordeListeners = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
foreach ($concordeListener in $concordeListeners) {
    $concordeTarget = Get-CimInstance Win32_Process -Filter "ProcessId = $($concordeListener.OwningProcess)"
    if ($concordeTarget.CommandLine -match 'uvicorn\s+l2c_app\.server:app' -and $concordeTarget.CommandLine -match '--port\s+8765') {
        Stop-Process -Id $concordeTarget.ProcessId
        Write-Host 'Concorde arrêté. Les fichiers et le cache sont conservés.'
    } else {
        throw 'Le port 8765 appartient à une autre application ; aucun processus arrêté.'
    }
}
