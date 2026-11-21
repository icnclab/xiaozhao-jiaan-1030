> Current production: STUST; PUBLIC_BASE_URL=https://stust.tailee6e4a.ts.net.
> Tailscale Funnel forwards to http://127.0.0.1:8140. Launcher: deploy/fieldtest/start_jiaan.ps1.
> The 24H host / Cloudflare instructions below are historical and do not apply to STUST.
> deploy/deploy24h_setup.ps1 now delegates to the STUST launcher without installation, data restore or old ingress changes.

# 部署與 LINE／LIFF 設定

## 1. 環境

| 環境 | 說明 | 狀態 |
|---|---|---|
| 開發機（ROG-HOME） | WSL Docker 跑 PostgreSQL；API／worker／Vite 跑在 Windows 主機；Ollama、faster-whisper sidecar、SAPI 本機 | ✅ 已跑通 |
| Docker Compose（`--profile app`） | api、worker、web(nginx)、db 全容器化；推論預設 extractive／hash／mock | ⚠ compose 檔已寫，**本機未建置映像驗證**（此機 Docker 只在 WSL，映像建置需在 WSL 內執行） |
| 機構核可主機／中華電信 hicloud | 部署目標 | ⬜ 未驗證；無帳號與規格 |
| 無 Docker（WSL2 原生 PostgreSQL） | PostgreSQL 16＋pgvector 直接裝在 WSL2 `Ubuntu-22.04`（非容器），監聽 `127.0.0.1:55432`；Ollama、STT sidecar（CUDA）、API／worker 皆跑在 Windows 主機。一鍵啟動：`start_all_no_docker.ps1` | ✅ 2026-11-21 已驗證資料筆數與 Docker 版正式庫一致 |

## 2. 正式環境必要設定

- `APP_ENV=production`：停用 dev-login 與 `/api/dev/*` 模擬端點；缺 `SECRET_KEY`、`DATA_ENCRYPTION_KEY`、`LINE_CHANNEL_SECRET` 會拒絕啟動。
- `PUBLIC_BASE_URL=https://<host>`：LINE 音訊訊息要求 HTTPS（TLS 1.2+）的 `originalContentUrl`；TTS 播放 URL 由此產生。
- 反向代理必須**原樣轉送 request body**（簽章驗證用），並保留 `X-Line-Signature` header（`frontend/nginx.conf` 已處理）。
- `DATA_DIR` 掛持久化卷；音訊暫存、TTS 檔、上傳原檔都在此，清理由 worker 的 retention sweep 執行。
- 備份：PostgreSQL（含向量與稽核）＋ `DATA_DIR/documents`（上傳原檔）。

## 3. LINE 設定步驟（真實模式）

1. LINE Developers Console 建立 **provider**；在同一 provider 下建立 **Messaging API channel** 與 **LINE Login channel**（不同 provider 的 userId 不一致，帳號會對不上）。
2. Messaging API channel：
   - 取得 **Channel secret** → `LINE_CHANNEL_SECRET`；發行 **Channel access token** → `LINE_CHANNEL_ACCESS_TOKEN`。
   - Webhook URL：`https://<host>/api/line/webhook`，開啟 Use webhook；關閉自動回覆訊息。
   - Rich menu（LINE Official Account Manager）：五格分別送出文字「問 AI」「錄音」「問題分類」「我的案件」「使用說明」（bot 會回 LIFF 連結），或直接設為 LIFF URL。
3. LINE Login channel：新增 **LIFF app**，Endpoint URL `https://<host>/liff`，Scope `openid profile`，Size Full → `LIFF_ID`；Channel ID → `LINE_LOGIN_CHANNEL_ID`。
4. `.env`：`LINE_MODE=real`，填上述四個值與 `PUBLIC_BASE_URL`；重啟 api 與 worker。
5. 驗證：Console 的 Verify webhook 應回 200（簽章由 LINE 產生）；加好友後收到歡迎訊息；管理員在後台為照服員產生綁定碼，照服員開 LIFF 輸入綁定。
6. 推播額度：免費方案每月推播有上限（依 LINE 官方方案）；超額回 429，通知會標 `failed/rate_limited_or_quota`，回覆本身不受影響。

## 4. 中華電信 STT／TTS 與 hicloud（未串接）

- `backend/app/providers/stt.py::ChtStt`、`tts.py::ChtTts` 為保留 adapter；設定鍵 `CHT_STT_ENDPOINT`、`CHT_TTS_ENDPOINT`、`CHT_API_KEY`。
- 尚未取得官方 API 規格與憑證，**未實作請求格式，呼叫會明確報錯**；不虛構 endpoint。
- 串接時須確認：音訊格式與取樣率、同步／非同步模式、資料保存條款（原音是否暫留）、熱詞（法規名、條號）支援。

## 5. 執行程序（Windows 主機常駐，可比照本機其他系統用工作排程器）

| 程序 | 指令 | 說明 |
|---|---|---|
| API | `backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8140` | 反向代理（nginx／Cloudflare Tunnel）在前 |
| worker | `backend\.venv\Scripts\python.exe -m app.worker` | 可多開；心跳寫入 `worker_heartbeats` |
| STT sidecar | `venvs\asr\Scripts\python.exe services\stt_sidecar\server.py --port 8147 --model medium` | 10 GB 顯存與 LLM 共用時用 `medium`；只跑 STT 可用 `large-v3` |
| Ollama | `ollama serve`（`LLM_MODEL` 需已 pull） | 服務啟動時會預熱模型 |

埠位：8140（api）、8141（web 容器）、8147（stt）、5173（vite dev）。本機 winnat 保留埠清單見 `tools/fix_winnat_ports.ps1`（8040 已被其他系統占用，故本專案用 81xx）。

## 6. 硬體與模型取捨（開發機實測）

- RTX 3080 10 GB：`gemma4:e4b`（3.2 GB）＋ faster-whisper `large-v3` fp16（約 3 GB）＋桌面共約 9.7 GB → LLM 生成明顯變慢並逾時；改 `medium` 後約 8 GB，第一題含檢索與驗證 < 10 秒。
- Ollama 若被 client 端逾時中斷，伺服器端生成仍會繼續並排隊後續請求；已設 `num_predict=400` 限制單次輸出，避免失控生成拖垮後續問答。
- 沒有 GPU：`LLM_PROVIDER=extractive`（摘錄模式，仍附出處）、`STT_PROVIDER=mock` 或 CPU 版 sidecar（`--device cpu`，慢）。

## 7. 24H 部署機（deploy-24h）與安裝包

- 安裝包：`deploy/install/build_package.ps1` 在開發機打包（離線 wheels＋前端 dist＋ffmpeg）；目標機解壓後跑 `deploy\install\install.ps1`（Python 3.11/3.12＋Docker 即可），`start.ps1` 啟動、`stop.ps1` 停止；細節見 `deploy/install/README_安裝.md`。
- 部署機落地：`deploy/deploy24h_setup.ps1`（scp 到 `F:ppdata\ltc_care\` 後以 `-File` 執行；**檔案須含 UTF-8 BOM**）。公網入口 `https://ltc.icnclab.net`（既有 Named Tunnel 加一條 ingress → `localhost:8140`；ingress 檔在 `C:\Windows\System32\config\systemprofile\.cloudflared\config.yml`，改完要重啟 cloudflared 服務並以 `cloudflared tunnel info` 確認 connector）。
- 常駐：排程 `LTC Serve`（登入觸發、無時限）；無人登入時由 WMI `Win32_Process.Create` 起 `start.ps1`（不綁 ssh session）。LINE：`backend/scripts/line_preflight.py --set-webhook --test-webhook` 把 webhook 指到 `https://ltc.icnclab.net/api/line/webhook`；LIFF Endpoint 須在 LINE Console 手動改為 `https://ltc.icnclab.net/liff`（LIFF 更新 API 需 Login channel 的 token，本專案未保存）。
- 切換後家中機的 Quick Tunnel 不再收 webhook（一個 channel 只能有一個 webhook URL）；本機開發回到 `LINE_MODE=mock`。

## 8. 無 Docker（WSL2 原生 PostgreSQL + RTX 3060 GPU）部署架構

> 2026-11-21 完成：去 Docker 化，`ltc_clean` 資料已完整遷移並核對筆數一致；仍保留 Docker 映像與資料卷作為備援，未刪除。

### 8.1 系統與硬體環境

| 項目 | 規格／設定 | 狀態 |
|---|---|---|
| 作業系統 | Windows + WSL2（`Ubuntu-22.04`） | ✅ |
| GPU | NVIDIA GeForce RTX 3060，12GB VRAM | ✅ `nvidia-smi` 確認 |
| 系統 RAM | 16GB | ✅ |
| WSL2 記憶體上限 | `C:\Users\<USER>\.wslconfig`：`[wsl2]` 區塊加 `memory=6GB`，避免 `VmmemWSL` 吃光主機板記憶體 | ✅ 本機已套用（`.wslconfig` 現存內容已是 `memory=6GB`） |
| Windows 快速啟動／休眠 | 建議關閉：系統設定「電源選項」取消「啟用快速啟動」；或 `powercfg /hibernate off` | ⬜ 建議設定，**尚未在本機套用**；關閉後會釋放等同實體記憶體大小的 `hiberfil.sys` 空間，但失去休眠功能，請自行評估後執行 |

### 8.2 無 Docker 服務架構與 Port 分配

| 服務 | 技術 | Port | 說明 |
|---|---|---|---|
| 資料庫 | WSL2 原生 PostgreSQL 16 ＋ `pgvector 0.8.6`（**非**容器，手動解壓 pgdg 二進位安裝，未走 apt／systemd） | `0.0.0.0:55432`（`postgresql.conf` `listen_addresses='*'`），`pg_hba.conf` 僅允許 `127.0.0.1/32`、`::1/128`、`172.16.0.0/12`、`192.168.0.0/16`（WSL2 內部網段） | 正式庫 `ltc_clean`；資料目錄 `/var/lib/pgsql16/data`；二進位 `/opt/pgsql16/usr/lib/postgresql/16/bin` |
| LLM／Embedding | Windows 主機原生 Ollama，模型 `gemma4:e4b`，100% 載入 RTX 3060 VRAM | `127.0.0.1:11434` | **嚴禁**設成 Windows 開機 Startup 自動啟動——開機常駐會在背景被觸發載入模型，佔用主機板系統 RAM（而非只佔 VRAM）；一律手動 `ollama serve` 或由 `start_all_no_docker.ps1` 依需求啟動 |
| STT（語音辨識） | `services/stt_sidecar/server.py`，`faster-whisper`，強制 `--device cuda` | `127.0.0.1:8147` | 跑在 RTX 3060 GPU；`--model medium`（與 LLM 共用顯存時的實測取捨，見第 6 節） |
| 後端 API／Worker | FastAPI + Uvicorn（`backend\.venv`），原生 Python 行程 | API `127.0.0.1:8140` | 連線 `DATABASE_URL=...@127.0.0.1:55432/ltc_clean`、Ollama `http://127.0.0.1:11434` |

### 8.3 一鍵啟動與日常維運指令

- **完整啟動**（專案根目錄）：
  ```powershell
  .\start_all_no_docker.ps1
  ```
  依序檢查並啟動：WSL PostgreSQL（55432）→ Ollama（11434）→ STT CUDA sidecar（8147）→ API（8140）→ Worker；每一步都先檢查該 port 是否已在監聽，已在跑則保留不重複啟動，最後印出 API `/api/healthz` 與 STT `/healthz` 的健康檢查結果。

- **單獨檢查／啟動 WSL PostgreSQL**（本環境未註冊為 systemd 服務，`service postgresql status/start` **不適用**；請用下列實際指令）：
  ```powershell
  # 檢查是否在跑（監聽 55432）
  wsl -d Ubuntu-22.04 -- bash -c "pg_isready -h 127.0.0.1 -p 55432 2>&1 || echo NOT_RUNNING"

  # 啟動
  wsl -d Ubuntu-22.04 -- bash -c "sudo -u postgres env LD_LIBRARY_PATH=/opt/pgsql16/icu72/usr/lib/x86_64-linux-gnu /opt/pgsql16/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/pgsql16/data -l /var/lib/pgsql16/pg16.log start"

  # 停止
  wsl -d Ubuntu-22.04 -- bash -c "sudo -u postgres env LD_LIBRARY_PATH=/opt/pgsql16/icu72/usr/lib/x86_64-linux-gnu /opt/pgsql16/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/pgsql16/data stop"
  ```

- **驗證 GPU 顯存佔用**：
  ```powershell
  nvidia-smi
  ollama ps   # 確認 gemma4:e4b 的 PROCESSOR 欄位顯示 100% GPU，而非 CPU
  ```

### 8.4 資料庫備份與還原（災難復原 SOP）

備份（從 Windows PowerShell 透過 `wsl` 執行，輸出到專案外目錄，**不得**放進 Git 版控）：
```powershell
wsl -d Ubuntu-22.04 -- env LD_LIBRARY_PATH=/opt/pgsql16/icu72/usr/lib/x86_64-linux-gnu `
  /opt/pgsql16/usr/lib/postgresql/16/bin/pg_dumpall -h 127.0.0.1 -p 55432 -U postgres `
  > "$HOME\Desktop\ltc_care_backup_$(Get-Date -Format yyyyMMdd_HHmmss).sql"
```

還原（還原到一個**乾淨、全新**的叢集；不得對正式叢集直接套用整庫還原，風險請先與使用者確認）：
```powershell
wsl -d Ubuntu-22.04 -- env LD_LIBRARY_PATH=/opt/pgsql16/icu72/usr/lib/x86_64-linux-gnu `
  /opt/pgsql16/usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -p 55432 -U postgres -f <備份檔路徑> postgres
```

- 大型 `.sql` 備份檔（如完整 `pg_dumpall` 輸出，常見 >100MB）**不得**提交進 Git（會超過 GitHub 單檔 100MB 限制且含真實個案資料），一律搬到專案目錄外（例如 `C:\Users\<USER>\Desktop\ltc_care_migration_backup\`）保存；`.gitignore` 已排除 `*.tar.gz`、`*.zip`、`db_migration_backup.sql` 等已知大型遷移檔名。
- 還原前務必先核對目標資料庫與備份檔的筆數／表結構（見第 3 階段遷移時使用的逐表 `count(*)` 核對方式），禁止盲目覆蓋正式庫。
