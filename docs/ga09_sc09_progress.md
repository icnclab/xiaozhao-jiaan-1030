# GA09／SC09 服務紀錄表單 — 進度紀錄（2026-11-01）

> 本檔僅記錄本次「草稿填寫通用架構」批次的程式與測試現況，不代表正式上線或真人驗收結果。
> 與 `C:\aa\XiaoZhao_Jiaan1030_GitHub_Ready\WORK_STATUS_1101.txt` 互補，該檔案為跨議題總進度，本檔僅聚焦 GA09/SC09。

## 第六輪更新（2026-11-02）— 照服員快速分類回報（性騷擾／不當觸碰、暴力／人身安全、跌倒、傷口／異常狀況）

依 10/30 嘉安訪談第六輪要求，新增四類人身安全快速分類回報，沿用現有 `ReportEntryPage`、`ReportPreviewPage`、`reportScenarios`、`reportSubmission` 架構，不新增頁面、不改動 BA 22 項與既有 8 個問題分類。

**設計決策（已與使用者確認，非自行擴充）**：
- 四類一律先建立一般案件（沿用既有 `POST /api/cases` 流程），使用者可另外勾選「同時標記為緊急」，確認後才額外呼叫既有 `POST /api/jiaan1030/emergencies`；不勾選則完全不呼叫該端點。
- 發現 `jiaan1030_emergency_routes.py` 的緊急分類代碼僅有 `fall/violence/injury/unresponsive/traffic/self_harm/other`，**沒有「性騷擾／不當觸碰」專屬代碼**；已請示使用者，確認暫對應到 `other`（記錄於 `reportScenarios.ts` 的 `SAFETY_EMERGENCY_CATEGORY`），未自行新增分類代碼或資料庫欄位。
- **發現既有缺口（本輪未處理，僅記錄）**：`jiaan1030_emergencies`／`jiaan1030_emergency_events` 兩張表完全沒有對應的 migration 檔案（`backend/migrations/versions/` 只到 `0005`），`backend/tests/` 也沒有任何測試涵蓋這兩張表；但 `main.py` 已掛載其路由、CLAUDE.md 記錄「角色安全提示與網頁緊急通報已在正式環境部署」。代表正式環境的這兩張表（如果存在）可能是透過本專案 migration 鏈以外的方式建立。本輪**完全未新增 migration、未連線任何資料庫**，僅由前端呼叫既有已存在的 API 路徑；若未來要在 `ltc_test`／CI 對此端點加後端測試，需先確認正式環境實際表結構，補上對應 migration。

**新增/修改檔案**：
- `frontend/src/liff/reportScenarios.ts`：`REPORT_MODES` 新增 `人身安全事件`；新增 `SAFETY_EVENT`（四類文字與參考來源）與 `SAFETY_EMERGENCY_CATEGORY`（分類→既有緊急代碼對應表）；`RECEIVING_CATEGORIES` 新增 `人身安全事件: ['事件處理規範']`（沿用 `backend/scripts/seed_demo.py` 既有示範分類名稱，未自行發明；若機構實際無此分類，既有 fail-closed 設計會擋下送出並提示聯絡居督，不會誤投其他分類）。
- `frontend/src/liff/reportSubmission.ts`：新增 `buildEmergencyPayload()`，將選定分類與一組獨立的 `client_request_id`（與案件送出的請求識別碼分離，各自冪等）組成緊急通報payload；分類不在四類白名單內一律擲錯，不做任何猜測。
- `frontend/src/liff/pages/ReportPreviewPage.tsx`：`details` 階段於選定分類後顯示「同時標記為緊急」勾選框與頻率提醒（沿用既有「僅網頁主動開啟時顯示，非背景推播」措辭）；`preview` 階段顯示目前是否標記緊急的摘要，仍需按「確認送出回報」才會送出；送出後才呼叫緊急 API，緊急通報失敗不影響已建立的一般案件，但會明確提示未確認送出、請改用機構既有方式通知督導；切換分類會重置勾選狀態，避免誤帶到不同分類的緊急標記。

**新增測試**：`frontend/tests/report-safety-event.test.tsx`（7 項，全數通過）涵蓋：四類分類正確顯示且無混入其他情境；不勾選只建立一般案件、完全不呼叫緊急端點；勾選並確認後才呼叫緊急端點且分類對應正確；四類對應既有緊急代碼（含性騷擾對應 `other` 的明確驗證）；切換分類重置勾選；緊急通報失敗時明確告知且不誤報成功，一般案件仍視為已建立；`buildEmergencyPayload` 對未知分類擲錯。

**測試結果（本輪實際執行，未重跑既有 191/181 項）**：
- 前端 `npx vitest run --environment jsdom tests/report-safety-event.test.tsx tests/report-click.test.tsx`：**57 passed**（新增 7 項 + 既有 `report-click.test.tsx` 50 項皆通過，確認未造成既有回報流程回歸）。
- 前端 `tsc --noEmit`：通過，無錯誤。
- 前端 `npm run build`：成功。
- 後端：本輪未修改任何後端程式或資料庫，未執行後端測試。

**未觸及正式環境**：本輪未連線 `ltc_clean`、未部署、未重啟正式 API、未 `git add`、未 commit、未 push；新增的緊急通報呼叫僅在前端 vitest 以 mock fetch 驗證，從未對任何真實後端或資料庫發送請求。

**尚未完成、不可宣稱已完成**：
- 四類分類本身（文字、是否齊全、是否還需要其他類型）、受理分類名稱 `事件處理規範` 是否確為嘉安正式環境實際分類、緊急標記是否真的要對應到既有 `other` 代碼，皆待嘉安／督導確認，目前僅是依訪談需求與使用者本輪確認所做的最小實作。
- `jiaan1030_emergencies`／`jiaan1030_emergency_events` 缺少 migration 與測試覆蓋的既有缺口未修復；若正式環境此表結構與本專案假設不同，本輪新增的緊急通報呼叫在真實環境可能需要調整。
- 真人登入操作驗收（照服員實際勾選緊急並送出、督導實際看到通知）未進行，僅完成程式與離線測試。

## 第五輪更新（2026-11-01）— GA09／SC09 正式表單欄位草稿版

依 10/30 嘉安訪談補充紀錄，建立 GA09／SC09 共用表單的欄位規格草稿，並驗證 LIFF 動態表單可正確渲染。

**已確認、納入草稿的欄位（僅這 5 類，不多不少）**：服務類型（GA09／SC09）、服務日期、服務時間、服務內容、簽章欄位。定義於新模組 [jiaan1030_ga09_sc09_fields.py](../backend/app/services/jiaan1030_ga09_sc09_fields.py) 的 `ga09_sc09_draft_fields()`，格式完全沿用既有 `fields_json` schema（`{version, sections:[{key,label,fields:[{key,label,type,required,options,max_length}]}]}`），**未新增任何 DynamicForm 不支援的欄位型別**，確認相容後才採用：
- `service_type`：`select`，選項 `["GA09","SC09"]`。
- `service_date`：`date`。
- `service_time`：`text`（起訖時間或時段的實際格式未確認，暫用文字輸入，避免新增 DynamicForm 尚未支援的 `time` 型別）。
- `service_content`：`textarea`。
- `signature`：沿用既有 `signature_placeholder`（只佔位、不收集簽章資料，本來就是為這種情境設計的既有型別）。

**尚未確認、本輪刻意未編造的部分**（全部保留 `required: False` 保守預設，列在模組的 `UNCONFIRMED_FIELDS`）：
1. 各欄位是否必填。
2. 服務時間的實際輸入格式（起訖時間／時段／純文字）。
3. 服務內容欄位的字數上限（暫訂 2000 字僅為保守佔位值，非確認值）。
4. 簽章欄位的簽署流程、載具與法規要求。
5. 服務類型下拉選項是否需顯示中文全名（目前僅用 GA09／SC09 代碼）。

**可回復、不覆蓋已核准內容的套用機制**：新增 `apply_draft_fields(db, form_code, fields_json)`，套用前檢查該表單 `schema_status`，若已是 `'approved'` 一律拒絕覆蓋（回傳 `'skipped_approved'`，不做任何寫入）；否則才更新 `fields_json`，不動 `reviewed`/`schema_status`，由呼叫端自行 commit/rollback。新測試 `test_apply_draft_fields_refuses_to_overwrite_approved_form` 直接驗證：對已核准表單套用，資料庫內容完全不變。

**完全沒有呼叫核准 API**：本輪沒有任何地方把 `reviewed` 或 `schema_status` 設為 `True`/`'approved'`；所有新測試建立的表單皆維持 `draft_unverified`/`reviewed=FALSE`。

**LIFF 驗證**：新增前端測試 [dynamic-form-ga09-sc09.test.tsx](../frontend/tests/dynamic-form-ga09-sc09.test.tsx)，直接用與後端模組鏡射的欄位結構渲染 `DynamicForm`，驗證 5 個欄位各自渲染正確元件（下拉含 GA09/SC09 選項、日期輸入、文字輸入、多行文字、簽章佔位提示），確認沒有欄位被標為必填，`onChange` 正確回傳合併後的 payload，`disabled` 時所有輸入正確鎖定。

**整合驗證**：新增 `test_draft_with_real_ga09_fields_still_blocked_from_submit`，用真實欄位鍵（`service_type`/`service_date`/`service_time`/`service_content`）填入假資料草稿，確認即使欄位內容已是這份草稿規格、送出仍被 409 擋下（表單仍未核准）。另有 `test_review_catalog_exposes_draft_fields_but_stays_unreviewed` 驗證：主任可在 `/service-catalog/review` 看到草稿欄位內容以供審核，但一般照服員走 `/service-catalog`（僅回 `reviewed=TRUE`）看不到這份未核准的草稿表單。

**測試結果**：後端新增 6 項（`test_jiaan1030_ga09_sc09_fields.py`）、前端新增 4 項，皆未重跑第四輪已通過的 19 項授權測試。後端 `pytest` 總計 **191 passed, 1 failed**（同前幾輪定位的 `test_qa_flow.py`，未處理）；前端 `vitest` 總計 **181 passed, 1 failed**（同前幾輪定位的 `admin-cases.test.tsx`，未處理）；`tsc --noEmit` 通過；`npm run build` 成功。

**未觸及正式環境**：本輪完全未呼叫 `jiaan1030_prod_migration_readonly_check.py`、未連線 `ltc_clean`；`apply_draft_fields()` 僅在 `tests/test_jiaan1030_ga09_sc09_fields.py` 內對 `ltc_test` 呼叫過，從未對任何其他資料庫執行。

## 第四輪更新（2026-11-01）— 跨居督共用照服員：明確、可撤銷的照服員個案授權

依 10/30 嘉安訪談需求，補足「共用照服員」情境：一位照服員可能服務跨居督分組的個案，第三輪的授權機制僅支援督導/主任/admin 唯讀，本輪擴充為**照服員也可被明確授權**。

- **無需新 migration**：`jiaan1030_service_client_grants` 的 `grantee_id` 本來就只是 `users.id` 外鍵，沒有角色層級的 DB 限制（角色限制原本只存在於應用層程式碼），所以本輪純屬應用層邏輯調整，資料庫結構不變，`ltc_test` 沿用第三輪的 migration 鏈（`0003`→`0004_jiaan1030_clients`→`0005_jiaan1030_drafts`），未重跑。
- **存取政策（角色決定授權後能做什麼，而非能不能看）**：
  - 建立者：讀寫不變。
  - 被授權的**照服員**：可唯讀個案＋可建立「自己的」服務草稿（新函式 `_can_create_draft_for_client`，區分「看得到」與「能寫」）。
  - 被授權的**督導/主任/admin**：僅唯讀，即使有有效授權仍**不可**建立/修改/送出草稿（新測試 `test_granted_supervisor_cannot_create_draft_even_with_valid_grant` 驗證，並確認有寫入 `jiaan1030_draft.forbidden` 稽核）。
  - 任何角色都**不可修改或送出其他人建立的草稿**，即使雙方都被授權存取同一個案（新測試 `test_caregiver_cannot_edit_or_submit_other_caregivers_draft_even_with_grant` 驗證：被授權照服員可以「看到」同個案下其他照服員的草稿列表，但 PATCH/submit 仍回 403）。
  - 授權/撤銷：僅建立者或主任/admin 可操作（不變）；新增防呆——不可對建立者本人重複授權（`grantee_id == client.created_by` → 400）、被授權人須為同機構現職使用者（`is_active` 檢查）。
- **稽核**：授權/撤銷/拒絕存取/草稿操作皆沿用既有 `audit.record`，新增 `jiaan1030_draft.forbidden`（`target_type="jiaan1030_service_client"`）記錄「有唯讀授權但嘗試建立草稿被擋」的情境；所有 meta 仍只放 ID 與動作代碼，不含個案代稱或填寫內容。
- **名冊對應（第 5 項要求）**：`jiaan1030_service_clients.display_label` 目前仍只是照服員自訂的假代稱字串，**沒有、也沒有新增**任何與嘉安既有長者名冊的自動比對/匹配邏輯。若日後要串接嘉安名冊，需要嘉安提供可驗證的對應鍵（例如政府個案編號），在那之前此對應關係**維持待確認狀態**，本輪未做任何假設性串接。
- **LIFF 修改**：`ServiceClientsPage.tsx` 新增「授權存取／撤銷授權」的最小化測試用輸入（直接輸入 User ID，因開發測試階段無人員查詢 API，不做真人姓名搜尋/選擇 UI）；僅對自己建立的個案顯示授權操作入口。
- **測試**：新增 5 項（`test_granted_caregiver_can_read_client_and_create_own_draft`、`test_caregiver_cannot_edit_or_submit_other_caregivers_draft_even_with_grant`、`test_granted_supervisor_cannot_create_draft_even_with_valid_grant`、`test_revoked_caregiver_grant_blocks_further_access_and_new_drafts`、`test_grantee_cannot_be_the_creator_themself`），原 14 項全數維持通過，GA09/SC09 專屬測試共 **19 項**。為了讓第二位照服員（`cg2`，原世界設定未綁定 LINE）能實際登入測試跨居督共用情境，測試新增 `_bind_line()` 輔助函式，僅在測試資料庫建立假的 LINE 綁定紀錄，不涉及真實帳號或正式環境。
- **離線測試結果**：後端 `pytest` **185 passed, 1 failed**（失敗項同前三輪定位的 `test_qa_flow.py`，與本批次無關，未處理，未修改測試或緊急安全文字）；前端 `vitest` **177 passed, 1 failed**（失敗項同前三輪定位的 `admin-cases.test.tsx`，與本批次無關，未處理）；`tsc --noEmit` 通過；`npm run build` 成功。

## 第三輪更新（2026-11-01）— 業務決策落實：改用獨立服務個案主檔

**業務決策（已採納，非本程式自行決定）**：第二輪審查指出 `cases` 是問題回報工單、不是服務個案，第三輪依此決策**不再**讓草稿強制綁定 `cases.id`。

- 全專案確認無可重用的受照顧者/服務個案主檔後，新增最小化獨立實體：
  - `jiaan1030_service_clients`（服務個案主檔：`org_id`、`created_by`、`display_label`——僅供假資料代稱，不存真實姓名/房號）。
  - `jiaan1030_service_client_grants`（明確授權：`service_client_id`、`grantee_id`、`granted_by`、`revoked_at`）。
- 存取政策（保守預設，無明確規則前）：**建立者可讀寫；督導/主任/admin 須「同機構」且有「未撤銷的明確授權」才可唯讀**；兩者皆不滿足一律視為不存在（404，不洩漏存在性）。這比第二輪草稿的「同機構即可讀」更嚴格。
- 草稿表 `jiaan1030_service_form_drafts` 的 `case_id` 欄位改為 `service_client_id`（FK 改指向新表）；因原 migration 從未套用到正式庫（第二輪唯讀檢查已確認 `ltc_clean` 無此表），**直接修改尚未套用的 migration 內容**並重新編號（`0004_jiaan1030_clients` → `0005_jiaan1030_drafts`），未在正式庫留下需要回溯修補的記錄。
- 新增 API：`POST/GET /api/jiaan1030/service-clients`、`POST /api/jiaan1030/service-clients/{id}/grants`、`POST /api/jiaan1030/service-clients/{id}/grants/{grantee_id}/revoke`。
- 雙旗標核准機制、稽核、`client_request_id` 冪等、送出前 `reviewed`+`schema_status` 雙重檢查、併發防重複送出，**全部原樣保留**，未放寬。
- 前端：移除第二輪在 `CaseDetailPage.tsx` 加的 GA09/SC09 入口（語意已不適用），新增獨立頁面 `ServiceClientsPage.tsx`（建立/列出可存取的服務個案，假資料代稱輸入），`HomePage.tsx` 新增入口連結；`ServiceFormPage.tsx` 路由參數改為 `serviceClientId`。
- 測試由 11 項擴充為 **14 項**，新增：無授權督導看不到草稿/個案（保守預設驗證）、有效授權督導可唯讀但不可寫、撤銷授權後立即失去存取、督導不可自行授權（僅建立者或主任/admin 可授權）、授權對象跨機構應被拒絕。
- 本機測試資料庫 `ltc_test` 已重新套用新編號的 migration 鏈（`0003`→`0004_jiaan1030_clients`→`0005_jiaan1030_drafts`），驗證通過；**完全未觸碰 `ltc_clean`**。
- 離線測試結果：後端 `pytest` **180 passed, 1 failed**（失敗項同第二輪定位的 `test_qa_flow.py`，與本批次無關，未處理）；前端 `vitest` **177 passed, 1 failed**（失敗項同第二輪定位的 `admin-cases.test.tsx`，與本批次無關，未處理）；`tsc --noEmit` 通過；`npm run build` 成功。

## 部署前審查結論（2026-11-01 第二輪，仍適用，`case_id` 項已由第三輪落實修正）— GO / NO-GO

| 項目 | 結論 | 說明 |
|---|---|---|
| migration 0003/0004 對正式庫（ltc_clean）相容性 | **GO** | 唯讀檢查確認：`alembic_version` 已在 `0002_quality_feedback`，`rag_quality`/`jiaan1030_service_forms`/`jiaan1030_ba_services` 現況與遷移假設一致，`jiaan1030_service_form_drafts` 尚不存在、可安全建立。無需任何資料轉換。 |
| 未核准表單無法正式提交（前後端） | **GO** | 後端 409 擋下、前端禁用送出鈕，兩層皆已離線測試驗證。 |
| 本批程式安全與回歸（組織隔離/角色權限/稽核/重複送出/前端錯誤處理） | **GO**（本輪已補強並重測） | 詳見下方「本次新增的安全性檢查與修補」。 |
| **草稿綁定 `case_id` 是否符合嘉安業務語意** | **已解決（第三輪）** | 已依業務決策改用獨立的 `jiaan1030_service_clients` 主檔（`service_client_id`），不再綁定 `cases.id`。詳見上方「第三輪更新」。 |
| 兩項既有失敗測試是否影響本批部署 | **GO（不阻擋 GA09/SC09，但各自需獨立處理）** | 兩者皆與 GA09/SC09 程式碼無相依，詳見下方定位說明；若要部署「包含這兩個檔案」的整支分支，仍需分別排除風險。 |

**整體建議：GA09/SC09 草稿架構的程式、遷移與安全性可視為技術就緒（GO）；但在嘉安確認「草稿應綁定什麼實體」之前，不建議把此功能接到正式案件流程或開放照服員大量使用（NO-GO on 業務綁定，不是 NO-GO on 程式品質）。**

## 1. `cases` 表語意與 `case_id` 綁定檢查（唯讀，未更動正式流程）

- 程式碼證據：`backend/app/models.py` 的 `Case` model docstring 為「督導待確認案件」；欄位組合（`source: ai_escalation|manual_escalation|quick_report`、`qa_item_id`、`reason`、`assignee_id`、`summary_masked`）全部指向「照服員問題回報 → AI 轉人工或手動建案 → 督導接手回覆」的工單流程，不含任何「受照顧者/長輩」身分欄位。
- 正式資料庫唯讀複核（`SET TRANSACTION READ ONLY`，只查 `information_schema`，無 `SELECT *`、無個資內容、執行後 `ROLLBACK`，詳見 [jiaan1030_prod_migration_readonly_check.py](../backend/checks/jiaan1030_prod_migration_readonly_check.py)）：`CASES_TABLE_COLUMNS` 與上述語意完全一致，確認 `cases` 在正式庫裡就是問題回報工單，不是服務個案表。
- 全專案搜尋確認：目前系統**沒有**任何獨立的「受照顧者／服務對象／個案」實體表；`個案`、`長輩`、`住民` 等詞只出現在去識別化（`deid.py`）與問答政策文字中，是「遮罩後的文字標記」，不是結構化資料實體。
- **結論**：目前草稿表把 GA09/SC09 服務紀錄綁定到 `cases.id`，實質上是「把服務紀錄掛在一張問題回報工單上」。這在技術上可行（本批 11 項測試已驗證跨機構/權限/稽核皆正確），但**業務語意不自然**：一筆喘息服務紀錄理應對應「某位受照顧者的某次服務」，而不是「某張待確認工單」。
- **修正方案（僅供決策，本輪未執行）**：
  1. **新增專屬「服務個案/受照顧者」實體**（例如 `service_recipients` 或沿用嘉安現有紙本個案編號），草稿改綁定此實體而非 `cases`；需要嘉安提供目前紙本/系統如何識別服務對象（有無既有編號）。
  2. **短期過渡方案**：若嘉安目前確實用「建立一張工單」來代表一次服務聯繫（例如先用 `quick_report` 建案登記這次服務），可保留現況但在 UI/文件上明確標示「此處的案件編號僅為系統內部工單，非正式服務紀錄編號」（目前 `CaseDetailPage.tsx` 已有類似提示文字："此編號不是政府個案案號，也不是服務歷程編號"，可延用同一原則）。
  3. 無論採用哪個方案，**都需要嘉安業務端確認**，不應由本批次自行決定並更動正式綁定關係。

## 2. Migration 0003／0004 對正式資料庫相容性（唯讀檢查，未執行正式 migration）

執行 [jiaan1030_prod_migration_readonly_check.py](../backend/checks/jiaan1030_prod_migration_readonly_check.py)（`SET TRANSACTION READ ONLY` + 只查結構/聚合統計 + 結束一律 `ROLLBACK`，全程無 COMMIT、無 CREATE/ALTER/INSERT/UPDATE/DELETE）對正式庫 `ltc_clean` 的唯讀檢查結果：

- `alembic_version` 目前為 `0002_quality_feedback`：與本機測試庫起點一致，`0003`→`0004` 是正常的下一步，不會重跑 `0001`/`0002`。
- `rag_quality` schema 已存在，且 `alembic_version` 已達 `0002`，兩者一致，**不是**衝突風險。
- `jiaan1030_service_forms` 現有欄位 `code, title, fields_json, reviewed` 與 migration 0003 假設完全一致；`title`/`fields_json`/`reviewed` 均無 NULL（2 筆資料），`ADD COLUMN IF NOT EXISTS schema_status ... DEFAULT 'draft_unverified'` 可安全套用、不會違反既有資料。
- `jiaan1030_ba_services` 現有 22 筆、欄位 `slot, code, name, reviewed` 與假設一致。
- `jiaan1030_service_form_drafts`（0004 新表）**尚不存在**於正式庫，套用時不會有物件衝突。
- 唯一提醒：正式庫 `jiaan1030_service_forms.code` 實際宣告長度為 `VARCHAR(4)`，本批 migration 0004 的 FK 欄位用 `VARCHAR(20)`（較寬鬆的父子型別，PostgreSQL 允許不同長度的 varchar 建立外鍵），**相容、非阻擋項**，但提醒未來若 BA/GA/SC 代碼規則改變超過 4 字元，需同時檢查 `jiaan1030_service_forms.code` 本身的欄位長度上限。
- rollback 安全性：0003 的 `downgrade()` 刻意 `raise NotImplementedError`（禁止自動刪除正式資料）；0004 的 `downgrade()` 僅 `DROP` 目前正式庫中**不存在**的新表，若未來已有草稿資料，rollback 前需人工評估是否接受刪除草稿資料。
- 重跑安全性：本機測試庫已驗證 `alembic upgrade head` 執行兩次，第二次完全無動作（冪等）；0003 內部亦用 `CREATE TABLE IF NOT EXISTS`／`ADD COLUMN IF NOT EXISTS`／條件式 `DO $$...$$` 檢查 constraint 是否存在，額外保護「手動重跑 SQL」情境。

**本項結論：技術上可安全套用到正式庫，無相容性阻擋項；唯一懸而未決的是上方第 1 點的業務語意問題，與 migration 本身無關。**

## 已完成（程式已製作 + 離線測試通過，尚未碰正式資料庫、未部署、未 push）

### 後端
- Migration `0003_jiaan1030_catalog_schema`：補齊既有 `jiaan1030_service_forms`/`jiaan1030_ba_services` 版控，新增 `schema_status` 欄位；`downgrade()` 刻意不可逆（raise `NotImplementedError`），避免誤刪正式資料。
- Migration `0004_jiaan1030_drafts`：新增 `jiaan1030_service_form_drafts` 草稿表（全新表，可安全 downgrade）。
- ORM model [jiaan1030_draft_models.py](../backend/app/jiaan1030_draft_models.py)、集中角色常數 [roles.py](../backend/app/roles.py)。
- API [jiaan1030_service_drafts.py](../backend/app/api/jiaan1030_service_drafts.py)：
  - `POST /api/jiaan1030/service-drafts`（建立草稿，`client_request_id` 冪等）
  - `PATCH /api/jiaan1030/service-drafts/{id}`（僅建立者本人、僅 `status=draft` 時可改）
  - `POST /api/jiaan1030/service-drafts/{id}/submit`（未核准表單一律 409 擋下；已送出的重複呼叫為冪等，不重複寫稽核）
  - `GET /api/jiaan1030/service-drafts`（照服員看自己的；督導/主任/admin 看同機構全部）
  - `POST /api/jiaan1030/service-forms/{code}/approve`（僅主任/admin；`reviewed=TRUE` 前置條件為 `schema_status='approved'`）
  - 每個動作皆呼叫既有 `app/services/audit.py` 寫入稽核，meta 只放代碼與狀態轉換，不含填寫內容。
- 既有唯讀 `/api/jiaan1030/service-catalog`、`/review` 回應補上 `schema_status` 欄位（供主任審核參考）。

### 前端（LIFF）
- [DynamicForm.tsx](../frontend/src/liff/components/DynamicForm.tsx)：依 `fields_json` schema 動態渲染文字/下拉/單選/核取/日期/數字欄位；簽章欄位僅佔位，不收集簽章資料。
- [ServiceFormPage.tsx](../frontend/src/liff/pages/ServiceFormPage.tsx)：建立草稿、debounce 自動存檔、未核准表單禁用送出鈕並顯示提示文字。
- 路由：`/liff/cases/:caseId/service-forms/:code`（已加入 `main.tsx`）。
- **入口連結已完成**：[CaseDetailPage.tsx](../frontend/src/liff/pages/CaseDetailPage.tsx) 新增「服務紀錄表單」區塊，**只列出 `reviewed=TRUE` 的表單**；目前正式環境 GA09/SC09 皆未核准，所以案件詳情頁會顯示「目前尚無已核准的服務紀錄表單」，刻意不讓照服員從此入口進入未核准表單的正式流程（測試填寫仍可透過直接網址進入 ServiceFormPage，該頁本身仍會擋下未核准表單的送出）。

## 本次新增的安全性檢查與修補（第一輪，已於第二輪重新驗證仍通過）

複查 diff 時發現並修正：
1. **稽核缺口**：非建立者嘗試修改/送出他人草稿時（403），原先未寫稽核；已補上 `jiaan1030_draft.forbidden`（outcome=denied）。跨機構存取仍走既有 `deny_not_found`（404 + `access_denied` 稽核），不洩漏資源是否存在。
2. **重複送出競態**：`submit` 原先是「讀取→判斷→寫入」三步，併發重送可能造成重複稽核紀錄；改為條件式 `UPDATE ... WHERE status='draft'`，0 列更新時直接回傳目前狀態，不重複寫稽核、不報錯。
3. **前端防禦性修補**：`CaseDetailPage` 新增的服務表單清單若 API 回應缺少 `service_forms` 欄位會導致畫面崩潰（由既有 vitest 測試 `case-waiting.test.tsx` 的通用 mock 觸發），已改為 `Array.isArray` 防禦性檢查。

## 第二輪新增的安全與回歸檢查（本次任務，均已重新跑測試確認）

1. **組織隔離**：複查 `_visible_draft`、`create_draft`、`list_drafts` 的 org_id 過濾邏輯，確認照服員只能存取自己建立的草稿、督導/主任/admin 僅能存取同機構草稿，無法跨機構讀取或寫入；由 `test_cross_org_draft_update_and_submit_return_404_not_403`、`test_cross_org_draft_not_visible` 驗證（含確認跨機構一律回 404 而非 403，不洩漏資源存在性）。
2. **角色權限**：複查 `require_roles`/`roles.py` 常數使用，確認督導不可呼叫核准 API（僅主任/admin），照服員不可呼叫核准 API，照服員不可替同機構其他照服員建立的案件建立草稿（避免冒用他人案件，新增 `test_caregiver_cannot_create_draft_on_another_caregivers_case_same_org`）。
3. **稽核內容**：複查所有 `audit.record` 呼叫的 `meta`，確認只含 `form_code`/`draft_id`/`status_from`/`status_to` 等代碼與狀態轉換，不含 `payload_json` 填寫內容或任何個資文字；核准動作的 meta 同樣只含代碼。
4. **重複送出**：複查已送出草稿重複呼叫 `submit` 的行為，確認回傳同一筆已送出結果、且稽核紀錄不重複寫入（`test_submitted_draft_submit_again_is_idempotent_no_duplicate_audit`）。已知殘留風險（非新增、與既有 `cases.py` 建案邏輯同構）：`create_draft` 的「查詢既有 client_request_id → 不存在才新增」屬於檢查後寫入（check-then-insert），理論上併發重送仍有極小機率觸發資料庫唯一鍵衝突；此為專案既有慣例（`cases.py` 的建案邏輯也是同樣模式），非本批次引入的新風險，暫不列為阻擋項。
5. **前端錯誤處理**：複查 `ServiceFormPage.tsx` 建立草稿失敗時的畫面狀態，原先會同時顯示錯誤訊息與「建立草稿中…」造成混淆，已修正為有錯誤時不再顯示「建立草稿中…」。

新增測試（[test_jiaan1030_service_drafts.py](../backend/tests/test_jiaan1030_service_drafts.py)，共 11 項，皆通過）涵蓋：
- 建立/更新/送出完整流程、未核准擋送出、核准後可送出。
- `client_request_id` 建立草稿冪等。
- 照服員不可呼叫核准 API（403）；**督導不可呼叫核准 API**（403，僅主任/admin）。
- 照服員不可修改他人草稿（同機構跨照服員、跨機構皆測）。
- 跨機構：草稿不可見、PATCH/submit 回 404（非 403，不洩漏存在性），且確實寫入 `access_denied` 稽核。
- **同機構照服員不可替他人建立的案件建立草稿**（避免冒用他人案件）。
- 已送出草稿重複呼叫 submit：冪等回應、稽核不重複。
- 主任不可跳過 `schema_status=approved` 直接核准 `reviewed=TRUE`。

## 離線測試結果（真實執行紀錄，非摘要臆測）

- 本機測試資料庫（`ltc_test`，已確認與正式庫 `ltc_clean`為不同資料庫）執行 `alembic upgrade head`：成功，重跑一次確認冪等。
- 後端 `pytest`（全專案）：**177 passed, 1 failed**。
- 前端 `npm run test`（vitest）：**177 passed, 1 failed**。
- 前端 `tsc --noEmit`：通過，無錯誤。
- 前端 `npm run build`：成功。

## 兩項既有失敗測試的定位與部署風險評估（本輪新增，未修改任何測試或安全規則）

### (a) `backend/tests/test_qa_flow.py::test_emergency_note_is_fixed_guidance`
- **根因已精確定位**：測試預期緊急情境回答文字包含固定字串「緊急應變程序」（來源常數 `app/services/qa_service.py:25` 的 `EMERGENCY_NOTE`）。但實際回傳文字已被 `backend/app/services/jiaan1030_role_guard.py`（`make_role_aware()`，本次 GA09/SC09 任務**之前**就已存在的未提交檔案，與本批草稿功能無程式相依）依角色改寫成「請先依機構SOP通報並聯絡119（消防）或110（警察）…」等語句，不再包含原字串，故斷言失敗。**不是終端編碼問題，是訊息內容本身已被改寫。**
- **與 GA09/SC09 本批次的關係**：無程式相依（`jiaan1030_service_drafts.py`、`jiaan1030_draft_models.py` 等本批檔案都沒有 import `jiaan1030_role_guard.py`），不會因為部署 GA09/SC09 草稿功能而受影響，也不會因此被觸發。
- **部署風險評估**：**若連同 `jiaan1030_role_guard.py` 一起部署，風險中高**——這代表緊急狀況回覆的「固定語句」已被改成角色相關的動態文字，且現有安全性測試並未更新為新預期值，等於緊急訊息的實際行為已偏離目前驗證過的版本。建議在部署含該檔案的變更前，由負責緊急處置流程的人確認新文字是否符合安全要求，再更新測試斷言，而不是反過來放寬或刪除測試。**本批次未修改此檔案或測試。**

### (b) `frontend/tests/admin-cases.test.tsx`
- **根因已精確定位**：測試點擊「只看指派給我」checkbox 後，預期下一次 API 呼叫的查詢字串包含 `mine=true`，但實際最後一次呼叫仍是 `include_test=true`（沒有 `mine` 參數），代表 `AdminCasesPage.tsx`（本次任務開始前就已是未提交修改狀態）目前並未把「只看指派給我」的勾選狀態轉成 API 查詢參數送出。
- **與 GA09/SC09 本批次的關係**：`AdminCasesPage.tsx` 與本批草稿功能的任何檔案都沒有程式相依，純屬管理後台案件列表的既有功能缺口。
- **部署風險評估**：風險侵限於「管理後台案件列表的指派篩選」功能本身失效（督導/主任篩選「只看指派給我」可能沒有實際生效），與 GA09/SC09 草稿功能無關，**不阻擋 GA09/SC09 部署**，但若要部署整支分支（含 `AdminCasesPage.tsx` 的變更），建議先修好這個篩選邏輯或恢復到可通過測試的版本。

## 本輪（第五輪）Git diff 檢視結果（未 `git add .`，未 commit）

- **本輪新增檔案**：`backend/app/services/jiaan1030_ga09_sc09_fields.py`（欄位規格草稿 + `apply_draft_fields` 可回復套用函式）、`backend/tests/test_jiaan1030_ga09_sc09_fields.py`（6 項新測試）、`frontend/tests/dynamic-form-ga09-sc09.test.tsx`（4 項新測試）。
- **本輪沒有修改任何既有程式檔案**（`jiaan1030_service_drafts.py`、`DynamicForm.tsx`、migration 等皆未變動），純粹新增欄位規格資料與測試，未重跑第四輪已通過的 19 項授權測試。
- `docs/ga09_sc09_progress.md` 新增本節記錄。

## 上輪（第四輪）Git diff 檢視結果（未 `git add .`，未 commit）

- **本輪修改檔案**（皆為先前已追蹤/新增的 GA09/SC09 檔案，非新檔案）：`backend/app/api/jiaan1030_service_drafts.py`（新增 `_can_create_draft_for_client`、統一 `list_service_clients`/`list_drafts` 的存取邏輯、`grant_client_access` 開放照服員為被授權人）、`backend/app/jiaan1030_client_models.py`（docstring 更新）、`backend/tests/test_jiaan1030_service_drafts.py`（新增 `_bind_line` 輔助與 5 項測試）、`frontend/src/liff/pages/ServiceClientsPage.tsx`（新增授權/撤銷輸入 UI）、`docs/ga09_sc09_progress.md`。
- **本輪沒有新增/修改任何 migration 或 ORM 欄位**（純應用層邏輯調整）。
- 未觸碰第三輪列出的「與本批次無關」檔案清單。

## 上輪（第三輪）Git diff 檢視結果（未 `git add .`，未 commit）

- **本批 GA09/SC09 新增檔案**（未追蹤）：`backend/app/api/jiaan1030_service_drafts.py`（改寫）、`backend/app/jiaan1030_draft_models.py`（改寫）、`backend/app/jiaan1030_client_models.py`（新增）、`backend/app/roles.py`、`backend/checks/jiaan1030_prod_migration_readonly_check.py`、`backend/migrations/versions/0003_jiaan1030_catalog_schema.py`、`backend/migrations/versions/0004_jiaan1030_clients.py`（取代原 `0004_jiaan1030_service_form_drafts.py`，因從未套用到任何資料庫而直接改名重寫，非刪除既有已套用 migration）、`backend/migrations/versions/0005_jiaan1030_drafts.py`（新增）、`backend/tests/test_jiaan1030_service_drafts.py`（擴充）、`docs/ga09_sc09_progress.md`、`frontend/src/liff/components/DynamicForm.tsx`、`frontend/src/liff/pages/ServiceFormPage.tsx`（改寫）、`frontend/src/liff/pages/ServiceClientsPage.tsx`（新增）。
- **本批修改的既有追蹤檔案**：
  - `backend/migrations/env.py`（註冊 `jiaan1030_client_models`/`jiaan1030_draft_models`）、`backend/tests/conftest.py`（測試清庫清單加入 jiaan1030 相關表）——**全部內容皆為本批次新增**。
  - `backend/app/api/caregiver_routes.py`——同時含有**非本批次**的既有未提交變更（`director` 角色支援、官方來源附掛），**本批次只新增檔案最底部兩段 `router.include_router(...)` 掛載**，未改動其他部分。
  - `frontend/src/liff/pages/CaseDetailPage.tsx`——第二輪曾新增的 GA09/SC09 入口區塊本輪**已移除**（語意不再適用），檔案其餘既有未提交變更不受影響。
  - `frontend/src/liff/pages/HomePage.tsx`——新增一個選單連結指向 `/liff/service-clients`。
  - `frontend/src/main.tsx`、`frontend/src/api.ts`——路由與型別定義更新（`case_id`→`service_client_id`，新增 `Jiaan1030ServiceClient` 型別與路由）。
- **其他大量未追蹤/已修改檔案與本批次無關**（`jiaan1030_role_guard.py`、`jiaan1030_official_source.py`、emergency 相關檔案、`ReportPreviewPage.tsx`、`AdminCasesPage.tsx`、`main.py` 等），**本輪未觸碰**。

## 尚未確認欄位（待嘉安審核，不可視為最終版）

1. 各欄位是否必填（目前一律 `required: False`）。
2. 服務時間的實際輸入格式（起訖時間／時段／純文字，目前暫用文字輸入佔位）。
3. 服務內容欄位的字數上限（目前暫訂 2000 字，僅為保守佔位值）。
4. 簽章欄位的簽署流程、載具與法規要求（目前僅佔位，不收集簽章資料）。
5. 服務類型下拉選項是否需顯示中文全名（目前僅用 GA09／SC09 代碼本身）。
6. 是否還有其他欄位（本輪只納入 10/30 訪談補充紀錄中明確列出的 5 類，未自行增列）。

## 尚未完成、不可宣稱已完成

- 未修改正式資料庫、未部署、未重啟正式 API、未 push GitHub、未 commit、未核准任何 `reviewed`/`schema_status`。
- 上方「尚未確認欄位」清單需嘉安審核後才能從草稿轉為正式規格；目前草稿版本**只存在於程式碼與 `ltc_test`**，尚未套用到任何持久化的開發/正式資料庫。
- 服務個案主檔目前僅有「代稱」欄位，尚無任何服務起止時間等結構化欄位——是否併入 `jiaan1030_service_clients` 或留在表單 `payload_json` 內，待欄位規格正式確認後再議。
- 授權（grant）機制目前是「建立者或主任/admin 可指定照服員/督導」的最小化版本，沒有到期日、沒有申請/審批流程、沒有通知；被授權人目前只能靠直接輸入 User ID 指定（無人員查詢 UI）；若嘉安需要更完整的授權審批（類似 `interaction_models.py` 裡的候選 `HistoryGrant` 設計），需另行討論。
- **服務個案與嘉安既有長者名冊的對應關係維持待確認狀態**：目前 `display_label` 只是假代稱，未做、也刻意不做任何自動比對；需嘉安提供可驗證的對應鍵才能進一步設計。
- 真人操作驗收（照服員/督導/主任實際登入操作、HTTP 驗收）未進行。
- `test_qa_flow.py`（緊急文字已被角色化改寫、測試未同步更新）、`admin-cases.test.tsx`（「只看指派給我」篩選未送出查詢參數）兩項既有失敗未修復，皆已精確定位、確認與本批次無程式相依，但分屬各自負責人範圍，未在本次處理，也未修改任何測試期待值或緊急安全文字。

## 下一步建議

①現在執行（實驗室電腦，PowerShell，本機測試環境）：無需動作，本輪已完成 GA09/SC09 欄位規格草稿、`apply_draft_fields` 可回復套用機制與離線測試，留待審閱。
②成功後執行：請嘉安確認上方「尚未確認欄位」清單（必填條件、服務時間格式、字數上限、簽章流程、服務類型選項顯示文字）；確認後我可用既有的 `apply_draft_fields()` 與主任核准 API（`schema_status`→`reviewed`）走正式流程，仍只在您指示的環境執行。也請確認照服員授權保守預設是否符合嘉安實際跨居督協作方式。確認後再決定是否要 `git add`（列明確檔名，不用 `git add .`）與建立 commit，以及是否將 migration 套到正式庫。
③失敗後執行：若審閱發現欄位規格、授權政策或資料模型需調整，請指出項目，我會在不碰正式環境、不關閉安全檢查、不修改測試期待值的前提下修改並重新跑測試。
