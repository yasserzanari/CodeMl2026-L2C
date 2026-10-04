from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from l2c_app import rapid


CONFIG={'device':'cuda','canvas_size':2560,'batch_size':32,'ocr_rotations':True,'ocr_strategy':'page'}


def test_page_strategy_single_detection_original_pixels_and_coordinates(monkeypatch):
    calls=[]
    polygon=[[3010,40],[3020,40],[3020,140],[3010,140]]
    def reader(array):
        calls.append(array.shape)
        # The backend returns input-pixel coordinates, including vertical crops.
        return [[polygon,'8-20M',.9]],[1,2,3]
    monkeypatch.setattr(rapid,'reader_for',lambda config:(reader,{},'cuda'))
    result,meta=rapid.recognize(Image.new('RGB',(4000,200)),CONFIG)
    assert calls==[(200,4000,3)]
    assert result==[(polygon,'8-20M',.9)]
    assert meta['tiles']==1 and meta['strategy']=='page'
    assert meta['phase_seconds']=={'detection':1,'classification':2,'recognition':3}
    assert meta['quality_warning'] and meta['crop_orientation']=='automatic'
    # The extraction layer's pixel-to-PDF transform at 96 dpi stays valid.
    assert [[x*.75,y*.75] for x,y in result[0][0]]==[[2257.5,30],[2265,30],[2265,105],[2257.5,105]]


def test_tiled_default_still_rotates_each_tile(monkeypatch):
    calls=[]
    def reader(array):
        calls.append(array.shape)
        return [],None
    monkeypatch.setattr(rapid,'reader_for',lambda config:(reader,{},'cuda'))
    config={k:v for k,v in CONFIG.items() if k!='ocr_strategy'}
    result,meta=rapid.recognize(Image.new('RGB',(80,40)),config)
    assert calls==[(40,80,3),(80,40,3),(80,40,3)]
    assert result==[] and meta['strategy']=='tiled' and meta['tiles']==3


def test_page_cuda_failure_does_not_retry_on_cpu(monkeypatch):
    configs=[]
    def broken(_):raise RuntimeError('CUDA failure allocation')
    def factory(config):
        configs.append(config)
        return broken,{'providers':['CUDAExecutionProvider']},'cuda'
    monkeypatch.setattr(rapid,'reader_for',factory)
    with pytest.raises(RuntimeError,match='CUDA failure'):
        rapid.recognize(Image.new('RGB',(20,20)),CONFIG)
    assert len(configs)==1 and configs[0]['device']=='cuda'


def test_page_does_not_swallow_other_errors(monkeypatch):
    def broken(_):raise RuntimeError('Invalid polygon')
    monkeypatch.setattr(rapid,'reader_for',lambda config:(broken,{},'cpu'))
    with pytest.raises(RuntimeError,match='Invalid polygon'):
        rapid.recognize(Image.new('RGB',(20,20)),CONFIG)


def test_strategy_changes_reader_configuration_without_leaking(monkeypatch):
    import rapidocr_onnxruntime
    created=[]
    class Reader:
        def __init__(self,**kwargs):
            created.append(kwargs)
            class Session:
                def __init__(self): self.providers=['CUDAExecutionProvider','CPUExecutionProvider']
                def get_providers(self): return self.providers
                def disable_fallback(self): pass
            self.text_det=SimpleNamespace(ort=SimpleNamespace(session=Session()))
            self.text_cls=SimpleNamespace(ort=SimpleNamespace(session=Session()))
            self.text_rec=SimpleNamespace(ort=SimpleNamespace(session=Session()))
    monkeypatch.setattr(rapidocr_onnxruntime,'RapidOCR',Reader)
    monkeypatch.setattr(rapid.torch.cuda,'is_available',lambda:True)
    monkeypatch.setattr(rapid,'_reader',None)
    monkeypatch.setattr(rapid,'_key',None)
    rapid.reader_for(CONFIG)
    rapid.reader_for(CONFIG)
    rapid.reader_for(CONFIG|{'ocr_strategy':'tiled'})
    rapid.reader_for(CONFIG|{'ocr_strategy':'tiled','batch_size':128})
    assert len(created)==3
    assert created[0]['max_side_len']>=4000
    assert created[0]['rec_batch_num']==32 and created[0]['cls_batch_num']==32
    assert created[1]['rec_batch_num']==32 and 'cls_batch_num' not in created[1]
    assert 'max_side_len' not in created[1]
    assert created[2]['rec_batch_num']==64 and 'cls_batch_num' not in created[2]
    assert 'max_side_len' not in created[2]


def test_reader_rejects_unknown_device(monkeypatch):
    with pytest.raises(ValueError,match='Périphérique OCR inconnu'):
        rapid.reader_for(CONFIG|{'device':'tpu'})
