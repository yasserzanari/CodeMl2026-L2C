"""Local PDF review report; machine candidates and human decisions stay separate."""
from collections import Counter, defaultdict
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .config import write_json
from .presence import LABELS as PRESENCE_LABELS,counts as presence_counts


MACHINE_LABELS = {
    'conforme': 'accord partiel',
    'non_conforme': 'écart candidat',
    'a_verifier': 'à vérifier',
}
REVIEW_LABELS = {'confirme': 'confirmée', 'rejete': 'rejetée', 'a_verifier': 'à reprendre'}


def export(run, folder):
    """Write JSON exports and a compact report without inferring absence or approval."""
    records_list = run.get('records') or []
    results = run.get('results') or []
    pages = run.get('pages') or []
    stats = run.get('statistics') or {}
    records = {}
    for record in records_list:
        info = record.get('information') or {}
        ident = info.get('id')
        if ident is not None:
            records[ident] = record

    write_json(folder / 'informations.json', [r.get('information', {}) for r in records_list])
    write_json(folder / 'comparaisons.json', {
        'scope': run.get('scope', 'inconnu'), 'statistics': stats,
        'pages': pages, 'results': results,
    })

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallFrench', fontName='Helvetica', fontSize=7.5,
                              leading=10, spaceAfter=4, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='TableFrench', parent=styles['SmallFrench'], fontSize=6.8,
                              leading=8))
    styles['Title'].textColor = colors.HexColor('#152734')

    def para(value, style='SmallFrench'):
        return Paragraph(escape(str(value if value not in (None, '') else '—')), styles[style])

    def status_of_page(page):
        method = page.get('method')
        if method == 'error':
            return 'échec'
        if method == 'skipped':
            return 'ignorée'
        if method in (None, ''):
            return 'inconnue'
        return 'traitée'

    # Each plan sheet is represented even if extraction produced no record or result.
    by_sheet = defaultdict(list)
    sheet_pages = defaultdict(list)
    for page in pages:
        if page.get('source') != 'plan':
            continue
        sheet = page.get('sheet') or f"{page.get('file', 'Plan')} · p.{page.get('page', '?')}"
        sheet_pages[sheet].append(page)
        by_sheet.setdefault(sheet, [])

    for result in results:
        plan_ids = result.get('plan_ids') or []
        result_sheets = {
            (records.get(ident, {}).get('information') or {}).get('feuillet')
            for ident in plan_ids if ident in records
        }
        result_sheets.discard(None)
        if result_sheets:
            for sheet in result_sheets:
                by_sheet[sheet].append(result)
        else:
            by_sheet['Atelier · sans plan associé'].append(result)

    machine_totals = Counter(r.get('status', 'inconnu') for r in results)
    reviews = Counter((r.get('review') or {}).get('decision', 'non examinée') for r in results)
    reviewed_count = sum(v for k, v in reviews.items() if k in REVIEW_LABELS)
    source_pages = defaultdict(set)
    source_files = defaultdict(set)
    for page in pages:
        role = page.get('source') or 'source inconnue'
        source_files[role].add(page.get('file') or 'fichier inconnu')
        if page.get('page') is not None:
            source_pages[role].add((page.get('file'), page.get('page')))
    for record in records_list:
        info = record.get('information') or {}
        role = info.get('source') or 'source inconnue'
        source_files[role].add(info.get('fichier') or 'fichier inconnu')

    story = [
        Paragraph('CONCORDE', styles['Title']),
        Paragraph('Rapport de conciliation · ' + escape(str(run.get('project_name', 'Projet'))), styles['Heading1']),
        para(f"Analyse {run.get('id', 'inconnue')} · {run.get('created_at', 'date inconnue')}"),
        para(f"Périmètre demandé : {run.get('scope', 'inconnu')}. Ce document est une aide à la révision des attributs extraits et comparés."),
        para(f"Pages : {stats.get('pages_processed', '—')}/{stats.get('pages_total', len(pages))} traitées · "
             f"{stats.get('pages_ocr', '—')} OCR · {stats.get('pages_skipped', '—')} ignorées · "
             f"{stats.get('pages_error', '—')} erreurs. Annotations extraites : {stats.get('annotations', len(records_list))}."),
        Paragraph('Résultats machine (propositions)', styles['Heading2']),
        para(' · '.join(f"{machine_totals.get(key, 0)} {label}" for key, label in MACHINE_LABELS.items())
             + f" · {machine_totals.get('inconnu', 0)} statut inconnu"),
        Paragraph('Décisions humaines enregistrées', styles['Heading2']),
        para(f"{reviewed_count}/{len(results)} observations examinées · "
             + ' · '.join(f"{reviews.get(key, 0)} {label}" for key, label in REVIEW_LABELS.items())
             + f" · {reviews.get('non examinée', 0)} non examinées"),
        para('Présence, décisions humaines : '+' · '.join(f'{presence_counts(results).get(k,0)} {label}' for k,label in PRESENCE_LABELS.items())),
        para('Les catégories « manquant dans l’atelier » et « ajouté dans l’atelier » nécessitent une décision humaine documentée sur un périmètre complet. Un élément non apparié, une page vide ou une lecture incomplète ne prouve pas une absence. Les décisions de présence restent séparées des propositions machine.'),
        para('Un « accord partiel » porte uniquement sur les attributs lisibles comparés. Il ne constitue pas une approbation technique, une vérification exhaustive ni une certification.'),
        Paragraph('Sources et sorties', styles['Heading2']),
    ]
    for role in ('plan', 'atelier'):
        n_pages = len(source_pages.get(role, set()))
        files = sorted(source_files.get(role, set()))
        story.append(para(f"{role.capitalize()} : {len(files)} fichier(s), {n_pages} page(s) parcourue(s) · "
                          + (', '.join(files) if files else 'source non identifiée')))
    story.append(para('Sorties : rapport.pdf · informations.json · comparaisons.json. Les détails et coordonnées des annotations sont conservés dans les exports JSON.'))

    story.append(Paragraph('Couverture par feuillet de plan', styles['Heading2']))
    data = [[para(x, 'TableFrench') for x in (
        'Feuillet', 'Pages / état', 'Accord partiel', 'Écart candidat', 'À vérifier', 'Revue humaine')]]
    sheet_names = list(by_sheet)
    if not sheet_names:
        data.append([para('Aucun feuillet de plan identifié', 'TableFrench')] + [para('inconnue', 'TableFrench') for _ in range(5)])
    for sheet in sheet_names:
        items = by_sheet[sheet]
        counts = Counter(r.get('status', 'inconnu') for r in items)
        decision_counts = Counter((r.get('review') or {}).get('decision', 'non examinée') for r in items)
        spages = sheet_pages.get(sheet, [])
        if not spages:
            coverage = 'inconnue'
        else:
            coverage = f"{sum(status_of_page(x) == 'traitée' for x in spages)}/{len(spages)} traitées"
            failures = sum(status_of_page(x) == 'échec' for x in spages)
            skipped = sum(status_of_page(x) == 'ignorée' for x in spages)
            unknown = sum(status_of_page(x) == 'inconnue' for x in spages)
            flags = [f'{failures} échec(s)' if failures else '', f'{skipped} ignorée(s)' if skipped else '',
                     f'{unknown} état(s) inconnu(s)' if unknown else '']
            if any(flags):
                coverage += ' · ' + ', '.join(x for x in flags if x)
        human = f"{sum(decision_counts[k] for k in REVIEW_LABELS)}/{len(items)} examinées"
        data.append([para(sheet, 'TableFrench'), para(coverage, 'TableFrench'),
                     para(counts.get('conforme', 0), 'TableFrench'),
                     para(counts.get('non_conforme', 0), 'TableFrench'),
                     para(counts.get('a_verifier', 0), 'TableFrench'), para(human, 'TableFrench')])
    table = Table(data, colWidths=[92, 112, 62, 62, 54, 78], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf1ff')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#dce4eb')),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.extend([table, para('Les compteurs de résultat portent sur les propositions rattachées au feuillet, pas sur une population complète d’éléments. Une ligne sans résultat ou sans page reconnue indique une preuve insuffisante, jamais zéro anomalie.'),
                  Paragraph('Observations par feuillet', styles['Heading2'])])

    for sheet, items in by_sheet.items():
        story.extend([PageBreak(), Paragraph(escape(str(sheet)), styles['Heading1'])])
        counts = Counter(r.get('status', 'inconnu') for r in items)
        story.append(para(' · '.join(f"{counts.get(key, 0)} {label}" for key, label in MACHINE_LABELS.items())))
        story.append(para('Présence, décisions humaines : '+' · '.join(f'{presence_counts(items).get(k,0)} {label}' for k,label in PRESENCE_LABELS.items())))
        for result in items:
            status = result.get('status', 'inconnu')
            presence=result.get('presence_review') or {}
            if status == 'a_verifier' and not presence:
                continue
            story.extend([Paragraph(escape(f"{result.get('element', 'Élément')} · {MACHINE_LABELS.get(status, status)}"), styles['Heading3']),
                          para(result.get('reason', 'Motif non renseigné.'))])
            if presence:
                story.append(para(PRESENCE_LABELS.get(presence['outcome'],'Conclusion de présence retirée / à vérifier')+' · '+presence['adjudicator']+' · '+presence['at']+' · '+presence['note']))
                story.append(para('Documents vérifiés : '+', '.join(d['name'] for d in presence.get('checked_documents',[]))))
            review = result.get('review') or {}
            if review:
                story.append(para(f"Décision humaine : {REVIEW_LABELS.get(review.get('decision'), review.get('decision', 'inconnue'))}"
                                  + (f" · {review.get('note')}" if review.get('note') else '')))
            for side in ('plan', 'atelier'):
                for ident in result.get(side + '_ids') or []:
                    record = records.get(ident)
                    if not record:
                        story.append(para(f"{side.upper()} · source introuvable dans les données exportées ({ident})"))
                        continue
                    info = record.get('information') or {}
                    story.append(para(f"{side.upper()} — {info.get('fichier', 'fichier inconnu')} · page {info.get('page', '?')} · "
                                       f"{info.get('feuillet', 'feuillet inconnu')} · x={info.get('x', '?')}, y={info.get('y', '?')} pt"))
                    if record.get('raw'):
                        story.append(para(record['raw']))
                    bars = info.get('armature') or []
                    if bars:
                        story.append(para(' | '.join(str(a) for a in bars)))
            for diff in result.get('differences') or []:
                story.append(para(f"Écart candidat {diff.get('repere','')} {diff.get('field', '?')} : plan {diff.get('plan', '?')} / atelier {diff.get('atelier', '?')}"))
            story.append(Spacer(1, 5))
        pending = [r for r in items if r.get('status') == 'a_verifier']
        if pending:
            story.extend([Paragraph('Observations à vérifier', styles['Heading2']),
                          para(f"{len(pending)} observation(s). Détail exhaustif, motifs et coordonnées : comparaisons.json et tableau de bord. Les éventuelles décisions humaines sont comptées séparément ci-dessus.")])
        spages = sheet_pages.get(sheet, [])
        if spages:
            story.append(Paragraph('Traitement des pages sources', styles['Heading2']))
            for page in spages:
                story.append(para(f"{page.get('file', 'Fichier inconnu')} · p.{page.get('page', '?')} · "
                                  f"{page.get('method', 'méthode inconnue')} · {page.get('annotations', '—')} annotation(s) · "
                                  f"{page.get('warning') or 'aucun avertissement consigné'}"))

    story.extend([PageBreak(), Paragraph('Couverture et traçabilité', styles['Heading1'])])
    if not pages:
        story.append(para('Aucune page de source consignée : la couverture est inconnue.'))
    for page in pages:
        story.append(para(f"{page.get('source', 'source inconnue')} · {page.get('file', 'fichier inconnu')} · "
                          f"p.{page.get('page', '?')} · {page.get('method', 'méthode inconnue')} · "
                          f"{page.get('annotations', '—')} annotation(s) · {page.get('warning') or 'aucun avertissement consigné'}"))

    def footer(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#596b7a'))
        canvas.drawString(40, 25, 'Confidentiel · Traitement local · L2C / Concorde')
        canvas.drawRightString(A4[0] - 40, 25, str(doc.page))

    SimpleDocTemplate(str(folder / 'rapport.pdf'), pagesize=A4, rightMargin=40, leftMargin=40,
                      topMargin=40, bottomMargin=42,
                      title='Concorde — ' + str(run.get('project_name', 'Projet'))).build(
                          story, onFirstPage=footer, onLaterPages=footer)
