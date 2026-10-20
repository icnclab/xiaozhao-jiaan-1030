# 前端部署 Replace 修復

本輪只修部署，未重跑正式部署，未操作 DB 或服務。

## 根因與原始參數

原腳本第 61 行準備將編譯後的 pending 入口原子替換正式 index；第 65 行準備在驗證失敗時還原。同樣使用三參數 File.Replace，第三參數為 `$null`。

實際檔案推得此次參數為：

1. `C:\aa\ltc_care_installer_20260912\ltc_care\frontend\dist\index-20261017_103407_746.pending`，System.String，絕對檔案路徑。
2. `C:\aa\ltc_care_installer_20260912\ltc_care\frontend\dist\index.html`，System.String，絕對檔案路徑。
3. PowerShell `$null` 綁定到 .NET string 參數後變成空字串，並非 CLR null。

在 Windows PowerShell 5.1.26100.9711、CLR 4.0.30319.42000 的暫存資料夾實測，完全相同的呼叫拋出 ArgumentException「不合法的路徑格式」，source 仍在、destination 仍是舊內容。另用 C# string 參數探針驗證收到字串長度 0；改傳真實備份路徑即成功。不是猜測檔名或中文字出錯。

## 失敗後現況與恢復方式

已唯讀逐檔核對 `backups/frontend-dist-20261017_103407_746`：四個舊檔都存在，與正式 dist 中同名檔 SHA256 全部相同。

正式 dist 多了新版本兩個 JS（index-B7uhfiJ5.js、index-CP1wFNqW.js）及 pending 入口。舊 assets 未損壞，原 index.html 未替換；8140/liff 的 index SHA256 仍是 `B3252B5825E2AABA724BA04FB16E15FA423E98C6FD2D666311BB6AADA4FDDE9D`，與舊備份相符。

因此目前仍提供完整舊版，不需先還原或刪檔。保留現有備份與 pending 作證據。若後續發布失敗，修正後腳本會使用完整備份路徑原子還原入口，並核對還原雜湊；若還原本身失敗，會明確停止並列出備份位置，不宣稱完成。

## 最小修正

- 主腳本仍先核對實際服務 Python 路徑、專案根目錄、線上入口，維持正式編譯、產物檢查及整份 dist 備份驗證。
- 把入口發布／還原收在 frontend_publish.ps1，兩次 Replace 都明確傳入絕對備份檔名，不傳 `$null`。發布本身亦納入錯誤保護。
- 驗證路徑為絕對、檔案存在、不同檔案、pending 與 live 同目錄、備份在外部且內容吻合；拒絕連結路徑及非 index.html 目的地。
- 新 assets 若與舊檔同名但內容不同就停止；相同內容不覆寫，只新增不存在的檔案。入口只在 assets 驗證成功後切換，保留舊 assets。

## 驗證範圍

前端 106/106、tsc --noEmit、Vite 正式編譯通過（獨立 dist-deploy-fix-check-20261017，不寫正式 dist）。PowerShell 隔離測試涵蓋正常、空白、方括號、單引號／&、中文路徑、非法／相對／缺失路徑、備份不符、鎖檔與發布後驗證失敗還原。所有替換測試只操作新建暫存目錄，旁邊的資料哨兵維持原樣。

測試通過不代表正式部署已完成；管理員身分與手機驗收仍需本人執行。
