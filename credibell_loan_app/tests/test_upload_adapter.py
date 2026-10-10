from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from loan_engine.demo_documents import fixture_fields
from loan_engine.documents import DocumentSubmission
from loan_engine.schema import AssessmentError
from server.ocr_adapter import parse_mock_layout,normalize_value
from server.store import Store

ROOT=Path(__file__).resolve().parents[1]

def lines(kind):
    values=deepcopy(fixture_fields()[kind]); values.pop('demo_marker'); values.pop('document_type')
    return [('ANONYMOUS SYNTHETIC MOCK SAMPLE',.999)]+[(f'{k}: {v}',.999) for k,v in values.items()]

class AlternateLayoutTests(unittest.TestCase):
    def test_malay_label_and_ddmmyyyy_date(self):
        d=parse_mock_layout('profile',[('MOCK',.99),('Umur: 32',.99),('Nationality: Malaysian',.99),('Statement date: 10/10/2026',.99)],'digest','DEMO00001')
        self.assertEqual(d.fields['age'],32); self.assertEqual(d.fields['citizenship'],'MY'); self.assertEqual(d.fields['issued_date'],'2026-10-10')

    def test_adjacent_label_and_value(self):
        d=parse_mock_layout('profile',[('SAMPLE',.99),('Applicant age',.99),('32',.99),('Nationality Malaysian',.99),('Issue date 2026-10-10',.99)],'digest','DEMO00001')
        self.assertEqual(d.fields['age'],32)

    def test_explicit_percent_and_rm_conversion(self):
        self.assertEqual(normalize_value('annual_rate_1','5.3% p.a.',float),.053)
        self.assertEqual(normalize_value('requested_principal','RM90,000',float),90000)
        self.assertEqual(normalize_value('variable_income_fraction','35%',float),.35)

    def test_ambiguous_percent_rate_is_rejected(self):
        with self.assertRaises(AssessmentError): normalize_value('annual_rate_1','5.3',float)

    def test_overflow_numeric_is_rejected(self):
        with self.assertRaises(AssessmentError): normalize_value('balance','9'*500,float)

    def test_no_marker_rejected(self):
        with self.assertRaises(AssessmentError): parse_mock_layout('profile',lines('profile')[1:],'digest','DEMO00001')

    def test_obvious_identifiers_rejected_without_echo(self):
        for identifier in ('000101-14-1234','someone@example.com','4111 1111 1111 1111'):
            with self.assertRaises(AssessmentError) as e: parse_mock_layout('profile',lines('profile')+[(identifier,.99)],'digest','DEMO00001')
            self.assertNotIn(identifier,str(e.exception))

    def test_missing_income_is_not_imputed(self):
        with self.assertRaises(AssessmentError): parse_mock_layout('bank_statement',[l for l in lines('bank_statement') if not l[0].startswith('income_credit_2:')],'digest','DEMO00001')

    def test_conflicting_age_and_low_confidence_are_rejected(self):
        for extra in ([('Umur: 35',.99)],[('Umur: 32',.50)]):
            with self.assertRaises(AssessmentError): parse_mock_layout('profile',lines('profile')+extra,'digest','DEMO00001')

    def test_wrong_declared_slot_rejected(self):
        with self.assertRaises(AssessmentError): parse_mock_layout('profile',lines('profile')+[('document_type: ctos_statement',.99)],'digest','DEMO00001')

    def test_bank_aliases_and_offer_count(self):
        recognized=lines('loan_quotation')
        recognized=[(t.replace('bank_code_1: PUBLIC_BANK_CAR','Bank name 1: Public Bank').replace('bank_code_2: MAYBANK_CAR','Bank name 2: Maybank'),c) for t,c in recognized if not t.startswith('offer_count:')]
        d=parse_mock_layout('loan_quotation',recognized,'digest','DEMO00001')
        self.assertEqual(d.fields['offer_count'],2); self.assertEqual(d.fields['bank_code_1'],'PUBLIC_BANK_CAR')

    def test_all_alternate_fields_reconcile_and_reject_inconsistent_salary(self):
        sub=DocumentSubmission(ROOT/'config/mock_registry.json')
        sub.documents={kind:parse_mock_layout(kind,lines(kind),'digest','DEMO00001') for kind in fixture_fields()}
        a,q,_=sub.compile('2026-10-10'); self.assertEqual(a.net_income,6500); self.assertEqual(len(q),2)
        sub.documents['bank_statement'].fields['income_credit_2']+=500
        with self.assertRaises(AssessmentError): sub.compile('2026-10-10')

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.temp.name)/'db.sqlite3'); self.s,_=self.store.session(); self.sid=self.s['id']
        self.doc={'source_sha256':'verified-digest','fields':{'demo_id':'DEMO00001'}}
    def tearDown(self): self.temp.cleanup()

    def test_separate_save_and_hash_match(self):
        self.store.put_document(self.sid,'profile',self.doc,b'image','test')
        self.assertEqual(self.store.documents(self.sid)['profile']['state'],'verified')
        self.assertFalse(self.store.save_document(self.sid,'profile','different'))
        self.assertTrue(self.store.save_document(self.sid,'profile','verified-digest'))
        self.assertEqual(self.store.documents(self.sid)['profile']['state'],'saved')

    def test_session_isolation_and_cookie_reuse(self):
        self.store.put_document(self.sid,'profile',self.doc,b'image','test')
        other,_=self.store.session(); self.assertEqual(self.store.documents(other['id']),{})
        same,new=self.store.session(self.sid); self.assertFalse(new); self.assertEqual(same['csrf'],self.s['csrf'])

    def test_upload_change_invalidates_result_and_stale_version(self):
        version=self.store.existing(self.sid)['version']; self.assertTrue(self.store.put_result(self.sid,version,{'test':1}))
        self.store.put_document(self.sid,'profile',self.doc,b'image','test')
        self.assertIsNone(self.store.result(self.sid)); self.assertFalse(self.store.put_result(self.sid,version,{'test':1}))

    def test_job_owner_and_restart_recovery(self):
        jid=self.store.job(self.sid,{'message':'test'}); other,_=self.store.session()
        self.assertIsNone(self.store.get_job(other['id'],jid)); self.assertEqual(self.store.active_job(self.sid)['id'],jid)
        self.store.recover_interrupted_jobs(); self.assertFalse(self.store.running(self.sid)); self.assertEqual(self.store.get_job(self.sid,jid)['state'],'failed')

    def test_clear_removes_images_and_result(self):
        self.store.put_document(self.sid,'profile',self.doc,b'image','test'); version=self.store.existing(self.sid)['version']; self.store.put_result(self.sid,version,{'test':1})
        self.store.clear(self.sid); self.assertIsNone(self.store.image(self.sid,'profile')); self.assertIsNone(self.store.result(self.sid))

if __name__=='__main__': unittest.main()
