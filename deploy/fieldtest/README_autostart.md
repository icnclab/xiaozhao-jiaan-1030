# 嘉安小照 Windows PIN 登入後自動啟動（免密碼）

採用 Windows Task Scheduler：`Jiaan-Autostart`，固定使用 `stust\icncl`、最高權限、InteractiveToken 執行持續監控。設定為 **Run only when user is logged on**，只保留該使用者登入觸發，延遲 30 秒。PIN 登入即可，不要求、不使用、不儲存 Windows 密碼。IgnoreNew 與檔案鎖防止多個 supervisor。不需要 VS Code、手動開 Docker Desktop 或手動執行啟動器。PowerShell 子程序隱藏執行，原有 start_jiaan.ps1／status_jiaan.ps1 入口保留。

## 安裝（只做一次）

使用 PIN 登入 `stust\icncl`，開啟「系統管理員 PowerShell」，執行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\aa\ltc_care_installer_20260912\ltc_care\deploy\fieldtest\install_autostart.ps1"
```

不會要求 Windows 密碼，也不會讀取或儲存密碼。使用目前已登入帳號的 token；不採用 Password、S4U 或 SYSTEM。安裝須以 `stust\icncl` 的管理員 PowerShell 執行，並保有原 Docker／Ollama 存取權。一般 UAC 管理員同意視窗仍可能出現。

安裝會註冊排程並立即背景執行；`-NoStart` 可只註冊。若已有同專案的 `Jiaan-Autostart`，先停止並移除舊註冊（含舊 Password logon 憑證），再以同一名稱建立免密碼排程。只保留一個小照排程。排程執行無時間上限，允許電池供電。

### 上線時間與登入條件

PIN 登入後 30 秒啟動監控；服務原本健康時通常再需數十秒，Docker／CUDA／STT 冷啟動時先預留 2–5 分鐘，較慢的主機可能更久。這是估計，不是實測冷啟 SLA；以 health check 全 PASS 與手機測試成功判定上線。

本版本在使用者登入後才啟動。鎖定螢幕仍維持登入與監控；登出後無法保證服務／監控繼續運作，必須再次登入。`com.docker.service` 不等於 Linux Docker engine；監控呼叫 `docker desktop start --detach --timeout 20`，舊版 CLI 不支援時改為隱藏啟動 Docker Desktop.exe，再等待 `docker info`。不設定 Windows 自動登入、不搬移 DB、不自動更新 Docker、下載模型或變更 GPU 設定。

參考：[Docker Desktop settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)、[Docker Desktop start CLI](https://docs.docker.com/reference/cli/docker/desktop/start/)、[Task Scheduler registration](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/register-scheduledtask)、[Tailscale unattended](https://tailscale.com/docs/how-to/run-unattended)、[Funnel persistence](https://tailscale.com/docs/reference/tailscale-cli/funnel)。

## 啟動順序與重試

| 項目 | 就緒条件／啟動動作 | 單輪等待 |
| --- | --- | --- |
| Docker | 自動啟動 Desktop；docker info 成功 | 30 次，每次間隔 10 秒 |
| PostgreSQL／pgvector | 確認既有 ltc_care-db-1、Compose 標籤與 ltc_care_ltc_pgdata 掛載，再啟動既有 DB；healthy | 30 次，每次間隔 5 秒 |
| Ollama | /api/tags 可用；沒有既有 Ollama 或 11434 listener 才隱藏啟動 serve | 30 次，每次間隔 10 秒 |
| gemma4:e4b | /api/tags 出現精確名稱，/api/show 能取得 model_info；不自動 pull | 30 次，每次間隔 10 秒 |
| STT :8147 | 原 venv 啟動；ok、medium、cuda、medium 已 loaded | 30 次，每次間隔 10 秒 |
| API :8140 | 原 backend venv 啟動；db=ok、LINE real mode | 30 次，每次間隔 10 秒 |
| Worker | 身分符合原專案、僅一份程序、API 心跳年齡 <60 秒 | 啟動後約 60 秒等待，再由監控重試 |
| Tailscale | Windows 服務運作、已登入 Running、DNSName 為 stust.tailee6e4a.ts.net；設定 unattended | 30 次，每次間隔 10 秒 |
| Funnel | --bg HTTPS 443 -> http://127.0.0.1:8140 的持久配置 | 6 次，每次間隔 10 秒 |

以上時間另含每次 probe 的時間，並非精確總秒數。HTTP timeout 為 5 秒，模型 show 15 秒，native 指令預設 30 秒逾時；單次啟動器總上限 2 小時。模型一時未出現只記錄 WAIT，不在第一次缺失中止。

監控每輪結束等待 30 秒，再檢查所有服務；啟動失敗也持續下一輪。崩潰的 STT／API／Worker 會補啟；連續三輪不健康、且依賴正常時，僅對 stop_jiaan.ps1 身分驗證成功的自有程序重啟。Worker 重啟另要求 API 健康，避免 API／DB 故障造成誤殺。既有手動啟動、没有身分紀錄的程序會保留並記錄 REFUSED；不以 port 或 process name 強制殺程序。Ollama 已存在但無回應時持續等待，不強制殺掉可能由其他工作使用的 Ollama。

監控本身非正常退出時，Task Scheduler 在使用者已登入的條件下每分鐘重啟，最多 999 次；另有下次該使用者登入觸發。缺模型、DB identity mismatch、未登入 Tailscale 等不會被擅自「修復」為新資源。自動重試不保證這些設定問題能自行解除。

## 重開機驗證

1. 安裝後重開機，用 PIN 登入 `stust\icncl`。不要開 VS Code、Docker Desktop 或手動執行 start_jiaan.ps1。
2. 等待約 2–5 分鐘，用手機行動網路存取原 LIFF／小照，測試頁面、問答、語音。
3. 用管理員 PowerShell 查排程與健康狀態：

```powershell
Get-ScheduledTask -TaskName Jiaan-Autostart | Select-Object TaskName,State
Get-ScheduledTaskInfo -TaskName Jiaan-Autostart
$task = Get-ScheduledTask -TaskName Jiaan-Autostart
$task.Principal | Format-List UserId,LogonType,RunLevel
$task.Triggers | Format-List CimClass,UserId,Delay
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\aa\ltc_care_installer_20260912\ltc_care\deploy\fieldtest\health_jiaan.ps1"
Get-Content "C:\aa\ltc_care_installer_20260912\ltc_care\deploy\fieldtest\logs\autostart.log" -Tail 80
```

排程應為 Running，健康檢查的 Docker、DB、Ollama、Model、STT、API、WORKER、Funnel、FunnelBackground、Autostart 都應 PASS。長期執行的 task 可能呈現 LastTaskResult=267009（0x41301，正在執行），不是失敗。

Principal 應為 `stust\icncl`（或相同帳號 SID）、Interactive、Highest；只應有一個 LogonTrigger，該使用者且 Delay=PT30S，沒有 BootTrigger。GUI General 頁應選 Run only when user is logged on。核對 log 的啟動／PASS 時間與自己 PIN 登入時間。健康檢查只驗證本機與 Funnel 設定，不保證外網連線；仍需手機測試。`health_jiaan.ps1 -Json` 可輸出機器可讀 JSON。

## 日誌與診斷

- `logs\install.log`：安裝排程時間及帳號。
- `logs\autostart.log`：監控、重試、restart／refused exit code、健康摘要；10 MB 輪替為 .1。
- `logs\startup.log`：每個 dependency 的 PASS／WAIT 與啟動失敗原因；10 MB 輪替為 .1。
- `logs\stt.log`、`api.log`、`worker.log`：本啟動器啟動的服務輸出，保留既有日誌方式。
- `run\health.json`：最後完成一輪檢查的時間與狀態；檢查 CheckedAt，舊 snapshot 不代表現在健康。
- 若完全沒有新 log，先確認目前登入帳號為 stust\icncl、排程已啟用、只有該帳號 LogonTrigger；再看 Task History／Windows Event Viewer。此方案不需要 batch logon 密碼或憑證更新。
- 不要刪除 run 程序身分紀錄；停掉監控前直接 stop_jiaan.ps1 會被監控補啟。

## 卸載

管理員 PowerShell 執行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\aa\ltc_care_installer_20260912\ltc_care\deploy\fieldtest\uninstall_autostart.ps1"
```

只停止／移除小照排程。DB、模型、log、Tailscale unattended 與背景 Funnel 配置保留；已啟動程序是否仍在需再跑 status_jiaan.ps1，若要停止自有應用程序再執行 stop_jiaan.ps1。不自動關閉公開 Funnel，以免中斷原有小照服務。

## 已驗證與未驗證

免密碼修改後：Windows API 已確認 principal 為 stust\icncl／Interactive／Highest，trigger 為單一 MSFT_TaskLogonTrigger、stust\icncl、PT30S；readiness regression 全部通過。本次檢查沒有既有 Jiaan-Autostart 排程。工具執行環境沒有管理員 token，安裝器已正確拒絕註冊；請在本機管理員 PowerShell 執行上方安裝指令。實際安裝與重開機 PIN 登入尚待驗證。

2026-10-14：PowerShell 語法、模型第 4 次才出現、第 5 次重試耗盡、暫時 probe 例外、native stderr/exit code、native timeout、Windows 引數 quoting 的 regression test 通過。新版 start_jiaan.ps1 -AutoStart 實機執行成功，八項既有服務全 PASS；gemma4:e4b metadata 檢查通過，持久背景 Funnel 通過，既有程序保留。

測試指令（不啟停服務、不存取 production DB）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\aa\ltc_care_installer_20260912\ltc_care\deploy\fieldtest\tests\test_autostart.ps1"
```

免密碼安裝使用 InteractiveToken，只在 stust\icncl 登入時啟動；真實重開機後 PIN 登入觸發仍需測試。未修改 .env、production DB 資料、Gold dataset、RAG、QA policy 或 docker-compose.yml；保留既有 DB volume/container guard，不執行 migration、seed、restore、down -v 或建立替代 DB。
