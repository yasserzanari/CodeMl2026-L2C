#!/usr/bin/env python3
"""Read-only coverage gate for the local Concorde L2C release artifacts.

The audit reads only the catalog cache and run/job/export metadata. It never
opens source PDFs or emits document names, OCR text, annotation content, or
project display names. Its JSON report is written only to the caller-selected
output directory (default: an ignored directory below data/l2c/app).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


EXPECTED_EXPORTS = ("informations.json", "comparaisons.json", "rapport.pdf")
REQUIRED_PACKAGES = (
    "fastapi", "uvicorn", "python-multipart", "pydantic", "pymupdf", "easyocr",
    "torch", "torchvision", "rapidocr-onnxruntime", "onnxruntime-gpu", "reportlab",
)
REQUIRED_PROJECTS = ("CLP", "EspCa3B", "LIGREP", "WP2")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def ignored_by_git(path: Path, workspace: Path) -> bool | None:
    """Return True/False where git is available, otherwise None."""
    try:
        relative = os.path.relpath(path, workspace)
        result = subprocess.run(
            ["git", "-C", str(workspace), "check-ignore", "-q", "--", relative],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except (OSError, ValueError):
        return None


def catalog_inventory(raw_root: Path, store_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Derive expected page inventory from fresh local catalog-cache entries."""
    catalog_path = store_root / "catalog.json"
    inventory: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {
        "available": catalog_path.is_file(),
        "sha256": sha256(catalog_path) if catalog_path.is_file() else None,
        "projects": {},
        "stale_entries": 0,
        "uncatalogued_pdfs": 0,
    }
    if not catalog_path.is_file():
        return inventory, summary
    try:
        cache = json_read(catalog_path)
    except (OSError, ValueError, TypeError):
        summary["available"] = False
        summary["error"] = "catalog_unreadable"
        return inventory, summary
    if not isinstance(cache, dict):
        summary["available"] = False
        summary["error"] = "catalog_not_object"
        return inventory, summary

    pdf_paths: list[Path] = []
    if raw_root.is_dir():
        for candidate in raw_root.rglob("*.pdf"):
            if candidate.is_file() and not candidate.is_symlink():
                pdf_paths.append(candidate)

    for pdf in pdf_paths:
        try:
            relative = pdf.resolve().relative_to(raw_root.resolve())
        except (OSError, ValueError):
            continue
        if len(relative.parts) < 2:
            continue
        project_id = relative.parts[0]
        # Catalog cache keys are absolute paths; never expose those paths in the report.
        cached = cache.get(str(pdf.resolve()))
        if not isinstance(cached, dict):
            summary["uncatalogued_pdfs"] += 1
            inventory.setdefault(project_id, {"documents": 0, "pages": 0, "plan_pages": 0,
                                               "atelier_pages": 0, "source_manifest": [],
                                               "_expected_page_keys": set(),
                                               "_expected_file_hashes": {},
                                               "fresh_documents": 0, "stale_documents": 0})
            inventory[project_id]["documents"] += 1
            continue
        try:
            stat = pdf.stat()
            stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            stamp = None
        fresh = stamp is not None and cached.get("stamp") == stamp
        project = inventory.setdefault(project_id, {"documents": 0, "pages": 0, "plan_pages": 0,
                                                       "atelier_pages": 0, "source_manifest": [],
                                                       "_expected_page_keys": set(),
                                                       "_expected_file_hashes": {},
                                                       "fresh_documents": 0, "stale_documents": 0})
        project["documents"] += 1
        if not fresh:
            project["stale_documents"] += 1
            summary["stale_entries"] += 1
            continue
        pages = cached.get("pages")
        digest = cached.get("sha256")
        if not isinstance(pages, int) or pages < 0 or not isinstance(digest, str):
            project["stale_documents"] += 1
            summary["stale_entries"] += 1
            continue
        project["fresh_documents"] += 1
        project["pages"] += pages
        # Match the application's role rule without including any document names.
        role = "atelier" if any(part.upper() in ("DA", "ATELIER") for part in relative.parts[:-1]) else "plan"
        project[f"{role}_pages"] += pages
        project["_expected_page_keys"].update(
            (relative.as_posix(), page_number) for page_number in range(1, pages + 1)
        )
        project["_expected_file_hashes"][relative.as_posix()] = digest
        project["source_manifest"].append((relative.as_posix(), digest, pages, role))

    for project_id, project in inventory.items():
        manifest = "\n".join("\t".join(map(str, row)) for row in sorted(project["source_manifest"]))
        project["source_manifest_sha256"] = hashlib.sha256(manifest.encode("utf-8")).hexdigest()
        del project["source_manifest"]
        project["catalog_complete"] = (
            project["documents"] > 0
            and project["fresh_documents"] == project["documents"]
            and project["stale_documents"] == 0
        )
        summary["projects"][project_id] = {
            key: value for key, value in project.items()
            if key not in ("source_manifest_sha256", "_expected_page_keys", "_expected_file_hashes")
        } | {"source_manifest_sha256": project["source_manifest_sha256"]}
    return inventory, summary


def page_coverage(run: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    pages = run.get("pages")
    if not isinstance(pages, list):
        pages = []
    expected_pages = expected.get("pages", 0)
    seen: set[tuple[str, int]] = set()
    source_counts = {"plan": 0, "atelier": 0, "other": 0}
    errors = 0
    skipped = 0
    source_hash_missing = 0
    source_hash_mismatch = 0
    malformed = 0
    for row in pages:
        if not isinstance(row, dict):
            malformed += 1
            continue
        filename = row.get("file")
        number = row.get("page")
        if isinstance(filename, str) and isinstance(number, int):
            normalized_filename = filename.replace("\\", "/")
            seen.add((normalized_filename, number))
            expected_hash = expected.get("_expected_file_hashes", {}).get(normalized_filename)
            actual_hash = row.get("source_sha256")
            if expected_hash:
                if not isinstance(actual_hash, str):
                    source_hash_missing += 1
                elif actual_hash != expected_hash:
                    source_hash_mismatch += 1
        else:
            malformed += 1
        source = row.get("source")
        source_counts[source if source in ("plan", "atelier") else "other"] += 1
        if row.get("method") == "error":
            errors += 1
        if row.get("method") == "skipped":
            skipped += 1
    statistics = run.get("statistics") if isinstance(run.get("statistics"), dict) else {}
    processed = statistics.get("pages_processed", len(pages))
    reported_total = statistics.get("pages_total")
    expected_keys = expected.get("_expected_page_keys", set())
    exact_file_page_coverage = seen == expected_keys if expected_keys else len(seen) == expected_pages
    return {
        "expected_pages": expected_pages,
        "page_rows": len(pages),
        "unique_file_page_pairs": len(seen),
        "statistics_pages_processed": processed,
        "statistics_pages_total": reported_total,
        "page_errors": errors,
        "page_skipped": skipped,
        "page_source_hash_missing": source_hash_missing,
        "page_source_hash_mismatch": source_hash_mismatch,
        "source_hashes_match_catalog": bool(expected.get("_expected_file_hashes"))
        and source_hash_missing == 0 and source_hash_mismatch == 0,
        "malformed_page_rows": malformed,
        "source_rows": source_counts,
        "missing_source_pages": len(expected_keys - seen) if expected_keys else None,
        "unexpected_source_pages": len(seen - expected_keys) if expected_keys else None,
        "exact_file_page_coverage": exact_file_page_coverage,
        "exact_page_count": len(pages) == expected_pages and len(seen) == expected_pages
        and exact_file_page_coverage,
        "processing_counts_consistent": processed == len(pages)
        and (reported_total is None or reported_total == expected_pages),
    }


def validate_information_export(path: Path, expected_records: int | None, workspace: Path) -> dict[str, Any]:
    """Check the delivered JSON against the app model without disclosing values."""
    try:
        values = json_read(path)
        if not isinstance(values, list):
            return {"valid": False, "records": None, "invalid_records": None, "reason": "not_array"}
        sys.path.insert(0, str(workspace))
        from l2c_app.models import Information

        invalid = 0
        identifiers: list[str] = []
        for value in values:
            try:
                parsed = Information.model_validate(value)
                identifiers.append(parsed.id)
            except Exception:
                invalid += 1
        count_matches = expected_records is None or len(values) == expected_records
        duplicate_ids = len(identifiers) - len(set(identifiers))
        return {"valid": invalid == 0 and count_matches and duplicate_ids == 0,
                "records": len(values), "invalid_records": invalid,
                "duplicate_ids": duplicate_ids, "count_matches_run": count_matches}
    except (OSError, ValueError, TypeError, ImportError):
        return {"valid": False, "records": None, "invalid_records": None,
                "reason": "unreadable_or_schema_unavailable"}


def inspect_runs(store_root: Path, inventory: dict[str, dict[str, Any]], workspace: Path) -> tuple[dict[str, Any], list[str]]:
    run_root = store_root / "runs"
    by_project: dict[str, list[dict[str, Any]]] = {project_id: [] for project_id in inventory}
    findings: list[str] = []
    if run_root.is_dir():
        for folder in run_root.iterdir():
            if not folder.is_dir():
                continue
            job_path, run_path = folder / "job.json", folder / "run.json"
            job: dict[str, Any] = {}
            run: dict[str, Any] = {}
            try:
                if job_path.is_file():
                    value = json_read(job_path)
                    if isinstance(value, dict):
                        job = value
            except (OSError, ValueError):
                findings.append("unreadable_job_metadata")
            try:
                if run_path.is_file():
                    value = json_read(run_path)
                    if isinstance(value, dict):
                        run = value
            except (OSError, ValueError):
                findings.append("unreadable_run_metadata")
            project_id = run.get("project_id") or job.get("project_id")
            if project_id not in by_project:
                continue
            expected = inventory[project_id]
            coverage = page_coverage(run, expected)
            exports: dict[str, Any] = {}
            for name in EXPECTED_EXPORTS:
                artifact = folder / name
                exports[name] = {
                    "present": artifact.is_file(),
                    "bytes": artifact.stat().st_size if artifact.is_file() else 0,
                    "sha256": sha256(artifact) if artifact.is_file() else None,
                }
            information_validation = (
                validate_information_export(
                    folder / "informations.json",
                    len(run.get("records", [])) if isinstance(run.get("records"), list) else None,
                    workspace,
                )
                if exports["informations.json"]["present"]
                else {"valid": False, "reason": "missing"}
            )
            scope = run.get("scope")
            complete_scope = scope == "complete"
            complete = (
                job.get("status") == "completed"
                and complete_scope
                and expected.get("catalog_complete", False)
                and coverage["exact_page_count"]
                and coverage["processing_counts_consistent"]
                and coverage["page_errors"] == 0
                and coverage["page_skipped"] == 0
                and coverage["source_hashes_match_catalog"]
                and coverage["malformed_page_rows"] == 0
                and information_validation["valid"]
                and all(item["present"] for item in exports.values())
            )
            item = {
                "run_id": folder.name,
                "created_at": run.get("created_at") or job.get("created_at"),
                "status": job.get("status", "unknown"),
                "scope": scope,
                "classification": "complete" if complete else "archival_partial_or_incomplete",
                "run_json_sha256": sha256(run_path) if run_path.is_file() else None,
                "job_json_sha256": sha256(job_path) if job_path.is_file() else None,
                "manifest_sha256": sha256(folder / "manifest.json") if (folder / "manifest.json").is_file() else None,
                "coverage": coverage,
                "exports": exports,
                "information_json_validation": information_validation,
                "model_prerequisites": run.get("config", {}),
            }
            by_project[project_id].append(item)

    result: dict[str, Any] = {}
    for project_id, runs in by_project.items():
        runs.sort(key=lambda item: (item["classification"] == "complete", item.get("created_at") or "",
                                    item.get("run_id", "")), reverse=True)
        complete_runs = [run for run in runs if run["classification"] == "complete"]
        result[project_id] = {
                "expected": {key: value for key, value in inventory[project_id].items()
                             if not key.startswith("_")},
            "runs": runs,
            "selected_complete_run_id": complete_runs[0]["run_id"] if complete_runs else None,
            "requirement_met": bool(complete_runs),
        }
    return result, findings


def runtime_inventory(workspace: Path) -> dict[str, Any]:
    packages: dict[str, Any] = {}
    for package in REQUIRED_PACKAGES:
        try:
            packages[package] = {"installed": True, "version": importlib.metadata.version(package)}
        except importlib.metadata.PackageNotFoundError:
            packages[package] = {"installed": False, "version": None}
    model_root = Path(os.environ.get("L2C_MODELS", workspace / "artifacts" / "l2c" / "models")).expanduser().resolve()
    model_files = [path for path in model_root.rglob("*") if path.is_file()] if model_root.is_dir() else []
    return {
        "python_version": sys.version.split()[0],
        "python_executable_fingerprint": hashlib.sha256(str(Path(sys.executable).resolve()).encode()).hexdigest(),
        "packages": packages,
        "model_store": {
            "present": model_root.is_dir(),
            "file_count": len(model_files),
            "total_bytes": sum(path.stat().st_size for path in model_files),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Workspace root (default: parent of scripts/).")
    parser.add_argument("--raw-root", type=Path, help="Source catalog root; default: <workspace>/data/l2c/raw.")
    parser.add_argument("--store-root", type=Path, help="Concorde store; default: <workspace>/data/l2c/app.")
    parser.add_argument("--output", type=Path, help="Ignored local output folder; default: <store-root>/audit-deliverables.")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    raw_root = (args.raw_root or workspace / "data" / "l2c" / "raw").resolve()
    store_root = (args.store_root or workspace / "data" / "l2c" / "app").resolve()
    output_root = (args.output or store_root / "audit-deliverables").resolve()
    if output_root == workspace or workspace not in output_root.parents:
        parser.error("--output doit se trouver dans l’espace de travail local.")
    ignore_state = ignored_by_git(output_root, workspace)
    if ignore_state is False:
        parser.error("Le dossier --output n'est pas ignoré par Git; choisissez un dossier local ignoré.")

    inventory, catalog_summary = catalog_inventory(raw_root, store_root)
    missing_projects = sorted(set(REQUIRED_PROJECTS) - set(inventory))
    unexpected_projects = sorted(set(inventory) - set(REQUIRED_PROJECTS))
    # The challenge's required set is explicit; only discovered provided projects contribute counts.
    runs, findings = inspect_runs(store_root, inventory, workspace)
    for project_id in missing_projects:
        runs[project_id] = {"expected": None, "runs": [], "selected_complete_run_id": None, "requirement_met": False}
    runtime = runtime_inventory(workspace)
    gate = all(runs.get(project_id, {}).get("requirement_met", False) for project_id in REQUIRED_PROJECTS)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "workspace_fingerprint": hashlib.sha256(str(workspace).encode()).hexdigest(),
        "roots": {
            "raw_root_fingerprint": hashlib.sha256(str(raw_root).encode()).hexdigest(),
            "store_root_fingerprint": hashlib.sha256(str(store_root).encode()).hexdigest(),
            "output_root_fingerprint": hashlib.sha256(str(output_root).encode()).hexdigest(),
            "output_ignored_by_git": ignore_state,
        },
        "required_projects": list(REQUIRED_PROJECTS),
        "missing_required_projects": missing_projects,
        "unexpected_catalog_projects": unexpected_projects,
        "catalog": catalog_summary,
        "projects": runs,
        "runtime_prerequisites": runtime,
        "gate": {
            "status": "complete_outputs_available" if gate else "incomplete",
            "passed": gate,
            "meaning": "Full-scope page coverage and JSON/PDF exports exist for each required local project.",
            "does_not_measure_accuracy": True,
            "findings": sorted(set(findings)),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "deliverable-audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Print only aggregate gate status and known project IDs; do not disclose source names or OCR.
    print(json.dumps({"report": str(report_path), "gate": report["gate"]["status"],
                      "required_projects": report["required_projects"],
                      "missing_required_projects": missing_projects}, ensure_ascii=False))
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
