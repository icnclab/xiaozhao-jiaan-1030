"""Standalone unittest. Integration uses two disposable schemas, never public data."""
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.quality_feedback import Correction, ReviewIn, encode_export, review
from app.services.quality_trace import historical, capture


class PureChecks(unittest.TestCase):
    def test_registry_required_fields_and_real_values(self):
        from build_parameter_registry import generate
        data=json.loads((ROOT/'quality_tests/optimization/parameters.json').read_text(encoding='utf-8'))
        actual=json.loads(json.dumps(generate()))
        self.assertEqual([r['current_value'] for r in data['parameters']],[r['current_value'] for r in actual['parameters']])
        required={'parameter_id','layer','name','current_value','code_location','configurable',
                  'possible_search_space','metric_affected','optimization_goal','change_risk','notes','classification'}
        for r in data['parameters']:
            self.assertTrue(required<=r.keys())
            file,line=r['code_location'].split(':')
            self.assertLessEqual(int(line),len((ROOT/file).read_text(encoding='utf-8').splitlines()))
        self.assertEqual(len({r['parameter_id'] for r in data['parameters']}),48)

    def test_rag_sources_unchanged(self):
        baseline=json.loads((ROOT/'quality_tests/optimization/production_rag_baseline.sha256.json').read_text())
        for path,digest in baseline.items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)

    def test_v1_development_only(self):
        text=(ROOT/'quality_tests/v1/README.md').read_text(encoding='utf-8')
        self.assertIn('Development Regression Set',text)
        self.assertIn('禁止描述為正式 AI 準確率',text)

    def test_untrusted_snapshot_status_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            Correction(error_type='other',expected_behavior='answer',status='verified',qa_snapshot={})

    def test_historical_missing_values_not_backfilled(self):
        item=SimpleNamespace(checks={'risk_codes':['medication']},question_masked='幾顆',
                             qa_policy_version='historical',outcome='escalated',escalation_reason='risk_medication',embedding_provider='hash')
        trace=historical(item)
        for field in ('rag_version','prompt_version','embedding_model','candidate_k','expanded_query'):
            self.assertIsNone(trace[field])
        self.assertEqual(trace['qa_policy_version'],'historical')

    def test_capture_does_not_execute_retrieval_for_risk(self):
        from datetime import date
        from app.services.qa_policy import DEFAULT_POLICY
        state=dict(policy=DEFAULT_POLICY,today=date(2026,10,11),question_masked='藥吃幾顆',
                   outcome='escalate',reason='risk_medication',risk_codes=['medication'])
        trace=capture(state)
        self.assertFalse(trace['retrieval_executed'])
        self.assertIsNone(trace['expanded_query'])
        self.assertEqual(trace['risk_gate_result']['codes'],['medication'])
        self.assertNotIn('retrieved',state)

    def test_verify_requires_evidence_and_second_reviewer(self):
        user=SimpleNamespace(id=uuid.uuid4(),role='admin',org_id=None)
        row=SimpleNamespace(org_id=None,revision=0,submitted_by=uuid.uuid4())
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            review(None,row,user,ReviewIn(error_type='other',expected_behavior='answer',status='verified',expected_revision=0))
        self.assertEqual(cm.exception.status_code,422)
        row.submitted_by=user.id
        with self.assertRaises(HTTPException) as cm:
            review(None,row,user,ReviewIn(error_type='other',expected_behavior='refuse',status='verified',expected_revision=0))
        self.assertEqual(cm.exception.status_code,403)

    def test_export_serialization_and_empty_headers(self):
        record=dict(id='id',qa_id='qa',status='verified',revision=1,dataset_split=None,
                    qa_snapshot={'question':'中文'},submission={},reviewed_correction={},review_history=[])
        self.assertEqual(json.loads(encode_export([record],'json'))['count'],1)
        self.assertEqual(json.loads(encode_export([record],'jsonl'))['dataset_split'],None)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(encode_export([record],'csv').lstrip('\ufeff'))))),1)
        self.assertIn('qa_id',encode_export([],'csv'))


class IsolatedIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine,text
        from sqlalchemy.engine import make_url
        from app.config import get_settings
        from app.db import Base
        from app import models,quality_models
        url=make_url(get_settings().database_url)
        if url.database!='ltc_clean': raise RuntimeError('Integration guard requires ltc_clean')
        suffix=uuid.uuid4().hex
        cls.business='phase1_test_business_'+suffix
        cls.quality='phase1_test_quality_'+suffix
        cls.raw_engine=create_engine(url)
        cls.engine=cls.raw_engine.execution_options(schema_translate_map={None:cls.business,'rag_quality':cls.quality})
        result=subprocess.run([sys.executable,'-m','alembic','upgrade','0001:head','--sql'],
                              cwd=ROOT/'backend',capture_output=True)
        if result.returncode: raise RuntimeError('Migration SQL generation failed')
        sql=result.stdout.decode('utf-8').replace('rag_quality',cls.quality)
        sql=re.sub(r"UPDATE alembic_version[^;]+;",'',sql)
        sql=sql.replace('BEGIN;','').replace('COMMIT;','')
        with cls.engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{cls.business}"')
            Base.metadata.create_all(conn,tables=[t for t in Base.metadata.sorted_tables if t.schema is None])
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{cls.business}", public')
            conn.exec_driver_sql(sql)

    @classmethod
    def tearDownClass(cls):
        with cls.raw_engine.begin() as conn:
            for schema in (cls.quality,cls.business):
                assert re.fullmatch(r'phase1_test_(quality|business)_[0-9a-f]{32}',schema)
                conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        cls.raw_engine.dispose()

    def setUp(self):
        from sqlalchemy.orm import Session
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.quality_routes import router
        from app.auth import current_user
        from app.db import get_db
        from app.models import Organization,User,QaItem,Document,DocumentVersion,Chunk,Citation
        self.db=Session(self.engine,expire_on_commit=False)
        org=Organization(code=uuid.uuid4().hex,name='isolated fixture',facility_type='home')
        other=Organization(code=uuid.uuid4().hex,name='other fixture',facility_type='home')
        self.db.add_all([org,other]);self.db.flush()
        def user(role,org):
            return User(org_id=org.id,username=uuid.uuid4().hex,display_name='fixture',role=role)
        self.cg=user('caregiver',org);self.sup=user('supervisor',org);self.admin=user('admin',org);self.other=user('supervisor',other)
        self.db.add_all([self.cg,self.sup,self.admin,self.other]);self.db.flush()
        self.qa=QaItem(org_id=org.id,user_id=self.cg.id,conversation_id=uuid.uuid4(),client_request_id=uuid.uuid4().hex,
                       source='text',question_masked='測試問題',outcome='answered',answer_text='測試答案',
                       llm_provider='mock',embedding_provider='hash',qa_policy_version='fixture')
        doc=Document(org_id=org.id,title='fixture document',doc_type='sop',facility_types=['home'])
        self.db.add_all([self.qa,doc]);self.db.flush()
        version=DocumentVersion(document_id=doc.id,version_label='fixture',status='published',file_path='fixture',
                                file_name='fixture.txt',file_sha256='0'*64,mime='text/plain')
        self.db.add(version);self.db.flush()
        chunk=Chunk(version_id=version.id,seq=0,locator='第1頁',text='測試來源原文')
        self.db.add(chunk);self.db.flush()
        self.db.add(Citation(qa_item_id=self.qa.id,chunk_id=chunk.id,version_id=version.id,label='c1',rank=1));self.db.commit()
        self.user=self.cg
        app=FastAPI();app.include_router(router,prefix='/api')
        app.dependency_overrides[current_user]=lambda:self.user
        def session():
            try:yield self.db
            finally:self.db.rollback()
        app.dependency_overrides[get_db]=session
        self.client=TestClient(app)
        self.body=dict(error_type='incomplete_answer',expected_behavior='answer',correct_answer='完整答案',
                       correct_source_document='fixture document',correct_source_page_or_section='第1頁',evidence_summary='來源摘要')

    def tearDown(self):
        self.client.close();self.db.close()

    def submit(self):
        response=self.client.post(f'/api/quality/qa/{self.qa.id}/feedback',json=self.body)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['id']

    def verify(self,fid,status='verified',revision=0):
        return self.client.post(f'/api/quality/feedback/{fid}/review',json=dict(self.body,status=status,
                               expected_revision=revision,evidence_checked=True))

    def test_snapshot_and_idempotency_do_not_change_qa_or_case(self):
        from app.models import Case,QaItem
        from app.quality_models import QualityFeedback
        from sqlalchemy import select,func
        before=self.db.scalar(select(func.count()).select_from(QaItem)),self.db.scalar(select(func.count()).select_from(Case))
        fid=self.submit();self.assertEqual(self.submit(),fid)
        row=self.db.get(QualityFeedback,uuid.UUID(fid))
        self.assertEqual(row.qa_snapshot['sources'][0]['text'],'測試來源原文')
        self.assertEqual(row.status,'pending_review')
        self.assertEqual(row.submission['correct_answer'],'完整答案')
        self.assertEqual(before,(self.db.scalar(select(func.count()).select_from(QaItem)),self.db.scalar(select(func.count()).select_from(Case))))
        self.assertEqual(self.db.get(QaItem,self.qa.id).answer_text,'測試答案')

    def test_roles_tenant_scope_and_forbidden_self_verify(self):
        fid=self.submit()
        self.assertEqual(self.client.get('/api/quality/feedback').status_code,403)
        self.assertEqual(self.client.get('/api/quality/dataset/export').status_code,403)
        self.user=self.other
        self.assertEqual(self.client.get(f'/api/quality/feedback/{fid}').status_code,404)
        self.assertEqual(self.verify(fid).status_code,404)
        self.assertEqual(self.client.post(f'/api/quality/qa/{self.qa.id}/feedback',json=self.body).status_code,404)
        self.user=self.cg;self.cg.role='supervisor'
        self.assertEqual(self.verify(fid).status_code,403)

    def test_verified_only_exports_all_formats_and_reviews(self):
        fid=self.submit();self.user=self.sup
        self.assertNotIn(fid,self.client.get('/api/quality/dataset/export').text)
        response=self.verify(fid);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.verify(fid).status_code,409)
        self.user=self.admin
        for format in ('json','jsonl','csv'):
            response=self.client.get('/api/quality/dataset/export?format='+format)
            self.assertEqual(response.status_code,200)
            self.assertIn(fid,response.text)
        details=self.client.get(f'/api/quality/feedback/{fid}').json()
        self.assertEqual(details['submission']['correct_answer'],'完整答案')
        self.assertEqual(len(details['review_history']),1)
        response=self.verify(fid,'rejected',1);self.assertEqual(response.status_code,200)
        self.assertNotIn(fid,self.client.get('/api/quality/dataset/export').text)

    def test_db_immutability_and_review_append_only(self):
        from sqlalchemy import text
        from sqlalchemy.exc import DBAPIError
        fid=self.submit();self.user=self.sup;self.assertEqual(self.verify(fid).status_code,200)
        with self.assertRaises(DBAPIError):
            self.db.execute(text(f"UPDATE {self.quality}.feedback_entries SET submission='{{}}'::jsonb WHERE id=:id"),{'id':uuid.UUID(fid)})
        self.db.rollback()
        with self.assertRaises(DBAPIError):
            self.db.execute(text(f'DELETE FROM {self.quality}.feedback_reviews WHERE feedback_id=:id'),{'id':uuid.UUID(fid)})
        self.db.rollback()


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PureChecks)
    if '--integration' in sys.argv:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(IsolatedIntegration))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
