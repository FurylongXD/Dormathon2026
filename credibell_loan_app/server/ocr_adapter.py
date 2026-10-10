"""Local OCR adapter for registered fixtures and anonymized mock label layouts.

Layout support is explicit, not a universal bank statement understanding model.
No financial values are invented. Missing/ambiguous required fields stop saving.
"""
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import re
import threading
from PIL import Image
from loan_engine.documents import LocalOCR, DocumentKind, COMMON, FIELDS, ParsedDocument, parse_fields, canonical
from loan_engine.schema import AssessmentError

ALIASES={
    'age':['applicant age','umur'], 'citizenship':['nationality','citizen','kewarganegaraan'],
    'issued_date':['statement date','issue date','document date','date issued','tarikh penyata'],
    'gross':['gross salary','gross pay','gross income','gaji kasar'],
    'net':['net salary','net pay','take home pay','gaji bersih'],
    'epf':['employee epf deduction','epf deduction','kwsp deduction'],
    'tax':['pcb deduction','pcb tax','tax deduction','income tax deduction'],
    'other_deductions':['other deduction','other payroll deductions'],
    'income_credit':['salary credit','salary credited','income deposit'],
    'living_expenses':['living costs','household expenses'],
    'cash_savings':['available cash','cash balance','available balance'],
    'employee_contribution':['employee epf contribution','employee contribution','caruman pekerja'],
    'regular_months':['regular contribution months','consecutive contribution months'],
    'arrears_max_months':['maximum months in arrears','max arrears months'],
    'late_payments_12m':['late payments last 12 months','late payment count'],
    'housing_loans_count':['outstanding housing loans','number of housing loans'],
    'mock_reported_score':['mock ctos score','ctos score','reported score'],
    'legal_flags':['legal record flag','legal flag'],
    'account':['account alias','mock account'], 'minimum_due':['minimum payment','minimum amount due'],
    'limit':['credit limit','card limit'], 'balance':['outstanding balance','statement balance','epf balance'],
    'monthly_payment':['monthly instalment','monthly installment','monthly repayment'],
    'early_settlement_fee':['settlement fee','loan settlement fee'],
    'months_in_job':['employment months','months employed','tenure in current job'],
    'contract_months_remaining':['remaining contract months','contract remaining months'],
    'variable_income_fraction':['variable income share','commission income fraction'],
    'asset_price':['purchase price','vehicle price','property price'],
    'requested_principal':['loan amount','requested loan amount','financing amount'],
    'down_payment':['deposit','cash deposit','downpayment'],
    'vehicle_age':['vehicle age years','car age'],
    'bank_code':['bank','bank name'], 'annual_rate':['interest rate','annual interest rate','profit rate'],
    'rate_method':['rate basis','calculation basis'], 'months':['term months','loan term months','tenure months'],
    'fees':['upfront fee','upfront fees','processing fee'], 'variable_rate':['variable rate flag'],
    'product':['loan type','financing type'], 'demo_id':['mock applicant id','anonymous id'],
}

def labels(key):
    options=[key,key.replace('_',' ')]
    m=re.fullmatch(r'(.*)_([123])',key)
    if m:
        base,index=m.groups()
        stems=[base.replace('_',' '),*ALIASES.get(base,[])]
        options += [f'{stem} {index}' for stem in stems]
        options += [f'{stem} month {index}' for stem in stems]
        options += [f'month {index} {stem}' for stem in stems]
        if base=='month': options += [f'salary month {index}',f'statement month {index}']
        if index=='1' and key in FIELDS['loan_quotation']: options += stems
    else: options+=ALIASES.get(key,[])
    return options

def field_date(raw):
    raw=raw.strip()
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d %b %Y','%d %B %Y','%m/%Y','%b %Y','%B %Y'):
        try: return datetime.strptime(raw,fmt).date().isoformat()
        except ValueError: pass
    raise AssessmentError('A document date or salary month could not be read. Use a clear dated mock sample.')

def normalize_value(key,raw,kind):
    raw=raw.strip().rstrip(';')
    if key.startswith('variable_rate'):
        explicit={'fixed':0,'no':0,'false':0,'variable':1,'floating':1,'yes':1,'true':1}
        if canonical(raw) in explicit: return explicit[canonical(raw)]
    if key=='legal_flags' and canonical(raw) in {'none','norecords','nolegalrecords','nolegalcases'}: return 0
    if key=='issued_date' or key.startswith('month_'): return field_date(raw)
    if key=='citizenship':
        return {'malaysian':'MY','malaysia':'MY','my':'MY','other':'OTHER','nonmalaysian':'OTHER'}.get(canonical(raw),raw)
    if key=='product': return {'car':'car','vehicle':'car','auto':'car','home':'home','housing':'home','house':'home','personal':'personal'}.get(canonical(raw),raw)
    if key.startswith('rate_method'):
        return {'flat':'flat','fixedflat':'flat','reducingnominal':'reducing_nominal',
                'nominalreducingbalance':'reducing_nominal','reducingeffective':'reducing_effective',
                'annuallycompoundedeffective':'reducing_effective'}.get(canonical(raw),raw)
    if kind in (float,int):
        percent='%' in raw
        cleaned=re.sub(r'(?i)^(?:RM|MYR)\s*','',raw)
        cleaned=re.sub(r'(?i)\b(?:months?|years?)\b|p\.a\.','',cleaned).replace(',','').replace('%','').strip()
        if not re.fullmatch(r'\d+(?:\.\d+)?',cleaned): raise AssessmentError(f'Could not read the value for {key.replace("_"," ")}.')
        value=float(cleaned)
        if not math.isfinite(value): raise AssessmentError('A numeric field is outside the supported range.')
        if key.startswith('annual_rate') or key=='variable_income_fraction':
            if percent: value/=100
            elif key.startswith('annual_rate') and value>1:
                raise AssessmentError('Interest rates above one need an explicit % sign; do not guess the rate unit.')
        if kind is int and not value.is_integer(): raise AssessmentError(f'{key.replace("_"," ")} must be a whole number.')
        return kind(value)
    return raw.replace(' ','')

def parse_mock_layout(kind,recognized,digest,session_demo_id,min_confidence=.90):
    joined=' '.join(t for t,_ in recognized)
    if not re.search(r'\b(synthetic\s*only|synthetic|mock|sample)\b',joined,re.I):
        raise AssessmentError('Add a visible SAMPLE or SYNTHETIC watermark to the anonymized mock document.')
    # Extra guard, not comprehensive anonymization. The AI path separately checks
    # sample text before sending it to the configured Grafilab client.
    if re.search(r'\b\d{6}[- ]?\d{2}[- ]?\d{4}\b|\b\d{13,19}\b|\b(?:\d{4}[ -]){3}\d{4}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',joined):
        raise AssessmentError('Remove identity/card numbers and email addresses from the mock document before upload.')
    types={**COMMON,**FIELDS[kind]}
    dictionary={canonical(alias):key for key in types for alias in labels(key)}
    values={}; confidence={}
    for index,(text,score) in enumerate(recognized):
        for part in re.split(r'\s*[|;]\s*',text):
            candidates=[]
            match=re.match(r'^\s*([^:：=]+)[:：=]\s*(.*?)\s*$',part)
            if match: candidates.append((canonical(match.group(1)),match.group(2),score))
            cleaned=canonical(part)
            if cleaned in dictionary and index+1<len(recognized):
                next_text,next_score=recognized[index+1]
                candidates.append((cleaned,next_text,min(score,next_score)))
            # Label and value printed together without a colon.
            for alias in sorted(dictionary,key=len,reverse=True):
                for cut in range(1,len(part)):
                    if part[cut-1].isspace() and canonical(part[:cut])==alias:
                        candidates.append((alias,part[cut:].strip(),score)); break
                if candidates: break
            for label,raw,score in candidates:
                key=dictionary.get(label)
                if not key or key=='demo_marker': continue
                if key=='document_type':
                    if canonical(raw)!=canonical(kind): raise AssessmentError('The stated document type does not match this upload slot.')
                    continue
                if score<min_confidence: raise AssessmentError(f'Low-confidence OCR for {key.replace("_"," ")}; upload a clearer mock image.')
                value=normalize_value(key,raw,types[key])
                if key in values and values[key]!=value: raise AssessmentError(f'Conflicting values for {key.replace("_"," ")}.')
                values[key]=value; confidence[key]=score
    values.update(demo_marker='SYNTHETICONLY',document_type=kind)
    if 'demo_id' not in values: values['demo_id']=session_demo_id
    if not re.fullmatch(r'DEMO\d+',values['demo_id']):
        # Explicit anonymous aliases must still reconcile; canonicalize deterministically.
        values['demo_id']='DEMO'+str(int(sha256(values['demo_id'].encode()).hexdigest()[:12],16))
    for field in ('demo_marker','document_type','demo_id'): confidence.setdefault(field,1.0)
    if kind=='loan_quotation':
        product=values.get('product')
        bank_names={'publicbank':'PUBLIC_BANK','maybank':'MAYBANK','cimb':'CIMB','rhb':'RHB','hongleong':'HONG_LEONG','hongleongbank':'HONG_LEONG','hlb':'HONG_LEONG','ambank':'AMBANK','bsn':'BSN'}
        for i in (1,2):
            field=f'bank_code_{i}'
            if field in values and canonical(values[field]) in bank_names and product:
                values[field]=bank_names[canonical(values[field])]+'_'+product.upper()
        if 'offer_count' not in values:
            values['offer_count']=2 if 'bank_code_2' in values else 1; confidence['offer_count']=1.0
        if product in {'home','personal'}:
            values.setdefault('vehicle_age',0); confidence.setdefault('vehicle_age',1.0)
        if product=='personal':
            values.setdefault('down_payment',0); confidence.setdefault('down_payment',1.0)
            if 'asset_price' not in values and 'requested_principal' in values:
                values['asset_price']=values['requested_principal']; confidence['asset_price']=confidence['requested_principal']
    required=set(types)
    if kind=='loan_quotation' and values.get('offer_count')==1: required-={k for k in FIELDS[kind] if k.endswith('_2')}
    missing=required-values.keys()
    if missing:
        readable=', '.join(k.replace('_',' ') for k in sorted(missing))
        raise AssessmentError('The mock layout is missing required readable information: '+readable+'.')
    return ParsedDocument(kind,values,confidence,digest,min(confidence.values()))

class DocumentReader:
    def __init__(self,registry_path,ai_extractor=None):
        self.registry=json.loads(Path(registry_path).read_text()); self.ocr=None; self.lock=threading.Lock()
        self.ai_extractor=ai_extractor

    @staticmethod
    def pages(content):
        if len(content)>12_000_000: raise AssessmentError('Maximum file size is 12 MB.')
        if content.startswith(b'%PDF-'):
            import pypdfium2 as pdfium
            try:
                document=pdfium.PdfDocument(content)
                try:
                    if not 1<=len(document)<=8: raise AssessmentError('Use a PDF with between one and eight pages per upload.')
                    pages=[]
                    for index in range(len(document)):
                        page=document[index]
                        try:
                            width,height=page.get_size()
                            if width<=0 or height<=0 or width*height>12_000_000: raise AssessmentError('A PDF page is too large to read safely.')
                            scale=min(2.5,(12_000_000/(width*height))**.5)
                            bitmap=page.render(scale=scale)
                            try:
                                buff=BytesIO(); bitmap.to_pil().convert('RGB').save(buff,format='PNG');pages.append(buff.getvalue())
                            finally: bitmap.close()
                        finally: page.close()
                    return pages
                finally: document.close()
            except AssessmentError: raise
            except Exception: raise AssessmentError('This PDF cannot be read. Remove password protection or upload clear page images.') from None
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format not in {'PNG','JPEG','WEBP'} or image.width*image.height>12_000_000 or getattr(image,'n_frames',1)!=1:
                    raise AssessmentError('Use PNG, JPEG, WEBP or PDF, up to 12 MB and 12 megapixels per image.')
                converted=BytesIO(); image.convert('RGB').save(converted,format='PNG');return [converted.getvalue()]
        except (OSError,ValueError): raise AssessmentError('The uploaded file is not a readable image or PDF.') from None

    def preview(self,content): return self.pages(content)[0]

    def warm(self):
        """Load local OCR assets in the background while the dashboard opens."""
        with self.lock:
            if self.ocr is None: self.ocr=LocalOCR()

    def read(self,kind,content,session_demo_id):
        parsed,source,_=self.read_with_preview(kind,content,session_demo_id)
        return parsed,source

    def read_with_preview(self,kind,content,session_demo_id):
        kind=DocumentKind(kind).value
        digest=sha256(content).hexdigest()
        pages=self.pages(content);rows=[];recognized=[]
        with self.lock:
            if self.ocr is None: self.ocr=LocalOCR()
            for p,image in enumerate(pages,1):
                page_rows=self.ocr.recognize(image); recognized.extend(page_rows)
                rows.extend({'id':f'p{p}l{i}','page':p,'text':text,'confidence':conf} for i,(text,conf) in enumerate(page_rows,1))
        if len(rows)>2500 or sum(len(r['text']) for r in rows)>65000:
            raise AssessmentError('This document has too much text. Split it into a shorter, relevant sample.')
        registration=self.registry['files'].get(digest)
        if registration:
            if registration['kind']!=kind: raise AssessmentError('This sample belongs to a different upload slot.')
            parsed=parse_fields(kind,recognized,digest);source='registered_synthetic_sample'
        else:
            from .document_ai import guard_sample
            guard_sample(rows)
            try:
                parsed=parse_mock_layout(kind,recognized,digest,session_demo_id);source='anonymized_mock_alias_layout'
            except AssessmentError as error:
                # Never use an LLM to bypass conflicts, identifiers or low-confidence reads.
                if not str(error).startswith('The mock layout is missing required readable information:'): raise
                if self.ai_extractor is None:
                    raise AssessmentError('This layout needs the AI document reader. Set your Grafilab key and an available chat model, or use a complete labelled sample.') from None
                return self.ai_extractor.extract(kind,rows,digest,session_demo_id,len(pages)), 'grafilab_evidence_checked', pages[0]
        parsed.page_count=len(pages)
        if not parsed.field_evidence:
            parsed.field_evidence={'readable_source':{'operation':'local_label_reader','sources':[{'page':r['page'],'line_id':r['id'],'text':r['text']} for r in rows]}}
        return parsed,source,pages[0]
