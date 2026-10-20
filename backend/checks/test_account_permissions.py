"""Real PostgreSQL API tests in a NEW template0 DB; each test rolls back.

Run directly, never through production pytest fixtures. No existing DB reset/delete.
"""
import os
import sys
import unittest
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import get_settings
from app.db import get_db
from app.api import admin_routes, auth_routes
from app.auth import issue_session, set_password, create_binding_code, find_line_user, LineIdentity
from app.models import Organization, User, LineAccount, AuthSession, BindingCode, Case, CaseMessage, QaItem, AuditLog, TtsAsset
from app.services import audit, jobs

class Accounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original = make_url(get_settings().database_url)
        assert (original.host,original.port) == ('127.0.0.1',55432)
        db = 'ltc_account_test_' + uuid.uuid4().hex[:12]
        admin_engine = create_engine(original.set(database='postgres'), isolation_level='AUTOCOMMIT')
        with admin_engine.connect() as c:
            c.execute(text(f'CREATE DATABASE "{db}" TEMPLATE template0'))
        admin_engine.dispose()
        url = original.set(database=db)
        os.environ['ALEMBIC_DATABASE_URL'] = url.render_as_string(hide_password=False)
        cfg = Config(str(ROOT/'backend/alembic.ini'))
        cfg.set_main_option('script_location',str(ROOT/'backend/migrations'))
        command.upgrade(cfg,'head')
        cls.engine = create_engine(url)
        print('Isolated test DB:',db,flush=True)
        cls.settings = get_settings()
        cls.previous = (cls.settings.app_env,cls.settings.line_mode)
        cls.settings.app_env,cls.settings.line_mode = 'test','mock'

    @classmethod
    def tearDownClass(cls):
        cls.settings.app_env,cls.settings.line_mode = cls.previous
        cls.engine.dispose()

    def setUp(self):
        self.connection = self.engine.connect()
        self.outer = self.connection.begin()
        self.s = Session(bind=self.connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
        orgs = [Organization(code=n,name=n,facility_type='home') for n in ['TEST','OTHER']]
        self.s.add_all(orgs); self.s.flush()
        self.users={}; self.headers={}
        for name,role,org in [('admin','admin',orgs[0]),('supervisor','supervisor',orgs[0]),
                              ('caregiver','caregiver',orgs[0]),('other','caregiver',orgs[1])]:
            u=User(org_id=org.id,username=name,display_name=name,role=role,is_active=True)
            set_password(u,'test-password-123')
            self.s.add(u); self.s.flush(); self.users[name]=u
            token=issue_session(self.s,u,'liff' if role=='caregiver' else 'web')
            self.headers[name]={'Authorization':'Bearer '+token}
        cg=self.users['caregiver']
        self.s.add(LineAccount(user_id=cg.id,line_user_id='U'+'a'*32))
        self.qa=QaItem(org_id=cg.org_id,user_id=cg.id,conversation_id=uuid.uuid4(),client_request_id='history-qa',
                       source='text',question_masked='test history',outcome='escalated',llm_provider='test',
                       embedding_provider='hash',qa_policy_version='test')
        self.s.add(self.qa);self.s.flush()
        self.case=Case(org_id=cg.org_id,number='TEST-1',created_by=cg.id,client_request_id='history-case',
                       source='ai_escalation',qa_item_id=self.qa.id,summary_masked='test history',reason='test',status='pending')
        self.s.add(self.case)
        audit.record(self.s,'test.history',actor=cg)
        self.s.commit()
        app=FastAPI();app.include_router(admin_routes.router,prefix='/api');app.include_router(auth_routes.router,prefix='/api')
        app.dependency_overrides[get_db]=lambda:self.s
        self.client=TestClient(app)

    def tearDown(self):
        self.client.close();self.s.close();self.outer.rollback();self.connection.close()

    def request(self,actor,method,path,**kwargs):
        return self.client.request(method,'/api/admin/'+path,headers=self.headers[actor],**kwargs)

    def test_listing_and_caregiver_denied(self):
        for actor in ['admin','supervisor']:
            r=self.request(actor,'GET','users');self.assertEqual(r.status_code,200)
            self.assertEqual(len(r.json()),3)
        self.assertEqual(self.request('caregiver','GET','users').status_code,403)
        for method,suffix,body in [('POST','binding-code',{}),('DELETE','line-binding',None),('PATCH','active',{'is_active':False})]:
            self.assertEqual(self.request('caregiver',method,f"users/{self.users['caregiver'].id}/{suffix}",json=body).status_code,403)

    def test_only_admin_creates_all_roles(self):
        for role in ['caregiver','supervisor','admin']:
            body=dict(username='new_'+role,display_name='test',role=role,password='test-password-123')
            self.assertEqual(self.request('supervisor','POST','users',json=body).status_code,403)
            self.assertEqual(self.request('caregiver','POST','users',json=body).status_code,403)
            self.assertEqual(self.request('admin','POST','users',json=body).status_code,200)

    def test_binding_role_active_and_org_guards(self):
        for actor in ['admin','supervisor']:
            for target in ['admin','supervisor']:
                self.assertEqual(self.request(actor,'POST',f'users/{self.users[target].id}/binding-code',json={}).status_code,403)
            self.assertEqual(self.request(actor,'POST',f"users/{self.users['other'].id}/binding-code",json={}).status_code,404)
            self.assertEqual(self.request(actor,'POST',f"users/{self.users['caregiver'].id}/binding-code",json={}).status_code,200)
        self.users['caregiver'].is_active=False;self.s.commit()
        for actor in ['admin','supervisor']:
            self.assertEqual(self.request(actor,'POST',f"users/{self.users['caregiver'].id}/binding-code",json={}).status_code,409)

    def test_active_permissions(self):
        for actor in ['supervisor','caregiver']:
            self.assertEqual(self.request(actor,'PATCH',f"users/{self.users['caregiver'].id}/active",json={'is_active':False}).status_code,403)
        self.assertEqual(self.request('admin','PATCH',f"users/{self.users['other'].id}/active",json={'is_active':False}).status_code,404)

    def test_disable_rejects_existing_sessions_and_logins(self):
        for name in ['supervisor','caregiver','admin']:
            # Admin self-disable is tested last.
            self.assertEqual(self.request('admin','PATCH',f'users/{self.users[name].id}/active',json={'is_active':False}).status_code,200)
            self.assertEqual(self.client.get('/api/me',headers=self.headers[name]).status_code,401)
            self.assertEqual(self.client.post('/api/auth/login',json={'username':name,'password':'test-password-123'}).status_code,401)
        self.assertIsNone(find_line_user(self.s,LineIdentity('U'+'a'*32,None,True)))
        self.assertIsNotNone(self.s.get(Case,self.case.id));self.assertIsNotNone(self.s.get(QaItem,self.qa.id))
        self.assertEqual(self.s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='test.history')),1)

    def test_unbind_scope_and_role(self):
        for actor in ['admin','supervisor']:
            self.assertEqual(self.request(actor,'DELETE',f"users/{self.users['other'].id}/line-binding").status_code,404)
        for name in ['supervisor','admin']:
            self.assertEqual(self.request('supervisor','DELETE',f'users/{self.users[name].id}/line-binding').status_code,403)
            self.assertEqual(self.request('admin','DELETE',f'users/{self.users[name].id}/line-binding').status_code,200)

    def test_unbind_invalidates_line_sessions_codes_and_allows_rebind(self):
        cg=self.users['caregiver'];actor=self.users['admin']
        code=create_binding_code(self.s,actor,cg)
        web=issue_session(self.s,cg,'web');self.s.commit()
        r=self.request('supervisor','DELETE',f'users/{cg.id}/line-binding');self.assertEqual(r.status_code,200)
        self.assertIsNone(self.s.scalar(select(LineAccount).where(LineAccount.user_id==cg.id)))
        self.assertEqual(self.client.get('/api/me',headers=self.headers['caregiver']).status_code,401)
        self.assertEqual(self.client.get('/api/me',headers={'Authorization':'Bearer '+web}).status_code,200)
        self.assertEqual(self.client.post('/api/auth/liff/bind',json={'id_token':'dev:U'+'b'*32,'binding_code':code}).status_code,400)
        new=self.request('supervisor','POST',f'users/{cg.id}/binding-code',json={}).json()['code']
        self.assertEqual(self.client.post('/api/auth/liff/bind',json={'id_token':'dev:U'+'b'*32,'binding_code':new}).status_code,200)
        self.assertIsNotNone(self.s.get(User,cg.id));self.assertIsNotNone(self.s.get(Case,self.case.id));self.assertIsNotNone(self.s.get(QaItem,self.qa.id))
        self.assertEqual(self.s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='test.history')),1)

    def test_enable_requires_new_session_and_old_code_stays_invalid(self):
        cg=self.users['caregiver'];code=create_binding_code(self.s,self.users['admin'],cg);self.s.commit()
        for active in [False,True]:
            self.assertEqual(self.request('admin','PATCH',f'users/{cg.id}/active',json={'is_active':active}).status_code,200)
        self.assertEqual(self.client.get('/api/me',headers=self.headers['caregiver']).status_code,401)
        self.assertEqual(self.client.post('/api/auth/liff/bind',json={'id_token':'dev:U'+'b'*32,'binding_code':code}).status_code,400)

    def test_legacy_non_caregiver_code_cannot_bind(self):
        code=create_binding_code(self.s,self.users['admin'],self.users['supervisor']);self.s.commit()
        self.assertEqual(self.client.post('/api/auth/liff/bind',json={'id_token':'dev:U'+'b'*32,'binding_code':code}).status_code,400)

    def test_soft_delete_preserves_history_releases_username_and_revokes_access(self):
        cg=self.users['caregiver'];old_id=cg.id;old_name=cg.display_name
        code=create_binding_code(self.s,self.users['admin'],cg);self.s.commit()
        self.assertEqual(self.request('admin','DELETE',f'users/{old_id}').status_code,200)
        old=self.s.get(User,old_id)
        self.assertIsNotNone(old);self.assertFalse(old.is_active);self.assertEqual(old.display_name,old_name)
        self.assertTrue(old.username.startswith('__deleted__'));self.assertIsNone(old.password_hash)
        self.assertIsNotNone(self.s.get(Case,self.case.id));self.assertIsNotNone(self.s.get(QaItem,self.qa.id))
        self.assertEqual(self.s.get(Case,self.case.id).created_by,old_id)
        self.assertEqual(self.s.get(QaItem,self.qa.id).user_id,old_id)
        history=self.s.scalar(select(AuditLog).where(AuditLog.action=='test.history'))
        self.assertEqual(history.actor_id,old_id)
        deletion=self.s.scalar(select(AuditLog).where(AuditLog.action=='user.delete'))
        self.assertEqual(deletion.meta['original_username'],'caregiver')
        self.assertIsNone(self.s.scalar(select(LineAccount).where(LineAccount.user_id==old_id)))
        self.assertEqual(self.client.get('/api/me',headers=self.headers['caregiver']).status_code,401)
        self.assertEqual(self.client.post('/api/auth/liff/bind',json={'id_token':'dev:U'+'b'*32,'binding_code':code}).status_code,400)
        self.assertEqual(self.request('admin','PATCH',f'users/{old_id}/active',json={'is_active':True}).status_code,409)
        self.assertEqual(self.request('admin','POST',f'users/{old_id}/binding-code',json={}).status_code,409)
        self.assertEqual(self.request('admin','DELETE',f'users/{old_id}').status_code,200)
        listed=self.request('admin','GET','users').json()
        self.assertNotIn(str(old_id),[u['id'] for u in listed])
        for actor in ['admin', 'supervisor']:
            response = self.request(actor, 'GET', 'users?include_deleted=true')
            self.assertEqual(response.status_code, 200)
            deleted = next(u for u in response.json() if u['id'] == str(old_id))
            self.assertTrue(deleted['is_deleted'])
            self.assertEqual(deleted['original_username'], 'caregiver')
            self.assertNotIn(str(self.users['other'].id), [u['id'] for u in response.json()])
        self.assertEqual(self.request('caregiver', 'GET', 'users?include_deleted=true').status_code, 401)
        created=self.request('admin','POST','users',json=dict(username='caregiver',display_name='new caregiver',role='caregiver'))
        self.assertEqual(created.status_code,200)
        self.assertNotEqual(created.json()['id'],str(old_id))
        self.assertEqual(self.s.get(Case,self.case.id).created_by,old_id)

    def test_soft_delete_permissions_and_reserved_namespace(self):
        cg=self.users['caregiver']
        for actor in ['supervisor','caregiver']:
            self.assertEqual(self.request(actor,'DELETE',f'users/{cg.id}').status_code,403)
        self.assertEqual(self.request('admin','DELETE',f"users/{self.users['other'].id}").status_code,404)
        self.assertEqual(self.request('admin','DELETE',f"users/{self.users['admin'].id}").status_code,409)
        self.assertEqual(self.request('admin','POST','users',json=dict(username='__deleted__fake',display_name='test',role='caregiver')).status_code,422)

    def test_deleted_supervisor_reply_and_audio_metadata_survive(self):
        supervisor=self.users['supervisor']
        reply=CaseMessage(case_id=self.case.id,author_id=supervisor.id,author_role='supervisor',body='historical reply',client_request_id='history-reply')
        self.s.add(reply)
        asset=TtsAsset(qa_item_id=self.qa.id,status='ready',provider='test',token_id='test-media-token',expires_at=jobs.utcnow()+timedelta(days=1))
        self.s.add(asset);self.s.commit()
        self.assertEqual(self.request('admin','DELETE',f'users/{supervisor.id}').status_code,200)
        self.assertEqual(self.s.get(CaseMessage,reply.id).author_id,supervisor.id)
        self.assertEqual(self.s.get(CaseMessage,reply.id).body,'historical reply')
        self.assertEqual(self.s.get(User,supervisor.id).display_name,supervisor.display_name)
        self.assertEqual(self.request('admin','DELETE',f"users/{self.users['caregiver'].id}").status_code,200)
        self.s.refresh(asset)
        self.assertLessEqual(asset.expires_at,jobs.utcnow())
        self.assertNotEqual(asset.token_id,'test-media-token')

if __name__=='__main__':
    unittest.main(verbosity=2)
