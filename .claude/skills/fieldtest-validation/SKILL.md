---
name: fieldtest-validation
description: 小照 47 人場測（A01-A40 照服員、S01-S07 居督）編號對應、統計、Excel 匯出與資料最小化驗證。修改 backend/app/api/fieldtest_routes.py、backend/app/static/fieldtest-dashboard.html、backend/migrations/versions/0009_fieldtest_participants.py.draft 時使用；也用於有人問「場測可以開始了嗎」「場測資料會不會洩漏個資」時。
---

# 小照 47 人場測驗證 Skill

## 用途
確保場測儀表板（管理員專用）的帳號名稱查詢、編號對應（A01–A40、S01–S07）、統計、Excel 匯出四個環節都正常運作、都限管理員、都不會洩漏姓名或問答內容，而且在 `fieldtest_participants` 資料表還沒建立時會給清楚的錯誤訊息，不是空白畫面或單純 HTTP 500。

## 啟動條件
- 修改了 `backend/app/api/fieldtest_routes.py`、`backend/app/static/fieldtest-dashboard.html`。
- 修改了 `backend/migrations/versions/0009_fieldtest_participants.py.draft`（或未來任何場測相關 Migration）。
- 有人要求「確認場測可以正式開始」「檢查場測資料有沒有洩漏個資」。

## 執行步驟
1. **後端 Mock 測試（不連資料庫）**：
   ```
   cd backend
   ./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); import test_fieldtest_routes_logic_unit as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('OK')"
   ./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); import test_fieldtest_dashboard_html_consistency_unit as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('OK')"
   ./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); import test_fieldtest_migration_consistency_unit as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('OK')"
   ```
   這些測試會檢查：編號與角色規則（A 開頭限照服員、S 開頭限居督）、管理員限定與跨機構隔離、資料表不存在時回傳清楚的 503（不是裸露的 500）、Excel 只輸出白名單欄位（不含問答內容、個案摘要、真實姓名）。
2. **前端真實 DOM 操作測試（不連資料庫，用 jsdom 實際執行畫面上的 `<script>`）**：
   ```
   cd frontend
   npx vitest run --environment jsdom tests/fieldtest-dashboard-dom.test.ts
   ```
   這一步會真的填表單、按按鈕，確認：47 個空位不會被誤判成「47 人已完成」、查無帳號時訊息清楚、Excel 匯出成功／失敗都有明確畫面反應。
3. **全套前端測試＋型別檢查（確認沒有連帶弄壞其他畫面）**：
   ```
   cd frontend
   npx vitest run --environment jsdom
   npx tsc --noEmit
   ```
4. **若要確認「資料表到底建好了沒」或「Migration 能不能正式套用」**：這一步需要連線資料庫，不屬於本 Skill 可自動執行的範圍，必須明確回報「需要管理者在隔離測試庫核可後驗證」，不可自行連線或執行 Migration。

## 驗證方式
- 以上三個後端測試檔與前端 `fieldtest-dashboard-dom.test.ts` 全部通過。
- `npx tsc --noEmit` 沒有任何錯誤。
- 人工檢查 Excel 匯出的欄位清單，確認沒有 `question_masked`、`summary_masked`、`display_name` 之類會洩漏個資或問答內容的欄位（這點已內建在 `test_fieldtest_routes_logic_unit.py` 的 `test_export_xlsx_columns_contain_no_free_text_or_names` 裡）。

## 停止條件
- `fieldtest_participants` 資料表尚未建立 → 這是已知、仍在等待授權的阻礙，不要假裝已經可以正式場測，也不要自己執行 Migration 建表。
- 測試需要連線資料庫才能完整驗證（例如要親自跑一次「真的對應到一個帳號」）→ 停下來，明確列出「這部分需要資料庫連線＋管理者授權」。
- 發現任何一項測試顯示可能洩漏個資（姓名、問答內容、住址等）→ 立刻停止，回報並視情況直接修正程式（例如白名單漏掉過濾），不要略過繼續宣稱驗證通過。
