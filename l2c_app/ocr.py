"""Offline EasyOCR: CRAFT detection and Latin CRNN recognition on CUDA."""
import threading
import hashlib
import time
import numpy as np
import torch
from .config import MODELS
from .ocr_duplicates import DuplicateIndex

_reader = None
_device = None
LOCK = threading.RLock()

def hardware():
    cuda = torch.cuda.is_available()
    result = {'cuda': cuda, 'device': torch.cuda.get_device_name(0) if cuda else 'CPU',
              'torch': torch.__version__, 'models_ready': all((MODELS / f).exists() for f in ['craft_mlt_25k.pth', 'latin_g2.pth']),
              'loaded_device': _device}
    if cuda:
        free, total = torch.cuda.mem_get_info()
        result.update(vram_total=total, vram_free=free, vram_used=total-free,
                      allocated=torch.cuda.memory_allocated(), reserved=torch.cuda.memory_reserved())
    return result

def reader_for(device='auto'):
    global _reader, _device
    cuda_available = torch.cuda.is_available()
    if device == 'cuda' and not cuda_available:
        raise RuntimeError('CUDA indisponible. Aucune inférence OCR CPU ne sera lancée.')
    if device not in ('auto', 'cuda', 'cpu'):
        raise ValueError('Périphérique OCR inconnu : choisir auto, cuda ou cpu.')
    desired = 'cuda' if device in ('auto', 'cuda') and cuda_available else 'cpu'
    with LOCK:
        if _reader is None or _device != desired:
            import easyocr
            _reader = None
            if desired == 'cuda':
                torch.cuda.empty_cache()
                torch.backends.cudnn.benchmark = True
                torch.set_float32_matmul_precision('high')
            torch.set_num_threads(min(8, max(1, __import__('os').cpu_count() or 4)))
            reader = easyocr.Reader(['fr', 'en'], gpu=desired == 'cuda',
                 model_storage_directory=str(MODELS), download_enabled=False, verbose=False)
            for name in ('detector','recognizer'):
                network=getattr(reader,name,None)
                try: device=next(network.parameters()).device.type
                except (AttributeError,StopIteration,TypeError): device='unknown'
                if device != desired:
                    raise RuntimeError(f'EasyOCR {name} n’est pas chargé sur {desired}.')
            _reader = reader
            _device = desired
        return _reader

def recognize(image, config):
    if config.get('ocr_engine')=='rapidocr':
        from .rapid import recognize as rapid_recognize
        return rapid_recognize(image,config)
    start = time.perf_counter()
    with LOCK, torch.inference_mode():
        reader = reader_for(config['device'])
        batch = config['batch_size'] if _device == 'cuda' else min(config['batch_size'], 8)
        kwargs = dict(detail=1, paragraph=False, batch_size=batch, workers=0,
                      canvas_size=config['canvas_size'], mag_ratio=1.0,
                      text_threshold=0.6, low_text=0.3, link_threshold=0.35,
                      rotation_info=[90, 270] if config['ocr_rotations'] else None)
        # Preserve small engineering callouts instead of shrinking an entire A0 sheet.
        width,height=image.size
        tile=min(config['canvas_size'],2560); overlap=160
        def starts(length):
            if length<=tile:return [0]
            positions=list(range(0,length-tile+1,tile-overlap))
            if positions[-1]!=length-tile:positions.append(length-tile)
            return positions
        values=[];tiles=0
        duplicates=DuplicateIndex()
        for top in starts(height):
            for left in starts(width):
                crop=image.crop((left,top,min(left+tile,width),min(top+tile,height)))
                try:
                    found=reader.readtext(np.asarray(crop), **kwargs)
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    raise RuntimeError('Mémoire CUDA insuffisante pour EasyOCR; réduisez la résolution ou la taille du lot.')
                tiles+=1
                for polygon,text,confidence in found:
                    polygon=[[float(x)+left,float(y)+top] for x,y in polygon]
                    cx=sum(x for x,y in polygon)/4;cy=sum(y for x,y in polygon)/4
                    duplicate=duplicates.find(text,cx,cy)
                    if duplicate is None:
                        duplicates.update(len(values),text,cx,cy)
                        values.append((polygon,text,float(confidence)))
                    elif confidence>values[duplicate][2]:
                        duplicates.update(duplicate,text,cx,cy)
                        values[duplicate]=(polygon,text,float(confidence))
    return values, {'device': _device, 'seconds': round(time.perf_counter()-start, 3), 'batch_size': kwargs['batch_size'],'tiles':tiles}
