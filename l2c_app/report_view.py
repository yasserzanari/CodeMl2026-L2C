"""On-demand, source-linked per-sheet reports, isolated from source PDFs."""
from collections import Counter
from io import BytesIO
from hashlib import sha256
from functools import lru_cache
from xml.sax.saxutils import escape
import json
import zipfile
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from . import catalog

LABELS={'conforme':'Accord partiel','non_conforme':'Écart proposé','a_verifier':'À vérifier'}

def groups(run):
    records={r['information']['id']:r for r in run['records']}
    result={}
    for row in run['results']:
        sheets={records[i]['information']['feuillet'] for i in row['plan_ids']} or {'Atelier — non apparié'}
        for sheet in sheets:result.setdefault(sheet,[]).append(row)
    for page in run['pages']:
        if page['source']=='plan':result.setdefault(page.get('sheet') or page['file']+' p.'+str(page['page']),[])
    return {sha256(s.encode()).hexdigest()[:16]:(s,rows) for s,rows in sorted(result.items())}

def index(run):
    return {'run_id':run['id'],'project_name':run['project_name'],'created_at':run['created_at'],
            'statistics':run['statistics'],'sheets':[{'id':ident,'name':s,'total':len(rows),
            'counts':dict(Counter(r['status'] for r in rows)),
            'reviewed':sum(bool(r.get('review')) for r in rows)} for ident,(s,rows) in groups(run).items()]}

def make_pdf(run,sheet_id):
    group=groups(run).get(sheet_id)
    if not group:raise KeyError('Feuillet introuvable')
    name,rows=group
    ids={i for row in rows for i in row['plan_ids']+row['atelier_ids']}
    payload={'name':name,'rows':rows,'records':[r for r in run['records'] if r['information']['id'] in ids],
             'project':run['project_name'],'created':run['created_at'],'statistics':run['statistics']}
    return _render(json.dumps(payload,ensure_ascii=False,sort_keys=True))

@lru_cache(maxsize=12)
def _render(payload):
    data=json.loads(payload);styles=getSampleStyleSheet()
    styles['BodyText'].fontSize=8;styles['BodyText'].leading=11
    p=lambda text:Paragraph(escape(str(text)),styles['BodyText'])
    records={r['information']['id']:r for r in data['records']}
    story=[Paragraph('CONCORDE',styles['Title']),Paragraph(escape('Rapport de révision / '+data['name']),styles['Heading1']),
           p(data['project']+' · '+data['created']),p('Aide à la révision. Les accords partiels portent uniquement sur les valeurs lues. Les décisions humaines restent séparées des propositions automatiques.'),Spacer(1,12)]
    counts=Counter(r['status'] for r in data['rows'])
    story += [p(' · '.join(f'{v} {LABELS[k].lower()}' for k,v in counts.items())),Spacer(1,12)]
    for row in data['rows']:
        story += [Paragraph(escape(row['element']+' · '+LABELS[row['status']]),styles['Heading3']),p(row['reason'])]
        if row.get('review'):story.append(p('Révision humaine : '+row['review']['decision']+' · '+row['review'].get('note','')+' · '+row['review']['at']))
        for diff in row['differences']:story.append(p(f"{diff['field']} : plan {diff['plan']} / atelier {diff['atelier']}"))
        show_images=row['status']=='non_conforme' or bool(row.get('review'))
        cells=[]
        for side in ('plan','atelier'):
            content=[p('PLAN DE STRUCTURE' if side=='plan' else 'DESSIN D’ATELIER')]
            for ident in row[side+'_ids']:
                r=records[ident];i=r['information']
                content += [p(f"{i['fichier']} · p.{i['page']} · x {i['x']:.1f}, y {i['y']:.1f} pt"),p(r['raw'])]
                if show_images and ident==row[side+'_ids'][0]:
                    try:
                        img=Image(BytesIO(catalog.render(r['doc_id'],i['page'],r['box'],.8)))
                        scale=min(225/img.imageWidth,125/img.imageHeight)
                        img.drawWidth=img.imageWidth*scale;img.drawHeight=img.imageHeight*scale;content.append(img)
                    except (KeyError,ValueError,OSError):content.append(p('Aperçu indisponible ; consulter la source.'))
            if not row[side+'_ids']:content.append(p('Correspondance non établie.'))
            cells.append(content)
        # Very large unresolved groups remain linear so a single table cell cannot exceed a page.
        if any(len(row[s+'_ids'])>3 for s in ('plan','atelier')):
            for cell in cells:story.extend(cell)
        else:
            table=Table([cells],colWidths=[250,250]);table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOX',(0,0),(-1,-1),.4,colors.HexColor('#DCE4EB'))]));story.append(table)
        story.append(Spacer(1,8))
    if not data['rows']:story.append(p('Aucune observation extraite pour ce feuillet. Cela ne certifie pas sa conformité.'))
    s=data['statistics'];story.extend([Spacer(1,12),p(f"Couverture globale : {s['pages_processed']}/{s['pages_total']} pages lues ; {s['pages_error']} erreurs. Une page lue ne garantit pas une extraction exhaustive.")])
    output=BytesIO()
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.drawString(40,24,'Confidentiel · Traitement local');canvas.drawRightString(555,24,str(doc.page))
    SimpleDocTemplate(output,rightMargin=40,leftMargin=40,topMargin=36,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()

def archive(run,ids):
    known=groups(run)
    if any(i not in known for i in ids):raise KeyError('Feuillet introuvable')
    output=BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for ident in dict.fromkeys(ids):z.writestr('rapport-'+ident+'.pdf',make_pdf(run,ident))
        z.writestr('index.json',json.dumps([{'fichier':'rapport-'+i+'.pdf','feuillet':known[i][0]} for i in dict.fromkeys(ids)],ensure_ascii=False,indent=2))
    return output.getvalue()
