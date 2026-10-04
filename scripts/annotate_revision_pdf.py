#!/usr/bin/env python3
"""Create review-only, linked PDF copies from Concorde JSON exports.

Coordinates in ``informations.json`` are PDF points with a top-left origin on
the displayed (rotation-adjusted) page. The script converts them back to
PyMuPDF's unrotated page coordinate system before drawing annotations.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import pymupdf as fitz


class AnnotationInputError(ValueError):
    """An export, source mapping, or coordinate cannot be resolved safely."""


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnnotationInputError(f"Impossible de lire le JSON {path}: {exc}") from exc


def _mapped_sources(source_map_path: Path, output_dir: Path) -> dict[str, Path]:
    raw = _read_json(source_map_path)
    if not isinstance(raw, dict) or not raw:
        raise AnnotationInputError("La table de sources doit être un objet JSON non vide {fichier_export: chemin_pdf}.")
    result: dict[str, Path] = {}
    destinations: set[str] = set()
    for name, path_value in raw.items():
        if not isinstance(name, str) or not name or not isinstance(path_value, str) or not path_value:
            raise AnnotationInputError("Chaque source doit associer un nom de fichier exporté à un chemin PDF non vide.")
        source = Path(path_value).expanduser().resolve()
        if not source.is_file():
            raise AnnotationInputError(f"PDF source introuvable pour {name!r}: {source}")
        if source.suffix.lower() != ".pdf":
            raise AnnotationInputError(f"La source {name!r} n'est pas un PDF: {source}")
        destination_name = f"{Path(name).stem}.annotated.pdf"
        if destination_name.casefold() in destinations:
            raise AnnotationInputError(f"Noms de sortie ambigus pour {name!r}; fournissez des noms de fichiers export uniques.")
        destinations.add(destination_name.casefold())
        destination = (output_dir / destination_name).resolve()
        if os.path.normcase(str(source)) == os.path.normcase(str(destination)):
            raise AnnotationInputError(f"La sortie écraserait la source PDF {source}.")
        result[name] = source
    return result


def _display_rect_to_pdf(rect: fitz.Rect, page: fitz.Page) -> fitz.Rect:
    """Convert a rectangle on the displayed, rotated page to PDF coordinates."""
    return rect * page.derotation_matrix


def _status_label(result: dict) -> str:
    status = result.get("status", "inconnu")
    if status == "non_conforme":
        return "ÉCART CANDIDAT · À CONFIRMER"
    if status == "conforme":
        return "ACCORD PARTIEL · À CONFIRMER"
    return "À VÉRIFIER · PROPOSITION"


def annotate_exports(informations_path: Path, comparisons_path: Path,
                     source_map_path: Path, output_dir: Path) -> list[Path]:
    """Write annotated copies and return their paths; never modify source PDFs."""
    informations = _read_json(informations_path)
    comparisons = _read_json(comparisons_path)
    if not isinstance(informations, list) or not isinstance(comparisons, dict):
        raise AnnotationInputError("Schéma attendu: informations.json (liste) et comparaisons.json (objet).")
    records: dict[str, dict] = {}
    for index, info in enumerate(informations):
        if not isinstance(info, dict):
            raise AnnotationInputError(f"information[{index}] n'est pas un objet JSON.")
        ident = info.get("id")
        if not isinstance(ident, str) or not ident or ident in records:
            raise AnnotationInputError(f"Identifiant absent ou ambigu dans information[{index}].")
        records[ident] = info

    sources = _mapped_sources(source_map_path, output_dir)
    needed_names = {i.get("fichier") for i in records.values()}
    missing = sorted(n for n in needed_names if not isinstance(n, str) or n not in sources)
    if missing:
        raise AnnotationInputError("Table de sources incomplète ou ambiguë; fichiers exportés sans PDF mappé: "
                                   + ", ".join(map(str, missing)))
    if not isinstance(comparisons.get("results", []), list):
        raise AnnotationInputError("comparaisons.json: 'results' doit être une liste.")

    related: dict[str, list[str]] = {ident: [] for ident in records}
    statuses: dict[str, str] = {}
    differences: dict[str, str] = {}
    for result_index, result in enumerate(comparisons.get("results", [])):
        if not isinstance(result, dict):
            raise AnnotationInputError(f"results[{result_index}] n'est pas un objet JSON.")
        ids = []
        for key in ("plan_ids", "atelier_ids"):
            values = result.get(key, [])
            if values is None:
                values = []
            if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
                raise AnnotationInputError(f"results[{result_index}].{key} est invalide.")
            ids.extend(values)
        for ident in ids:
            if ident not in records:
                raise AnnotationInputError(f"results[{result_index}] référence un identifiant absent de informations.json: {ident}")
            statuses[ident] = _status_label(result)
            diff_text = "; ".join(
                f"{d.get('field', '?')}: plan {d.get('plan', '?')} / atelier {d.get('atelier', '?')}"
                for d in result.get("differences", []) if isinstance(d, dict)
            )
            if diff_text:
                differences[ident] = diff_text
        for ident in ids:
            related[ident] = [other for other in ids if other != ident]

    outputs = {name: output_dir / f"{Path(name).stem}.annotated.pdf" for name in sources}
    existing_outputs = [path for path in outputs.values() if path.exists()]
    if existing_outputs:
        raise AnnotationInputError(
            "Une ou plusieurs sorties existent déjà; choisissez un dossier vide pour préserver les fichiers: "
            + ", ".join(str(path) for path in existing_outputs)
        )
    planned: dict[str, list[tuple[str, dict]]] = {name: [] for name in sources}
    for ident, info in records.items():
        name = info["fichier"]
        for field in ("page", "x", "y"):
            if isinstance(info.get(field), bool) or not isinstance(info.get(field), (int, float)):
                raise AnnotationInputError(f"Coordonnée/page manquante ou ambiguë pour {ident}: {field}.")
        planned[name].append((ident, info))

    # Stage all PDFs in memory before writing any copy, so malformed geometry
    # cannot leave a misleading partial deliverable set.
    staged: dict[str, bytes] = {}
    for name, source in sources.items():
        try:
            with fitz.open(source) as document:
                if document.is_encrypted:
                    raise AnnotationInputError(f"PDF source chiffré, non annotable sans autorisation explicite: {source}")
                for ident, info in planned[name]:
                    page_number = info["page"]
                    if not isinstance(page_number, int) or not 1 <= page_number <= len(document):
                        raise AnnotationInputError(f"Page ambiguë ou hors limites pour {ident}: {page_number} dans {name}.")
                    page = document[page_number - 1]
                    point = fitz.Point(float(info["x"]), float(info["y"]))
                    if not (point.x == point.x and point.y == point.y) or not page.rect.contains(point):
                        raise AnnotationInputError(
                            f"Coordonnée hors page ou ambiguë pour {ident}: ({point.x}, {point.y}) sur {name}, p.{page_number}; "
                            "x/y doivent être des points PDF depuis le coin haut-gauche de la page affichée."
                        )
                    # A consistent, clearly artificial marker box: exports have
                    # centers but no reliable source bounding boxes.
                    marker_display = fitz.Rect(point.x - 14, point.y - 14, point.x + 14, point.y + 14)
                    if not page.rect.contains(marker_display):
                        raise AnnotationInputError(f"Coordonnée trop près d'un bord pour surlignage non ambigu: {ident} ({name}, p.{page_number}).")
                    marker = _display_rect_to_pdf(marker_display, page)
                    highlight = page.add_highlight_annot(marker)
                    highlight.set_colors(stroke=(1, 0.75, 0.05))
                    highlight.set_opacity(0.38)
                    note = "Repère centré sur x/y exportés; ce cadre n'est pas une boîte détectée ni une validation technique."
                    if ident in differences:
                        note += " Écarts déclarés: " + differences[ident]
                    highlight.set_info(title="Concorde - proposition", content=note)
                    highlight.update()
                    # The export only gives a center point, not the symbol's
                    # extent. This is a circular location marker, not a claim
                    # that the drawing object itself has been circled.
                    circle = _display_rect_to_pdf(marker_display, page)
                    page.draw_oval(circle, color=(0.72, 0.12, 0.09), width=1.4, overlay=True)

                    # Place the callout to the right, or left if needed, in
                    # displayed coordinates; transform the entire box for a
                    # rotated page before drawing and linking it.
                    label_w, label_h = 172, 24
                    left = point.x + 19
                    if left + label_w > page.rect.width - 3:
                        left = point.x - 19 - label_w
                    top = max(3, min(point.y - label_h / 2, page.rect.height - label_h - 3))
                    label_display = fitz.Rect(left, top, left + label_w, top + label_h)
                    if left < 3 or not page.rect.contains(label_display):
                        raise AnnotationInputError(f"Aucun emplacement sûr pour l'étiquette de {ident} ({name}, p.{page_number}).")
                    label = _display_rect_to_pdf(label_display, page)
                    # Keep the visible callout short enough for small plan
                    # sheets. Full difference details live in the annotation
                    # popup, where they cannot be clipped by the label box.
                    label_text = statuses.get(ident, "EXTRACTION - NON VALIDEE")
                    page.draw_rect(label, color=(0.65, 0.18, 0.08), fill=(1, 0.94, 0.65), width=1.2, overlay=True)
                    text_rect = fitz.Rect(label.x0 + 4, label.y0 + 3, label.x1 - 4, label.y1 - 3)
                    page.insert_textbox(text_rect, label_text[:180], fontsize=6.2,
                                        fontname="helv", color=(0.25, 0.12, 0.05),
                                        rotate=(360 - page.rotation) % 360, overlay=True)
                    page.draw_line(_display_rect_to_pdf(fitz.Point(point.x, point.y), page),
                                   _display_rect_to_pdf(fitz.Point(left if left > point.x else left + label_w, top + label_h / 2), page),
                                   color=(0.65, 0.18, 0.08), width=0.8, overlay=True)

                    peers = related.get(ident) or []
                    target_id = peers[0] if peers else ident
                    target_info = records[target_id]
                    if target_info["fichier"] == name:
                        target_point = fitz.Point(float(target_info["x"]), float(target_info["y"]))
                        target_page_number = target_info["page"]
                        target_page = document[target_page_number - 1]
                        target_pdf_point = target_point * target_page.derotation_matrix
                        page.insert_link({"kind": fitz.LINK_GOTO, "from": label, "page": target_page_number - 1,
                                          "to": target_pdf_point, "zoom": 0})
                    else:
                        target_name = target_info["fichier"]
                        target_out = outputs[target_name]
                        uri = quote(target_out.name, safe="/._-") + f"#page={int(target_info['page'])}"
                        page.insert_link({"kind": fitz.LINK_URI, "from": label, "uri": uri})
                staged[name] = document.tobytes(garbage=4, deflate=True)
        except AnnotationInputError:
            raise
        except Exception as exc:
            raise AnnotationInputError(f"Impossible d'annoter {source}: {exc}") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for name, content in staged.items():
            # Exclusive creation avoids replacing an output created by another
            # process after the preflight check above.
            with outputs[name].open("xb") as stream:
                created.append(outputs[name])
                stream.write(content)
    except Exception as exc:
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        raise AnnotationInputError(f"Impossible de créer les copies annotées sans écraser un fichier: {exc}") from exc
    return list(outputs.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--informations", required=True, type=Path, help="Chemin vers informations.json")
    parser.add_argument("--comparaisons", required=True, type=Path, help="Chemin vers comparaisons.json")
    parser.add_argument("--source-map", required=True, type=Path,
                        help="JSON {valeur information.fichier: chemin vers PDF source}")
    parser.add_argument("--output-dir", required=True, type=Path, help="Dossier de copies annotées distinct des originaux")
    args = parser.parse_args(argv)
    try:
        outputs = annotate_exports(args.informations, args.comparaisons, args.source_map, args.output_dir)
    except AnnotationInputError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
