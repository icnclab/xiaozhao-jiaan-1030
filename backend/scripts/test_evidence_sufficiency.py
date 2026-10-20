"""Fact-availability and high-support off-target answer regression tests, no DB."""
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.providers.llm import CandidateAnswer
from app.services.evidence_sufficiency import (
    asks_penalty_amount, supported_penalty_amounts, answers_supported_penalty_amount,
)
from app.services.qa_graph import node_verify
from app.services.qa_policy import DEFAULT_POLICY

QUESTION = '行政聯繫會議缺席一次要罰多少錢'
EVIDENCE = '評鑑當日業務負責人未出席，本項逕評核為 E。行政聯繫會議至少每3個月召開。'


class SufficiencyTests(unittest.TestCase):
    def verify(self, evidence, answer):
        chunk = SimpleNamespace(title='會議規定', locator='第1條', text=evidence,
                                coverage=0.8, document_id=uuid.uuid4(), chunk_id=uuid.uuid4())
        return node_verify(dict(policy=DEFAULT_POLICY, question_masked=QUESTION,
                               evidence_map={'E1': chunk},
                               candidate=CandidateAnswer(claims=[dict(text=answer, citation_refs=['E1'])])))

    def test_multiple_money_intents(self):
        for q in (QUESTION, '未出席行政聯繫會議罰款金額是多少',
                  '行政聯繫會議未參加要扣薪幾元', '遲到扣款金額上限？'):
            self.assertTrue(asks_penalty_amount(q))

    def test_frequency_not_money(self):
        for q in ('行政聯繫會議多久至少要開一次', '督導制度多久至少要開一次聯繫會議',
                  '長照服務部分負擔比率應查哪一份附表？', '罰站幾分鐘？'):
            self.assertFalse(asks_penalty_amount(q))

    def test_grade_and_interval_not_amount(self):
        self.assertFalse(supported_penalty_amounts(QUESTION, EVIDENCE))

    def test_unrelated_money_cannot_fill_slot(self):
        self.assertFalse(supported_penalty_amounts(QUESTION, EVIDENCE + '違法停車罰款3000元。'))
        self.assertFalse(supported_penalty_amounts(QUESTION, '行政聯繫會議缺席會受處罰。申請證明費用100元。'))

    def test_supporting_amount_not_blanket_refused(self):
        evidence = '行政聯繫會議缺席一次罰款3,000元。'
        self.assertEqual(supported_penalty_amounts(QUESTION, evidence), {'3000元'})
        self.assertTrue(answers_supported_penalty_amount(QUESTION, '罰款3000元。', evidence))
        self.assertEqual(self.verify(evidence, evidence)['outcome'], 'answer')

    def test_invented_amount_rejected(self):
        self.assertFalse(answers_supported_penalty_amount(QUESTION, '罰款5000元。',
                         '行政聯繫會議缺席一次罰款3000元。'))

    def test_high_support_off_target_answer_rejected(self):
        state = self.verify(EVIDENCE, '評鑑當日業務負責人未出席，本項逕評核為 E。')
        self.assertEqual(state['outcome'], 'escalate')
        self.assertEqual(state['reason'], 'insufficient')
        self.assertGreater(state['checks']['claims'][0]['support'], DEFAULT_POLICY.min_support)

    def test_off_target_even_with_money_elsewhere_rejected(self):
        state = self.verify(EVIDENCE + '行政聯繫會議缺席一次罰款3000元。',
                            '評鑑當日業務負責人未出席，本項逕評核為 E。')
        self.assertEqual(state['outcome'], 'escalate')


if __name__ == '__main__':
    unittest.main()
