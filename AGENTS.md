# 專案開發最高規則（11/15 比賽死線前）
1. 第七版候選修改（SOS/LIFF/Admin）已同步至主目錄，原始備份位於 backups\BEFORE_SEVENTH_SYNC_20261113_213936。
2. 知識庫安全匯入工具位於 tools\kb_import_20261113，6 份候選 PDF 位於 data\kb_candidates_20261113，直接呼叫既有管理 API 匯入待審區，禁止重寫 admin_routes.py / documents.py / ingest.py。
3. 採用「整批完成修改後再統一執行回歸測試」模式，禁止每改一個檔案就反覆跑測試原地踏步。
