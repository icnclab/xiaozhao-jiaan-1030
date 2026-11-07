# 嘉安 1030 第七輪：多人逐字稿角色標註 — 進度紀錄（2026-11-02）

## 本輪範圍
延續第六輪快速分類回報（57/57 前端測試）與 GA09/SC09 草稿（19 項授權測試），本輪僅處理：
逐字稿多人說話者標註、角色對應（未辨識／照服員／居督／長者／家屬／其他）、文字與角色人工修正後的
明確確認流程，以及未同步草稿的明確標示。**未重跑舊有的 191/181 項既有測試**。

## 既有基線（確認未動）
- `backend/app/services/transcripts.py` 的草稿／確認流程（`create_upload` → STT → 加密草稿 →
  人工 `confirm` → 遮罩存檔並刪除未遮罩草稿）本就存在，本輪未改動其狀態機、加密、音訊保留規則。
- `frontend/src/liff/pages/TranscriptPage.tsx` 本就有「草稿逐段修正文字／指定說話者／角色對應／
  摘要／明確按鈕確認送出」的 UI，確認按鈕本就不會自動送出（需使用者點擊）。

## 本輪新增／修正
1. **角色集補上「居督」**
   - `backend/app/services/transcripts.py`：`ROLES` 新增 `supervisor: 居督`（原本只有
     照服員／長輩／家屬／其他工作人員／未辨識，缺少居督這個角色選項）。
   - `frontend/src/api.ts`：`ROLE_LABELS` 同步新增 `supervisor: 居督`，並將 `staff` 的顯示
     文字由「其他工作人員」簡化為「其他」以符合本輪訪談用語（未辨識／照服員／居督／長者／家屬／其他）。
2. **多人標註上限擴大到 8 人**
   - `frontend/src/liff/pages/TranscriptPage.tsx`：`SPEAKERS` 下拉選單由 `speaker_1..4` 擴大到
     `speaker_1..8`，對齊後端 `transcripts.py` 本就支援的 `speaker_1..8` 驗證範圍，讓多人談話
     （照服員＋居督＋長者＋家屬＋其他）可以分別標註不互相覆蓋。
3. **草稿階段直接顯示說話者已對應的角色**
   - 同一畫面在說話者下拉選單旁加上「（居督）」等角色提示，方便多人逐字稿時確認是否標對，
     不需要往下捲到角色對應區塊才看得到。
4. **明確標示「未同步」的本機修改**
   - 目前文字／說話者／角色的修正只存在瀏覽器記憶體（React state），尚未呼叫 `/confirm` 寫入
     後端前，刷新或離開頁面就會遺失。本輪新增：
     - 畫面上的 `role="alert"` 警示：「⚠️ 修改尚未儲存：…離開或重新整理會遺失，請按下方
       「確認送出」保存。」
     - `beforeunload` 監聽：草稿狀態且有未送出修改時，離開/重新整理分頁會被瀏覽器要求再次確認。
   - 未新增任何「自動暫存於後端」的 API；在沒有安全的後端草稿儲存端點前，**不宣稱本機修改已永久保存**。
5. 確認送出流程維持原有「按鈕點擊才送出、未點擊絕不呼叫 `/confirm`」的行為，未新增自動送出路徑。

## 測試
- 後端：`backend/tests/test_transcripts.py`
  - 新增 `test_supervisor_role_tags_multiple_speakers`：speaker_1=居督、speaker_2=家屬，
    確認後角色與對應片段各自正確、未標註片段維持 unknown。
  - 執行範圍：僅本檔案（本輪相關），**未重跑其他既有測試檔**。
  - 結果：`pytest tests/test_transcripts.py -q` → 9 passed（8 項既有 + 1 項新增），全部在真實
    Postgres 測試資料庫（`conftest.py` fixture）上執行，非 mock 假通過。
- 前端：`frontend/tests/speaker-annotation.test.tsx`（新增，6 項測試）
  - 下拉選單含 `speaker_1..speaker_8` 全部 9 個選項（含未辨識）。
  - 角色選項依序為 照服員／居督／長輩／家屬／其他／未辨識。
  - 載入時不會自動呼叫 `/confirm`；一有修改即出現「尚未儲存」警示，點擊確認前都不送出。
  - 草稿修改後出現「離開或重新整理會遺失」警示；尚未修改時不出現。
  - 說話者標註角色後，畫面即時顯示「（居督）」等角色提示。
  - 點擊「確認送出」後，POST 的 `segments`／`roles` 內容與畫面修正一致。
  - 執行：`npx vitest run tests/speaker-annotation.test.tsx` → 6 passed。**未重跑其他既有前端測試檔**。
- 型別檢查／建置：`npx tsc --noEmit` 無錯誤；`npm run build` 成功產出 `dist/`。

## 是否可真正儲存及重新讀取
- **確認後**（按下「確認送出」且後端回應成功）：segments／speaker_roles／summary_masked 寫入
  Postgres（`TranscriptSegment`、`Transcript.speaker_roles`），關閉分頁或重新登入後，`GET
  /api/transcripts/{id}` 會讀回同樣的已確認內容 — 這部分是既有機制，本輪未更動，已由
  `test_transcripts.py` 既有測試與本輪新增測試覆蓋。
- **確認前**（草稿階段的文字／說話者／角色修改）：只存在瀏覽器當前頁面的 React state，**不會**
  自動同步到後端、也不會寫入任何瀏覽器儲存（本專案規範音訊與逐字稿不落地瀏覽器儲存）。重新整理或
  離開頁面會遺失，本輪已加上明確警示與離開前確認，避免誤以為已保存。

## 正式環境是否受影響
- 未連線、未查詢、未修改正式 `ltc_clean` 資料庫；未執行任何 migration；未重啟正式 API；
  未部署。全部工作在本機程式碼與測試資料庫完成，`git status` 顯示僅工作目錄修改，未 `add`／
  `commit`／`push`。

## 尚待驗證／下一步
1. **真人 HTTP／LIFF 驗收尚未進行**：以上僅離線測試通過，尚未有照服員／居督在 LIFF 介面實際
   操作多人逐字稿標註並驗收。
2. 若嘉安後續提供「居督」在原始訪談中是否有更細分角色（例如區分主責居督／協同居督）的要求，需
   依據實際訪談資料再調整，不可自行擴充。
3. 背景持續的多人語音分段（diarization，見 `backend/app/providers/diarization.py` 的
   `NoDiarization`）仍是人工標註為主，本輪未新增自動語音辨識說話者的模型（刻意維持，避免以聲音
   猜測身分）。
4. 下一步若要做「安全的後端草稿自動儲存 API」，需先與使用者確認資料保留期限、加密與存取權限
   設計，屬於資料庫結構異動，依規則須先停下來提出差異待核准，本輪未執行。

## 失敗點
無。本輪變更皆通過對應測試；未發現阻礙。
