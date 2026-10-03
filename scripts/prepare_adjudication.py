"""Prepare and validate local human-adjudication packets for Concorde runs.

The script never reads source PDFs unless --source-root is explicitly supplied,
never modifies runs, and never treats machine suggestions as adjudicated labels.
Generated packets can contain challenge document OCR and must stay outside Git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = {
    "same_identity",
    "different_identity",
    "unresolved",
    "confirmed_missing_in_atelier",
    "confirmed_added_in_atelier",
}
DISCREPANCY_FIELDS = {"diametre", "quantite", "espacement_mm", "longueur_mm"}
CSV_FIELDS = [
    "pair_id", "project_id", "family", "plan_record_id", "atelier_record_id",
    "machine_sources", "machine_evidence_json", "machine_warnings_json",
    "machine_result_ids", "machine_statuses", "machine_differences_json",
    "plan_source_file", "plan_source_sha256", "plan_sheet", "plan_page",
    "plan_x", "plan_y", "plan_box_json", "plan_raw",
    "atelier_source_file", "atelier_source_sha256", "atelier_sheet", "atelier_page",
    "atelier_x", "atelier_y", "atelier_box_json", "atelier_raw",
    "human_outcome", "confirmed_discrepancy_fields", "adjudicator", "reviewed_at",
    "group_id", "split", "notes",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pair_id(project_id: str, plan_id: str | None, atelier_id: str | None) -> str:
    seed = "|".join((project_id, plan_id or "NO_PLAN", atelier_id or "NO_ATELIER"))
    return "pair_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def safe_source_path(root: Path, project_id: str, relative: str) -> Path | None:
    """Resolve either one project's root or the common root of several projects."""
    resolved_root = root.resolve()
    for candidate in ((root / relative).resolve(), (root / project_id / relative).resolve()):
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def validate_run_shape(run: Any, path: Path) -> None:
    if not isinstance(run, dict) or not isinstance(run.get("records"), list):
        raise ValueError(f"{path}: expected a Concorde run JSON with a records array")
    if not run.get("project_id") or not run.get("id"):
        raise ValueError(f"{path}: project_id and id are required")
    for index, record in enumerate(run["records"]):
        info = record.get("information", {}) if isinstance(record, dict) else {}
        if not info.get("id") or info.get("source") not in ("plan", "atelier"):
            raise ValueError(f"{path}: invalid information.id/source in records[{index}]")


def load_inputs(run_paths: list[Path], source_root: Path | None) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    projects: set[str] = set()
    runs: list[dict] = []
    records_by_id: dict[str, dict] = {}
    record_run: dict[str, dict] = {}
    source_hashes: dict[tuple[str, str], str | None] = {}
    for path in run_paths:
        path = path.resolve()
        run = json.loads(path.read_text(encoding="utf-8"))
        validate_run_shape(run, path)
        project_id = str(run["project_id"])
        if project_id in projects:
            raise ValueError(f"More than one run for project {project_id!r}; choose one canonical run per project")
        projects.add(project_id)
        lineage = {
            "run_id": run["id"],
            "project_id": project_id,
            "project_name": run.get("project_name"),
            "scope": run.get("scope"),
            "run_json_path": str(path),
            "run_json_sha256": sha256_file(path),
        }
        runs.append({"data": run, "lineage": lineage})
        for page in run.get("pages", []):
            relative = page.get("file")
            key = (project_id, str(relative)) if relative else None
            if source_root and key and key not in source_hashes:
                source = safe_source_path(source_root, project_id, str(relative))
                source_hashes[key] = sha256_file(source) if source else None
        for record in run["records"]:
            info = record["information"]
            ident = str(info["id"])
            if ident in records_by_id:
                raise ValueError(f"Duplicate annotation ID {ident!r}; runs must have unique IDs")
            source_file = str(info.get("fichier", ""))
            source_sha = None
            if source_root and source_file:
                source_key = (project_id, source_file)
                if source_key not in source_hashes:
                    source = safe_source_path(source_root, project_id, source_file)
                    source_hashes[source_key] = sha256_file(source) if source else None
                source_sha = source_hashes[source_key]
            # Keep source evidence and extracted fields together. This is an inventory,
            # not a label. No source PDF is copied into the packet.
            entry = {
                "record_id": ident,
                "project_id": project_id,
                "run_id": run["id"],
                "source": info["source"],
                "source_file": source_file,
                "source_sha256": source_sha,
                "sheet": info.get("feuillet"),
                "page": info.get("page"),
                "x": info.get("x"),
                "y": info.get("y"),
                "box": record.get("box"),
                "raw_ocr": record.get("raw"),
                "normalized_ocr": record.get("normalized"),
                "method": record.get("method"),
                "confidence": record.get("confidence"),
                "information": info,
                "extraction_context": {k: record.get(k) for k in (
                    "level", "role", "phase", "anchor_kind", "identity_resolved", "multiplicities"
                )},
            }
            records_by_id[ident] = entry
            record_run[ident] = {"run": run, "record": record, "lineage": lineage}
    return runs, records_by_id, record_run


def build_suggestions(runs: list[dict], record_run: dict[str, dict], max_candidates: int) -> list[dict]:
    # Import the same deterministic, conservative retrieval function used in the app.
    sys.path.insert(0, str(REPO_ROOT))
    from l2c_app.pairing import candidates

    suggestions: dict[tuple[str, str], dict] = {}

    def add(plan_id: str, atelier_id: str, source: str, evidence: list | None = None,
            warnings: list | None = None, result: dict | None = None) -> None:
        key = (plan_id, atelier_id)
        row = suggestions.setdefault(key, {"plan_record_id": plan_id, "atelier_record_id": atelier_id,
                                           "sources": [], "evidence": [], "warnings": [],
                                           "automatic_results": []})
        if source not in row["sources"]:
            row["sources"].append(source)
        for item in evidence or []:
            if item not in row["evidence"]:
                row["evidence"].append(item)
        for item in warnings or []:
            if item not in row["warnings"]:
                row["warnings"].append(item)
        if result and all(x["result_id"] != result["id"] for x in row["automatic_results"]):
            row["automatic_results"].append({"result_id": result["id"], "status": result.get("status"),
                                               "differences": result.get("differences", [])})

    for item in runs:
        run = item["data"]
        project_id = str(run["project_id"])
        records = run["records"]
        for plan in records:
            if plan["information"]["source"] != "plan":
                continue
            for candidate in candidates(plan, records, limit=max_candidates):
                add(str(plan["information"]["id"]), str(candidate["record_id"]),
                    "retrieval_candidate", candidate.get("evidence"), candidate.get("warnings"))
        # Preserve automatic groupings as inspectable suggestions, including cases the
        # retrieval helper did not rank. Large ambiguous groups are not expanded.
        by_id = {str(r["information"]["id"]): r for r in records}
        for result in run.get("results", []):
            plans = result.get("plan_ids", [])
            ateliers = result.get("atelier_ids", [])
            if plans and ateliers and len(plans) * len(ateliers) <= 100:
                for left in plans:
                    for right in ateliers:
                        if left in by_id and right in by_id:
                            add(str(left), str(right), "automatic_reconciliation", result=result)

    output = []
    for (plan_id, atelier_id), row in sorted(suggestions.items()):
        project_id = record_run[plan_id]["lineage"]["project_id"]
        output.append({"pair_id": pair_id(project_id, plan_id, atelier_id), **row})
    return output


def csv_row(suggestion: dict, records: dict[str, dict]) -> dict[str, str]:
    plan = records[suggestion["plan_record_id"]]
    atelier = records[suggestion["atelier_record_id"]]
    result = {
        "pair_id": suggestion["pair_id"], "project_id": plan["project_id"],
        "family": str(plan["information"].get("type_element", "")),
        "plan_record_id": plan["record_id"], "atelier_record_id": atelier["record_id"],
        "machine_sources": ";".join(suggestion["sources"]),
        "machine_evidence_json": json.dumps(suggestion["evidence"], ensure_ascii=False),
        "machine_warnings_json": json.dumps(suggestion["warnings"], ensure_ascii=False),
        "machine_result_ids": ";".join(x["result_id"] for x in suggestion["automatic_results"]),
        "machine_statuses": ";".join(x["status"] or "" for x in suggestion["automatic_results"]),
        "machine_differences_json": json.dumps([x for row in suggestion["automatic_results"]
                                                  for x in row["differences"]], ensure_ascii=False),
    }
    for prefix, record in (("plan", plan), ("atelier", atelier)):
        result.update({
            f"{prefix}_source_file": record["source_file"],
            f"{prefix}_source_sha256": record["source_sha256"] or "",
            f"{prefix}_sheet": record["sheet"] or "",
            f"{prefix}_page": str(record["page"] or ""),
            f"{prefix}_x": str(record["x"] if record["x"] is not None else ""),
            f"{prefix}_y": str(record["y"] if record["y"] is not None else ""),
            f"{prefix}_box_json": json.dumps(record["box"], ensure_ascii=False),
            f"{prefix}_raw": record["raw_ocr"] or "",
        })
    for field in CSV_FIELDS:
        result.setdefault(field, "")
    # Suggestions remain visibly unreviewed; all annotation fields were derived from a run.
    for field in ("human_outcome", "confirmed_discrepancy_fields", "adjudicator", "reviewed_at", "split", "notes"):
        result[field] = ""
    result["group_id"] = plan["project_id"]
    return result


def ensure_external_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        raise ValueError(f"Output must be outside the repository: {resolved}")
    if resolved.exists():
        raise FileExistsError(f"Output already exists; choose a new directory: {resolved}")
    return resolved


def prepare(args: argparse.Namespace) -> None:
    out = ensure_external_output(args.out)
    source_root = args.source_root.expanduser().resolve() if args.source_root else None
    runs, records, record_run = load_inputs(args.run, source_root)
    suggestions = build_suggestions(runs, record_run, args.max_candidates)
    packet = {
        "schema_version": "l2c-adjudication-packet-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Human review packet. Machine suggestions are not ground truth.",
        "lineage": [item["lineage"] for item in runs],
        "source_root": str(source_root) if source_root else None,
        "records": list(records.values()),
        "machine_suggestions": suggestions,
        "limits": [
            "Only annotations present in the supplied run are catalogued; missed source elements are absent.",
            "Candidate pairs and automatic verdicts are suggestions, never human labels.",
            "A missing/added outcome requires review of the complete declared project/family scope.",
        ],
    }
    out.mkdir(parents=True)
    (out / "review-packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "review-template.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for suggestion in suggestions:
            writer.writerow(csv_row(suggestion, records))
    hashed_sources = {(r["source_file"], r["source_sha256"]) for r in records.values()
                      if r["source_sha256"]}
    manifest = {"packet": "review-packet.json", "template": "review-template.csv",
                "runs": [item["lineage"] for item in runs], "record_count": len(records),
                "suggestion_count": len(suggestions), "source_files_hashed": len(hashed_sources),
                "source_file_hashes_missing": sorted({r["source_file"] for r in records.values()
                                                       if source_root and not r["source_sha256"]})}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), **manifest}, ensure_ascii=False, indent=2))


def validate(args: argparse.Namespace) -> None:
    packet_path = args.packet.resolve()
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if packet.get("schema_version") != "l2c-adjudication-packet-v1":
        raise ValueError("Unsupported packet schema_version")
    records = {str(r["record_id"]): r for r in packet.get("records", [])}
    run_for_project = {str(x["project_id"]): x for x in packet.get("lineage", [])}
    label_path = args.labels.resolve()
    validated = []
    seen: set[str] = set()
    with label_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing_columns = {"plan_record_id", "atelier_record_id", "human_outcome", "confirmed_discrepancy_fields"} - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError("Missing label columns: " + ", ".join(sorted(missing_columns)))
        for line, row in enumerate(reader, start=2):
            plan_id = (row.get("plan_record_id") or "").strip() or None
            atelier_id = (row.get("atelier_record_id") or "").strip() or None
            outcome = (row.get("human_outcome") or "").strip()
            if not outcome:
                continue  # Unreviewed template row, not a negative label.
            if outcome not in OUTCOMES:
                raise ValueError(f"{label_path}:{line}: invalid human_outcome {outcome!r}")
            if not plan_id and not atelier_id:
                raise ValueError(f"{label_path}:{line}: at least one record ID is required")
            if plan_id and plan_id not in records:
                raise ValueError(f"{label_path}:{line}: unknown plan_record_id {plan_id!r}")
            if atelier_id and atelier_id not in records:
                raise ValueError(f"{label_path}:{line}: unknown atelier_record_id {atelier_id!r}")
            if plan_id and records[plan_id]["source"] != "plan":
                raise ValueError(f"{label_path}:{line}: plan_record_id must refer to a plan annotation")
            if atelier_id and records[atelier_id]["source"] != "atelier":
                raise ValueError(f"{label_path}:{line}: atelier_record_id must refer to an atelier annotation")
            if outcome in {"same_identity", "different_identity"} and not (plan_id and atelier_id):
                raise ValueError(f"{label_path}:{line}: {outcome} requires both source IDs")
            if outcome == "confirmed_missing_in_atelier" and not (plan_id and not atelier_id):
                raise ValueError(f"{label_path}:{line}: confirmed_missing_in_atelier requires only a plan ID")
            if outcome == "confirmed_added_in_atelier" and not (atelier_id and not plan_id):
                raise ValueError(f"{label_path}:{line}: confirmed_added_in_atelier requires only an atelier ID")
            if outcome == "unresolved" and not (plan_id and atelier_id):
                raise ValueError(f"{label_path}:{line}: unresolved requires a candidate pair")
            project_id = (row.get("project_id") or (records[plan_id]["project_id"] if plan_id else records[atelier_id]["project_id"])).strip()
            if plan_id and records[plan_id]["project_id"] != project_id:
                raise ValueError(f"{label_path}:{line}: plan_record_id does not belong to project {project_id!r}")
            if atelier_id and records[atelier_id]["project_id"] != project_id:
                raise ValueError(f"{label_path}:{line}: atelier_record_id does not belong to project {project_id!r}")
            if plan_id and atelier_id and records[plan_id]["project_id"] != records[atelier_id]["project_id"]:
                raise ValueError(f"{label_path}:{line}: a pair cannot cross projects")
            if project_id not in run_for_project:
                raise ValueError(f"{label_path}:{line}: unknown project_id {project_id!r}")
            pair = pair_id(project_id, plan_id, atelier_id)
            supplied_pair_id = (row.get("pair_id") or "").strip()
            if supplied_pair_id and supplied_pair_id != pair:
                raise ValueError(f"{label_path}:{line}: pair_id does not match the supplied record IDs")
            if pair in seen:
                raise ValueError(f"{label_path}:{line}: duplicate adjudicated relation {pair}")
            seen.add(pair)
            raw_fields = (row.get("confirmed_discrepancy_fields") or "").strip()
            fields = sorted({x.strip() for x in raw_fields.replace(",", ";").split(";") if x.strip()})
            unknown = set(fields) - DISCREPANCY_FIELDS
            if unknown:
                raise ValueError(f"{label_path}:{line}: unsupported discrepancy fields {sorted(unknown)}")
            if fields and outcome != "same_identity":
                raise ValueError(f"{label_path}:{line}: discrepancy fields require same_identity")
            if outcome in {"same_identity", "different_identity", "confirmed_missing_in_atelier", "confirmed_added_in_atelier"} and not (row.get("adjudicator") or "").strip():
                raise ValueError(f"{label_path}:{line}: adjudicator is required for a resolved outcome")
            if outcome in {"confirmed_missing_in_atelier", "confirmed_added_in_atelier"} and not (row.get("notes") or "").strip():
                raise ValueError(f"{label_path}:{line}: evidence/scope note required to confirm absence")
            if outcome == "unresolved" and not (row.get("notes") or "").strip():
                raise ValueError(f"{label_path}:{line}: note the reason the pair remains unresolved")
            validated.append({
                "pair_id": pair, "project_id": project_id, "group_id": (row.get("group_id") or project_id).strip(),
                "split": (row.get("split") or "").strip() or None,
                "plan_record_id": plan_id, "atelier_record_id": atelier_id,
                "human_outcome": outcome, "confirmed_discrepancy_fields": fields,
                "adjudicator": (row.get("adjudicator") or "").strip() or None,
                "reviewed_at": (row.get("reviewed_at") or "").strip() or None,
                "notes": (row.get("notes") or "").strip() or None,
                "machine_suggestion": any(s.get("pair_id") == pair for s in packet.get("machine_suggestions", [])),
                "source_run_sha256": run_for_project[project_id]["run_json_sha256"],
            })
    output = ensure_external_output(args.out)
    output.mkdir(parents=True)
    result = {
        "schema_version": "l2c-adjudicated-labels-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_packet": str(packet_path),
        "source_labels_csv": str(label_path),
        "source_packet_sha256": sha256_file(packet_path),
        "source_labels_sha256": sha256_file(label_path),
        "scope_warning": "Labels apply only to annotations present in supplied runs. Pair precision/recall requires a declared exhaustive scope and independently enumerated ground truth.",
        "labels": validated,
        "counts": {outcome: sum(x["human_outcome"] == outcome for x in validated) for outcome in sorted(OUTCOMES)},
    }
    (output / "validated-labels.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "labels": len(validated), "counts": result["counts"]}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="Create a local reviewer packet and blank CSV template")
    prep.add_argument("--run", type=Path, action="append", required=True, help="Concorde run JSON; repeat for separate projects")
    prep.add_argument("--out", type=Path, required=True, help="New output directory outside the repository")
    prep.add_argument("--source-root", type=Path, help="Optional local PDF root; hashes matched source files, copies nothing")
    prep.add_argument("--max-candidates", type=int, default=8)
    prep.set_defaults(func=prepare)
    check = sub.add_parser("validate", help="Validate a filled CSV without changing the original packet or labels")
    check.add_argument("--packet", type=Path, required=True)
    check.add_argument("--labels", type=Path, required=True)
    check.add_argument("--out", type=Path, required=True, help="New output directory outside the repository")
    check.set_defaults(func=validate)
    args = parser.parse_args()
    if getattr(args, "max_candidates", 1) < 1:
        parser.error("--max-candidates must be at least 1")
    try:
        args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
