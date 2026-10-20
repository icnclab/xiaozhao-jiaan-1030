"""Export existing QA history for a manual-lookup experiment; never runs QA."""
import hashlib
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db import new_session

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/manual_lookup_experiment'
OUT.mkdir(parents=True, exist_ok=True)
protected = [ROOT / p for p in ('backend/app/services/retrieval.py', 'backend/app/services/qa_graph.py',
                              'backend/app/services/qa_policy.py', 'backend/app/providers/llm.py')]
hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
formal = json.loads((ROOT / 'docs/q1_q3_formal_snapshot.json').read_text(encoding='utf-8'))
# Mix subjects and source types; do not select repeated paraphrases or refusal questions.
selection = [(19, '法規'), (17, '函釋'), (10, '工作手冊'), (7, '操作指引'), (9, '評鑑基準'),
             (20, '法規'), (14, '函釋'), (8, '操作指引'), (18, '法規'), (15, '函釋')]
session = new_session()
session.execute(text('SET TRANSACTION READ ONLY'))
records = []
for number, (index, kind) in enumerate(selection, 1):
    question = formal[index-1]['question']
    assert formal[index-1]['outcome'] == 'answered'
    candidates = session.execute(text('''
        SELECT id, created_at, outcome, answer_text, timings_ms, qa_policy_version, llm_model
        FROM qa_items WHERE question_masked=:q AND outcome='answered'
        ORDER BY created_at DESC, id DESC
    '''), {'q': question}).mappings().all()
    for item in candidates:
        citations = session.execute(text('''
            SELECT d.title, c.locator, c.text, dv.version_label, dv.status
            FROM citations ci JOIN chunks c ON c.id=ci.chunk_id
            JOIN document_versions dv ON dv.id=ci.version_id
            JOIN documents d ON d.id=dv.document_id
            WHERE ci.qa_item_id=:id ORDER BY ci.rank
        '''), {'id': item['id']}).mappings().all()
        ms = item['timings_ms'].get('graph_total')
        if (isinstance(ms, (int, float)) and ms > 0 and citations
            and all(c['version_label']=='Phase1_MD_2026-10-06_v1' and c['status']=='published' for c in citations)):
            break
    else:
        raise RuntimeError(f'No eligible historical QA timing: {question}')
    sources = []
    for c in citations:
        label = f"{c['title']}（{c['locator']}）"
        if label not in sources:
            sources.append(label)
    records.append(dict(id=f'T{number:02d}', formal_index=index, category=kind, question=question,
                        correct_source='；'.join(sources), system_seconds=ms / 1000,
                        qa_id=str(item['id']), qa_created_at=item['created_at'].astimezone(ZoneInfo('Asia/Taipei')).isoformat(),
                        qa_policy_version=item['qa_policy_version'], llm_model=item['llm_model'],
                        timings_ms=item['timings_ms'], answer=item['answer_text'],
                        citations=[dict(c) for c in citations]))
session.rollback()
session.close()
assert hashes == {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
(OUT / 'qa_history_sources.json').write_text(json.dumps(dict(
    selection_method='Latest answered QA with positive graph_total and published Phase1 MD citations; not fastest record.',
    timing_scope='graph_total / 1000; excludes network, UI, QA persistence and user reading time.',
    protected_file_hashes=hashes, records=records), ensure_ascii=False, indent=2), encoding='utf-8')
print(*[(r['id'], r['category'], r['system_seconds'], r['correct_source']) for r in records], sep='\n')
