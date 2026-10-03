from copy import deepcopy
import pytest
from l2c_app.pairing import element_key,level_key,candidates,candidate_differences
from test_pipeline import record

@pytest.mark.parametrize('value,key',[('C12','C-12'),('C / 12','C-12'),('K.1–6.2','K.1-6.2'),('C1-2','C1-2')])
def test_element_normalization(value,key):assert element_key(value)==key

@pytest.mark.parametrize('value,key',[('NIVEAU 02','N2'),('NIV. 3','N3'),('N2|N3','N2|N3'),('','')])
def test_level_normalization(value,key):assert level_key(value)==key

def test_alias_candidate_keeps_verdict_external():
    a,b=record('plan'),record('atelier');b['information']['element']='C/99';b['level']='NIVEAU 01'
    assert candidates(a,[b])[0]['record_id']=='atelier'

def test_values_do_not_choose_identity():
    a,b=record('plan'),record('atelier');c=deepcopy(b);c['information']['id']='another'
    before=[x['record_id'] for x in candidates(a,[b,c])]
    b['information']['armature'][0].update(diametre='55M',quantite=999)
    after=[x['record_id'] for x in candidates(a,[b,c])]
    assert before==after
    assert all('Plusieurs candidats' in ' '.join(x['warnings']) for x in candidates(a,[b,c]))

@pytest.mark.parametrize('field,value',[('level','N9'),('role','etr'),('phase','haut')])
def test_explicit_conflicts_reject(field,value):
    a,b=record('plan'),record('atelier');a[field]='N1' if field=='level' else 'vert' if field=='role' else 'bas';b[field]=value
    assert candidates(a,[b])==[]

def test_missing_context_is_warning():
    a,b=record('plan'),record('atelier');b['level']=''
    assert any('Niveau incomplet' in x for x in candidates(a,[b])[0]['warnings'])

def test_decimal_axes_stay_distinct():
    a,b=record('plan'),record('atelier');a['information']['element']='A.1-2';b['information']['element']='A-1.2'
    assert candidates(a,[b])==[]

def test_differences_follow_retrieval():
    a,b=record('plan'),record('atelier','8-25M')
    assert {d['field'] for d in candidate_differences(a,b)}=={'diametre','quantite'}
