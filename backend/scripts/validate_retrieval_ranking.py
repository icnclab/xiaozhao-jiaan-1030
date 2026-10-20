"""Compare real ranking snapshots and verify unchanged expansion/safety gates."""
import importlib.util
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.services import retrieval, qa_graph
from app.services.qa_policy import DEFAULT_POLICY
from app.services.text import normalize

spec = importlib.util.spec_from_loader('retrieval_topic_before', loader=None)
before_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = before_module
backup = root / 'backend/app/services/retrieval.py.bak_topic_intent_20261008'
exec(compile(backup.read_text(encoding='utf-8'), str(backup), 'exec'), before_module.__dict__)
before = json.loads((root / 'docs/retrieval_ranking_before_20261008.json').read_text(encoding='utf-8'))
after = json.loads((root / 'docs/retrieval_ranking_after_20261008.json').read_text(encoding='utf-8'))
by_id = {r['chunk_id']: r for r in before['results']}
assert set(by_id) == {r['chunk_id'] for r in after['results']}
for r in after['results']:
    assert (r['coverage'], r['vector']) == (by_id[r['chunk_id']]['coverage'], by_id[r['chunk_id']]['vector'])
    assert abs(r['combined'] - r['hybrid_score'] - r['title_bonus'] - r['intent_bonus']) < 0.0002
    if 'BA13' in r['document'] or '清除糞便' in r['document']:
        assert r['intent_bonus'] == 0
target = next(r for r in after['results'] if '1090119919' in r['document'] and '一般傷口更換敷料' in normalize(r['text']))
assert target['rank'] <= 5
questions = [row['question'] for row in json.loads((root / 'docs/q1_q3_formal_snapshot.json').read_text(encoding='utf-8'))]
questions += ['我可以幫他換藥嗎？', '能不能餵食？', '抽痰是否需要資格？']
for q in questions:
    assert retrieval._expand_query(q, date(2026, 10, 8)) == before_module._expand_query(q, date(2026, 10, 8))

# Prove the legacy expansion test fails on the pre-edit backup as well.
import test_q1_q3_expansion as legacy
with patch.object(legacy, '_expand_query', before_module._expand_query):
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(legacy.ExpansionTests)
    result = unittest.TextTestRunner().run(suite)
assert len(result.failures) == 1 and not result.errors
assert 'test_formal_queries_unchanged' in result.failures[0][0].id()

# Historical assertion must use the historical gate, not today's replacement.
gate_backup = sorted((root / 'backend/app/services').glob('qa_graph.py.bak_evidence_gate_*'))[0]
gate_spec = importlib.util.spec_from_loader('qa_graph_before_evidence_gate', loader=None)
gate_before = importlib.util.module_from_spec(gate_spec)
sys.modules[gate_spec.name] = gate_before
exec(compile(gate_backup.read_text(encoding='utf-8'), str(gate_backup), 'exec'), gate_before.__dict__)
import uuid
top = retrieval.RetrievedChunk(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), target['document'], 'regulation',
                               target['locator'], '', None, None, target['text'],
                               target['coverage'], target['vector'], target['combined'], False)
with patch.object(gate_before, 'retrieve', return_value=[top]):
    outcome = gate_before.node_retrieve({'session': None, 'question_masked': after['question'],
        'org_id': uuid.uuid4(), 'facility_type': after['facility_type'], 'today': date(2026, 10, 8), 'policy': DEFAULT_POLICY})
assert outcome['outcome'] == 'escalate' and outcome['reason'] == 'no_evidence'
print('PASS: candidate set, coverage and vector unchanged; score components reconcile.')
print('PASS: target meaningful chunk rank', target['rank'], '; unrelated intent bonuses = 0.')
print('PASS: expansion unchanged; legacy failure reproduced using pre-edit backup.')
print('PASS: historical QA gate returns escalate/no_evidence; see new evidence gate tests for current behavior.')
