import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from loan_llm.client import GrafilabClient, ServiceError
from loan_llm.settings import Settings, read_env_file


class FakeTransport:
    def __init__(self, modify=None): self.calls=[]; self.modify=modify
    def __call__(self, method, path, payload):
        self.calls.append((method,path,payload))
        if path == '/models': return {'data':[{'id':'accessible/chat-model'}]}
        context = json.loads(payload['messages'][1]['content'])
        if 'reviewed_facts' in context:
            key = next(iter(context['reviewed_facts']))
            answer = {'paragraphs':[{'template':f'The reviewed reference states: [[{key}]]',
                'source_ids':context['reviewed_facts'][key]['source_ids']}]}
        else:
            answer = {'summary_template':'Your simulation indicates [[O0_BASE]].',
                      'rationales':[{'action_id':a['action_id'],'template':f"Consider this calculated scenario: [[{a['action_id']}_RESULT]]."}
                                    for a in context['eligible_actions'][:3]],
                      'checklist_ids':['REQUOTE','RESERVE']}
        if self.modify: answer = self.modify(answer)
        return {'choices':[{'message':{'content':json.dumps(answer)}}], 'usage':{'total_tokens':100}}

class ClientTests(unittest.TestCase):
    def test_models_available_and_case_insensitive(self):
        c=GrafilabClient(Settings(model='ACCESSIBLE/CHAT-MODEL'),FakeTransport())
        self.assertTrue(c.models()['configured_model_available'])

    def test_no_assumed_model(self):
        c=GrafilabClient(Settings(),FakeTransport())
        with self.assertRaises(ServiceError) as e: c.complete('',{})
        self.assertEqual(e.exception.code,'MISSING_MODEL')

    def test_missing_key_actionable(self):
        with self.assertRaises(ServiceError) as e: GrafilabClient(Settings()).models()
        self.assertEqual(e.exception.code,'MISSING_KEY')

    def test_invalid_endpoint_prevents_key_exfiltration(self):
        with self.assertRaises(ServiceError): GrafilabClient(Settings(base_url='https://evil.example/v1'))

    def test_provider_error_body_not_exposed(self):
        import urllib.error, io
        error=urllib.error.HTTPError('https://llm.grafilab.ai/v1/models',401,'bad',{},io.BytesIO(b'private secret'))
        with patch('urllib.request.OpenerDirector.open',side_effect=error):
            with self.assertRaises(ServiceError) as e: GrafilabClient(Settings(api_key='existing-key')).models()
        self.assertEqual(e.exception.code,'AUTH_REJECTED'); self.assertNotIn('secret',str(e.exception))

    def test_status_does_not_expose_key(self):
        self.assertNotIn('my-key',json.dumps(Settings(api_key='my-key').public_status()))

    def test_dotenv_is_literal_and_os_settings_win(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'.env'; p.write_text('GRAFILAB_API_KEY="existing-key"\nGRAFILAB_MODEL=a\nIGNORED=bad\n')
            self.assertEqual(read_env_file(p)['GRAFILAB_API_KEY'],'existing-key')
            with patch.dict('os.environ',{'GRAFILAB_MODEL':'available-model'}):
                self.assertEqual(Settings.load(p).model,'available-model')
