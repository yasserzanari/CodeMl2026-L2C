import sys
from types import SimpleNamespace

import pytest

from l2c_app import ocr, rapid
from l2c_app.config import DEFAULTS, settings
from l2c_app.models import Settings


def test_settings_prefers_auto_but_preserves_explicit_device(monkeypatch, tmp_path):
    monkeypatch.setattr('l2c_app.config.STORE', tmp_path)
    assert DEFAULTS['device'] == 'auto'
    assert settings()['device'] == 'auto'
    (tmp_path / 'settings.json').write_text('{"device":"cpu"}', encoding='utf-8')
    assert settings()['device'] == 'cpu'
    (tmp_path / 'settings.json').write_text('{"device":"auto","ocr_engine":"rapidocr"}', encoding='utf-8')
    assert settings()['ocr_engine'] == 'rapidocr'
    (tmp_path / 'settings.json').write_text('{"ocr_engine":"unsupported"}', encoding='utf-8')
    assert settings()['ocr_engine'] == DEFAULTS['ocr_engine']
    (tmp_path / 'settings.json').write_text('{', encoding='utf-8')
    assert settings()['device'] == DEFAULTS['device']
    assert Settings(device='cuda').device == 'cuda'
    assert Settings(device='cpu').device == 'cpu'


def test_explicit_cuda_fails_instead_of_silent_cpu(monkeypatch):
    monkeypatch.setattr(ocr.torch.cuda, 'is_available', lambda: False)
    with pytest.raises(RuntimeError, match='CUDA indisponible'):
        ocr.reader_for('cuda')
    with pytest.raises(RuntimeError, match='CUDA indisponible'):
        rapid.reader_for({'device': 'cuda', 'canvas_size': 1280, 'batch_size': 1,
                          'ocr_strategy': 'tiled'})


def test_easyocr_auto_uses_cpu_when_cuda_is_unavailable(monkeypatch):
    class Network:
        def parameters(self):
            return iter([SimpleNamespace(device=SimpleNamespace(type='cpu'))])

    class FakeReader:
        def __init__(self, languages, gpu, **kwargs):
            self.gpu = gpu
            self.detector = Network()
            self.recognizer = Network()

    monkeypatch.setitem(sys.modules, 'easyocr', SimpleNamespace(Reader=FakeReader))
    monkeypatch.setattr(ocr.torch.cuda, 'is_available', lambda: False)
    monkeypatch.setattr(ocr, '_reader', None)
    monkeypatch.setattr(ocr, '_device', None)
    reader = ocr.reader_for('auto')
    assert reader.gpu is False
    assert ocr._device == 'cpu'


def test_rapidocr_auto_uses_cpu_provider(monkeypatch):
    class Session:
        def get_providers(self):
            return ['CPUExecutionProvider']

        def disable_fallback(self):
            raise AssertionError('CPU sessions must not disable CPU fallback')

    class SessionHolder:
        def __init__(self):
            self.session = Session()

    class FakeRapidOCR:
        def __init__(self, **kwargs):
            self.text_det = SimpleNamespace(engine=SessionHolder())
            self.text_cls = SimpleNamespace(engine=SessionHolder())
            self.text_rec = SimpleNamespace(engine=SessionHolder())

    monkeypatch.setitem(sys.modules, 'rapidocr_onnxruntime', SimpleNamespace(RapidOCR=FakeRapidOCR))
    monkeypatch.setattr(rapid.torch.cuda, 'is_available', lambda: False)
    monkeypatch.setattr(rapid, '_reader', None)
    monkeypatch.setattr(rapid, '_key', None)
    monkeypatch.setattr(rapid, '_configure_onnxruntime_provider_order', lambda: None)
    reader, providers, device = rapid.reader_for({
        'device': 'auto', 'canvas_size': 1280, 'batch_size': 1, 'ocr_strategy': 'tiled'
    })
    assert isinstance(reader, FakeRapidOCR)
    assert all(values == ['CPUExecutionProvider'] for values in providers.values())
    assert device == 'cpu'
