param(
    [ValidateSet('cuda','cpu')][string]$Device = 'cuda',
    [string]$Wheelhouse = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$concordeLocal = Join-Path $PSScriptRoot 'local-settings.ps1'
if (Test-Path -LiteralPath $concordeLocal) { . $concordeLocal }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Création de l’environnement Python 3.11 échouée." }
}
$concordePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$concordeSource = @()
if ($Wheelhouse) {
    $concordeWheels = (Resolve-Path -LiteralPath $Wheelhouse).Path
    $concordeSource = @('--no-index','--find-links',$concordeWheels)
    & $concordePython -m pip install @concordeSource torch==2.11.0 torchvision==0.26.0
} else {
    $concordeIndex = if ($Device -eq 'cpu') { 'https://download.pytorch.org/whl/cpu' } else { 'https://download.pytorch.org/whl/cu128' }
    & $concordePython -m pip install torch==2.11.0 torchvision==0.26.0 --index-url $concordeIndex
}
if ($LASTEXITCODE -ne 0) { throw 'Installation PyTorch échouée.' }
& $concordePython -m pip install @concordeSource -r l2c_app/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances échouée.' }
$concordeRuntime = if ($Device -eq 'cpu') { 'onnxruntime==1.23.2' } else { 'onnxruntime-gpu==1.23.2' }
& $concordePython -m pip install @concordeSource rapidocr-onnxruntime==1.4.4 $concordeRuntime --no-deps
if ($LASTEXITCODE -ne 0) { throw 'Installation RapidOCR échouée.' }
if ($Wheelhouse) {
    $concordeModels = if ($env:L2C_MODELS) { $env:L2C_MODELS } else { Join-Path $PSScriptRoot 'artifacts\l2c\models' }
    foreach ($concordeModel in @('craft_mlt_25k.pth','latin_g2.pth')) {
        if (-not (Test-Path -LiteralPath (Join-Path $concordeModels $concordeModel))) {
            throw "Poids local absent : $concordeModel. Copier les modèles préparés avant l’installation hors ligne."
        }
    }
} else {
    & $concordePython scripts/download_l2c_models.py
    if ($LASTEXITCODE -ne 0) { throw 'Téléchargement des modèles échoué.' }
}
Write-Host 'Installation terminée. Lancez .\start-concorde.ps1. Pour le notebook : installer jupyterlab et ipykernel séparément.'
