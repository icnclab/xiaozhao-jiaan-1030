# 小照多輪 Context 最終安全整合審核（2026-11-08）

## 結論

- 核准基線 `9331dcb8c408` 上的多輪功能與 GitHub `integration/multiturn-context-20261108` 已核對；遠端 HEAD 為 `7c84d783555f57b4f4ae08e33beda12bd7af9d12`。
- 審核發現一項高優先相容性缺口：`/api/qa/ask` 未呼叫既有 `Interaction` 逐次驗證，已結束的互動仍可能被當作多輪 Context 使用。
- 修正採最小變更：解析 `conversation_id` 後，先呼叫既有 `interaction_routes.validate_ask()`，再進入 `qa_service.ask()`。因此重用原有擁有者、機構、角色、冪等與結束狀態規則，沒有新增權限模型或 migration。
- 未連接正式／UAT 資料庫，未啟動或停止 API、Worker、Webhook，未使用真實個案或付費服務。

## 安全審核

### 多輪 Context 邊界

- 上一題查詢同時限定 `user_id`、`org_id`、`conversation_id`，且只讀取最新一筆 `question_masked`。
- 未知、偽造、他人或跨機構 ID 不回傳存在性細節；查不到上一題時統一失敗。
- 若 ID 對應 `Interaction`，現在會額外驗證擁有者、機構、caregiver 角色與 `ended_at`；已結束互動只允許同一 request ID 的同對話冪等重試，不允許新增追問。
- `client_request_id` 不可跨機構或跨對話重播既有回答。
- 前端只有明確點選「繼續提問」才攜帶 `conversation_id`；新提問與身分切換不延續舊脈絡。

### 個案 Context

- 後端 `AskIn` 使用 `extra="forbid"`，`case_id`、`case_context` 等未定義欄位回 422。
- Context 查詢不 JOIN `cases`，不讀答案、引用、逐字稿或個案欄位。
- 前端不轉送導覽狀態中的個案資料。這是後端 fail closed，不只是隱藏 UI。

### RAG、高風險與角色

- Context 展開後仍進入原 `qa_graph`：先去識別與風險篩選，再檢索、生成、引用與支持度檢查。
- 前輪答案不作證據；引用仍以本輪 `qa_item_id` 儲存與序列化。
- 高風險追問仍被 `screen_risk` 攔截；高風險前題不會被窄化追問拼接而淡化。
- 既有 `make_role_aware` 與轉督導建案流程未修改；角色保護單元測試通過。

## 隔離驗證矩陣

| 項目 | 結果 | 證據 |
|---|---|---|
| 單輪提問 | 通過 | LIFF 測試確認新提問不送 `conversation_id` |
| 同使用者連續追問 | 通過 | 前端續問傳遞、後端 owner/org/conversation scoped 查詢 |
| 新對話重新開始 | 通過 | 新入口與身分切換均清除舊 thread |
| 跨使用者／機構隔離 | 通過 | SQL scope 與 foreign/missing fail-closed Mock |
| 偽造、未知 ID | 通過 | UUID 格式錯誤及查無對話不揭露 404 |
| 已失效 ID | 修正後通過 | 已結束 Interaction 拒絕新追問；同 request 冪等重試保留 |
| 個案 Context 拒絕 | 通過 | Pydantic extra forbid、無 case JOIN、前端不轉送 |
| RAG 來源引用 | 通過 | 引用限定本輪 `qa_item_id`；沿用既有已通過引用整合證據 |
| 高風險／轉督導 | 通過 | 風險拼接 Mock、角色保護 4 項；沿用既有轉督導整合證據 |
| LIFF 文字、語音、轉文字 | 通過 | 7 項多輪前端測試包含三入口 |
| Context 延遲 | 有限通過 | 純文字展開 100,000 次平均 23.621 μs；未量測真實 DB／LINE E2E |

本輪執行結果：後端多輪與角色 Mock 17/17、前端 Vitest 220/220、TypeScript、Vite build、Python compile、`git diff --check` 全部通過。沒有執行正式或 UAT HTTP 驗收。

## Git 歷史與長期版本管理

- 2026-11-08 核對 GitHub `main` 為 `e7bd2923ee8b7b80e6f7badfae087eaeb45f3879`；與整合線 `7c84d783...` 執行 `git merge-base` 無結果，確定沒有共同祖先。
- 不使用 `--allow-unrelated-histories`，不 force push，也不直接修改或合併 main。
- 長期建議：以核准線 `9331dcb8...`／整合分支作為受保護的 canonical release lineage；GitHub 現有獨立 main 保留封存並改名或設唯讀保護。經維護者核准後，以「新 repository 或新 canonical default branch」承接核准線，再用一般 PR／fast-forward／cherry-pick 個別審核提交；不可把兩份根歷史硬合併。
- 每次發版保存基線 tag、來源 commit、檔案 manifest、測試證據與回復 commit，並要求 branch protection、PR review、禁止 force push。

## 回復方案

- 本修正未部署；若要回復，只在修正分支對本次提交執行 `git revert <修正提交>` 並一般 push。
- 若要回復原多輪功能，沿用既有方案：在整合線 revert `9e210f8`，不可 reset、force push 或在主工作目錄覆蓋檔案。
- 修正沒有 schema、設定或資料變更，不需 migration rollback。

## 尚未完成的真實驗收

- 尚未使用真實 LINE／LIFF 測試帳號、隔離測試資料庫與可觀測環境做端到端延遲、重送、網路中斷及 token/session 生命週期驗證。
- 因修正尚未進入供測環境，不應直接把遠端 `integration/multiturn-context-20261108` 視為可開始 LINE 驗收的版本。

