"""Score private local benchmark outputs without copying them into the repository."""
import argparse,json,unicodedata,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from l2c_app.extraction import parse_armatures

def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC',text).upper().split())

def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        new=[i]
        for j,y in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=new
    return row[-1]

def score(manifest, result):
    truth={c['id']:c for c in manifest}; rows=[]; chars=words=ce=we=0
    for prediction in result['rows']:
        case=truth[prediction['id']]; ref=normalize(case['expected_text']); pred=normalize(prediction['text'])
        ce+=distance(ref,pred);chars+=len(ref);we+=distance(ref.split(),pred.split());words+=len(ref.split())
        bars=parse_armatures(prediction['text']); value=bars[0]['value'] if len(bars)==1 else {}
        fields={k:value.get(k)==v for k,v in case['expected_fields'].items()}
        rows.append({'id':case['id'],'correct':all(fields.values()),'fields':fields,'error':prediction.get('error')})
    n=len(rows)
    return {'engine':result['engine'],'split':result['split'],'dpi':result['dpi'],'rotations':result.get('rotations',True),
            'n':n,'exact_fields':sum(r['correct'] for r in rows),'cer':ce/max(chars,1),'wer':we/max(words,1),
            'runtime':result.get('runtime'),'median_seconds':statistics.median([r['seconds'] for r in result['rows']]) if n else None,
            'load_seconds':result.get('load_seconds'),'peak_device_mib':result.get('resources',{}).get('peak_device_memory_mib'),
            'field_counts':{k:{'correct':sum(r['fields'].get(k,False) for r in rows),'total':sum(k in r['fields'] for r in rows)} for k in next(iter(truth.values()))['expected_fields']},
            'rows':rows,'initialization_error':result.get('initialization_error')}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);args=p.parse_args()
    manifest=json.loads((args.folder/'manifest-v1.json').read_text('utf8'));out=[]
    for file in sorted((args.folder/'runs').glob('*/result.json')):
        r=score(manifest,json.loads(file.read_text('utf8')));r['run']=file.parent.name;out.append(r)
        print(r['run'],r['split'],r['dpi'],'rot',r['rotations'],f"{r['exact_fields']}/{r['n']}",round(r['cer'],3))
    (args.folder/'scores.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),'utf8')
