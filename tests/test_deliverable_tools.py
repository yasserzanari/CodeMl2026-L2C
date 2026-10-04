import json
from scripts.audit_deliverables import catalog_inventory, page_coverage
from scripts.run_full_local import completed_projects


def test_catalog_uses_project_relative_paths_and_fresh_hashes(tmp_path):
    raw, store = tmp_path / "raw", tmp_path / "store"
    pdf = raw / "CLP" / "DA" / "sample.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"local fixture")
    store.mkdir()
    stat = pdf.stat()
    (store / "catalog.json").write_text(json.dumps({str(pdf.resolve()): {
        "stamp": f"{stat.st_mtime_ns}:{stat.st_size}", "pages": 2, "sha256": "hash"
    }}))
    inventory, _ = catalog_inventory(raw, store)
    expected = inventory["CLP"]
    assert expected["_expected_page_keys"] == {("DA/sample.pdf", 1), ("DA/sample.pdf", 2)}
    pages = [{"file": "DA\\sample.pdf", "page": n, "source": "atelier", "source_sha256": "hash"} for n in (1, 2)]
    run = {"pages": pages, "statistics": {"pages_processed": 2, "pages_total": 2}}
    coverage = page_coverage(run, expected)
    assert coverage["exact_page_count"] and coverage["source_hashes_match_catalog"]
    assert coverage["missing_source_pages"] == coverage["unexpected_source_pages"] == 0
    pages[0]["source_sha256"] = "changed"
    assert not page_coverage(run, expected)["source_hashes_match_catalog"]
    pages[0]["source_sha256"] = "hash"
    pages.append(pages[0])
    assert not page_coverage(run, expected)["exact_page_count"]


def test_skip_completed_requires_current_sources_and_exports(tmp_path):
    folder = tmp_path / "runs" / "r1"
    folder.mkdir(parents=True)
    (folder / "job.json").write_text(json.dumps({"status": "completed"}))
    run = {"project_id": "CLP", "scope": "complete", "pages": [{"file": "DA/x.pdf", "page": 1, "source_sha256": "hash"}], "statistics": {"pages_processed": 1, "pages_total": 1}}
    (folder / "run.json").write_text(json.dumps(run))
    docs = {"CLP": {"DA/x.pdf": {"pages": 1, "sha256": "hash"}}}
    assert completed_projects(tmp_path, docs) == set()
    for name in ("informations.json", "comparaisons.json", "rapport.pdf"):
        (folder / name).write_bytes(b"fixture")
    assert completed_projects(tmp_path, docs) == {"CLP"}
    docs["CLP"]["DA/x.pdf"]["sha256"] = "changed"
    assert completed_projects(tmp_path, docs) == set()
