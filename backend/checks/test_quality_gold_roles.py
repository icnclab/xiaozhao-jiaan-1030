"""Role/API regression using isolated in-memory doubles; no production DB writes."""
import sys,unittest,uuid,copy,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from app.auth import current_user
from app.db import get_db
from app.api.quality_routes import router
from app.services import quality_feedback as service
from test_quality_gold import row, ORG
class Rows(list):
    def all(self):return self
class Db:
    def __init__(self,rows): self.rows=rows;self.added=[];self.queries=[]
    def scalar(self,q):
        values=q.compile().params;self.queries.append(values)
        return next((r for r in self.rows if r.id==values.get('id_1') and r.org_id==values.get('org_id_1')),None)
    def scalars(self,q):
        values=q.compile().params;self.queries.append(values)
        return Rows(r for r in self.rows if r.org_id==values.get('org_id_1') and ('status_1' not in values or r.status==values['status_1']))
    def add(self,r):self.added.append(r)
    def commit(self):pass
class Roles(unittest.TestCase):
    def setUp(self):
        self.r=row();self.db=Db([self.r]);self.user=SimpleNamespace(id=uuid.uuid4(),role='supervisor',org_id=ORG)
        app=FastAPI();app.include_router(router,prefix='/api')
        app.dependency_overrides[current_user]=lambda:self.user
        app.dependency_overrides[get_db]=lambda:self.db
        self.client=TestClient(app)
        self.clean=patch.object(service,'clean',side_effect=lambda db,u,b:b.model_dump());self.clean.start()
        self.audit=patch.object(service.audit,'record');self.audit.start()
        self.history=patch.object(service,'review_history',return_value=[]);self.history.start()
    def tearDown(self):self.history.stop();self.audit.stop();self.clean.stop();self.client.close()
    def payload(self):
        c=self.r.reviewed_correction
        return {**{k:c.get(k,'') for k in service.GENERAL_FIELDS},'status':'verified','expected_revision':self.r.revision}
    def endpoint(self):return f'/api/quality/feedback/{self.r.id}/review'
    def test_supervisor_review_and_preservation(self):
        original=copy.deepcopy(self.r.submission);gold={k:self.r.reviewed_correction.get(k) for k in service.GOLD_FIELDS};body=self.payload();body['correct_answer']='督導修正版'
        response=self.client.post(self.endpoint(),json=body);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.r.reviewed_correction['correct_answer'],'督導修正版')
        self.assertEqual({k:self.r.reviewed_correction.get(k) for k in service.GOLD_FIELDS},gold)
        self.assertEqual(self.r.submission,original);self.assertEqual(len(self.db.added),1);self.assertEqual(self.r.revision,2)
        self.assertEqual(service.gold_readiness(self.r)['state'],'needs_review')
        response=self.client.post(self.endpoint(),json=self.payload());self.assertEqual(response.status_code,200)
        self.assertEqual(service.gold_readiness(self.r)['state'],'needs_review')
    def test_all_gold_fields_rejected_on_direct_api(self):
        before=copy.deepcopy(self.r.reviewed_correction)
        samples=service.ReviewIn(error_type='wrong_answer',expected_behavior='answer',status='verified',expected_revision=1).model_dump()
        for key in service.GOLD_FIELDS:
            response=self.client.post(self.endpoint(),json={**self.payload(),key:samples[key]})
            self.assertEqual(response.status_code,403,(key,response.text))
        self.assertEqual(self.r.reviewed_correction,before);self.assertEqual(self.db.added,[])
    def test_admin_can_edit_and_normalize_gold(self):
        self.user.role='admin'
        body={**self.payload(),**{k:self.r.reviewed_correction.get(k,v) for k,v in service.ReviewIn(error_type='wrong_answer',expected_behavior='answer',status='verified',expected_revision=1).model_dump().items() if k in service.GOLD_FIELDS},'data_quality_conflicts':'無'}
        response=self.client.post(self.endpoint(),json=body);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.r.reviewed_correction['data_quality_conflicts'],'')
        self.assertEqual(response.json()['gold_readiness'],'ready')
        self.assertEqual(self.db.added[0].correction['gold_approved_by'],str(self.user.id))
    def test_conflict_sentinels_and_real_issue(self):
        for value in ['', '無','沒有','none','NONE','n/a','NA','不適用','  無  ']:
            r=row(data_quality_conflicts=value);self.assertEqual(service.normalize_conflicts(value),'')
            self.assertNotIn('data_quality_conflict',service.gold_readiness(r)['reasons'])
        r=row(data_quality_conflicts='來源尚待核對');self.assertIn('data_quality_conflict',service.gold_readiness(r)['reasons'])
    def test_admin_queue_filters_and_priority(self):
        self.user.role='admin';ready=self.r;risk=row(error_type='risk_false_negative',expected_behavior='risk_block',complete_answer_confirmed=False);quality=row(complete_answer_confirmed=False)
        self.db.rows=[ready,quality,risk]
        response=self.client.get('/api/quality/feedback?gold_queue=true');self.assertEqual(response.status_code,200)
        records=response.json();self.assertEqual([r['id'] for r in records],[str(risk.id),str(quality.id)])
        self.assertEqual([r['gold_priority'] for r in records],['P0 安全','P1 資料品質'])
        self.assertNotIn(str(ready.id),[r['id'] for r in records])
        stats=self.client.get('/api/quality/gold/stats').json();self.assertEqual(stats['needs_review'],2);self.assertEqual(stats['ready'],1)
    def test_supervisor_cannot_gold_export_queue_or_stats(self):
        for path in ['/api/quality/dataset/gold/export','/api/quality/gold/stats','/api/quality/feedback?gold_queue=true']:
            self.assertEqual(self.client.get(path).status_code,403,path)
    def test_admin_gold_export_only_ready(self):
        self.user.role='admin';needs=row(complete_answer_confirmed=False);rejected=row();rejected.status='rejected';self.db.rows=[self.r,needs,rejected]
        response=self.client.get('/api/quality/dataset/gold/export');self.assertEqual(response.status_code,200)
        self.assertEqual([r['id'] for r in response.json()['records']],[str(self.r.id)])
    def test_org_isolation(self):
        self.user.org_id=uuid.uuid4()
        self.assertEqual(self.client.get(f'/api/quality/feedback/{self.r.id}').status_code,404)
        self.assertEqual(self.client.post(self.endpoint(),json=self.payload()).status_code,404)
        self.user.role='admin';self.assertEqual(self.client.get('/api/quality/gold/stats').json()['ready'],0)
        self.assertEqual(self.client.get('/api/quality/dataset/gold/export').json()['count'],0)
    def test_supervisor_trace_redacted(self):
        self.r.qa_snapshot={'runtime':{'retrieval_candidates':[{'chunk_id':'hidden'}],'normalized_query':'hidden','risk_gate_result':{'codes':[]},'escalation_result':{'outcome':'answer'}},'rag_version':'hidden'}
        response=self.client.get(f'/api/quality/feedback/{self.r.id}')
        snapshot=response.json()['qa_snapshot'];self.assertNotIn('retrieval_candidates',snapshot['runtime']);self.assertNotIn('rag_version',snapshot)
    def test_supervisor_status_reopen_requires_admin_confirmation(self):
        body=self.payload();body['status']='rejected';self.assertEqual(self.client.post(self.endpoint(),json=body).status_code,200)
        self.assertEqual(self.client.post(self.endpoint(),json=self.payload()).status_code,200)
        self.assertIn('admin_gold_confirmation_required',service.gold_readiness(self.r)['reasons'])
if __name__=='__main__':unittest.main(verbosity=2)
