from copy import deepcopy
from pathlib import Path
import unittest
from loan_engine.documents import FIELDS
from loan_engine.demo_documents import fixture_fields
from loan_engine.schema import AssessmentError
from server.document_ai import guard_sample,validate_fields,AIDocumentExtractor
from server.ocr_adapter import DocumentReader
from server.bank_comparison import compare_banks

ROOT=Path(__file__).resolve().parents[1]

def response(kind):
    fields=fixture_fields()[kind];rows=[{'id':'p1l1','page':1,'text':'SAMPLE ONLY','confidence':.99}];answer={'document_kind':kind,'fields':{},'missing_fields':[]}
    for i,(k,v) in enumerate(fields.items(),2):
        if k in {'demo_marker','document_type'}: continue
        ident=f'p1l{i}';rows.append({'id':ident,'page':1,'text':f'{k}: {v}','confidence':.99})
        answer['fields'][k]={'op':'direct','raw':str(v),'line_ids':[ident]}
    return rows,answer

class EvidenceTests(unittest.TestCase):
    def test_all_ten_document_schemas_with_evidence(self):
        for kind in FIELDS:
            rows,answer=response(kind)
            parsed=validate_fields(kind,answer,rows,'digest','DEMO00001',1)
            self.assertEqual(parsed.fields,fixture_fields()[kind]); self.assertIn('issued_date',parsed.field_evidence)

    def test_invented_and_substring_amounts_rejected(self):
        for raw in ('31','3'):
            rows,answer=response('profile');answer['fields']['age']['raw']=raw
            with self.assertRaises(AssessmentError):validate_fields('profile',answer,rows,'h','DEMO00001',1)

    def test_missing_income_never_filled(self):
        rows,answer=response('payslip');answer['fields'].pop('net_2')
        with self.assertRaises(AssessmentError):validate_fields('payslip',answer,rows,'h','DEMO00001',1)

    def test_low_confidence_reference_stops_extraction(self):
        rows,answer=response('profile');rows[-1]['confidence']=.45
        with self.assertRaises(AssessmentError):validate_fields('profile',answer,rows,'h','DEMO00001',1)

    def test_wrong_page_or_field_or_slot_rejected(self):
        for change in ('page','field','slot'):
            rows,answer=response('profile')
            if change=='page':answer['fields']['age']['line_ids']=['p9l9']
            if change=='field':answer['fields']['guaranteed_approval']={'op':'direct','raw':'1','line_ids':['p1l1']}
            if change=='slot':answer['document_kind']='ctos_statement'
            with self.assertRaises(AssessmentError):validate_fields('profile',answer,rows,'h','DEMO00001',1)

    def test_age_computation_uses_visible_dates(self):
        rows,answer=response('profile');rows.append({'id':'p1l99','page':1,'text':'Birth date: 1994-10-10','confidence':.98})
        answer['fields']['age']={'op':'age','operands':[{'raw':'1994-10-10','line_ids':['p1l99']},answer['fields']['issued_date']]}
        p=validate_fields('profile',answer,rows,'h','DEMO00001',1);self.assertEqual(p.fields['age'],32)

    def test_duplicate_transactions_and_unlabelled_transfers_rejected(self):
        rows,answer=response('bank_statement');row={'id':'p1l99','page':1,'text':'Salary payroll credit: RM6,400','confidence':.99};rows.append(row)
        operand={'raw':'RM6,400','line_ids':['p1l99']}
        answer['fields']['income_credit_1']={'op':'sum','operands':[operand,operand]}
        with self.assertRaises(AssessmentError):validate_fields('bank_statement',answer,rows,'h','DEMO00001',1)
        answer['fields']['income_credit_1']['operands']=[operand];row['text']='Transfer: RM6,400'
        with self.assertRaises(AssessmentError):validate_fields('bank_statement',answer,rows,'h','DEMO00001',1)

    def test_privacy_and_sample_watermark_before_provider(self):
        for text in ('no watermark','SAMPLE Full name: John Example','SAMPLE 000101-14-1234','SAMPLE email: person@example.com'):
            with self.assertRaises(AssessmentError):guard_sample([{'text':text}])

    def test_valid_provider_mapping_separate_from_predictions(self):
        rows,answer=response('profile');calls=[]
        class Client:
            def complete(self,prompt,context,max_tokens):calls.append(context);return answer,{}
        p=AIDocumentExtractor(Client()).extract('profile',rows,'h','DEMO00001',1)
        self.assertEqual(p.fields['age'],32);self.assertNotIn('approval_probability',calls[0]['requested_fields'])

class PDFTests(unittest.TestCase):
    def test_actual_multipage_pdf_rendered(self):
        pages=DocumentReader.pages((ROOT/'sample_documents/pdf/bank_statement.pdf').read_bytes())
        self.assertEqual(len(pages),3);self.assertTrue(all(p.startswith(b'\x89PNG') for p in pages))

    def test_invalid_or_oversized_file_rejected(self):
        for content in (b'%PDF-bad',b'invalid image',b'x'*12_000_001):
            with self.assertRaises(AssessmentError):DocumentReader.pages(content)

class ComparisonTests(unittest.TestCase):
    def setUp(self):
        from loan_engine.documents import DocumentSubmission,parse_fields
        sub=DocumentSubmission(ROOT/'config/mock_registry.json')
        sub.documents={k:parse_fields(k,[(f'{key}: {value}',.99) for key,value in f.items()],'h') for k,f in fixture_fields().items()}
        self.a,self.q,_=sub.compile('2026-10-10')

    def test_six_car_banks_have_no_invented_borrower_rates(self):
        rows=compare_banks(self.a,self.q[0],[],'2026-10-10')
        self.assertEqual(len(rows),6);self.assertTrue(all(r['effective_cashflow_rate'] is None for r in rows))
        self.assertTrue(all(r['published_principal_ceiling_rm']==90000 for r in rows))

    def test_public_bank_older_car_band_reduces_ceiling(self):
        from dataclasses import replace
        rows=compare_banks(self.a,replace(self.q[0],vehicle_age=11),[],'2026-10-10')
        pb=next(r for r in rows if r['bank_code']=='PUBLIC_BANK_CAR');self.assertEqual(pb['published_margin'],.75)

    def test_expired_terms_do_not_publish_old_amounts(self):
        rows=compare_banks(self.a,self.q[0],[],'2026-12-10')
        self.assertTrue(all(r['published_principal_ceiling_rm'] is None for r in rows))

    def test_combined_home_margin_never_treated_as_asset_margin(self):
        from dataclasses import replace
        rows=compare_banks(self.a,replace(self.q[0],product='home'),[],'2026-10-10')
        amb=next(r for r in rows if r['bank_code']=='AMBANK_HOME')
        self.assertEqual(amb['combined_margin'],.95);self.assertIsNone(amb['published_principal_ceiling_rm'])

if __name__=='__main__':unittest.main()
