# 請直接貼給 STUST 實驗室 VS Code Codex 的完整任務

請接續現有的「小照／嘉安 AI 長照助手」專題，不要重新建立、不覆蓋既有部署，也不要重複做已完成的驗證。Claude Code 額度不足，由你 Codex 接手。全程繁體中文。一般安全、可逆、非正式環境操作請自行執行，不必逐項問我。

## 已知現況（不是今日即時驗證結果）

- 正式主專案：`C:\aa\ltc_care_installer_20260912\ltc_care`。
- 正式 API `8140`、示範站 `8151`，正式資料庫 `ltc_clean`；不准動它們。
- GitHub 私人儲存庫：`https://github.com/icnclab/xiaozhao-jiaan-1030`。
- 已知完整穩定分支：`sync/stable-20261107-jiaan1030`，歷史 Commit `139887e60ebd9db1cdaea21a0c021931daeb822c`。另有 11/8 的公開端點與健康檢查 Token 安全修正分支，今日要重新核對。
- GitHub `main` 目前從我下載的 ZIP 只有原始骨架；**不要用 `main` 覆蓋完整專案，也不要強行合併無共同祖先的歷史**。
- 已存在的 GitHub 同步工具：`deploy/fieldtest/github_sync_check.ps1`、`.claude/github-sync.json`、`.claude/skills/github-sync/SKILL.md`，每日排程 `XiaoZhao-GitHubSyncDaily`（歷史記錄：09:00）。排程曾因主目錄未提交修改而跳過，不能把 exit 0 當成成功備份。
- 我的老師 GitHub 帳號：`chtsai-stust`；**實驗室 GitHub 上傳目的地**仍是 `icnclab/xiaozhao-jiaan-1030`，不是老師的個人首頁。邀請老師存取私人 Repository 需另行確認權限。
- 新的 LINE 官方帳號：**「小照 UAT 測試機器人」**；相關資訊已手動填入本機的 `uat.local.env`，應查清楚實際位置及是否被正確載入。不能輸出金鑰內容。
- 誌展 11/7 提供 `backend_handover_package 2.zip`，含 `mpc_core.py`、`iot_api_client.py`、5 個情境 JSON、三場真實訪談摘錄 JSON 和對接說明。這次我提供的工具包在 `handover_review/` 中只放了**不含真實訪談資料的參考檔**。
- 我已另外接通 ChatGPT 的 Google Drive，但這**不等於** STUST 上的實驗室 Google 帳號或同步磁碟已登入。

## 一、只讀盤點及保全（優先）

1. 檢查目前主專案 HEAD、分支、status（含 untracked）、worktree、remote URL，核對完整 FastAPI/React/RAG/LINE/LIFF/資料庫 Migration/測試/維運文件；只讀核對 GitHub 最新各分支，避免誤用骨架 `main`。
2. 從工具包 `README_先看.md` 和 `docs/交接差異與限制.md` 開始讀，先 `python -m unittest discover -s tests -v` 驗證工具包本身。找出工具包實際存放路徑；如果未解壓在 STUST，請說明需要我複製 ZIP 到哪個路徑。
3. 檢查現有 `github_sync_check.ps1`、Windows 排程、Claude SessionEnd Hook、Codex 觸發方式；不要重建已存在功能，不要誤把 09:00 排程的 SKIP 當備份成功。
4. 檢查 `uat.local.env` 是否存在、被 Git **實際忽略**、從未被追蹤/提交，UAT 是否讀取正確設定；僅回報變數名稱存在／缺少，禁止輸出值。
5. 檢查現有 GitHub/private repo 的敏感資訊風險及完整度，建立「本機有、遠端沒有／遠端分支已有／不該上傳」的具體檔案清單。嚴禁直接 `git add .`、`git add -A`、盲目上傳未知 ZIP。
6. 不得切換含未提交檔案的主工作目錄；必要改動一律隔離 clone/worktree，先留下 SHA 與差異報告。

## 二、補足完整 GitHub 程式（基於現有原始碼，不要重寫）

1. 以 STUST 的**實際運作程式**和已通過測試的穩定分支作基礎，比對所有必要的 `backend/`、`frontend/`、API、RAG、LLM、LINE LIFF、UAT、Migration、測試、文件與執行設定範例，將**可共享且必要**但尚未被 Git 追蹤的程式納入待審核清單。
2. 去重後補齊原始碼所需的非機密模板（例如 `*.example.env`，只能是空值或明確假值）、必要的套件清單、README、部署說明及 GitHub Actions；不要把正式環境 `.env`、`uat.local.env`、個資、原始資料、dump 當作「缺失」而上傳。
3. `main` 歷史不相關時不要強制合併；建立適合交老師的**清楚、完整、通過測試**的私人 GitHub 分支，核對遠端 commit。必要時另提議以 GitHub UI 將穩定分支設為預設分支，但不能未經我確認就變更私人權限或預設分支。
4. 稽核 `backend_handover_package 2`：原始 `mpc_core.py --quiet-test` 可通過 5 個合成情境，不代表完整整合；與現有 RAG／多角色權限／P0 安全路由比對。`iot_api_client.py` 缺 Pi 模組，不能直接部署。真實訪談 `real_interviews_extracted_samples.json` **不得進入 GitHub、Google Drive、LM**。
5. 將 MPC 整合設計/測試先放獨立分支與 UAT feature flag（預設關閉），不得改變正式系統的問答與緊急通知；如需資料庫變更或實際部署，**先提出差異與風險，不要直接執行**。

## 三、建立 GitHub + 實驗室 Google Drive 的雙重同步

目標：功能完成且通過測試後，將**同一個審核過的 Git Commit**保存在實驗室私人 GitHub，再保存在**實驗室帳號** Google Drive。新檔案必須被審核並 Commit 才能同步，不能把未完成修改或所有未追蹤檔自動傳出去。

1. 優先沿用既有 GitHub `github_sync_check.ps1`、Skills、Hooks 與 `XiaoZhao-GitHubSyncDaily`。不要製造第二套會跟舊機制競爭的自動 Commit／Push 程式。
2. 本工具包的 `scripts/sync_verified.py` 可在符合 stable-ready 標籤、正式測試與敏感資料檢查時呼叫既有 GitHub 同步腳本，再以 `git ls-remote` 和 `fetch` 驗證 **GitHub 真正存在的 Commit SHA**，將白名單原始碼 ZIP 備份到 Google Drive。它不會操作資料庫。
3. 先檢查實驗室電腦是否已有 Google Drive for desktop；如果有，請我**當場確認登入的是實驗室帳號**，並選取其「我的雲端硬碟」`XiaoZhao/ApprovedSource` 同步資料夾的實際路徑，不能只看磁碟代號。若無，評估已授權的 `rclone`（使用**實驗室** Google 帳號，認證由我完成；不額外購買服務）；不得把 OAuth Token 放在 Repo 或日誌。
4. 將 `config/sync_targets.template.json` 複製到 `%LOCALAPPDATA%\XiaoZhaoSync\sync_targets.local.json`（**不要提交 Git**）。首次 `allowGitHubAutoPush=false`、`driveAccountCheckedByHuman=false`，核對完才改真實值。
5. 先使用假 Git 儲存庫／假 Drive 目錄執行完整雙端試驗，再以 `--check-only` 只讀確認真的私人 GitHub，最後在我核對實驗室 Google Drive 帳號及目標資料夾之後，執行一次真正備份。
6. 正式備份以**每個穩定 Commit 一份版本化 ZIP**保留歷史。先確認 Repo 所有要分享的檔案符合團隊授權，包含經審核的前端／後端／必要測試／文件。對可疑來源、真實個資、音檔、資料庫 dump、LINE 金鑰、Web Push 私鑰，一律拒絕；絕不為方便上傳而關閉保護。
7. Google Drive for desktop 只保證複製至同步資料夾、SHA256 一致；**還要在雲端網頁實際看見檔案或 Google Drive 客戶端上傳完成，才能報告成功上雲**。如果選 rclone，使用遠端 checksum 核對成功才標記雲端完成。
8. 驗證全部通過後，沿用既有 Hook／觸發器，補足 Windows 每 15 分鐘固定檢查（`scripts/install_schedule.ps1` 已備）。先檢查是否已存在同名或等效工作排程，不得重複。系統關機／未登入時無法保證 15 分鐘同步；應記錄實際執行結果與補跑策略。
9. 每次測試、上傳、跳過均應留本機不含密碼的 JSONL 記錄，並列出 GitHub SHA、Drive 快照 ZIP SHA256、已確認或待雲端確認狀態。
10. 每個新 Commit，產生不含敏感資訊的 `待交給LM學習_<commit>.md` 提醒我把**新增知識、程式架構、測試結果、功能變更**依我原本交給 LM 的規則提供學習；**不得自行將真實訪談或程式秘密上傳到 LM**。

## 四、小照 UAT 測試機器人

1. 確認 `uat.local.env` 的實際路徑、格式與載入方式，不印出 Secret 或 Token。
2. 確認 UAT 使用獨立 LINE 官方帳號／Channel Secret／Channel Access Token／Webhook URL（HTTPS）。不得默認它已經接上正確的 Webhook。
3. UAT 必須隔離正式 LINE、正式 `ltc_clean`、正式 API 8140、正式 Funnel 與任何真人個資。
4. 先用 mock／合成資料測試 LINE/LIFF 角色、綁定與事件流程；正式的 UAT Webhook 變更及測試訊息送出，須在列出目標、影響與回滾方案後再由我確認。

## 五、不可違反的限制

- 不得擅自停止、重啟、部署 API 8140、Worker、8151，操作 `ltc_clean` 或執行 Migration。
- 不得修改 Tailscale Funnel、防火牆、正式 LINE Webhook；不得 push 到 `main`、force push、reset --hard、git clean、覆寫其他 worktree。
- 不得上傳 `.env`、`uat.local.env`、金鑰、Token、訪談逐字稿、個資、原始錄音、正式 SQL Patch、資料庫備份、尚未審核的機構資料。
- 不得使用中國大陸開發的 AI 模型／工具或額外付費 API；不需要安裝 Kimi/Agent Swarm。
- GitHub 的既有測試若失敗，不要降低斷言、跳過測試、用 `--no-verify`，應修復或保留未上傳並回報。
- 不得僅靠 GitHub 版本就聲稱正式資料庫或執行中的程式已備份／更新。
- 若發現權限問題、Google Drive 登入錯帳號、敏感資料外洩、需要修改正式環境或不可逆操作，請停止該高風險步驟，其他安全工作照常繼續。

## 六、完成後一次回報

以繁體中文清楚列出：

1. **GitHub**：目前完整度（哪些缺失已補）、遠端分支／Commit／URL、老師 `chtsai-stust` 是否能讀取（若需要邀請，告訴我點選步驟）。
2. **交接整合**：哪些 MPC／IoT 功能已經進入 UAT、哪些只是參考，測試結果及未完成依賴。
3. **LINE UAT**：獨立帳號和設定是否載入、Webhook 是否完成驗證、有無可能碰正式資料。
4. **Google Drive**：實驗室帳號核對方式、實際路徑／備份檔案／SHA、**是本機已複製還是雲端已上傳驗證**。
5. **自動同步**：Hooks、排程、每多久檢查、觸發條件、失敗阻擋、實際端對端測試證據、是否需要人工操作。
6. **LM**：哪些新的知識／程式／架構要提醒我交 LM 學習，產出不含敏感資料的更新摘要。

**優先順序：保全現況 → GitHub 完整性 → MPC 交接差異 → UAT 隔離 → Google Drive 身分與備份 → 自動化 → LM 摘要。**
