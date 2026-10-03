"""Optional local PP-OCRv4 via RapidOCR. No network calls or dynamic downloads."""
import os
from pathlib import Path
import time
import numpy as np
import torch

_reader = None
_key = None
_handles = []

def reader_for(config):
    global _reader, _key
    import onnxruntime as ort
    from rapidocr_onnxruntime import RapidOCR
    cuda=config['device']!='cpu' and torch.cuda.is_available()
    key=(cuda,config['canvas_size'],min(config['batch_size'],16))
    if key!=_key:
        dll=Path(torch.__file__).parent/'lib'
        if os.name=='nt':
            if str(dll) not in os.environ.get('PATH','').split(os.pathsep):
                os.environ['PATH']=str(dll)+os.pathsep+os.environ.get('PATH','')
            _handles.append(os.add_dll_directory(str(dll)))
        ort.preload_dlls(directory=str(dll)) if cuda else None
        _reader=RapidOCR(det_use_cuda=cuda,cls_use_cuda=cuda,rec_use_cuda=cuda,
            det_limit_side_len=config['canvas_size'],det_limit_type='max',text_score=.25,
            intra_op_num_threads=4,inter_op_num_threads=2,rec_batch_num=key[2])
        _key=key
    providers={}
    for name in ('text_det','text_cls','text_rec'):
        for value in vars(getattr(_reader,name)).values():
            if hasattr(value,'session') and hasattr(value.session,'get_providers'):
                providers[name]=value.session.get_providers()
    actual=len(providers)==3 and all('CUDAExecutionProvider' in p for p in providers.values())
    if config['device']=='cuda' and not actual:
        raise RuntimeError('RapidOCR ne dispose pas de CUDA pour ses trois modèles. Choisissez Auto ou CPU.')
    return _reader,providers,'cuda' if actual else 'cpu'

def recognize(image,config):
    from .ocr import LOCK
    start=time.perf_counter(); values=[]; count=0
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
                    try:found,_=reader(data)
                    except Exception as exc:
                        if not any(token in str(exc).lower() for token in ('out of memory','alloc','cuda failure')):raise
                        # Explicit CPU retry is reported; never silently claim GPU execution.
                        reader=None
                        fallback,_,_=reader_for(config|{'device':'cpu','batch_size':1})
                        reader=fallback
                        found,_=reader(data);device='cpu-fallback'
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
                        dup=next((i for i,(p,t,c) in enumerate(values) if t==text and
                            abs(sum(x for x,y in p)/4-cx)<20 and abs(sum(y for x,y in p)/4-cy)<20),None)
                        item=(mapped,str(text),float(confidence))
                        if dup is None:values.append(item)
                        elif confidence>values[dup][2]:values[dup]=item
    return values,{'device':device,'engine':'rapidocr','providers':providers,'seconds':round(time.perf_counter()-start,3),
                   'batch_size':min(config['batch_size'],16),'tiles':count}
