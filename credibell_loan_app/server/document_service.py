"""Session-scoped extraction reuse without sharing applicant records."""
from dataclasses import asdict
from hashlib import sha256
from loan_engine.documents import DocumentKind, ParsedDocument
from loan_engine.schema import AssessmentError

def verify_document(store,reader,sid,kind,content,session_demo_id):
    if kind not in {k.value for k in DocumentKind}: raise AssessmentError('Choose a supported document slot.')
    if len(content)>12_000_000: raise AssessmentError('Maximum file size is 12 MB.')
    previous=store.documents(sid).get(kind)
    if previous and previous['doc']['source_sha256']==sha256(content).hexdigest():
        parsed=ParsedDocument(**previous['doc']);source=previous['source'];preview=store.image(sid,kind)
    elif hasattr(reader,'read_with_preview'):
        parsed,source,preview=reader.read_with_preview(kind,content,session_demo_id)
    else:
        parsed,source=reader.read(kind,content,session_demo_id);preview=reader.preview(content)
    store.put_document(sid,kind,asdict(parsed),preview,source)
    return parsed
