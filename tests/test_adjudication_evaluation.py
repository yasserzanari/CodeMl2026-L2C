import pytest
from scripts.evaluate_adjudication import evaluate


def fixture(status='a_verifier'):
    run={'id':'synthetic','project_id':'demo','records':[
        {'information':{'id':'p','source':'plan','type_element':'colonne'}},
        {'information':{'id':'a','source':'atelier','type_element':'colonne'}}],
        'results':[{'plan_ids':['p'],'atelier_ids':['a'],'status':status,
                    'differences':[{'field':'quantite'}] if status=='non_conforme' else []}]}
    label={'project_id':'demo','source_run_sha256':'hash','plan_record_id':'p',
           'atelier_record_id':'a','human_outcome':'same_identity',
           'confirmed_discrepancy_fields':['quantite'],'adjudicator':'synthetic'}
    return run,label


def test_abstention_counts_as_missed_known_discrepancy():
    run,label=fixture()
    result=evaluate(run,[label],'hash')
    assert result['slices']['all']['fn']==1
    assert result['slices']['all']['recall_on_reviewed_subset']==0
    assert result['project_recall'] is None


def test_empty_labels_cannot_produce_performance_claim():
    run,_=fixture()
    assert evaluate(run,[],'hash')['slices']=={}


def test_wrong_pair_alert_counts_false_positive():
    run,label=fixture('non_conforme')
    label.update(human_outcome='different_identity',confirmed_discrepancy_fields=[])
    assert evaluate(run,[label],'hash')['slices']['all']['fp']==1


def test_stale_labels_rejected():
    run,label=fixture()
    with pytest.raises(ValueError,match='hash'):
        evaluate(run,[label],'different-hash')


def test_field_and_pair_detection():
    run,label=fixture('non_conforme')
    result=evaluate(run,[label],'hash')['slices']['all']
    assert result['tp']==1 and result['field_tp']==1
    assert result['precision_on_reviewed_subset']==1


def test_duplicate_labels_rejected():
    run,label=fixture()
    with pytest.raises(ValueError,match='Duplicate'):
        evaluate(run,[label,label],'hash')
