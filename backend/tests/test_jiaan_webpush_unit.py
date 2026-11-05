import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'app' / 'services' / 'jiaan_webpush.py'
spec = importlib.util.spec_from_file_location('jiaan_webpush_standalone', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class WebpushUnit(unittest.TestCase):
    def test_dispatch_is_off_by_default(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'JIAAN_WEBPUSH_DISPATCH':'off'}):
            self.assertFalse(module.enabled())
    def test_endpoint_ssrf_rejection(self):
        for value in ['http://localhost/a', 'https://127.0.0.1/push',
                      'https://evil.example/push','file:///etc/passwd',
                      'https://fcm.googleapis.com.evil.com/x',
                      'https://name:password@fcm.googleapis.com/x']:
            self.assertFalse(module.endpoint_allowed(value), value)
    def test_known_provider(self):
        self.assertTrue(module.endpoint_allowed('https://fcm.googleapis.com/fcm/send/AA'))
        self.assertTrue(module.endpoint_allowed('https://web.push.apple.com/123'))
    def test_privacy_payload(self):
        import uuid
        d=module.alert_payload(uuid.uuid4(),'new')
        self.assertNotIn('patient',str(d)); self.assertNotIn('姓名',str(d))
        self.assertNotIn('address',str(d)); self.assertEqual(d['stage'],'new')
    def test_queue_off_no_database_access(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'JIAAN_WEBPUSH_DISPATCH':'off'}):
            self.assertEqual(module.sweep(None),0)
            self.assertEqual(module.dispatch_due(None),0)

if __name__=='__main__': unittest.main()
