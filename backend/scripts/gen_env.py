"""由 .env.example 產生含隨機密鑰的 .env（已存在則不覆寫）。

用法：
    python backend/scripts/gen_env.py
"""

from __future__ import annotations

import base64
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build_env_text(template: str) -> str:
    """把範本中的空白密鑰與預設密碼換成隨機值。

    Args:
        template: `.env.example` 的全文。

    Returns:
        可直接寫入 `.env` 的全文。
    """
    db_password = secrets.token_urlsafe(18)
    replacements = {
        "SECRET_KEY=": f"SECRET_KEY={secrets.token_urlsafe(48)}",
        "DATA_ENCRYPTION_KEY=": "DATA_ENCRYPTION_KEY="
        + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
        # mock 模式也要一把測試 channel secret 來做真實的簽章驗證
        "LINE_CHANNEL_SECRET=": f"LINE_CHANNEL_SECRET={secrets.token_hex(16)}",
    }
    lines = []
    for line in template.splitlines():
        key_part = line.split("#", 1)[0].strip()
        if key_part in replacements:
            line = replacements[key_part]
        line = line.replace("change-me", db_password)
        lines.append(line)
    return "\n".join(lines) + "\n"


def main() -> int:
    """寫出 .env。

    Returns:
        行程結束碼。
    """
    target = ROOT / ".env"
    if target.exists() and target.stat().st_size > 0:
        print(f".env 已存在，不覆寫：{target}")
        return 0
    if target.exists():
        print("既有 .env 是空檔（0 bytes），視為不存在並重新產生。")
    template = (ROOT / ".env.example").read_text(encoding="utf-8")
    target.write_text(build_env_text(template), encoding="utf-8")
    print(f"已產生 {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
