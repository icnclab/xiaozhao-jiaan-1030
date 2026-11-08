# Google 官方 Drive API：準備完成，實際授權／上傳／排程停用

> 2026-11-08 最新決定：暫不使用 Cloud Console／API／OAuth；改採 [GitHub＋Drive 網頁手動備份](GitHub與Drive網頁手動備份.md)。下文只保留作未來評估，不應依本文啟動授權、試傳或排程。

本分支以 Google Drive v3 API 取代電腦版同步與 rclone。不安裝 Google Drive 電腦版、不接觸 OneDrive、不新增付費服務；Google Cloud 不啟用計費服務，Drive 空間或 API quota 不足就失敗，不自動購買。

## 目前狀態

- 同步目的地是本人已在網頁建立的 XiaoZhao/ApprovedSource；實驗室 email 僅放本機 private config，原始碼／測試使用假帳號。
- `%LOCALAPPDATA%/XiaoZhaoSync/sync_targets.local.json` 已準備；driveEnabled=false、driveAccountCheckedByHuman=false、allowGitHubAutoPush=false，兩個 folder ID 與 OAuth 憑證尚未填。沒有 OAuth、沒有 Google 實際上傳、沒有新排程。
- SDK 是可選獨立備份工具依賴，不能安裝或升級 backend/.venv；模擬測試不需要 SDK。

## 本人集中完成的準備

1. 使用實驗室帳號建立／選取 Google Cloud 專案，啟用 Drive API 與 Google Picker API；設定 OAuth consent、測試使用者。建立 OAuth 用戶端類型「Desktop app」，下載 client JSON 到本機 `%LOCALAPPDATA%/XiaoZhaoSync/oauth/client_secret.json`。這只是 OAuth 類型，不是安裝 Drive 電腦版。不要把 JSON／密碼／Token 貼到聊天或 Git。
2. 在專用 backup-tools venv 安裝 tools/approved_sync/requirements-drive-api.txt（本次未建立或安裝）；本人執行 authorize_google_drive.py --config <本機設定> --authorize。工具才會開本人瀏覽器及暫時 loopback callback，使用 PKCE／state，只要求 drive.file；不輸出授權 URL、code 或 Token，錯誤只印類型。只在 API about 驗證與私存實驗室 email 相同後保存新 Token，且資料夾 ACL 僅本人與 SYSTEM。
3. **drive.file 不會因填入網頁資料夾 ID 就自動授權既有資料夾。** 使用本次準備的 picker_google_drive.py，讓本人依序選取 XiaoZhao 與 ApprovedSource。此頁面與一次性測試已完成離線模擬，Google 真實授權／頁面尚未驗證。不得自動改成整個 Drive 權限。實際步驟見下方；若 403／404 就停，不擴權。
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

## 2026-11-08 接續：本人 OAuth → Picker → 一次測試

工作區為主目錄下 `run/handover-integration-20261108/review`，基底 commit `78ff63e9041243125e785e661f45c7f11fe3bcab`。本次以獨立分支 `preparation/oauth-picker-uat-metrics-20261108` 交付工具與文件；提交／遠端驗證結果見該分支 Git 紀錄。本次不是部署，不修改原穩定分支或自動備份目標，也不替新分支加 stable-ready tag；原 receipt 僅對原來源有效。

### A. 本人先做 Google Cloud 設定

1. 本人在 STUST 以指定實驗室帳號登入 [Google Cloud Console](https://console.cloud.google.com/)，核對右上角帳號，且與本機 expectedDriveAccount 完全一致。不得改用私人、老師或其他帳號。點頂端專案選單 →「新增專案」，命名例如 `XiaoZhao Backup Lab` →「建立」→ 切換至新專案。不要連結帳單、啟用免費試用升級或輸入信用卡。這是備份工具的 Google Cloud 專案，不是變更正式小照部署。
2. 左上選單 →「API 和服務」→「程式庫」，分別搜尋 **Google Drive API** 與 **Google Picker API** →「啟用」。確認畫面專案名稱正確，沒有啟用其他付費 API。
3. 左上選單 → **Google Auth Platform** →「開始使用」（舊介面可由 API 和服務 → OAuth 同意畫面進入）。Branding 填 `XiaoZhao Approved Backup`、本人指定實驗室帳號作支援／聯絡 email。Audience 選 **External**、Publishing status 保持 **Testing**，在 Test users 只新增同一實驗室帳號。個人 gmail 帳號不能冒用 Workspace 的 Internal 模式。Data Access →「新增／移除範圍」，只保留 `https://www.googleapis.com/auth/drive.file`，確認列於 Non-sensitive；不加 drive、drive.readonly、metadata.readonly、Gmail 或 domain-wide delegation。
4. Google Auth Platform →「用戶端」→「建立用戶端」→ Application type **Desktop app**，名稱 `STUST Backup CLI` →「建立」→ 下載 JSON。先在 STUST 建立 `%LOCALAPPDATA%\XiaoZhaoSync\oauth`，將 JSON 存為其中的 `client_secret.json`，不要存到專案、OneDrive 或共用資料夾；不可覆蓋已存在憑證。本工具用 Python installed-app PKCE callback 取得 token，再把短效 access token 傳給本機 Picker；不使用 Google 範例中的 JavaScript OAuth 登入，因此不需另外建立 Web client 或 Funnel callback。必須是同一專案的 client、API key 與 project number。實際相容性仍待本人授權確認。
5. API 和服務 →「憑證」→「建立憑證」→「API 金鑰」→「編輯」。Application restrictions 選 Websites，referrer 限制加入 `http://127.0.0.1:17866/*` 與 `https://docs.google.com/*`；API restrictions 選 Restrict key，只選 Google Picker API、Google Drive API →「儲存」。IAM 和管理 →「設定」取得 **數字 project number**，不是文字 project ID。這兩個值填在本機設定 `pickerApiKey`、`pickerProjectNumber`，不要貼聊天或 Git。Google 官方 Picker 範例要求 docs.google.com iframe 的 referrer 一併列入。
6. 用本機編輯器開 `%LOCALAPPDATA%\XiaoZhaoSync\sync_targets.local.json`，保持 `driveEnabled=false`、`driveAccountCheckedByHuman=false`，新增 `pickerGrantVerified=false`。保留既有 expectedDriveAccount、repoPath、OAuth 檔案路徑，不覆寫成模板空值；兩個 folder ID 由 Picker 保存。勿將實際 JSON 放進 Git；本人只回報完成狀態，不回傳內容。

### B. 本人在 PowerShell 執行（不需更動任何服務）

以下只建立獨立工具 venv，不安裝 Drive 電腦版，也不更動 backend/.venv：

```powershell
$reviewRoot = 'C:\aa\ltc_care_installer_20260912\ltc_care\run\handover-integration-20261108\review'
$toolPython = "$env:LOCALAPPDATA\XiaoZhaoSync\backup-tools-venv\Scripts\python.exe"
$privateConfig = "$env:LOCALAPPDATA\XiaoZhaoSync\sync_targets.local.json"
# 只在這個獨立 venv 不存在時建立；不覆寫既有環境。
if (-not (Test-Path -LiteralPath $toolPython)) {
    & "$reviewRoot\backend\.venv\Scripts\python.exe" -m venv "$env:LOCALAPPDATA\XiaoZhaoSync\backup-tools-venv"
}
& $toolPython -m pip install -r "$reviewRoot\tools\approved_sync\requirements-drive-api.txt"
& $toolPython "$reviewRoot\tools\approved_sync\scripts\authorize_google_drive.py" --config $privateConfig --authorize
```

瀏覽器登入、核對 scope、同意全部由本人完成。若帳號不符、權限超過 drive.file、陌生 app 或要求付費，停止，不繞過警示。授權成功只保存至本機私有 OAuth 資料夾，不覆蓋既有 token；已有 token 時先用現有設定核對，不刪檔重來。

```powershell
& $toolPython "$reviewRoot\tools\approved_sync\scripts\picker_google_drive.py" --config $privateConfig --select-folders
```

這支工具僅啟動 **127.0.0.1:17866** 暫時本機頁面，五分鐘內由本人依序按「選 XiaoZhao」→「選 ApprovedSource」→「核對並保存」。不經 UAT／正式服務、Cloudflare 或 Tailscale。頁面使用隨機 nonce、Host／Origin 檢查、不快取、不記錄 token。API 會再次核對實驗室身分、兩個目錄名稱、本人擁有、上下層關係與可新增檔案；失敗不存新設定。保留變更前私有設定備份，成功仍保持同步停用及人工確認 false。關閉此頁後回本機：

```powershell
& $toolPython "$reviewRoot\tools\approved_sync\scripts\authorize_google_drive.py" --config $privateConfig --check-identity
```

只有本人確認 PASS 且目的地確為指定資料夾後，才在**本機**設定 `driveAccountCheckedByHuman=true`；**driveEnabled 仍為 false**。不要回傳任何 token、client JSON 或 API key，只需回覆「OAuth／Picker／唯讀核對完成」或不含憑證的錯誤類型。

### C. 完成授權後只做一次非敏感檔案試傳

```powershell
& $toolPython "$reviewRoot\tools\approved_sync\scripts\probe_google_drive.py" --config $privateConfig --run-once
```

檔案內容固定為合成連線測試說明＋隨機 run ID，約數百 bytes，不讀專案檔案或資料庫。只向核對過的 ApprovedSource 上傳一份 `xiaozhao_synthetic_probe_<run>.txt`，再下載同一 file ID，核對 parent、size、appProperties 及完整內容 SHA256。這是連線測試，**不是程式碼備份**，不會設 source-backup cloudVerified=true。

`%LOCALAPPDATA%\XiaoZhaoSync\drive-probe.once.json` 在網路寫入前以 exclusive create 建立；`drive-probe.jsonl` 記 started／upload_attempted／uploaded_not_verified／passed 或 failed_or_unknown_no_retry、參考 commit、兩端 SHA256、file ID 與錯誤類型。HTTP 單次 POST、無 retry、無 redirect、無 auth-refresh resend。API 失敗、quota、下載損毀或網路中斷都停止；第二次執行直接拒絕，不自動刪 marker、刪測試檔或再上傳。逾時可能已上傳，必須先用網頁／唯讀 API 依 run ID 查核，人工決定後續處置。

### D. 排程仍不可直接啟用

需先有實際 probe passed 證據，再單獨授權第一份 **78ff63e90412** 已審核 ZIP／LM 摘要的版本備份；核對 GitHub SHA、來源品質 receipt、遠端內容及同步紀錄後，才考慮設 driveEnabled=true 與排程。External／Testing 狀態的此類 OAuth refresh token 通常七天到期；長期排程還須確認發布狀態及本人重新授權策略，失效時停用／記錄，不循環上傳或擴大 scope。

本次新增離線 mock 案例核對成功、錯誤帳號／folder、漏人工確認、403、timeout、下載 SHA 不符與重複執行拒絕；不等於真實 Google 上傳通過。

官方依據：[Picker 範例與 API key 限制](https://developers.google.com/workspace/drive/picker/guides/web-picker-sample)、[drive.file 最小範圍](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)、[OAuth token 效期](https://developers.google.com/identity/protocols/oauth2)。

## E. 免費長期定時備份方案（僅規劃，本次不啟用）

### 已查證的七天限制

Google 官方明定：External＋Testing 發出的 Refresh Token 於七天後失效，只有單純基本身分 scope 的例外；**drive.file 不在該例外**。定期執行 refresh 不會取消七天期限，換成 API key 也不能替代使用者 OAuth。[官方 Token 到期規則](https://developers.google.com/identity/protocols/oauth2#expiration)

短期維持 Testing，只適合本人測試與手動重新授權；不把每週人工授權包裝成無人長期備份。不要改用範圍更大的 Drive scope、service account 私鑰、他人帳號或付費 Workspace 來繞過限制。

### 建議的長期配置

1. 先完成本文件的 Testing OAuth／Picker 與一次性合成檔案驗證。長期自動化另用備份專用專案（例如 `XiaoZhao Backup Automation`），與開發測試分開；相同實驗室帳號、同一目標資料夾，只用 drive.file，仍不連結計費帳單。Production 專案不得帶入未驗證的測試功能；若尚未符合 Google 要求，就停在手動模式。[Google 建議開發與 production 專案分離](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance)
2. **由本人操作** Google Auth Platform → Audience → Publishing status → Publish app／In production，核對 Google 提示、Branding／Verification Center 要求後才確認。drive.file 為 non-sensitive，通常不需敏感或受限 scope 的額外安全審查；仍須遵守基本品牌／OAuth 驗證要求，不能保證完全免審，亦不能代按發布。若主控台要求擁有網域或額外流程，先回報；不買網域、不假填網址、不繞過 Google 要求。[Scope 分類](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
3. 發布不代表只允許測試清單帳號：External Published 的 OAuth audience 會擴大。工具仍以 STUST 本機 expectedDriveAccount 與實際 about 身分做嚴格核對；不向外提供授權頁服務、不分享 client JSON／Token、不允許其他帳號用於此備份。[Google app 狀態與 audience](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)
4. 本人為新 production client 重新授權並以相同專案的 Picker 再選既有兩個資料夾。使用新的本機 Token 檔名（例如 `authorized_user.production.json`，仍限 oauth 私人資料夾），保留 Testing token，不覆蓋、不自動刪除。不能假設舊 Testing Token 自動變永久；取得新授權後須重新核對 email／scope／folder。若先前單次 probe 已執行，保留 marker 和紀錄，不直接再跑；第二輪須先人工審核並另核准程序，不繞過禁止重傳。
5. Published 授權不再受上述 Testing 七天規則，但仍可能因本人撤銷、六個月未使用、帳號／Google 政策或 token 數量限制而失效，**不是永久憑證**。client、token 與 API key 僅在 STUST 本機；Token ACL 限本人＋SYSTEM，禁止雲端同步。主機移轉要本人重新授權，不把 Token 當備份檔。
6. 在真正上線排程之前，另行完成：實際 probe 成功、第一份原穩定版備份雙端核對、長期身分／權限核對、失敗停用與人工恢復演練。現有 helper 的 blocked 紀錄不能冒充已完成「自動暫停排程」；未驗證的自動暫停／告警閘門須先補妥，再授權排程。遇 invalid_grant／403／不確定上傳，停寫、保留現場、人工核對，不每 15 分鐘重送。
7. 排程只在本人登入的 STUST 上執行，不是 SYSTEM；可採每日或每 15 分鐘唯讀檢查 GitHub 版本，僅有新且通過品質閘門的 commit 才備份。既有版本核對後跳過，不重複上傳；未提交 167 筆不會自動 Commit。開機／登入後補檢查，關機期間不能保證備份。過期授權、鎖檔或未知結果必須先人工處置，不能自動清除證據。
8. 免費使用現有 Drive 儲存空間與 API 免費額度，採來源 ZIP、每版本一次、低頻 metadata 檢查；不連結帳單、不提高付費配額、不自動刪版本／買容量。Google 2026 年新配額與未來計價可能變動，超過額度或容量不足就停止；啟用前再次核對主控台的實際 quota 與帳單狀態，不能保證服務永遠免費。[Drive API 使用限制](https://developers.google.com/workspace/drive/api/guides/limits)

本次沒有建立 Google 專案、代替本人授權或發布、真實上傳、變更本機私人憑證，也沒有啟用排程。
