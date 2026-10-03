$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { py -3.11 -m venv .venv }
$concordePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $concordePython -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'Installation PyTorch CUDA échouée.' }
& $concordePython -m pip install -r l2c_app/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances échouée.' }
& $concordePython -m pip install rapidocr-onnxruntime==1.4.4 onnxruntime-gpu==1.23.2 --no-deps
if ($LASTEXITCODE -ne 0) { throw 'Installation RapidOCR CUDA échouée.' }
& $concordePython scripts/download_l2c_models.py
if ($LASTEXITCODE -ne 0) { throw 'Téléchargement des modèles échoué.' }
Write-Host 'Installation terminée. Lancez .\start-concorde.ps1'
