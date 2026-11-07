# 第八輪｜緊急通報整合驗證

## 已完成
- 修正 client_request_id 的 UUID/VARCHAR 型別不一致。
- FastAPI TestClient 與 PostgreSQL ltc_test 整合測試通過。
- 驗證建立、冪等重送、權限、接手、結案及事件歷程。

## 尚未完成
- 0006 Migration 與既有正式表格的完整相容性審核。
- Migration rollback 與版本管理。
- 實際 LINE/LIFF 場域驗收。
- 跨 APP 背景持續警報。

## 安全限制
未修改 ltc_clean，未部署、未 commit、未 push。
