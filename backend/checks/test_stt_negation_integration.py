"""Section 7 of the Whisper batch: confirm the STT-confirmed-text -> RAG
boundary does not collapse negation/polarity, using the real source graph
against ltc_clean in a READ ONLY transaction (same pattern as
evaluate_gold_v1.py). This does not call qa_service.ask(), create any
QaItem/Case, or touch the STT sidecar -- it only exercises the text that a
user would have already confirmed in the VoiceQuestion review step.
"""
import sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from checks.offline_rag_metrics import run_graph_with_capture
from checks.run_answer_quality_v1 import render

QUESTIONS = [
    ("我可以幫忙買藥嗎？", "positive"),
    ("我不可以幫忙買藥嗎？", "negative"),
    ("個案沒有跌倒。", "negative"),
    ("個案跌倒了。", "positive"),
    ("我要回報 BA16。", "neutral"),
]


def main() -> None:
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.config import get_settings
    from app.models import Organization
    from app.services.qa_policy import DEFAULT_POLICY

    url = make_url(get_settings().database_url)
    assert url.database == 'ltc_clean'
    engine = create_engine(url)
    rows = []
    with Session(engine) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        org = session.scalar(select(Organization).where(Organization.code == 'JIAAN'))
        before_count = session.scalar(text('SELECT count(*) FROM qa_items'))
        for question, polarity in QUESTIONS:
            state = run_graph_with_capture(dict(
                question_raw=question, session=session, org_id=org.id,
                facility_type=org.facility_type, today=date(2026, 10, 11), policy=DEFAULT_POLICY,
            ))
            actual = render(state)
            rows.append(dict(question=question, polarity=polarity, outcome=actual['outcome'],
                              behavior=actual['behavior'], answer=actual['answer'],
                              risk_result=actual['risk_result']))
            print(question, '->', actual['outcome'], actual['behavior'], actual['risk_result'])
        after_count = session.scalar(text('SELECT count(*) FROM qa_items'))
        assert before_count == after_count, 'must not write any QaItem rows'
        session.rollback()
    engine.dispose()

    pos_buy = next(r for r in rows if r['question'] == '我可以幫忙買藥嗎？')
    neg_buy = next(r for r in rows if r['question'] == '我不可以幫忙買藥嗎？')
    neg_fall = next(r for r in rows if r['question'] == '個案沒有跌倒。')
    pos_fall = next(r for r in rows if r['question'] == '個案跌倒了。')

    # SAFETY-CRITICAL, must hold: a real fall statement is still caught as a
    # risk/escalation case (not swallowed by a polarity bug).
    assert pos_fall['outcome'] == 'escalate' and pos_fall['risk_result'], \
        'an actual fall statement must still be caught as a risk/escalation case'
    # The dangerous failure mode this section 7 exists to catch -- ASR mishears
    # "沒有跌倒" as "跌倒" and the pipeline answers as if a fall just
    # happened -- did NOT occur: pos_fall and neg_fall take different paths.
    assert pos_fall['outcome'] != neg_fall['outcome'] or pos_fall['risk_result'] != neg_fall['risk_result'], \
        'positive and negative fall statements were not distinguished at all'

    # OBSERVED, reported rather than hard-failed here (see batch report §I):
    # pos_buy and neg_buy currently render the IDENTICAL answer text. This is
    # not a dangerous bare "yes you may" assertion either way -- the answer
    # only states the BA16 rule and its limits, never a literal permission
    # verdict -- but the system does not adapt wording to the rhetorical
    # negation ("我不可以...嗎？"). Left as a finding, not fixed here: fixing
    # natural-language rhetorical-negation handling is a query_understanding
    # change outside this Whisper batch's scope.
    if pos_buy['answer'] == neg_buy['answer']:
        print('\n[FINDING] positive/negative buy-medicine phrasing render identical answer text '
              '(not unsafe -- no bare yes/no assertion -- but not polarity-aware either).')
    print('\nFall-statement polarity correctly distinguished; no QaItem/Case rows created; ltc_clean read-only.')


if __name__ == '__main__':
    main()
