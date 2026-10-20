# Phase 1 修改／新增檔案

- `quality_tests/v1/README.md`
- `docs/rag_optimization_parameter_registry.md`
- `docs/quality_feedback_phase1.md`
- `quality_tests/optimization/README.md`
- `quality_tests/optimization/parameters.json`
- `quality_tests/optimization/runner_design.json`
- `quality_tests/optimization/production_rag_baseline.sha256.json`
- `quality_tests/optimization/0002_quality_feedback.sql`
- `quality_tests/optimization/migration_preflight.json`
- `quality_tests/optimization/migration_verification.json`
- `quality_tests/optimization/phase1_verification.json`
- `backend/checks/build_parameter_registry.py`
- `backend/checks/test_quality_phase1.py`
- `backend/app/quality_models.py`
- `backend/app/services/quality_feedback.py`
- `backend/app/services/quality_trace.py`
- `backend/app/api/quality_routes.py`
- `backend/app/services/qa_service.py`
- `backend/app/main.py`
- `backend/migrations/env.py`
- `backend/migrations/versions/0002_quality_feedback.py`
- `frontend/src/quality/FeedbackFields.tsx`
- `frontend/src/quality/FeedbackCollector.tsx`
- `frontend/src/quality/AdminQualityFeedbackPage.tsx`
- `frontend/src/liff/components.tsx`
- `frontend/src/admin/pages/AdminFeedbackPage.tsx`
- `frontend/tests/quality-feedback.test.tsx`
- `deploy/fieldtest/restart_api_quality.ps1`

另有 frontend/dist build輸出與 deploy/fieldtest/run/api.json 的 API ownership記錄更新。既有 v1 資料／回放報表保留；未修改RAG核心檔案（hash核對）。
