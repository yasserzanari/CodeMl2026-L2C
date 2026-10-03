"""Run complete local analyses serially for selected Concorde projects.

The script uses only the configured local catalogue, OCR models and run store.
It does not download models or contact a remote service.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "http://127.0.0.1:8765"
STORE = Path(os.environ.get("L2C_STORE", ROOT / "data/l2c/app")).expanduser().resolve()


def api_json(path, method="GET", value=None):
    data = None if value is None else json.dumps(value).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers.update({"Content-Type": "application/json", "X-Concorde-Request": "1"})
    request = Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", str(exc))
        except (ValueError, AttributeError):
            detail = str(exc)
        raise RuntimeError(f"API locale HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError("Serveur Concorde local indisponible. Lancez .\\start-concorde.ps1.") from exc


def completed_projects(store):
    completed = set()
    for job_path in (store / "runs").glob("*/job.json"):
        try:
            job = json.loads(job_path.read_text("utf-8"))
            run_path = job_path.with_name("run.json")
            if job.get("status") != "completed" or not run_path.exists():
                continue
            run = json.loads(run_path.read_text("utf-8"))
            stats = run.get("statistics") or {}
            pages = run.get("pages") or []
            exports = all((job_path.parent / name).is_file() for name in (
                "informations.json", "comparaisons.json", "rapport.pdf"
            ))
            if (run.get("scope") == "complete"
                    and stats.get("pages_processed") == stats.get("pages_total")
                    and stats.get("pages_error", 0) == 0
                    and stats.get("pages_skipped", 0) == 0
                    and len(pages) == stats.get("pages_total")
                    and exports):
                completed.add(run.get("project_id"))
        except (OSError, ValueError):
            continue
    return completed


def main():
    parser = argparse.ArgumentParser(
        description="Lance les analyses OCR complètes en local, une à la fois."
    )
    parser.add_argument("--project", action="append", dest="projects", metavar="ID",
                        help="ID de projet du catalogue; répétable")
    parser.add_argument("--list", action="store_true", help="afficher le catalogue local")
    parser.add_argument("--skip-completed", action="store_true",
                        help="ignorer les projets qui ont déjà un run complet terminé")
    args = parser.parse_args()

    try:
        overview = api_json("/api/overview")
    except RuntimeError as exc:
        parser.error(str(exc))
    available = overview.get("projects", [])
    by_id = {project["id"]: project for project in available}
    if args.list:
        for project in available:
            print(f"{project['id']}\t{project['name']}\t{project['pages']} pages")
        return 0
    if not args.projects:
        parser.error("indiquez --project ID (ou --list pour voir le catalogue)")
    unknown = sorted(set(args.projects) - set(by_id))
    if unknown:
        parser.error("ID introuvable dans le catalogue : " + ", ".join(unknown))
    if len(set(args.projects)) != len(args.projects):
        parser.error("chaque ID de projet ne doit apparaître qu’une fois")

    active = [job for job in overview.get("jobs", [])
              if job.get("status") in ("queued", "running")]
    if active:
        parser.error("une autre analyse est déjà en cours; attendez sa fin avant le lot")

    already_complete = completed_projects(STORE) if args.skip_completed else set()
    selected = [project_id for project_id in args.projects
                if project_id not in already_complete]
    for project_id in args.projects:
        if project_id in already_complete:
            print(f"IGNORÉ {by_id[project_id]['name']} : run complet déjà terminé")
    if not selected:
        print("Aucun nouveau run à lancer.")
        return 0

    for project_id in selected:
        project = by_id[project_id]
        try:
            job = api_json(f"/api/projects/{project_id}/analyse", method="POST",
                           value={"profile": "complete", "max_ocr_pages": 1000})
        except (RuntimeError, ValueError) as exc:
            print(f"ARRÊT {project['name']} — {exc}", file=sys.stderr)
            return 1
        print(f"DÉMARRÉ {project['name']} — {project['pages']} pages — run {job['id']}", flush=True)
        last_report = 0.0
        try:
            while True:
                time.sleep(1)
                current = api_json(f"/api/jobs/{job['id']}")
                now = time.monotonic()
                if now - last_report >= 5 or current["status"] not in ("queued", "running"):
                    print(f"  {current['current']}/{current['total']} pages — "
                          f"{current['status']} — {current.get('message', '')}", flush=True)
                    last_report = now
                if current["status"] not in ("queued", "running"):
                    break
        except KeyboardInterrupt:
            try:
                api_json(f"/api/jobs/{job['id']}/cancel", method="POST", value={})
            except (RuntimeError, ValueError):
                print("Impossible de confirmer la demande d’arrêt; vérifiez le tableau de bord.",
                      file=sys.stderr, flush=True)
                return 1
            print("Arrêt demandé; la page en cours se terminera avant l’arrêt.", flush=True)
            while True:
                time.sleep(1)
                current = api_json(f"/api/jobs/{job['id']}")
                if current["status"] not in ("queued", "running"):
                    break

        if current["status"] != "completed":
            print(f"ARRÊT {project['name']} — {current['status']}: {current.get('message', '')}",
                  file=sys.stderr)
            return 1
        folder = STORE / "runs" / job["id"]
        print(f"TERMINÉ {project['name']} — JSON: {folder / 'informations.json'}")
        print(f"  Comparaisons: {folder / 'comparaisons.json'}")
        print(f"  Rapport: {folder / 'rapport.pdf'}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
