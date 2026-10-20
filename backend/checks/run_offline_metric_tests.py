"""Run explicit synthetic suites only; deny app/DB imports and all networking.
No pytest collection, conftest, dataset reads or subprocesses.
Run: backend/.venv/Scripts/python.exe -B backend/checks/run_offline_metric_tests.py
"""
import argparse
import importlib.abc
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class DenyRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"app", "sqlalchemy", "psycopg", "dotenv", "httpx", "requests"}:
            raise RuntimeError("Runtime import forbidden in isolated tests: " + fullname)


def denied(*args, **kwargs):
    raise RuntimeError("Network/subprocess forbidden in isolated tests")


original_open = Path.open

def safe_open(path, *args, **kwargs):
    if path.name.startswith(".env") or "quality_tests" in path.parts:
        raise RuntimeError("Configuration/dataset read forbidden")
    return original_open(path, *args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description="Isolated metrics or independent research suites")
    parser.add_argument("--suite", choices=("phase1", "recall", "research", "all"), default="phase1")
    args = parser.parse_args()
    sys.meta_path.insert(0, DenyRuntime())
    with patch.object(socket.socket, "connect", denied), patch.object(socket, "create_connection", denied), patch.object(Path, "open", safe_open):
        import subprocess
        with patch.object(subprocess, "Popen", denied):
            loader = unittest.TestLoader()
            suite = unittest.TestSuite()
            if args.suite == "recall":
                import test_recall_baseline
                suite.addTests(loader.loadTestsFromModule(test_recall_baseline))
            if args.suite in ("research", "all"):
                import test_offline_failure_diagnosis
                suite.addTests(loader.loadTestsFromModule(test_offline_failure_diagnosis))
            if args.suite in ("phase1", "all"):
                import test_offline_rag_metrics
                import test_gold_baseline
                import test_answer_quality_v1
                suite.addTests(loader.loadTestsFromModule(test_offline_rag_metrics))
                suite.addTests(loader.loadTestsFromModule(test_gold_baseline))
                # Dataset/subprocess tests deliberately excluded.
                names = ["test_pass_and_alternative", "test_false_refusal_missing_source_and_terms",
                         "test_forbidden_and_false_answer", "test_no_evidence_is_not_medication_interception",
                         "test_empty_denominator_and_error", "test_offline_metrics_do_not_change_existing_scores"]
                suite.addTests(test_answer_quality_v1.QualityEvaluator(name) for name in names)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
