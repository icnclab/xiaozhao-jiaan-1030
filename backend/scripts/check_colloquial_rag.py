"""Read-only UI-history, KB and A-H diagnostics; optional real LOCAL graph."""
import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, text
from app.config import get_settings
from app.db import new_session
from app.models import QaItem, Organization
from app.services.documents import current_versions
from app.services.retrieval import retrieve, _expand_query, _topic_token_groups
from app.services.retrieval_gate import assess_evidence
from app.services.qa_policy import DEFAULT_POLICY
from app.services.qa_graph import run_graph, _needs_clarification
from app.services.text import normalize

QUESTIONS = {
    'A': '我可以幫他換藥嗎？', 'B': '照服員可以幫忙清傷口嗎？',
    'C': '這個傷口我可以自己處理嗎？', 'D': '長輩跌倒要不要回報？',
    'E': '跌倒要不要回報督導？', 'F': '家屬叫我做服務計畫外的事情，可以嗎？',
    'G': '這個可以嗎？', 'H': '可以提供火星基地量子護盾校準服務嗎？',
}
parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--flow', action='store_true')
args = parser.parse_args()
settings = get_settings()
if args.flow:
    url = urlsplit(settings.ollama_base_url)
    assert settings.llm_provider == 'ollama' and (url.scheme, url.hostname, url.port) == ('http', '127.0.0.1', 11434), 'Only verified local Ollama permitted'
clean = lambda q: normalize(q).replace('?', '').replace('？', '').strip()
report = {'date': '2026-10-08', 'questions': {}, 'ui_history': [], 'kb_scope_candidates': []}

def save():
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

with new_session() as session:
    session.execute(text('SET TRANSACTION READ ONLY'))
    history = session.scalars(select(QaItem).where(
        QaItem.question_masked.in_([q for q in QUESTIONS.values()] + [q.rstrip('？') for q in QUESTIONS.values()])
    ).order_by(QaItem.created_at.desc()).limit(32)).all()
    for qa in history:
        org = session.get(Organization, qa.org_id)
        item = {'id': str(qa.id), 'created_at': str(qa.created_at), 'org_code': org.code,
                'question': qa.question_masked, 'outcome': qa.outcome, 'reason': qa.escalation_reason,
                'policy': qa.qa_policy_version, 'checks': qa.checks}
        report['ui_history'].append(item)
        print('UI', item['created_at'], item['question'], item['outcome'], item['reason'], item['policy'], flush=True)
        print('UI retrieval', json.dumps(qa.checks.get('retrieval', []), ensure_ascii=False), flush=True)
    org = session.get(Organization, history[0].org_id) if history else session.scalar(select(Organization).where(Organization.code == 'HAPPY'))
    report['org'] = {'code': org.code, 'facility_type': org.facility_type}
    versions = current_versions(session, org.id, org.facility_type, date(2026, 10, 8))
    rows = session.execute(text('''SELECT c.id, c.text, c.locator, d.title FROM chunks c
        JOIN document_versions dv ON dv.id=c.version_id JOIN documents d ON d.id=dv.document_id
        WHERE c.version_id=ANY(:versions) AND
        (c.text ~ '服務計畫|計畫外|計劃外|臨時要求|服務範圍|工作範圍|額外需求|服務契約|家屬.{0,15}要求')'''), {'versions': versions}).all()
    for row in rows:
        report['kb_scope_candidates'].append({'chunk_id': str(row.id), 'title': row.title, 'locator': row.locator, 'text': row.text})
    print('KB scope candidates', len(rows), flush=True)
    for row in rows[:8]:
        print('KB', row.title, row.locator, row.text[:600], flush=True)
    for key, q in QUESTIONS.items():
        results = retrieve(session, q, org.id, org.facility_type, date(2026, 10, 8))
        item = {'question': q, 'expanded': _expand_query(q, date(2026, 10, 8)),
                'topic_groups': [[sorted(v) for v in g] for g in _topic_token_groups(q)],
                'clarify': _needs_clarification(q), 'top5': []}
        for rank, c in enumerate(results[:5], 1):
            item['top5'].append({'rank': rank, **asdict(c), 'gate': assess_evidence(q, c, DEFAULT_POLICY).audit()})
        item['admitted'] = [{'rank': rank, 'title': c.title, 'locator': c.locator,
                             'gate': assess_evidence(q, c, DEFAULT_POLICY).audit()}
                            for rank, c in enumerate(results, 1) if assess_evidence(q, c, DEFAULT_POLICY).admitted]
        if args.flow:
            final = run_graph({'session': session, 'org_id': org.id, 'facility_type': org.facility_type,
                               'today': date(2026, 10, 8), 'question_raw': q})
            item['flow'] = {'outcome': final.get('outcome'), 'reason': final.get('reason'),
                'checks': final.get('checks'), 'evidence': [asdict(e) for e in final.get('evidence', [])],
                'candidate': asdict(final['candidate']) if final.get('candidate') else None,
                'claims': final.get('claims'), 'timings_ms': final.get('timings_ms')}
        report['questions'][key] = item
        print(key, q, 'clarify', item['clarify'], 'admitted', [(r['rank'], r['title'], r['locator']) for r in item['admitted'][:5]],
              'flow', item.get('flow', {}).get('outcome'), item.get('flow', {}).get('reason'), flush=True)
        for c in item['top5']:
            print('TOP', c['rank'], c['combined'], c['coverage'], c['vector'], c['title'], c['locator'], c['gate']['reason'],
                  c['gate']['title_topic'], c['gate']['body_topic'], c['gate']['rule_topic'], flush=True)
        save()
