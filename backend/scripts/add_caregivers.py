"""批次建立照服員帳號並各產生一組一次性 LINE 綁定碼（7 天有效）。

用法：
    uv run python scripts/add_caregivers.py --org HAPPY 學生A 學生B 學生C
    uv run python scripts/add_caregivers.py --org HAPPY --prefix stu --count 5

綁定碼寫到 DATA_DIR 上一層的 binding_codes_<日期時間>.txt（不進版控），由督導轉交本人；
已存在的帳號不重建，只重新發一組綁定碼（舊碼作廢）。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import create_binding_code  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.models import BindingCode, Organization, User  # noqa: E402


def slug(name: str, index: int) -> str:
    """帳號：英數保留，其餘轉成序號。"""
    base = re.sub(r"[^a-z0-9]", "", name.lower())
    return base or f"cg{index:02d}"


def main() -> int:
    """進入點。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default="HAPPY")
    parser.add_argument("--prefix", default="stu")
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    names = args.names or [f"{args.prefix}{i:02d}" for i in range(1, args.count + 1)]
    if not names:
        print("請給名單或 --count")
        return 1
    lines = []
    with session_scope() as session:
        org = session.scalar(select(Organization).where(Organization.code == args.org))
        if org is None:
            print(f"找不到機構代碼 {args.org}")
            return 1
        admin = session.scalar(select(User).where(User.org_id == org.id, User.role == "admin"))
        for index, name in enumerate(names, start=1):
            username = f"{args.prefix}_{slug(name, index)}" if not name.startswith(args.prefix) else name
            user = session.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(org_id=org.id, username=username, display_name=name, role="caregiver")
                session.add(user)
                session.flush()
                status = "新建"
            else:
                status = "既有"
            # 舊的未用綁定碼作廢
            for old in session.scalars(select(BindingCode).where(BindingCode.user_id == user.id,
                                                                 BindingCode.used_at.is_(None))):
                old.expires_at = datetime.now(old.expires_at.tzinfo)
            code = create_binding_code(session, admin, user)
            lines.append(f"{org.name}\t{name}\t{username}\t綁定碼 {code}\t{status}")
    out = get_settings().data_dir.parent / f"binding_codes_{datetime.now():%Y%m%d_%H%M}.txt"
    out.write_text("機構\t顯示名稱\t帳號\t綁定碼（7 天、一次性）\t狀態\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"已建立 {len(lines)} 組綁定碼：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
