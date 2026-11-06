# 小照／嘉安專題：Commit 前輕量級檢查

這個資料夾放的是版本控制的 Git Hook（`pre-commit`），對應 `CLAUDE.md` 要求的流程：
讀取需求 → 確認修改範圍 → 修改程式 → 執行測試 → 修正 → 驗證 → Git Commit。

## 這個 Hook 做什麼

- 執行一批**已確認不會連資料庫**的後端純邏輯／Mock 測試。
- 執行前端 `tsc --noEmit`（型別檢查）與 `vitest run`（Mock／jsdom 測試，不連真實資料庫）。
- 任何一項失敗就中止 Commit（`exit 1`），不會讓測試沒過的程式碼被提交。

**絕對不會**：連線任何資料庫、執行 Migration、部署正式環境、`git push`、發送真實 LINE／Web Push。

## 啟用方式（每台電腦要各自執行一次）

Git 預設不會自動套用 repo 內的 Hook 腳本，要先指定 Hook 路徑（這個設定只存在
本機的 `.git/config`，**不會被提交，也不會影響你電腦上其他 Claude Code 或 Git 專案**）：

```powershell
git config core.hooksPath .githooks
```

之後每次 `git commit`，Git 會自動先跑這個腳本。

## 停用方式

```powershell
git config --unset core.hooksPath
```

## 已知限制

- `SAFE_BACKEND_TESTS` 清單是手動維護的；新增同類型（不連資料庫）的測試檔後，
  要自己把檔名加進 `pre-commit` 腳本裡的清單，否則這個 Hook 不會自動執行它。
- 這個 Hook 刻意不執行會連資料庫的測試（例如 `backend/tests/conftest.py` 會用到
  的整合測試），所以通過這個 Hook **不代表**所有功能都驗證過，只代表「不需要
  資料庫就能驗證的部分」沒有壞掉。
