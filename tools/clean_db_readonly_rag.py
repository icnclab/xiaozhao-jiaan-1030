"""Exercise the final clean corpus without writing QA, cases or sessions."""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean_db as provision
provision.configure('ltc_clean')
from sqlalchemy import select, text
from app.db import new_session
from app.models import Organization
from app.services.documents import current_versions
from app.services.qa_graph import run_graph
from app.services.qa_policy import DEFAULT_POLICY

with new_session() as s:
    s.execute(text('SET TRANSACTION READ ONLY'))
    assert s.scalar(text('SELECT current_database()')) == 'ltc_clean'
    org = s.scalar(select(Organization).where(Organization.code == 'JIAAN'))
    current = current_versions(s, org.id, org.facility_type, date.today())
    assert len(current) == 32
    state = run_graph(dict(session=s, org_id=org.id, facility_type=org.facility_type, today=date.today(),
                           question_raw='居家式喘息服務可以協助進食嗎？', deid_terms=set(), policy=DEFAULT_POLICY))
    assert state['outcome'] == 'answer' and state.get('claims') and state.get('evidence_map')
    out = dict(database='ltc_clean', transaction='READ ONLY', current_documents=len(current),
               outcome=state['outcome'], claims=state['claims'],
               sources=[dict(title=c.title, version_id=str(c.version_id)) for c in state['evidence_map'].values()],
               checks=state.get('checks'), policy=DEFAULT_POLICY.version)
    provision.save('clean-db-readonly-rag.json', out)
    print('Final clean corpus RAG: PASS; 32 current documents; READ ONLY; no QA/cases/sessions written.')
