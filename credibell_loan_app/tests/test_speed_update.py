import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hashlib import sha256
from loan_engine.documents import parse_fields
from loan_engine.demo_documents import fixture_fields
from server.document_service import verify_document
from server.store import Store
from server.ocr_adapter import DocumentReader
from launch import missing_packages, required_versions

ROOT=Path(__file__).resolve().parents[1]

class Reader:
    def __init__(self): self.calls=0
    def read_with_preview(self,kind,content,sid):
        self.calls+=1
        lines=[(f'{key}: {value}',.999) for key,value in fixture_fields()[kind].items()]
        return parse_fields(kind,lines,sha256(content).hexdigest()),'controlled_sample',b'preview'

class SpeedTests(unittest.TestCase):
    def test_identical_upload_reused_only_in_same_session_and_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            reader=Reader();store=Store(Path(directory)/'test.sqlite3');session,_=store.session()
            sid=session['id']
            for content in (b'first',b'first',b'changed'):
                parsed=verify_document(store,reader,sid,'profile',content,'DEMO00001')
                self.assertEqual(parsed.source_sha256,sha256(content).hexdigest())
            self.assertEqual(reader.calls,2);self.assertEqual(store.image(sid,'profile'),b'preview')
            verify_document(store,reader,sid,'ctos_statement',b'changed','DEMO00001')
            self.assertEqual(reader.calls,3)
            other,_=store.session()
            verify_document(store,reader,other['id'],'profile',b'changed','DEMO00001')
            self.assertEqual(reader.calls,4)

    def test_read_and_preview_share_one_render(self):
        reader=DocumentReader(ROOT/'config/mock_registry.json')
        reader.ocr=type('OCR',(),{'recognize':lambda _,content:[('ANONYMIZED SAMPLE',.999)]+[(f'{key}: {value}',.999) for key,value in fixture_fields()['profile'].items()]})()
        with patch.object(reader,'pages',return_value=[b'first-page']) as pages:
            parsed,source,preview=reader.read_with_preview('profile',b'sample','DEMO00001')
        pages.assert_called_once_with(b'sample');self.assertEqual(preview,b'first-page');self.assertEqual(parsed.fields['age'],32)

    def test_package_version_check_does_not_import_models_or_install(self):
        result=type('Result',(),{'returncode':0,'stdout':'[]'})()
        with patch('launch.subprocess.run',return_value=result) as run:
            self.assertEqual(missing_packages('python',{'numpy':'2.5.3'}),[])
        command=run.call_args.args[0]
        self.assertIn('importlib.metadata',command[2]);self.assertNotIn('pip',command)
        self.assertEqual(json.loads(command[3]),{'numpy':'2.5.3'})

    def test_requirements_are_checked_by_pinned_version(self):
        expected=required_versions(ROOT/'requirements.txt')
        self.assertEqual(expected['pypdfium2'],'5.13.0')
        result=type('Result',(),{'returncode':0,'stdout':'["pypdfium2"]'})()
        with patch('launch.subprocess.run',return_value=result):
            self.assertEqual(missing_packages('python',expected),['pypdfium2'])

if __name__=='__main__': unittest.main()
