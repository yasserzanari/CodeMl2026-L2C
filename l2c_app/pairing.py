"""Explainable retrieval for human review. Never changes an automatic verdict.

Reinforcement values must not participate in candidate retrieval or ordering.
Scores are evidence counts, not calibrated probabilities. Unknown levels remain unknown.
"""
import re
import unicodedata
from collections import defaultdict

def candidate_index(records):
    """Index identities only; reinforcement values never affect retrieval."""
    index=defaultdict(list)
    for record in records:
        info=record['information']
        if info['source']=='atelier' and record.get('identity_resolved'):
            index[(info['type_element'],element_key(info['element']))].append(record)
    return index

def element_key(value):
    text=unicodedata.normalize('NFKC',value).strip().upper()
    text=re.sub('[–—−]','-',text)
    match=re.fullmatch(r'([A-Z]+(?:\.\d+)?)\s*[-/ ]?\s*(\d+(?:\.\d+)?)',text)
    return '-'.join(match.groups()) if match else text

def level_key(value):
    text=unicodedata.normalize('NFKC',value).strip().upper()
    match=re.fullmatch(r'(?:N|NIV\.?|NIVEAU)\s*[-:]?\s*(\d+)',text)
    if match:return 'N'+str(int(match.group(1)))
    return 'RDC' if text in ('RDC','REZ-DE-CHAUSSÉE','REZ-DE-CHAUSSEE') else text

def candidates(plan,records,limit=8,index=None):
    info=plan['information']
    if info['source']!='plan' or not plan.get('identity_resolved') or info['type_element']=='inconnu':return []
    key=element_key(info['element']); result=[]
    pool=index.get((info['type_element'],key),[]) if index is not None else records
    for other in pool:
        item=other['information']
        if item['source']!='atelier' or not other.get('identity_resolved'):continue
        if item['type_element']!=info['type_element'] or element_key(item['element'])!=key:continue
        evidence=['Même famille','Même repère normalisé'];warnings=[]
        rejected=False
        for field,title,normalize in [('level','Niveau',level_key),('role','Rôle',str),('phase','Position haut/bas',str)]:
            a,b=normalize(plan.get(field,'')),normalize(other.get(field,''))
            if a and b and a!=b:rejected=True;break
            if a and b and '|' not in a:evidence.append(title+' identique')
            else:warnings.append(title+' incomplet ou multiple')
        if rejected:continue
        for side,row in [('plan',plan),('atelier',other)]:
            if row.get('anchor_kind') in ('grid','unresolved',None):warnings.append('Identité '+side+' issue d’une heuristique')
            if row.get('confidence',0)<.8 or row.get('ocr_corrected'):warnings.append('Lecture '+side+' incertaine')
        result.append({'record_id':item['id'],'evidence':evidence,'warnings':warnings,
                       'source_file':item['fichier'],'page':item['page'],'record':other})
    # Tie breaking is deterministic and independent of diameter, quantity, spacing and length.
    result.sort(key=lambda c:(len(c['warnings']),-len(c['evidence']),c['source_file'],c['page'],c['record_id']))
    if len(result)>1:
        for row in result:row['warnings'].append('Plusieurs candidats : aucune sélection automatique')
    return result if limit is None else result[:limit]

def review_queue(run):
    """Coverage and navigation for human review, never accuracy or new verdicts."""
    records=run['records'];index=candidate_index(records)
    observations={pid:row['id'] for row in run['results'] for pid in row['plan_ids']}
    items=[];plans=0;missing_level=0;unresolved=0
    for plan in records:
        info=plan['information']
        if info['source']!='plan':continue
        plans+=1;missing_level+=not bool(plan.get('level'));unresolved+=not bool(plan.get('identity_resolved'))
        found=candidates(plan,records,limit=None,index=index)
        if not found:continue
        items.append({'plan_id':info['id'],'result_id':observations.get(info['id']),
                      'element':info['element'],'sheet':info['feuillet'],'family':info['type_element'],
                      'page':info['page'],'raw':plan.get('raw',''),
                      'context':' · '.join(str(plan.get(k,'')) for k in ('level','role','phase') if plan.get(k)),
                      'candidate_count':len(found)})
    items.sort(key=lambda row:(row['candidate_count']!=1,row['sheet'],row['element'],row['plan_id']))
    return {'plans':plans,'with_candidates':len(items),'without_candidates':plans-len(items),
            'multiple_candidates':sum(row['candidate_count']>1 for row in items),
            'missing_level':missing_level,'unresolved_identity':unresolved,'items':items}

def candidate_differences(plan,atelier):
    """Comparison is explicitly downstream of identity retrieval; no engineering tolerance inferred."""
    from .matching import compare_armatures
    return compare_armatures(plan,atelier)[0]
