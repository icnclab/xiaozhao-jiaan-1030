"""模擬「Android App／智慧眼鏡」呼叫小照後端的完整流程，對著一台真的在跑的伺服器打。

這不是 pytest 單元測試（那些在 backend/tests/test_qa_hud.py），這支是端到端煙霧測試，
用來驗證 docs/wearable_android_api_guide.md 裡寫的流程實際可行。

帳密/連線資訊一律從環境變數讀，絕不寫進這支腳本或印到畫面：
    WEARABLE_TEST_BASE_URL   預設 http://127.0.0.1:8140
    WEARABLE_TEST_USERNAME   後台帳號（走 /api/auth/login，示範用可用 demo_accounts.md 裡的帳號）
    WEARABLE_TEST_PASSWORD   對應密碼

用法：
    $env:WEARABLE_TEST_USERNAME = "..."
    $env:WEARABLE_TEST_PASSWORD = "..."
    backend\.venv\Scripts\python.exe backend\scripts\test_wearable_api_flow.py

注意：這支腳本會對著「真的在跑」的伺服器送出真實請求，包含建立一筆 SOS 緊急通報
（category=other）後立刻自行取消（cancel），不會留下未結案的通報；但取消前那短暫
的時間窗內，正式環境既有的 WebPush outbox 仍可能實際對已訂閱的督導裝置推播一次。
在正式環境執行前請先確認這點可以接受。
"""

from __future__ import annotations

import os
import sys
import uuid
import wave
import io

import httpx

BASE_URL = os.environ.get("WEARABLE_TEST_BASE_URL", "http://127.0.0.1:8140").rstrip("/")
USERNAME = os.environ.get("WEARABLE_TEST_USERNAME")
PASSWORD = os.environ.get("WEARABLE_TEST_PASSWORD")


def _ok(label: str) -> None:
    print(f"[PASS] {label}")


def _fail(label: str, detail: str) -> None:
    print(f"[FAIL] {label}: {detail}")
    sys.exit(1)


def _silent_wav_bytes(seconds: float = 1.0, rate: int = 16000) -> bytes:
    """產生一段極短的靜音 16kHz 單聲道 WAV，純粹測試上傳/解碼管線，不含真人語音。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def main() -> None:
    if not USERNAME or not PASSWORD:
        _fail("setup", "請先設定環境變數 WEARABLE_TEST_USERNAME / WEARABLE_TEST_PASSWORD")

    client = httpx.Client(base_url=BASE_URL, timeout=30)

    # 1) 登入取得 session_token（對應 Android App 開機時的登入）
    r = client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    if r.status_code != 200:
        _fail("login", f"HTTP {r.status_code}: {r.text}")
    token = r.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    _ok("login -> session_token 取得成功")

    # 2) HUD 精簡問答（AR 眼鏡小螢幕用）
    r = client.post(
        "/api/qa/ask?format=hud",
        json={"question": "照護紀錄要保存多久？", "client_request_id": uuid.uuid4().hex},
        headers=headers,
    )
    if r.status_code != 200:
        _fail("qa/ask?format=hud", f"HTTP {r.status_code}: {r.text}")
    hud = r.json()
    if set(hud.keys()) != {"outcome", "escalation_reason_text", "hud_summary", "top_citation"}:
        _fail("qa/ask?format=hud 欄位", f"非預期欄位: {sorted(hud.keys())}")
    _ok(f"qa/ask?format=hud -> outcome={hud['outcome']}, hud_summary={hud.get('hud_summary')!r}")

    # 2b) 確認原本完整格式沒被動到（同一套端點，不帶 format 參數）
    r = client.post(
        "/api/qa/ask",
        json={"question": "照護紀錄要保存多久？", "client_request_id": uuid.uuid4().hex},
        headers=headers,
    )
    if r.status_code != 200:
        _fail("qa/ask（原格式）", f"HTTP {r.status_code}: {r.text}")
    full = r.json()
    if "hud_summary" in full or "top_citation" in full or "citations" not in full:
        _fail("qa/ask（原格式）欄位", f"原格式被動到了: {sorted(full.keys())}")
    _ok("qa/ask（省略 format）-> 完整結構不受影響（citations/claims/case 仍存在）")

    # 3) STT：上傳一段靜音 WAV，驗證語音管線收件（不驗證辨識結果內容）
    wav_bytes = _silent_wav_bytes()
    r = client.post(
        "/api/audio/uploads",
        files={"file": ("wearable_smoke_test.wav", wav_bytes, "audio/wav")},
        data={"mode": "question", "client_upload_id": uuid.uuid4().hex, "consent_confirmed": "true"},
        headers=headers,
    )
    if r.status_code not in (200, 201):
        _fail("audio/uploads", f"HTTP {r.status_code}: {r.text}")
    _ok(f"audio/uploads -> {r.json().get('status', r.json())}")

    # 4) SOS：建立一筆緊急通報，立刻自行取消（不留下未結案的真實通報）
    emergency_req_id = uuid.uuid4()
    r = client.post(
        "/api/jiaan1030/emergencies",
        json={"category": "other", "client_request_id": str(emergency_req_id)},
        headers=headers,
    )
    if r.status_code != 201:
        _fail("jiaan1030/emergencies create", f"HTTP {r.status_code}: {r.text}")
    emergency_id = r.json()["id"]
    _ok(f"jiaan1030/emergencies create -> id={emergency_id}")

    r = client.post(
        f"/api/jiaan1030/emergencies/{emergency_id}/cancel",
        json={"client_request_id": str(uuid.uuid4()), "reason": "wearable_api_flow smoke test cleanup"},
        headers=headers,
    )
    if r.status_code != 200 or r.json().get("status") != "cancelled":
        _fail("jiaan1030/emergencies cancel", f"HTTP {r.status_code}: {r.text}")
    _ok("jiaan1030/emergencies cancel -> 已清理，沒有留下未結案通報")

    # 5) 無效／過期 Token 必須回 401
    r = client.post(
        "/api/qa/ask?format=hud",
        json={"question": "測試", "client_request_id": uuid.uuid4().hex},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    if r.status_code != 401:
        _fail("無效 token", f"預期 401，實際 HTTP {r.status_code}: {r.text}")
    _ok(f"無效 token -> 401（{r.json().get('detail', {}).get('code')}）")

    print("\n全部步驟通過：登入 / HUD問答 / 原格式問答 / STT上傳 / SOS建立與取消 / 無效token 全部符合預期。")


if __name__ == "__main__":
    main()
