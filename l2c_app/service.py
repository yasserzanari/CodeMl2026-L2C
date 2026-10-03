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
        job={'id':ident,'project_id':project_id,'project_name':project['name'],'status':'queued','current':0,
             'total':project['pages'],'message':'Préparation des documents','created_at':datetime.now(timezone.utc).isoformat(),
             'request':request,'config':settings(),'errors':[]}
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
                allow=job['request']['profile']=='complete' or (job['request']['profile']=='sample' and ocr_used<job['request']['max_ocr_pages'])
                try:
                    reading=read_page(doc['path'],index,doc['sha256'],job['config'],allow_ocr=allow)
                    if reading['method']=='ocr': ocr_used+=1
                    extracted,extra=extract_information(doc,index+1,reading,job['project_id'])
                    records.extend(extracted)
                    meta.update(extra,method=reading['method'],cached=reading['cached'],seconds=reading.get('seconds',0),
                                device=reading.get('device','cpu'),warning=reading.get('warning',''))
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
