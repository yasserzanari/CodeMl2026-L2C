"""Isolated synthetic import/OCR/review/export/recovery integration check.
Requires installed local weights. No challenge documents are accessed.
"""
from pathlib import Path
import argparse,os,tempfile,sys,time,json,io,hashlib

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--models',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():raise RuntimeError('Preserve prior checks: choose a new output filename')
    with tempfile.TemporaryDirectory(prefix='concorde-flow-') as directory:
        os.environ.update(L2C_DATA=str(Path(directory)/'raw'),L2C_STORE=str(Path(directory)/'store'),L2C_MODELS=str(args.models.resolve()))
        sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
        import pymupdf as fitz
        from PIL import Image,ImageDraw,ImageFont
        from fastapi.testclient import TestClient
        from l2c_app.server import app
        from l2c_app import service,catalog
        from l2c_app.config import STORE,DEFAULTS
        from l2c_app.models import Information
        font_path=Path('C:/Windows/Fonts/arial.ttf')
        font=ImageFont.truetype(str(font_path) if font_path.exists() else 'DejaVuSans.ttf',30)
        def fixture(quantity):
            with fitz.open() as pdf:
                p=pdf.new_page(width=550,height=400)
                p.insert_text((40,60),'COLONNE NIVEAU 1 C-99',fontsize=14)
                p.insert_text((40,85),f'{quantity}-20M',fontsize=16)
                p.insert_text((40,280),'SYNTHETIC DOCUMENT FOR LOCAL INTEGRATION CHECK ONLY. '*3,fontsize=4)
                image=Image.new('RGB',(1100,800),'white');draw=ImageDraw.Draw(image)
                draw.text((80,110),'COLONNE NIVEAU 1',font=font,fill='black')
                draw.text((80,180),'C-98',font=font,fill='black')
                draw.text((80,220),f'{quantity}-20M',font=font,fill='black')
                buf=io.BytesIO();image.save(buf,format='PNG')
                p=pdf.new_page(width=550,height=400);p.insert_image(p.rect,stream=buf.getvalue())
                return pdf.tobytes()
        originals=[fixture(7),fixture(9)];checks=[];headers={'X-Concorde-Request':'1'}
        with TestClient(app) as client:
            response=client.post('/api/import',headers=headers,data={'name':'Synthetic flow'},files=[
                ('plans',('plan-colonne-NIV1.pdf',originals[0],'application/pdf')),
                ('atelier',('atelier-colonne-NIV1.pdf',originals[1],'application/pdf'))])
            assert response.status_code==201,response.text
            project=response.json()['id']
            for engine in ('easyocr','rapidocr'):
                config=DEFAULTS|{'ocr_engine':engine,'ocr_rotations':False,'batch_size':4,'pairing_assistance':True}
                assert client.post('/api/settings',headers=headers,json=config).status_code==200
                response=client.post(f'/api/projects/{project}/analyse',headers=headers,json={'profile':'complete'})
                assert response.status_code==202,response.text
                ident=response.json()['id'];deadline=time.monotonic()+180
                while time.monotonic()<deadline:
                    job=client.get('/api/jobs/'+ident).json()
                    if job['status'] not in ('running','queued'):break
                    time.sleep(.1)
                assert job['status']=='completed',job
                run=service.load_run(ident)
                assert run['statistics']['pages_error']==0,run['pages']
                assert run['statistics']['pages_ocr']==2,run['statistics']
                assert run['statistics']['pages_processed']==4
                assert run['records'],'No extracted annotations'
                values=client.get(f'/api/runs/{ident}/download/informations.json').json()
                for value in values:Information.model_validate(value)
                for record in run['records']:
                    i=record['information'];assert 0<=i['x']<=record['page_width'] and 0<=i['y']<=record['page_height']
                row=run['results'][0]
                detail=client.get(f"/api/runs/{ident}/results/{row['id']}")
                assert detail.status_code==200
                note='Synthetic review retained across restart'
                response=client.post(f"/api/runs/{ident}/results/{row['id']}/review",headers=headers,json={'decision':'a_verifier','note':note})
                assert response.status_code==200,response.text
                document=client.get(f'/api/runs/{ident}/download/rapport.pdf')
                assert document.status_code==200
                with fitz.open(stream=document.content,filetype='pdf') as pdf:assert 'CONCORDE' in pdf[0].get_text()
                checks.append({'engine':engine,'statistics':run['statistics'],'seconds':job['seconds'],
                    'devices':[p.get('device') for p in run['pages']],'review_saved':True,'exports_valid':True})
                # Same recovery code as application startup; process restart is a separate operational check.
                with service.LOCK:service.jobs.clear()
                service.recover()
                restored=service.load_run(ident)
                assert restored['results'][0]['review']['note']==note
                assert service.jobs[ident]['status']=='completed'
            paths=[Path(catalog.document(i)['path']) for i in catalog.project(project)['documents']]
            assert sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in paths)==sorted(hashlib.sha256(b).hexdigest() for b in originals)
        result={'synthetic_only':True,'checks':checks,'startup_recovery_passed':True,'originals_unchanged':True}
        args.output.write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
