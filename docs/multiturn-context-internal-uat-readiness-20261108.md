# 小照多輪 Context：內部驗收準備報告（2026-11-08）

## 結論

程式、ORM、API 與新增 migration 已在全新臨時 PostgreSQL 及臨時 API 完成離線 HTTP 驗收；現有 UAT 8151 尚不相容，不能直接開始本人 LINE 測試，也未對 8151、Worker、Webhook、Tailscale 或既有資料庫做任何變更。

## 實際版本與 UAT 唯讀結果

- 正式 8140 與 UAT 8151 均有實際 Python/Uvicorn listener；兩者健康檢查回 200，但 health 回應沒有 commit/build identity，因此不能由 health 宣稱部署版本。
- 8151 API 與 UAT Worker 均由正式主目錄的 venv 啟動；active metadata 指向既有 UAT 隔離執行組，資料庫 `ltc_demo`、角色 `ltc_uat_app`、outbound blocked、Web Push off。
- UAT source 工作樹基準 HEAD 為 `acabff64fe4e7c38b38193e7045e482325e761f4`，且有既存未提交 UAT 作業檔；未覆蓋或修改。
- UAT 的 caregiver routes、interaction routes、qa_service、Alembic env 與 frontend build 均不同於本次驗收版本；UAT 沒有 `0010_service_interactions.py`。
- 專案內建 UAT 靜態隔離與 read-only DB 預檢通過：專用設定、最小權限 roster、`ltc_demo` 及跨資料庫拒絕均符合既有防線。
- UAT schema read-only 檢查：Alembic `0007_embedding_gemma_768`；`qa_items.conversation_id` 存在；`service_interactions`、`interaction_read_grants` 不存在。
- LINE Messaging API webhook 的唯讀查詢回 `HTTPError`，未修改設定、未送訊；因此目前只能確認本機設定與正式值隔離，不能確認 LINE 後台 endpoint 當下有效。

## 本次修正

### Schema

- 新增線性 migration `0010_service_interactions`，接在目前 active head `0009_fieldtest_participants` 後。
- 新增 `service_interactions` 與 `interaction_read_grants`，其欄位、外鍵、唯一鍵與 ORM 一致。
- `qa_items.conversation_id` 刻意不加 Interaction foreign key，以保留既有 standalone UUID thread 相容性。
- Alembic env 現在載入 `interaction_models`，autogenerate metadata 不再漏表。

### API／Context

- caregiver 第一題省略 `conversation_id` 時，後端以該 request ID 透明建立 Interaction；第一題不讀上一題。
- 只有明確帶入既有 `conversation_id` 才載入上一筆遮罩問題。
- 同一第一題 request ID 重送會回到同一 Interaction／QA，不重建對話。
- 已結束 Interaction 拒絕新 request；既有 request 的同對話冪等重送仍可取回原結果。
- 舊 standalone UUID 與非 caregiver 原行為保留。

## 隔離驗證環境

- 臨時 PostgreSQL：全新 `pgvector/pgvector:pg16` 容器、loopback port 55803、全新 synthetic credentials；未掛載既有 volume。
- 臨時 API：loopback port 18152、Mock LLM/STT/TTS/LINE、虛構兩機構與帳號；未啟動 Worker。
- 測試後停止並以 `--rm` 自動移除容器；其中只有虛構資料，已不可恢復且無保留必要。
- 未連正式／UAT 寫入、未發 LINE、mock outbox 0、notification jobs 0。

## 測試結果

- Migration fresh upgrade：`0001 -> 0002 -> 0003 -> 0004 -> 0005 -> 0006 -> 0007 -> 0009 -> 0010` 通過。
- Schema checker：fresh DB compatible，Alembic `0010_service_interactions`。
- Migration rollback：`0010 -> 0009` 正確移除兩張 Interaction 表；再 upgrade `0009 -> 0010` 恢復相容。
- ORM／migration／Context／角色純測試：22/22 通過。
- 真實 HTTP checks：27/27 通過，0 失敗。原始結果見 `multiturn-context-http-e2e-raw-20261108.json`。
- HTTP 問答延遲 12 次：min 7.21 ms、median 12.07 ms、p95 57.12 ms、max 121.32 ms；這是本機 Mock，不代表 LINE／正式模型延遲。
- 前端 production API wrapper 對 live isolated API：1/1 通過。
- 完整 Vitest：18 files、221/221 通過；TypeScript 與 Vite build 通過。
- 瀏覽器 UI 自動化因 browser access host unavailable 未能執行；既有 7 項 LIFF component flow 與本次 live API wrapper 合併覆蓋前端送值邏輯，但不冒充手機 LIFF 視覺驗收。

## 8151 若獲授權後的必要變更

以下全部尚未執行，需本人另行明確授權：

1. 從乾淨、固定 commit 建立 UAT artifact；不可從目前有未提交內容的 UAT source 直接部署。
2. 以受控 migration 身分將 UAT 從 `0007` 升級。因 active chain 會先套 `0009_fieldtest_participants` 再套 `0010_service_interactions`，審核範圍包含三張新表及其 indexes。`ltc_uat_app` 無 DDL 權限，不應臨時提升它。
3. 受控替換 8151 API 與對應 UAT Worker 的程式來源，保留 UAT profile、outbound blocked、Web Push off；核對啟動後 PID、application_name、health 與 schema。
4. 重新建置並由 8151 託管本 commit 的 frontend/dist。
5. 唯讀確認測試 Channel webhook endpoint；若仍失敗，先判定 token、網路或 LINE API 回應，不直接改 Webhook。
6. 只有 endpoint 確認需要變更時，才另行核准 LINE 後台修改；本次不建議變更正式 Channel 或正式 Webhook。

### 影響

- 新 caregiver 問答會新增 `service_interactions` row；歷史 QA 保持可讀。
- `interaction_read_grants` 預設沒有分享，未核准不擴大督導／主任讀取。
- API／Worker 短暫切換期間 8151 不可用；8140 不受影響。

### 回復

- 切換失敗：停止新的 UAT 子程序，使用既有精確 PID／execution metadata 回到原 UAT artifact；不得 name-wide stop。
- Schema 尚無 UAT 資料時可 `alembic downgrade 0009_fieldtest_participants` 回復 0010；若已有 Interaction rows，先匯出與人工核准，不可直接 drop。
- 程式回復使用 `git revert`／前一固定 artifact，不 reset、force push 或覆蓋主工作目錄。
- LINE Webhook 若未修改就無需回復；若日後另獲授權修改，先記錄原 endpoint／active 狀態並準備立即復原。

## 判定

- 離線 HTTP 驗收準備：完成。
- 現有 UAT 可否立即供本人 LINE 測試：否。
- 既有「小照 UAT 測試機器人」可否沿用：架構上可沿用既有專用 Channel／LIFF，不需新建官方帳號；但必須先完成上述 UAT schema、artifact、8151 API／Worker／frontend 切換與 webhook 唯讀確認。

