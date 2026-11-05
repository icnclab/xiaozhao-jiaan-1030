"""No external network, no database; verify Web Push encryption contract."""
import os
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
from app.services import jiaan_webpush as wp

class WebPushEncryptedSubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.ctx = patch.dict(os.environ, {'JIAAN_WEBPUSH_SUBSCRIPTION_KEY': Fernet.generate_key().decode('ascii'),
                                         'JIAAN_WEBPUSH_DISPATCH':'off'})
        self.ctx.start()

    def tearDown(self):
        self.ctx.stop()

    def test_encrypted_no_plaintext_and_roundtrip(self):
        raw = 'https://fcm.googleapis.com/fcm/send/fake_device_0123456789'
        ciphertext = wp.encrypt_subscription_value(raw)
        self.assertTrue(ciphertext.startswith('enc:v1:'))
        self.assertNotIn(raw, ciphertext)
        self.assertEqual(wp.decrypt_subscription_value(ciphertext),raw)

    def test_digest_stable_and_secret(self):
        raw='https://fcm.googleapis.com/fcm/send/fake_device_0123456789'
        self.assertEqual(wp.endpoint_hash(raw), wp.endpoint_hash(raw))
        self.assertNotEqual(wp.endpoint_hash(raw), wp.endpoint_hash(raw+'2'))
        self.assertEqual(len(wp.endpoint_hash(raw)),64)

    def test_encrypt_randomized_digest_stable(self):
        text='secret'
        self.assertNotEqual(wp.encrypt_subscription_value(text),wp.encrypt_subscription_value(text))
        self.assertEqual(wp.endpoint_hash(text),wp.endpoint_hash(text))

    def test_plaintext_rejected(self):
        with self.assertRaises(RuntimeError):wp.decrypt_subscription_value('https://example.com/test')

    def test_wrong_key_rejected(self):
        cipher=wp.encrypt_subscription_value('sensitive')
        os.environ['JIAAN_WEBPUSH_SUBSCRIPTION_KEY']=Fernet.generate_key().decode('ascii')
        with self.assertRaises(RuntimeError):wp.decrypt_subscription_value(cipher)

    def test_missing_key_fails_closed(self):
        del os.environ['JIAAN_WEBPUSH_SUBSCRIPTION_KEY']
        with self.assertRaises(RuntimeError):wp.encrypt_subscription_value('secret')
        with self.assertRaises(RuntimeError):wp.endpoint_hash('secret')

if __name__=='__main__':unittest.main()
