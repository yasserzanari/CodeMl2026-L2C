#!/usr/bin/env python3
"""Conservative, review-only comparison of two L2C JSON information exports.

This utility performs no OCR and never decides whether a change is acceptable.
It only pairs observations when document, sheet, level, element identity, mark,
and coordinates are all present and identical after conservative normalization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


KEY_FIELDS = ("document", "feuillet", "niveau", "type_element", "element", "repere", "x", "y")
ATTRIBUTE_FIELDS = ("diametre", "quantite", "espacement_mm", "longueur_mm")
OUTPUT_SCHEMA = "l2c-revision-comparison-v1"


class ExportError(ValueError):
    """Input file is not a supported L2C JSON information export."""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value)).strip()
    return normalized.casefold() if normalized else None


def _coordinate(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    # Coordinates exported from the same pipeline should be stable. Rounding
    # only removes floating-point serialization noise; there is no spatial
    # tolerance or nearest-neighbour association.
    return format(round(float(value), 6), ".6f")


def _record_parts(value: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("information")
    if isinstance(nested, dict):
        metadata = {key: item for key, item in value.items() if key != "information"}
        return nested, metadata
    return value, {}


def _level(info: dict[str, Any], metadata: dict[str, Any]) -> Any:
    for key in ("niveau", "level"):
        if key in metadata:
            return metadata[key]
        if key in info:
            return info[key]
    return None


def _document(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    # A path's parent can change between local runs. Keep the actual document
    # filename, not its directory, as the conservative source identity.
    return _text(Path(text.replace("\\", "/")).name)


def _observations(data: Any, side: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(data, dict):
        raw = data.get("records", data.get("informations"))
    else:
        raw = data
    if not isinstance(raw, list):
        raise ExportError(f"{side}: attendu une liste d'informations ou un objet records/informations.")

    observations: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for index, raw_record in enumerate(raw):
        parts = _record_parts(raw_record)
        if parts is None:
            invalid.append({"index": index, "reason": "entrée non objet JSON"})
            continue
        info, metadata = parts
        bars = info.get("armature")
        if not isinstance(bars, list) or not bars:
            invalid.append({"index": index, "id": info.get("id"), "reason": "aucune armature exploitable"})
            continue
        for bar_index, bar in enumerate(bars):
            if not isinstance(bar, dict):
                invalid.append({"index": index, "id": info.get("id"), "bar_index": bar_index,
                                "reason": "armature non objet JSON"})
                continue
            mark = bar.get("repere", info.get("repere"))
            candidate = {
                "document": _document(info.get("fichier", metadata.get("document"))),
                "feuillet": _text(info.get("feuillet", metadata.get("feuillet"))),
                "niveau": _text(_level(info, metadata)),
                "type_element": _text(info.get("type_element")),
                "element": _text(info.get("element")),
                "repere": _text(mark),
                "x": _coordinate(info.get("x")),
                "y": _coordinate(info.get("y")),
                "attributes": {field: bar.get(field) for field in ATTRIBUTE_FIELDS},
                "source_record": {"index": index, "id": info.get("id"), "bar_index": bar_index},
            }
            missing = [field for field in KEY_FIELDS if candidate[field] is None]
            candidate["missing_key_fields"] = missing
            observations.append(candidate)
    return observations, invalid


def _key(observation: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(observation[field] for field in KEY_FIELDS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_data(old_data: Any, new_data: Any, *, old_source: str = "<memory>",
                 new_source: str = "<memory>", old_sha256: str | None = None,
                 new_sha256: str | None = None) -> dict[str, Any]:
    old, old_invalid = _observations(old_data, "ancienne révision")
    new, new_invalid = _observations(new_data, "nouvelle révision")

    old_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    new_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in old:
        if not item["missing_key_fields"]:
            old_groups[_key(item)].append(item)
    for item in new:
        if not item["missing_key_fields"]:
            new_groups[_key(item)].append(item)

    matched_old: set[int] = set()
    matched_new: set[int] = set()
    ambiguous: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for key in sorted(old_groups.keys() | new_groups.keys(), key=repr):
        left, right = old_groups.get(key, []), new_groups.get(key, [])
        if len(left) > 1 or len(right) > 1:
            ambiguous.append({
                "status": "ambiguous_review_required",
                "key": dict(zip(KEY_FIELDS, key)),
                "old_sources": [item["source_record"] for item in left],
                "new_sources": [item["source_record"] for item in right],
                "reason": "Plusieurs observations partagent la même clé conservatrice; aucune association automatique.",
            })
            matched_old.update(id(item) for item in left)
            matched_new.update(id(item) for item in right)
            continue
        if not left or not right:
            continue
        before, after = left[0], right[0]
        matched_old.add(id(before))
        matched_new.add(id(after))
        changes = []
        for field in ATTRIBUTE_FIELDS:
            old_value, new_value = before["attributes"][field], after["attributes"][field]
            if old_value != new_value:
                changes.append({"attribute": field, "old": old_value, "new": new_value})
        candidates.append({
            "status": "change_candidate_review_required" if changes else "matched_no_attribute_change_detected",
            "key": dict(zip(KEY_FIELDS, key)),
            "old_source": before["source_record"],
            "new_source": after["source_record"],
            "attribute_changes": changes,
            "reason": "Candidat de changement à vérifier par une personne qualifiée." if changes else
                      "Clé identique et aucun changement détecté dans les attributs exportés.",
        })

    unmatched_old = []
    for item in old:
        if id(item) in matched_old:
            continue
        unmatched_old.append({"side": "old", "source": item["source_record"],
                              "partial_key": {field: item[field] for field in KEY_FIELDS},
                              "missing_key_fields": item["missing_key_fields"],
                              "reason": "Aucune contrepartie exacte; une observation retirée ne peut pas être déclarée manquante."})
    unmatched_new = []
    for item in new:
        if id(item) in matched_new:
            continue
        unmatched_new.append({"side": "new", "source": item["source_record"],
                              "partial_key": {field: item[field] for field in KEY_FIELDS},
                              "missing_key_fields": item["missing_key_fields"],
                              "reason": "Aucune contrepartie exacte; une observation ajoutée ne peut pas être déclarée non autorisée."})

    return {
        "schema": OUTPUT_SCHEMA,
        "decision_policy": "review_candidates_only_no_engineering_decisions",
        "sources": {
            "old": {"path": old_source, "sha256": old_sha256},
            "new": {"path": new_source, "sha256": new_sha256},
        },
        "matching_policy": {
            "key_fields": list(KEY_FIELDS),
            "attribute_fields_compared": list(ATTRIBUTE_FIELDS),
            "coordinate_policy": "Exact after rounding serialization noise to 6 decimal places; no spatial tolerance.",
            "document_policy": "Case-insensitive filename only; directory path is excluded.",
        },
        "summary": {
            "old_observations": len(old), "new_observations": len(new),
            "matched": len(candidates), "ambiguous": len(ambiguous),
            "unmatched_old": len(unmatched_old), "unmatched_new": len(unmatched_new),
            "invalid_old_entries": len(old_invalid), "invalid_new_entries": len(new_invalid),
        },
        "change_candidates": candidates,
        "ambiguous": ambiguous,
        "unmatched": {"old": unmatched_old, "new": unmatched_new},
        "invalid_entries": {"old": old_invalid, "new": new_invalid},
        "limitations": [
            "Les exports informations.json standards peuvent ne pas contenir le niveau; sans celui-ci les observations restent non appariées.",
            "Les observations non appariées ne prouvent ni un élément manquant ni un ajout non autorisé.",
            "Les différences et accords sont des candidats techniques; aucune validation d'ingénieur ou décision métier n'est produite.",
        ],
    }


def compare_files(old_path: Path, new_path: Path) -> dict[str, Any]:
    old_path, new_path = old_path.resolve(), new_path.resolve()
    try:
        old_data = json.loads(old_path.read_text(encoding="utf-8"))
        new_data = json.loads(new_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExportError(str(exc)) from exc
    return compare_data(old_data, new_data, old_source=str(old_path), new_source=str(new_path),
                        old_sha256=_sha256(old_path), new_sha256=_sha256(new_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_export", type=Path, help="informations.json de l'ancienne révision")
    parser.add_argument("new_export", type=Path, help="informations.json de la nouvelle révision")
    parser.add_argument("-o", "--output", type=Path, required=True, help="chemin du rapport JSON à créer")
    args = parser.parse_args(argv)
    try:
        report = compare_files(args.old_export, args.new_export)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ExportError, OSError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output.resolve()), "summary": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
