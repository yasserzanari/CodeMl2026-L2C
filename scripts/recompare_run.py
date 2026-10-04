"""Reconcile saved extractions into a NEW run, without OCR or modifying its source."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args=parser.parse_args()
    from l2c_app.config import STORE,write_json
    from l2c_app.matching import reconcile,statistics
    from l2c_app.reports import export
    # IDs are directory names from the registry, never arbitrary paths.
    if not args.run_id.isalnum():parser.error('Identifiant d’analyse invalide.')
    source=STORE/'runs'/args.run_id
    if not (source/'run.json').is_file():parser.error('Analyse source introuvable.')
    old=json.loads((source/'run.json').read_text('utf8'))
    source_job=json.loads((source/'job.json').read_text('utf8'))
    if source_job.get('status')!='completed':parser.error('Analyse source non terminée.')
    ident=uuid.uuid4().hex;now=datetime.now(timezone.utc).isoformat()
    results=reconcile(old['records'])
    run={k:v for k,v in old.items() if k not in ('id','created_at','results','statistics')}
    run.update(id=ident,created_at=now,results=results,
               statistics=statistics(old['records'],results,old['pages']),
               reconciliation_source={'run_id':args.run_id,'sha256':hashlib.sha256((source/'run.json').read_bytes()).hexdigest(),
                                      'reviews':'Les décisions restent dans l’analyse source et ne sont pas transférées automatiquement.'})
    folder=STORE/'runs'/ident;folder.mkdir(parents=True,exist_ok=False)
    job=source_job|{'id':ident,'created_at':now,'status':'reporting','stage':'reporting','message':'Nouveau rapprochement sans OCR','statistics':run['statistics']}
    write_json(folder/'job.json',job)
    try:
        write_json(folder/'run.json',run);export(run,folder)
    except Exception as exc:
        job.update(status='failed',message=str(exc)[:500]);write_json(folder/'job.json',job)
        raise
    job.update(status='completed',stage='completed',message='Rapprochement recalculé sans OCR ; décisions conservées dans l’analyse source.')
    write_json(folder/'job.json',job)
    print(json.dumps({'run_id':ident,'source_run_id':args.run_id,'counts':run['statistics']['counts'],
                      'notice':'Redémarrer le serveur une fois ses analyses terminées pour afficher cette analyse.'},ensure_ascii=False))


if __name__=='__main__':main()
