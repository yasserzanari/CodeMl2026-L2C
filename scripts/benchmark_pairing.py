"""Read-only matching audit of frozen local runs and optional organizer spreadsheet.
No OCR rerun, no reference values passed to the candidate retriever.
"""
import argparse,json,sys,hashlib,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from l2c_app.pairing import candidates,element_key,candidate_index
from l2c_app.matching import reconcile
from l2c_app.extraction import parse_armatures

def audit(run):
    records=run['records'];baseline=reconcile(records);index=candidate_index(records)
    plans=[r for r in records if r['information']['source']=='plan'];counts=collections.Counter()
    for p in plans:
        c=candidates(p,records,index=index)
        counts['plans']+=1;counts['with_candidates']+=bool(c);counts['multiple_candidates']+=len(c)>1
        counts['unresolved_identity']+=not p.get('identity_resolved',False)
        counts['missing_level']+=not p.get('level')
        counts['repeated_candidate_text']+=len({r['record'].get('raw') for r in c})<len(c)
    old={(r['id'],r['status']) for r in run['results']}
    now={(r['id'],r['status']) for r in baseline}
    return dict(project=run['project_id'],run=run['id'],coverage=dict(counts),
        scope=run.get('scope'),source_annotations=dict(collections.Counter(r['information']['source'] for r in records)),
        page_coverage=run.get('statistics',{}).get('pages_processed'),pages_total=run.get('statistics',{}).get('pages_total'),
        baseline_verdict_changes=len(old.symmetric_difference(now)),
        precision=None,recall=None,reason='No exhaustive adjudicated pair labels; coverage is not accuracy')

def organizer_cases(run,path):
    import openpyxl
    rows=list(openpyxl.load_workbook(path,data_only=True).active.values)[1:];out=[]
    for sheet,location,left,right,*_ in rows:
        a,b=parse_armatures(str(left)),parse_armatures(str(right))
        reliable=len(a)==len(b)==1 and a[0]['value']!=b[0]['value']
        plans=[r for r in run['records'] if r['information']['source']=='plan' and
            r['information']['feuillet']==sheet and element_key(r['information']['element'])==element_key(str(location))]
        suggestions=[c for p in plans for c in candidates(p,run['records'])]
        conclusions=[r for r in run['results'] if r['sheet']==sheet and element_key(r['element'])==element_key(str(location))]
        detected=any(r['status']=='non_conforme' for r in conclusions)
        out.append(dict(sheet=sheet,location=location,reference_left=left,reference_right=right,
            interpretable_reference=reliable,plan_annotations_at_declared_identity=len(plans),
            retrieved_candidates=len(suggestions),automatic_alert_at_declared_identity=detected,
            limitation='Exact identity lookup only; geometrical localization not independently adjudicated'))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',action='append',type=Path,required=True)
    p.add_argument('--labels',type=Path);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);result={'runs':[],'claim':'Exploratory retrieval audit, not official scoring'}
    for path in args.run:
        run=json.loads(path.read_text('utf8'));r=audit(run);r['input_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        result['runs'].append(r)
    if args.labels:
        run=json.loads(args.run[0].read_text('utf8'));result['organizer_cases']=organizer_cases(run,args.labels)
        result['labels_sha256']=hashlib.sha256(args.labels.read_bytes()).hexdigest()
    (args.out/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
