---
name: github-sync
description: 小照／嘉安私人 GitHub（icnclab/xiaozhao-jiaan-1030）安全同步流程。每次完成穩定功能、要把本機程式推上 GitHub 時使用；也用於有人問「可以同步 GitHub 了嗎」「這次改動能不能推上去」時。
---

# 小照／嘉安 GitHub 安全同步 Skill

## 背景
- 私人 repo：`https://github.com/icnclab/xiaozhao-jiaan-1030`（Private）。
- GitHub 上的 `main` 目前只是初始骨架 commit，和本機完整開發歷史**沒有共同祖先**（不同歷史）。
- 本機通常同時存在：真正要同步的程式、.before_* 備份檔、未知來源 zip、正式 SQL Patch／資料庫備份／還原紀錄、真實訪談逐字稿、展示用錄音文件、金鑰檔。只有第一類該進 GitHub。

## 固定流程：檢查修改 → 測試 → 敏感資訊掃描 → Commit → Push → 遠端確認

### 1. 檢查修改
```
cd C:\aa\ltc_care_installer_20260912\ltc_care
git status
git remote -v
git fetch origin
git merge-base origin/main HEAD   # 失敗代表歷史仍無關聯，不能對 main 做 fast-forward/merge
```
逐一分類未追蹤檔案：程式／測試／文件 → 保留；`.before_*` 備份、未知 zip、`*production_patch*.sql`、`*production_schema_review*`、`restore_log.txt`、`data_demo/`、`docs/interviews/`、金鑰（`*.key` `*.pem`）→ 加進 `.gitignore`，不要刪除原始檔。

### 2. 測試（必須全部實際執行，不可只憑 import 成功宣稱通過）
```
cd backend && .venv/Scripts/python.exe -m pytest -q
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run --environment jsdom
```
三項都要看到實際通過（exit code 0 / 測試數與 passed 數），任何一項失敗就停止，不得降低標準讓測試通過。

### 3. 敏感資訊掃描
```
# 掃描「這次要加入」的內容，不是只看工作目錄現狀
git diff --cached -G'AKIA[0-9A-Z]{16}|BEGIN (RSA|PRIVATE|OPENSSH) PRIVATE KEY|xox[baprs]-|postgresql://[^@]*:[^@]*@|password\s*=\s*"[^"$]|api[_-]?key\s*[:=]\s*"[^"$]' --stat

# 歷史若有新 commit 要首次推送，額外掃一次全歷史
git log --all -G'BEGIN (RSA|PRIVATE|OPENSSH) PRIVATE KEY|AKIA[0-9A-Z]{16}|xox[baprs]-|postgresql://.*:.*@' --oneline
```
掃到就停下，回報，不要自行決定要不要推送含密碼／金鑰的內容。

### 4. Commit（明確檔案清單，不用 `git add .` / `git add -A`）
```
git add <明確列出每個要加入的路徑>
git commit -m "<說明這次穩定變更>"
```
Commit 會自動觸發 `.githooks/pre-commit`（前端 tsc + vitest + 一批不連資料庫的後端純邏輯測試），失敗會中止 commit。

### 5. Push：永遠推到新分支，不直接動 main
```
git checkout -b sync/stable-YYYYMMDD-<主題>
git push -u origin sync/stable-YYYYMMDD-<主題>
```
- 不 force push、不 reset --hard、不刪遠端分支／歷史。
- 若要推已存在的分支，先 `git fetch origin` 確認沒有別人推過的新 commit，不確定就不要覆蓋，改開新分支名。

### 6. 遠端確認
```
git fetch origin
git rev-parse HEAD
git rev-parse origin/<分支名>
# 兩者必須相同才算同步成功
```

### 7. 若同步前你原本分支（如 experiment/...）上有未提交的修改
不要用 `git checkout <其他分支>` 直接切換（這會讓 git 把工作目錄「安全地」還原成目標分支的舊內容，看起來像是修改消失，其實是因為已經在別的分支 commit 過，git 認定可以覆蓋）。若需要兩邊都保留原始未提交狀態：
```
git checkout <新分支> -- .   # 把剛剛 commit 的內容複製回工作目錄
git reset                    # 取消暫存，恢復成原本「M / ??」的未提交狀態
```
每次切換分支前後都用 `git status` 確認未提交檔案的數量與清單沒有變少。

## 停止條件（不得自動繼續，必須回報）
- 沒有私人 repo 存取權限，或 `gh auth status` 顯示未登入 / token 權限不足。
- 敏感資訊掃描掃到疑似真實金鑰、密碼、個資。
- GitHub 歷史與本機history 不同，且必須靠 merge/rebase/force 才能處理。
- 任何一項測試失敗且無法在安全範圍內修正。

## 自動化（2026-11-07 建立）

已有兩個觸發點會自動執行 `deploy/fieldtest/github_sync_check.ps1`：
1. Claude Code `SessionEnd` hook（`.claude/settings.local.json`，本機專用、未進 git）。
2. Windows 工作排程器 `XiaoZhao-GitHubSyncDaily`，每天本機時間 09:00、以目前使用者（非系統管理員）身分執行，只有在這台電腦開機且該使用者已登入時才會跑；離線或關機不會補跑，也不會假裝跑過。

兩者共用同一支腳本與同一個鎖檔 `.claude/github-sync.lock`（20 分鐘內視為執行中，超過視為過期鎖並清除），不會互相搶跑。

### 「穩定」判斷方式：明確的 git tag，不是猜測
腳本本身**不會**自動 commit，也不會自己判斷「這次改動算不算穩定」。要讓自動化去同步某個 commit，必須：
1. 該 commit 已經是目前分支 HEAD。
2. 工作目錄裡「已追蹤檔案」沒有未提交修改（`git status --porcelain --untracked-files=no` 必須為空；本專案長期存在的未追蹤草稿檔案──zip、`.before_*`、`restore_log.txt` 等──不影響這個判斷，因為它們本來就不會被 push）。
3. 在 HEAD 上打一個 `stable-ready-*` 開頭的 tag，例如：
   ```
   git tag stable-ready-20261110-ga09-form
   ```

符合以上三點時，下一次 SessionEnd 或每天 09:00 的排程就會自動：抓遠端 → 確認這個 commit還沒在目標分支（`.claude/github-sync.json` 的 `branch` 欄位，目前是 `sync/stable-20261107-jiaan1030`）→ 對要推送的差異做敏感資訊掃描 → 跑 `pytest` / `tsc --noEmit` / `vitest` → 全過才用 `git push origin HEAD:<branch>`（不 force）→ push 完再 `git fetch` 確認遠端真的對得上。任何一步沒過，就只寫 log 到 `deploy/fieldtest/logs/github_sync.log`，不會繼續、不會重試、不會自己降級標準。

### 不會自動發生的事
- 不會自動 commit 未提交的修改。
- 不會自動幫你打 `stable-ready-*` tag——這一步永遠是人（或這個 Claude Code 工作階段）確認過才做的明確動作。
- 不會 force push，不會對 `main` 動手，不會推沒打過 tag 的 commit。
- 排程只在開機且使用者已登入時執行；不保證離線或關機期間的「補跑」。

### 除錯
- 看 `deploy/fieldtest/logs/github_sync.log`（純文字、不含密碼/金鑰細節，只會寫「掃到了，擋下」這種結論）。
- 排程任務狀態：`Get-ScheduledTask -TaskName XiaoZhao-GitHubSyncDaily | Get-ScheduledTaskInfo`。
- 手動重跑一次：`powershell -File deploy\fieldtest\github_sync_check.ps1`。
