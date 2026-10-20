"""Read-only regression check against published documents; never seeds or writes DB."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db import new_session
from app.services.qa_graph import run_graph
from app.services.retrieval import retrieve

ROOT = Path(__file__).resolve().parents[2]
session = new_session()
session.execute(text("SET TRANSACTION READ ONLY"))
org = session.execute(text("SELECT id, facility_type FROM organizations WHERE code='HAPPY'")).one()
questions = [
    ('Q1', '長照人員的認證證明快到期了，最晚要在什麼時候前申請展延？'),
    ('Q3', '居家式機構的督導制度，聯繫會議至少多久要開一次？'),
]
mode = sys.argv[1]
if mode in ('baseline', 'boundary_before'):
    import app.services.retrieval as retrieval_module
    backup = sorted((ROOT / 'backend/app/services').glob('retrieval.py.bak_*_q1_q3'))[-1]
    exec(compile(backup.read_text(encoding='utf-8'), str(backup), 'exec'), retrieval_module.__dict__)
    retrieve = retrieval_module.retrieve
if mode == 'baseline':
    rows = session.execute(text('SELECT question_masked, outcome FROM qa_items ORDER BY created_at DESC LIMIT 41')).all()
    # The last contiguous formal run precedes the subsequent exploratory questions.
    formal = [dict(question=r.question_masked, outcome=r.outcome) for r in rows[16:41]]
    (ROOT / 'docs/q1_q3_formal_snapshot.json').write_text(json.dumps(formal, ensure_ascii=False, indent=2), encoding='utf-8')
elif mode in ('boundary', 'boundary_before'):
    formal = []
    questions = [
        ('refusal_certificate', '長照人員認證證明快到期了，申請更新是否保證一天內核准？'),
        ('refusal_meeting', '居家式機構的督導制度，行政聯繫會議缺席一次要罰多少錢？'),
    ]
else:
    formal = json.loads((ROOT / 'docs/q1_q3_formal_snapshot.json').read_text(encoding='utf-8'))
    questions += [('Q1_variant', '長照人員認證證明即將到期，何時申請更新？'),
                  ('Q3_variant', '居家式機構督導制度的行政聯繫會議多久召開一次？')]
    questions += [(f'formal_{i+1}', r['question']) for i, r in enumerate(formal)]
results = []
for key, question in questions:
    initial = dict(session=session, org_id=org.id, facility_type=org.facility_type,
                   today=date(2026, 10, 6), question_raw=question)
    if mode == 'baseline':
        chunks = retrieve(session, question, org.id, org.facility_type, initial['today'])
        row = dict(id=key, question=question, top=[dict(title=c.title, locator=c.locator,
                   coverage=c.coverage, combined=c.combined) for c in chunks[:3]])
    else:
        state = run_graph(initial)
        row = dict(id=key, question=question, outcome=state['outcome'], reason=state.get('reason'),
                   claims=state.get('claims', []), checks=state.get('checks'), timings=state.get('timings_ms'),
                   evidence={ref: dict(title=c.title, locator=c.locator, version=c.version_label, text=c.text)
                             for ref, c in state.get('evidence_map', {}).items()})
        if key.startswith('formal_'):
            expected = formal[int(key.split('_')[1])-1]['outcome']
            row['expected_outcome'] = expected
            row['outcome_match'] = state['outcome'] == ('answer' if expected == 'answered' else 'escalate')
    results.append(row)
    print(key, row.get('outcome', row.get('top')), row.get('reason'), flush=True)
(ROOT / f'docs/q1_q3_{mode}.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
session.rollback()
session.close()
