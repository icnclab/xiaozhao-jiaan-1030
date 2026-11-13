"""Isolated, rollback-only PostgreSQL notification integration probe.

Execute with the repository Python: python tools/xz_ltc_test_notification_probe.py
Only connects to a local database whose CURRENT_DATABASE() is exactly ltc_test.
No persistent writes, no schema changes, no live LINE calls, no pytest autouse fixtures.
"""
from __future__ import annotations

import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

REPO = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[2]
BACKEND = REPO / 'backend'
sys.path.insert(0, str(BACKEND))


def fail(message: str, code: int = 1) -> None:
    print(message, flush=True)
    raise SystemExit(code)


def test_url():
    env_file = REPO / '.env'
    if not env_file.is_file():
        fail('SKIP: LOCAL_TEST_DB_URL_NOT_CONFIGURED', 0)
    lines = env_file.read_text(encoding='utf-8-sig').splitlines()
    settings = [line.partition('=')[2].split('#', 1)[0].strip().strip('"\'')
                for line in lines if line.strip().startswith('TEST_DATABASE_URL=')]
    if len(settings) != 1 or not settings[0]:
        fail('SKIP: LOCAL_TEST_DB_URL_NOT_CONFIGURED', 0)
    from sqlalchemy.engine import make_url
    try:
        parsed = make_url(settings[0])
    except Exception:
        fail('STOP: INVALID_TEST_DATABASE_URL')
    if parsed.database != 'ltc_test' or parsed.host not in ('localhost', '127.0.0.1', '::1'):
        fail('STOP: REFUSED_NON_LOCAL_OR_NON_TEST_DATABASE', 3)
    return settings[0]


def main() -> None:
    db_url = test_url()
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import Session
    from app.models import Organization, User, LineAccount, NotificationJob
    from app.services import jiaan_emergency_dispatch as dispatch
    from app.services import notifications

    engine = create_engine(db_url, pool_pre_ping=True)
    original_switch = os.environ.get('JIAAN_EMERGENCY_LINE_DISPATCH')
    try:
        with engine.connect() as conn:
            db_name = conn.execute(text('SELECT current_database()')).scalar_one()
            if db_name != 'ltc_test':
                fail('STOP: CONNECTED_DATABASE_IS_NOT_LTC_TEST', 3)
            expected_tables = ('organizations', 'users', 'line_accounts', 'jobs',
                               'notification_jobs', 'jiaan1030_emergencies')
            missing = [table for table in expected_tables if conn.execute(
                text('SELECT to_regclass(:name)'), {'name': 'public.' + table}
            ).scalar_one() is None]
            if missing:
                print('SKIP: LTC_TEST_SCHEMA_MISSING ' + ','.join(missing))
                return
            conn.rollback()
            outer = conn.begin()
            session = Session(bind=conn, expire_on_commit=False)
            try:
                unique = uuid.uuid4().hex[:10]
                home = Organization(code='XZ' + unique.upper(), name='XZ合成測試機構', facility_type='home')
                other = Organization(code='XY' + unique.upper(), name='XY其他測試機構', facility_type='home')
                session.add_all([home, other]); session.flush()
                cg = User(org_id=home.id, username='xz_cg_' + unique, display_name='測試照服員', role='caregiver')
                sup1 = User(org_id=home.id, username='xz_s1_' + unique, display_name='測試督導A', role='supervisor')
                sup2 = User(org_id=home.id, username='xz_s2_' + unique, display_name='測試督導B', role='supervisor')
                director = User(org_id=home.id, username='xz_d_' + unique, display_name='測試主任', role='director')
                outsider = User(org_id=other.id, username='xz_o_' + unique, display_name='外機構督導', role='supervisor')
                session.add_all([cg, sup1, sup2, director, outsider]); session.flush()
                for user in (sup1, sup2, director, outsider):
                    session.add(LineAccount(user_id=user.id, line_user_id='U' + uuid.uuid4().hex,
                                            linked_at=datetime.now(timezone.utc), is_blocked=False))
                session.flush()
                incident = uuid.uuid4()
                session.execute(text('''
                    INSERT INTO public.jiaan1030_emergencies
                      (id, org_id, created_by, client_request_id, category, status, created_at)
                    VALUES (:id, :org, :cg, :req, 'fall', 'open', now() - interval '205 seconds')
                '''), {'id': incident, 'org': home.id, 'cg': cg.id, 'req': uuid.uuid4()})
                session.flush()
                # The flag is changed ONLY in this one-shot Python probe process.
                os.environ['JIAAN_EMERGENCY_LINE_DISPATCH'] = 'on'
                count = dispatch.sweep(session, now=datetime.now(timezone.utc))
                session.flush()
                jobs = session.scalars(select(NotificationJob).where(
                    NotificationJob.source_type == 'jiaan_emergency',
                    NotificationJob.payload['emergency_id'].as_string() == str(incident)
                )).all()
                assert len(jobs) == 5, f'expected 5 jobs, got {len(jobs)} (sweep={count})'
                assert len({j.source_id for j in jobs}) == len(jobs), 'source IDs not unique'
                assert {j.recipient_id for j in jobs} == {sup1.id, sup2.id, director.id}, 'wrong recipients'
                assert all(j.org_id == home.id for j in jobs), 'cross-org notification detected'
                staged = {(j.payload['stage'], j.recipient_id) for j in jobs}
                assert ('new', sup1.id) in staged and ('new', sup2.id) in staged
                assert ('unacknowledged_60s', sup1.id) in staged
                assert ('unacknowledged_180s', director.id) in staged
                again = dispatch.sweep(session, now=datetime.now(timezone.utc))
                session.flush()
                second = session.scalars(select(NotificationJob).where(
                    NotificationJob.source_type == 'jiaan_emergency',
                    NotificationJob.payload['emergency_id'].as_string() == str(incident)
                )).all()
                assert len(second) == 5, 'sweep was not idempotent'
                # Two DB transactions cannot claim the same sweep advisory lock concurrently.
                with engine.connect() as competing:
                    locked = competing.execute(text(
                        'SELECT pg_try_advisory_xact_lock(16430102, 20261102)'
                    )).scalar_one()
                    assert locked is False, 'concurrent sweep lock not effective'
                    competing.rollback()
                # Test failure -> retry -> LINE accepts using an in-process fake client.
                selected = next(j for j in jobs if j.payload['stage'] == 'new' and j.recipient_id == sup1.id)
                attempts = []
                class FakeLineClient:
                    def push(self, line_user_id, messages, retry_key):
                        attempts.append((line_user_id, retry_key))
                        if len(attempts) == 1:
                            return SimpleNamespace(accepted=False, status_code=503,
                                                   error_code='mock_503', retryable=True)
                        return SimpleNamespace(accepted=True, status_code=200,
                                               error_code=None, retryable=False)
                with mock.patch.object(notifications, 'get_line_client', return_value=FakeLineClient()), \
                     mock.patch.object(notifications, 'build_messages', return_value=[{'type': 'text', 'text': 'synthetic test'}]):
                    first = notifications.send(session, selected.id)
                    assert first == (False, True), f'expected retryable failure: {first}'
                    session.flush()
                    assert selected.status == 'failed'
                    second_attempt = notifications.send(session, selected.id)
                    assert second_attempt == (True, False), f'expected accepted: {second_attempt}'
                    session.flush()
                    assert selected.status == 'accepted'
                assert len(attempts) == 2 and attempts[0][1] == attempts[1][1], 'retry key changed'
                # Acknowledged incident must not generate any new LINE push.
                session.execute(text('''UPDATE public.jiaan1030_emergencies
                    SET status='acknowledged', acknowledged_by=:uid, acknowledged_at=now()
                    WHERE id=:eid'''), {'uid': sup2.id, 'eid': incident})
                blocked = next(j for j in jobs if j.payload['stage'] == 'new' and j.recipient_id == sup2.id)
                with mock.patch.object(notifications, 'get_line_client', side_effect=AssertionError('LINE must not be called')):
                    skipped = notifications.send(session, blocked.id)
                assert skipped == (True, False) and blocked.status == 'skipped', 'acknowledged alert was sent'
                # Off switch must block previously enqueued alerts even without ack state.
                os.environ['JIAAN_EMERGENCY_LINE_DISPATCH'] = 'off'
                other_notice = next(j for j in jobs if j.payload['stage'] == 'unacknowledged_60s' and j.recipient_id == sup1.id)
                with mock.patch.object(notifications, 'get_line_client', side_effect=AssertionError('LINE must stay off')):
                    skip_off = notifications.send(session, other_notice.id)
                assert skip_off == (True, False) and other_notice.last_error_code == 'feature_disabled'
                print('PASS: LTC_TEST_MULTIRECIPIENT_ROLES_STAGE_DEDUP')
                print('PASS: LTC_TEST_CONCURRENT_SWEEP_LOCK')
                print('PASS: LTC_TEST_MOCK_LINE_RETRY_KEY')
                print('PASS: LTC_TEST_ACKNOWLEDGE_CANCEL_AND_FLAG_OFF')
                print('NO_REAL_LINE_CALLS; ALL_SYNTHETIC_DB_ROWS_ROLLED_BACK')
            finally:
                session.close()
                if outer.is_active:
                    outer.rollback()
    finally:
        if original_switch is None:
            os.environ.pop('JIAAN_EMERGENCY_LINE_DISPATCH', None)
        else:
            os.environ['JIAAN_EMERGENCY_LINE_DISPATCH'] = original_switch
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, Exception) as exc:
        print('FAILED: LTC_TEST_EMERGENCY_INTEGRATION ' + type(exc).__name__ + ': ' + str(exc)[:240])
        raise SystemExit(1)
