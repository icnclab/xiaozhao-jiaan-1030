"""Read-only boundary and 25-question regression with frozen expected results."""
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db import new_session
from app.services.qa_graph import run_graph

ROOT = Path(__file__).resolve().parents[2]
mode = sys.argv[1]
reference = json.loads((ROOT / 'docs/answer_speed_final.json').read_text(encoding='utf-8'))['results']
questions = [
    dict(id='fine', question='行政聯繫會議缺席一次要罰多少錢', outcome='escalate'),
    dict(id='frequency', question='行政聯繫會議多久至少要開一次', outcome='answer'),
    dict(id='supervision_frequency', question='督導制度多久至少要開一次聯繫會議', outcome='answer'),
    dict(id='fine_variant', question='沒有參加行政聯繫會議，罰款金額是多少？', outcome='escalate'),
    dict(id='deduction_variant', question='行政聯繫會議未出席一次要扣薪多少元？', outcome='escalate'),
]
if mode != 'before':
    questions += reference
else:
    import app.services.qa_graph as graph_module
    import app.services.retrieval as retrieval_module
    for module, name in ((retrieval_module, 'retrieval.py'), (graph_module, 'qa_graph.py')):
        backup = sorted((ROOT / 'backend/app/services').glob(name + '.bak_*_sufficiency'))[-1]
        exec(compile(backup.read_text(encoding='utf-8'), str(backup), 'exec'), module.__dict__)
    run_graph = graph_module.run_graph
session = new_session()
session.execute(text('SET TRANSACTION READ ONLY'))
org = session.execute(text("SELECT id,facility_type FROM organizations WHERE code='HAPPY'")).one()
results = []
for expected in questions:
    start = time.perf_counter()
    state = run_graph(dict(session=session, org_id=org.id, facility_type=org.facility_type,
                           today=date(2026, 10, 6), question_raw=expected['question']))
    wall = round((time.perf_counter() - start) * 1000)
    claims = state.get('claims', [])
    evidence = state.get('evidence_map', {})
    cited = sorted({(evidence[ref].title, evidence[ref].version_label) for c in claims for ref in c['refs']})
    passed = state['outcome'] == expected['outcome']
    if 'cited' in expected:
        passed = passed and cited == [tuple(c) for c in expected['cited']]
    answer = ' '.join(c['text'] for c in claims)
    if expected['id'] in ('frequency', 'supervision_frequency', 'Q3', 'Q3_variant'):
        passed = passed and any(n in answer for n in ('3 個月', '3個月', '三個月'))
        passed = passed and '行政聯繫會議' in answer
        passed = passed and bool(cited) and all('115年度' in title for title, _ in cited)
    if expected['id'] in ('Q1', 'Q1_variant'):
        passed = passed and '有效期限屆至前六個月內' in answer
        passed = passed and any(evidence[ref].locator == '第 12 條' for c in claims for ref in c['refs'])
    row = dict(id=expected['id'], question=expected['question'], passed=passed, outcome=state['outcome'],
               reason=state.get('reason'), answer=answer, claims=claims, cited=cited,
               wall_ms=wall, timings=state['timings_ms'], checks=state.get('checks'),
               evidence={ref: dict(title=c.title, locator=c.locator, version=c.version_label, text=c.text)
                         for ref, c in evidence.items()})
    if 'claims' in expected:
        row['claims_unchanged'] = claims == expected['claims']
    results.append(row)
    print(expected['id'], 'PASS' if passed else 'FAIL', row['outcome'], row['reason'], wall, flush=True)
session.rollback()
session.close()
answered = [r['wall_ms'] for r in results if r['outcome']=='answer']
summary = dict(passed=sum(r['passed'] for r in results), n=len(results),
               answer_median_ms=statistics.median(answered) if answered else None)
(ROOT / f'docs/evidence_sufficiency_{mode}.json').write_text(json.dumps(dict(summary=summary, results=results),
                                                                    ensure_ascii=False, indent=2), encoding='utf-8')
print(summary)
sys.exit(0 if all(r['passed'] for r in results) else 1)
