"""Isolated HTTP tests: no database connection, seed, reset, or app lifespan."""
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi import HTTPException

from app.api import caregiver_routes as routes
from app.auth import current_user
from app.db import get_db
from app.models import Document, DocumentVersion, User
from app.services import source_downloads


class FakeDb:
    def __init__(self, user, version, document):
        self.objects = {(User, user.id): user, (DocumentVersion, version.id): version,
                        (Document, document.id): document}
        self.logs = []
    def get(self, model, key):
        return self.objects.get((model, key))
    def execute(self, *args, **kwargs):
        pass
    def scalar(self, statement, params=None):
        if params and 'nonce' in params:
            return next((1 for log in self.logs if log.action == 'source.download'
                         and log.meta.get('download_nonce') == params['nonce']), None)
        return None
    def add(self, row):
        self.logs.append(row)
    def commit(self):
        pass


def _fake_visible_version(db, user, version_id):
    """站在這份測試的範圍外：只重現 org 隔離這一條，不重現完整的
    facility_type／current_versions／歷史引用規則（那些由 tests/test_authz.py、
    tests/test_source_disposition.py 的真實 DB fixture 覆蓋）。"""
    version = db.get(DocumentVersion, version_id)
    document = db.get(Document, version.document_id) if version else None
    if version is None or document is None or document.org_id != user.org_id:
        raise HTTPException(404, detail={"code": "not_found", "message": "找不到資料"})
    return version, document


class Downloads(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / 'source.pdf'
        path.write_bytes(b'%PDF-1.4 test')
        self.user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), is_active=True, role='caregiver')
        self.document = SimpleNamespace(id=uuid.uuid4(), org_id=self.user.org_id)
        self.version = SimpleNamespace(id=uuid.uuid4(), document_id=self.document.id,
                                       mime='application/pdf', file_path=str(path), file_name='source.pdf')
        self.db = FakeDb(self.user, self.version, self.document)
        patcher = patch.object(routes, '_visible_version', _fake_visible_version)
        patcher.start()
        self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(routes.router, prefix='/api')
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def issue(self):
        return self.client.post(f'/api/sources/versions/{self.version.id}/download-url')

    def test_authorized_url_and_download(self):
        response = self.issue()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['expires_in'], 300)
        result = self.client.get(response.json()['url'])
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.content, b'%PDF-1.4 test')
        self.assertEqual(result.headers['content-type'], 'application/pdf')
        # PDF 可在瀏覽器內建檢視器開啟，應為 inline 而非強制下載。
        self.assertIn('inline;', result.headers['content-disposition'])
        self.assertEqual(self.client.get(response.json()['url']).status_code, 403)

    def test_non_viewable_type_stays_attachment(self):
        path = Path(self.temp.name) / 'source.docx'
        path.write_bytes(b'PK fake docx')
        self.version.mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        self.version.file_path = str(path)
        self.version.file_name = 'source.docx'
        result = self.client.get(self.issue().json()['url'])
        self.assertEqual(result.status_code, 200)
        # docx 無法在瀏覽器原生預覽，不能假裝成線上閱讀，維持下載。
        self.assertIn('attachment;', result.headers['content-disposition'])

    def test_wrong_org_cannot_issue(self):
        self.document.org_id = uuid.uuid4()
        self.assertEqual(self.issue().status_code, 404)

    def test_wrong_role_cannot_issue(self):
        self.user.role = 'other'
        self.assertEqual(self.issue().status_code, 403)

    def test_expired(self):
        with patch.object(source_downloads.time, 'time', return_value=1000):
            ticket = source_downloads.issue(str(self.user.id), str(self.version.id), self.version.file_path)
        with patch.object(source_downloads.time, 'time', return_value=1300):
            self.assertEqual(self.client.get('/api/sources/download/' + ticket).status_code, 403)

    def test_tampered(self):
        url = self.issue().json()['url']
        replacement = '0' if url[-1] != '0' else '1'
        self.assertEqual(self.client.get(url[:-1] + replacement).status_code, 403)

    def test_missing_file(self):
        url = self.issue().json()['url']
        Path(self.version.file_path).unlink()
        self.assertEqual(self.client.get(url).status_code, 404)


if __name__ == '__main__':
    unittest.main()
