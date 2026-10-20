"""端到端示範：用本機 TTS 合成一段語音 → 以 LINE 語音訊息（模擬 webhook）送入 → 真實 STT 轉錄 → 用轉錄提問。

只在 LINE_MODE=mock 且 API、worker、STT sidecar 都在跑時使用。
用法：
    uv run python scripts/demo_line_voice.py [--base http://127.0.0.1:8140] [--user cg_happy_1] [--text "小照你好，照護紀錄要保存多久"]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.tts import SapiTts  # noqa: E402
from app.services.audio import to_m4a  # noqa: E402


def wait_outbox(client: httpx.Client, base: str, contains: str, after_id: int, timeout: float = 90) -> dict | None:
    """輪詢模擬信箱直到出現「本次執行之後」含指定文字的訊息（忽略更早的紀錄）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for row in client.get(f"{base}/api/dev/line/outbox", params={"limit": 20}).json():
            if row["id"] <= after_id:
                continue
            for message in row["messages"]:
                if contains in (message.get("text") or ""):
                    return message
        time.sleep(1.5)
    return None


def latest_outbox_id(client: httpx.Client, base: str) -> int:
    """目前模擬信箱最新一筆的 id（之後的才算本次結果）。"""
    rows = client.get(f"{base}/api/dev/line/outbox", params={"limit": 1}).json()
    return rows[0]["id"] if rows else 0


def main() -> int:
    """進入點。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8140")
    parser.add_argument("--user", default="cg_happy_1")
    parser.add_argument("--text", default="小照你好，照護紀錄要保存多久")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        m4a = Path(tmp) / "speech.m4a"
        SapiTts("Microsoft Hanhan Desktop").synthesize(args.text, wav)
        to_m4a(wav, m4a)  # LINE 語音訊息實際為 m4a
        with httpx.Client(timeout=30) as client:
            since = latest_outbox_id(client, args.base)
            started = time.perf_counter()
            with m4a.open("rb") as handle:
                response = client.post(f"{args.base}/api/dev/line/simulate",
                                       data={"kind": "audio", "username": args.user},
                                       files={"audio": ("speech.m4a", handle, "audio/mp4")})
            print("webhook:", response.json()["response"])
            draft = wait_outbox(client, args.base, "語音轉文字結果", since)
            if draft is None:
                print("轉錄結果未在時限內出現（檢查 worker 與 STT sidecar）")
                return 1
            print(f"轉錄推播（{time.perf_counter() - started:.1f}s）：{draft['text']}")
            postback = next(item["action"]["data"] for item in draft["quickReply"]["items"] if "data" in item["action"])
            transcript_id = parse_qs(postback)["t"][0]
            client.post(f"{args.base}/api/dev/line/simulate",
                        data={"kind": "postback", "username": args.user, "postback": postback})
            answer = (wait_outbox(client, args.base, "AI 初步參考", since)
                      or wait_outbox(client, args.base, "已送交督導", since, 5))
            print(f"回答推播（transcript {transcript_id}）：\n{answer['text'] if answer else '（無）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
