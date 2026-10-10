"""Verify public extraction changes the real policy/model calculation, without a paid API call."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from loan_engine.documents import DocumentSubmission,parse_fields
from loan_engine.demo_documents import fixture_fields
from loan_engine.engine import LoanAssessmentEngine
from loan_llm.live_policies import write_engine_policy_config,public_rate_planning_quote
from loan_llm.service import LoanLLMService
from loan_llm.settings import Settings

ROOT=Path(__file__).resolve().parents[1]
TEXT='Synthetic test product only. Maximum loan amount is RM10,000. A flat annual rate of 3% applies to synthetic eligible salaried borrowers.'

class ControlledClient:
    def __init__(self): self.context=None
    def complete(self,system,context,max_tokens=1800):
        self.context=context
        return {'rules':{'max_principal':{'source_id':'CIMB_PERSONAL','evidence_quote':'Maximum loan amount is RM10,000.',
            'raw_number':10000,'raw_unit':'rm'}},'age_bands':[],
            'rates':[{'source_id':'CIMB_PERSONAL','evidence_quote':'A flat annual rate of 3% applies to synthetic eligible salaried borrowers.',
            'annual_rate_percent':3,'rate_basis':'flat','basis_evidence_quote':'A flat annual rate of 3%',
            'conditions_quote':'applies to synthetic eligible salaried borrowers.','is_variable':False}],
            'missing_fields':[]},{'model':'controlled-public-test'}

class EngineBridgeTests(unittest.TestCase):
    def test_live_terms_change_policy_and_explicit_rate_scenario_reruns_models(self):
        sub=DocumentSubmission(ROOT/'config/mock_registry.json')
        sub.documents={k:parse_fields(k,[(f'{f}: {v}',.999) for f,v in d.items()],'test') for k,d in fixture_fields('personal').items()}
        a,quotes,_=sub.compile('2026-10-10'); q=quotes[1]
        a=replace(a,months_in_job=12)  # Isolate the published amount ceiling from the separate employment requirement.
        baseline=LoanAssessmentEngine(ROOT/'artifacts'); before=baseline.assess_offer(a,q,'2026-10-10')
        client=ControlledClient(); service=LoanLLMService(Settings(),client,lambda source:TEXT)
        snapshot=service.live_bank_context(q.bank_code)
        self.assertEqual(snapshot['status'],'live_extracted')
        self.assertNotIn('DEMO00001',json.dumps(client.context)); self.assertNotIn('document_audit',json.dumps(client.context))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'policy.json'; write_engine_policy_config(ROOT/'config/bank_policies.json',[snapshot],path)
            after=LoanAssessmentEngine(ROOT/'artifacts',path).assess_offer(a,q,'2026-10-10')
            self.assertTrue(before['policy']['published_rules_pass']); self.assertFalse(after['policy']['published_rules_pass'])
            self.assertEqual(after['policy']['principal_ceiling_rm'],10000)
        changed=public_rate_planning_quote(q,snapshot,'R0',snapshot['rates'][0]['conditions_hash'])
        scenario=baseline.assess_offer(a,changed,'2026-10-10')
        self.assertEqual(q.annual_rate,.0788); self.assertEqual(changed.annual_rate,.03)
        self.assertLess(scenario['financials']['monthly_instalment_rm'],before['financials']['monthly_instalment_rm'])
        self.assertNotEqual(scenario['approval_chance']['generic_synthetic_probability'],before['approval_chance']['generic_synthetic_probability'])

if __name__=='__main__': unittest.main()
