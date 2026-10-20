# 長照 AI 照護小幫手「小照」— 安裝說明（實驗室／個人電腦版）

> 解壓後整個資料夾就是系統；資料放在同一資料夾內（`data\`、`logs\`），刪掉資料夾＝解除安裝（資料庫在 Docker volume，另需 `docker compose down -v`）。

## 需要先有的東西

| 項目 | 必要？ | 說明 |
|---|---|---|
| Windows 10/11 64 位元 | 必要 | PowerShell 5.1 以上（內建） |
| Python 3.11 或 3.12 | 必要 | https://www.python.org/downloads/ ，安裝時勾選 **Add python.exe to PATH** |
| Docker Desktop（或 WSL 內已裝 docker） | 必要 | 只用來跑 PostgreSQL＋pgvector 資料庫；https://www.docker.com/products/docker-desktop/ 安裝後**要先打開一次** |
| ffmpeg | 內建 | 安裝包 `bin\` 已附；若沒有，安裝腳本會用 winget 裝 |
| Ollama＋模型 | 選用 | 沒有就走「摘錄模式」（不生成、只摘錄條文、仍附出處）。要用 LLM：安裝 https://ollama.com → `ollama pull gemma4:e4b` |
| NVIDIA GPU | 選用 | 語音辨識加速；沒有 GPU 也能用 CPU 跑 `small` 模型 |
| 網路 | 安裝時不需要 | 除非要裝語音辨識（`-WithStt`）或拉 LLM 模型 |

## 安裝（3 步）

1. 解壓 `ltc_care_installer_<日期>.zip` 到**不含中文與空白**的路徑，例如 `D:\ltc_care`。
2. 在該資料夾按 Shift＋右鍵 →「在此處開啟 PowerShell」，執行：
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\install\install.ps1
   ```
   要一併裝語音辨識（需網路，下載約 1.5 GB）：加 `-WithStt`；要順便拉 LLM 模型：加 `-PullModel`。
3. 啟動：
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\install\start.ps1
   ```
   照服員端 <http://127.0.0.1:8140/liff>（瀏覽器開發者工具切成手機尺寸較好看）、督導後台 <http://127.0.0.1:8140/admin>。

帳號密碼：安裝時印在畫面上，也存於 `logs\seed.log` 所指的檔案。全部是合成資料、虛構機構。

## 常用指令

| 目的 | 指令 |
|---|---|
| 停止 | `powershell -ExecutionPolicy Bypass -File deploy\install\stop.ps1` |
| 健康檢查 | `powershell -ExecutionPolicy Bypass -File deploy\install\status.ps1` |
| 重建展示資料 | `install.ps1 -ResetDemo` |
| 跑測試 | `backend\.venv\Scripts\python.exe -m pytest backend\tests`（需 db 在跑） |
| 跑 25 題初測 | `backend\.venv\Scripts\python.exe backend\scripts\eval_run.py --llm extractive` |
| 改設定 | 只改 `.env`；改完重跑 `stop.ps1`＋`start.ps1`。改單一鍵可用 `backend\.venv\Scripts\python.exe backend\scripts\env_set.py KEY=value` |

## 接真實 LINE（可選）

見 `docs\line-setup-checklist.md`。Messaging API channel 與 LINE Login channel 建在**同一 provider**；`.env` 填 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_LOGIN_CHANNEL_ID`、`LIFF_ID`，`LINE_MODE=real`；需要 HTTPS 公網入口（`start.ps1 -Tunnel` 會開一條 Cloudflare 臨時通道，網址每次不同，須到 LINE Console 更新 webhook 與 LIFF endpoint）。

## 常見問題

- **找不到 Python 3.11 或 3.12**：裝好 Python 後關掉 PowerShell 重開。
- **資料庫未就緒**：Docker Desktop 沒開，或 55432 埠被占用（改 `-DbPort 55433`）。
- **語音上傳回「找不到 ffmpeg」**：`.env` 的 `FFMPEG_DIR` 應指向 `bin\`；或把 ffmpeg 加到 PATH 後重啟。
- **回答都是「摘錄模式」**：沒偵測到 Ollama 模型；裝好後把 `.env` 的 `LLM_PROVIDER` 改 `ollama`。
- **畫面頂端出現「模擬登入／line=mock」**：正常，代表未接真實 LINE。
