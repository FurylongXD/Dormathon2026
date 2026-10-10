"""Local loan dashboard with evidence-checked sample-document and public-bank AI."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime,timezone,timedelta
from io import BytesIO
import hmac
import json
from pathlib import Path
import secrets
import threading
from typing import Literal
from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,Response,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict
from PIL import Image
from loan_engine.documents import DocumentKind,DocumentSubmission,ParsedDocument
from loan_engine.engine import LoanAssessmentEngine
from loan_engine.schema import AssessmentError
from loan_llm.service import LoanLLMService
from loan_llm.settings import Settings
from loan_llm.live_policies import valid_until,write_engine_policy_config
from loan_llm.client import ServiceError
from loan_llm.api import RequestGuard
from .ocr_adapter import DocumentReader
from .document_ai import AIDocumentExtractor
from .bank_comparison import compare_banks
from .document_service import verify_document
from .store import Store

ROOT=Path(__file__).resolve().parents[1]
KINDS=[k.value for k in DocumentKind]
LABELS={'profile':'Profile','payslip':'Payslip','bank_statement':'Bank statement','epf_statement':'EPF statement',
        'ccris_statement':'CCRIS report','ctos_statement':'CTOS report','credit_card_statement':'Credit card statement',
        'existing_loan_statement':'Existing loan statement','employment_contract':'Employment contract','loan_quotation':'Loan quotation'}

def today(): return datetime.now(timezone(timedelta(hours=8))).date().isoformat()

class DigestRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    digest:str

class DemoRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    product:Literal['car','home','personal']='car'

def create_app(runtime_dir=None,reader=None,settings=None):
    runtime=Path(runtime_dir or ROOT/'runtime'); runtime.mkdir(parents=True,exist_ok=True)
    store=Store(runtime/'local.sqlite3')
    store.recover_interrupted_jobs()
    settings=settings or Settings.load(ROOT/'.env')
    llm=LoanLLMService(settings)
    reader=reader or DocumentReader(ROOT/'config/mock_registry.json',AIDocumentExtractor(llm.client) if settings.api_key and settings.model else None)
    workers=ThreadPoolExecutor(max_workers=4); bank_lock=threading.Lock()
    app=FastAPI(title='CrediBell local loan intelligence',version='2.1.0',docs_url='/api/docs')
    app.add_middleware(RequestGuard,maximum=13_000_000)
    app.state.store=store; app.state.reader=reader; app.state.llm=llm

    def session(request):
        row=store.existing(request.cookies.get('finlens_session',''))
        if not row: raise ServiceError('SESSION_REQUIRED','Refresh the page to start a local session.',401)
        return row

    @app.middleware('http')
    async def security(request,call_next):
        if request.method in {'POST','DELETE','PUT','PATCH'}:
            origin=request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):
                return JSONResponse({'error':{'message':'This action must come from your local dashboard.'}},403)
            s=store.existing(request.cookies.get('finlens_session',''))
            if not s or not hmac.compare_digest(request.headers.get('x-csrf-token','').encode(),s['csrf'].encode()):
                return JSONResponse({'error':{'message':'Session check failed. Refresh the page.'}},403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request,error): return JSONResponse({'error':error.public()},error.status)

    @app.exception_handler(AssessmentError)
    async def assessment_error(request,error): return JSONResponse({'error':{'code':'DOCUMENT_OR_ASSESSMENT_ERROR','message':str(error)}},400)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,error): return JSONResponse({'error':{'message':'Check the request fields.'}},422)

    def document_status(sid):
        docs=store.documents(sid)
        return [{'kind':k,'label':LABELS[k],'state':docs[k]['state'] if k in docs else 'empty',
                 'digest':docs[k]['doc']['source_sha256'] if k in docs else None,
                 'confidence':docs[k]['doc']['recognition_min_confidence'] if k in docs else None,
                 'source':docs[k]['source'] if k in docs else None} for k in KINDS]

    def demo_id(sid):
        docs=store.documents(sid)
        explicit=next((r['doc']['fields'].get('demo_id') for r in docs.values()),None)
        return explicit or 'DEMO'+str(int(sid[:10],16))

    def verify(sid,kind,content):
        return verify_document(store,reader,sid,kind,content,demo_id(sid))

    @app.get('/api/health')
    def health(): return {'status':'ok','as_of':today(),'synthetic_only':True,'llm_scope':'anonymized sample document extraction and public bank information'}

    @app.get('/api/bootstrap')
    def bootstrap(request:Request):
        s,new=store.session(request.cookies.get('finlens_session'))
        value={'csrf':s['csrf'],'documents':document_status(s['id']),'assessment':store.result(s['id']),
               'active_job':store.active_job(s['id']),
               'as_of':today(),'bank_service':{'configured':bool(settings.api_key and settings.model),
               'scope':'sample document extraction and public bank information','model':settings.model or None},
               'sample_products':['car','home','personal']}
        response=JSONResponse(value)
        if new: response.set_cookie('finlens_session',s['id'],httponly=True,samesite='strict',max_age=86400)
        return response

    @app.get('/api/documents')
    def docs(request:Request): return {'documents':document_status(session(request)['id'])}

    @app.post('/api/documents/{kind}/verify')
    async def upload(kind:str,request:Request):
        sid=session(request)['id']
        if store.running(sid): raise ServiceError('JOB_RUNNING','Wait for the current document or analysis job to finish.',409)
        if request.headers.get('x-mock-only')!='true': raise AssessmentError('Confirm the image is an anonymized mock document before uploading.')
        content=await request.body()
        # OCR is blocking; keep the async request loop responsive.
        import asyncio
        parsed=await asyncio.to_thread(verify,sid,kind,content)
        return {'state':'verified','digest':parsed.source_sha256,'confidence':parsed.recognition_min_confidence,
                'field_count':len(parsed.fields),'documents':document_status(sid)}

    @app.post('/api/documents/{kind}/save')
    def save(kind:str,body:DigestRequest,request:Request):
        sid=session(request)['id']
        if store.running(sid): raise ServiceError('JOB_RUNNING','Wait for the current job to finish.',409)
        if not store.save_document(sid,kind,body.digest): raise AssessmentError('Verify the selected image before saving it.')
        return {'documents':document_status(sid)}

    @app.get('/api/documents/{kind}')
    def document(kind:str,request:Request):
        row=store.documents(session(request)['id']).get(kind)
        if not row: raise ServiceError('DOCUMENT_NOT_FOUND','No image is saved in this slot.',404)
        return {'fields':row['doc']['fields'],'confidences':row['doc']['field_confidences'],'source':row['source'],
                'evidence':row['doc'].get('field_evidence',{}),'page_count':row['doc'].get('page_count',1)}

    @app.get('/api/documents/{kind}/preview')
    def preview(kind:str,request:Request):
        content=store.image(session(request)['id'],kind)
        if content is None: raise ServiceError('DOCUMENT_NOT_FOUND','No preview available.',404)
        return Response(content,media_type='image/png')

    @app.delete('/api/documents/{kind}')
    def remove(kind:str,request:Request):
        sid=session(request)['id']
        if store.running(sid): raise ServiceError('JOB_RUNNING','Wait for the current job to finish.',409)
        store.remove_document(sid,kind); return {'documents':document_status(sid)}

    @app.post('/api/clear')
    def clear(request:Request):
        sid=session(request)['id']
        if store.running(sid): raise ServiceError('JOB_RUNNING','Wait for the current job to finish before clearing.',409)
        store.clear(sid); return {'cleared':True}

    def failure(jid,error):
        message=str(error) if isinstance(error,(AssessmentError,ServiceError)) else 'The job could not finish. Check installed dependencies and use clear, complete mock images.'
        store.update_job(jid,'failed',{'message':message,'progress':100})

    def load_demo(sid,jid,product):
        try:
            for i,kind in enumerate(KINDS):
                store.update_job(jid,'running',{'message':f'Reading {LABELS[kind].lower()}','progress':round(i/len(KINDS)*100)})
                content=(ROOT/'sample_documents'/product/(kind+'.png')).read_bytes()
                parsed=verify(sid,kind,content)
                store.save_document(sid,kind,parsed.source_sha256)
            store.update_job(jid,'done',{'message':'All sample documents verified and saved. Ready to submit.','progress':100})
        except Exception as error: failure(jid,error)

    @app.post('/api/load-demo')
    def demo(body:DemoRequest,request:Request):
        sid=session(request)['id']
        if store.running(sid): raise ServiceError('JOB_RUNNING','Wait for the current job to finish.',409)
        store.clear(sid)
        jid=store.job(sid,{'message':'Opening sample document set','progress':0})
        workers.submit(load_demo,sid,jid,body.product)
        return {'job_id':jid}

    def bank_context(code,force=False):
        # Never send applicant information here. Shared cache contains public sources only.
        with bank_lock:
            saved=store.bank(code)
            if saved and not force:
                try:
                    valid_until(saved)
                    if saved.get('status')=='live_extracted': return saved
                except ServiceError: pass
            result=llm.live_bank_context(code)
            if result.get('status')=='live_extracted': store.put_bank(code,result)
            return result

    def assess_job(sid,jid,force=False):
        try:
            version=store.existing(sid)['version']
            documents=store.documents(sid)
            if set(documents)!=set(KINDS) or any(d['state']!='saved' for d in documents.values()):
                raise AssessmentError('Verify and save all ten documents before submitting.')
            submission=DocumentSubmission(ROOT/'config/mock_registry.json')
            submission.documents={k:ParsedDocument(**d['doc']) for k,d in documents.items()}
            store.update_job(jid,'running',{'message':'Matching financial records and validating documents','progress':15})
            as_of=today(); applicant,quotes,audit=submission.compile(as_of)
            contexts=[]; policy_path=ROOT/'config/bank_policies.json'; policy_adapter=None
            if settings.api_key and settings.model:
                store.update_job(jid,'running',{'message':'Checking official bank policies and rates','progress':35})
                codes=list(dict.fromkeys(q.bank_code for q in quotes))
                if force:
                    catalog=json.loads((ROOT/'config/bank_catalog.json').read_text())
                    codes=list(dict.fromkeys(codes+[p['bank_code'] for p in catalog['products'] if p['product']==quotes[0].product]))
                for i,code in enumerate(codes):
                    store.update_job(jid,'running',{'message':f'Checking bank {i+1} of {len(codes)}','progress':35+round(i/len(codes)*25)})
                    contexts.append(bank_context(code,force))
                defined=json.loads(policy_path.read_text())['products']
                successful=[c for c in contexts if c.get('status')=='live_extracted' and c['bank_code'] in defined]
                if successful:
                    # Keep unsupported/fetch-failed products in a explicitly dated base config.
                    fresh=runtime/(jid+'_policy.json')
                    overlay=runtime/(jid+'_overlay.json')
                    policy_adapter=write_engine_policy_config(policy_path,successful,overlay)
                    base=json.loads(policy_path.read_text()); updated=json.loads(overlay.read_text())
                    base['products'].update(updated['products']); base['live_provenance']=updated['live_provenance']
                    fresh.write_text(json.dumps(base,indent=2)); policy_path=fresh
            store.update_job(jid,'running',{'message':'Calculating predictions, risk grades and SHAP explanations','progress':65})
            engine=LoanAssessmentEngine(ROOT/'artifacts',policy_path)
            result=engine.assess(applicant,quotes,as_of,audit)
            for quote,offer in zip(quotes,result['offers']):
                offer['quotation_summary']={'months':quote.months,'annual_rate':quote.annual_rate,
                    'rate_method':quote.rate_method,'fees_rm':quote.fees,'variable_rate':quote.variable_rate}
            result['bank_comparison']=compare_banks(applicant,quotes[0],result['offers'],as_of,contexts)
            result['live_bank_context']=contexts
            result['live_policy_adapter']=policy_adapter
            result['bank_data_status']='live_partial' if policy_adapter else 'reviewed_snapshot'
            result['bank_service_configured']=bool(settings.api_key and settings.model)
            result['llm_scope']='Grafilab translates evidence from anonymized sample documents and extracts public bank terms. Prediction and scenario amounts are calculated locally.'
            result['privacy']['llm_used_for_document_extraction']=any(d['source']=='grafilab_evidence_checked' for d in documents.values())
            result['privacy']['external_document_data']='Visible sample OCR text only; images and PDFs are not sent to Grafilab.'
            result['profile_summary']={'age':applicant.age,'gross_income_rm':applicant.gross_income,
                'net_income_rm':applicant.net_income,'living_expenses_rm':applicant.living_expenses,
                'months_in_job':applicant.months_in_job,'cash_savings_rm':applicant.cash_savings,
                'card_balance_rm':applicant.card_balance,'card_limit_rm':applicant.card_limit,
                'income_variability':applicant.income_variability,'variable_income_fraction':applicant.variable_income_fraction}
            # Extracted raw document fields are not needed in the dashboard result.
            result['document_audit']={k:{kk:vv for kk,vv in record.items() if kk!='fields'} for k,record in audit.items()}
            result['future_awareness']=[
                'Keep repayments current. Paying an overdue balance does not erase previous months of arrears from CCRIS.',
                'Review credit-report errors with the report issuer; this app does not access CCRIS or CTOS systems.',
                'Keep an emergency reserve before increasing a deposit or repaying debt.',
                'Confirm a revised quotation after changing the loan amount, rate or repayment term.',
                'Compare total financing cost and rate basis, not only the lowest advertised percentage.',
                'A rejected application is not automatically recorded as a rejection in CCRIS; BNM does not blacklist or issue a credit rating.']
            if not store.put_result(sid,version,result): raise AssessmentError('Documents changed during analysis. Submit the saved set again.')
            store.update_job(jid,'done',{'message':'Analysis is ready','progress':100})
        except Exception as error: failure(jid,error)

    @app.post('/api/assess')
    def assess(request:Request):
        sid=session(request)['id']
        if store.running(sid): raise ServiceError('JOB_RUNNING','An analysis is already running.',409)
        docs=store.documents(sid)
        if len(docs)!=10 or any(d['state']!='saved' for d in docs.values()): raise AssessmentError('Save all ten document uploads first.')
        jid=store.job(sid,{'message':'Starting your analysis','progress':0}); workers.submit(assess_job,sid,jid)
        return {'job_id':jid}

    @app.post('/api/refresh-banks')
    def refresh(request:Request):
        sid=session(request)['id']
        if not settings.api_key or not settings.model: raise ServiceError('MISSING_BANK_SERVICE','Set your existing Grafilab key and available model in backend .env, then restart.',400)
        if store.running(sid): raise ServiceError('JOB_RUNNING','Wait for the current job to finish.',409)
        jid=store.job(sid,{'message':'Refreshing public bank sources','progress':0}); workers.submit(assess_job,sid,jid,True)
        return {'job_id':jid}

    @app.get('/api/jobs/{jid}')
    def job(jid:str,request:Request):
        result=store.get_job(session(request)['id'],jid)
        if result is None: raise ServiceError('JOB_NOT_FOUND','This job does not belong to the current session.',404)
        return result

    @app.get('/api/result')
    def result(request:Request): return {'assessment':store.result(session(request)['id'])}

    @app.get('/api/result/download')
    def download(request:Request):
        value=store.result(session(request)['id'])
        if value is None: raise ServiceError('NO_ANALYSIS','Submit documents to generate an analysis.',404)
        return Response(json.dumps(value,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename=credibell_analysis.json'})

    @app.get('/api/samples/{product}/{kind}')
    def sample(product:str,kind:str):
        if product not in {'car','home','personal'} or kind not in KINDS: raise ServiceError('NOT_FOUND','Sample not found.',404)
        return FileResponse(ROOT/'sample_documents'/product/(kind+'.png'),media_type='image/png')

    @app.get('/')
    def index(): return FileResponse(ROOT/'web/index.html')
    app.mount('/assets',StaticFiles(directory=ROOT/'web'),name='assets')
    return app
