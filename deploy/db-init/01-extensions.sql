-- 首次建立資料庫時執行：啟用 pgvector，並建立測試用資料庫。
-- ltc_test：手機隔離驗收用；ltc_pytest：pytest 專屬，兩者互不共用，
-- 避免 pytest 的破壞性 DELETE 清空正在進行手機驗收的 ltc_test
-- （見 docs/20261113_SOS隔離程序安全與測試DB防護.md）。
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE ltc_test;
\connect ltc_test
CREATE EXTENSION IF NOT EXISTS vector;
\connect postgres
CREATE DATABASE ltc_pytest;
\connect ltc_pytest
CREATE EXTENSION IF NOT EXISTS vector;
