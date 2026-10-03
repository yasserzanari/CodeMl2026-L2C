# Local adjudication workflow

This workflow prepares annotation-pair review material from existing Concorde
`run.json` files. It is for human verification of identity and reinforcement
differences. It does not infer truth from the retriever, reconcile output, or OCR.

## Safety and operating rules

- Keep challenge PDFs, OCR text, reviewer packets, filled CSVs, and adjudicated
  labels on the local machine. The script refuses output paths inside this Git
  repository. Do not add these files to Git or share them outside the authorized
  challenge process.
- The script reads runs only. It copies no source PDF and changes no run,
  annotation, or label file. `--source-root` is optional and used only to hash
  source PDFs for lineage.
- One canonical run per project is required in a packet. Repeated projects are
  rejected so annotation IDs from multiple runs cannot be silently conflated.
- The supplied run must include a records array in Concorde's current schema:
  `information.id/source/fichier/feuillet/page/x/y/type_element/element/armature`
  plus extraction `box`, `raw`, `confidence`, identity and context fields. The
  run JSON itself is SHA-256 hashed. Optional source-PDF hashes are attached when
  a matching file exists under `--source-root`.
- OCR and normalized text in the packet are source evidence for the reviewer.
  A model suggestion is data to inspect, never an adjudicated label.
- A one-sided missing/added label is a claim of absence. Before using one, review
  the complete declared project/family scope in the original source documents;
  absence from OCR output or from the candidate list is not evidence of absence.

## 1. Prepare a reviewer packet

Run from the repository root in PowerShell. Choose a new destination outside
the repository. The input run JSONs are local Concorde run exports; repeat
`--run` for each distinct project.

```powershell
python .\scripts\prepare_adjudication.py prepare `
  --run "C:\path\to\local\run-a.json" `
  --run "C:\path\to\local\run-b.json" `
  --source-root "C:\path\to\local\project-pdfs" `
  --out "C:\Users\PC\Documents\l2c-review\packet-2026-10-03"
```

For one run, `--source-root` may be that project's root. For multiple runs, it
may be their common parent (for example, the directory containing each
project-ID folder). The resolver checks both layouts while ensuring paths stay
under that root. If the paths do not match, omit `--source-root`; the run
SHA-256 remains in `manifest.json`. No PDF is copied into the output.

The new directory contains:

- `review-packet.json`: source annotation inventory, run lineage, and candidate
  pair suggestions. Each record has source role/file/hash, sheet and page,
  PDF-point x/y and bounding box, raw and normalized OCR, confidence, extracted
  information, and extraction context.
- `review-template.csv`: one row per pair proposed by either candidate
  retrieval or automatic reconciliation. Columns beginning `machine_` are
  suggestions/provenance. Columns beginning `human_`, plus discrepancy,
  adjudicator, date, split and notes, are reserved for review. Source/page/OCR
  columns are evidence copied from the run.
- `manifest.json`: counts and run hashes for a compact handoff record.

The CSV is intentionally not an exhaustive list of possible pairs. To adjudicate
a pair the machine did not suggest, add a row and fill `plan_record_id`,
`atelier_record_id`, and the human fields. Find IDs in `review-packet.json`'s
`records` array. For a confirmed missing/added element, use only the appropriate
one-sided ID after checking the full relevant scope. Never label a blank or
unreviewed template row as a negative.

## 2. Fill the human fields

Allowed `human_outcome` values:

| Value | Meaning | Required record IDs |
|---|---|---|
| `same_identity` | The plan and shop-drawing annotations are the same physical/design element. | Both |
| `different_identity` | They are distinct elements despite the suggestion. | Both |
| `unresolved` | The relationship cannot be established from available evidence. | Both; add a reason in `notes` |
| `confirmed_missing_in_atelier` | The plan element has no counterpart in the reviewed shop-drawing scope. | Plan only; explain the exhaustive search in `notes` |
| `confirmed_added_in_atelier` | The shop-drawing element has no counterpart in the reviewed plan scope. | Atelier only; explain the exhaustive search in `notes` |

For `same_identity`, fill `confirmed_discrepancy_fields` with a semicolon-
separated subset of `diametre`, `quantite`, `espacement_mm`, and `longueur_mm`.
An empty value means the reviewer found no confirmed discrepancy among those
four fields after reviewing them; it does not mean missing or unreadable
attributes are equal. Only mark fields that the source drawings support. Use
`notes` for engineering interpretation or unreadable attributes. Non-empty
discrepancy fields are rejected for outcomes other than `same_identity`.

`adjudicator` is required for resolved outcomes. `reviewed_at` should be an ISO
date/time when practical. `group_id` should keep correlated cases together (by
default, the project). `split` is optional and should be assigned by project or
larger structure group, never randomly by page, annotation, or pair.

## 3. Validate and freeze a local label export

Validation skips rows whose `human_outcome` is blank, checks ID roles and
project consistency, rejects repeated relations and invalid field names, and
requires evidence notes for unresolved/missing/added cases. It writes a new
directory and preserves both input files unchanged.

```powershell
python .\scripts\prepare_adjudication.py validate `
  --packet "C:\Users\PC\Documents\l2c-review\packet-2026-10-03\review-packet.json" `
  --labels "C:\Users\PC\Documents\l2c-review\packet-2026-10-03\review-template.csv" `
  --out "C:\Users\PC\Documents\l2c-review\validated-2026-10-03"
```

Output `validated-labels.json` includes stable relation IDs, human outcomes,
run/packet/CSV hashes, and a flag indicating whether the relation was suggested
by the machine. This is still an annotation file, not an official benchmark
score.

## Label schema and stable identity

The packet schema is `l2c-adjudication-packet-v1`. Annotation IDs are taken from
the run and pair IDs are deterministic SHA-256 prefixes over
`project_id | plan_record_id | atelier_record_id`; a one-sided relation uses
`NO_PLAN` or `NO_ATELIER`. IDs remain stable when the same run records are
repackaged. Source changes require a new run and are visible through lineage
hashes.

The validated schema is `l2c-adjudicated-labels-v1`. Each label records project
and group, optional split, both source annotation IDs, a human outcome, confirmed
discrepancy fields, adjudicator metadata, notes, machine-suggestion provenance,
and the run JSON SHA-256.

## What metrics these labels can support

- Reviewing every machine-proposed pair in a declared scope supports pair
  precision for that scope (`same_identity` among proposed pairs).
- Exhaustively identifying all true plan-to-atelier identity links in that same
  scope, including links absent from machine suggestions, is necessary for
  pair recall. Add those missed links manually to the CSV. The automatically
  generated packet alone cannot establish recall.
- Comparing the machine's attribute-difference fields with human-confirmed
  fields supports discrepancy detection metrics only for identity-confirmed
  pairs and fields the reviewer could assess.
- A run contains extracted annotations only. Therefore these labels cannot
  measure elements missed by OCR/extraction, overall drawing-level recall,
  reliable missing/added rates, or official challenge performance without an
  independent exhaustive source review and an explicit scope denominator.
- Keep all pages/documents from one project or building in one split. With only
  a few projects, a page-level random split leaks near-duplicate drawing
  conventions and does not provide a trustworthy held-out estimate. Preserve a
  genuinely untouched project for final validation when available.

These limitations are intentional: the workflow records what reviewers actually
establish and does not convert incomplete coverage into performance claims.
