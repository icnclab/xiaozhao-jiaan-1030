"""Pure multi-turn Context checks. Run by direct import; never loads conftest."""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql://test:test@127.0.0.1:1/isolated_no_connect",
    "LLM_PROVIDER": "mock",
    "EMBEDDING_PROVIDER": "hash",
    "LINE_MODE": "mock",
})

from app.api import caregiver_routes, serializers  # noqa: E402
from app.models import QaItem  # noqa: E402
from app.services import qa_service  # noqa: E402
from app.services.query_understanding import contextual_question  # noqa: E402
from app.services.qa_policy import screen_risk  # noqa: E402


class ScalarSession:
    def __init__(self, value):
        self.value = value
        self.statement = None
        self.calls = 0

    def scalar(self, statement):
        self.calls += 1
        self.statement = statement
        return self.value


def test_context_lookup_is_owner_org_and_conversation_scoped_and_limited():
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    conversation_id = uuid.uuid4()
    session = ScalarSession("x" * 700)

    previous = qa_service._previous_question(session, user, conversation_id)

    assert previous == "x" * qa_service.MAX_QUESTION_CHARS
    assert session.calls == 1
    sql = str(session.statement)
    assert "qa_items.user_id" in sql
    assert "qa_items.org_id" in sql
    assert "qa_items.conversation_id" in sql
    assert "LIMIT" in sql
    assert "JOIN" not in sql
    assert "cases" not in sql


@pytest.mark.parametrize("unsupported_field", ["case_id", "case_context"])
def test_qa_request_rejects_case_context_fields(unsupported_field):
    payload = {
        "question": "一般規範問題",
        "client_request_id": "request-id-123",
        unsupported_field: "must-not-be-used",
    }

    with pytest.raises(ValidationError):
        caregiver_routes.AskIn.model_validate(payload)


def test_missing_or_foreign_context_fails_closed():
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    session = ScalarSession(None)

    try:
        qa_service._previous_question(session, user, uuid.uuid4())
    except qa_service.QaError as exc:
        assert exc.code == "conversation_not_found"
    else:
        raise AssertionError("an unknown or foreign conversation must be rejected")


def test_idempotency_retry_from_another_org_fails_closed():
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    old_item = SimpleNamespace(org_id=uuid.uuid4())
    session = ScalarSession(old_item)

    try:
        qa_service._existing_request(session, user, "request-id-789")
    except qa_service.QaError as exc:
        assert exc.code == "request_organization_mismatch"
    else:
        raise AssertionError("a prior organization's response must not be replayed")
    sql = str(session.statement)
    assert "qa_items.user_id" in sql
    assert "qa_items.client_request_id" in sql


def test_contextual_followup_is_narrow_and_does_not_override_high_risk():
    previous = "家屬要我幫住民代購成藥，機構規定可以嗎？"
    assert not screen_risk(previous)
    assert contextual_question("那可以代買嗎", previous) == previous + "，那可以代買嗎"
    assert screen_risk(contextual_question("住民昏倒了沒有呼吸", previous))

    high_risk_previous = "家屬要我幫住民代購成藥，住民昏倒了沒有呼吸"
    assert screen_risk(high_risk_previous)
    assert contextual_question("那可以代買嗎", high_risk_previous) == "那可以代買嗎"


def test_context_expansion_never_exceeds_question_limit():
    previous = "家屬要我幫住民代購成藥，機構規定可以嗎？" + "補充" * 300

    result = qa_service._apply_question_context("那可以代買嗎", previous)

    assert result == "那可以代買嗎"
    assert len(result) <= qa_service.MAX_QUESTION_CHARS


def test_unknown_conversation_maps_to_not_found_without_disclosure():
    body = caregiver_routes.AskIn(
        question="可以嗎？",
        conversation_id=str(uuid.uuid4()),
        client_request_id="request-id-123",
    )
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), role="caregiver")

    def reject(*args, **kwargs):
        raise qa_service.QaError("conversation_not_found", "找不到對話")

    with patch.object(caregiver_routes.qa_service, "ask", reject):
        try:
            caregiver_routes.ask(body, user, object())
        except caregiver_routes.HTTPException as exc:
            assert exc.status_code == 404
            assert exc.detail["code"] == "not_found"
            assert exc.detail["message"] == "找不到資料"
        else:
            raise AssertionError("unknown conversation must return 404")


def test_idempotency_key_cannot_be_reused_for_another_conversation():
    body = caregiver_routes.AskIn(
        question="可以嗎？",
        conversation_id=str(uuid.uuid4()),
        client_request_id="request-id-456",
    )
    user = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), role="caregiver")

    def reject(*args, **kwargs):
        raise qa_service.QaError("request_conversation_mismatch", "提問請求與對話不一致")

    with patch.object(caregiver_routes.qa_service, "ask", reject):
        try:
            caregiver_routes.ask(body, user, object())
        except caregiver_routes.HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail["message"] == "提問請求與對話不一致"
        else:
            raise AssertionError("request ID reuse across conversations must be rejected")


class EmptyResult:
    def all(self):
        return []


class SerializerSession:
    def __init__(self):
        self.statements = []

    def scalar(self, statement):
        return None

    def execute(self, statement):
        self.statements.append(statement)
        return EmptyResult()


def test_answer_serializes_its_thread_id_and_keeps_citations_qa_scoped():
    qa_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    item = SimpleNamespace(
        id=qa_id,
        conversation_id=conversation_id,
        created_at=None,
        outcome="answered",
        question_masked="問題",
        answer_text="回答",
        claims=[],
        checks={},
        escalation_reason=None,
        case_error=None,
        llm_provider="mock",
        embedding_provider="hash",
        qa_policy_version="test",
    )
    session = SerializerSession()
    serializers.get_settings.cache_clear()

    result = serializers.qa_out(session, item)

    assert result["conversation_id"] == str(conversation_id)
    assert result["citations"] == []
    assert len(session.statements) == 1
    citation_query = str(session.statements[0])
    assert "citations.qa_item_id" in citation_query
    assert "qa_items.conversation_id" not in citation_query
