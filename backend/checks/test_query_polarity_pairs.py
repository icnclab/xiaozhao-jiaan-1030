"""2026-11-13 batch: 問題語意理解配對測試 (EMERGENCY_NOTE 批次附帶項目二).

Finds and documents where polarity/tense matters versus where it is safe to
be insensitive to it, instead of assuming "same answer == bug". Pure-function
checks (no DB) cover query_understanding/qa_policy directly; a few read-only
replays against ltc_clean (same pattern as test_stt_negation_integration.py)
confirm the real graph's end-to-end behavior for declarative statements that
are not risk-rule hits.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.qa_policy import screen_risk, DEFAULT_POLICY
from app.services.query_understanding import (
    permission_intent, medication_admin_intent, purchasing_rule_intent,
)


def _codes(question):
    return {r.code for r in screen_risk(question, DEFAULT_POLICY)}


class PermissionQuestionsAreIntentionallyPolarityInsensitive(unittest.TestCase):
    """類別 1（詢問允許與否）：「可以／不可以」都是在問同一條規範是否適用，
    規範答案本來就該相同（不是錯誤）。根因在 query_understanding 的
    _FRAME／PERMISSION_RE：兩種問法都辨識為同一個 permission_intent + 同一個
    purchasing_rule_intent('medicine')，所以會查到同一條 BA16 規則 —— 這是
    設計如此，不需要修正；過去有人誤以為「答案相同」就是 bug，這裡用測試
    把「規則查詢路徑本來就不分極性」這個事實釘下來，避免之後被誤修。"""

    def test_can_and_cannot_help_buy_medicine_hit_the_same_rule(self):
        pos, neg = '我可以幫忙買藥嗎？', '我不可以幫忙買藥嗎？'
        self.assertTrue(permission_intent(pos))
        self.assertTrue(permission_intent(neg))
        self.assertTrue(medication_admin_intent(pos))
        self.assertTrue(medication_admin_intent(neg))
        self.assertEqual(purchasing_rule_intent(pos), purchasing_rule_intent(neg))


class DeclarativeFactStatementsDoNotFalselyEscalate(unittest.TestCase):
    """類別 2/3（描述已發生事實／否定已發生事實），非風險語句：
    「家屬要求／沒有要求我購買成藥」「我已經／尚未幫忙買藥」都只是在描述
    一個行政事實，不是風險事件，也不是在問允不允許。這兩對在
    qa_policy.screen_risk 不應該命中任何風險規則（兩邊都不該被誤判成
    緊急狀況），且彼此命中的風險規則集合必須相同（都是空集合）——
    negation 不該在這裡被用來「發明」或「消除」一個不存在的風險。"""

    def test_family_request_pair_hits_no_risk_rules(self):
        pos, neg = '家屬要求我購買成藥。', '家屬沒有要求我購買成藥。'
        self.assertEqual(_codes(pos), set())
        self.assertEqual(_codes(neg), set())

    def test_already_vs_not_yet_bought_medicine_hits_no_risk_rules(self):
        pos, neg = '我已經幫忙買藥了。', '我尚未幫忙買藥。'
        self.assertEqual(_codes(pos), set())
        self.assertEqual(_codes(neg), set())


class FallNegationIsExplicitlyGuardedInRiskScreening(unittest.TestCase):
    """類別 3/6（否定已發生事實 + 緊急否定語句）：跌倒是唯一會被誤判的風險
    規則（因為「跌倒」兩字本身就是 fall_head_impact 的觸發詞），所以
    qa_policy.screen_risk 專門用 app/services/qa_policy.py:227 的 negation
    strip 去掉「沒有跌倒／還沒跌倒／尚未跌倒」再比對規則。這裡直接測
    screen_risk（根因所在的函式），比透過整個 graph 更精準地釘住根因。"""

    def test_actual_fall_is_flagged(self):
        self.assertIn('fall_head_impact', _codes('個案跌倒了。'))

    def test_negated_fall_is_not_flagged(self):
        self.assertNotIn('fall_head_impact', _codes('個案沒有跌倒。'))
        self.assertNotIn('fall_head_impact', _codes('個案還沒跌倒。'))
        self.assertNotIn('fall_head_impact', _codes('個案尚未跌倒。'))

    def test_fall_prevention_training_mention_is_not_flagged(self):
        # 「跌倒預防課程」同樣會命中「跌倒」字面，但不是事件描述。
        self.assertNotIn('fall_head_impact', _codes('請問跌倒預防課程怎麼報名？'))


class EmergencyVitalSignNegationIsCorrectlyTreatedAsThePositiveFinding(unittest.TestCase):
    """類別 6 的另一個方向，容易被誤修：「沒有呼吸」「沒有脈搏」字面上有
    「沒有」，但臨床意義上『沒有呼吸/沒有脈搏』本身就是緊急狀況的陽性
    發現，不是在否定風險。emergency 規則故意把「沒有呼吸」「沒有心跳」
    寫進觸發詞本身（qa_policy.py:116, 169），而不是像 fall_head_impact
    那樣去 strip 「沒有」。這裡釘住這個刻意的不對稱設計，避免未來有人
    看到「含有『沒有』」就直覺地套用跟跌倒一樣的 negation-strip，
    那樣反而會把真正的緊急狀況消除成『無風險』，提高危險漏辨率。"""

    def test_no_breathing_is_flagged_as_emergency_not_negated_away(self):
        self.assertIn('emergency', _codes('個案沒有呼吸。'))

    def test_no_pulse_is_flagged_as_emergency_not_negated_away(self):
        self.assertIn('emergency', _codes('摸不到脈搏。'))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful():
        raise SystemExit(1)
