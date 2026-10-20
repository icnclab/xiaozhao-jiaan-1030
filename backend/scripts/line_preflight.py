"""真實 LINE 模式前置檢查：驗證 .env、channel token、webhook 設定，全程不印出任何密鑰。

用法：
    uv run python scripts/line_preflight.py                  # 只檢查
    uv run python scripts/line_preflight.py --set-webhook    # 依 PUBLIC_BASE_URL 設定 webhook URL 並啟用
    uv run python scripts/line_preflight.py --test-webhook   # 請 LINE 平臺對 webhook 送測試請求（真實簽章）

只呼叫 LINE 官方固定端點（api.line.me）。token 只從 .env 讀，不接受命令列傳入。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402

API = "https://api.line.me"


def check(label: str, ok: bool, detail: str = "") -> bool:
    """印一行檢查結果。"""
    print(f"  [{'OK' if ok else 'FAIL'}] {label}{('：' + detail) if detail else ''}")
    return ok


def main() -> int:
    """進入點。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-webhook", action="store_true")
    parser.add_argument("--test-webhook", action="store_true")
    args = parser.parse_args()
    s = get_settings()
    print("1. .env")
    ok = True
    ok &= check("LINE_MODE=real", s.line_mode == "real", f"目前 {s.line_mode}")
    ok &= check("LINE_CHANNEL_SECRET 已設", bool(s.line_channel_secret), f"長度 {len(s.line_channel_secret)}")
    ok &= check("LINE_CHANNEL_ACCESS_TOKEN 已設", bool(s.line_channel_access_token),
                f"長度 {len(s.line_channel_access_token)}")
    ok &= check("LINE_LOGIN_CHANNEL_ID 已設（數字）", s.line_login_channel_id.isdigit(), s.line_login_channel_id or "空")
    ok &= check("LIFF_ID 格式（<數字>-<英數>）", "-" in s.liff_id and s.liff_id.split("-")[0].isdigit(), s.liff_id or "空")
    ok &= check("PUBLIC_BASE_URL 為 https", s.public_base_url.startswith("https://"), s.public_base_url)
    ok &= check("LIFF 的 channel 與 LINE_LOGIN_CHANNEL_ID 一致",
                bool(s.liff_id) and s.liff_id.split("-")[0] == s.line_login_channel_id)
    if not s.line_channel_access_token:
        print("沒有 access token，後續檢查略過。")
        return 1
    headers = {"Authorization": f"Bearer {s.line_channel_access_token}"}
    with httpx.Client(timeout=15, headers=headers) as client:
        print("2. Messaging API channel")
        r = client.get(f"{API}/v2/bot/info")
        if not check("token 有效（GET /v2/bot/info）", r.status_code == 200, f"HTTP {r.status_code}"):
            return 1
        info = r.json()
        print(f"     bot：{info.get('displayName')}（basicId {info.get('basicId')}，chatMode={info.get('chatMode')}，"
              f"markAsReadMode={info.get('markAsReadMode')}）")
        check("chatMode=bot（否則官方帳號的聊天模式會攔截訊息，webhook 收不到）", info.get("chatMode") == "bot")
        expected = f"{s.public_base_url.rstrip('/')}/api/line/webhook"
        if args.set_webhook:
            r = client.put(f"{API}/v2/bot/channel/webhook/endpoint", json={"endpoint": expected})
            check("設定 webhook URL", r.status_code == 200, f"HTTP {r.status_code}")
        r = client.get(f"{API}/v2/bot/channel/webhook/endpoint")
        if r.status_code == 200:
            data = r.json()
            check("webhook URL 與 PUBLIC_BASE_URL 一致", data.get("endpoint") == expected,
                  f"平臺上：{data.get('endpoint')}")
            check("webhook 已啟用（active）", bool(data.get("active")))
        else:
            check("讀取 webhook 設定", False, f"HTTP {r.status_code}（尚未設定 URL 時會 404）")
        if args.test_webhook:
            r = client.post(f"{API}/v2/bot/channel/webhook/test", json={"endpoint": expected})
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            check("LINE 平臺測試請求抵達且簽章驗證通過", r.status_code == 200 and data.get("success") is True,
                  f"HTTP {r.status_code} statusCode={data.get('statusCode')} reason={data.get('reason')} "
                  f"detail={data.get('detail')}")
        r = client.get(f"{API}/v2/bot/message/quota")
        if r.status_code == 200:
            q = r.json()
            print(f"     推播額度：type={q.get('type')} value={q.get('value', '無上限')}")
    print("3. 提醒")
    print("   - LINE Login channel 與 Messaging API channel 必須在同一 provider，否則 userId 對不上。")
    print("   - LIFF Endpoint 須為 PUBLIC_BASE_URL/liff；scope 至少 openid profile。")
    print("   - Quick Tunnel 網址改變後要重跑 --set-webhook，並到 Console 更新 LIFF Endpoint。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
