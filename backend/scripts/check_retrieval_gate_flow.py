"""Read-only real graph runs, restricted to LOCAL configured LLM."""
import hashlib
import importlib.util
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
from app.models import Organization
from app.services.qa_graph import run_graph

root = Path(__file__).resolve().parents[2]
questions = ['我可以幫他換藥嗎？', '我可以幫他處理一個完全不存在於知識庫的事情嗎？',
             '長照人員的認證證明快到期了，最晚要在什麼時候前申請展延？']
settings = get_settings()
if settings.llm_provider == 'ollama':
    dest = urlsplit(settings.ollama_base_url)
    if dest.scheme != 'http' or dest.hostname != '127.0.0.1' or dest.port != 11434:
        raise SystemExit('This diagnostic only permits local Ollama at http://127.0.0.1:11434')
elif settings.llm_provider != 'extractive':
    raise SystemExit('This diagnostic requires real local Ollama or extractive provider')
report = {'date': '2026-10-08', 'org_code': 'HAPPY', 'embedding': settings.embedding_provider,
          'llm_provider': settings.llm_provider, 'llm_model': settings.llm_model, 'flows': [], 'versions': []}
with new_session() as session:
    session.execute(text('SET TRANSACTION READ ONLY'))
    org = session.scalar(select(Organization).where(Organization.code == 'HAPPY'))
    for q in questions:
        print('RUN', q, flush=True)
        final = run_graph({'session': session, 'org_id': org.id, 'facility_type': org.facility_type,
                           'today': date(2026, 10, 8), 'question_raw': q})
        flow = {'question': q, 'outcome': final.get('outcome'), 'reason': final.get('reason'),
                'reason_detail': final.get('reason_detail'), 'checks': final.get('checks'),
                'ranking': [asdict(c) for c in final.get('retrieved', [])[:15]],
                'selected_evidence': [asdict(e) for e in final.get('evidence', [])],
                'candidate': asdict(final['candidate']) if final.get('candidate') else None,
                'verified_claims': final.get('claims'), 'timings_ms': final.get('timings_ms')}
        report['flows'].append(flow)
        print('OUTCOME', flow['outcome'], flow['reason'], 'evidence', [(e['ref'], e['locator']) for e in flow['selected_evidence']], flush=True)
        (root / 'docs/retrieval_gate_flow_20261008.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    # Reruns are against today's corpus, not a reconstruction of historical DB.
    for path in sorted((root / 'backend/app/services').glob('retrieval.py.bak*')):
        if 'evidence_gate' in path.name:
            continue
        spec = importlib.util.spec_from_loader('rank_history_' + hashlib.sha256(path.name.encode()).hexdigest()[:8], loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
        rows = module.retrieve(session, questions[0], org.id, org.facility_type, date(2026, 10, 8))
        item = {'backup': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'target_ranks_today': [{'rank': i, 'combined': c.combined, 'coverage': c.coverage,
                    'vector': c.vector, 'locator': c.locator} for i, c in enumerate(rows, 1) if '1090119919' in c.title]}
        report['versions'].append(item)
        print('VERSION', item['backup'], [r['rank'] for r in item['target_ranks_today']], flush=True)
    for name in ('retrieval.py', 'qa_graph.py', 'qa_policy.py', 'retrieval_gate.py'):
        path = root / 'backend/app/services' / name
        report.setdefault('current_sha256', {})[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / 'docs/retrieval_gate_flow_20261008.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
