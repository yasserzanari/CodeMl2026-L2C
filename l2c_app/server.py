"""Loopback-only dashboard. No remote model calls or third-party UI resources."""
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
import json
import re
import uuid
import pymupdf as fitz
from fastapi import FastAPI,HTTPException,UploadFile,File,Form,Query,Request
from fastapi.responses import FileResponse,Response,JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import catalog,service
from .config import STORE,settings,write_json
from .models import AnalysisRequest,Settings,Review,PairReview,PairingAssistRequest,PresenceReview
from .ocr import hardware

@asynccontextmanager
async def lifespan(app):
    catalog.refresh();service.recover()
    yield

app=FastAPI(title='Concorde · L2C',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.middleware('http')
async def local_only(request:Request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if request.headers.get('x-concorde-request')!='1' or (origin and urlparse(origin).netloc!=request.headers.get('host')):
            return JSONResponse({'detail':'Requête locale non autorisée.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'"
    return response

@app.exception_handler(KeyError)
async def missing(request,exc):return JSONResponse({'detail':str(exc)},status_code=404)

@app.get('/api/overview')
def overview():
    with service.LOCK: jobs=sorted([dict(j) for j in service.jobs.values()],key=lambda j:j['created_at'],reverse=True)
    return {'application':'concorde','projects':catalog.projects(),'jobs':jobs,'hardware':hardware(),'settings':settings()}

@app.get('/api/projects/{project_id}')
def project(project_id:str):
    p=catalog.project(project_id)
    if not p:raise KeyError('Projet introuvable')
    return p|{'documents':[catalog.public_document(catalog.document(i)) for i in p['documents']]}

@app.post('/api/projects/{project_id}/analyse',status_code=202)
def analyse(project_id:str,request:AnalysisRequest):
    try:return service.start(project_id,request.model_dump())
    except RuntimeError as exc:raise HTTPException(409,str(exc))

@app.get('/api/jobs/{job_id}')
def job(job_id:str):
    with service.LOCK:
        if job_id not in service.jobs:raise KeyError('Analyse introuvable')
        return dict(service.jobs[job_id])

@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id:str):
    state=job(job_id)
    if state['status'] not in ('running','queued'):raise HTTPException(409,'Analyse déjà terminée.')
    service.cancelled.add(job_id)
    return {'message':'Arrêt demandé à la fin de la page en cours.'}

@app.get('/api/runs/{run_id}/results')
def results(run_id:str,q:str=Query('',max_length=200),status:str='',family:str='',sheet:str='',review_state:str='',offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
    run=service.load_run(run_id)
    def human_decision(row):
        review=row.get('review') or {}
        presence=row.get('presence_review') or {}
        return review.get('decision') or presence.get('outcome')
    rows=[r for r in run['results'] if (not status or r['status']==status) and (not family or r['family']==family)
          and (not sheet or r['sheet']==sheet)
          and (not review_state or (review_state=='unreviewed' and not human_decision(r)) or human_decision(r)==review_state)
          and (not q or q.casefold() in (r['element']+' '+r['sheet']+' '+r['reason']).casefold())]
    return {'id':run_id,'project_name':run['project_name'],'scope':run['scope'],'statistics':run['statistics'],
            'sheets':sorted({r['sheet'] for r in run['results']}),'total':len(rows),'items':rows[offset:offset+limit],'offset':offset,'limit':limit}

@app.get('/api/runs/{run_id}/results/{result_id}')
def detail(run_id:str,result_id:str,assist:bool=False,plan_id:str=''):
    from .presence import requirements
    run=service.load_run(run_id)
    row=next((r for r in run['results'] if r['id']==result_id),None)
    if not row:raise KeyError('Observation introuvable')
    ids=set(row['plan_ids']+row['atelier_ids'])
    records=[r for r in run['records'] if r['information']['id'] in ids]
    suggestions=[]
    if assist or settings().get('pairing_assistance',False):
        from .pairing import candidates,candidate_differences,candidate_index
        candidate_lookup=candidate_index(run['records'])
        plans=[r for r in records if r['information']['source']=='plan' and (not plan_id or r['information']['id']==plan_id)]
        for plan in plans[:4]:
            for c in candidates(plan,run['records'],limit=None,index=candidate_lookup):
                suggestions.append(c|{'plan_id':plan['information']['id'],
                    'differences':candidate_differences(plan,c['record'])})
    index=run['results'].index(row)
    return row|{'presence_review_requirements':requirements(run,row),'records':records,'pairing_candidates':suggestions,'pair_reviews':service.pair_reviews(run_id)['items'],'position':index+1,'total':len(run['results']),
                'previous':run['results'][index-1]['id'] if index else None,
                'next':run['results'][index+1]['id'] if index+1<len(run['results']) else None}

@app.get('/api/runs/{run_id}/pairing')
def pairing_queue(run_id:str,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
    from .pairing import review_queue
    run=service.load_run(run_id);summary=review_queue(run)
    items=summary.pop('items')
    return summary|{'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit,
                    'reviewed_pairs':len(service.pair_reviews(run_id)['items']),
                    'pages_processed':run['statistics']['pages_processed'],'pages_total':len(run['pages'])}

@app.post('/api/runs/{run_id}/pair-reviews')
def save_pair_review(run_id:str,value:PairReview):
    try:return service.review_pair(run_id,value.model_dump())
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post('/api/runs/{run_id}/pairing-assist')
def pairing_assist(run_id:str,value:PairingAssistRequest):
    run=service.load_run(run_id)
    by_id={r['information']['id']:r for r in run['records']}
    plan,atelier=by_id.get(value.plan_id),by_id.get(value.atelier_id)
    if not plan or plan['information']['source']!='plan':raise HTTPException(404,'Annotation de plan introuvable.')
    if not atelier or atelier['information']['source']!='atelier':raise HTTPException(404,'Annotation atelier introuvable.')
    from .llm_pairing import PairingModelError,PairingModelUnavailable,analyze_pair
    try:return analyze_pair(plan,atelier)
    except PairingModelUnavailable as exc:raise HTTPException(503,str(exc))
    except PairingModelError as exc:raise HTTPException(502,str(exc))

@app.get('/api/runs/{run_id}/pair-reviews')
def export_pair_reviews(run_id:str):
    return JSONResponse(service.pair_reviews(run_id),headers={'Content-Disposition':'attachment; filename="correspondances-revisees.json"'})

@app.get('/api/runs/{run_id}/reports')
def report_index(run_id:str):
    from .report_view import index
    return index(service.load_run(run_id))

@app.get('/api/runs/{run_id}/reports/{sheet_id}/preview')
def report_preview(run_id:str,sheet_id:str,page:int=Query(1,ge=1)):
    from .report_view import make_pdf
    content=make_pdf(service.load_run(run_id),sheet_id)
    with catalog.PDF_LOCK,fitz.open(stream=content,filetype='pdf') as document:
        if page>len(document):raise HTTPException(422,'Page de rapport invalide.')
        pix=document[page-1].get_pixmap(matrix=fitz.Matrix(1.3,1.3),alpha=False)
        return Response(pix.tobytes('png'),media_type='image/png',headers={'X-Report-Pages':str(len(document))})

@app.get('/api/runs/{run_id}/reports/{sheet_id}/pdf')
def report_pdf(run_id:str,sheet_id:str):
    from .report_view import make_pdf
    return Response(make_pdf(service.load_run(run_id),sheet_id),media_type='application/pdf',
                    headers={'Content-Disposition':f'attachment; filename="rapport-{sheet_id}.pdf"'})

@app.post('/api/runs/{run_id}/reports-export')
def report_archive(run_id:str,value:dict):
    from .report_view import archive
    ids=value.get('sheets')
    if not isinstance(ids,list) or not ids or len(ids)>500 or not all(isinstance(s,str) for s in ids):
        raise HTTPException(422,'Sélectionnez de 1 à 500 feuillets.')
    return Response(archive(service.load_run(run_id),ids),media_type='application/zip',
                    headers={'Content-Disposition':'attachment; filename="rapports-par-feuillet.zip"'})

@app.get('/api/documents/{doc_id}/meta')
def document_meta(doc_id:str,page:int=Query(1,ge=1)):
    doc=catalog.document(doc_id)
    if not doc:raise KeyError('Document introuvable')
    with catalog.PDF_LOCK,fitz.open(doc['path']) as pdf:
        if page>len(pdf):raise HTTPException(422,'Page invalide.')
        p=pdf[page-1]
        return catalog.public_document(doc)|{'page':page,'width':p.rect.width,'height':p.rect.height,
                                             'native_text':len(p.get_text().strip())>=100}

@app.post('/api/runs/{run_id}/results/{result_id}/review')
def review(run_id:str,result_id:str,value:Review):return service.review(run_id,result_id,value.model_dump())

@app.post('/api/runs/{run_id}/results/{result_id}/presence-review')
def presence_review(run_id:str,result_id:str,value:PresenceReview):
    try:return service.review_presence(run_id,result_id,value.model_dump())
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.get('/api/runs/{run_id}/download/{filename}')
def download(run_id:str,filename:str):
    if filename not in ('rapport.pdf','informations.json','comparaisons.json'):raise KeyError('Export introuvable')
    if job(run_id)['status']!='completed':raise HTTPException(409,'Export non disponible.')
    return FileResponse(STORE/'runs'/run_id/filename,filename=filename)

@app.get('/api/documents/{doc_id}/pdf')
def pdf(doc_id:str):
    doc=catalog.document(doc_id)
    if not doc:raise KeyError('Document introuvable')
    return FileResponse(doc['path'],media_type='application/pdf')

@app.get('/api/documents/{doc_id}/preview')
def preview(doc_id:str,page:int=Query(1,ge=1),box:str='',scale:float=Query(.35,ge=.1,le=2),full:bool=False):
    bounds=None
    if box:
        try:
            bounds=[float(n) for n in box.split(',')]
            import math
            if len(bounds)!=4 or not all(math.isfinite(n) for n in bounds) or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:raise ValueError()
        except ValueError:raise HTTPException(422,'Zone invalide.')
    try:return Response(catalog.render(doc_id,page,bounds,scale,full=full),media_type='image/png')
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.get('/api/settings')
def get_settings():return {'settings':settings(),'hardware':hardware()}

@app.post('/api/settings')
def set_settings(value:Settings):
    write_json(STORE/'settings.json',value.model_dump())
    return {'settings':value.model_dump(),'hardware':hardware()}

@app.post('/api/import',status_code=201)
async def import_project(name:str=Form(...,min_length=1,max_length=80),plans:list[UploadFile]=File(...),atelier:list[UploadFile]=File(...)):
    if len(plans)+len(atelier)>200:raise HTTPException(413,'Maximum 200 documents par projet.')
    ident='import-'+uuid.uuid4().hex[:12];root=STORE/'imports'/ident;total=0
    # No registry visibility until all files validate and project.json is committed.
    try:
        for role,files in [('plan',plans),('atelier',atelier)]:
            (root/role).mkdir(parents=True,exist_ok=True)
            for index,upload in enumerate(files):
                filename=Path(upload.filename or '').name
                if not filename.lower().endswith('.pdf'):raise HTTPException(422,'Seuls les fichiers PDF sont acceptés.')
                safe=re.sub(r'[^\w .()-]','_',filename)[:140]
                path=root/role/f'{index+1:03d}-{safe}'
                count=0
                with path.open('wb') as output:
                    while chunk:=await upload.read(1024*1024):
                        count+=len(chunk);total+=len(chunk)
                        if count>150*1024**2 or total>600*1024**2:raise HTTPException(413,'Limite : 150 Mo par PDF, 600 Mo par projet.')
                        output.write(chunk)
                try:
                    with catalog.PDF_LOCK,fitz.open(path) as doc:
                        if doc.needs_pass or len(doc)==0:raise ValueError()
                except Exception:raise HTTPException(422,f'PDF invalide ou protégé : {safe}')
        write_json(root/'project.json',{'name':name.strip() or 'Nouveau projet'})
        catalog.refresh()
        return catalog.project(ident)
    except Exception:
        # Only remove this request's freshly allocated UUID directory, never an existing project.
        import shutil
        if root.exists() and root.parent.resolve()==(STORE/'imports').resolve():shutil.rmtree(root)
        raise
    finally:
        for upload in plans+atelier:await upload.close()

app.mount('/',StaticFiles(directory=Path(__file__).parent/'static',html=True),name='ui')
