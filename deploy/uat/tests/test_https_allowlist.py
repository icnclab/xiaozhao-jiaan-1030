"""New allowlist checks only; no live DB, LINE, HTTP or service starts."""
from pathlib import Path
import sys,unittest,httpx
from starlette.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import https_bridge as bridge

class Empty(httpx.AsyncByteStream):
    async def __aiter__(self):yield b'Unauthorized'

class AllowlistChecks(unittest.TestCase):
    def test_liff_and_actual_assets(self):
        self.assertTrue(bridge.route_allowed('GET','/liff'))
        self.assertTrue(bridge.route_allowed('GET','/liff/bind'))
        self.assertEqual(len(bridge.STATIC_FILES),3)
        self.assertTrue(all(bridge.route_allowed('GET',p) for p in bridge.STATIC_FILES))
        self.assertFalse(bridge.route_allowed('GET','/assets/unknown.js'))
    def test_auth_and_caregiver_methods(self):
        for method,path in [('POST','/api/auth/liff'),('POST','/api/auth/liff/bind'),('GET','/api/me'),('POST','/api/qa/ask'),('GET','/api/cases/mine')]:self.assertTrue(bridge.route_allowed(method,path))
        self.assertFalse(bridge.route_allowed('GET','/api/auth/liff'))
        self.assertFalse(bridge.route_allowed('DELETE','/api/me'))
    def test_all_non_uat_surfaces_deny(self):
        for path in ['/admin','/api/admin/healthz','/api/auth/login','/api/dev/line/users','/api/fieldtest/dashboard','/.env','/run/uat-private/uat.local.env','/api/docs','/api/redoc','/api/openapi.json','/api/line/webhook','/api/jiaan1030/emergencies','/api/jiaan1030/emergency-ui','/api/jiaan1030/service-catalog/review','/liff/mpc-review','/api/unknown']:
            for method in ['GET','POST','PUT','DELETE','OPTIONS']:self.assertFalse(bridge.route_allowed(method,path),(method,path))
    def test_noncanonical_paths_deny(self):
        for path in ['/api//me','/api/%6de','/assets/.env','/assets/../index.js','/assets/index.js.map','/api\\admin']:
            self.assertFalse(bridge.route_allowed('GET',path))
    def test_denied_routes_never_reach_upstream(self):
        seen=[]
        def fake(request):seen.append(request);return httpx.Response(401,stream=Empty())
        with TestClient(bridge.create_app('https://uat-routes.trycloudflare.com',httpx.MockTransport(fake)),headers={'host':'uat-routes.trycloudflare.com'}) as c:
            for path in ['/admin','/.env','/api/line/webhook','/api/admin/users','/api/fieldtest/dashboard']:
                self.assertEqual(c.post(path,json={}).status_code,404)
            self.assertFalse(seen)
            self.assertEqual(c.get('/api/me').status_code,401)
            self.assertEqual(str(seen[0].url),'http://127.0.0.1:8151/api/me')

if __name__=='__main__':unittest.main()
