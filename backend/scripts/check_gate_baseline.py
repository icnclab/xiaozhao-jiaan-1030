"""Run failed legacy tests against pre-gate code IN MEMORY, test DB only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
from app.config import get_settings

s = get_settings()
assert make_url(s.database_url).database != make_url(s.test_database_url).database
assert 'test' in make_url(s.test_database_url).database.lower()
from app.services import qa_policy, qa_graph
services = Path(__file__).resolve().parents[1] / 'app/services'
for module, name in ((qa_policy, 'qa_policy.py'), (qa_graph, 'qa_graph.py')):
    backup = sorted(services.glob(name + '.bak_evidence_gate_*'))[0]
    exec(compile(backup.read_text(encoding='utf-8'), str(backup), 'exec'), module.__dict__)
    print('BASELINE', backup.name, flush=True)
import os
os.chdir(Path(__file__).resolve().parents[1])
import pytest
raise SystemExit(pytest.main(['tests/test_documents.py::test_version_supersede_and_history',
    'tests/test_qa_flow.py::test_escalate_conflict', 'tests/test_qa_flow.py::test_escalate_clinical_and_medication',
    '-q', '--junitxml=../docs/retrieval_gate_baseline_20261008.xml']))
