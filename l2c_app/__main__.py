import argparse,json,time
from . import catalog,service

def main():
    parser=argparse.ArgumentParser(description='Concorde : analyse locale plan / atelier')
    parser.add_argument('--project',help='Identifiant du projet, affiché dans le dashboard')
    parser.add_argument('--profile',choices=['complete','native','sample'],default='complete')
    parser.add_argument('--max-ocr-pages',type=int,default=4)
    parser.add_argument('--list',action='store_true')
    args=parser.parse_args();catalog.refresh();service.recover()
    if args.list:print(json.dumps(catalog.projects(),ensure_ascii=False,indent=2));return
    if not args.project:parser.error('--project requis (ou --list)')
    job=service.start(args.project,{'profile':args.profile,'max_ocr_pages':args.max_ocr_pages})
    ident=job['id'];last=''
    while True:
        state=service.jobs[ident]
        message=f"{state['current']}/{state['total']} {state['message']}"
        if message!=last:print(message,flush=True);last=message
        if state['status'] not in ('running','queued'):break
        time.sleep(1)
    print(json.dumps(state,ensure_ascii=False,indent=2))
    if state['status']!='completed':raise SystemExit(1)

if __name__=='__main__':main()
