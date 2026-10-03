"""Local document registry. Client identifiers never become filesystem paths."""
from pathlib import Path
import hashlib
import threading
import pymupdf as fitz
from .config import RAW, STORE, write_json

PDF_LOCK = threading.RLock()
CATALOG_LOCK = threading.RLock()
_projects = {}
_docs = {}

def refresh():
    global _projects, _docs
    with CATALOG_LOCK:
        projects, documents = {}, {}
        roots = [(p.name,p) for p in RAW.iterdir() if p.is_dir()] if RAW.exists() else []
        roots += [(p.name,p) for p in (STORE/'imports').iterdir() if p.is_dir() and (p/'project.json').exists()]
        import json
        cache_path=STORE/'catalog.json'
        cache=json.loads(cache_path.read_text('utf-8')) if cache_path.exists() else {}
        new_cache={}
        for project_id, root in roots:
            info=json.loads((root/'project.json').read_text('utf-8')) if (root/'project.json').exists() else {'name':project_id}
            project={'id':project_id,'name':info['name'],'documents':[],'pages':0,'plan_pages':0,'atelier_pages':0}
            for path in sorted(root.rglob('*.pdf')):
                if path.is_symlink(): continue
                relative=path.relative_to(root).as_posix()
                stat=path.stat(); key=str(path); stamp=f'{stat.st_mtime_ns}:{stat.st_size}'
                item=cache.get(key)
                if not item or item['stamp']!=stamp:
                    try:
                        with PDF_LOCK, fitz.open(path) as pdf:
                            item={'stamp':stamp,'pages':len(pdf),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                    except Exception:
                        continue
                new_cache[key]=item
                doc_id=hashlib.sha256(f'{project_id}/{relative}'.encode()).hexdigest()[:24]
                role='atelier' if any(p.upper() in ('DA','ATELIER') for p in path.relative_to(root).parts[:-1]) else 'plan'
                document={'id':doc_id,'project_id':project_id,'name':path.name,'relative':relative,'role':role,
                          'pages':item['pages'],'sha256':item['sha256'],'path':str(path),'bytes':stat.st_size}
                documents[doc_id]=document
                project['documents'].append(doc_id); project['pages']+=item['pages']; project[role+'_pages']+=item['pages']
            project['documents'].sort(key=lambda ident:(documents[ident]['role']!='plan',documents[ident]['relative']))
            if project['documents']: projects[project_id]=project
        _projects,_docs=projects,documents
        write_json(cache_path,new_cache)
    return list(projects.values())

def projects():
    with CATALOG_LOCK: return list(_projects.values())
def project(identifier):
    with CATALOG_LOCK: return _projects.get(identifier)
def document(identifier):
    with CATALOG_LOCK: return _docs.get(identifier)
def public_document(doc): return {k:v for k,v in doc.items() if k!='path'}

def render(doc_id,page_number,box=None,scale=1.0,full=False):
    doc=document(doc_id)
    if not doc: raise KeyError('Document introuvable')
    with PDF_LOCK, fitz.open(doc['path']) as pdf:
        if page_number<1 or page_number>len(pdf): raise ValueError('Page invalide')
        page=pdf[page_number-1]
        clip=page.rect
        if box:
            rect=fitz.Rect(box)
            clip=page.rect if full else fitz.Rect(rect.x0-65,rect.y0-55,rect.x1+65,rect.y1+55)&page.rect
            if clip.is_empty:raise ValueError('Zone hors de la page.')
            # In-memory overlay only. The confidential source PDF is never overwritten.
            annotation=page.add_rect_annot(rect*page.derotation_matrix)
            annotation.set_colors(stroke=(.14,.39,.86));annotation.set_border(width=1)
            annotation.update()
        # Render in the visible rotated coordinate system used by extracted bounding boxes.
        pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=clip,alpha=False)
        return pix.tobytes('png')
