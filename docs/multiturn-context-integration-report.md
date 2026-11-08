# 小照多輪 Context MVP 整合報告

## 整合結果

- 整合分支：`integration/multiturn-context-20261108`
- 原始固定基線：`139887e60ebd9db1cdaea21a0c021931daeb822c`
- Patch SHA-256：`18a8b65828722b74c3450d5938223c3b6288172343d9ad5d71957c46b32d1472`
- 最新核准 GitHub 基線：tag `stable-ready-20261108-approved-branch-sync`，commit `9331dcb8c408d589505b5191fe4f7301566371dc`
- 多輪功能提交：固定基線測試後 rebase 到最新核准 tag；無衝突（完整 SHA 以 `git log` 為準）。
- Patch 原含 11 個檔案，533 additions、19 deletions。沒有新增授權資料模型或 migration。

最新核准 tag 比固定基線多 7 個提交，含健康檢查 API hardening、內部 health token 初始化、UAT 隔離與已審核的 handover / Drive 備份作業。這些提交沒有改動 Patch 的 11 個目標路徑或前端依賴 manifest；已完整保留在整合分支上。其他較新 handover tag 是該核准 tag 的祖先，不是遺漏的後續分支。

## 整合功能與安全邊界

- LIFF 只在明確續問時傳遞 `conversation_id`；新對話不繼承上一段脈絡，切換登入身分時清除前端脈絡。
- 後端 Context 僅查詢同一使用者、同一機構、同一對話的上一筆遮罩問題；不載入答案、案件或逐字稿。
- 問答請求拒絕未定義欄位；個案 Context 停用，不依角色、同機構、案件建立者或客戶端 ID 推定授權。
- 原有高風險攔截與轉督導流程未改；前輪答案不作為證據，引用仍由本輪 RAG 問答產生並限定在本輪 `qa_item_id`。
- 登入、角色權限及核准版本的安全更新皆保留；未更動資料庫 schema、正式設定、Worker、LINE Webhook 或 UAT。

## 測試結果

於固定基線套用 Patch 後完成一輪測試；rebase 到最新核准 tag 後再完成一輪整合驗證：

- 後端純 Mock：`python -m pytest --noconftest -q tests\test_multiturn_context_unit.py`，10 項通過。
- 前端完整 Vitest：17 個測試檔、220 項通過。
- 前端 TypeScript：`npm run build` 的 `tsc --noEmit` 通過。
- Vite production build：成功。
- Git hooks 提交檢查：後端純邏輯檢查、TypeScript 與 220 項 Vitest 通過。
- `git diff --check`、Patch SHA-256 與交付敏感模式掃描通過。

標準 pytest 會載入 conftest 並要求 `.env`；本次使用 `--noconftest` 執行不連資料庫的 Mock 測試。未執行任何正式或 UAT HTTP 驗收。

## GitHub Push 規則與限制

- 只允許推送新分支 `integration/multiturn-context-20261108`；不得合併 main 或 force push。
- Push 前確認遠端同名分支不存在；使用一般 push，遠端若有競爭更新則 push 會拒絕。
- Push 後確認 GitHub 分支 HEAD 等於本地 `git rev-parse HEAD`，並以 GitHub API / `git ls-remote` 核對。
- 正式部署與真人操作驗收均未進行。個案 Context 在授權資料模型及業務規則核准前必須保持停用。

## 回復方案

- 本分支尚未發布時，要回復多輪功能可在整合分支執行 `git revert --no-edit 9e210f8`（以完整 commit SHA 為準）；不重寫或 force push 歷史。
- 若分支已推送，仍以 `git revert` 建立反向提交，再正常 push，保留審核歷史。
- 如尚未提交而僅需回復 Patch，先 `git apply --reverse --check <Patch絕對路徑>`，通過後才 `git apply --reverse <Patch絕對路徑>`。
- 不在原主工作目錄執行回復；不使用 `reset --hard`、`checkout --` 或 `clean`。
