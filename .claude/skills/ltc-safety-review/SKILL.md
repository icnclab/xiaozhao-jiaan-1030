---
name: ltc-safety-review
description: 小照（長照 AI 助手）角色權限、個案資料保護與高風險回答審查。修改 backend/app/api/admin_routes.py、backend/app/auth.py、backend/app/api/caregiver_routes.py、任何角色常數（SUP／CASE_OVERSIGHT／GOVERNANCE／STAFF_VIEW／roles.py）或前端 frontend/src/admin/* 的權限顯示邏輯時使用；也用於有人問「這樣改會不會讓不該看的人看到個案」時。
---

# 小照長照安全審查 Skill

## 用途
確保照服員／居督／主任／管理員四種角色，看得到、改得到的範圍跟後端實際授權一致；確保個案資料不會跨機構外洩；確保高風險問題（緊急、用藥、補助金額等）一定轉人工，不由 AI 直接回答。

## 啟動條件
- 修改了角色權限相關程式：`backend/app/api/admin_routes.py`（`SUP`／`CASE_OVERSIGHT`／`GOVERNANCE`／`STAFF_VIEW`）、`backend/app/auth.py`、`backend/app/api/caregiver_routes.py`、`backend/app/services/qa_policy.py`（風險規則）。
- 修改了前端依角色顯示選單／按鈕的邏輯：`frontend/src/admin/AdminApp.tsx`（`navGroupsForRole`、`DIRECTOR_HIDDEN_LINKS`）、`frontend/src/admin/pages/AdminUsersPage.tsx`。
- 有人要求「確認權限沒有被不小心放大」「確認跨機構不會看到別人的資料」。

## 執行步驟
1. **先列出這次改動實際影響哪些角色、哪些端點**：`git diff` 相關檔案，比對後端角色常數與前端選單隱藏清單是否一致（例如：後端只給主任唯讀的案件監督、治理指標、人員查看，前端就不該出現「發布文件」「刪除帳號」的按鈕給主任）。
2. **前端角色測試（不連資料庫，用 Mock API）**：
   ```
   cd frontend
   npx vitest run --environment jsdom tests/admin-director-home.test.tsx
   npx vitest run --environment jsdom tests/admin-users.test.tsx
   npx vitest run --environment jsdom tests/admin-case-detail-events.test.tsx
   ```
3. **後端權限邏輯（純邏輯／Mock，不連資料庫）**：若有新增的 Mock 測試檔（例如 `backend/tests/test_fieldtest_routes_logic_unit.py` 裡的 `test_lookup_user_requires_admin_role_before_any_db_access`、`test_lookup_user_query_is_scoped_to_caller_org_not_just_username` 這類「非該角色就該被拒絕」「不同機構查不到對方資料」的測試），用直接 import 方式執行：
   ```
   cd backend
   ./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); import <對應測試檔> as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('OK')"
   ```
4. **高風險規則檢查（純邏輯）**：確認 `backend/app/services/qa_policy.py` 的 `RISK_RULES`／`_RISK_VARIANTS` 是否會正確攔截緊急、用藥、補助金額等問題，可用既有的 `test_care_record_retention_unit.py` 裡針對 `qa_policy` 的測試作為範例延伸。
5. **若需要真實資料庫才能完整驗證**（例如實際用虛構帳號登入測試跨機構存取），明確記錄這一步「需要資料庫連線＋授權」，不要自己連線；若之前的回合已經用隔離測試環境驗證過（例如 `ltc_demo` 的示範帳號），可以引用那次的結論，但要註明是哪一輪、用什麼帳號。

## 驗證方式
- 前端測試全部顯示 `passed`，沒有角色相關斷言失敗。
- Mock 測試確認：非授權角色呼叫會被拒絕（403）、跨機構查詢查不到別人的資料（404 或空結果），且這些判斷發生在任何資料庫寫入之前（`db.execute`／`db.commit` 沒被呼叫）。

## 停止條件
- 發現前端選單跟後端權限不一致（例如前端顯示了後端會 403 的按鈕）→ 直接回報並修正前端，不要自行放寬後端權限去配合前端。
- 需要放寬某個角色的權限才能讓功能動起來 → 停下來，列出需要授權的具體範圍，交由管理者／蔡老師決定，不自行擴大權限。
- 需要用真實個案資料才能驗證 → 停下來，只能用虛構／示範資料驗證。
