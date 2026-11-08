# 待交給 LM 學習：OAuth／Picker 與 UAT 量測接續摘要

基底穩定版 `78ff63e9041243125e785e661f45c7f11fe3bcab` 保持原樣；以下由隔離分支 `preparation/oauth-picker-uat-metrics-20261108` 交付，實際 Commit／推送以 Git 紀錄為準，未部署。請由本人審閱後交給 LM，不附私人設定、Token、錄音、訪談或真實個案。

1. GitHub 個人私人庫 collaborator 包含寫入，不能設定 Read-only。老師目前無權限；安全交付優先使用已審核來源 ZIP＋SHA256，由本人指定對象分享。GitHub 真正 Read 角色須組織庫並另授權，不分享 PAT／SSH key。
2. Google Drive 備份沿用官方 API、drive.file，無電腦版／OneDrive。新增本人操作的本機 Google Picker 頁面，逐一授權 XiaoZhao 及 ApprovedSource；以 about 身分、ownedByMe、名稱、parent 與 canAddChildren 核對。Picker 成功不自動開啟同步。
3. 一次性合成小檔探針：上傳前建立不可重入 marker，單次 POST、不 redirect／retry，下載同檔做 SHA256 與 metadata 核對；錯誤／逾時記 failed_or_unknown_no_retry，須先人工唯讀查核。這不是程式來源備份，不設 cloudVerified=true，排程保持停用。
4. OAuth 與 Picker 尚未真人授權，沒有真實 Drive 上傳成功證據。External／Testing 的 drive.file refresh token 七天後失效，持續 refresh 不能延長此限制。長期建議另建備份專用 production 專案，由本人依 Google 規範發布、取得新授權並重驗 Picker；non-sensitive 不代表免除所有驗證。Published token 仍可撤銷／失效，實際帳號仍僅限本機核對的實驗室帳號。七天限制與免費額度均已查官方文件，未開計費／發布／排程，失效不循環重傳、不擴 scope。
5. 原 UAT 25 項結果未更動。新增多人多輪意圖量測附表：gold 雙人獨立標記、完全匹配率、各類 precision／recall／F1、macro／micro-F1、危險漏辨與個案歸屬；回應時間同裝置單調時計、p50／p95／max，成功／錯誤／timeout 分記。單人序列不能宣稱多人驗證；閾值與樣本數仍待嘉安核定。
6. 新交接核心仍是未部署、預設關閉的 synthetic shadow；不能把其離線意圖結果當目前真人 UAT 的證據。正式 API／UAT API／Worker／資料庫／Funnel／LINE Webhook 未變更。

本次工具測試 31 項離線 mock 已通過（含 12 項本人授權／Picker／probe 測試）；Google Picker 的真實瀏覽器相容性、實際帳號與資料夾授權、真實下載 SHA256 及真人 UAT 均仍待執行。審核另補強 OAuth offline／consent 與完整 refresh token、精確 scope 檢查；Mock 同步暫存改用測試私人目錄，避免碰使用者真實備份位置。
