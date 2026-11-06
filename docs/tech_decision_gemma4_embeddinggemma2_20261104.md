# 技術決策紀錄：改用 Google Gemma 4 + EmbeddingGemma 2

- 日期：2026-11-04
- 專題：小照／嘉安居服專題（ChatGPT 端對外簡稱「鯨魚－專題」，為同一專題的不同代號）
- 性質：既有系統技術維護，非新增業務需求
- 核准：已取得指導老師同意
- 目的：符合 AgeTech 競賽資安及模型來源規範

本紀錄為獨立技術決策文件，**不取代、不覆寫** `CLAUDE.md` 所載 2026-10-30
嘉安第二次照服員訪談需求範圍；嘉安需求仍以 `CLAUDE.md` 與
`WORK_STATUS_1101.txt` 為準。本紀錄只記錄「生成與嵌入模型由何者改為何者、
為何改、改了哪些檔案」。

## 決策內容

| 項目 | 舊 | 新 |
|---|---|---|
| 生成模型（LLM） | 未鎖定（經 config.py 歷史顯示曾為其他模型） | `gemma4:e4b`（本機 Ollama） |
| 嵌入模型（Embedding） | 舊模型，1024 維 | `embeddinggemma-2:270m`（本機 Ollama），768 維 |
| LLM/Embedding 服務位置 | 本機 Ollama（`http://127.0.0.1:11434`） | 不變，仍為本機 Ollama，未串接任何雲端或第三方 API |

兩個模型皆由 `backend/app/config.py` 的 `field_validator` 強制鎖定
（`_only_gemma_llm`、`_only_gemma_embedding`、`_check_embedding_dim`），
不接受其他模型名稱或維度，以符合競賽對模型來源的規範要求。

## 已確認：無中國來源 AI 模型或連線設定

已搜尋 `backend/app/providers/`、`backend/app/config.py`、
`backend/app/services/` 等全部後端程式，確認：
- LLM provider 僅有 `ollama`（本機）、`extractive`（規則式摘錄，不呼叫任何
  外部服務）、`mock`（測試用）三種，無任何雲端 API 金鑰或連線設定。
- Embedding provider 僅有 `ollama`（本機）與 `hash`（測試用，純本地雜湊),
  同樣無外部連線。
- 全庫未發現任何中國來源大型語言模型（如 DeepSeek、Qwen、文心一言、智譜
  GLM、Kimi、豆包等）相關的套件、API 端點或設定鍵。

## 修改範圍

- `backend/app/config.py`、`backend/app/providers/embedding.py`、
  `backend/app/models.py`：模型與維度設定（改動前已存在，本次確認內容
  正確一致）。
- `backend/migrations/versions/0007_embedding_gemma_768.py`：
  `chunks.embedding` 欄位由 `vector(1024)` 改為 `vector(768)`（詳見下方
  「資料庫變更安全計畫」）。
- `backend/scripts/revectorize_chunks.py`：重新向量化腳本，補回被
  migration 清空的 embedding。
- `frontend/package.json` / `package-lock.json`：`@line/liff` 由
  `^2.26.1` 升級為 `^2.31.2`。
- `backend/app/services/documents.py`、`retrieval.py`、`worker.py` 等
  RAG 呼叫端：檢查後確認皆透過 `get_embedding_provider()` 抽象呼叫，
  未寫死舊模型名稱或維度，**不需修改**。

## 不受影響、必須保留的既有功能

本次重構僅調整 LLM／Embedding 模型與維度，**未新增、未刪除、未變更**以下
既有業務邏輯與規則：
LINE／LIFF 綁定、照服員／居督／主任角色權限、嘉安服務分類（BA/GA09/SC09）、
跨居督案件共享、緊急通報、稽核紀錄、法規出處引用、證據不足或高風險問題
轉人工（escalation）流程。

## 資料庫變更安全計畫（尚未對正式庫執行）

詳見 `docs/tech_decision_gemma4_embeddinggemma2_20261104.md` 本節與
對話中提供的三段式操作指令。摘要：
1. 備份正式 `ltc_clean`（pg_dump 或等效機制）。
2. 對正式庫執行 `alembic upgrade head`（套用 0007），此步驟會把
   `chunks.embedding`／`embedding_model` 清空為 NULL（因 1024→768 維度
   不相容，無法直接轉型）。
3. 立即執行 `scripts/revectorize_chunks.py --apply`，用
   `embeddinggemma-2:270m` 補回所有切塊的 embedding。
4. 執行期間檢索功能會暫時失效（embedding 為 NULL 的切塊不會被檢索
   SQL 選中），需安排在低使用時段，並於補完後以既有驗收問題覆核。

以上四步**皆未自動執行**，僅產生腳本與計畫，待使用者核准後於正式環境
手動執行。
