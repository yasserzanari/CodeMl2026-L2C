"""Conservative baseline: resolve identity before checking reinforcement values."""
from collections import defaultdict, Counter
import hashlib

FIELDS=('diametre','quantite','espacement_mm','longueur_mm')

def compare_armatures(a,b):
    """Compare unique bar marks after element identity; never match by bar values."""
    av,bv=a['information']['armature'],b['information']['armature']
    if not av or not bv or any(n!=1 for n in a.get('multiplicities',[])+b.get('multiplicities',[])):
        return [],[], 'Groupe de fabrication ou armatures absentes : contrôle des quantités requis.'
    if len(av)==len(bv)==1:
        pairs=[(None,av[0],bv[0])]
    else:
        def indexed(bars):
            result={}
            for bar in bars:
                key=(bar.get('repere') or '').strip().upper()
                if not key or key in result:return None
                result[key]=bar
            return result
        left,right=indexed(av),indexed(bv)
        if not left or not right or left.keys()!=right.keys():
            return [],[], 'Plusieurs armatures sans repères uniques communs : association manuelle requise.'
        pairs=[(key,left[key],right[key]) for key in sorted(left)]
    diffs=[];common=[]
    for mark,left,right in pairs:
        shared=[]
        for field in FIELDS:
            x,y=left.get(field),right.get(field)
            if x is None or y is None:continue
            shared.append(field)
            same=abs(x-y)<1e-6 if field.endswith('_mm') else x==y
            if not same:
                diff={'field':field,'plan':x,'atelier':y}
                if mark:diff['repere']=mark
                diffs.append(diff)
        common.append(shared)
    return diffs,common,''

def _observation_signature(record):
    """Return comparable values for deciding whether separate shop files agree."""
    info=record['information']
    bars=tuple(sorted((tuple(bar.get(field) for field in FIELDS)+(bar.get('repere'),)
                       for bar in info.get('armature',[])), key=repr))
    return (info['type_element'], info['element'], record.get('level',''),
            record.get('role',''), record.get('phase',''), bars,
            tuple(record.get('multiplicities',[])))

def _consensus_copy(records):
    """Collapse only identical observations repeated in distinct shop documents.

    All original rows are retained as evidence in the emitted result. Conflicting
    values, repeated rows within one source document, or missing provenance abstain.
    """
    if len(records)<2 or any(not row.get('doc_id') for row in records):return None
    if len({row['doc_id'] for row in records})!=len(records):return None
    signatures={_observation_signature(row) for row in records}
    return records[0] if len(signatures)==1 else None

def reconcile(records):
    from .pairing import element_key,level_key
    groups=defaultdict(lambda:{'plan':[],'atelier':[]})
    unresolved=[]
    for record in records:
        info=record['information']
        # Grid and table positions produce review candidates, never certified conclusions.
        if not record['identity_resolved'] or not record['level'] or info['type_element']=='inconnu':
            unresolved.append(record); continue
        key=(info['type_element'],element_key(info['element']),level_key(record['level']),record['role'],record['phase'])
        groups[key][info['source']].append(record)
    results=[]
    def add(left,right,status,reason,differences=None):
        ids=[r['information']['id'] for r in left+right]
        ident=hashlib.sha256('|'.join(sorted(ids)).encode()).hexdigest()[:20]
        first=(left+right)[0]['information']
        results.append({'id':ident,'status':status,'reason':reason,'differences':differences or [],
                        'plan_ids':[r['information']['id'] for r in left],
                        'atelier_ids':[r['information']['id'] for r in right],
                        'element':first['element'],'family':first['type_element'],'sheet':first['feuillet'],
                        'review':None})
    for pair in groups.values():
        left,right=pair['plan'],pair['atelier']
        if len(left)!=1:
            add(left,right,'a_verifier','Correspondance ambiguë ou contrepartie non retrouvée. Présence/absence non établie.'); continue
        a=left[0]
        if len(right)==1:
            b=right[0]
        elif right and _consensus_copy(right):
            # Multiple independent shop PDFs can repeat one identical schedule row.
            # Compare the shared value evidence, but keep every source ID in the result.
            b=_consensus_copy(right)
        else:
            add(left,right,'a_verifier','Plusieurs candidats atelier avec valeurs ou provenance distinctes.'); continue
        diffs,common,blocked=compare_armatures(a,b)
        if blocked:
            add(left,right,'a_verifier',blocked); continue
        if min(a['confidence'],b['confidence'])<.8 or a.get('ocr_corrected') or b.get('ocr_corrected'):
            add(left,right,'a_verifier','Lecture OCR incertaine : vérifier les deux extraits.'); continue
        if diffs:
            reason=('Écart candidat sur une identité commune ; validation humaine nécessaire.'
                    if len(right)==1 else 'Écart commun à des copies atelier identiques ; validation humaine nécessaire.')
            add(left,right,'non_conforme',reason,diffs)
        elif common and all('diametre' in fields and ('quantite' in fields or 'espacement_mm' in fields) for fields in common):
            add(left,right,'conforme','Accord sur les attributs lisibles comparés. Les attributs absents restent non vérifiés.')
        else:
            add(left,right,'a_verifier','Attributs communs insuffisants pour conclure.')
    for r in unresolved:
        add([r] if r['information']['source']=='plan' else [],[r] if r['information']['source']=='atelier' else [],
            'a_verifier','Annotation extraite ; emplacement, niveau ou correspondance à confirmer.')
    order={'non_conforme':0,'a_verifier':1,'conforme':2}
    return sorted(results,key=lambda x:(order[x['status']],x['sheet'],x['element']))

def statistics(records,results,pages):
    counts=Counter(r['status'] for r in results)
    return {'annotations':len(records),'comparisons':len(results),'counts':dict(counts),
            'pages_processed':sum(p['method'] not in ('skipped','error') for p in pages),
            'pages_ocr':sum(p['method']=='ocr' for p in pages),'pages_total':len(pages),
            'pages_skipped':sum(p['method']=='skipped' for p in pages),'pages_error':sum(p['method']=='error' for p in pages),
            'families':dict(Counter(r['information']['type_element'] for r in records))}
