"""Provider regression tests with mock HTTP, without a database."""
import json
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.providers.llm import ANSWER_SCHEMA, SYSTEM_PROMPT, EvidenceItem, OllamaLlm, _ollama_client


class ProviderTests(unittest.TestCase):
    def call(self, content):
        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={
                'message': {'content': content}, 'load_duration': 100,
                'prompt_eval_count': 123, 'eval_count': 25,
            })

        evidence = [EvidenceItem('E1', 'chunk', 'Title', '第 12 條', 'v1', '2026-10-06', '原文')]
        with httpx.Client(transport=httpx.MockTransport(handler), base_url='http://ollama') as client:
            with patch('app.providers.llm._ollama_client', return_value=client):
                answer = OllamaLlm('http://ollama', 'gemma4:e4b', 60).answer('期限？', evidence)
        self.assertEqual(requests[0]['format'], ANSWER_SCHEMA)
        self.assertEqual(requests[0]['options'], dict(temperature=0, num_ctx=6144, num_predict=400))
        self.assertFalse(requests[0]['think'])
        self.assertIn('原文', requests[0]['messages'][1]['content'])
        return answer

    def test_citations_and_metrics(self):
        answer = self.call(json.dumps(dict(direct_answer={'text': '', 'citations': []},
                            claims=[{'text': '原文', 'citations': ['E1']}],
                            needs_human=False, conflict=False, reason='')))
        self.assertEqual(answer.claims, [{'text': '原文', 'citation_refs': ['E1']}])
        self.assertEqual(answer.metrics['eval_count'], 25)

    def test_invalid_json_still_rejected(self):
        answer = self.call('truncated {')
        self.assertFalse(answer.raw_ok)
        self.assertTrue(answer.needs_human)

    def test_non_object_still_rejected(self):
        self.assertFalse(self.call('[]').raw_ok)

    def test_client_reused_across_provider_instances(self):
        with patch('app.providers.llm.httpx.Client') as constructor:
            first = _ollama_client('http://speed-test', 13)
            self.assertIs(first, _ollama_client('http://speed-test', 13))
            self.assertEqual(constructor.call_count, 1)

    def test_answer_rules_and_schema_unchanged(self):
        root = Path(__file__).resolve().parents[2]
        backup = sorted((root / 'backend/app/providers').glob('llm.py.bak_*_speed'))[-1]
        spec = importlib.util.spec_from_loader('llm_before_speed', loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        exec(compile(backup.read_text(encoding='utf-8'), str(backup), 'exec'), module.__dict__)
        self.assertEqual(SYSTEM_PROMPT, module.SYSTEM_PROMPT)
        self.assertEqual(ANSWER_SCHEMA, module.ANSWER_SCHEMA)


if __name__ == '__main__':
    unittest.main()
