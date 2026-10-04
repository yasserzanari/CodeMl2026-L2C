"""Synthetic-only tests for the review-only revision comparator."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from compare_l2c_revisions import compare_data, compare_files  # noqa: E402


def row(*, ident="r1", filename="plans.pdf", sheet="S-101", level="Niveau 1",
        mark="A1", x=10.0, y=20.0, diameter="15", quantity=2, spacing=200,
        length=1000, family="poutre", element="B1"):
    return {
        "id": ident,
        "fichier": filename,
        "feuillet": sheet,
        "niveau": level,
        "type_element": family,
        "element": element,
        "x": x,
        "y": y,
        "armature": [{"repere": mark, "diametre": diameter, "quantite": quantity,
                      "espacement_mm": spacing, "longueur_mm": length}],
    }


def test_same_conservative_key_reports_only_attribute_review_candidate():
    report = compare_data([row()], [row(ident="r2", quantity=3)], old_sha256="old", new_sha256="new")

    assert report["decision_policy"] == "review_candidates_only_no_engineering_decisions"
    assert report["summary"]["matched"] == 1
    assert report["change_candidates"][0]["status"] == "change_candidate_review_required"
    assert report["change_candidates"][0]["attribute_changes"] == [
        {"attribute": "quantite", "old": 2, "new": 3}
    ]
    assert report["sources"]["old"]["sha256"] == "old"
    assert "engineering" not in report["change_candidates"][0]["status"]


@pytest.mark.parametrize("field,value", [
    ("fichier", "other.pdf"), ("feuillet", "S-102"), ("niveau", "Niveau 2"),
    ("x", 10.5), ("y", 20.5),
])
def test_identity_coordinate_change_stays_unmatched(field, value):
    before, after = row(), row(ident="r2")
    after[field] = value
    report = compare_data([before], [after])

    assert report["summary"]["matched"] == 0
    assert report["summary"]["unmatched_old"] == 1
    assert report["summary"]["unmatched_new"] == 1
    assert "contrepartie exacte" in report["unmatched"]["old"][0]["reason"]


def test_missing_level_prevents_pairing_and_explains_why():
    before, after = row(), row(ident="r2")
    del before["niveau"]
    del after["niveau"]
    report = compare_data([before], [after])

    assert report["summary"]["matched"] == 0
    assert report["unmatched"]["old"][0]["missing_key_fields"] == ["niveau"]
    assert any("niveau" in item for item in report["limitations"])


def test_duplicate_key_is_ambiguous_and_never_arbitrarily_paired():
    report = compare_data([row(), row(ident="duplicate")], [row(ident="new")])

    assert report["summary"]["ambiguous"] == 1
    assert report["summary"]["matched"] == 0
    assert report["ambiguous"][0]["status"] == "ambiguous_review_required"


def test_file_inputs_are_hashed_and_json_report_is_plain_data(tmp_path):
    old_path, new_path = tmp_path / "old.json", tmp_path / "new.json"
    old_path.write_text(json.dumps([row()]), encoding="utf-8")
    new_path.write_text(json.dumps([row(ident="r2")]), encoding="utf-8")

    report = compare_files(old_path, new_path)

    assert report["sources"]["old"]["sha256"]
    assert report["sources"]["new"]["sha256"]
    assert report["schema"] == "l2c-revision-comparison-v1"
    json.dumps(report, ensure_ascii=False)


def test_bad_export_shape_is_rejected():
    with pytest.raises(ValueError, match="attendu une liste"):
        compare_data({"results": []}, [])
