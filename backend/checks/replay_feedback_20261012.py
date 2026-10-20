"""Freeze and replay the 14 new feedback cases using a read-only transaction."""
import sys, json
from pathlib import Path
from datetime import date, datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, text
from app.db import new_session
from app.models import Organization
from app.quality_models import QualityFeedback
from app.services.qa_graph import run_graph
from app.services.qa_policy import DEFAULT_POLICY
from checks.run_answer_quality_v1 import render

DEST = Path(__file__).resolve().parents[2] / 'quality_tests/systematic_20261012'

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    frozen = DEST / 'feedback_14.json'
    with new_session() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        if not frozen.exists():
            records = db.scalars(select(QualityFeedback).where(
                QualityFeedback.created_at >= datetime.fromisoformat('2026-10-12T00:00:00+08:00'),
                QualityFeedback.created_at < datetime.fromisoformat('2026-10-13T00:00:00+08:00')).order_by(QualityFeedback.created_at)).all()
            assert len(records) == 14, f'Expected 14 feedback records, got {len(records)}'
            cases = [dict(id=str(r.id), org_id=str(r.org_id), question=r.qa_snapshot['question'],
                          expected=r.submission) for r in records]
            frozen.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding='utf-8')
        cases = json.loads(frozen.read_text(encoding='utf-8'))
        rows = []
        for case in cases:
            import uuid
            org = db.get(Organization, uuid.UUID(case['org_id']))
            state = run_graph(dict(question_raw=case['question'], session=db, org_id=org.id,
                                   facility_type=org.facility_type, today=date(2026,10,12)))
            actual = render(state)
            expected = case['expected']
            failures = []
            target = 'risk_block' if expected['expected_behavior'] == 'risk_block' else 'answer'
            behavior = 'risk_block' if actual['risk_result'] else actual['outcome']
            if behavior != target: failures.append('behavior')
            risk = expected['correct_source_page_or_section'].replace(' ', '_')
            if target == 'risk_block' and risk not in actual['risk_result']: failures.append('risk_family')
            if target == 'answer':
                source = ''.join(r['text'] for r in actual['source'])
                if not actual['source'] or 'BA16' not in source: failures.append('source')
                from app.services.query_understanding import purchasing_rule_intent
                field = purchasing_rule_intent(case['question'])
                required = {'medicine': ['藥品'], 'items': ['生活用品'], 'subsidized_items': ['補助品'],
                            'organize': ['歸位'], 'recipient': ['自行負擔'], 'distance': ['自行負擔']}.get(field, [])
                for term in required:
                    if term not in actual['answer']: failures.append('missing:'+term)
                if '藥' in case['question'] and '用藥安全提醒' not in actual['answer']: failures.append('medication_notice')
                if expected['error_type'] == 'verbose_answer':
                    for term in ['公里', '百分之五十', '購物清單', '歸位']:
                        if term in actual['answer']: failures.append('unrelated:'+term)
            rows.append(dict(**case, actual=actual, passed=not failures, failures=failures))
            print(case['id'][:8], behavior, failures, flush=True)
        db.rollback()
    report = dict(policy=DEFAULT_POLICY.version, read_only=True, passed=sum(r['passed'] for r in rows),
                  total=len(rows), results=rows)
    (DEST/'feedback_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(report['passed'], '/', report['total'])

if __name__ == '__main__': main()
