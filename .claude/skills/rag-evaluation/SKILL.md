---
name: rag-evaluation
description: 小照（長照 AI 問答）RAG 問答、來源引用、拒答與高風險轉人工驗證流程。修改 backend/app/services/{retrieval,retrieval_gate,evidence_selection,qa_policy,query_understanding,transcripts}.py、backend/app/providers/embedding.py、backend/app/services/documents.py 任何一個檔案時使用；也用於有人問「RAG 還正常嗎」「這次改動會不會斷鏈」時。
---

# 小照 RAG 驗證 Skill

## 用途
確保「提問 → 檢索 → 證據篩選 → 風險規則 → 回答／轉人工 → 引用」這條鏈，在修改 RAG 相關程式後仍然完整、仍然安全（不亂答、不漏判高風險、不假裝有出處）。

## 啟動條件（符合任一項就該用這個 Skill）
- 修改了下列任一檔案：
  `backend/app/services/retrieval.py`、`backend/app/services/retrieval_gate.py`、
  `backend/app/services/evidence_selection.py`、`backend/app/services/qa_policy.py`、
  `backend/app/services/query_understanding.py`、`backend/app/services/transcripts.py`、
  `backend/app/providers/embedding.py`、`backend/app/services/documents.py`。
- 有人要求「驗證 RAG」「確認問答沒有斷鏈」「確認引用正確」。
- 要調整 embedding 模型或向量維度（`EMBEDDING_DIM`、`embedding_model`）。

## 執行步驟
1. **先看清楚改了什麼**：`git diff` 上述檔案，確認是否牽動 embedding 維度／模型（會牽連 `backend/app/models.py` 的 `EMBEDDING_DIM` 與資料庫 `chunks.embedding` 欄位，屬於需要 Migration 的高風險變更，不能只靠這個 Skill 驗證完就直接套用）。
2. **純邏輯測試（不連資料庫，一定要先做這一步）**：
   `backend/tests/` 下目前已有的純邏輯測試檔，用直接 import 方式執行（繞開會連資料庫的 `backend/tests/conftest.py`）：
   ```
   cd backend
   ./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); import test_care_record_retention_unit as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('OK')"
   ./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); import test_embedding_gemma_compat_unit as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_') and 'monkeypatch' not in __import__('inspect').signature(getattr(t,n)).parameters]; print('OK')"
   ```
   （若新增了其他 RAG 純邏輯測試檔，一併用同樣方式跑過。）
3. **模組載入檢查（不連資料庫）**：
   ```
   cd backend
   DATABASE_URL=postgresql+psycopg://placeholder:placeholder@127.0.0.1:1/placeholder ./.venv/Scripts/python.exe -c "import app.main; print('import OK')"
   ```
4. **若有已在跑的展示環境（`http://127.0.0.1:8151`，連的是 `ltc_demo`，不是正式庫）**，可用既有的虛構示範帳號做一次端對端驗證（不得用在正式 API `8140`）：
   - 用 `backend/scripts/seed_demo.py` 已知的種子帳號（例如 `cg_happy_1`）登入，問一題貼近種子文件內容的問題，確認 `outcome` 是 `answered` 且 `citations` 有正確出處；再問一題明顯無關的問題，確認會 `escalated` 轉人工，不會亂答。
   - 這一步需要展示 API 真的在跑，才能做；不行就略過，不要假裝測過。

## 驗證方式
- 以上指令全部印出 `OK`／測試函式沒有拋出例外，視為通過。
- 若用了展示環境驗證，`outcome:"answered"` 且 `citations` 非空、出處內容與問題相關，才算通過；`outcome:"escalated"` 且 `citations` 為空也是正確行為（證據不足時的安全預設），不是缺陷。

## 停止條件（出現任何一項就停下來，不要自己決定繼續）
- 牽動 embedding 維度或模型（需要 Migration 才能生效）→ 列出需要的 Migration 與審核條件，不自行執行。
- 純邏輯測試有任何一項失敗 → 先修正程式或測試本身（需判斷是程式錯還是測試過時），不得略過失敗繼續宣稱「已驗證」。
- 需要連線正式資料庫或正式 API（`8140`）才能驗證 → 明確回報「這部分需要資料庫連線／管理者授權才能驗證」，不要自己連。
