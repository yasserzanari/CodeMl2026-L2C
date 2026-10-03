"""PDF geometry, OCR and conservative reinforcement parsing."""
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
import pymupdf as fitz
from .models import Armature, Information
from .config import STORE, write_json
from .ocr import recognize
from .catalog import PDF_LOCK

VERSION = 'concorde-1.3-engine-choice'
SHEET = re.compile(r'\bS\s*[-–]\s*(\d{3}(?:[A-Ca-c]|[.][a-c])?)\b')
BAR = re.compile(r'(?<!\d)(10|15|20|25|30|35|45|55)\s*[Mm]\b')
AXIS = re.compile(r'^(?!S[-/]\d{3})(?:[A-Z](?:\.\d+)?[-/ ]?\d{1,2}(?:\.\d+)?|[CP][- ]?\d+(?:\.\d+)?)$')

def norm(text):
    return unicodedata.normalize('NFKC', text).replace('–', '-').replace('−', '-').strip()

def family(text, fallback='inconnu'):
    t = norm(text).upper()
    for words, name in [('COLONN', 'colonne'), ('POUTR', 'poutre'), ('RADIER|SEMELLE|FONDATION', 'fondation'),
                        ('REFEND|CISAIL|MUR', 'mur_refend'), ('DALLE|ARMATURE DU|ARMATURES DU', 'dalle')]:
        if re.search(words, t): return name
    return fallback

def level(text):
    t = norm(text).upper()
    matches = re.findall(r'\b(?:NIV(?:EAU)?\s*[-.:]?\s*(\d+)|(?<![A-Z])(RDC|REZ-DE-CHAUSS[EÉ]E|SS\s*\d|SOUS-SOL|TOIT|TR[EÉ]FOND))', t)
    vals = []
    for number, word in matches:
        value = 'N'+number if number else word.replace(' ', '').replace('REZ-DE-CHAUSSÉE','RDC').replace('REZ-DE-CHAUSSEE','RDC')
        if value not in vals: vals.append(value)
    return '|'.join(vals[:4])

def parse_armatures(text):
    t = norm(text)
    out = []
    for match in BAR.finditer(t):
        before, after = t[max(0, match.start()-32):match.start()], t[match.end():match.end()+65]
        q = re.search(r'(?:(\d+)\s*[xX×]\s*)?(\d+)\s*[-:]?\s*$', before)
        # A number directly preceding a designation can also be a spacing; reject @ context.
        if q and re.search(r'@\s*$|RANG\s*$', before[:q.start()],re.I): q = None
        quantity = int(q.group(2)) if q else None
        if quantity is not None and (quantity == 0 or quantity > 10000): quantity = None
        spacing = re.search(r'^\s*@\s*(\d+(?:[.,]\d+)?)(\s*(?:["″]|\x27\x27|po\b|mm\b))?', after, re.I)
        sp = None
        if spacing:
            sp = float(spacing.group(1).replace(',', '.'))
            unit = (spacing.group(2) or '').strip()
            if unit and unit.lower() != 'mm': sp *= 25.4
            elif not unit and sp<50: sp=None  # Imperial-looking unitless notation is not silently millimetres.
        # Length is used only when explicitly labelled, never guessed from a fabrication mark.
        length = re.search(r'\b(?:LONG(?:UEUR)?|L)\s*[=:]\s*(\d+(?:[.,]\d+)?)\s*(mm|["″])?', after, re.I)
        lng = float(length.group(1).replace(',', '.')) if length else None
        if length and length.group(2) in ['"', '″']: lng *= 25.4
        rep = re.search(r'\b\d{2}[A-Z]\d+(?:-\d+)?\b', after)
        mult = int(q.group(1)) if q and q.group(1) else 1
        role = 'etr' if re.search(r'ETR|ÉTR|LIG\.?|ÉP\.', t.upper()) else ('vert' if 'VERT' in t.upper() or 'ARM.' in t.upper() else '')
        out.append({'value': Armature(repere=rep.group(0) if rep else None, diametre=match.group(1)+'M', quantite=quantity,
                                     espacement_mm=round(sp,3) if sp else None, longueur_mm=lng).model_dump(),
                    'multiplicity': mult, 'role': role})
    return out

def native_lines(page):
    lines=[];seen=set()
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            text=norm(' '.join(s['text'] for s in line['spans']))
            if not text: continue
            rect=fitz.Rect(line['bbox']) * page.rotation_matrix
            key=(text,*(round(v,1) for v in rect))
            if key in seen: continue
            seen.add(key)
            lines.append({'text':text, 'box':list(rect), 'confidence':1.0, 'method':'pdf'})
    return lines

def read_page(path, page_index, digest, config, allow_ocr=True, force_ocr=False):
    signature = {k:config[k] for k in ['dpi','canvas_size','ocr_confidence','ocr_rotations']}
    signature['ocr_engine']=config.get('ocr_engine','easyocr')
    key=hashlib.sha256((VERSION+digest+str(page_index)+json.dumps(signature,sort_keys=True)+str(force_ocr)).encode()).hexdigest()
    cache=STORE/'cache'/f'{key}.json'
    if cache.exists():
        result=json.loads(cache.read_text('utf-8'))
        if result['method']=='ocr' and not allow_ocr:
            return {'lines':[],'method':'skipped','width':result['width'],'height':result['height'],
                    'rotation':result['rotation'],'cached':False,'warning':'OCR exclu du périmètre demandé.'}
        result['cached']=True
        return result
    with PDF_LOCK, fitz.open(path) as doc:
        page=doc[page_index]
        lines=native_lines(page)
        use_ocr=force_ocr or sum(len(l['text']) for l in lines)<100
        meta={'method':'pdf','device':'cpu','seconds':0}
        if use_ocr and not allow_ocr:
            return {'lines':[], 'method':'skipped','width':page.rect.width,'height':page.rect.height,'cached':False,
                    'rotation':page.rotation,'warning':'Page sans texte natif, OCR non exécuté.'}
        dims={'width':page.rect.width,'height':page.rect.height,'rotation':page.rotation}
        if use_ocr:
            pix=page.get_pixmap(matrix=fitz.Matrix(config['dpi']/72, config['dpi']/72), alpha=False)
            from PIL import Image
            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            sx,sy=page.rect.width/pix.width,page.rect.height/pix.height
    if use_ocr:
        raw,meta=recognize(image,config)
        lines=[]
        for polygon,text,confidence in raw:
            if confidence < config['ocr_confidence']: continue
            xs,ys=zip(*polygon)
            lines.append({'text':norm(text),'box':[float(min(xs)*sx),float(min(ys)*sy),float(max(xs)*sx),float(max(ys)*sy)],
                          'confidence':float(confidence),'method':'ocr'})
        meta['method']='ocr'
    result={'lines':lines,**dims,'cached':False,**meta}
    write_json(cache,result)
    return result

def center(box): return ((box[0]+box[2])/2,(box[1]+box[3])/2)

def join_ocr_lines(lines):
    """Join only close fragments on the same baseline; keep original OCR evidence."""
    if not lines or lines[0].get('method')!='ocr':return lines
    lines=sorted(lines,key=lambda line:(line['box'][0],line['box'][1]))
    output=[];used=set()
    for i,line in enumerate(lines):
        if i in used:continue
        group=[line];used.add(i);box=list(line['box']);cy=center(box)[1];height=box[3]-box[1]
        neighbours=sorted(enumerate(lines),key=lambda pair:pair[1]['box'][0])
        for j,other in neighbours:
            if j in used:continue
            ob=other['box'];oh=ob[3]-ob[1]
            if ob[0]>=box[2] and ob[0]-box[2]<max(12,height*2) and abs(center(ob)[1]-cy)<min(height,oh)*.4:
                group.append(other);used.add(j);box=[box[0],min(box[1],ob[1]),ob[2],max(box[3],ob[3])]
        output.append({'text':' '.join(g['text'] for g in group),'box':box,'method':'ocr','confidence':min(g['confidence'] for g in group)})
    return output

def normalize_ocr_designations(text):
    # Restrict common OCR substitutions to a known bar designation, never arbitrary dimensions.
    text=re.sub(r'(?<!\w)([123])[oO]\s*[Mm]\b',lambda m:m.group(1)+'0M',text)
    text=re.sub(r'(?<!\w)[Il][oO0]\s*[Mm]\b','10M',text)
    return re.sub(r'(?<!\w)([12345])[sS]\s*[Mm]\b',lambda m:m.group(1)+'5M',text)

def grid_axes(lines,width,height):
    """Keep repeated, aligned grid labels; avoid interpreting any nearby number as an axis."""
    groups=defaultdict(list)
    for line in lines:
        s=line['text'].strip()
        if re.fullmatch(r'[A-Z](?:\.\d+)?|\d{1,2}(?:\.\d+)?',s): groups[s].append(center(line['box']))
    grids={'alpha':[],'numeric':[]}
    for s,points in groups.items():
        for x,y in points:
            for a,b in points:
                orient='x' if abs(x-a)<width*.012 and abs(y-b)>height*.3 else ('y' if abs(y-b)<height*.012 and abs(x-a)>width*.3 else '')
                if orient:
                    grids['alpha' if s[0].isalpha() else 'numeric'].append((s,orient,x if orient=='x' else y))
                    break
    return grids

def extract_information(doc_info, page_number, reading, project_id):
    lines=join_ocr_lines(reading['lines']); w,h=reading['width'],reading['height']
    tail=[l for l in lines if center(l['box'])[0]>w*.87 and center(l['box'])[1]>h*.65]
    candidates=[(SHEET.findall(l['text']),l) for l in tail]
    ids=[ids[-1] for ids,l in candidates if ids]
    if not ids:
        ids=[ids[-1] for l in lines if (ids:=SHEET.findall(l['text']))]
    sheet='S-'+ids[-1] if ids else f"{doc_info['name']} · {page_number}"
    title=' '.join(l['text'] for l in tail)
    titles=[l['text'] for l in tail if re.search(r'PLAN|TABLEAU|ARMATURE|FONDATION|NIVEAU',l['text'],re.I)]
    typ=family(' '.join(titles))
    if typ=='inconnu':typ=family(doc_info['relative'])
    if typ=='inconnu' and sheet.startswith('S-'):
        code=re.search(r'\d{3}',sheet)
        if code:
            num=int(code.group())
            typ='fondation' if num in (50,60,100) else {3:'poutre',4:'mur_refend',5:'colonne',6:'dalle'}.get(num//100,'inconnu')
    lev=level(title) or level(doc_info['name'])
    anchors=[(l,AXIS.fullmatch(l['text'].strip().upper())) for l in lines]
    anchors=[l for l,m in anchors if m]
    grids=grid_axes(lines,w,h)
    # Column schedules use a lane label at the bottom and floor elevations down the left edge.
    schedule_anchors=[a for a in anchors if center(a['box'])[1]>h*.7]
    schedule_levels=[(center(l['box'])[1],level(l['text'])) for l in lines if center(l['box'])[0]<w*.065 and level(l['text'])]
    is_schedule=doc_info['role']=='atelier' and typ=='colonne' and len(schedule_anchors)>=3 and len(schedule_levels)>=2
    schedule_levels=sorted(set(schedule_levels))
    records=[]
    for line_index,line in enumerate(lines):
        parsed_text=normalize_ocr_designations(line['text']) if line['method']=='ocr' else line['text']
        parsed=parse_armatures(parsed_text)
        if not parsed: continue
        x,y=center(line['box'])
        neighbours=sorted(anchors,key=lambda a:(center(a['box'])[0]-x)**2+(center(a['box'])[1]-y)**2)
        element=''; anchor_kind='unresolved'; item_level=lev
        if is_schedule:
            eligible=[a for a in schedule_anchors if a['box'][0]-10<=x]
            if eligible and y<max(center(a['box'])[1] for a in schedule_anchors):
                a=max(eligible,key=lambda a:a['box'][0])
                if x-a['box'][0]<w*.055:
                    element=a['text'].upper().replace('/','-').replace(' ','')
                    anchor_kind='schedule'
                    below=[v for yy,v in schedule_levels if yy>=y]
                    if below:item_level=below[0]
        if neighbours and not element:
            ax,ay=center(neighbours[0]['box'])
            if ((ax-x)**2+(ay-y)**2)**.5<max(70,min(w,h)*.05):
                element=neighbours[0]['text'].upper().replace('/','-').replace(' ','')
                anchor_kind='label'
        if not element and all(grids.values()):
            chosen=[]
            for values in grids.values():
                best=min(values,key=lambda a:abs((x if a[1]=='x' else y)-a[2]))
                chosen.append(best[0])
            element='-'.join(chosen); anchor_kind='grid'
        resolved=bool(element)
        if not element: element=f"Annotation {line_index+1}"
        roles=sorted({p['role'] for p in parsed if p['role']})
        phase='haut' if re.search(r'\bHAUT\b|\bTOP\b',line['text'],re.I) else ('bas' if re.search(r'\bBAS\b|\bBOTTOM\b',line['text'],re.I) else '')
        record_id=hashlib.sha256(f"{project_id}:{doc_info['id']}:{page_number}:{line_index}".encode()).hexdigest()[:20]
        info=Information(id=record_id,source=doc_info['role'],fichier=doc_info['relative'],feuillet=sheet,page=page_number,
                         x=max(0,x),y=max(0,y),type_element=typ,element=element,
                         armature=[Armature(**p['value']) for p in parsed])
        records.append({'information':info.model_dump(), 'doc_id':doc_info['id'],'box':line['box'],
                        'raw':line['text'],'normalized':parsed_text,'ocr_corrected':parsed_text!=line['text'],
                        'confidence':line['confidence'],'method':line['method'],
                        'level':item_level,'role':'|'.join(roles),'phase':phase,'anchor_kind':anchor_kind,
                        'identity_resolved':resolved,'multiplicities':[p['multiplicity'] for p in parsed],
                        'page_width':w,'page_height':h})
    return records,{'sheet':sheet,'family':typ,'level':lev,'annotations':len(records)}
