# 小照／嘉安 隔離展示環境啟動腳本

這組腳本只用於**隔離展示環境**：資料庫 `ltc_demo`、LINE Mock、本機 8151（API）／5180（前端）。
完全不會啟動、重啟、關閉正式 API（8140）、正式 Worker 或正式資料庫 `ltc_clean`。

## 如何啟動（重開機後）

在 PowerShell（專題根目錄 `C:\aa\ltc_care_installer_20260912\ltc_care` 或任意位置皆可，腳本會自行定位路徑）執行：

```powershell
& 'C:\aa\ltc_care_installer_20260912\ltc_care\deploy\demo\start_demo_all.ps1'
```

或分別啟動：

```powershell
& 'C:\aa\ltc_care_installer_20260912\ltc_care\deploy\demo\start_demo_api.ps1'
& 'C:\aa\ltc_care_installer_20260912\ltc_care\deploy\demo\start_demo_worker.ps1'
& 'C:\aa\ltc_care_installer_20260912\ltc_care\deploy\demo\start_demo_frontend.ps1'
```

啟動前每支腳本都會先檢查對應 port／PID 紀錄檔（`deploy/demo/run/*.pid`），
若已有相同展示服務在執行，會直接顯示「已在執行中，不重複啟動」並結束，不會啟動第二個 Worker。

## 驗證是否正常

```powershell
curl http://127.0.0.1:8151/api/healthz
curl http://127.0.0.1:5180/liff
```

`healthz` 回應中的 `database_name` 應為 `ltc_demo`；若顯示 `ltc_clean` 請立即停止，代表環境變數設定有誤。

## 安全限制（已內建於腳本）

- `DATABASE_URL` 一律由 `.env` 的 `TEST_DATABASE_URL` 推導、把資料庫名稱換成 `ltc_demo`，腳本不會印出或寫出密碼／連線字串。
- 啟動前以程式檢查連線字串中的資料庫名稱必須等於 `ltc_demo`，否則直接中止。
- `JIAAN_EMERGENCY_LINE_DISPATCH=on` 只在這個隔離展示環境中設定；正式環境 `.env` 沒有這個變數，正式庫行為不受影響。60/180 秒時限仍為展示用途，尚待嘉安核准為正式政策。
- 腳本只會啟動 port 8151／5180，絕不觸碰 8140（正式 API）或正式 Worker/DB。
- 不會寫入任何密碼、Token 或真實個案資料到腳本或記錄檔。

## 停止展示服務

目前沒有自動停止腳本；如需關閉，請先用 `Get-CimInstance Win32_Process` 核對 PID 確實屬於
`ltc_demo`／8151／5180，再手動 `Stop-Process -Id <PID>`，並刪除對應的 `deploy/demo/run/*.pid`。
