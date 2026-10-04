"""Human-only presence adjudication. OCR coverage never proves absence."""
from collections import Counter
from . import catalog

LABELS = {'manquant_dans_atelier': 'Manquant dans l’atelier (confirmé humainement)',
          'ajoute_dans_atelier': 'Ajouté dans l’atelier (confirmé humainement)'}


def requirements(run, row):
    source = 'plan' if row['plan_ids'] and not row['atelier_ids'] else (
        'atelier' if row['atelier_ids'] and not row['plan_ids'] else '')
    opposite = 'atelier' if source == 'plan' else 'plan'
    project = catalog.project(run.get('project_id'))
    docs = [catalog.document(i) for i in project['documents']] if project else []
    docs = [d for d in docs if d]
    targets = [{'id':d['id'], 'name':d['relative'], 'pages':d['pages']} for d in docs if d['role']==opposite]
    reason = ''
    if not source:
        reason = 'La décision nécessite une observation avec une seule source.'
    elif run.get('scope') != 'complete':
        reason = 'Une analyse complète du projet est nécessaire.'
    elif not docs or not targets:
        reason = 'Inventaire des documents sources indisponible.'
    else:
        expected = {(d['id'], p) for d in docs for p in range(1, d['pages']+1)}
        actual = Counter((p.get('doc_id'), p.get('page')) for p in run['pages'])
        lookup = {d['id']:d for d in docs}
        if set(actual)!=expected or any(n!=1 for n in actual.values()):
            reason = 'La couverture des pages ne correspond pas à l’inventaire complet.'
        elif any(p.get('method') not in ('pdf','native','ocr') for p in run['pages']):
            reason = 'Des pages restent ignorées, en erreur ou non vérifiées.'
        elif any(p.get('source_sha256') != lookup[p['doc_id']]['sha256'] for p in run['pages']):
            reason = 'Les empreintes sources ne sont pas vérifiées ; relancer l’analyse complète.'
    return {'eligible':not reason,'reason':reason,'source':source,'opposite_documents':targets,
            'expected_outcome':'manquant_dans_atelier' if source=='plan' else 'ajoute_dans_atelier' if source else None}


def validate(run, row, value):
    if not value['adjudicator'].strip() or not value['note'].strip():
        raise ValueError('Le nom du réviseur et une justification sont obligatoires.')
    if value['outcome']=='unresolved':
        return requirements(run,row)
    needed = requirements(run,row)
    if not needed['eligible']:raise ValueError(needed['reason'])
    if value['outcome']!=needed['expected_outcome']:
        raise ValueError('La catégorie ne correspond pas à la source de cette observation.')
    if not value['source_identity_verified']:
        raise ValueError('Confirmez l’identité et les annotations dans la source originale.')
    if set(value['checked_doc_ids'])!={d['id'] for d in needed['opposite_documents']}:
        raise ValueError('Vérifiez tous les documents de la source opposée et leurs pages.')
    return needed


def counts(rows):
    return dict(Counter(r['presence_review']['outcome'] for r in rows
                        if (r.get('presence_review') or {}).get('outcome') in LABELS))
