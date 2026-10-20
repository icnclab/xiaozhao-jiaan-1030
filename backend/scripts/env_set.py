"""安全地設定 .env 中的單一鍵值（只改該行，其餘原樣保留；值不會被印出）。

用法：
    uv run python scripts/env_set.py KEY=value [KEY2=value2 ...]
    uv run python scripts/env_set.py --show KEY [KEY2 ...]     # 只顯示非密鑰鍵的值（含 SECRET/TOKEN/PASSWORD/KEY 字樣的鍵只顯示長度）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parents[2] / ".env"
SENSITIVE = re.compile(r"SECRET|TOKEN|PASSWORD|KEY|URL$", re.IGNORECASE)


def main() -> int:
    """進入點。"""
    args = sys.argv[1:]
    text = ENV.read_text(encoding="utf-8-sig") if ENV.exists() else ""
    if args and args[0] == "--show":
        for key in args[1:]:
            match = re.search(rf"(?m)^{re.escape(key)}=(.*)$", text)
            value = match.group(1).strip() if match else None
            if value is None:
                print(f"{key}: (missing)")
            elif SENSITIVE.search(key) and key not in {"DATABASE_URL", "PUBLIC_BASE_URL", "OLLAMA_BASE_URL", "STT_BASE_URL"}:
                print(f"{key}: len={len(value)}")
            else:
                print(f"{key}={value}")
        return 0
    if len(text) < 200:
        print(f".env 內容過短（{len(text)} bytes），拒絕修改；先跑 gen_env.py")
        return 1
    for item in args:
        key, _, value = item.partition("=")
        if not key or not re.fullmatch(r"[A-Z0-9_]+", key):
            print(f"略過不合法的鍵：{key}")
            continue
        if re.search(rf"(?m)^{re.escape(key)}=.*$", text):
            text = re.sub(rf"(?m)^{re.escape(key)}=.*$", lambda _m, k=key, v=value: f"{k}={v}", text)
        else:
            text = text.rstrip("\n") + f"\n{key}={value}\n"
        print(f"set {key}")
    ENV.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
