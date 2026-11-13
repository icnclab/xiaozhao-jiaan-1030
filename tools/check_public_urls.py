import sys,unittest,ast
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root/'backend'))
from app.config import Settings,get_settings
from app.services import notifications,tts_service
from app.api import caregiver_routes
from fastapi import Response
class HostTests(unittest.TestCase):
 def test_default_local(self):
  self.assertEqual(Settings.model_fields['public_base_url'].default,'http://127.0.0.1:8140')
 def test_production_config(self):
  self.assertEqual(get_settings().public_base_url,'https://stust.tail379935.ts.net')
 def test_notification_config_with_and_without_liff(self):
  for base in ('https://stust.tail379935.ts.net/','https://example.invalid'):
   for liff in ('','123-abc'):
    with patch.object(notifications,'get_settings',return_value=SimpleNamespace(public_base_url=base,liff_id=liff)):
     self.assertEqual(notifications.liff_url('/cases/42'),base.rstrip('/')+'/liff/cases/42')
 def test_tts_url(self):
  a=SimpleNamespace(status='ready',expires_at=datetime.now(timezone.utc),token_id='test')
  with patch.object(tts_service,'sign_media_token',return_value='mock-token'):
   self.assertEqual(tts_service.media_url(a),'https://stust.tail379935.ts.net/api/media/tts/mock-token')
 def test_download_url_without_db(self):
  v=SimpleNamespace(id='v',file_path='unused'); u=SimpleNamespace(id='u'); response=Response()
  with patch.object(caregiver_routes,'_download_version',return_value=v), patch.object(caregiver_routes.source_downloads,'issue',return_value='mock-ticket'):
   result=caregiver_routes.source_download_url('v',response,u,None)
  self.assertEqual(result['url'],'https://stust.tail379935.ts.net/api/sources/download/mock-ticket')
  self.assertEqual(response.headers['Cache-Control'],'no-store')
 def test_python_syntax(self):
  for name in ('backend/app/config.py','backend/app/services/notifications.py'):
   ast.parse((root/name).read_text(encoding='utf-8'))
 def test_frontend_relative_and_admin_routes(self):
  self.assertIn('fetch(path,',(root/'frontend/src/api.ts').read_text(encoding='utf-8'))
  self.assertIn('navigate("/admin/login"',(root/'frontend/src/admin/AdminApp.tsx').read_text(encoding='utf-8'))
  self.assertIn('navigate("/admin/cases"',(root/'frontend/src/admin/AdminApp.tsx').read_text(encoding='utf-8'))
 def test_caregiver_sos_entries_use_sos_app_not_emergency_ui(self):
  # 照服員可見的LIFF頁一律連獨立SOS App(8443)；/emergency-ui只留給後台管理介面。
  sos_app='https://stust.tail379935.ts.net:8443/api/jiaan1030/sos-app/'
  for name in ('frontend/src/liff/pages/HomePage.tsx','frontend/src/liff/pages/ReportEntryPage.tsx'):
   text=(root/name).read_text(encoding='utf-8')
   self.assertIn(sos_app,text,name)
   self.assertNotIn('href="/api/jiaan1030/emergency-ui"',text,name)
  for name in ('frontend/src/admin/AdminApp.tsx','frontend/src/admin/pages/AdminCasesPage.tsx'):
   text=(root/name).read_text(encoding='utf-8')
   self.assertIn('/api/jiaan1030/emergency-ui',text,name)
unittest.main(verbosity=2)
