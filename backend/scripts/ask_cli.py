"""命令列提問（開發除錯用）：以指定帳號跑完整問答流程並印出出口、原因、引用與檢索分數。

用法：
    uv run python scripts/ask_cli.py cg_happy_1 "家屬要我代購成藥可以嗎？" ["第二題" ...]
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import new_session  # noqa: E402
from app.models import Citation, Chunk, Document, DocumentVersion, User  # noqa: E402
from app.services import qa_service  # noqa: E402


def main() -> int:
    """進入點。"""
    username, questions = sys.argv[1], sys.argv[2:]
    session = new_session()
    user = session.scalar(select(User).where(User.username == username))
    for question in questions:
        item, case, _ = qa_service.ask(session, user, question=question, source="text",
                                       client_request_id=f"cli-{uuid.uuid4()}")
        print(f"\n問：{question}\n遮罩：{item.question_masked}\n出口：{item.outcome}  原因：{item.escalation_reason}"
              f"  案件：{case.number if case else '-'}  時間：{item.timings_ms}")
        print(f"答：{item.answer_text}")
        for row in session.execute(
            select(Citation.label, Document.title, Chunk.locator, DocumentVersion.version_label)
            .join(Chunk, Chunk.id == Citation.chunk_id).join(DocumentVersion, DocumentVersion.id == Citation.version_id)
            .join(Document, Document.id == DocumentVersion.document_id).where(Citation.qa_item_id == item.id)
        ):
            print(f"  出處 {row.label}: {row.title}｜{row.locator}｜{row.version_label}")
        for entry in item.checks.get("retrieval", [])[:4]:
            chunk = session.get(Chunk, uuid.UUID(entry["chunk_id"]))
            print(f"  cand cov={entry['coverage']:.2f} vec={entry['vector']:.2f} comb={entry['combined']:.2f}"
                  f" inj={entry['injection_flag']} {chunk.locator} {chunk.text[:28]!r}")
        if item.checks.get("claims"):
            print("  claims:", item.checks["claims"], item.checks.get("conflict"))
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
