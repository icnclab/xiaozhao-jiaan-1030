"""EmbeddingGemma 2：chunks.embedding 自 vector(1024) 改為 vector(768)。

重要：改維度前所有既有向量都失去意義（不同模型、不同維度），因此本次
升級會把 embedding / embedding_model 清空，之後必須執行
`backend/scripts/revectorize_chunks.py` 重新向量化，否則檢索會
查不到任何結果（embedding IS NULL 的切塊不會被檢索 SQL 選中）。

本檔僅產生腳本，不自動對正式資料庫執行；請先在測試庫驗證，並於
執行前備份（pg_dump 或等效機制）。

重複執行保護：ltc_demo 已確認 alembic_version 記錄為 0007、chunks.embedding
實際欄位型別已是 vector(768)（唯讀查核於先前回合完成）。正常情況下 Alembic
自己的版本表會阻止重複套用同一版本，但若有人改用其他方式（例如直接複製本檔
upgrade() 的 SQL 手動執行、或 alembic_version 因故被改動）重跑這段腳本，
原本沒有防呆的版本會再次把已經正確的 768 維向量清空成 NULL，等同重新造成
一次「檢索暫時失效」的事故。因此 upgrade()／downgrade() 都先查詢欄位目前
的實際型別，已經是目標型別就直接跳過，不重複清空資料。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


def _current_embedding_type() -> str | None:
    """查詢 chunks.embedding 目前實際的型別字串（如 "vector(768)"）。

    查不到資料表／欄位（例如全新空庫尚未跑過 0001）就回傳 None，交由呼叫端
    走正常升級流程；不在這裡假設資料表一定存在。
    """
    conn = op.get_bind()
    return conn.execute(sa.text(
        "SELECT format_type(a.atttypid, a.atttypmod) "
        "FROM pg_attribute a JOIN pg_class c ON a.attrelid = c.oid "
        "WHERE c.relname = 'chunks' AND a.attname = 'embedding' "
        "AND a.attnum > 0 AND NOT a.attisdropped"
    )).scalar_one_or_none()

revision = "0007_embedding_gemma_768"
down_revision = "0006_jiaan1030_emergency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _current_embedding_type() == "vector(768)":
        # 已經是目標維度（例如 alembic_version 曾被手動對齊過）：不重複清空
        # 既有向量，直接視為本版本已完成。
        return

    # 1) 先清空舊維度向量與模型標記，避免型別轉換時資料不相容
    op.execute("UPDATE chunks SET embedding = NULL, embedding_model = NULL")

    # 2) HNSW 索引綁定向量維度，必須先移除才能改欄位型別
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")

    # 3) 欄位型別改為 vector(768)
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(768)")

    # 4) 重建 HNSW 索引
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    if _current_embedding_type() == "vector(1024)":
        return

    op.execute("UPDATE chunks SET embedding = NULL, embedding_model = NULL")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024)")
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
