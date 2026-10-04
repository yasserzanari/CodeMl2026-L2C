import json

import pymupdf as fitz
import pytest

from scripts.annotate_revision_pdf import AnnotationInputError, annotate_exports


def make_pdf(path, rotation=0):
    with fitz.open() as pdf:
        page = pdf.new_page(width=320, height=440)
        page.insert_text((45, 70), "PLAN SYNTHETIQUE")
        if rotation:
            page.set_rotation(rotation)
        pdf.save(path)


def make_exports(tmp_path, point=(90, 110)):
    plan = tmp_path / "plan-source.pdf"
    shop = tmp_path / "atelier-source.pdf"
    make_pdf(plan)
    make_pdf(shop, 90)
    info = [
        {"id": "p1", "source": "plan", "fichier": "plan.pdf", "feuillet": "S-001",
         "page": 1, "x": 90, "y": 110, "element": "C1"},
        {"id": "a1", "source": "atelier", "fichier": "atelier.pdf", "feuillet": "S-001",
         "page": 1, "x": point[0], "y": point[1], "element": "C1"},
    ]
    (tmp_path / "informations.json").write_text(json.dumps(info), encoding="utf-8")
    (tmp_path / "comparaisons.json").write_text(json.dumps({"results": [{
        "plan_ids": ["p1"], "atelier_ids": ["a1"], "status": "non_conforme",
        "differences": [{"field": "diametre", "plan": "20M", "atelier": "25M"}],
    }]}), encoding="utf-8")
    (tmp_path / "sources.json").write_text(json.dumps({
        "plan.pdf": str(plan), "atelier.pdf": str(shop),
    }), encoding="utf-8")
    return plan, shop


def test_creates_review_only_copies_with_highlights_and_cross_pdf_links(tmp_path):
    plan, shop = make_exports(tmp_path)
    original_bytes = (plan.read_bytes(), shop.read_bytes())
    output_dir = tmp_path / "annotated"

    outputs = annotate_exports(tmp_path / "informations.json", tmp_path / "comparaisons.json",
                               tmp_path / "sources.json", output_dir)

    assert {p.name for p in outputs} == {"plan.annotated.pdf", "atelier.annotated.pdf"}
    assert (plan.read_bytes(), shop.read_bytes()) == original_bytes
    for path in outputs:
        with fitz.open(path) as pdf:
            page = pdf[0]
            assert "ÉCART CANDIDAT" in page.get_text()
            assert "NON VALIDÉ" in page.get_text() or "CONFIRMER" in page.get_text()
            assert any(a.type[0] == fitz.PDF_ANNOT_HIGHLIGHT for a in (page.annots() or []))
            links = page.get_links()
            assert links and any(
                (link["kind"] == fitz.LINK_URI and "#page=1" in link.get("uri", ""))
                or (link["kind"] == fitz.LINK_GOTOR and link.get("page") == 0
                    and link.get("file", "").endswith(".annotated.pdf"))
                for link in links
            )
    with fitz.open(output_dir / "atelier.annotated.pdf") as pdf:
        page = pdf[0]
        # Coordinates are in the rotated, top-left display coordinate system.
        # The highlight transforms back to that same location for a 90-degree page.
        highlight = next(a for a in page.annots() if a.type[0] == fitz.PDF_ANNOT_HIGHLIGHT)
        displayed = highlight.rect * page.rotation_matrix
        assert abs((displayed.x0 + displayed.x1) / 2 - 90) < 3
        assert abs((displayed.y0 + displayed.y1) / 2 - 110) < 3
        # A circle marks the exported center. It is not asserted to enclose
        # the drawing symbol because the export has no source bounding box.
        assert any(any(item[0] == "c" for item in drawing["items"])
                   for drawing in page.get_drawings())


def test_refuses_existing_output_without_replacing_any_file(tmp_path):
    plan, shop = make_exports(tmp_path)
    output_dir = tmp_path / "annotated"
    output_dir.mkdir()
    existing = output_dir / "plan.annotated.pdf"
    existing.write_bytes(b"keep this prior file")

    with pytest.raises(AnnotationInputError, match="existent déjà"):
        annotate_exports(tmp_path / "informations.json", tmp_path / "comparaisons.json",
                         tmp_path / "sources.json", output_dir)

    assert existing.read_bytes() == b"keep this prior file"
    assert not (output_dir / "atelier.annotated.pdf").exists()
    assert plan.exists() and shop.exists()


def test_refuses_case_insensitive_source_destination_collision(tmp_path):
    make_exports(tmp_path)
    colliding_source = tmp_path / "Plan.annotated.pdf"
    make_pdf(colliding_source)
    source_bytes = colliding_source.read_bytes()
    source_map = {"plan.pdf": str(colliding_source), "atelier.pdf": str(tmp_path / "atelier-source.pdf")}
    (tmp_path / "sources.json").write_text(json.dumps(source_map), encoding="utf-8")

    with pytest.raises(AnnotationInputError, match="écraserait la source"):
        annotate_exports(tmp_path / "informations.json", tmp_path / "comparaisons.json",
                         tmp_path / "sources.json", tmp_path)

    assert colliding_source.read_bytes() == source_bytes


def test_rejects_out_of_page_or_ambiguous_coordinates_without_outputs(tmp_path):
    make_exports(tmp_path, point=(500, 110))
    output_dir = tmp_path / "annotated"
    with pytest.raises(AnnotationInputError, match="Coordonnée hors page"):
        annotate_exports(tmp_path / "informations.json", tmp_path / "comparaisons.json",
                         tmp_path / "sources.json", output_dir)
    assert not output_dir.exists() or not list(output_dir.glob("*.pdf"))


def test_rejects_missing_source_mapping(tmp_path):
    make_exports(tmp_path)
    (tmp_path / "sources.json").write_text(json.dumps({"plan.pdf": str(tmp_path / "plan-source.pdf")}), encoding="utf-8")
    with pytest.raises(AnnotationInputError, match="Table de sources incomplète"):
        annotate_exports(tmp_path / "informations.json", tmp_path / "comparaisons.json",
                         tmp_path / "sources.json", tmp_path / "annotated")
