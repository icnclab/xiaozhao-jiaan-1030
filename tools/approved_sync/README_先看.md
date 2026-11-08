# 11/8 整合版：Google Drive 官方 API，預設全部停用

> 最新策略改為 GitHub 安全同步＋Google Drive 網頁手動上傳。API／OAuth 工具保留但不啟用；先讀專案根目錄 `docs/sync/GitHub與Drive網頁手動備份.md`。不需 Google Cloud Console 或 Drive 電腦版。以下 API 說明是保留的歷史方案。

本目錄源自使用者補充工具包，原件留在本機隔離審核區。此版本依最新要求只使用官方 Drive v3 API，不依賴電腦版、rclone 或 OneDrive。

- 先讀 docs/sync/GoogleDrive_API_準備與啟用.md（專案根目錄）。
- sync_verified.py 只備份遠端已 stable-ready 標記、測試 receipt／source digest 相符且敏感掃描通過的 commit；不 auto add／commit。
- OAuth／帳號／Picker 資料夾授權由本人操作；實際上傳與排程目前關閉。
- handover_review 僅是無訪談原始檔的參考，MPC adapter 在獨立服務中預設關閉，IoT 不能部署。
- tests 使用假 Git、假 Drive API 與合成情境；成功不代表 Google 已上雲或真人 UAT 已通過。

子目錄 docs 中原始指令是交接歷史，涉及 Drive 電腦版／rclone 的段落已由上述 API 指南取代。
