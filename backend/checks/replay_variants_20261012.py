"""Actual scoped KB graph replay for expanded purchasing questions, read only."""
import json
from datetime import date
from pathlib import Path
from sqlalchemy import select, text
from app.db import new_session
from app.models import Organization
from app.services.qa_graph import run_graph
from checks.test_systematic_improvement import PURCHASE_ROWS
from checks.run_answer_quality_v1 import render

def main():
    rows = []
    with new_session() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        org = db.scalar(select(Organization).where(Organization.code == 'JIAAN'))
        for q, field in PURCHASE_ROWS:
            state = run_graph(dict(question_raw=q, session=db, org_id=org.id,
                                   facility_type=org.facility_type, today=date(2026,10,12)))
            actual = render(state)
            required = {'items': ['生活用品'], 'distance': ['公里'], 'recipient': ['本身所需|本人所需'],
                        'subsidized_items': ['補助品'], 'errands': ['事項'], 'organize': ['歸位'],
                        'accounting': ['記帳|記賬'], 'medicine': ['藥品'], 'scope': ['代購']}
            failures = []
            if actual['outcome'] != 'answer': failures.append('behavior')
            for term in required[field]:
                if not any(t in actual['answer'] for t in term.split('|')): failures.append('missing:'+term)
            if not actual['source']: failures.append('source')
            rows.append(dict(question=q, field=field, passed=not failures, failures=failures, actual=actual))
            print(field, q, failures, flush=True)
        db.rollback()
    dest = Path(__file__).resolve().parents[2]/'quality_tests/systematic_20261012/variants_report.json'
    dest.write_text(json.dumps(dict(total=len(rows), passed=sum(r['passed'] for r in rows), results=rows),ensure_ascii=False,indent=2,default=str),encoding='utf-8')

if __name__ == '__main__': main()
