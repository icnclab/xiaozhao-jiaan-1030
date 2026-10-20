"""Service scope and recording intent remain distinct from clinical safety."""
import pytest
from app.services.query_understanding import record_intent, record_support, topic_token_groups
from app.services.qa_policy import DEFAULT_POLICY, screen_risk
from app.services.retrieval_gate import assess_evidence
from scripts.test_retrieval_gate import chunk

@pytest.mark.parametrize('q', ['今天協助長輩吃飯，要記什麼？','進食服務要不要留紀錄？','沐浴服務怎麼記？','翻身紀錄什麼？','服務要不要記錄？','服務怎麼記錄？','服务要記錄什麼？'])
def test_record_variants(q):
    assert record_intent(q)
    technique = chunk('進食技巧','使用粗柄湯匙調整餐椅高度。', coverage=.9,vector=.9)
    assert assess_evidence(q,technique,DEFAULT_POLICY).reason=='record_evidence_missing'

@pytest.mark.parametrize('q',['居家喘息可以協助進食嗎？','居家式喘息能幫忙餵飯嗎？'])
def test_respite_scope_rule(q):
    evidence=chunk('居家式喘息服務進食服務疑義','居家式喘息服務所含之進食可包含協助餵食、餐具準備與清潔。',coverage=.7,vector=.3)
    assert assess_evidence(q,evidence,DEFAULT_POLICY).admitted
    unrelated=chunk(evidence.title,'進食時應練習使用湯匙。',coverage=.9,vector=.9)
    assert not assess_evidence(q,unrelated,DEFAULT_POLICY).admitted

def test_general_assistance_not_record_intent():
    assert not record_intent('長輩吃飯要怎麼協助？')
    assert not screen_risk('長輩吃飯要怎麼協助？')

def test_swallowing_safety_unchanged():
    assert [r.code for r in screen_risk('長輩吃飯一直嗆到怎麼辦？')]==['clinical']
