"""HTTP integration verification against a running local server, in isolated synthetic sessions.

Does not invoke Grafilab unless the server was explicitly configured with a key/model.
Run: python verify_api.py --url http://127.0.0.1:8502
"""
import argparse
from http.cookiejar import CookieJar
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent

class LocalClient:
    def __init__(self,url):
        self.url=url.rstrip('/'); self.csrf=''; self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    def call(self,path,method='GET',data=None,headers=None,expected=200):
        h={'Origin':self.url}
        if self.csrf: h['X-CSRF-Token']=self.csrf
        if isinstance(data,dict): data=json.dumps(data).encode(); h['Content-Type']='application/json'
        h.update(headers or {})
        request=urllib.request.Request(self.url+path,method=method,data=data,headers=h)
        try:
            with self.opener.open(request,timeout=90) as response: status=response.status; raw=response.read(); content_type=response.headers.get('Content-Type','')
        except urllib.error.HTTPError as e: status=e.code; raw=e.read(); content_type=e.headers.get('Content-Type','')
        assert status==expected,(path,status,raw[:300])
        return json.loads(raw) if 'application/json' in content_type else raw
    def wait(self,jid):
        until=time.monotonic()+120
        while time.monotonic()<until:
            job=self.call('/api/jobs/'+jid)
            if job['state']=='failed': raise AssertionError(job['message'])
            if job['state']=='done': return job
            time.sleep(.25)
        raise AssertionError('Local job timed out.')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--url',default='http://127.0.0.1:8502'); args=parser.parse_args()
    parts=urlparse(args.url)
    if parts.scheme!='http' or parts.hostname not in {'127.0.0.1','localhost'}: parser.error('This verification only calls your localhost server.')
    c=LocalClient(args.url); bootstrap=c.call('/api/bootstrap'); c.csrf=bootstrap['csrf']
    assert all(d['state']=='empty' for d in bootstrap['documents'])
    c.call('/api/assess','POST',expected=400)
    c.call('/api/load-demo','POST',{'product':'car'},headers={'X-CSRF-Token':'bad'},expected=403)
    c.call('/api/load-demo','POST',{'product':'car'},headers={'Origin':'https://other.example'},expected=403)
    c.call('/api/documents/profile/verify','POST',b'not an image',headers={'X-Mock-Only':'true'},expected=400)
    raw=(ROOT/'sample_documents/alternate/profile.png').read_bytes()
    c.call('/api/documents/profile/verify','POST',raw,expected=400)
    verified=c.call('/api/documents/profile/verify','POST',raw,headers={'X-Mock-Only':'true'})
    assert verified['state']=='verified'; assert sum(d['state']=='saved' for d in verified['documents'])==0
    c.call('/api/documents/profile/save','POST',{'digest':'wrong'},expected=400)
    c.call('/api/documents/profile/save','POST',{'digest':verified['digest']})
    viewed=c.call('/api/documents/profile'); assert viewed['fields']['age']==32
    other=LocalClient(args.url); other.csrf=other.call('/api/bootstrap')['csrf']; other.call('/api/documents/profile',expected=404)
    jid=c.call('/api/load-demo','POST',{'product':'car'})['job_id']
    other.call('/api/jobs/'+jid,expected=404); c.wait(jid)
    assert all(d['state']=='saved' for d in c.call('/api/documents')['documents'])
    # A PDF replaces an image through the same verify/review/save API.
    for kind in ('profile','bank_statement'):
        pdf=c.call('/api/documents/'+kind+'/verify','POST',(ROOT/'sample_documents/pdf'/(kind+'.pdf')).read_bytes(),headers={'X-Mock-Only':'true'})
        assert pdf['state']=='verified'
        fields=c.call('/api/documents/'+kind)
        assert fields['page_count']==(3 if kind=='bank_statement' else 1)
        assert fields['evidence']
        c.call('/api/documents/'+kind+'/save','POST',{'digest':pdf['digest']})
    # Replace the quotation with an unregistered, differently labelled mock image, then save it independently.
    q=c.call('/api/documents/loan_quotation/verify','POST',(ROOT/'sample_documents/alternate/loan_quotation.png').read_bytes(),headers={'X-Mock-Only':'true'})
    c.call('/api/assess','POST',expected=400)
    c.call('/api/documents/loan_quotation/save','POST',{'digest':q['digest']})
    c.wait(c.call('/api/assess','POST')['job_id'])
    result=c.call('/api/result')['assessment']; assert len(result['offers'])==2
    assert len(result['bank_comparison'])==6
    assert all(b['effective_cashflow_rate'] is None for b in result['bank_comparison'] if not b['quoted_offer_id'])
    for offer in result['offers']:
        assert 0<=offer['approval_chance']['generic_synthetic_probability']<=1
        assert offer['approval_chance']['bank_specific_probability'] is None
        assert offer['credit_risk']['rating'] in 'ABCDEF'
        assert set(offer['shap'])=={'approval','risk','health','risk_rating'}
        assert offer['quotation_summary']['months']==84
        assert offer['financials']['requested_bank_financing_rm']==90000
        assert offer['financials']['minimum_asset_cash_rm']==10000
        for name,target in [('approval',offer['approval_chance']['generic_synthetic_probability']),('risk',offer['credit_risk']['probability_90day_arrears_next_12m']),('health',offer['internal_credit_health_score']['value'])]:
            assert abs(offer['shap'][name]['reconstructed_prediction']-target)<1e-5
        assert any(s['approval_change_percentage_points']>0 for s in offer['alternative_scenarios'])
    assert all('fields' not in item for item in result['document_audit'].values())
    assert c.call('/api/bootstrap')['assessment']==result
    c.call('/api/documents/profile','DELETE'); assert c.call('/api/result')['assessment'] is None
    c.call('/api/clear','POST'); assert all(d['state']=='empty' for d in c.call('/api/bootstrap')['documents'])
    print('PASS: isolated HTTP sessions, CSRF/origin, image validation, separate saves, actual OCR, alternate layouts, complete analysis, three SHAP reconstructions, comparison, result persistence and invalidation.')

if __name__=='__main__': main()
