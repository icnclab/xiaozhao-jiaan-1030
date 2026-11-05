"""No external services. Verify emergency UI uses read-only notification status API."""
import pathlib
import unittest


class TestEmergencyStatusUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[2]
        cls.html = (root / 'backend/app/api/jiaan1030_emergency.html').read_text(encoding='utf-8-sig')
        cls.home = (root / 'frontend/src/liff/pages/HomePage.tsx').read_text(encoding='utf-8-sig')

    def test_notification_status_is_read_only(self):
        self.assertIn("'/delivery-status'", self.html)
        self.assertIn('/emergencies/notification-readiness', self.html)
        self.assertIn('LINE 平台受理≠手機已收到', self.html)
        self.assertIn('p.textContent=line', self.html)
        self.assertNotIn('detail.innerHTML=', self.html)

    def test_both_active_and_resolved_incidents_have_status_button(self):
        # 2026-11 改版後，開啟／已接手／已完成三種清單改共用同一張卡片渲染函式 evCard()，
        # 不再各自內嵌重複的 appendDeliveryButton 呼叫；改為驗證：
        # (1) evCard() 內部確實呼叫了 appendDeliveryButton，(2) 開啟中與已完成清單都有呼叫 evCard()。
        self.assertIn('appendDeliveryButton(x,wrap)', self.html)
        self.assertGreaterEqual(self.html.count('evCard(x'), 2)
        self.assertIn('showReadiness()', self.html)

    def test_entry_not_restricted_by_username(self):
        self.assertIn('XZ_EMERGENCY_ROLE_ENTRY_20261103', self.home)
        self.assertNotIn('user.username.startsWith("jiaan_")', self.home)

    def test_statuses_cover_all_stages(self):
        for value in ('unacknowledged_60s', 'unacknowledged_180s', 'queued', 'accepted', 'failed', 'skipped'):
            self.assertIn(value, self.html)

if __name__ == '__main__':
    unittest.main()
