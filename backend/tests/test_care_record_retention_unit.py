"""Pure-logic tests for the new care-record-retention intent recognizer and
its two downstream consumers (evidence_selection, retrieval_gate), plus the
independent qa_policy emergency-regex widening and transcripts ROLES label
fix. None of these touch embedding dimension/model -- no database, no
embedding provider, no network call.
"""
import uuid
from datetime import date

from app.services.query_understanding import care_record_retention
from app.services.evidence_selection import field_support
from app.services.qa_policy import DEFAULT_POLICY
from app.services.retrieval import RetrievedChunk
from app.services.retrieval_gate import assess_evidence
from app.services.transcripts import ROLES


def test_care_record_retention_recognizes_plain_question():
    assert care_record_retention("居家服務紀錄要保存多久？") is True
    assert care_record_retention("請問照顧紀錄應保存幾年") is True


def test_care_record_retention_recognizes_framed_question():
    assert care_record_retention("我是一名居家服務的照服員，想請問，服務紀錄要保存多久？") is True


def test_care_record_retention_rejects_unrelated_question():
    assert care_record_retention("個案的補助金額可以領多少？") is False
    assert care_record_retention("今天天氣如何？") is False


def test_care_record_retention_rejects_non_framing_prefix_clause():
    # A non-framing clause before the final one must not be silently accepted.
    assert care_record_retention("我昨天去醫院，想請問服務紀錄要保存多久？") is False


def test_field_support_matches_retention_sentence_via_new_subject_path():
    question = "居家服務紀錄要保存多久？"
    matching_body = "機構應將居家服務紀錄保存5年。"
    unrelated_body = "本機構每年會舉辦兩次員工旅遊活動。"
    assert field_support(question, matching_body) == 1
    assert field_support(question, unrelated_body) == 0


def test_qa_policy_emergency_rule_matches_added_death_and_pulse_phrases():
    emergency = next(r for r in DEFAULT_POLICY.risk_rules if r.code == "emergency")
    assert emergency.pattern.search("摸不到脈搏怎麼辦") is not None
    assert emergency.pattern.search("個案疑似已經死亡，怎麼辦") is not None
    assert emergency.pattern.search("失去生命跡象") is not None
    assert emergency.pattern.search("今天天氣很好") is None


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(), version_id=uuid.uuid4(), document_id=uuid.uuid4(),
        title="測試文件", doc_type="internal_rule", locator="第1條",
        version_label="v1", effective_from=date(2026, 1, 1), effective_to=None,
        text=text, coverage=0.5, vector=0.5, combined=0.5, injection_flag=False,
    )


def test_assess_evidence_rejects_retention_question_without_retention_topic_in_body():
    question = "居家服務紀錄要保存多久？"
    decision = assess_evidence(question, _chunk("本機構每年會舉辦兩次員工旅遊活動。"), DEFAULT_POLICY)
    assert decision.admitted is False
    assert decision.reason == "body_topic_missing"


def test_assess_evidence_admits_retention_question_with_matching_body():
    question = "居家服務紀錄要保存多久？"
    decision = assess_evidence(question, _chunk("機構應將居家服務紀錄保存5年，以供查核。"), DEFAULT_POLICY)
    assert decision.admitted is True


def test_transcripts_roles_label_matches_committed_frontend_role_labels():
    # frontend/src/api.ts ROLE_LABELS (already committed): supervisor:"居督", staff:"其他".
    assert ROLES["supervisor"] == "居督"
    assert ROLES["staff"] == "其他"
