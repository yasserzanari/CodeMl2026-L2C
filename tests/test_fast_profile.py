import hashlib
import json
from l2c_app import extraction,service
from l2c_app.config import DEFAULTS
from l2c_app.models import AnalysisRequest


def test_fast_request_and_job_config_are_explicit(monkeypatch,tmp_path):
    monkeypatch.setattr(service,'STORE',tmp_path)
    monkeypatch.setattr(service,'jobs',{})
    monkeypatch.setattr(service.catalog,'project',lambda _: {'name':'Synthetic','pages':2})
    monkeypatch.setattr(service,'settings',lambda:dict(DEFAULTS))
    monkeypatch.setattr(service.POOL,'submit',lambda *args: None)
    request=AnalysisRequest(profile='fast').model_dump()
    job=service.start('synthetic',request)
    assert job['config']['ocr_strategy']=='page'
    assert job['config']['dpi']==96
    assert job['config']['ocr_engine']=='rapidocr'
    assert job['request']['profile']=='fast'
    assert 'ocr_strategy' not in DEFAULTS


def test_fast_reuses_detailed_cache_without_mutating_it(monkeypatch,tmp_path):
    monkeypatch.setattr(extraction,'STORE',tmp_path)
    (tmp_path/'cache').mkdir()
    config=dict(DEFAULTS,ocr_engine='rapidocr',dpi=96,ocr_rotations=False,ocr_strategy='page')
    signature={k:config[k] for k in ['dpi','canvas_size','ocr_confidence','ocr_rotations']}
    signature.update(dpi=144,ocr_rotations=True,ocr_engine='rapidocr')
    key=hashlib.sha256((extraction.VERSION+'source'+'0'+json.dumps(signature,sort_keys=True)+'False').encode()).hexdigest()
    path=tmp_path/'cache'/f'{key}.json'
    payload={'method':'ocr','lines':[],'width':200,'height':300,'rotation':0,'device':'cuda'}
    path.write_text(json.dumps(payload),'utf-8')
    before=path.read_bytes()
    reading=extraction.read_page('not-opened.pdf',0,'source',config)
    assert reading['reused_cache'] and reading['cached']
    assert reading['ocr_strategy']=='tiled'
    assert path.read_bytes()==before
