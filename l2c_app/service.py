from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import threading
import uuid
import time
from . import catalog
from .config import STORE,settings,write_json
from .extraction import read_page,extract_information
from .matching import reconcile,statistics
from .reports import export

POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='concorde')
LOCK=threading.RLock()
jobs={}
cancelled=set()

def recover():
    for path in (STORE/'runs').glob('*/job.json'):
        try:
            job=json.loads(path.read_text('utf-8'))
            if job['status'] in ('queued','running'):
                job.update(status='interrupted',message='Service redémarré. Relancez : le cache des pages sera réutilisé.')
                write_json(path,job)
            jobs[job['id']]=job
        except (ValueError,OSError): pass

def save(job):
    with LOCK: write_json(STORE/'runs'/job['id']/'job.json',job)
def start(project_id,request):
    project=catalog.project(project_id)
    if not project: raise KeyError('Projet introuvable')
    with LOCK:
        if any(j['status'] in ('queued','running') for j in jobs.values()): raise RuntimeError('Une analyse est déjà en cours.')
        ident=uuid.uuid4().hex
        config=settings()
        if request['profile']=='fast':
            config=config|{'ocr_engine':'rapidocr','dpi':96,
                           'ocr_rotations':False,'ocr_strategy':'page',
                           'batch_size':64,'device':config.get('device','auto')}
        job={'id':ident,'project_id':project_id,'project_name':project['name'],'status':'queued','current':0,
             'total':project['pages'],'message':'Préparation des documents','created_at':datetime.now(timezone.utc).isoformat(),
             'request':request,'config':config,'errors':[]}
        jobs[ident]=job;save(job)
        POOL.submit(execute,ident)
        return dict(job)

def execute(ident):
    job=jobs[ident]; project=catalog.project(job['project_id']); folder=STORE/'runs'/ident
    records=[]; pages=[]; ocr_used=0; begin=time.perf_counter()
    try:
        job['status']='running';save(job)
        for doc_id in project['documents']:
            doc=catalog.document(doc_id)
            for index in range(doc['pages']):
                if ident in cancelled:
                    job.update(status='cancelled',message='Analyse arrêtée. Les pages déjà traitées restent en cache.'); save(job);return
                job.update(stage='reading',current_doc=doc_id,current_page=index+1)
                job['message']=f"{doc['name']} · page {index+1}/{doc['pages']}";save(job)
                meta={'doc_id':doc_id,'file':doc['relative'],'page':index+1,'source':doc['role'],
                      'source_sha256':doc['sha256']}
                allow=job['request']['profile'] in ('complete','fast') or (job['request']['profile']=='sample' and ocr_used<job['request']['max_ocr_pages'])
                try:
                    reading=read_page(doc['path'],index,doc['sha256'],job['config'],allow_ocr=allow)
                    if reading['method']=='ocr': ocr_used+=1
                    extracted,extra=extract_information(doc,index+1,reading,job['project_id'])
                    records.extend(extracted)
                    meta.update(extra,method=reading['method'],cached=reading['cached'],seconds=reading.get('seconds',0),
                                ocr_strategy=reading.get('ocr_strategy',reading.get('strategy','tiled')),reused_cache=reading.get('reused_cache',False),
                                device=reading.get('device','cpu'),warning=reading.get('warning',reading.get('quality_warning','')))
                except Exception as exc:
                    meta.update(method='error',warning=str(exc)[:300]);job['errors'].append(meta)
                pages.append(meta);job['current']+=1;job['annotations']=len(records);job['ocr_pages']=ocr_used
                job['seconds']=round(time.perf_counter()-begin,1);save(job)
        job.update(stage='matching',message='Rapprochement des annotations');save(job)
        results=reconcile(records)
        run={'id':ident,'project_id':job['project_id'],'project_name':project['name'],'created_at':job['created_at'],
             'scope':job['request']['profile'],'config':job['config'],'records':records,'results':results,'pages':pages,
             'statistics':statistics(records,results,pages)}
        job.update(stage='reporting',message='Préparation du rapport PDF');save(job)
        write_json(folder/'run.json',run);export(run,folder)
        job.update(stage='completed',status='completed',message='Rapport disponible',statistics=run['statistics'],seconds=round(time.perf_counter()-begin,1));save(job)
    except Exception as exc:
        job.update(status='failed',message=str(exc)[:500]);save(job)

def load_run(ident):
    if ident not in jobs: raise KeyError('Analyse introuvable')
    path=STORE/'runs'/ident/'run.json'
    if not path.exists(): raise KeyError('Résultats non disponibles')
    return json.loads(path.read_text('utf-8'))

def review(ident,result_id,value):
    with LOCK:
        run=load_run(ident)
        row=next((r for r in run['results'] if r['id']==result_id),None)
        if not row: raise KeyError('Observation introuvable')
        row['review']=value | {'at':datetime.now(timezone.utc).isoformat()}
        folder=STORE/'runs'/ident
        write_json(folder/'run.json',run);export(run,folder)
        return row

def pair_reviews(ident):
    load_run(ident)
    path=STORE/'runs'/ident/'pair-reviews.json'
    return json.loads(path.read_text('utf-8')) if path.exists() else {'schema_version':1,'run_id':ident,'items':[]}

def review_presence(ident,result_id,value):
    from .presence import validate,counts
    import hashlib
    with LOCK:
        run=load_run(ident)
        row=next((r for r in run['results'] if r['id']==result_id),None)
        if not row:raise KeyError('Observation introuvable')
        needed=validate(run,row,value)
        if value['outcome']!='unresolved':
            ids=set(row['plan_ids']+row['atelier_ids'])
            if any(p['outcome']=='same_identity' and (p['plan_id'] in ids or p['atelier_id'] in ids)
                   for p in pair_reviews(ident)['items']):
                raise ValueError('Une correspondance est déjà confirmée pour cette annotation. Révisez cette correspondance avant de conclure à une absence.')
        folder=STORE/'runs'/ident
        decision=value|{'at':datetime.now(timezone.utc).isoformat(),
                        'source_run_sha256':hashlib.sha256((folder/'run.json').read_bytes()).hexdigest(),
                        'checked_documents':needed['opposite_documents'],
                        'basis':'human_document_review'}
        row.setdefault('presence_history',[]).append(decision)
        row['presence_review']=decision
        run['statistics']['presence_counts']=counts(run['results'])
        # Original machine status and existing reviews remain intact.
        write_json(folder/'run.json',run);export(run,folder)
        return row

def review_pair(ident,value):
    """Record identity adjudication separately from machine verdicts and source runs."""
    import hashlib
    with LOCK:
        run=load_run(ident)
        by_id={r['information']['id']:r for r in run['records']}
        for field,source in [('plan_id','plan'),('atelier_id','atelier')]:
            record=by_id.get(value[field])
            if not record or record['information']['source']!=source:
                raise ValueError('Annotation absente de cette analyse ou source incorrecte.')
        if not value['adjudicator'].strip():raise ValueError('Indiquez le nom du réviseur.')
        if value['outcome']=='unresolved' and not value['note'].strip():
            raise ValueError('Expliquez pourquoi la correspondance reste incertaine.')
        if value['outcome']=='same_identity':
            ids={value['plan_id'],value['atelier_id']}
            if any((r.get('presence_review') or {}).get('outcome') in ('manquant_dans_atelier','ajoute_dans_atelier')
                   and ids.intersection(r['plan_ids']+r['atelier_ids']) for r in run['results']):
                raise ValueError('Retirez la conclusion de présence/absence avant de confirmer cette correspondance.')
        pair_id=hashlib.sha256(json.dumps([ident,value['plan_id'],value['atelier_id']]).encode()).hexdigest()
        path=STORE/'runs'/ident/'run.json'
        row=value|{'id':pair_id,'at':datetime.now(timezone.utc).isoformat(),
                   'source_run_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                   'attributes_reviewed':False}
        if value['outcome']=='same_identity':
            from .matching import compare_armatures
            left,right=by_id[value['plan_id']],by_id[value['atelier_id']]
            diffs,common,blocked=compare_armatures(left,right)
            uncertain=any(r.get('confidence',0)<.8 or r.get('ocr_corrected') for r in (left,right))
            row['comparison']={'differences':diffs,'common_fields_by_bar':common,
                               'quantity_compared':bool(common) and all('quantite' in fields for fields in common),
                               'status':'a_verifier' if blocked or uncertain else 'non_conforme' if diffs else
                                        'conforme' if common and all('diametre' in f and ('quantite' in f or 'espacement_mm' in f) for f in common) else 'a_verifier',
                               'reason':blocked or ('Lecture incertaine : vérifier les valeurs dans les sources.' if uncertain else 'Proposition sur les valeurs extraites après validation humaine de l’identité ; attributs non validés.')}
        data=pair_reviews(ident)
        data.setdefault('history',[]).append(row)
        data['items']=[r for r in data['items'] if r['id']!=pair_id]+[row]
        write_json(STORE/'runs'/ident/'pair-reviews.json',data)
        return row
