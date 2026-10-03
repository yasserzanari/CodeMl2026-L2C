"""Single-engine, offline benchmark worker. Each invocation writes a unique run."""
from pathlib import Path
import argparse,json,sys,os,time,socket,hashlib,threading,subprocess,uuid,ctypes
from datetime import datetime,timezone
import numpy as np
from PIL import Image,ImageOps

CODE_ROOT=Path(__file__).resolve().parent.parent
ROOT=Path(os.environ.get('L2C_WORKSPACE',CODE_ROOT)).resolve()
DATA=ROOT/'data/l2c/benchmark'
sys.path.insert(0,str(CODE_ROOT))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TF_ENABLE_ONEDNN_OPTS='0',TF_CPP_MIN_LOG_LEVEL='2')
sys.stdout.reconfigure(encoding='utf-8')

def block_network(*args,**kwargs):raise RuntimeError('Network disabled during benchmark inference')
socket.socket.connect=block_network
socket.socket.connect_ex=block_network
socket.create_connection=block_network

def grouped_text(values,width,height):
    """Spatially select the central text line in a single-annotation crop; no label access."""
    if not values:return ''
    lines=[]
    for poly,text,score in sorted(values,key=lambda v:min(p[1] for p in v[0])):
        xs,ys=zip(*poly);cy=(min(ys)+max(ys))/2;hh=max(ys)-min(ys)
        group=next((g for g in lines if abs(g['y']-cy)<max(4,min(g['h'],hh)*.6)),None)
        if group:group['items'].append((min(xs),text));group['length']+=len(text)
        else:lines.append({'y':cy,'h':hh,'items':[(min(xs),text)],'length':len(text)})
    selected=min(lines,key=lambda g:abs(g['y']-height/2))
    return ' '.join(txt for x,txt in sorted(selected['items']))

class ResourceMonitor:
    def __init__(self):self.stop=threading.Event();self.samples=[]
    def start(self):
        def sample():
            while not self.stop.is_set():
                try:
                    value=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],
                        creationflags=0x08000000 if os.name=='nt' else 0,timeout=5,text=True)
                    memory,util=[int(x.strip()) for x in value.splitlines()[0].split(',')]
                    self.samples.append({'t':time.time(),'device_memory_mib':memory,'gpu_utilization_pct':util})
                except Exception:pass
                self.stop.wait(.5)
        self.thread=threading.Thread(target=sample,daemon=True);self.thread.start()
    def finish(self):
        self.stop.set();self.thread.join(timeout=6)
        return {'samples':self.samples,'metric':'Shared device memory; includes other processes, not an exclusive allocator measure',
                'peak_device_memory_mib':max((s['device_memory_mib'] for s in self.samples),default=None)}

def load_engine(name, rotations=True):
    if name=='easyocr':
        from l2c_app.ocr import reader_for
        import torch
        reader=reader_for('cuda' if torch.cuda.is_available() else 'cpu')
        torch.cuda.reset_peak_memory_stats() if torch.cuda.is_available() else None
        def run(img):return reader.readtext(np.asarray(img),detail=1,paragraph=False,batch_size=16,workers=0,canvas_size=2560,
                                            rotation_info=[90,270] if rotations else None,text_threshold=.6,low_text=.3,link_threshold=.35)
        return run,{'device':str(reader.device),'version':__import__('easyocr').__version__,'torch':torch.__version__}
    if name=='rapidocr':
        import onnxruntime as ort
        dll=ROOT/'.venv/Lib/site-packages/torch/lib'
        handles=[]
        if dll.exists():os.environ['PATH']=str(dll)+os.pathsep+os.environ.get('PATH','')
        if os.name=='nt' and dll.exists():handles.append(os.add_dll_directory(str(dll)));ort.preload_dlls(directory=str(dll))
        from rapidocr_onnxruntime import RapidOCR
        reader=RapidOCR(det_use_cuda=True,cls_use_cuda=True,rec_use_cuda=True,det_limit_side_len=2560,det_limit_type='max',
                        text_score=.25,intra_op_num_threads=4,inter_op_num_threads=2,rec_batch_num=16)
        providers={}
        for key in ('text_det','text_cls','text_rec'):
            obj=getattr(reader,key)
            for value in vars(obj).values():
                if hasattr(value,'session') and hasattr(value.session,'get_providers'):providers[key]=value.session.get_providers()
        def run(img):
            # RapidOCR expects BGR arrays; input to every candidate was the same RGB crop.
            result,_=reader(np.asarray(img)[:,:,::-1].copy())
            return result or []
        import importlib.metadata
        return run,{'device':'cuda' if all('CUDAExecutionProvider' in p for p in providers.values()) and providers else 'cpu',
                    'providers':providers,'version':importlib.metadata.version('rapidocr-onnxruntime'),'onnxruntime':ort.__version__}
    if name=='tesseract':
        import pymupdf as fitz
        def run(img):
            pix=fitz.Pixmap(fitz.csRGB,img.width,img.height,img.tobytes(),False)
            encoded=pix.pdfocr_tobytes(language='eng',tessdata=str(ROOT/'artifacts/l2c/models/tessdata'))
            values=[]
            with fitz.open(stream=encoded,filetype='pdf') as doc:
                p=doc[0];sx=img.width/p.rect.width;sy=img.height/p.rect.height
                for block in p.get_text('dict')['blocks']:
                    for line in block.get('lines',[]):
                        x0,y0,x1,y1=line['bbox'];txt=' '.join(s['text'] for s in line['spans'])
                        values.append(([[x0*sx,y0*sy],[x1*sx,y0*sy],[x1*sx,y1*sy],[x0*sx,y1*sy]],txt,None))
            return values
        return run,{'device':'cpu','version':'MuPDF integrated Tesseract','pymupdf':fitz.VersionBind,'confidence_available':False}
    if name=='ocrx-linefree':
        import importlib.util,cv2
        runner,meta=load_engine('rapidocr',rotations)
        path=ROOT/'artifacts/l2c/research/ocrx-engineering-drawings/tools/ocrx.py'
        spec=importlib.util.spec_from_file_location('benchmark_ocrx',path)
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        def run(img):
            cleaned=module.remove_structural_lines(cv2.cvtColor(np.asarray(img),cv2.COLOR_RGB2GRAY))
            return runner(Image.fromarray(cv2.cvtColor(cleaned,cv2.COLOR_BGR2RGB)))
        return run,meta|{'component':'OCRX structural-line removal + shared RapidOCR, not entire OCRX pipeline','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    if name=='a0-cpu':
        import importlib.util,io,pymupdf as fitz
        path=ROOT/'artifacts/l2c/research/a0-drawing-ocr/dutu_ocr.py'
        spec=importlib.util.spec_from_file_location('benchmark_a0',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        reader=module.get_ocr()
        providers={}
        for key in ('text_det','text_cls','text_rec'):
            for value in vars(getattr(reader,key)).values():
                if hasattr(value,'session') and hasattr(value.session,'get_providers'):providers[key]=value.session.get_providers()
        def run(img):
            buffer=io.BytesIO();img.save(buffer,format='PNG')
            with fitz.open() as doc:
                page=doc.new_page(width=img.width,height=img.height);page.insert_image(page.rect,stream=buffer.getvalue())
                horizontal,vertical,_,_,_=module.ocr_page(page,zoom=1,do_vertical=True)
            return [([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],text,conf) for text,conf,x0,y0,x1,y1 in horizontal+vertical]
        return run,{'device':'cpu','providers':providers,'component':'Unmodified A0 OCR page algorithm on the same crop embedded at 1 pixel per point; default CPU configuration','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    if name=='edocr2':
        import tensorflow as tf,types,importlib
        tf.config.threading.set_inter_op_parallelism_threads(2);tf.config.threading.set_intra_op_parallelism_threads(4)
        source=ROOT/'artifacts/l2c/research/edocr2/edocr2'
        # Import only the audited recognizer and tools. Avoid package initializers importing cloud integrations.
        package=types.ModuleType('benchmark_edocr_keras');package.__path__=[str(source/'keras_ocr')]
        sys.modules[package.__name__]=package
        module=importlib.import_module(package.__name__+'.recognition')
        alphabet=(source/'models/recognizer_dimensions_2.txt').read_text('utf8').strip()
        reader=module.Recognizer(alphabet=alphabet,weights=None)
        reader.model.load_weights(str(source/'models/recognizer_dimensions_2.keras'))
        def run(img):
            text=reader.recognize(np.asarray(img))
            return [([[0,0],[img.width,0],[img.width,img.height],[0,img.height]],str(text),None)]
        return run,{'device':'gpu' if tf.config.list_physical_devices('GPU') else 'cpu','tensorflow':tf.__version__,
                    'component':'Dimension recognizer on the same annotated crop; not the complete drawing pipeline','alphabet':alphabet}
    raise ValueError(name)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--engine',required=True,choices=['easyocr','rapidocr','tesseract','edocr2','ocrx-linefree','a0-cpu'])
    ap.add_argument('--split',choices=['development','validation','holdout'],required=True)
    ap.add_argument('--dpi',type=int,choices=[144,300],required=True);ap.add_argument('--no-rotations',action='store_true');args=ap.parse_args()
    manifest=DATA/'manifest-v1.json';items=json.loads(manifest.read_text('utf8'))
    items=[i for i in items if i['split']==args.split]
    folder=DATA/'runs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+args.engine+'-'+uuid.uuid4().hex[:6]);folder.mkdir(parents=True)
    monitor=ResourceMonitor();monitor.start();start=time.perf_counter();rows=[]
    result={'engine':args.engine,'split':args.split,'dpi':args.dpi,'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'network_disabled':True,'rotations':not args.no_rotations,'worker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'created_at':datetime.now(timezone.utc).isoformat(),'rows':rows}
    try:
        runner,meta=load_engine(args.engine,not args.no_rotations);result.update(runtime=meta,load_seconds=time.perf_counter()-start)
        for case in items:
            image=Image.open(DATA/case['images'][str(args.dpi)]).convert('RGB')
            if image.height>image.width*2:image=image.rotate(270,expand=True)
            image=ImageOps.expand(image,border=12,fill='white')
            begin=time.perf_counter()
            try:
                raw=runner(image)
                values=[([[float(x),float(y)] for x,y in poly],str(txt),float(score) if score is not None else None) for poly,txt,score in raw]
                text=grouped_text(values,image.width,image.height)
                row={'id':case['id'],'text':text,'all_text':'\n'.join(v[1] for v in values),'boxes':values,'seconds':time.perf_counter()-begin}
            except Exception as exc:row={'id':case['id'],'error':str(exc),'text':'','seconds':time.perf_counter()-begin}
            rows.append(row);print(case['id'],repr(row['text']),flush=True)
            (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        if args.engine=='easyocr':
            import torch
            if torch.cuda.is_available():result['torch_peak_allocated_bytes']=torch.cuda.max_memory_allocated()
    except Exception as exc:result['initialization_error']=repr(exc);print(repr(exc),flush=True)
    finally:
        result['resources']=monitor.finish();result['total_seconds']=time.perf_counter()-start
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        print('RESULT',folder,flush=True)
    if result.get('initialization_error'):raise SystemExit(1)

if __name__=='__main__':main()
