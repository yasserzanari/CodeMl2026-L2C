from copy import deepcopy
import json
import pytest
import pymupdf as fitz
from fastapi.testclient import TestClient
from l2c_app.extraction import parse_armatures, native_lines
from l2c_app.matching import reconcile, statistics
from l2c_app.models import Information
from l2c_app.reports import export
from l2c_app.server import app


@pytest.mark.parametrize('text,quantity,spacing,mult', [
    ('7-20M', 7, None, 1), ('5x4 25M', 4, None, 5),
    ('RANG 2: 15M @ 175', None, 175, 1),
    ('10M @ 8"', None, 203.2, 1), ('10M @ 8', None, None, 1),
])
def test_notation(text, quantity, spacing, mult):
    result = parse_armatures(text)[0]
    assert result['value']['quantite'] == quantity
    assert result['value']['espacement_mm'] == spacing
    assert result['multiplicity'] == mult


def record(source, text='7-20M', level='N1'):
    bars = parse_armatures(text)
    info = Information(id=source, source=source, fichier='synthetic.pdf', feuillet='S-999',
        page=1, x=60, y=60, type_element='colonne', element='C99',
        armature=[b['value'] for b in bars]).model_dump()
    return dict(information=info, identity_resolved=True, level=level, role='', phase='',
                multiplicities=[b['multiplicity'] for b in bars], confidence=1,
                box=[50,50,70,70], raw=text, doc_id='synthetic')


@pytest.mark.parametrize('text,status', [('7-20M','conforme'),('8-20M','non_conforme'),
                                           ('7-25M','non_conforme'),('5x4 25M','a_verifier')])
def test_identity_before_values(text,status):
    result = reconcile([record('plan'),record('atelier',text)])
    assert len(result)==1 and result[0]['status']==status


def test_different_levels_abstain():
    assert all(r['status']=='a_verifier' for r in reconcile([record('plan'),record('atelier',level='N2')]))


def test_uncertainty_abstains():
    a,b=record('plan'),record('atelier','9-25M'); b['confidence']=.3
    assert reconcile([a,b])[0]['status']=='a_verifier'


def test_unmatched_is_not_missing():
    assert reconcile([record('plan')])[0]['status']=='a_verifier'


def test_identical_copies_across_shop_documents_can_reach_comparison():
    plan=record('plan','4-35M','N2')
    plan['information']['element']='K-6';plan['role']='vert';plan['doc_id']='plan-file'
    first=record('atelier','4-25M','N2')
    first['information']['element']='K-6';first['role']='vert';first['doc_id']='shop-part-2'
    second=deepcopy(first);second['information']['id']='atelier-copy';second['doc_id']='shop-part-3'
    result=reconcile([plan,first,second])[0]
    assert result['status']=='non_conforme'
    assert result['differences']==[{'field':'diametre','plan':'35M','atelier':'25M'}]
    assert result['atelier_ids']==['atelier','atelier-copy']
    assert 'copies atelier identiques' in result['reason']


def test_conflicting_duplicate_shop_documents_remain_unresolved():
    plan=record('plan','4-35M','N2');plan['information']['element']='K-6';plan['role']='vert'
    first=record('atelier','4-25M','N2');first['information']['element']='K-6';first['role']='vert';first['doc_id']='part-2'
    second=record('atelier','4-30M','N2');second['information']['id']='atelier-copy';second['information']['element']='K-6';second['role']='vert';second['doc_id']='part-3'
    result=reconcile([plan,first,second])[0]
    assert result['status']=='a_verifier' and not result['differences']


def test_repeat_in_one_shop_document_is_not_collapsed():
    plan=record('plan','4-35M','N2');plan['information']['element']='K-6';plan['role']='vert'
    first=record('atelier','4-25M','N2');first['information']['element']='K-6';first['role']='vert';first['doc_id']='part-2'
    second=record('atelier','4-25M','N2');second['information']['id']='atelier-copy';second['information']['element']='K-6';second['role']='vert';second['doc_id']='part-2'
    assert reconcile([plan,first,second])[0]['status']=='a_verifier'


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_pdf_rotation_geometry(angle):
    with fitz.open() as doc:
        page=doc.new_page(width=300,height=400)
        page.insert_text((40,60),'7-20M'); page.set_rotation(angle)
        line=native_lines(page)[0]
        box=fitz.Rect(line['box'])
        assert box in page.rect
        assert line['text']=='7-20M'
        restored=box*page.derotation_matrix
        assert abs(restored.x0-40)<1


def test_json_pdf_exports(tmp_path):
    records=[record('plan'),record('atelier')]
    results=reconcile(records)
    pages=[dict(source='plan',method='pdf',sheet='S-999',file='synthetic.pdf',page=1)]
    run=dict(id='synthetic',created_at='2026-01-01',project_name='Synthetic',scope='synthetic',
             records=records,results=results,pages=pages,statistics=statistics(records,results,pages))
    export(run,tmp_path)
    values=json.loads((tmp_path/'informations.json').read_text('utf8'))
    assert len(values)==2
    for value in values: Information.model_validate(value)
    with fitz.open(tmp_path/'rapport.pdf') as doc:
        assert len(doc)>=2 and 'CONCORDE' in doc[0].get_text()


def test_api_local_guard():
    with TestClient(app) as client:
        assert client.get('/api/overview').json()['application']=='concorde'
        assert client.post('/api/settings',json={}).status_code==403
        assert client.get('/api/overview',headers={'Host':'untrusted.invalid'}).status_code==400
        assert client.post('/api/settings',json={},headers={'x-concorde-request':'1','origin':'https://untrusted.invalid'}).status_code==403
        assert client.get('/api/documents/unknown/pdf').status_code==404
