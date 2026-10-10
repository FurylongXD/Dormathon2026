import io
import json
import unittest
import urllib.error
from unittest.mock import Mock
from grafilab_diagnose import diagnose, error_details
from loan_llm.settings import Settings
from loan_llm.client import ServiceError


class DiagnosticTests(unittest.TestCase):
    def test_recognizes_currency_without_echoing_message(self):
        raw=b'{"error":{"code":"billing_currency_unset","message":"key private-secret"}}'
        result=error_details(raw,{'X-Request-Id':'req_'+'a'*24},'private-secret')
        self.assertEqual(result['provider_error_code'],'billing_currency_unset')
        self.assertNotIn('private-secret',json.dumps(result))

    def test_unknown_code_not_printed(self):
        result=error_details(b'{"error":{"code":"private-secret","message":"secret"}}',{},'private-secret')
        self.assertIsNone(result['provider_error_code'])

    def test_html_denial_classified_without_echo(self):
        result=error_details(b'<!DOCTYPE html><html>private-secret</html>',{})
        self.assertEqual(result['body_format'],'html')
        self.assertNotIn('private-secret',json.dumps(result))

    def test_invalid_request_id_omitted(self):
        self.assertIsNone(error_details(b'{}',{'X-Request-Id':'private-secret'})['request_id'])

    def test_missing_key_has_no_network_call(self):
        opener=Mock()
        with self.assertRaises(ServiceError): diagnose(Settings(),opener)
        opener.open.assert_not_called()

    def test_403_code_and_request_id_reach_diagnostics(self):
        headers={'X-Request-Id':'req_'+'b'*24}
        opener=Mock()
        opener.open.side_effect=urllib.error.HTTPError('https://llm.grafilab.ai/v1/models',403,'forbidden',headers,
            io.BytesIO(b'{"error":{"code":"billing_currency_unset","message":"do not echo"}}'))
        result=diagnose(Settings(api_key='existing-key'),opener)
        self.assertEqual(result['http_status'],403)
        self.assertEqual(result['provider_error_code'],'billing_currency_unset')
        self.assertNotIn('do not echo',json.dumps(result))


if __name__=='__main__': unittest.main()
