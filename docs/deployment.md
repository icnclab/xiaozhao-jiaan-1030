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
