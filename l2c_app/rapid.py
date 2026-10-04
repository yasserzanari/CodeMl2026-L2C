"""Optional local PP-OCRv4 via RapidOCR. No network calls or dynamic downloads."""
import os
from pathlib import Path
import time
import numpy as np
import torch
from .ocr_duplicates import DuplicateIndex

_reader = None
_key = None
_handles = []
_ort_provider_check_ready = False

def _configure_onnxruntime_provider_order():
    """Keep CUDA first while preserving a safe CPU fallback for unsupported ops.

    RapidOCR's ONNX graphs are not guaranteed to be fully CUDA-compatible on
    every provider/build combination. CUDA remains the preferred execution
    provider, but disabling ONNX Runtime's CPU fallback can turn a readable
    page into a hard failure. The provider order is therefore checked without
    forbidding a CPU fallback.
    """
    global _ort_provider_check_ready
    if _ort_provider_check_ready:return
    try:
        from rapidocr_onnxruntime.utils.infer_engine import OrtInferSession, EP
        original_providers=OrtInferSession._get_ep_list
    except (ImportError,AttributeError) as exc:
        raise RuntimeError('Impossible de vérifier les providers RapidOCR.') from exc

    def providers_cuda_first(self):
        available=original_providers(self)
        if not getattr(self, 'cfg_use_cuda', False):
            return available
        if not any(entry[0]==EP.CUDA_EP.value for entry in available):
            raise RuntimeError('ONNX Runtime ne fournit pas CUDAExecutionProvider pour RapidOCR.')
        return available

    OrtInferSession._get_ep_list=providers_cuda_first
    _ort_provider_check_ready=True

def reader_for(config):
    global _reader, _key
    import onnxruntime as ort
    from rapidocr_onnxruntime import RapidOCR
    requested=config.get('device','auto')
    if requested not in ('auto','cuda','cpu'):
        raise ValueError('Périphérique OCR inconnu : choisir auto, cuda ou cpu.')
    if requested=='cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA indisponible. Aucune inférence OCR CPU ne sera lancée.')
    cuda=requested in ('auto','cuda') and torch.cuda.is_available()
    actual_device='cuda' if cuda else 'cpu'
    strategy=config.get('ocr_strategy','tiled')
    if strategy not in ('tiled','page'):
        raise ValueError('Stratégie OCR inconnue : choisir tiled ou page.')
    # Honor the configured recognition batch for both strategies. The previous
    # tiled-mode cap of 16 left the GPU underfilled when the UI selected 32/64.
    batch=min(config['batch_size'],64)
    key=(actual_device,config['canvas_size'],batch,strategy)
    if key!=_key:
        dll=Path(torch.__file__).parent/'lib'
        if os.name=='nt':
            if str(dll) not in os.environ.get('PATH','').split(os.pathsep):
                os.environ['PATH']=str(dll)+os.pathsep+os.environ.get('PATH','')
            _handles.append(os.add_dll_directory(str(dll)))
        ort.preload_dlls(directory=str(dll)) if cuda else None
        _configure_onnxruntime_provider_order()
        # Page mode retains original pixels for recognition crops. Detection still
        # uses RapidOCR 1.4.4's internal max-side resize (2000 px on large pages).
        # Keep the detailed classifier's conservative library default; only
        # the fast page profile opts into a larger classifier batch.
        extra={'max_side_len':1000000,'det_max_candidates':10000,'cls_batch_num':batch} if strategy=='page' else {}
        _reader=RapidOCR(det_use_cuda=cuda,cls_use_cuda=cuda,rec_use_cuda=cuda,
            det_limit_side_len=config['canvas_size'],det_limit_type='max',text_score=.25,
            intra_op_num_threads=4,inter_op_num_threads=2,rec_batch_num=key[2],**extra)
        _key=key
    providers={}
    for name in ('text_det','text_cls','text_rec'):
        for value in vars(getattr(_reader,name)).values():
            if hasattr(value,'session') and hasattr(value.session,'get_providers'):
                # Keep the registered provider list verbatim. CUDA is first
                # when requested; ONNX Runtime may use CPU for unsupported ops.
                providers[name]=value.session.get_providers()
    actual=len(providers)==3 and all(p and p[0]==('CUDAExecutionProvider' if cuda else 'CPUExecutionProvider') for p in providers.values())
    if not actual:
        expected = 'CUDA' if cuda else 'CPU'
        raise RuntimeError(f'RapidOCR n’a pas chargé ses trois modèles sur {expected}; providers incomplets détectés.')
    return _reader,providers,actual_device

def recognize_page(image,config):
    """Explicit fast strategy: one page detection, original-resolution crops.

    RapidOCR rectifies vertical crops and classifies 0/180 degrees itself.
    Small callouts can be missed by whole-page detection; this is not the tiled
    strategy with an invisible shortcut and must have a separate cache key.
    """
    from .ocr import LOCK
    start=time.perf_counter()
    config=config|{'ocr_strategy':'page'}
    actual_batch=min(config['batch_size'],64)
    with LOCK:
        reader,providers,device=reader_for(config)
        array=np.asarray(image)[:,:,::-1].copy()
        found,timings=reader(array)
        values=[]
        duplicates=DuplicateIndex()
        for polygon,text,confidence in found or []:
            mapped=[[float(x),float(y)] for x,y in polygon]
            cx=sum(x for x,y in mapped)/4;cy=sum(y for x,y in mapped)/4
            duplicate=duplicates.find(text,cx,cy)
            item=(mapped,str(text),float(confidence))
            if duplicate is None:
                duplicates.update(len(values),item[1],cx,cy)
                values.append(item)
            elif confidence>values[duplicate][2]:
                duplicates.update(duplicate,item[1],cx,cy)
                values[duplicate]=item
    phases={name:round(float(value),4) for name,value in zip(('detection','classification','recognition'),timings or [])}
    return values,{'device':device,'engine':'rapidocr','providers':providers,
                   'cpu_ep_fallback_disabled':False,
                   'strategy':'page','seconds':round(time.perf_counter()-start,3),
                   'phase_seconds':phases,'batch_size':actual_batch,
                   'tiles':1,'page_rotations':1,'crop_orientation':'automatic',
                   'quality_warning':'Détection page entière : les petits textes peuvent être manqués; valider les résultats.'}


def recognize(image,config):
    if config.get('ocr_strategy','tiled')=='page':
        return recognize_page(image,config)
    from .ocr import LOCK
    start=time.perf_counter(); values=[]; count=0
    duplicates=DuplicateIndex()
    with LOCK:
        reader,providers,device=reader_for(config)
        tile=min(config['canvas_size'],2560);step=tile-160
        width,height=image.size
        def starts(length):
            return sorted(set(list(range(0,max(1,length-tile+1),step))+[max(0,length-tile)]))
        for top in starts(height):
            for left in starts(width):
                arr=np.asarray(image.crop((left,top,min(left+tile,width),min(top+tile,height))))[:,:,::-1].copy()
                # Keep horizontal and vertical detection separate: avoid confidence-only rotation selection.
                rotations=(0,1,3) if config['ocr_rotations'] else (0,)
                for k in rotations:
                    data=np.ascontiguousarray(np.rot90(arr,k))
                    found,_=reader(data)
                    count+=1
                    for poly,text,confidence in found or []:
                        mapped=[];h,w=arr.shape[:2]
                        for x,y in poly:
                            if k==1:x,y=w-y,x
                            elif k==3:x,y=y,h-x
                            mapped.append([float(x)+left,float(y)+top])
                        xs,ys=zip(*mapped)
                        if k and (max(ys)-min(ys))<1.1*(max(xs)-min(xs)):continue
                        cx,cy=sum(xs)/4,sum(ys)/4
                        dup=duplicates.find(text,cx,cy)
                        item=(mapped,str(text),float(confidence))
                        if dup is None:
                            duplicates.update(len(values),item[1],cx,cy)
                            values.append(item)
                        elif confidence>values[dup][2]:
                            duplicates.update(dup,item[1],cx,cy)
                            values[dup]=item
    return values,{'device':device,'engine':'rapidocr','providers':providers,'seconds':round(time.perf_counter()-start,3),
                   'cpu_ep_fallback_disabled':False,
                   'batch_size':min(config['batch_size'],64),'tiles':count,'strategy':'tiled'}
