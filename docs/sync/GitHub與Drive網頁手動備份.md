# 目前採用：GitHub 安全同步＋Drive 網頁手動備份

更新：2026-11-08，依本人最新決定取代 Drive API 啟用計畫。本文件是目前備份策略；既有 API／OAuth 教學保留作歷史與未來評估，不代表授權執行。

接續更新：78ff63e90412 的四份檔案已由本人回報上傳，**尚未重新下載驗證 SHA256**，見 [手動備份紀錄](GoogleDrive_手動備份紀錄.md)。新版核准隔離分支 publisher 與每日排程切換方式見 [安全隔離分支同步](安全隔離分支同步.md)；下方舊每日排程為改善前的查核紀錄，不代表新版結果。

## 啟用與停用範圍

- 保留既有 GitHub 排程／SessionEnd 安全同步：不自動 Commit，只處理已提交、明確標記穩定、測試與敏感掃描通過的版本。
- Google Drive 僅由本人登入實驗室帳號，在網頁將確認安全的交付檔案上傳到 `XiaoZhao/ApprovedSource`。
- 不使用 Google Cloud Console、Drive API、OAuth 或 Drive 自動排程；不安裝 Drive 電腦版、不碰 OneDrive。
- OAuth／Picker／probe 工具保留在遠端 `preparation/oauth-picker-uat-metrics-20261108`，commit `3effb91cfc2a8ea81df90549cd6074be64cd66cb`。不刪除、不部署、不執行授權／試傳；private driveEnabled 及人工確認旗標均保持 false。
- 不修改主目錄未提交內容、正式／UAT API、Worker、資料庫、LINE Webhook 或 Tailscale。

## GitHub 排程的實際狀態（本次唯讀核對）

`XiaoZhao-GitHubSyncDaily` Ready，每日 09:00，以 Windows PowerShell 執行主目錄的 `deploy/fieldtest/github_sync_check.ps1`。最近執行為 2026-11-08 09:00:01，Task result 0；但日誌 09:00:03 明確寫：**SKIP: tracked files have uncommitted changes**，因此該次沒有測試／推送成功證據，不能說已備份。

排程仍以主目錄為 RepoRoot，`.claude/github-sync.json` 目標是 `sync/stable-20261107-jiaan1030`。它只檢查主目錄 HEAD，不會監控所有分支或自動跟隨新隔離分支。主目錄目前 167 筆狀態保留，存在 tracked dirty，所以目前仍會 SKIP。本次沒有實際執行同步腳本，避免觸發測試、鎖檔清理或推送。

未來要由此機制真的同步新穩定版，必須同時符合：

1. 被檢查的工作區與目標分支正確；不能以為新隔離分支會自動被舊排程採用。
2. 已追蹤檔案沒有未提交內容；一般 untracked 草稿不會被自動加入，但其存在也不表示已備份。
3. HEAD 是已審核的 Commit，且有 `stable-ready-*` tag。
4. Git fetch、敏感掃描、後端／TypeScript／前端測試全通過。
5. 非 force push 成功，最後重新 fetch 的遠端 SHA 與本機 HEAD 相同，日誌實際出現 `OK: pushed ... verified match`。

另有鎖檔、缺設定、缺 stable tag、遠端已含版本等 SKIP；網路／授權、敏感命中、測試或非 fast-forward 失敗會停止。單看排程 Ready、result 0、每日執行或 SessionEnd 被觸發，均不能判定備份成功。主目錄需保留修改時，繼續在獨立 clone 逐檔審核提交與推送；不得為讓排程通過而整批 Commit、切主分支或清除修改。若未來需要排程處理隔離來源，先另提明確設定變更，不在本次更改原排程。

## 每個新穩定版本的交付規則（沿用既有匯出工具，不另開發）

1. 先確認私人 GitHub 遠端完整 Commit、穩定標記、測試／審核證據；沒有 stable-ready 與相符 receipt 的準備分支不能冒稱穩定版。
2. 使用既有 `tools/approved_sync/scripts/export_approved_snapshot.py` 從該不可變 Git commit 匯出白名單來源 ZIP，不讀未提交內容、不包整個資料夾。沿用敏感規則與審核表；任何疑似內容停止並人工審核，不自動放寬。
3. 產出 `xiaozhao_code_<SHA前12碼>.zip`、同名 `.zip.sha256`、`VERSION_<SHA前12碼>.md` 與 `LM_更新摘要_<SHA前12碼>_*.md`。版本說明記完整 SHA、分支／tag、檔案數、測試、範圍／限制及本機包 SHA256。已產出的同版包核對後沿用，不覆寫舊備份。
4. 檢查 ZIP 可解壓、manifest Commit／逐檔 hash／路徑與選檔規則，排除實際 .env、Token、client JSON、私人設定、訪談、個資、錄音、資料庫與未審核來源。只有明確無秘密的必要模板可依原審核規則保留。
5. 提醒本人手動上傳四個具名檔案至指定帳號與 `XiaoZhao/ApprovedSource`；不代按上傳、不以其他同步目錄代替。
6. 記錄狀態分開：`GitHub 遠端確認完成`、`本機交付檔已備妥`、`Drive 待本人上傳`。只有本人上傳後，再從 Drive 網頁下載 ZIP 回 STUST，SHA256 相同並留下版本、檔名、上傳／核對時間，才能標「Drive 下載核對通過」。畫面看到檔名不是內容驗證。
7. 下載損毀或上傳不確定就記失敗／待核對，不自動重複上傳、覆寫或刪除版本。不得把 GitHub 來源備份誤認為正式資料庫備份。
8. 重要程式、架構、模型、知識或備份政策改變時，另附不含機密的 LM 摘要，提醒本人審閱後交給 LM；不是自動傳送給 LM。

## 本次可手動上傳的既有穩定版

- 遠端分支 `sync/stable-20261108-handover-dual-api`。
- Commit `78ff63e9041243125e785e661f45c7f11fe3bcab`，tag `stable-ready-20261108-handover-dual-api`，本次唯讀確認三者相同。
- 來源 ZIP 356 檔；SHA256 `bf2dff594abc9e0071c709482ed385c1bfe07729eb621493385be9dd3c9f5e3c`。
- 檔案均在主目錄下 `run/handover-integration-20261108/approved-local-artifacts/`；完整檔名見同資料夾 VERSION 文件。
- OAuth／UAT 指標分支的 `3effb91cfc2a` 已備份至 GitHub，但沒有 stable-ready 標記，不取代上述穩定來源 ZIP。
- 本次未上傳 Google Drive，未啟用 API／OAuth／排程，也未重跑完整測試。
