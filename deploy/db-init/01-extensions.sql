-- 首次建立資料庫時執行：啟用 pgvector，並建立測試用資料庫。
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE ltc_test;
\connect ltc_test
CREATE EXTENSION IF NOT EXISTS vector;
