"""Read actual images with local OCR and compare to the independent fixture oracle."""
import json
import math
from pathlib import Path
from server.ocr_adapter import DocumentReader
from loan_engine.documents import DocumentKind,DocumentSubmission

ROOT=Path(__file__).resolve().parent

def matches(actual,expected):
    return set(actual)==set(expected) and all(
        math.isclose(actual[k],v,rel_tol=1e-9,abs_tol=1e-9) if isinstance(v,(int,float)) else actual[k]==v
        for k,v in expected.items())

def main():
    reader=DocumentReader(ROOT/'config/mock_registry.json'); count=0
    for product in ('car','home','personal'):
        expected=json.loads((ROOT/'sample_documents'/product/'expected_fields.json').read_text())
        submission=DocumentSubmission(ROOT/'config/mock_registry.json')
        for kind in DocumentKind:
            parsed,source=reader.read(kind.value,(ROOT/'sample_documents'/product/(kind.value+'.png')).read_bytes(),'DEMO00001')
            assert matches(parsed.fields,expected[kind.value]),f'OCR mismatch: {product}/{kind.value}'
            assert source=='registered_synthetic_sample'
            submission.documents[kind.value]=parsed; count+=1
            print(f'{product}/{kind.value}: {parsed.recognition_min_confidence:.3f}',flush=True)
        issued=expected['profile']['issued_date']; submission.compile(issued)
    expected=json.loads((ROOT/'sample_documents/car/expected_fields.json').read_text())
    for kind in ('profile','loan_quotation'):
        parsed,source=reader.read(kind,(ROOT/'sample_documents/alternate'/(kind+'.png')).read_bytes(),'DEMO00001')
        assert source=='anonymized_mock_alias_layout'
        assert matches(parsed.fields,expected[kind]),f'Alternate OCR mismatch: {kind}: {parsed.fields}'
        count+=1; print(f'alternate/{kind}: {parsed.recognition_min_confidence:.3f}',flush=True)
    print(f'PASS: {count} images read, parsed and matched. No LLM used.')

if __name__=='__main__': main()
