"""Actual PDF rendering + OCR + controlled provider recipes; no paid API call.

This checks the evidence validator, not the accuracy/availability of a Grafilab model.
"""
from pathlib import Path
import re
from loan_engine.demo_documents import fixture_fields
from server.document_ai import AIDocumentExtractor
from server.ocr_adapter import DocumentReader

ROOT=Path(__file__).resolve().parent
class ControlledReader:
    def complete(self,prompt,context,max_tokens):
        rows=context['lines'];out={'document_kind':context['document_kind'],'fields':{},'missing_fields':[]}
        def find(text,page=None):return next(r for r in rows if text.lower() in r['text'].lower() and (page is None or r['page']==page))
        def operand(raw,row,extra=None):return {'raw':raw,'line_ids':[row['id']]+([extra['id']] if extra else [])}
        def direct(key,raw,row,extra=None):out['fields'][key]={'op':'direct',**operand(raw,row,extra)}
        issue=find('issued_date');issued=re.search(r'\d{4}-\d{2}-\d{2}',issue['text']).group()
        direct('issued_date',issued,issue);alias=find('demo_id');direct('demo_id',re.search(r'DEMO\d+',alias['text']).group(),alias)
        if context['document_kind']=='profile':
            birth=find('birth');dob=re.search(r'\d{4}-\d{2}-\d{2}',birth['text']).group()
            nationality=find('Nationality');direct('citizenship','Malaysian',nationality)
            out['fields']['age']={'op':'age','operands':[operand(dob,birth),operand(issued,issue)]}
        else:
            labels={'gross':'Gross pay','epf':'Employee EPF','tax':'PCB tax','other_deductions':'Other deductions','net':'Net salary'}
            for page in (1,2,3):
                period=find('Pay period',page);direct(f'month_{page}',re.search(r'\d{4}-\d{2}-\d{2}',period['text']).group(),period)
                page_rows=[r for r in rows if r['page']==page]
                for key,label in labels.items():
                    label_row=find(label,page);idx=page_rows.index(label_row)
                    amount=label_row if re.search(r'\d[\d,]*\.\d{2}',label_row['text']) else page_rows[idx+1]
                    raw=re.search(r'\d[\d,]*\.\d{2}',amount['text']).group()
                    direct(f'{key}_{page}',raw,amount,label_row if label_row!=amount else None)
        return out,{'model':'controlled-validation-fixture'}

def main():
    reader=DocumentReader(ROOT/'config/mock_registry.json',AIDocumentExtractor(ControlledReader()))
    for kind,file in [('profile','profile_birth_date.pdf'),('payslip','payslip_table.pdf')]:
        parsed,source=reader.read(kind,(ROOT/'sample_documents/pdf'/file).read_bytes(),'DEMO00001')
        expected=fixture_fields(as_of=parsed.fields['issued_date'])[kind]
        assert parsed.fields==expected,(kind,parsed.fields)
        assert source=='grafilab_evidence_checked';assert parsed.field_evidence
        print(f'PASS {file}: actual OCR, {parsed.page_count} pages, source-linked recipes validated against expected values.')
    print('Grafilab authentication/inference is not tested by this offline verification.')
if __name__=='__main__':main()
