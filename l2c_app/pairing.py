"""Explainable retrieval for human review. Never changes an automatic verdict.

Reinforcement values must not participate in candidate retrieval or ordering.
Scores are evidence counts, not calibrated probabilities. Unknown levels remain unknown.
"""
import re
import unicodedata

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

def candidates(plan,records,limit=8):
    info=plan['information']
    if info['source']!='plan' or not plan.get('identity_resolved') or info['type_element']=='inconnu':return []
    key=element_key(info['element']); result=[]
    for other in records:
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
    return result[:limit]

def candidate_differences(plan,atelier):
    """Comparison is explicitly downstream of identity retrieval; no engineering tolerance inferred."""
    a,b=plan['information']['armature'],atelier['information']['armature']
    if len(a)!=1 or len(b)!=1:return []
    result=[]
    for field in ('diametre','quantite','espacement_mm','longueur_mm'):
        x,y=a[0].get(field),b[0].get(field)
        if x is None or y is None:continue
        same=abs(x-y)<1e-6 if isinstance(x,(int,float)) and isinstance(y,(int,float)) else x==y
        if not same:result.append({'field':field,'plan':x,'atelier':y})
    return result
