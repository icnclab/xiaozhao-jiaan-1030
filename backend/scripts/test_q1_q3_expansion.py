"""Targeted query normalization regression tests (no DB mutation)."""
import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.retrieval import _expand_query

TODAY = date(2026, 10, 6)


class ExpansionTests(unittest.TestCase):
    def test_certificate_deadline(self):
        result = _expand_query('長照人員的認證證明快到期了，最晚要在什麼時候前申請展延？', TODAY)
        self.assertIn('有效期限屆至', result)
        self.assertIn('申請更新', result)
        self.assertNotIn('申請展延', result)

    def test_meeting_frequency(self):
        result = _expand_query('居家式機構的督導制度，聯繫會議至少多久要開一次？', TODAY)
        self.assertIn('行政聯繫會議', result)
        self.assertIn('定期召開', result)
        self.assertNotIn('3', result)  # No answer injected into retrieval.

    def test_other_subjects_unchanged(self):
        for question in ('長照機構設立許可快到期了，何時申請展延？',
                         '長照人員居留證到期要申請展延嗎？',
                         '居家式機構個別督導會議多久一次？',
                         '居家式機構的督導制度，行政聯繫會議缺席一次要罰多少錢？',
                         '長照人員認證證明過期兩年，申請更新需要哪些文件？'):
            self.assertEqual(_expand_query(question, TODAY), question)

    def test_conditions_preserved(self):
        result = _expand_query('長照人員認證證明到期，未完成繼續教育可以申請更新嗎？', TODAY)
        self.assertIn('未完成繼續教育', result)
        self.assertIn('可以申請更新嗎', result)

    def test_formal_queries_unchanged(self):
        import json
        root = Path(__file__).resolve().parents[2]
        backup = sorted((root / 'backend/app/services').glob('retrieval.py.bak_*_q1_q3'))[-1]
        spec = importlib.util.spec_from_loader('retrieval_before', loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        exec(compile(backup.read_text(encoding='utf-8'), str(backup), 'exec'), module.__dict__)
        for row in json.loads((root / 'docs/q1_q3_formal_snapshot.json').read_text(encoding='utf-8')):
            self.assertEqual(_expand_query(row['question'], TODAY), module._expand_query(row['question'], TODAY))


if __name__ == '__main__':
    unittest.main()
