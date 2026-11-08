# OAuth／Picker 與 UAT 量測：隔離分支審核紀錄

- 基底：`78ff63e9041243125e785e661f45c7f11fe3bcab`，不修改原穩定分支、main 或 stable-ready tag。
- 本次分支：`preparation/oauth-picker-uat-metrics-20261108`，提交與遠端 SHA 以 Git 紀錄為準。
- 原主工作目錄分支不變、167 筆修改保留；所有變更只在獨立 review clone。

## 審核範圍

本人操作的 OAuth／Google Picker、一次性合成檔案探針、同步模板、原 UAT 25 項量測附表、老師安全交付指引、Google Cloud 逐步操作與 LM 摘要。不納入 .env、私人設定、憑證、資料庫備份、真實訪談與測試執行日誌。

補強 OAuth offline／consent、Refresh Token 存在與精確 drive.file 檢查；Picker 輸入型別及 folder／parent／owner／身分核對；probe 不重傳、拒絕 redirect、上傳前 exclusive marker、下載 SHA256。測試中的 mock staging 強制放臨時資料夾，不寫使用者真實備份暫存。

## 本次實際結果

| 檢查 | 實際結果 | 邊界 |
|---|---|---|
| Drive／同步／OAuth 模擬 | 31 項通過，含本次 12 項 manual flow | 全部 fake／mock，不代表 Google 實際授權成功 |
| 後端 | 356 項通過，exit 0 | 新建 loopback、tmpfs 的臨時 pgvector 容器；僅合成測試資料，結束僅停止此容器 |
| TypeScript | exit 0 | 不啟動網頁服務 |
| 前端 | 213 項通過，exit 0 | jsdom／mock |
| 新 Picker JS／Python 語法 | 通過 | 不是 Google 真實瀏覽器相容性驗證 |
| 提交內容與完整來源篩檢 | 依既有白名單與逐檔 hash 審核規則執行 | 真正憑證命中即停止；不降低敏感規則 |

第一次 mock 套件執行因沿用真實 LOCALAPPDATA 暫存路徑而遭沙箱拒絕；已修正測試 setUp 隔離暫存路徑，重新執行 31 項全過，未擴權或放寬斷言。後端有既有 FastAPI duplicate Operation ID 警告、前端有 React Router future 警告，均未變更部署／套件來消除警告。

PostgreSQL 測試初始化僅讀 demo schema 到新建臨時容器，不搬資料、不執行 migration，不寫 ltc_demo／ltc_clean，不修改任何現有容器、權限或服務。測試容器已依唯一 label 核對並移除；原環境不重啟。

## 尚未完成，不能算通過

Google Cloud 專案／發布狀態尚待本人操作；OAuth client JSON、Token、Picker key／project number 尚未取得；真人帳號授權、Picker 真實頁面、實際 Drive 上下傳與 SHA256 尚未驗證。Drive 同步 false、沒有新排程、沒有真人 UAT，也沒有部署 shadow 模組或修改 LINE Webhook。新分支未加 stable-ready tag；舊品質 receipt 不能替新來源背書，排程不得自動採用此分支。

## 已查核的長期設計

External／Testing＋drive.file 的 Refresh Token 七天失效；持續 refresh 不取消期限。建議開發與備份 production 專案分開，由本人依 Google 規範發布、重新授權，維持最小 scope／指定帳號／Picker 資料夾與 STUST 私存。發布不代表永久 token、也不代表測試帳號 allowlist 仍限制 audience。失效停寫、人工重新授權；自動暫停排程機制尚未實際驗證，不直接啟用。

詳見 [完整本人操作與長期方案](../sync/GoogleDrive_API_準備與啟用.md)、[LM 摘要](LM_更新摘要_OAuth與UAT量測_20261108.md)。
