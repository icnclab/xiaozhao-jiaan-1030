"""Isolated HTTP tests: no database connection, seed, reset, or app lifespan."""
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
        self.assertIn('attachment;', result.headers['content-disposition'])
        self.assertEqual(self.client.get(response.json()['url']).status_code, 403)

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
