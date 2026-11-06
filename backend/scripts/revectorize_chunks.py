"""重新向量化 chunks：改用 Google EmbeddingGemma 2（768 維）後，補回被
migration 0007 清空的 embedding。

前提：
    - 已對正式／測試資料庫執行 migrations/versions/0007_embedding_gemma_768.py
      （本腳本不會自動跑 migration，也不會自動對正式庫執行任何東西）。
    - 本機 Ollama 已啟動並下載 embeddinggemma-2:270m（EMBEDDING_PROVIDER=ollama）。

安全設計：
    - 只處理 chunks.embedding IS NULL 的切塊；每批次獨立交易，逐批 commit。
    - 可重複執行、可中斷續跑：中途中斷只會少補一部分，已寫入的批次不受影響，
      重新執行會自動從剩餘 NULL 的切塊繼續。
    - 單一批次失敗（如 Ollama 逾時、維度不符）只記錄並跳過該批次 chunk id，
      不會讓整個程序中斷，也不會讓同一批在本次執行內無限重試；下次重新執行
      仍會自動再嘗試那些失敗過的切塊。
    - 只更新 embedding／embedding_model／tsv，不刪除、不覆寫 chunks.text 等
      原始資料；失敗紀錄只存 chunk id 與錯誤類型，不寫入切塊內容。
    - 預設 --dry-run：只統計筆數、不寫入；要真正寫入必須加 --apply。

進度與失敗紀錄：
    - 同步印到終端機，並附加寫入 backend/logs/revectorize_chunks.log
      （ROOT/backend/logs，自動建立；僅記錄筆數、chunk id、錯誤類型，不含文字內容）。

用法（實驗室 PowerShell，backend\\.venv\\Scripts\\python.exe）：
    python scripts/revectorize_chunks.py --dry-run
    python scripts/revectorize_chunks.py --apply --batch-size 16
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from app.db import get_engine  # noqa: E402
from app.providers.embedding import get_embedding_provider  # noqa: E402
from app.services.text import tsvector_source  # noqa: E402

LOG_PATH = ROOT / "backend" / "logs" / "revectorize_chunks.log"


def _setup_logger() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("revectorize_chunks")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
    return logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="實際寫入；省略則只統計筆數")
    parser.add_argument("--dry-run", action="store_true", help="明確指定只統計不寫入（與省略 --apply 效果相同，僅供文件清楚標示）")
    parser.add_argument("--batch-size", type=int, default=16, help="每批次筆數，預設 16")
    parser.add_argument("--limit", type=int, default=0, help="最多處理筆數，0 表示不限制（測試用）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = _setup_logger()
    engine = get_engine()
    provider = get_embedding_provider()

    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM chunks WHERE embedding IS NULL")
        ).scalar_one()

    logger.info("待補 embedding 的切塊數：%s", total)
    logger.info("Embedding provider：%s / model=%s / dim=%s", provider.name, provider.model, provider.dim)

    if not args.apply:
        logger.info("[dry-run] 未寫入任何資料。確認無誤後加 --apply 執行。")
        return 0

    processed = 0
    failed_total = 0
    skip_ids: list = []

    while True:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, text FROM chunks WHERE embedding IS NULL "
                    "AND NOT (id = ANY(CAST(:skip AS uuid[]))) ORDER BY id LIMIT :n"
                ),
                {"n": args.batch_size, "skip": skip_ids},
            ).all()

        if not rows:
            break

        try:
            with engine.begin() as conn:
                vectors = provider.embed_documents([row.text for row in rows])

                updated = 0
                for row, vector in zip(rows, vectors, strict=True):
                    result = conn.execute(
                        text(
                            "UPDATE chunks SET embedding = CAST(:emb AS vector), "
                            "embedding_model = :model, "
                            "tsv = to_tsvector('simple', :tsv_src) "
                            "WHERE id = :id AND embedding IS NULL"
                        ),
                        {
                            "emb": str(vector),
                            "model": provider.model,
                            "tsv_src": tsvector_source(row.text),
                            "id": row.id,
                        },
                    )
                    updated += result.rowcount
        except (RuntimeError, SQLAlchemyError) as exc:
            failed_ids = [row.id for row in rows]
            skip_ids.extend(failed_ids)
            failed_total += len(failed_ids)
            logger.warning(
                "本批次 %s 筆失敗，已跳過（本次執行內不再重試；下次重新執行會再嘗試）："
                "chunk_ids=%s error_type=%s",
                len(failed_ids), failed_ids, type(exc).__name__,
            )
            continue

        logger.info("本批次 %s 筆，實際更新 %s 筆", len(rows), updated)
        processed += updated

        if args.limit and processed >= args.limit:
            logger.info("已達 --limit %s，停止。", args.limit)
            break

    logger.info("完成，共更新 %s 筆，失敗跳過 %s 筆（詳見 %s）。", processed, failed_total, LOG_PATH)
    return 1 if failed_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
