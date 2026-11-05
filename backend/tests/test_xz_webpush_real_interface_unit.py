"""Web Push isolated checks. Never connect to a DB or send to a push service."""
from __future__ import annotations
import os
import unittest
from unittest.mock import patch
from app.services import jiaan_webpush as push

class WebPushCurrentInterfaceTests(unittest.TestCase):
    def test_off_by_default(self):
        with patch.dict(os.environ, {'JIAAN_WEBPUSH_DISPATCH': 'off'}):
            self.assertFalse(push.enabled())
            self.assertEqual(push.sweep(None), 0)
            self.assertEqual(push.dispatch_due(None), 0)

    def test_only_https_known_push_provider(self):
        for endpoint in ('http://fcm.googleapis.com/a', 'https://localhost/a',
                         'https://fcm.googleapis.com.attacker.invalid/a',
                         'https://127.0.0.1/','https://fcm.googleapis.com:8443/a'):
            self.assertFalse(push.endpoint_allowed(endpoint), endpoint)
        self.assertTrue(push.endpoint_allowed('https://fcm.googleapis.com/fcm/send/abc'))

    def test_stage_order_and_age(self):
        self.assertEqual(push.STAGES, (('new',0),('unacknowledged_60s',60),('unacknowledged_180s',180)))

    def test_payload_has_no_patient_data(self):
        import uuid
        uid=uuid.UUID('12345678-1234-4123-8123-123456789abc')
        payload=push.alert_payload(uid,'new')
        self.assertEqual(payload['emergency_id'],str(uid))
        self.assertEqual(payload['stage'],'new')
        self.assertNotIn('client',payload)
        self.assertNotIn('patient',payload)

if __name__=='__main__':
    unittest.main()
