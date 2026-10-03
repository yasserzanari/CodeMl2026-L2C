"""Private page-level comparison using identical local manifests and frozen settings."""
import os,json,sys,time,uuid,argparse,socket
from pathlib import Path
ROOT=Path(os.environ.get('L2C_WORKSPACE',Path(__file__).resolve().parent.parent))
for key,path in [('L2C_DATA','data/l2c/raw'),('L2C_STORE','data/l2c/app'),('L2C_MODELS','artifacts/l2c/models')]:
    os.environ.setdefault(key,str(ROOT/path))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from l2c_app import catalog
from l2c_app.config import DEFAULTS
from l2c_app.extraction import read_page,extract_information,parse_armatures,join_ocr_lines

def blocked(*a,**k):raise RuntimeError('Network disabled during benchmark')
socket.socket.connect=blocked;socket.create_connection=blocked
sys.stdout.reconfigure(encoding='utf8')
p=argparse.ArgumentParser();p.add_argument('--engine',choices=['easyocr','rapidocr'],required=True)
p.add_argument('--split',choices=['validation','holdout'],required=True);args=p.parse_args()
data=ROOT/'data/l2c/benchmark';cases=json.loads((data/'manifest-v1.json').read_text('utf8'))
cases=[c for c in cases if c['split']==args.split and c['source_kind']=='outlined_vector']
catalog.refresh();config=DEFAULTS|{'ocr_engine':args.engine,'batch_size':16}
out=data/'page-runs'/str(uuid.uuid4());out.mkdir(parents=True);results=[]
for doc_id,page_no in sorted({(c['doc_id'],c['page']) for c in cases}):
    doc=catalog.document(doc_id);start=time.perf_counter()
    # Unique cache digest makes this a cold page extraction for every comparison.
    reading=read_page(doc['path'],page_no-1,str(uuid.uuid4()),config,force_ocr=True)
    records,page_metadata=extract_information(doc,page_no,reading,'benchmark')
    rows=[]
    for c in cases:
        if (c['doc_id'],c['page'])!=(doc_id,page_no):continue
        x0,y0,x1,y1=c['box'];hits=[]
        for line in reading['lines']:
            a,b,d,e=line['box'];cx,cy=(a+d)/2,(b+e)/2
            if x0<=cx<=x1 and y0<=cy<=y1:hits.append(line)
        text=' '.join(l['text'] for l in sorted(hits,key=lambda l:l['box'][0]))
        parsed=parse_armatures(text);value=parsed[0]['value'] if len(parsed)==1 else {}
        ok=all(value.get(k)==v for k,v in c['expected_fields'].items())
        rows.append({'id':c['id'],'text':text,'exact_fields':ok,'hit_count':len(hits)})
    result={'doc_id':doc_id,'page':page_no,'engine':args.engine,'split':args.split,'rows':rows,
            'reading':reading,'records':records,'page_metadata':page_metadata,'seconds':time.perf_counter()-start}
    results.append(result);(out/'result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf8')
    print(args.engine,args.split,'fields',sum(r['exact_fields'] for r in rows),'/',len(rows),'annotations',len(records),'seconds',round(result['seconds'],2),flush=True)
print(out)
