"""A5（後端部分）／A6：錄音上傳、實際解碼驗證、冪等、角色確認不虛構身分。"""

from __future__ import annotations

from sqlalchemy import select

from app.db import new_session
from app.models import Transcript, TranscriptRevision, TranscriptSegment
from app.providers.stt import MockStt
from app.worker import drain
from tests.conftest import login_liff, make_wav, new_id

SEGMENTS = [
    {"start_ms": 0, "end_ms": 2000, "text": "阿嬤說她今天不想洗澡", "uncertain": False},
    {"start_ms": 2000, "end_ms": 4000, "text": "家屬王小姐要我們多餵一餐", "uncertain": True},
    {"start_ms": 4000, "end_ms": 6000, "text": "我先記下來再問督導", "uncertain": False},
]


def upload(client, headers, path, mode="conversation", consent=True, upload_id=None):
    with path.open("rb") as handle:
        return client.post("/api/audio/uploads", headers=headers,
                           data={"mode": mode, "client_upload_id": upload_id or new_id(),
                                 "consent_confirmed": str(consent).lower()},
                           files={"file": ("rec.webm", handle, "audio/webm")})


def test_rejects_non_audio_even_with_audio_extension(client, world, tmp_path):
    headers = login_liff(client, "cg1")
    fake = tmp_path / "fake.webm"
    fake.write_bytes(b"this is not audio at all" * 100)
    response = upload(client, headers, fake)
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"decode_failed", "no_audio"}


def test_conversation_requires_consent(client, world, tmp_path):
    headers = login_liff(client, "cg1")
    response = upload(client, headers, make_wav(tmp_path / "a.wav"), consent=False)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "consent_required"


def test_too_long_rejected(client, world, tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "question_max_sec", 1)
    headers = login_liff(client, "cg1")
    response = upload(client, headers, make_wav(tmp_path / "a.wav", seconds=3), mode="question")
    assert response.status_code == 413


def test_upload_idempotent(client, world, tmp_path):
    headers = login_liff(client, "cg1")
    wav = make_wav(tmp_path / "a.wav")
    upload_id = new_id()
    first = upload(client, headers, wav, upload_id=upload_id).json()
    second = upload(client, headers, wav, upload_id=upload_id).json()
    assert first["transcript_id"] == second["transcript_id"]
    assert second["created"] is False


def test_roles_confirmed_by_caregiver_unknown_stays_unknown(client, world, tmp_path):
    """A6：預設全部未辨識；照服員只標了 speaker_1，其餘維持 unknown，不虛構身分。"""
    headers = login_liff(client, "cg1")
    MockStt.script = SEGMENTS
    transcript_id = upload(client, headers, make_wav(tmp_path / "a.wav")).json()["transcript_id"]
    drain()
    draft = client.get(f"/api/transcripts/{transcript_id}", headers=headers).json()
    assert draft["status"] == "draft"
    assert {s["speaker"] for s in draft["segments"]} == {"unknown"}
    assert draft["segments"][1]["uncertain"] is True
    body = {
        "segments": [{"idx": 0, "speaker": "speaker_1"}, {"idx": 1, "text": "家屬王小姐要我們晚上多餵一餐"}],
        "roles": {"speaker_1": "resident"},
        "selected_idx": [1],
        "summary": "家屬王小姐要求多餵一餐",
    }
    confirmed = client.post(f"/api/transcripts/{transcript_id}/confirm", json=body, headers=headers).json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["roles"] == {"speaker_1": "resident"}
    speakers = [s["speaker"] for s in confirmed["segments"]]
    assert speakers == ["speaker_1", "unknown", "unknown"]
    # 確認後只存遮罩版；未遮罩草稿刪除
    assert all("王小姐" not in s["text"] for s in confirmed["segments"])
    assert "王小姐" not in (confirmed["summary_masked"] or "")
    session = new_session()
    transcript = session.get(Transcript, transcript_id)
    assert transcript.draft_encrypted is None and transcript.draft_deleted_at is not None
    revisions = session.scalars(select(TranscriptRevision)).all()
    assert len(revisions) == 2
    assert all("王小姐" not in r.before_masked + r.after_masked for r in revisions)
    assert session.scalar(select(TranscriptSegment.selected).where(TranscriptSegment.idx == 1)) is True
    session.close()
    # 用確認後的逐字稿提問
    ask = client.post("/api/qa/ask", headers=headers, json={
        "question": "家屬要求多餵一餐怎麼處理", "source": "transcript", "transcript_id": transcript_id,
        "client_request_id": new_id()}).json()
    assert ask["outcome"] in {"answered", "escalated"}


def test_supervisor_role_tags_multiple_speakers(client, world, tmp_path):
    """第七輪：多人逐字稿角色標註，speaker_1=居督、speaker_2=家屬，各自留存角色與對應片段。"""
    headers = login_liff(client, "cg1")
    MockStt.script = SEGMENTS
    transcript_id = upload(client, headers, make_wav(tmp_path / "a.wav")).json()["transcript_id"]
    drain()
    body = {
        "segments": [{"idx": 0, "speaker": "speaker_1"}, {"idx": 1, "speaker": "speaker_2"}],
        "roles": {"speaker_1": "supervisor", "speaker_2": "family"},
        "selected_idx": [],
        "summary": None,
    }
    confirmed = client.post(f"/api/transcripts/{transcript_id}/confirm", json=body, headers=headers).json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["roles"] == {"speaker_1": "supervisor", "speaker_2": "family"}
    speakers = {s["idx"]: s["speaker"] for s in confirmed["segments"]}
    assert speakers[0] == "speaker_1" and speakers[1] == "speaker_2" and speakers[2] == "unknown"


def test_invalid_role_rejected(client, world, tmp_path):
    headers = login_liff(client, "cg1")
    MockStt.script = SEGMENTS
    transcript_id = upload(client, headers, make_wav(tmp_path / "a.wav")).json()["transcript_id"]
    drain()
    response = client.post(f"/api/transcripts/{transcript_id}/confirm", headers=headers,
                           json={"roles": {"speaker_1": "doctor"}})
    assert response.status_code == 400


def test_stt_failure_then_retry(client, world, tmp_path):
    headers = login_liff(client, "cg1")
    MockStt.script = RuntimeError("gpu busy")
    transcript_id = upload(client, headers, make_wav(tmp_path / "a.wav")).json()["transcript_id"]
    for _ in range(3):  # 3 次嘗試（退避時間在測試中直接放行）
        session = new_session()
        from sqlalchemy import text

        session.execute(text("UPDATE jobs SET run_after = now()"))
        session.commit()
        session.close()
        drain()
    data = client.get(f"/api/transcripts/{transcript_id}", headers=headers).json()
    assert data["status"] == "failed"
    assert data["audio_deleted"] is False  # 保留到期限內供重試
    MockStt.script = [{"start_ms": 0, "end_ms": 1000, "text": "重試成功", "uncertain": False}]
    assert client.post(f"/api/transcripts/{transcript_id}/retry", headers=headers).status_code == 200
    drain()
    assert client.get(f"/api/transcripts/{transcript_id}", headers=headers).json()["status"] == "draft"


def test_cancel_deletes_audio_and_draft(client, world, tmp_path):
    headers = login_liff(client, "cg1")
    MockStt.script = SEGMENTS
    transcript_id = upload(client, headers, make_wav(tmp_path / "a.wav")).json()["transcript_id"]
    drain()
    assert client.delete(f"/api/transcripts/{transcript_id}", headers=headers).status_code == 204
    session = new_session()
    transcript = session.get(Transcript, transcript_id)
    assert transcript.status == "cancelled" and transcript.draft_encrypted is None
    session.close()
