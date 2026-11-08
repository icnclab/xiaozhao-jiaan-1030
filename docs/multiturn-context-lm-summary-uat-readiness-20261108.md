# LM 學習摘要：多輪 Context 內部驗收準備（2026-11-08）

## 新增架構事實

- Interaction ORM 原先沒有 migration；已新增 `0010_service_interactions`，建立 `service_interactions` 與 `interaction_read_grants`，Alembic env 也必須 import `interaction_models`。
- `qa_items.conversation_id` 同時支援舊 standalone UUID 與新 managed Interaction，因此不能加強制 foreign key。
- caregiver 第一題省略 conversation ID 時，後端以第一題 request ID 建立 managed Interaction，但不載入 Context；只有明確續問才載入上一筆遮罩問題。
- 已結束 Interaction 拒絕新的 request，同一 request ID 的既有成功結果仍可安全重送。

## 驗證事實

- 全新 PostgreSQL 完整 migration、0010 downgrade／re-upgrade 均通過。
- 真實 HTTP checks 27/27、前端 live API wrapper 1/1、完整前端 221/221、後端純測試 22/22 通過。
- 本機 Mock HTTP latency：median 12.07 ms、p95 57.12 ms；不可當作 LINE 或正式模型 SLA。
- 沒有啟動 Worker、沒有 LINE 發訊，notification jobs 與 mock outbox 均為 0。

## UAT 現況

- 8151 不是本分支版本；UAT schema 在 0007，缺少兩張 Interaction 表，frontend build 也不同。
- UAT 靜態隔離及 read-only DB 防線通過；LINE webhook 唯讀查詢回 HTTPError，尚未確認後台 endpoint。
- 既有 UAT 測試機器人可作為未來入口，不需新官方帳號，但在 schema／artifact／8151 API、Worker、frontend 受控切換前不能開始本人 LINE 測試。
- 任何 UAT 切換、migration、Worker、Webhook 修改都需本人另行授權；正式 8140 不得變更。

## 隱私

只使用虛構帳號、Mock provider 與臨時資料庫；未包含憑證、LINE userId、真實個案或訪談原文。
