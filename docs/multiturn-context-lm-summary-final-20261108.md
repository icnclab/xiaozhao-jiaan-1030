# LM 學習摘要：多輪 Context 最終安全審核（2026-11-08）

## 應保留的規則

- 多輪只使用同一使用者、同一機構、同一對話的上一筆遮罩問題。
- 若 `conversation_id` 對應 `Interaction`，每次提問都必須套用既有擁有者、機構、角色、冪等與結束狀態驗證；已結束互動不得新增追問。
- 個案 Context 維持後端停用：拒絕 `case_id`／`case_context`，不讀案件、答案、逐字稿或個案資料。
- 前輪內容不是證據；每輪 RAG 引用只能來自該輪檢索並綁定本輪 `qa_item_id`。
- 高風險與轉督導流程必須在 Context 展開後仍執行，不能因追問簡短而降級風險。

## 本次發現與修正

- 發現 `/api/qa/ask` 原本沒有呼叫 `interaction_routes.validate_ask()`，可能讓已結束的 Interaction 繼續新增追問。
- 修正為在進入 `qa_service.ask()` 前先呼叫既有驗證；沒有新增授權規則、資料表或 migration。
- 修正後後端 Mock／角色測試 17 項、前端 220 項、TypeScript、Vite build 與 compile 均通過。

## Git 與驗收限制

- GitHub 整合分支原 HEAD：`7c84d783555f57b4f4ae08e33beda12bd7af9d12`。
- GitHub main：`e7bd2923ee8b7b80e6f7badfae087eaeb45f3879`；兩線無共同祖先，不可用 `--allow-unrelated-histories` 或 force push。
- 本輪沒有正式／UAT HTTP、真實 LINE 或資料庫驗收。部署前仍需在完全隔離的 LINE 測試設定與測試 DB 用虛構資料驗證。

## 隱私

本摘要不含憑證、真實個案或訪談原文；測試只使用 Mock 與虛構資料。

