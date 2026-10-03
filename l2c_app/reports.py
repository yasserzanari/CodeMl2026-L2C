"""Local, paginated PDF review report with a section per plan sheet."""
from xml.sax.saxutils import escape
from collections import defaultdict,Counter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from .config import write_json

def export(run,folder):
    write_json(folder/'informations.json',[r['information'] for r in run['records']])
    write_json(folder/'comparaisons.json',{'scope':run['scope'],'statistics':run['statistics'],'pages':run['pages'],'results':run['results']})
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallFrench',fontName='Helvetica',fontSize=8,leading=12,spaceAfter=6))
    styles['Title'].textColor=colors.HexColor('#152734')
    p=lambda s:Paragraph(escape(str(s)),styles['SmallFrench'])
    stats=run['statistics']; story=[]
    story+=[Paragraph('CONCORDE',styles['Title']),Paragraph('Rapport de conciliation · '+escape(run['project_name']),styles['Heading1']),
            p('Analyse '+run['id']+' · '+run['created_at']),
            p('Périmètre : '+run['scope']+'. Ce rapport présente une aide à la révision. Les accords portent uniquement sur les attributs extraits et comparés.'),
            p(f"{stats['annotations']} annotations · {stats['pages_processed']}/{stats['pages_total']} pages traitées · {stats['pages_ocr']} pages OCR · {stats['pages_error']} erreurs."),
            p('Correspondances : '+str(stats['counts'])),
            p('Les scores OCR ne constituent pas une probabilité de conformité. Les absences/ajouts ne sont pas déduits automatiquement des éléments non appariés. Toutes les zones non lues restent à examiner.')]
    records={r['information']['id']:r for r in run['records']}
    grouped=defaultdict(list)
    for result in run['results']:
        sheets={records[i]['information']['feuillet'] for i in result['plan_ids']} or {'Atelier : annotations non appariées'}
        for sheet in sheets: grouped[sheet].append(result)
    for page in run['pages']:
        if page['source']=='plan': grouped.setdefault(page.get('sheet',page['file']+' p.'+str(page['page'])),[])
    story.append(Paragraph('Synthèse par feuillet',styles['Heading2']))
    data=[[p('Feuillet'),p('Accords partiels'),p('Écarts candidats'),p('À vérifier')]]
    for sheet,items in grouped.items():
        counts=Counter(r['status'] for r in items)
        data.append([p(sheet),p(counts['conforme']),p(counts['non_conforme']),p(counts['a_verifier'])])
    table=Table(data,colWidths=[240,75,75,75],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf1ff')),
                              ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#dce4eb'))]))
    story.append(table)
    for sheet,results in grouped.items():
        counts=Counter(r['status'] for r in results)
        story+=[PageBreak(),Paragraph(escape(sheet),styles['Heading1']),
                p(f"{counts['conforme']} accords partiels · {counts['non_conforme']} écarts candidats · {counts['a_verifier']} observations à vérifier")]
        for result in results:
            if result['status']=='a_verifier':continue
            story+=[Paragraph(escape(result['element']+' · '+result['status'].replace('_',' ')),styles['Heading3']),p(result['reason'])]
            if result.get('review'): story.append(p('Révision humaine : '+str(result['review'])))
            for side in ('plan','atelier'):
                for ident in result[side+'_ids']:
                    r=records[ident]; info=r['information']
                    story.append(p(f"{side.upper()} — {info['fichier']} · page {info['page']} · {info['feuillet']} · x={info['x']:.1f}, y={info['y']:.1f} pt"))
                    story.append(p(r['raw']))
                    story.append(p(' | '.join(str(a) for a in info['armature'])))
            for diff in result['differences']: story.append(p(f"Écart {diff['field']} : plan {diff['plan']} / atelier {diff['atelier']}"))
            story.append(Spacer(1,8))
        pending=[r for r in results if r['status']=='a_verifier']
        if pending:
            story+=[Paragraph('Annotations en attente de révision',styles['Heading2']),
                    p('Le détail exhaustif et les coordonnées figurent dans informations.json et comparaisons.json. Les extraits sont consultables dans le tableau de bord.')]
            for result in pending:
                sources=[]
                for side in ('plan','atelier'):
                    ids=result[side+'_ids']
                    if ids:
                        first=records[ids[0]]['information']
                        sources.append(f"{side} p.{first['page']} ({len(ids)} annotations)")
                story.append(p(result['id']+' · '+result['element']+' · '+' / '.join(sources)))
    story+=[PageBreak(),Paragraph('Couverture et traçabilité',styles['Heading1'])]
    for page in run['pages']:
        story.append(p(f"{page['file']} · p.{page['page']} · {page['method']} · {page.get('annotations',0)} annotations · {page.get('warning','')}"))
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#596b7a'))
        canvas.drawString(40,25,'Confidentiel · Traitement local · L2C / Concorde')
        canvas.drawRightString(A4[0]-40,25,str(doc.page))
    SimpleDocTemplate(str(folder/'rapport.pdf'),pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=42,
                      title='Concorde — '+run['project_name']).build(story,onFirstPage=footer,onLaterPages=footer)
