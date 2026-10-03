"""Conservative baseline: resolve identity before checking reinforcement values."""
from collections import defaultdict, Counter
import hashlib

FIELDS=('diametre','quantite','espacement_mm','longueur_mm')

def reconcile(records):
    groups=defaultdict(lambda:{'plan':[],'atelier':[]})
    unresolved=[]
    for record in records:
        info=record['information']
        # Grid and table positions produce review candidates, never certified conclusions.
        if not record['identity_resolved'] or not record['level'] or info['type_element']=='inconnu':
            unresolved.append(record); continue
        key=(info['type_element'],info['element'],record['level'],record['role'],record['phase'])
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
        if len(left)!=1 or len(right)!=1:
            add(left,right,'a_verifier','Correspondance ambiguë ou contrepartie non retrouvée. Présence/absence non établie.'); continue
        a,b=left[0],right[0]
        av,bv=a['information']['armature'],b['information']['armature']
        if len(av)!=1 or len(bv)!=1 or any(n!=1 for n in a['multiplicities']+b['multiplicities']):
            add(left,right,'a_verifier','Plusieurs armatures ou groupe de fabrication : association manuelle requise.'); continue
        if min(a['confidence'],b['confidence'])<.8 or a.get('ocr_corrected') or b.get('ocr_corrected'):
            add(left,right,'a_verifier','Lecture OCR incertaine : vérifier les deux extraits.'); continue
        diffs=[]; common=[]
        for field in FIELDS:
            x,y=av[0][field],bv[0][field]
            if x is None or y is None: continue
            common.append(field)
            equal=abs(x-y)<=.5 if isinstance(x,(int,float)) and field.endswith('_mm') else x==y
            if not equal: diffs.append({'field':field,'plan':x,'atelier':y})
        if diffs:
            add(left,right,'non_conforme','Écart candidat sur une identité commune ; validation humaine nécessaire.',diffs)
        elif 'diametre' in common and ('quantite' in common or 'espacement_mm' in common):
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
