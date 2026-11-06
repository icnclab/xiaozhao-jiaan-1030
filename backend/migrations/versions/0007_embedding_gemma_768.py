"""EmbeddingGemma 2：chunks.embedding 自 vector(1024) 改為 vector(768)。

重要：改維度前所有既有向量都失去意義（不同模型、不同維度），因此本次
升級會把 embedding / embedding_model 清空，之後必須執行
`backend/scripts/revectorize_chunks.py` 重新向量化，否則檢索會
查不到任何結果（embedding IS NULL 的切塊不會被檢索 SQL 選中）。

本檔僅產生腳本，不自動對正式資料庫執行；請先在測試庫驗證，並於
執行前備份（pg_dump 或等效機制）。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_embedding_gemma_768"
down_revision = "0006_jiaan1030_emergency"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.execute("UPDATE chunks SET embedding = NULL, embedding_model = NULL")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024)")
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
