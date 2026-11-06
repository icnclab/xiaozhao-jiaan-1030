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

責任分離（重要）：本檔只負責、也只判斷「chunks.embedding 欄位結構」這一件
事，分三種可能且互不蘊含的狀態來看：
  1. 結構狀態：欄位型別是 vector(768) 還是 vector(1024)——本檔唯一會檢查、
     依據來決定是否執行的狀態。
  2. 向量資料完整性：有多少筆 chunks.embedding 實際非 NULL——本檔完全不
     查，也不假設；那是 scripts/revectorize_chunks.py 的職責（它自己會先
     統計 IS NULL 筆數再處理）。
  3. Embedding 模型標記一致性：chunks.embedding_model 是否確實等於目前設
     定的模型名稱——同樣由 revectorize_chunks.py 負責寫入與更新，本檔不
     檢查。
結構狀態已是 vector(768) 絕不代表狀態 2、3 也已完成；本檔回傳（無論是正
常升級完或判定「已升級故跳過」）都只保證結構正確，從不宣稱、也不暗示向
量資料已重新嵌入或模型標記已對齊。若欄位不存在、或型別既非 vector(768)
也非 vector(1024)（結構異常、無法判定），直接丟出例外中止，絕不把「看
不懂」當成「尚未升級」而執行會清空資料的 UPDATE。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_embedding_gemma_768"
down_revision = "0006_jiaan1030_emergency"
branch_labels = None
depends_on = None

_TARGET_TYPE = "vector(768)"
_SOURCE_TYPE = "vector(1024)"


def _chunks_embedding_type() -> str | None:
    """查詢 chunks.embedding 目前實際的 Postgres 型別字串（如 "vector(768)"）。

    只回答欄位結構是什麼型別，不查、也不代表向量資料是否已補齊或
    embedding_model 標記是否一致——那是 scripts/revectorize_chunks.py 的
    職責，刻意與本 Migration 分離。回傳 None 表示資料表或欄位不存在。
    """
    conn = op.get_bind()
    return conn.execute(sa.text(
        "SELECT format_type(a.atttypid, a.atttypmod) "
        "FROM pg_attribute a JOIN pg_class c ON a.attrelid = c.oid "
        "WHERE c.relname = 'chunks' AND a.attname = 'embedding' "
        "AND a.attnum > 0 AND NOT a.attisdropped"
    )).scalar_one_or_none()


def _refuse_if_unknown_state(current: str | None, step: str) -> None:
    if current not in (_TARGET_TYPE, _SOURCE_TYPE):
        raise RuntimeError(
            f"0007 {step}：chunks.embedding 目前型別為 {current!r}，"
            f"既非 {_SOURCE_TYPE} 亦非 {_TARGET_TYPE}，狀態無法判定。"
            "拒絕執行會清空資料的 UPDATE；此鏈上游（0001-0006）理應已建立"
            "正常欄位，請人工確認實際資料庫結構後再處理，不要重跑本腳本。"
        )


def upgrade() -> None:
    current = _chunks_embedding_type()
    _refuse_if_unknown_state(current, "upgrade")
    if current == _TARGET_TYPE:
        # 結構已是目標維度：僅代表「結構」已升級，不代表向量資料已重新
        # 嵌入或模型標記已對齊（見檔頭「責任分離」）。不得重複清空資料。
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
    current = _chunks_embedding_type()
    _refuse_if_unknown_state(current, "downgrade")
    if current == _SOURCE_TYPE:
        return

    op.execute("UPDATE chunks SET embedding = NULL, embedding_model = NULL")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024)")
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
