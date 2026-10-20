"""Read-only full-graph benchmark using the frozen 25-question snapshot and Q1/Q3."""
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import text
from app.db import new_session
from app.services.qa_graph import run_graph

ROOT = Path(__file__).resolve().parents[2]
reference = json.loads((ROOT / 'docs/q1_q3_after.json').read_text(encoding='utf-8'))
mode = sys.argv[1]
post = httpx.post
metrics = {}


def measured_post(*args, **kwargs):
    response = post(*args, **kwargs)
    if args and str(args[0]).endswith('/api/chat'):
        payload = response.json()
        metrics.update({k: payload.get(k) for k in ('load_duration', 'prompt_eval_duration',
                       'eval_duration', 'prompt_eval_count', 'eval_count', 'total_duration')})
    return response


httpx.post = measured_post
session = new_session()
session.execute(text('SET TRANSACTION READ ONLY'))
org = session.execute(text("SELECT id, facility_type FROM organizations WHERE code='HAPPY'")).one()
results = []
for expected in reference:
    metrics.clear()
    start = time.perf_counter()
    state = run_graph(dict(session=session, org_id=org.id, facility_type=org.facility_type,
                           today=date(2026, 10, 6), question_raw=expected['question']))
    wall = round((time.perf_counter() - start) * 1000)
    evidence = state.get('evidence_map', {})
    claims = state.get('claims', [])
    cited = {(evidence[ref].title, evidence[ref].version_label) for c in claims for ref in c['refs']}
    previous = {(expected['evidence'][ref]['title'], expected['evidence'][ref]['version'])
                for c in expected['claims'] for ref in c['refs']}
    row = dict(id=expected['id'], question=expected['question'], outcome=state['outcome'],
               reason=state.get('reason'), claims=claims, cited=sorted(cited),
               outcome_match=state['outcome'] == expected['outcome'],
               citation_match=cited == previous, wall_ms=wall,
               timings=state['timings_ms'], ollama=state.get('checks', {}).get('llm_metrics') or dict(metrics),
               checks=state.get('checks'),
               evidence={ref: dict(title=c.title, version=c.version_label, locator=c.locator, text=c.text)
                         for ref, c in evidence.items()})
    results.append(row)
    print(row['id'], row['outcome'], wall, 'ms', 'outcome', row['outcome_match'],
          'citations', row['citation_match'], flush=True)
session.rollback()
session.close()
times = [r['wall_ms'] for r in results if r['outcome'] == 'answer']
summary = dict(n=len(results), outcome_matches=sum(r['outcome_match'] for r in results),
               citation_matches=sum(r['citation_match'] for r in results),
               answer_median_ms=statistics.median(times), answer_mean_ms=statistics.mean(times),
               answer_max_ms=max(times))
(ROOT / f'docs/answer_speed_{mode}.json').write_text(json.dumps(dict(summary=summary, results=results),
                                                               ensure_ascii=False, indent=2), encoding='utf-8')
print(summary)
