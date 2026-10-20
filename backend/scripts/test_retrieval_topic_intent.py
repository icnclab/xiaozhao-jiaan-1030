"""Ranking regressions; no database mutation or provider substitution."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.retrieval import _ranking_bonuses, _topic_token_groups


class TopicIntentTests(unittest.TestCase):
    def test_short_permission_question(self):
        topic, title, intent = _ranking_bonuses('我可以幫他換藥嗎？', '照顧服務員執行傷口換藥疑義', '一般傷口更換敷料涉及醫療專業判斷')
        self.assertEqual((topic, title, intent), (1.0, 0.3, 0.22))

    def test_unrelated_permission_titles(self):
        for title in ('陪同外出BA13及陪同就醫BA14相關疑義', '照顧服務員伸入肛門清除糞便行為疑義', '口腔抽吸服務使用疑義'):
            self.assertEqual(_ranking_bonuses('我可以幫他換藥嗎？', title, '不得更換管路，須具備資格'), (0.0, 0.0, 0.0))

    def test_technique_not_permission(self):
        self.assertEqual(_ranking_bonuses('我可以幫他換藥嗎？', '基本傷口換藥技術', '更換敷料操作步驟')[2], 0.0)
        self.assertEqual(_ranking_bonuses('換藥怎麼做？', '傷口換藥疑義', '一般傷口更換敷料不得涉及醫療')[2], 0.0)

    def test_other_topics_and_permission_forms(self):
        for action in ('移位', '餵食', '抽痰', '沐浴', '翻身'):
            for question in (f'我可否幫他{action}？', f'能不能{action}？', f'{action}是否能執行？'):
                self.assertGreater(_ranking_bonuses(question, f'{action}業務範圍疑義', f'{action}服務範疇不得涉及醫療')[2], 0.0)
                self.assertEqual(_ranking_bonuses(question, '清除糞便行為疑義', '資格及業務範圍')[2], 0.0)

    def test_scope_chunk_vs_letterhead(self):
        question, title = '我可以幫他換藥嗎？', '傷口換藥疑義'
        self.assertGreater(_ranking_bonuses(question, title, '業務範圍不得涉及護理行為')[2], _ranking_bonuses(question, title, '發文日期及受文者')[2])

    def test_vague_query_no_topic_bonus(self):
        self.assertFalse(_topic_token_groups('我可以幫他嗎？'))
        self.assertEqual(_ranking_bonuses('我可以幫他嗎？', '業務範圍疑義', '不得涉及醫療'), (0.0, 0.0, 0.0))

    def test_multiple_topics_not_full_bonus(self):
        topic, _, intent = _ranking_bonuses('可否換藥、移位？', '換藥疑義', '更換敷料不得涉及護理')
        self.assertEqual(topic, 0.5)
        self.assertLess(intent, 0.22)


if __name__ == '__main__':
    unittest.main()
