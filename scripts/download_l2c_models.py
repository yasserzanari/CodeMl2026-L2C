"""One-time inbound download. Never sends project documents to a service."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from l2c_app.config import MODELS,write_json
import easyocr,torch

if __name__=='__main__':
    reader=easyocr.Reader(['fr','en'],gpu=torch.cuda.is_available(),model_storage_directory=str(MODELS),download_enabled=True)
    manifest={'source':'https://github.com/JaidedAI/EasyOCR','easyocr':easyocr.__version__,
              'models':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in MODELS.glob('*.pth')]}
    write_json(MODELS/'manifest.json',manifest)
    print(json.dumps(manifest,indent=2))
    import rapidocr_onnxruntime,importlib.metadata
    package=Path(rapidocr_onnxruntime.__file__).parent
    write_json(MODELS/'rapid-manifest.json',{
        'source':'https://github.com/RapidAI/RapidOCR',
        'weight_origin':'https://github.com/PaddlePaddle/PaddleOCR',
        'version':importlib.metadata.version('rapidocr-onnxruntime'),
        'models':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                   'bytes':p.stat().st_size} for p in package.rglob('*.onnx')]})
