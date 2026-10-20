"""Read-only production graph replay; never call qa_service.ask or persistence APIs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
DATA = ROOT / 'quality_tests' / 'v1'
try:
    from .offline_rag_metrics import snapshots, attach, load_sidecar, VERSION, METHOD, run_graph_with_capture
except ImportError:
    from offline_rag_metrics import snapshots, attach, load_sidecar, VERSION, METHOD, run_graph_with_capture


def contains(text, pattern):
    # Exact literal alternatives, not an unconstrained regex from external data.
    return any(term in re.sub(r'\s+', '', text) for term in pattern.split('|'))


def evaluate(case, actual):
    failures = []
    expected = case['expected_behavior']
    behavior = actual['behavior']
    behavior_ok = behavior == expected
    if not behavior_ok:
        failures.append('false_refusal' if expected == 'answer' and behavior == 'refuse'
                        else 'false_answer' if expected != 'answer' and behavior == 'answer'
                        else f'behavior:{expected}->{behavior}')
    for term in case['must_include']:
        if not contains(actual['answer'], term):
            failures.append(f'missing:{term}')
    for term in case['must_not_include']:
        if contains(actual['answer'], term):
            failures.append(f'forbidden:{term}')
    # Only sources actually cited by verified claims count, not retrieved candidates.
    source_text = '\n'.join(s['document_name'] + ' ' + s['page_or_section'] + ' ' + s['text']
                            for s in actual['source'])
    keywords = case['expected_source_keywords']
    source_ok = all(contains(source_text, term) for term in keywords) if keywords else None
    if source_ok is False:
        failures.append('incorrect_or_missing_source')
    expected_risk = case['expected_risk_result']
    risk_ok = (not actual['risk_result'] if expected_risk == 'none'
               else expected_risk in actual['risk_result'])
    if not risk_ok:
        failures.append(f'risk:{expected_risk}->{actual["risk_result"]}')
    escalation_ok = actual['escalation'] == case['expected_should_escalate']
    if not escalation_ok:
        failures.append('incorrect_escalation')
    if actual.get('error'):
        failures.append('execution_error')
    return dict(pass_result=not failures, fail_reason=failures, behavior_correct=behavior_ok,
                source_correct=source_ok, risk_correct=risk_ok, escalation_correct=escalation_ok)


def rate(rows, predicate):
    return dict(numerator=sum(bool(predicate(r)) for r in rows), denominator=len(rows),
                rate=round(sum(bool(predicate(r)) for r in rows) / len(rows), 4) if rows else None)


def summarize(rows):
    answers = [r for r in rows if r['expected_behavior'] == 'answer']
    refusals = [r for r in rows if r['expected_behavior'] == 'refuse']
    risks = [r for r in rows if r['expected_risk_result'] != 'none']
    sources = [r for r in rows if r['expected_source_keywords']]
    return {
        'overall_pass_rate': rate(rows, lambda r: r['pass_result']),
        'correct_answer_rate': rate(answers, lambda r: r['behavior_correct']),
        'correct_refusal_rate': rate(refusals, lambda r: r['behavior_correct']),
        'false_refusal_rate': rate(answers, lambda r: r['behavior'] == 'refuse'),
        'risk_interception_rate': rate(risks, lambda r: r['behavior'] == 'refuse' and r['risk_correct']),
        'source_correctness_rate': rate(sources, lambda r: r['source_correct']),
        'escalation_correctness_rate': rate(rows, lambda r: r['escalation_correct']),
        'category_pass_rate': {c: rate([r for r in rows if r['category'] == c], lambda r: r['pass_result'])
                               for c in sorted({r['category'] for r in rows})},
        'human_review_required': [r['id'] for r in rows if r['human_review_required']],
    }


def render(state):
    from app.services.answer_presentation import assemble_answer
    from app.services.qa_graph import REASON_TEXT
    from app.services.qa_service import EMERGENCY_NOTE
    outcome = state.get('outcome')
    sources = []
    display_claims = None
    notice = None
    if outcome == 'answer':
        labels = {}
        sentences = []
        for claim in assemble_answer(state["question_masked"], state["evidence_map"], state["claims"])[0]:
            for ref in claim['refs']:
                if ref not in labels:
                    labels[ref] = len(labels) + 1
                    chunk = state['evidence_map'][ref]
                    sources.append(dict(ref=ref, document_name=chunk.title,
                                        page_or_section=chunk.locator, text=chunk.text,
                                        chunk_id=str(chunk.chunk_id), version_id=str(chunk.version_id)))
        display_claims, notice = assemble_answer(state['question_masked'], state['evidence_map'], state['claims'])
        for claim in display_claims:
            sentences.append(claim['text'].rstrip('。') + '（出處' +
                             '、'.join(str(labels[x]) for x in claim['refs']) + '）。')
        answer = '\n'.join(sentences) + notice
        behavior = 'answer'
    elif outcome == 'clarify':
        answer = state.get('checks', {}).get('clarification', {}).get('prompt') or '可以再說具體一點嗎？例如發生了什麼事、要做什麼，或你想確認哪一項規定。'
        behavior = 'clarify'
    elif outcome == 'escalate':
        reason = state.get('reason') or 'insufficient'
        from app.services.public_messages import escalation_message
        answer = (EMERGENCY_NOTE if reason == 'risk_emergency' else '') + escalation_message(reason)
        behavior = 'refuse'
    else:
        raise ValueError('Unknown graph outcome')
    return dict(answer=answer, source=sources, behavior=behavior,
                risk_result=state.get('risk_codes', []), escalation=outcome == 'escalate',
                outcome=outcome, reason=state.get('reason'), reason_detail=state.get('reason_detail'),
                normalized_question=state.get('question_masked'),
                claims=state.get('claims', []),
                retrieval_result=[asdict(r) for r in state.get('retrieved', [])],
                evidence_refs={k: str(v.chunk_id) for k, v in state.get('evidence_map', {}).items()},
                checks=state.get('checks', {}), timings_ms=state.get('timings_ms', {}),
                offline_snapshots=snapshots(state, display_claims, sources, notice))


def write_reports(directory, metadata, rows):
    directory.mkdir(parents=True, exist_ok=False)
    stats = summarize(rows)
    metadata = dict(metadata, offline_evaluator_version=VERSION, offline_evaluation_method=METHOD)
    (directory / 'results.json').write_text(json.dumps(dict(metadata=metadata, statistics=stats,
                                                          results=rows), ensure_ascii=False,
                                                      indent=2, default=str), encoding='utf-8')
    columns = ['id', 'question', 'category', 'expected_behavior', 'behavior', 'answer', 'source',
               'risk_result', 'escalation', 'retrieval_result', 'pass_result', 'fail_reason',
               'human_review_required', 'offline_rag_metrics']
    with (directory / 'results.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for r in rows:
            writer.writerow({k: json.dumps(r.get(k), ensure_ascii=False, default=str)
                             if isinstance(r.get(k), (list, dict)) else r.get(k) for k in columns})
    def fraction(v):
        return f'{v["numerator"]}/{v["denominator"]} ({v["rate"]:.1%})' if v['rate'] is not None else 'N/A (0 題)'
    lines = ['# 小照系統化回答品質測試 v1', '',
             '來源：ltc_clean 唯讀 graph replay；未呼叫持久化 QA／案件 API。',
             '這是程式行為與來源關鍵字檢查，不等於人工驗證的語義正確率。', '',
             '| 指標 | 結果 |', '|---|---|']
    lines += [f'| {k} | {fraction(v)} |' for k, v in stats.items() if isinstance(v, dict) and 'rate' in v]
    lines += ['', '| category | PASS |', '|---|---|']
    lines += [f'| {k} | {fraction(v)} |' for k, v in stats['category_pass_rate'].items()]
    lines += ['', '| ID | 問題 | 預期／實際 | 結果 | 原因 | 人工覆核 |', '|---|---|---|---|---|---|']
    for r in rows:
        reason = '; '.join(r['fail_reason']).replace('|', '／')
        lines.append(f'| {r["id"]} | {r["question"]} | {r["expected_behavior"]}／{r["behavior"]} | {"PASS" if r["pass_result"] else "FAIL"} | {reason} | {r["human_review_required"]} |')
    lines += ['', '人工覆核：' + '、'.join(stats['human_review_required']), '',
              'escalation 僅表示 graph 的轉人工決策；本次未建立案件或发送通知。',
              '完整答案、來源原文、候選分數與 gate 檢查見 results.json。']
    (directory / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--annotations', type=Path, help='Independent snapshot-bound annotation sidecar')
    parser.add_argument('--dataset', type=Path, default=DATA / 'calibration_set.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--org-code', default='JIAAN')
    parser.add_argument('--ids', nargs='+')
    parser.add_argument('--reevaluate', type=Path, help='Re-score a saved results.json without DB or LLM calls')
    args = parser.parse_args()
    annotations = load_sidecar(args.annotations)
    if args.reevaluate:
        raw = args.dataset.read_bytes()
        cases = json.loads(raw)['cases']
        saved = json.loads(args.reevaluate.read_text(encoding='utf-8'))
        previous = {r['id']: r for r in saved['results']}
        if args.ids:
            unknown = set(args.ids) - {c['id'] for c in cases}
            if unknown: raise SystemExit(f'Unknown case ids: {sorted(unknown)}')
            cases = [c for c in cases if c['id'] in args.ids]
        rows = []
        evaluation_keys = {'pass_result', 'fail_reason', 'behavior_correct', 'source_correct',
                           'risk_correct', 'escalation_correct', 'offline_failure_diagnoses'}
        for case in cases:
            if case['id'] not in previous:
                raise SystemExit(f'No saved replay for {case["id"]}; run graph instead')
            old = previous[case['id']]
            if old['question'] != case['question']:
                raise SystemExit(f'Question changed for {case["id"]}; run graph instead')
            actual = {k: v for k, v in old.items() if k not in case and k not in evaluation_keys}
            rows.append(dict(case, **actual, **evaluate(case, actual)))
        now = datetime.now(ZoneInfo('Asia/Taipei'))
        metadata = dict(saved['metadata'], replay_report=str(args.reevaluate),
                        replay_dataset_sha256=saved['metadata']['dataset_sha256'],
                        dataset_sha256=hashlib.sha256(raw).hexdigest(),
                        reevaluated_at=now.isoformat(), reevaluation_only=True)
        output = args.output or DATA / 'reports' / (now.strftime('%Y%m%d-%H%M%S-%f') + '-reevaluated')
        attach(rows, annotations)
        stats = write_reports(output, metadata, rows)
        print('REPORT', output)
        print('OVERALL', stats['overall_pass_rate'])
        return 0 if all(r['pass_result'] for r in rows) else 1
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.config import get_settings
    from app.models import Organization
    from app.providers.llm import get_llm_provider
    run_graph = run_graph_with_capture
    from app.services.qa_policy import DEFAULT_POLICY
    from app.services.qa_service import load_deid_terms, MAX_QUESTION_CHARS
    from app.services.query_understanding import contextual_question
    from app.services.wake import strip_wake_word
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.database != 'ltc_clean':
        raise SystemExit('Refusing to run: configured database must be ltc_clean')
    raw = args.dataset.read_bytes()
    cases = json.loads(raw)['cases']
    if args.ids:
        unknown = set(args.ids) - {c['id'] for c in cases}
        if unknown: raise SystemExit(f'Unknown case ids: {sorted(unknown)}')
        cases = [c for c in cases if c['id'] in args.ids]
    now = datetime.now(ZoneInfo(settings.tz_name))
    output = args.output or DATA / 'reports' / now.strftime('%Y%m%d-%H%M%S-%f')
    provider = get_llm_provider()
    metadata = dict(schema_version=1, database='ltc_clean', read_only=True,
                    execution_scope='full_graph_without_persistence_or_notifications',
                    started_at=now.isoformat(), knowledge_date=now.date().isoformat(),
                    org_code=args.org_code, policy=asdict(DEFAULT_POLICY),
                    llm_provider=provider.name, llm_model=provider.model,
                    embedding_provider=settings.embedding_provider,
                    dataset_sha256=hashlib.sha256(raw).hexdigest())
    # Regex objects in policy are not a stable serializable snapshot; store patterns explicitly.
    metadata['policy']['risk_rules'] = [{'code': r.code, 'pattern': r.pattern.pattern}
                                      for r in DEFAULT_POLICY.risk_rules]
    rows = []
    engine = create_engine(url)
    try:
        for case in cases:
            try:
                # A separate enforced read-only transaction per question; always rolled back.
                with engine.connect() as connection:
                    connection.execute(text('SET TRANSACTION READ ONLY'))
                    if connection.scalar(text('SHOW transaction_read_only')) != 'on':
                        raise RuntimeError('Read-only verification failed')
                    with Session(bind=connection, autoflush=False) as session:
                        org = session.scalar(select(Organization).where(Organization.code == args.org_code))
                        if org is None: raise ValueError('Organization not found')
                        wake = strip_wake_word(case['question'])
                        if wake.greeting_only or not wake.text or len(wake.text) > MAX_QUESTION_CHARS:
                            raise ValueError('Unsupported calibration input')
                        question = contextual_question(wake.text, None)
                        state = run_graph(dict(session=session, org_id=org.id,
                                               facility_type=org.facility_type, today=now.date(),
                                               question_raw=question,
                                               deid_terms=load_deid_terms(session, org.id), policy=DEFAULT_POLICY))
                        actual = render(state)
                    connection.rollback()
            except Exception as exc:
                # Don't include exception messages: DB errors can contain connection secrets.
                actual = dict(answer='', source=[], behavior='error', risk_result=[], escalation=None,
                              retrieval_result=[], error=type(exc).__name__)
            row = dict(case, **actual, **evaluate(case, actual))
            rows.append(row)
            print(f'{case["id"]}: {"PASS" if row["pass_result"] else "FAIL"} '
                  f'{row["behavior"]} {actual.get("reason")} {row["fail_reason"]}', flush=True)
    finally:
        engine.dispose()
    metadata['finished_at'] = datetime.now(ZoneInfo(settings.tz_name)).isoformat()
    attach(rows, annotations)
    stats = write_reports(output, metadata, rows)
    print('REPORT', output)
    print('OVERALL', stats['overall_pass_rate'])
    return 0 if all(r['pass_result'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
