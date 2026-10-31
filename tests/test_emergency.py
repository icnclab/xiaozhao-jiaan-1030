"""Local, isolated regression tests. Never accesses production DB."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
import uuid
from datetime import datetime,timezone
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT=Path(__file__).resolve().parents[1] / 'backend' / 'app'

def load_route():
    # Stub only unrelated application dependencies, not FastAPI/Pydantic or the tested source.
    app=types.ModuleType('app');app.__path__=[]
    auth=types.ModuleType('app.auth');auth.current_user=lambda:None
    db=types.ModuleType('app.db');db.get_db=lambda:None
    models=types.ModuleType('app.models');models.User=type('User',(object,),{})
    previous={key:sys.modules.get(key) for key in ('app','app.auth','app.db','app.models')}
    try:
        sys.modules.update({'app':app,'app.auth':auth,'app.db':db,'app.models':models})
        spec=importlib.util.spec_from_file_location('j1030_test_route', ROOT/'jiaan1030_emergency_routes.py')
        mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod);return mod
    finally:
        for key,value in previous.items():
            if value is None:sys.modules.pop(key,None)
            else:sys.modules[key]=value
MOD=load_route()

class Tests(unittest.TestCase):
    def user(self,role='caregiver',active=True):return types.SimpleNamespace(role=role,is_active=active,username='jiaan_test')
    def test_valid_emergency_category(self):
        obj=MOD.NewEmergency(category='fall',client_request_id=uuid.uuid4());self.assertEqual(obj.category,'fall')
    def test_category_rejects_nonsense(self):
        with self.assertRaises(ValidationError):MOD.NewEmergency(category='lunch',client_request_id=uuid.uuid4())
    def test_request_id_required(self):
        with self.assertRaises(ValidationError):MOD.NewEmergency(category='fall',client_request_id='')
    def test_caregiver_can_report(self):MOD.check_role(self.user(),MOD.RESPONDERS)
    def test_supervisor_can_manage(self):MOD.check_role(self.user('supervisor'),MOD.MANAGERS)
    def test_director_can_manage(self):MOD.check_role(self.user('director'),MOD.MANAGERS)
    def test_caregiver_cannot_manage(self):
        with self.assertRaises(HTTPException) as m:MOD.check_role(self.user(),MOD.MANAGERS)
        self.assertEqual(m.exception.status_code,403)
    def test_inactive_cannot_report(self):
        with self.assertRaises(HTTPException):MOD.check_role(self.user(active=False),MOD.RESPONDERS)
    def test_non_jiaan_accounts_blocked(self):
        with self.assertRaises(HTTPException):
            MOD.check_role(types.SimpleNamespace(role='caregiver',is_active=True,username='other_cg01'), MOD.RESPONDERS)
    def test_unknown_role_rejected(self):
        with self.assertRaises(HTTPException):MOD.check_role(self.user('visitor'),MOD.RESPONDERS)
    def test_serialization_web_only_delivery(self):
        row=dict(id=uuid.uuid4(),category='fall',status='open',created_at=datetime.now(timezone.utc),acknowledged_at=None,
                 resolved_at=None,created_by=uuid.uuid4(),acknowledged_by=None,resolved_by=None)
        self.assertEqual(MOD.serialize(row)['delivery'],'web_poll_only')
    def test_fall_and_violence_and_unresponsive(self):
        for c in ('fall','violence','injury','unresponsive','traffic','self_harm','other'):
            self.assertIn(c,MOD.CATEGORIES)
    def test_api_routes(self):
        paths={(r.path,tuple(sorted(r.methods))) for r in MOD.router.routes if hasattr(r,'methods')}
        self.assertTrue(any(p=='/jiaan1030/emergencies' and 'POST' in methods for p,methods in paths))
        self.assertTrue(any(p.endswith('/acknowledge') for p,_ in paths))
        self.assertTrue(any(p.endswith('/resolve') for p,_ in paths))
        self.assertTrue(any(p.endswith('/history') for p,_ in paths))
    def test_served_ui_and_launcher(self):
        app=FastAPI();app.include_router(MOD.router,prefix='/api')
        client=TestClient(app)
        ui=client.get('/api/jiaan1030/emergency-ui')
        js=client.get('/api/jiaan1030/launcher.js')
        self.assertEqual(ui.status_code,200)
        self.assertEqual(js.status_code,200)
        self.assertIn('text/html',ui.headers['content-type'])
        self.assertIn('javascript',js.headers['content-type'])
    def test_frontend_contains_urgent_and_telephone(self):
        h=(ROOT/'jiaan1030_emergency.html').read_text(encoding='utf-8')
        for s in ('tel:119','tel:110','/api/jiaan1030','ltc_session','/api/auth/login','session_token'):
            self.assertIn(s,h)
    def test_launcher_preserves_same_tab(self):
        j=(ROOT/'jiaan1030_emergency_launcher.js').read_text(encoding='utf-8')
        self.assertIn("a.href = '/api/jiaan1030/emergency-ui'",j)
    def test_no_push_claim(self):
        h=(ROOT/'jiaan1030_emergency.html').read_text(encoding='utf-8')
        self.assertIn('不保證 LINE',h)

if __name__=='__main__':unittest.main(verbosity=2)
