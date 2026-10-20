"""Integration acceptance, restricted to disposable ltc_clean_verify.

Uses existing API/services. No fixture cleanup, migrations or production LINE calls.
"""
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean_db as provision
provision.configure('ltc_clean_verify')
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.main import app
from app.db import new_session, session_scope
from app.models import User
from app.auth import create_binding_code

credentials = json.loads((provision.PRIVATE / 'credentials.json').read_text(encoding='utf-8'))
results = {}

def check(condition, name):
    results[name] = 'PASS' if condition else 'FAIL'
    print(f'{name}: {results[name]}', flush=True)
    provision.save('clean-db-acceptance.json', results)
    assert condition, name

with new_session() as s:
    check(s.scalar(text('SELECT current_database()')) == 'ltc_clean_verify', 'isolated_database')
    check(s.scalar(text('SELECT count(*) FROM cases')) == 0, 'initial_cases_zero')
    check(s.scalar(text('SELECT count(*) FROM qa_items')) == 0, 'initial_qa_zero')
    check(s.scalar(text('SELECT count(*) FROM line_accounts')) == 0, 'initial_binding_zero')

with TestClient(app) as client:
    def login(name):
        r = client.post('/api/auth/login', json=dict(username=name, password=credentials[name]))
        check(r.status_code == 200 and r.json().get('status') == 'ok', f'login_{name}')
        return {'Authorization': 'Bearer ' + r.json()['session_token']}
    admin = login('jiaan_admin')
    supervisor = login('jiaan_sv01')
    for status in ['pending', 'in_progress', 'replied,closed']:
        r = client.get('/api/admin/cases', params={'status':status}, headers=admin)
        check(r.status_code == 200 and r.json() == [], 'admin_zero_' + status)
    identity = 'U' + uuid.uuid4().hex
    r = client.post('/api/auth/liff', json={'id_token':'dev:' + identity})
    check(r.status_code == 200 and r.json().get('status') == 'needs_binding', 'unbound_liff')
    # Test code exists ONLY in validation DB; never printed or generated for real users.
    with session_scope() as s:
        actor = s.scalar(select(User).where(User.username == 'jiaan_admin'))
        cg = s.scalar(select(User).where(User.username == 'jiaan_cg01'))
        code = create_binding_code(s, actor, cg)
    r = client.post('/api/auth/liff/bind', json={'id_token':'dev:' + identity, 'binding_code':code})
    check(r.status_code == 200 and r.json().get('status') == 'ok', 'mock_liff_bind')
    caregiver = {'Authorization':'Bearer ' + r.json()['session_token']}
    with new_session() as s:
        check(s.scalar(text('SELECT count(*) FROM line_accounts')) == 1, 'mock_binding_zero_to_one')
    for endpoint in ['/api/qa/history', '/api/cases/mine']:
        r = client.get(endpoint, headers=caregiver)
        check(r.status_code == 200 and r.json() == [], 'caregiver_empty_' + endpoint.rsplit('/',1)[1])
    def ask(question):
        r = client.post('/api/qa/ask', headers=caregiver,
                        json={'question':question,'client_request_id':'clean-verify-' + uuid.uuid4().hex})
        check(r.status_code == 200, 'ask_http_' + str(len(results)))
        return r.json()
    answer = ask('居家式喘息服務可以協助進食嗎？')
    provision.save('clean-db-rag-answer.json', answer)
    check(answer['outcome'] == 'answered' and bool(answer['citations']) and bool(answer['answer_text']), 'formal_rag_answer_with_sources')
    version = answer['citations'][0]['version_id']
    r = client.post(f'/api/sources/versions/{version}/download-url', headers=caregiver)
    check(r.status_code == 200 and r.json()['url'].startswith('https://stust.tailee6e4a.ts.net/'), 'download_public_base')
    with new_session() as s:
        check(s.scalar(text('SELECT count(*) FROM cases')) == 0, 'normal_question_no_case')
    risk = ask('長輩突然胸痛呼吸困難，我可以給他吃藥嗎？')
    provision.save('clean-db-risk-answer.json', risk)
    check(risk['outcome'] == 'escalated' and bool(risk.get('case')), 'high_risk_case_created')
    r = client.get('/api/admin/cases', headers=supervisor)
    check(r.status_code == 200 and len(r.json()) == 1 and r.json()[0]['id'] == risk['case']['id'], 'supervisor_only_new_first_case')
    with new_session() as s:
        check(s.scalar(text('SELECT count(*) FROM cases')) == 1, 'validation_case_count_one')
    r = client.get('/admin')
    check(r.status_code == 200, 'admin_spa_served')
provision.check('ltc_clean_verify')
print('Acceptance completed; real phone LINE/Funnel remains a manual check.')
