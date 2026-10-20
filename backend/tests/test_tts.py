"""A8：TTS 可播放；失敗時文字與案件不受影響；播放 URL 限時且不可偽造。"""

from __future__ import annotations

from app.providers.tts import MockTts
from app.worker import drain
from tests.conftest import login_liff, new_id


def answered(client, headers):
    data = client.post("/api/qa/ask", headers=headers,
                       json={"question": "照護紀錄要保存多久？", "client_request_id": new_id()}).json()
    assert data["outcome"] == "answered"
    return data


def test_tts_ready_and_playable(client, world):
    headers = login_liff(client, "cg1")
    data = answered(client, headers)
    assert client.post(f"/api/qa/{data['id']}/tts", headers=headers).json()["status"] == "queued"
    drain()
    status = client.get(f"/api/qa/{data['id']}/tts", headers=headers).json()
    assert status["status"] == "ready" and status["audio_url"]
    path = status["audio_url"].replace("http://testserver", "")
    audio = client.get(path)  # 不需 Bearer（供 LINE 取用），靠簽章＋到期保護
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mp4"
    assert len(audio.content) > 1000
    # 竄改簽章 → 404
    token = path.rsplit("/", 1)[1]
    tampered = token[:-4] + ("0000" if not token.endswith("0000") else "1111")
    assert client.get(f"/api/media/tts/{tampered}").status_code == 404
    # 重複點擊不會重複產生
    assert client.post(f"/api/qa/{data['id']}/tts", headers=headers).json()["status"] == "ready"


def test_tts_failure_keeps_text(client, world):
    headers = login_liff(client, "cg1")
    data = answered(client, headers)
    MockTts.fail = True
    client.post(f"/api/qa/{data['id']}/tts", headers=headers)
    for _ in range(3):
        from sqlalchemy import text

        from app.db import new_session

        session = new_session()
        session.execute(text("UPDATE jobs SET run_after = now()"))
        session.commit()
        session.close()
        drain()
    status = client.get(f"/api/qa/{data['id']}/tts", headers=headers).json()
    assert status["status"] == "failed" and status["audio_url"] is None
    again = client.get(f"/api/qa/{data['id']}", headers=headers).json()
    assert again["answer_text"] == data["answer_text"]
    assert again["citations"] == data["citations"]
    # 失敗後可再點一次重試
    MockTts.fail = False
    assert client.post(f"/api/qa/{data['id']}/tts", headers=headers).json()["status"] == "queued"
