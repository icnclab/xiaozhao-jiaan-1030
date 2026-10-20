"""Run directly: isolated PostgreSQL DB, rollback per test; no runtime data reset."""
import unittest
import uuid

from test_account_permissions import Accounts
from app.api import caregiver_routes
from app.auth import issue_session
from app.models import AuditLog, Category, LineAccount, NotificationJob, User
from sqlalchemy import select


class CaseVisibility(Accounts):
    def setUp(self):
        super().setUp()
        self.client.app.include_router(caregiver_routes.router, prefix='/api')
        self.category = Category(org_id=self.users['admin'].org_id, name='測試分類')
        self.s.add(self.category)
        for index, name in enumerate(['test_cg01', 'test_cg02', 'test_cg03', 'jiaan_cg01', 'testXcg01']):
            user = User(org_id=self.category.org_id, username=name, display_name='相同顯示名稱', role='caregiver')
            self.s.add(user); self.s.flush()
            self.users[name] = user
            self.s.add(LineAccount(user_id=user.id, line_user_id='U' + str(index + 1) * 32))
            self.headers[name] = {'Authorization': 'Bearer ' + issue_session(self.s, user, 'liff')}
        self.s.commit()

    def create(self, name):
        response = self.client.post('/api/cases', headers=self.headers[name], json={
            'category_id': str(self.category.id), 'text': '案件分流測試',
            'client_request_id': str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'pending')
        return response.json()

    def test_prefix_visibility_and_roles(self):
        cases = {name: self.create(name) for name in ['test_cg01', 'test_cg02', 'test_cg03', 'jiaan_cg01', 'testXcg01']}
        for actor in ['admin', 'supervisor']:
            for suffix in ['', '&include_test=false', '&include_test=true']:
                response = self.request(actor, 'GET', 'cases?status=pending' + suffix)
                self.assertEqual(response.status_code, 200)
                rows = {row['id']: row for row in response.json()}
                for name, case in cases.items():
                    expected = not name.startswith('test_') or suffix.endswith('true')
                    self.assertEqual(case['id'] in rows, expected)
                    if expected:
                        self.assertEqual(rows[case['id']]['is_test'], name.startswith('test_'))
        self.assertEqual(self.request('caregiver', 'GET', 'cases?include_test=true').status_code, 403)
        self.assertEqual(self.request('admin', 'GET', 'cases?include_test=true&q=nonexistent').json(), [])

    def test_test_case_lifecycle_audit_and_line(self):
        case = self.create('test_cg01')
        cid = case['id']
        response = self.request('supervisor', 'POST', f'cases/{cid}/take')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'in_progress')
        response = self.request('supervisor', 'POST', f'cases/{cid}/reply', json={
            'text': '測試回覆', 'client_request_id': str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['reply_saved'])
        self.assertEqual(response.json()['notification']['status'], 'queued')
        note = self.s.get(NotificationJob, uuid.UUID(response.json()['notification']['id']))
        self.assertEqual(note.channel, 'line')
        self.assertEqual(note.recipient_id, self.users['test_cg01'].id)
        mine = self.client.get('/api/cases/mine', headers=self.headers['test_cg01']).json()
        self.assertTrue(next(row for row in mine if row['id'] == cid)['has_reply'])
        response = self.request('supervisor', 'POST', f'cases/{cid}/close', json={'reason': '測試完成'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'closed')
        actions = set(self.s.scalars(select(AuditLog.action).where(AuditLog.target_id == cid)))
        self.assertTrue({'case.create', 'case.take', 'case.reply', 'case.close'} <= actions)
        detail = self.request('admin', 'GET', f'cases/{cid}').json()
        self.assertTrue({'created', 'taken', 'replied', 'closed'} <= {event['kind'] for event in detail['events']})

    def test_all_statuses_and_deleted_creator(self):
        test = self.create('test_cg01')
        formal = self.create('jiaan_cg01')
        from app.models import Case
        for deleted in [False, True]:
            if deleted:
                for name in ['test_cg01', 'jiaan_cg01']:
                    response = self.request('admin', 'DELETE', f'users/{self.users[name].id}')
                    self.assertEqual(response.status_code, 200)
            for status in ['pending', 'in_progress', 'replied', 'closed']:
                for case in [test, formal]:
                    self.s.get(Case, uuid.UUID(case['id'])).status = status
                self.s.commit()
                for actor in ['admin', 'supervisor']:
                    for suffix in ['', '&include_test=false', '&include_test=true']:
                        response = self.request(actor, 'GET', f'cases?status={status}' + suffix)
                        self.assertEqual(response.status_code, 200, response.text)
                        rows = {row['id']: row for row in response.json()}
                        self.assertIn(formal['id'], rows)
                        self.assertFalse(rows[formal['id']]['is_test'])
                        self.assertEqual(test['id'] in rows, suffix.endswith('true'))
                        if test['id'] in rows:
                            self.assertTrue(rows[test['id']]['is_test'])


if __name__ == '__main__':
    # Only run this class's cases, not inherited account tests.
    suite = unittest.TestSuite(CaseVisibility(name) for name in [
        'test_prefix_visibility_and_roles', 'test_test_case_lifecycle_audit_and_line',
        'test_all_statuses_and_deleted_creator'])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
