# Google 官方 Drive API：準備完成，實際授權／上傳／排程停用

本分支以 Google Drive v3 API 取代電腦版同步與 rclone。不安裝 Google Drive 電腦版、不接觸 OneDrive、不新增付費服務；Google Cloud 不啟用計費服務，Drive 空間或 API quota 不足就失敗，不自動購買。

## 目前狀態

- 同步目的地是本人已在網頁建立的 XiaoZhao/ApprovedSource；實驗室 email 僅放本機 private config，原始碼／測試使用假帳號。
- `%LOCALAPPDATA%/XiaoZhaoSync/sync_targets.local.json` 已準備；driveEnabled=false、driveAccountCheckedByHuman=false、allowGitHubAutoPush=false，兩個 folder ID 與 OAuth 憑證尚未填。沒有 OAuth、沒有 Google 實際上傳、沒有新排程。
- SDK 是可選獨立備份工具依賴，不能安裝或升級 backend/.venv；模擬測試不需要 SDK。

## 本人集中完成的準備

1. 使用實驗室帳號建立／選取 Google Cloud 專案，只啟用 Drive API；設定 OAuth consent、測試使用者。建立 OAuth 用戶端類型「Desktop app」，下載 client JSON 到本機 `%LOCALAPPDATA%/XiaoZhaoSync/oauth/client_secret.json`。這只是 OAuth 類型，不是安裝 Drive 電腦版。不要把 JSON／密碼／Token 貼到聊天或 Git。
2. 在專用 backup-tools venv 安裝 tools/approved_sync/requirements-drive-api.txt（本次未建立或安裝）；本人執行 authorize_google_drive.py --config <本機設定> --authorize。工具才會開本人瀏覽器及暫時 loopback callback，使用 PKCE／state，只要求 drive.file；不輸出授權 URL、code 或 Token，錯誤只印類型。只在 API about 驗證與私存實驗室 email 相同後保存新 Token，且資料夾 ACL 僅本人與 SYSTEM。
3. **drive.file 不會因填入網頁資料夾 ID 就自動授權既有資料夾。** 必須透過 Google Picker 讓此 app 明確取得 XiaoZhao 與 ApprovedSource 的存取，或另經本人同意改用 app 建立的專用資料夾；不得自動改成整個 Drive 權限。Picker 的實際授權／頁面尚未設定與驗證，這是第一次真實備份前的必要條件。填入兩個 folder ID 後，用 --check-identity 做唯讀核對；若 403／404 就停，不擴權。
4. 工具會核對 authenticated email、me、ownedByMe、資料夾名稱／parent ID、非 shared drive、未刪除及 canAddChildren。本人確認後才能設 driveAccountCheckedByHuman=true；另明確允許真實備份後才設 driveEnabled=true。--check-identity 本身不能上傳。
5. 第一份實際備份必須核對 GitHub 同一個 SHA、zip SHA256，以及 Drive API 遠端 md5Checksum／size／appProperties.source_commit。沒有這些證據，不能宣稱上雲。現在完全沒有真實 Google 雲端成功紀錄。

## 品質與隱私閘門

先沿用 github_sync_check.ps1，這支程式仍是唯一可選的 GitHub 自動 pusher；沒有第二套 auto add／commit。backup helper 只讀真正遠端 stableBranch SHA；非 check-only 的上傳還必須有遠端 stable-ready-* tag 和該 commit 中的 `.claude/approved-sync-validation.json`。receipt 必須為 backend／typescript／frontend／sensitiveReview 全 PASS，且 exported source digest 完全一致；改來源就必須重新審核／測試。

來源從 immutable Git blob 匯出，不讀工作目錄或資料庫。只包含白名單程式／必要測試／文件／模板；不包含 .env、*.local.env、OAuth、private run、資料目錄、訪談、錄音、SQL patch 或 DB dump。疑似 credential／個資攔截即停止。歷史已確認合成範例／regex／port-1 fake DSN 使用逐檔文字 hash＋逐命中 hash 的審核表，內容改變即失效；不是關閉規則。參數化環境變數與明確 REPLACE_* 模板不是明文密碼，真實 literal DSN 仍拒絕。

每 commit 一份確定性 ZIP，既有遠端版本必須內容及 commit 都相同；不覆蓋、不刪版本。Google API resumable upload 不使用額外服務，SDK 不自動重試不可判定的上傳；中斷／無 checksum／重名／quota 失敗都記 blocked，保留證據。只有 ZIP 與 LM reminder 都核對成功才 cloudVerified=true。

## 排程與紀錄

現有 SessionEnd hook 與每日 09:00 XiaoZhao-GitHubSyncDaily 保持原樣，主目錄 dirty 時會 SKIP，不等於已備份。新 install_schedule.ps1 預設 dry-run，Drive API／人工身分與目標未完成不得 -Install；會拒絕同名或等效工作。15 分鐘工作目前未建立。未來只在登入與開機時執行，StartWhenAvailable 可補跑，不能保證關機期間同步。

新 helper 以 `%LOCALAPPDATA%/XiaoZhaoSync/approved-sync.lock` 防重入，殘留鎖保留並要求審核，不自動搶鎖；JSONL 記錄 started／ok／blocked、Git SHA、ZIP SHA256、cloudVerified、錯誤類型，不記帳密。Codex 不假設有 SessionEnd API；可在完成測試／Commit／stable tag 後手動呼叫同一 helper，日後啟用排程仍沿用這條路徑，不增加 auto commit。

Google 官方依據：
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- https://developers.google.com/identity/protocols/oauth2/native-app
- https://developers.google.com/workspace/drive/api/guides/manage-uploads
