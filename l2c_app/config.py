from pathlib import Path
import json
import os
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get('L2C_DATA', ROOT / 'data/l2c/raw')).resolve()
STORE = Path(os.environ.get('L2C_STORE', ROOT / 'data/l2c/app')).resolve()
MODELS = Path(os.environ.get('L2C_MODELS', ROOT / 'artifacts/l2c/models')).resolve()
for folder in (STORE, MODELS, STORE / 'runs', STORE / 'cache', STORE / 'imports'):
    folder.mkdir(parents=True, exist_ok=True)

DEFAULTS = {'device': 'auto', 'batch_size': 32, 'dpi': 144, 'canvas_size': 2560,
            'ocr_confidence': 0.25, 'ocr_rotations': True, 'ocr_engine': 'easyocr', 'pairing_assistance': False}

def settings():
    path = STORE / 'settings.json'
    return DEFAULTS | (json.loads(path.read_text('utf-8')) if path.exists() else {})

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
    for attempt in range(12):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 11: raise
            time.sleep(.05 * (attempt + 1))
