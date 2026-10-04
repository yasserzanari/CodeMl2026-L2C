import base64
import json

import pytest
from fastapi.testclient import TestClient

from l2c_app import catalog, llm_pairing, service
from l2c_app.server import app


def record(source, element):
    return {
        "doc_id": source + "-doc",
        "box": [10, 20, 30, 40],
        "raw": "4-20M @ 200",
        "confidence": 0.95,
        "anchor_kind": "label",
        "identity_resolved": True,
        "level": "N1",
        "role": "vert",
        "phase": "haut",
        "information": {
            "id": source + "-id", "source": source, "fichier": source + ".pdf",
            "page": 1, "feuillet": "S-101", "type_element": "colonne",
            "element": element,
        },
    }


def test_only_loopback_ollama_urls_are_allowed(monkeypatch):
    monkeypatch.setenv("CONCORDE_OLLAMA_URL", "https://example.com")
    with pytest.raises(llm_pairing.PairingModelUnavailable, match="bouclage"):
        llm_pairing._connection()


def test_status_explains_when_model_is_not_downloaded(monkeypatch):
    monkeypatch.delenv("CONCORDE_OLLAMA_URL", raising=False)
    monkeypatch.delenv("CONCORDE_VLM_MODEL", raising=False)
    monkeypatch.setattr(llm_pairing, "_request_json", lambda *_args, **_kwargs: {"models": []})

    result = llm_pairing.status()

    assert result["available"] is False
    assert result["model"] == "qwen3.5:4b"
    assert "ollama pull qwen3.5:4b" in result["message"]


def test_structured_answer_rejects_unknown_identity():
    with pytest.raises(llm_pairing.PairingModelError, match="identité reconnue"):
        llm_pairing._answer('{"identity":"probably","summary_fr":"hmm"}')


def test_local_pair_analysis_sends_two_unmarked_crops_and_is_advisory(monkeypatch):
    sent = {}
    rendered = []
    monkeypatch.setattr(llm_pairing, "status", lambda: {"available": True, "model": "qwen3.5:4b"})
    monkeypatch.setattr(catalog, "render", lambda *args, **kwargs: rendered.append((args, kwargs)) or b"synthetic-png")

    def request(url, body, timeout):
        sent.update(url=url, body=body, timeout=timeout)
        return {"message": {"content": json.dumps({
            "identity": "uncertain", "summary_fr": "Le repère de niveau manque.",
            "evidence": [{"source": "plan", "text": "Repère peu lisible."}],
            "questions": ["Confirmer le niveau dans les deux feuillets."],
        })}}

    monkeypatch.setattr(llm_pairing, "_request_json", request)
    result = llm_pairing.analyze_pair(record("plan", "C-4"), record("atelier", "C-4"))

    message = sent["body"]["messages"][1]
    assert sent["url"] == "http://127.0.0.1:11434/api/chat"
    assert sent["body"]["model"] == "qwen3.5:4b"
    assert sent["body"]["format"] == "json"
    assert len(message["images"]) == 4
    assert base64.b64decode(message["images"][0]) == b"synthetic-png"
    assert [kwargs["full"] for _, kwargs in rendered] == [True, False, True, False]
    assert all(kwargs["highlight"] is False for _, kwargs in rendered)
    assert result["identity"] == "uncertain"
    assert result["advisory_only"] is True
    assert "aucun verdict automatique" in result["notice_fr"].casefold()


def test_pairing_assist_api_requires_correct_sources_and_does_not_save_advice(monkeypatch):
    plan, atelier = record("plan", "C-4"), record("atelier", "C-4")
    run = {"records": [plan, atelier]}
    monkeypatch.setattr(service, "load_run", lambda _run_id: run)
    monkeypatch.setattr(llm_pairing, "analyze_pair", lambda _plan, _atelier: {
        "identity": "uncertain", "summary_fr": "Contexte insuffisant.",
        "evidence": [], "questions": [], "model": "qwen3.5:4b",
        "advisory_only": True, "notice_fr": "Aucun verdict automatique modifié.",
    })

    with TestClient(app) as client:
        response = client.post("/api/runs/run-1/pairing-assist",
                               headers={"x-concorde-request": "1"},
                               json={"plan_id": "plan-id", "atelier_id": "atelier-id"})
        bad_source = client.post("/api/runs/run-1/pairing-assist",
                                 headers={"x-concorde-request": "1"},
                                 json={"plan_id": "atelier-id", "atelier_id": "plan-id"})

    assert response.status_code == 200
    assert response.json()["advisory_only"] is True
    assert bad_source.status_code == 404
