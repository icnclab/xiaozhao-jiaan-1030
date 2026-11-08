> 2026-11-08 審核分支：完整既有程式＋UAT 維運／合成 MPC shadow／官方 Drive API 準備。運行中服務未因本分支更新；Drive OAuth／上傳／新排程未啟用。請先讀 [整合狀態](docs/handover/整合狀態_20261108.md) 與 [API 同步指南](docs/sync/GoogleDrive_API_準備與啟用.md)。以下原 MVP 說明含歷史狀態及新機開發步驟，不是授權在正式主機執行安裝／migration。

# 長照 AI 照護小幫手（小照）— 住宿式機構 MVP

照服員透過 LINE（Bot＋LIFF）以文字或語音詢問法規與機構規範；系統只回答知識庫中有依據的問題並附完整出處卡，依據不足、文件衝突或涉及臨床／用藥／補助金額時轉督導確認；督導在 Web 後台接手案件、回覆、維護文件版本。

> **狀態：本機可執行的 MVP。** LINE 為**模擬模式**（未取得真實 channel 憑證）、STT／TTS／LLM 為本機推論、知識庫全為**合成文件與虛構機構**。中華電信 STT／TTS 與 hicloud **未串接**（只保留 adapter）。未驗證項目見 [docs/acceptance.md §4](docs/acceptance.md)。

## 目錄

```
backend/     FastAPI＋LangGraph＋worker（Python 3.11+，uv 鎖定相依）
frontend/    React＋TypeScript（Vite）：/liff 照服員端、/admin 督導後台
services/    stt_sidecar：faster-whisper HTTP sidecar（本機 GPU）
demo/        合成文件、評測題庫、展示腳本
docs/        需求對照、架構、資料流、API 契約、驗收、部署、進度、評測結果
deploy/      資料庫初始化 SQL
```

## 快速啟動（開發機：Windows＋WSL Docker；API／worker 跑在主機以使用 GPU、SAPI、Ollama）

```bash
# 1. 產生 .env（隨機密鑰；已存在不覆寫）
python backend/scripts/gen_env.py

# 2. 資料庫（pgvector）
docker compose up -d db

# 3. 後端相依與 migration
cd backend && uv sync && uv run alembic upgrade head

# 4. 合成展示資料（兩個虛構機構、帳號、分類、文件）；帳號密碼寫到 F:\appdata\ltc_care\demo_accounts.txt
uv run python scripts/seed_demo.py --reset

# 5. API 與 worker（兩個視窗）
uv run uvicorn app.main:app --host 127.0.0.1 --port 8140 --reload
uv run python -m app.worker

# 6.（可選）本機 STT sidecar：需 venv 內有 faster-whisper＋CUDA runtime
C:\Users\<you>\venvs\asr\Scripts\python.exe services/stt_sidecar/server.py --port 8147 --model medium

# 7. 前端
cd ../frontend && npm ci && npm run dev      # http://localhost:5173/liff 、 /admin
```

`.env` 重點（全部見 `.env.example`）：

| 變數 | 說明 |
|---|---|
| `LINE_MODE` | `mock`（預設；簽章仍真實驗證，reply／push 寫入模擬信箱）或 `real` |
| `LLM_PROVIDER` | `ollama`（`LLM_MODEL`）、`extractive`（不生成、摘錄條文）、`mock` |
| `STT_PROVIDER` | `whisper_http`（sidecar）、`mock`、`cht`（未串接） |
| `TTS_PROVIDER` | `sapi`（Windows 語音）、`mock`、`cht`（未串接） |
| `WAKE_WORDS` | 喚醒詞清單（預設含「小照你好」與同音「小昭」） |

畫面與 API 回應會標示目前 provider 模式；**模擬模式的結果不算真實串接成功**。

## 測試

```bash
cd backend && uv run pytest              # 96 項：流程、授權、版本、冪等、清理、注入（全部 mock provider）
uv run python scripts/eval_run.py --llm extractive   # 24 題初測（獨立 ltc_eval 資料庫）
uv run python scripts/eval_run.py --llm ollama
```

結果寫入 `docs/eval-results.md`；引用是否支持主張需人工標註 `docs/eval-citation-review.csv`。

## Docker Compose 展示（全部容器化）

```bash
docker compose --profile app up -d --build   # web:8141 → api:8140；推論預設 extractive／hash／mock
```

容器內沒有 GPU 與 SAPI：要用本機 Ollama／STT sidecar 時，把 `OLLAMA_BASE_URL`、`STT_BASE_URL` 指向主機（如 `http://host.docker.internal:11434`）。

## LINE／LIFF 設定（真實模式）

見 [docs/deployment.md](docs/deployment.md)。要點：Messaging API channel 與 LINE Login channel 須在**同一 provider**；webhook 需 HTTPS；LIFF endpoint 指向 `https://<host>/liff`；`LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_LOGIN_CHANNEL_ID`、`LIFF_ID`、`PUBLIC_BASE_URL` 填入 `.env`，`LINE_MODE=real`。

## 文件

- [docs/requirements.md](docs/requirements.md) 需求對照（新增／沿用／暫緩）
- [docs/architecture.md](docs/architecture.md) 架構、問答 StateGraph、案件與轉錄狀態機
- [docs/data-flow.md](docs/data-flow.md) 資料流與第三方處理邊界（LINE、瀏覽器語音服務）
- [docs/api-contract.md](docs/api-contract.md) API 契約
- [docs/acceptance.md](docs/acceptance.md) 驗收清單、評測規格、未驗證項目
- [docs/deployment.md](docs/deployment.md) 部署與 LINE 設定
- [docs/progress.md](docs/progress.md) 各階段進度、測試結果、待解問題（中斷後由此續作）
- [docs/eval-results.md](docs/eval-results.md) 初測結果
- [demo/DEMO_SCRIPT.md](demo/DEMO_SCRIPT.md) 展示操作腳本
