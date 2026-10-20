小照｜2026/10/17 嘉安場測

2026/10/14 更新：開機自啟與持久背景 Funnel 請依 README_autostart.md 安裝。
以下保留原場測手動操作紀錄；完成自啟安裝後不需人工開 Docker 或執行 start_jiaan.ps1。

一、出門前啟動
使用目前已驗證 LINE、STT、TTS 的 Windows 帳號。先開 Docker Desktop，等待啟動完成。
開「系統管理員 PowerShell」，執行：
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\aa\ltc_care_installer_20260912\ltc_care\deploy\fieldtest\start_jiaan.ps1"
腳本只處理 aa，不下載模型、不改 .env、不建立排程、不改 Funnel。
第一次接管前，已有的服務會保留；不要先關掉原本的服務視窗。

二、看結果
Docker、DB、Ollama、Model、STT、API、WORKER、Funnel 八項都要 PASS。
FAIL 時不要出門，查看畫面原因及 logs\startup.log。
API／Worker／STT 啟动錯誤分別看 logs\api.log、worker.log、stt.log。
已有手動服務的日誌仍在原視窗，不一定寫入這裡。
FAIL 不會停止其他已健康服務。不要連續點擊期待修復；先看原因。
PASS 只是本機健康與 Funnel 設定檢查，最後一定要做手機外網測試。

三、哪些視窗可以關
本腳本跑完後，啟動器及純檢查視窗可以關。它啟動的 API、Worker、STT 在背景執行。
原本手動啟動的 API、Worker、STT、前景 Funnel 視窗不可關。
不確定哪個視窗屬於舊手動服務，就先保留。
Docker Desktop、Ollama、Tailscale 必須保持運作。電腦不要登出、關機、睡眠或休眠。
留在實驗室持續供電及連網；人離開時鎖定螢幕即可。

四、只查看狀態
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\aa\ltc_care_installer_20260912\ltc_care\deploy\fieldtest\status_jiaan.ps1"
不啟動或停止服务。若程序資訊讀不到，使用管理員 PowerShell。
Worker 心跳只代表最近有 Worker 回報，不代表每個工作都成功。

五、手機最終測試
關 Wi-Fi，改用 4G／5G。
從正式 OA Rich Menu 開 LIFF，確認登入與帳號綁定。
問一題已通過的規範題，查看原文、下載原始檔。
錄一小段語音，確認轉文字；播放 TTS。
送交督導並完成回覆，確認照服員收到通知。
成功後才出門。人在嘉安只需使用 LINE，STUST 主機持續運作。

六、Funnel FAIL
本腳本不會修改 Funnel。先確認原本前景 Funnel 視窗是否仍在。
若確定沒有運作，在另一個管理員 PowerShell 人工執行：
& "C:\Program Files\Tailscale\tailscale.exe" funnel http://127.0.0.1:8140
保持该視窗開啟，再跑狀態檢查及手機行動網路測試。
不要在已正常的 Funnel 上重複執行，不用舊 Cloudflare 腳本。
持久化 --bg 與開機自啟留待後續安排，本輪腳本不處理。

七、10/17 當天最小檢查
確認電源、網路、Docker Desktop；跑啟動器，八項 PASS。
手機行動網路開 LIFF、問答、STT、TTS、督導回覆各測一次。
保留前景 Funnel 及原有手動服務視窗，鎖屏，不登出。
本方案不是開機自啟；重開機後需本人登入並重新執行啟動器。

八、需要停止時
只有確定場測結束才執行 stop_jiaan.ps1。
它只停止本啟動器記錄且身分核對成功的 API／Worker／STT。
不停止原有手動程序、DB、Docker、Ollama、Tailscale 或 V2。
若顯示 REFUSED，保留現況請工程人員檢查，不手動刪除 run 記錄。
run\*.json 是程序身分紀錄，不可任意修改或複製到別台主機使用。
