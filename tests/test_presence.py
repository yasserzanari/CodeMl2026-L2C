from copy import deepcopy
import json
import pytest
import pymupdf as fitz
from l2c_app import presence,service
from l2c_app.matching import reconcile,statistics
from l2c_app.reports import export
from test_pipeline import record


@pytest.fixture
def evidence(monkeypatch):
    docs=[dict(id=s,relative=s+'.pdf',pages=1,role=s,sha256=s) for s in ('plan','atelier')]
    monkeypatch.setattr(presence.catalog,'project',lambda _: {'documents':['plan','atelier']})
    monkeypatch.setattr(presence.catalog,'document',lambda i:next(d for d in docs if d['id']==i))
    records=[record('plan')]
    pages=[dict(doc_id=s,page=1,method='pdf',source=s,source_sha256=s,file=s+'.pdf',sheet='S-999') for s in ('plan','atelier')]
    rows=reconcile(records)
    run=dict(id='test',project_id='test',project_name='Test',created_at='2026',scope='complete',records=records,pages=pages,results=rows,statistics=statistics(records,rows,pages))
    value=dict(outcome='manquant_dans_atelier',adjudicator='Synthetic reviewer',note='Synthetic evidence only',checked_doc_ids=['atelier'],source_identity_verified=True)
    return run,rows[0],value


def test_presence_requires_human_evidence(evidence):
    run,row,value=evidence
    assert presence.requirements(run,row)['eligible']
    presence.validate(run,row,value)
    for changes in [dict(checked_doc_ids=[]),dict(source_identity_verified=False),dict(note=' '),dict(outcome='ajoute_dans_atelier')]:
        with pytest.raises(ValueError):presence.validate(run,row,value|changes)


@pytest.mark.parametrize('mutation',['scope','skipped','duplicate','missing','fingerprint'])
def test_incomplete_evidence_blocks_presence(evidence,mutation):
    run,row,value=evidence
    if mutation=='scope':run['scope']='sample'
    if mutation=='skipped':run['pages'][1]['method']='skipped'
    if mutation=='duplicate':run['pages'].append(deepcopy(run['pages'][0]))
    if mutation=='missing':run['pages'].pop()
    if mutation=='fingerprint':run['pages'][0].pop('source_sha256')
    with pytest.raises(ValueError):presence.validate(run,row,value)
    presence.validate(run,row,value|{'outcome':'unresolved','checked_doc_ids':[],'source_identity_verified':False})


def test_pair_cannot_be_marked_missing(evidence):
    run,row,value=evidence
    row['atelier_ids']=['atelier']
    with pytest.raises(ValueError):presence.validate(run,row,value)


def test_saved_presence_keeps_machine_review_and_history(evidence,tmp_path,monkeypatch):
    run,row,value=evidence
    row['review']={'decision':'a_verifier','note':'older note','at':'2026'}
    folder=tmp_path/'runs'/'test';folder.mkdir(parents=True)
    (folder/'run.json').write_text(json.dumps(run),encoding='utf8')
    monkeypatch.setattr(service,'STORE',tmp_path)
    monkeypatch.setattr(service,'jobs',{'test':{'id':'test'}})
    result=service.review_presence('test',row['id'],value)
    assert result['status']=='a_verifier' and result['review']==row['review']
    assert len(result['presence_history'])==1
    saved=json.loads((folder/'comparaisons.json').read_text('utf8'))
    assert saved['statistics']['presence_counts']=={'manquant_dans_atelier':1}
    with fitz.open(folder/'rapport.pdf') as pdf:
        assert 'Synthetic reviewer' in ''.join(p.get_text() for p in pdf)
    result=service.review_presence('test',row['id'],value|{'outcome':'unresolved'})
    assert len(result['presence_history'])==2
    assert service.load_run('test')['statistics']['presence_counts']=={}


def test_normalized_identity_and_numerical_tolerance():
    a,b=record('plan'),record('atelier')
    b['information']['element']='C/99';b['level']='NIVEAU 01'
    assert reconcile([a,b])[0]['status']=='conforme'
    a['information']['armature'][0]['longueur_mm']=1000
    b['information']['armature'][0]['longueur_mm']=1000.2
    assert reconcile([a,b])[0]['status']=='non_conforme'


def test_multiple_bars_match_only_unique_marks():
    a,b=record('plan'),record('atelier')
    for r in (a,b):
        first=r['information']['armature'][0];first['repere']='A'
        second=deepcopy(first);second.update(repere='B',quantite=9)
        r['information']['armature'].append(second);r['multiplicities']=[1,1]
    b['information']['armature'].reverse()
    assert reconcile([a,b])[0]['status']=='conforme'
    b['information']['armature'][0]['quantite']=10
    result=reconcile([a,b])[0]
    assert result['status']=='non_conforme' and result['differences'][0]['repere']=='B'
    b['information']['armature'][0]['repere']='A'
    assert reconcile([a,b])[0]['status']=='a_verifier'


def test_human_identity_unlocks_comparison_without_certifying_values(evidence,tmp_path,monkeypatch):
    run,_,_=evidence
    run['records'].append(record('atelier','8-20M'))
    folder=tmp_path/'runs'/'test';folder.mkdir(parents=True)
    (folder/'run.json').write_text(json.dumps(run),encoding='utf8')
    monkeypatch.setattr(service,'STORE',tmp_path)
    monkeypatch.setattr(service,'jobs',{'test':{'id':'test'}})
    value=dict(plan_id='plan',atelier_id='atelier',outcome='same_identity',adjudicator='Synthetic',note='Identity checked')
    row=service.review_pair('test',value)
    assert row['attributes_reviewed'] is False
    assert row['comparison']['status']=='non_conforme'
    assert row['comparison']['quantity_compared']
    assert row['comparison']['differences']==[{'field':'quantite','plan':7,'atelier':8}]
    assert service.load_run('test')['results']==run['results']
    row=service.review_pair('test',value|{'outcome':'different_identity'})
    assert 'comparison' not in row
