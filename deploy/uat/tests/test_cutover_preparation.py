"""Only new preparation checks. No DB, listener, LINE or live HTTP operations."""
from pathlib import Path
import json,sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from starlette.testclient import TestClient
HERE=Path(__file__).resolve()
sys.path.insert(0,str(HERE.parents[1]));sys.path.insert(0,str(HERE.parents[3]/'backend'))
import https_bridge
from app.uat_preflight import database_denial_verified

ORIGIN='https://uat-preparation.trycloudflare.com'
HOST=ORIGIN.removeprefix('https://')
class Body(httpx.AsyncByteStream):
    async def __aiter__(self):yield b'prepared'

class BridgeChecks(unittest.TestCase):
    def client(self,seen):
        async def upstream(request):
            seen.append(request)
            return httpx.Response(200,stream=Body(),headers={'content-type':'text/plain'})
        return TestClient(https_bridge.create_app(ORIGIN,httpx.MockTransport(upstream)),headers={'host':HOST})
    def test_fixed_destination_and_https_headers(self):
        seen=[]
        with self.client(seen) as c:
            r=c.post('/api/auth/liff?probe=1',content=b'test',headers={'X-Forwarded-Host':'evil','X-Forwarded-Proto':'http','X-Internal-Health-Token':'never-forward'})
            self.assertEqual(r.text,'prepared')
        self.assertEqual(str(seen[0].url),'http://127.0.0.1:8151/api/auth/liff?probe=1')
        self.assertEqual(seen[0].headers['host'],HOST)
        self.assertEqual(seen[0].headers['x-forwarded-proto'],'https')
        self.assertNotIn('x-internal-health-token',seen[0].headers)
    def test_webhook_stays_blocked(self):
        seen=[]
        with self.client(seen) as c:
            for method in ['GET','POST','OPTIONS']:
                self.assertEqual(c.request(method,'/api/line/webhook').status_code,404)
            self.assertEqual(c.post('/api/line%2Fwebhook/').status_code,404)
        self.assertFalse(seen)
    def test_wrong_host_is_rejected(self):
        seen=[]
        with self.client(seen) as c:self.assertEqual(c.get('/liff',headers={'host':'stust.tail379935.ts.net'}).status_code,421)
        self.assertFalse(seen)
    def test_docs_not_proxied(self):
        seen=[]
        with self.client(seen) as c:
            for path in ['/api/docs','/api/redoc','/api/openapi.json']:
                self.assertEqual(c.get(path).status_code,404)
        self.assertFalse(seen)
    def test_body_limit_before_upstream(self):
        seen=[]
        with patch.object(https_bridge,'MAX_BODY',4),self.client(seen) as c:
            self.assertEqual(c.post('/api/audio/uploads',content=b'12345').status_code,413)
        self.assertFalse(seen)
    def test_upstream_failure_is_generic(self):
        def failed(request):raise httpx.ConnectError('not public')
        with TestClient(https_bridge.create_app(ORIGIN,httpx.MockTransport(failed)),headers={'host':HOST}) as c:
            r=c.get('/liff');self.assertEqual(r.status_code,502);self.assertNotIn('not public',r.text)
    def test_formal_origin_refused(self):
        with self.assertRaises(ValueError):https_bridge.create_app('https://stust.tail379935.ts.net')

class DenialChecks(unittest.TestCase):
    def test_explicit_hba_without_startup_sqlstate(self):
        self.assertTrue(database_denial_verified(SimpleNamespace(orig=Exception('pg_hba.conf rejects connection'))))
    def test_unrelated_failures_do_not_pass(self):
        for message in ['timeout','password authentication failed','role is not permitted to log in']:
            self.assertFalse(database_denial_verified(SimpleNamespace(orig=Exception(message))))

if __name__=='__main__':unittest.main()
