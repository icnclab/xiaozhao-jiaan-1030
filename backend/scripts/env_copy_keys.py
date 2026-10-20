"""從另一份 .env 複製指定鍵到本專案 .env（值不印出）。

用法：python scripts/env_copy_keys.py <來源 .env> KEY [KEY ...]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """進入點。"""
    src, keys = Path(sys.argv[1]), sys.argv[2:]
    text = src.read_text(encoding="utf-8-sig")
    pairs = []
    for key in keys:
        match = re.search(rf"(?m)^{re.escape(key)}=(.*)$", text)
        if match:
            pairs.append(f"{key}={match.group(1).split('#', 1)[0].strip()}")
        else:
            print(f"missing in source: {key}")
    if pairs:
        subprocess.run([sys.executable, str(Path(__file__).with_name("env_set.py")), *pairs], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
