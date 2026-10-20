"""Swallowing safety routes before clarification, retrieval and generation."""
from datetime import date
from unittest.mock import patch
import pytest
from app.services import qa_graph as graph
from app.services.qa_policy import DEFAULT_POLICY, screen_risk

CLINICAL = ["長輩吃飯一直嗆到怎麼辦？", "長輩最近常嗆咳", "長輩吞嚥困難要怎麼處理？",
            "喝水嗆到", "吃東西一直嗆", "長輩吞不下去", "長輩噎到", "這個吞嚥困難要怎麼處理？"]
ADMIN = ["居家喘息可以協助進食嗎？", "進食服務要不要留下紀錄？", "今天協助長輩吃飯，要記什麼？"]

@pytest.mark.parametrize("question", CLINICAL)
def test_clinical_stops_before_clarify_retrieval_llm(question):
    with patch.object(graph, "node_clarify", side_effect=AssertionError("clarify reached")), \
         patch.object(graph, "node_retrieve", side_effect=AssertionError("retrieval reached")), \
         patch.object(graph, "node_generate", side_effect=AssertionError("LLM reached")):
        result = graph.build_graph().invoke(dict(question_raw=question, policy=DEFAULT_POLICY,
            session=None, org_id=None, facility_type="home", today=date(2026,10,8)))
    assert result["outcome"] == "escalate"
    assert result["reason"] == "risk_clinical"
    assert result["checks"]["risk_codes"] == ["clinical"]
    assert not result.get("claims") and not result.get("retrieved")

@pytest.mark.parametrize("question", ADMIN)
def test_meal_administration_reaches_retrieval(question):
    assert screen_risk(question) == []
    with patch.object(graph, "node_retrieve", return_value={"outcome":"escalate", "reason":"no_evidence"}) as retrieval:
        result = graph.build_graph().invoke(dict(question_raw=question, policy=DEFAULT_POLICY,
            session=None, org_id=None, facility_type="home", today=date(2026,10,8)))
    retrieval.assert_called_once()
    assert result["reason"] == "no_evidence"

def test_emergency_priority_preserved():
    rules = screen_risk("長輩噎到呼吸困難，這個怎麼處理？")
    assert rules[0].code == 'emergency'
    assert 'clinical' in [r.code for r in rules]
    assert 'respiratory_abnormality' in [r.code for r in rules]
