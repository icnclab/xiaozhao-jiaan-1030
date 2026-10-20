"""Direct unittest only. Real list_categories body + actual models + SQLite memory.

Never import app routes/pytest fixtures, read credentials or call production get_engine.
"""
import ast
import json
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import Category, CategoryTemplate

PACKET = ROOT / 'docs/report_template_candidates_20261017.json'


def isolated_route():
    tree = ast.parse((ROOT / 'backend/app/api/caregiver_routes.py').read_text(encoding='utf-8-sig'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'list_categories')
    fn.decorator_list = []
    fn.returns = None
    fn.args.defaults = []
    for arg in fn.args.args:
        arg.annotation = None
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    env = dict(select=select, Category=Category, CategoryTemplate=CategoryTemplate)
    exec(compile(module, '<isolated real list_categories>', 'exec'), env)
    return env['list_categories']


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.packet = json.loads(PACKET.read_text(encoding='utf-8'))

    def test_eight_groups_three_each_24_unique(self):
        groups = self.packet['groups']
        self.assertEqual([g['candidate_group'] for g in groups], [
            '家屬額外要求', '服務範圍', '移位', '沐浴', '飲食', '事件處理', '紀錄申報', '其他'])
        self.assertTrue(all(len(g['questions']) == 3 for g in groups))
        questions = [q for g in groups for q in g['questions']]
        self.assertEqual(len(questions), 24)
        self.assertEqual(len(set(questions)), 24)
        self.assertTrue(all(0 < len(q) <= 200 for q in questions))

    def test_no_guessed_mapping_or_approval(self):
        self.assertIsNone(self.packet['org_id'])
        self.assertIs(self.packet['human_approved'], False)
        self.assertIs(self.packet['is_active'], False)
        for group in self.packet['groups']:
            self.assertIsNone(group['category_id'])
            self.assertIsNone(group['actual_category_name'])
            self.assertIs(group['mapping_confirmed'], False)

    def test_source_and_emergency_notice_preserved(self):
        self.assertEqual(self.packet['source'], '小照專題情境設計，待嘉安確認')
        self.assertIn('不取代正式緊急處理', self.packet['warning'])
        self.assertEqual(self.packet['format'], 'review_only_not_api_payload')

    def test_schema_has_activation_but_no_review_or_source(self):
        columns = set(CategoryTemplate.__table__.columns.keys())
        self.assertEqual(columns, {'id', 'category_id', 'text', 'sort_order', 'is_active'})
        self.assertEqual(CategoryTemplate.__tablename__, 'category_templates')


class TemplateReadTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:')
        self.assertEqual(self.engine.url.database, ':memory:')
        Category.__table__.create(self.engine)
        CategoryTemplate.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.org = uuid.uuid4()
        self.other_org = uuid.uuid4()
        self.categories = []
        for i, group in enumerate(json.loads(PACKET.read_text(encoding='utf-8'))['groups']):
            category = Category(id=uuid.uuid4(), org_id=self.org, name=group['candidate_group'], sort_order=i, is_active=True)
            self.db.add(category)
            self.categories.append(category)
            for j, text in enumerate(group['questions']):
                self.db.add(CategoryTemplate(id=uuid.uuid4(), category_id=category.id, text=text, sort_order=j, is_active=True))
        self.private = Category(id=uuid.uuid4(), org_id=self.other_org, name='private-only', is_active=True)
        self.disabled = Category(id=uuid.uuid4(), org_id=self.org, name='disabled-only', is_active=False)
        self.db.add_all([self.private, self.disabled])
        self.db.add_all([
            CategoryTemplate(id=uuid.uuid4(), category_id=self.private.id, text='other org private template', is_active=True),
            CategoryTemplate(id=uuid.uuid4(), category_id=self.disabled.id, text='disabled category template', is_active=True),
            CategoryTemplate(id=uuid.uuid4(), category_id=self.categories[0].id, text='inactive unapproved fixture', is_active=False),
        ])
        self.db.commit()
        self.route = isolated_route()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_confirmed_fixture_mapping_returns_three_per_category(self):
        result = self.route(SimpleNamespace(org_id=self.org), self.db)
        self.assertEqual(len(result), 8)
        for category, row in zip(self.categories, result):
            self.assertEqual(row['id'], str(category.id))
            self.assertEqual(row['name'], category.name)
            self.assertEqual(len(row['templates']), 3)
        self.assertEqual(sum(len(row['templates']) for row in result), 24)

    def test_other_org_and_disabled_templates_not_returned(self):
        result = self.route(SimpleNamespace(org_id=self.org), self.db)
        text = json.dumps(result)
        self.assertNotIn('private-only', text)
        self.assertNotIn('other org private template', text)
        self.assertNotIn('inactive unapproved fixture', text)
        self.assertNotIn('disabled category template', text)

    def test_empty_org_does_not_fall_back_to_private_templates(self):
        self.assertEqual(self.route(SimpleNamespace(org_id=uuid.uuid4()), self.db), [])

    def test_template_read_has_no_writes(self):
        from sqlalchemy import event
        statements = []
        def record(conn, cursor, statement, params, context, many):
            statements.append(statement.strip().split()[0].upper())
        event.listen(self.engine, 'before_cursor_execute', record)
        self.route(SimpleNamespace(org_id=self.org), self.db)
        self.assertTrue(statements)
        self.assertEqual(set(statements), {'SELECT'})
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)


if __name__ == '__main__':
    unittest.main()
