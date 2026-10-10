from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from loan_llm.client import ServiceError
from loan_llm.settings import Settings
from loan_llm.service import LoanLLMService
from loan_llm.live_policies import LiveBankPolicyService, write_engine_policy_config, public_rate_planning_quote

TEXT='Synthetic test product: minimum income RM2,000. Term up to 7 years. A flat annual rate of 3% applies only to synthetic eligible salaried borrowers.'

def extraction():
    return {'rules':{
        'min_gross_income':{'source_id':'CIMB_PERSONAL','evidence_quote':'minimum income RM2,000.','raw_number':2000,'raw_unit':'rm'},
        'max_months':{'source_id':'CIMB_PERSONAL','evidence_quote':'Term up to 7 years.','raw_number':7,'raw_unit':'years'}},
        'age_bands':[], 'rates':[{'source_id':'CIMB_PERSONAL',
            'evidence_quote':'A flat annual rate of 3% applies only to synthetic eligible salaried borrowers.',
            'annual_rate_percent':3,'rate_basis':'flat','basis_evidence_quote':'A flat annual rate of 3%',
            'conditions_quote':'applies only to synthetic eligible salaried borrowers.','is_variable':False}],
        'missing_fields':['min_age']}

class Stub:
    def __init__(self, reply=None): self.reply=reply or extraction(); self.context=None
    def complete(self,system,context,max_tokens=1800):
        self.context=context; return deepcopy(self.reply),{'model':'test-only-model'}

def service(reply=None,fetcher=None):
    stub=Stub(reply)
    return LoanLLMService(Settings(),stub,fetcher or (lambda s: TEXT)),stub

def snapshot():
    svc,_=service(); return svc.live_bank_context('CIMB_PERSONAL')

class LiveTests(unittest.TestCase):
    def test_fresh_page_values_return_in_model_units(self):
        result=snapshot()
        self.assertEqual(result['status'],'live_extracted')
        self.assertEqual(result['rules']['max_months']['value'],84)
        self.assertEqual(result['rates'][0]['annual_rate'],0.03)

    def test_no_old_numeric_catalogue_sent_to_llm(self):
        svc,stub=service(); svc.live_bank_context('CIMB_PERSONAL')
        self.assertNotIn('reviewed_facts',stub.context)
        self.assertIn(TEXT,stub.context['fresh_pages']['CIMB_PERSONAL']['untrusted_page_text'])

    def test_every_refresh_fetches_again(self):
        calls=[]; svc,_=service(fetcher=lambda s: calls.append(s['id']) or TEXT)
        svc.live_bank_context('CIMB_PERSONAL'); svc.live_bank_context('CIMB_PERSONAL')
        self.assertEqual(len(calls),2)

    def test_fetch_failure_does_not_reuse_stored_rates(self):
        def fail(s): raise OSError('not public')
        svc,stub=service(fetcher=fail); result=svc.live_bank_context('CIMB_PERSONAL')
        self.assertEqual(result['status'],'unavailable'); self.assertEqual(result['rates'],[])
        self.assertIsNone(stub.context)

    def test_provider_failure_is_not_online_success(self):
        svc,_=service()
        svc.client.complete=lambda *a,**k: (_ for _ in ()).throw(ServiceError('ACCESS_REJECTED','HTTP 403'))
        result=svc.live_bank_context('CIMB_PERSONAL')
        self.assertEqual(result['status'],'unavailable'); self.assertEqual(result['rules'],{})

    def test_invented_excerpt_rejected(self):
        reply=extraction(); reply['rules']['min_gross_income']['evidence_quote']='invented salary RM1000'
        svc,_=service(reply); result=svc.live_bank_context('CIMB_PERSONAL')
        self.assertEqual(result['provider_error']['code'],'UNSUPPORTED_LIVE_EVIDENCE')

    def test_invented_number_rejected(self):
        reply=extraction(); reply['rates'][0]['annual_rate_percent']=2
        svc,_=service(reply)
        self.assertEqual(svc.live_bank_context('CIMB_PERSONAL')['provider_error']['code'],'UNSUPPORTED_LIVE_NUMBER')

    def test_private_dsr_rule_rejected(self):
        reply=extraction(); reply['rules']['bank_dsr_cutoff']=reply['rules']['max_months']
        svc,_=service(reply)
        self.assertEqual(svc.live_bank_context('CIMB_PERSONAL')['provider_error']['code'],'INVALID_LIVE_EXTRACTION')

    def test_combined_margin_not_used_as_asset_margin(self):
        reply=extraction(); reply['rules']={'margin_asset_only':{'source_id':'CIMB_PERSONAL',
            'evidence_quote':'Up to 95% including fees.','raw_number':95,'raw_unit':'percent'}}
        svc,_=service(reply,lambda s:TEXT+' Up to 95% including fees.')
        self.assertEqual(svc.live_bank_context('CIMB_PERSONAL')['provider_error']['code'],'AMBIGUOUS_MARGIN')

    def test_unknown_rate_basis_stays_noncalculable(self):
        reply=extraction(); reply['rates'][0]['rate_basis']='unknown'; reply['rates'][0]['basis_evidence_quote']=''
        svc,_=service(reply); result=svc.live_bank_context('CIMB_PERSONAL')
        self.assertFalse(result['rates'][0]['usable_for_planning_calculation'])

    def test_nominal_claim_needs_nominal_evidence(self):
        reply=extraction(); reply['rates'][0]['rate_basis']='reducing_nominal'
        svc,_=service(reply)
        self.assertEqual(svc.live_bank_context('CIMB_PERSONAL')['provider_error']['code'],'AMBIGUOUS_RATE_BASIS')

    def test_no_partial_commit_after_failed_rate_validation(self):
        reply=extraction(); reply['rates'][0]['annual_rate_percent']=49
        svc,_=service(reply); result=svc.live_bank_context('CIMB_PERSONAL')
        self.assertEqual(result['rules'],{}); self.assertEqual(result['rates'],[])

    def test_dated_base_safeguards_not_silently_extended(self):
        base={'verified_on':'2026-10-10','valid_until':'2026-11-09','bnm_sources':{},
              'products':{'CIMB_PERSONAL':{'bank':'CIMB','product':'personal','max_months':60,'max_age':58,'source':'old'}}}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'base.json'; p.write_text(json.dumps(base)); out=Path(d)/'live.json'
            meta=write_engine_policy_config(p,[snapshot()],out)
            generated=json.loads(out.read_text())
            self.assertEqual(generated['products']['CIMB_PERSONAL']['max_months'],84)
            self.assertEqual(generated['valid_until'],'2026-11-09')
            self.assertIn('max_age',meta['provenance']['CIMB_PERSONAL']['inherited_offline_fields'])

    def test_expired_live_context_rejected(self):
        s=snapshot(); s['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        with self.assertRaises(ServiceError): public_rate_planning_quote(None,s,'R0','')

    def test_public_rate_needs_matching_product_and_conditions(self):
        q=SimpleNamespace(bank_code='CIMB_PERSONAL',product='personal')
        s=snapshot()
        with self.assertRaises(ServiceError) as e: public_rate_planning_quote(q,s,'R0','wrong')
        self.assertEqual(e.exception.code,'RATE_CONDITIONS_UNCONFIRMED')


if __name__=='__main__': unittest.main()
