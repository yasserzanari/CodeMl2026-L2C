# Concorde L2C deliverable coverage gate

This command inventories local release evidence for the four provided projects (CLP, EspCa3B, LIGREP, WP2). It derives expected file/page pairs and source hashes from fresh catalog entries, classifies each saved run as complete or archival/partial, checks that run page hashes match the current PDFs, checks the three generated export artifacts, and validates each information row against Concorde's current `Information` model. It records SHA-256 digests for catalog, run/job metadata, optional manifests, and exports. The only write is the caller-selected audit JSON.

The report contains project IDs and aggregate counts only. It does not open source PDFs, print source file names, or include OCR text, annotation content, or display names. It does not modify the catalog, saved runs, source documents, or exports. The only write is the JSON report in the selected local output folder.

## Run the gate

From the workspace root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\audit_deliverables.py
$LASTEXITCODE
```

The default output is `data/l2c/app/audit-deliverables/deliverable-audit.json`, under the workspace's ignored local data. Exit code `0` means each required project has a completed run with `scope: complete`, exact source-file/page coverage and matching source SHA-256 values against fresh catalog entries, no skipped/error pages, valid `informations.json` rows matching the run record count with unique IDs, and all three exports (`informations.json`, `comparaisons.json`, `rapport.pdf`). Exit code `1` means at least one project is missing a complete set. Invalid roots or a non-ignored output path are command errors.

To audit an explicitly selected local store and output location:

```powershell
python scripts/audit_deliverables.py `
  --workspace "C:\path\to\workspace" `
  --raw-root "C:\path\to\workspace\data\l2c\raw" `
  --store-root "C:\path\to\workspace\data\l2c\app" `
  --output "C:\path\to\workspace\data\l2c\app\audit-deliverables"
```

The output location must stay under `--workspace` and be ignored by Git. The command reports aggregate runtime package versions and whether the local model store has files; it does not download, initialize, or validate the model contents.

## What the gate establishes

- Catalog page totals come from local `catalog.json` entries whose cached file stamp still matches the local source file metadata. Missing or stale entries prevent a completeness pass; source PDFs are not opened to repair the cache.
- A run is complete only when its saved job is completed, its run scope is `complete`, every expected source file/page pair occurs exactly once with the same SHA-256 as the current catalog, no page is skipped, errored, or malformed, the processed counts agree, the information JSON validates against the current Pydantic model and row count with unique IDs, and all expected export files exist. Partial, sample, native-only, old runs without per-page source hashes, failed, and interrupted runs remain in the report as archival/partial evidence.
- Digests support later integrity checks for the listed local artifacts. They do not certify authorship, semantic correctness, or that the source set itself is the intended official set.

## What it cannot establish

- **Detection quality or semantic correctness.** A zero-alert report is not evidence of accuracy. Precision, recall, conformity labels, missing/additional element decisions, and matching correctness require engineer-adjudicated ground truth and independent evaluation.
- **The jury evaluation project.** The fifth project is not in this local catalog, so this gate cannot measure its runtime, coverage, or performance.
- **Successful execution on a clean machine.** Dependency versions and model-store presence are an inventory of this Python environment and workspace only. Reproducible offline installation and live execution still need a separate clean-machine rehearsal.
- **PDF content completeness.** Exact page counts establish coverage of pages listed by the local catalog, not that all official source files were supplied, readable by humans, or correctly classified as plan versus atelier.
