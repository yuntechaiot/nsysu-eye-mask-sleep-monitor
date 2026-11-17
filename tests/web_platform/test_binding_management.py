"""Signature-verified, confirmed cancellation releases only the owner's binding."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import uuid

import pytest
from werkzeug.security import generate_password_hash

from nsysu.acceptance_adapter import RecordingLine, SyntheticDiary
from nsysu.line_menu import binding_rich_menu
from nsysu.reminders import FlowError, ReminderService, State, TZ, digest


@pytest.fixture
def flow(tmp_path):
    state = State(tmp_path / 'state.sqlite3', initialize=True)
    diary = SyntheticDiary(state)
    for number in (1, 50):
        member = f'ycc{number:08}'
        state.enroll(member, generate_password_hash('SYNTHETIC_PASSWORD'), 'study-A', member)
        with state.connect() as db:
            db.execute('insert into acceptance_invites values(?,?)', (member, f'{number:064x}'))
    clock = [datetime(2026, 11, 18, 9, tzinfo=TZ)]
    service = ReminderService(state, RecordingLine(), diary, 'http://127.0.0.1:64660/', 'TEST_LIFF', 'TEST_SECRET', clock=lambda: clock[0])
    service.test_clock = clock
    post(service, 'binding:start')
    service.bind(service.line.token, 'ycc00000001', 'SYNTHETIC_PASSWORD')
    return service


def post(service, data, identity=None, eid=None):
    event = {'type': 'postback', 'webhookEventId': eid or str(uuid.uuid4()), 'timestamp': int(service.clock().timestamp()*1000),
             'source': {'type': 'user', 'userId': identity or service.line.identity}, 'postback': {'data': data}}
    raw = json.dumps({'events': [event]}).encode()
    signature = base64.b64encode(hmac.new(service.secret.encode(), raw, hashlib.sha256).digest()).decode()
    return service.webhook(raw, signature)


def rows(service, table):
    with service.state.connect() as db:
        return [dict(row) for row in db.execute('select * from ' + table)]


def challenge(service):
    post(service, 'binding:cancel')
    message = json.loads(rows(service, 'outbox')[-1]['payload'])['messages'][0]
    return message['template']['actions'][0]['data']


def test_menu_actions_and_rebind_do_not_silently_replace_account(flow):
    before = rows(flow, 'bindings')
    menu = binding_rich_menu()
    for area in menu['areas'][:2]:
        post(flow, area['action']['data'])
    assert rows(flow, 'bindings') == before
    response = json.loads(rows(flow, 'outbox')[-1]['payload'])['messages'][0]
    assert 'ycc00000001' in response['template']['text']
    with pytest.raises(FlowError) as conflict:
        flow.bind(flow.line.token, 'ycc00000050', 'SYNTHETIC_PASSWORD')
    assert conflict.value.status == 409


def test_confirmed_cancel_preserves_records_cancels_uncertain_jobs_and_allows_new_account(flow):
    original = rows(flow, 'bindings')[0]
    flow.test_clock[0] += timedelta(days=1)
    flow.line.result = 'uncertain'
    flow.tick(send=True)
    with flow.state.connect() as db:
        db.execute("insert into acceptance_logs(member,date,entry) values('ycc00000001','2026-11-18','{}')")
    confirmation = challenge(flow)
    assert rows(flow, 'bindings')  # Clicking Cancel alone has no effect.
    post(flow, confirmation)
    assert not rows(flow, 'bindings')
    history = rows(flow, 'binding_history')
    assert len(history) == 1 and history[0]['bound_at'] == original['bound_at']
    assert history[0]['reminder_start'] == original['reminder_start']
    assert len(rows(flow, 'acceptance_logs')) == 1
    assert all(row['status'] == 'cancelled' for row in rows(flow, 'outbox') if row['kind'] == 'diary')
    before_calls = len(flow.line.calls)
    flow.line.result = 'accepted'
    flow.tick(send=True)
    assert not any(call['payload']['messages'][0].get('altText') == '請填寫睡眠日誌' for call in flow.line.calls[before_calls:])
    with pytest.raises(FlowError):
        flow.bind(flow.line.token, 'ycc00000050', 'WRONG_PASSWORD')
    result = flow.bind(flow.line.token, 'ycc00000050', 'SYNTHETIC_PASSWORD')
    assert result['first_reminder_at'] == '2026-11-20T09:00:00+08:00'
    assert rows(flow, 'bindings')[0]['account_hash'] == digest('ycc00000050')


def test_confirmation_is_owner_scoped_expiring_and_one_time(flow):
    data = challenge(flow)
    post(flow, data, identity='SYNTHETIC_OTHER')
    assert rows(flow, 'bindings')
    flow.test_clock[0] += timedelta(minutes=11)
    post(flow, data)
    assert rows(flow, 'bindings')
    data = challenge(flow)
    post(flow, data.replace(':confirm:', ':keep:'))
    post(flow, data)
    assert rows(flow, 'bindings') and not rows(flow, 'binding_history')


def test_stale_confirmation_cannot_cancel_new_binding_even_with_frozen_clock(flow):
    old = challenge(flow)
    current = challenge(flow)
    post(flow, old)
    assert rows(flow, 'bindings')
    post(flow, current)
    flow.bind(flow.line.token, 'ycc00000001', 'SYNTHETIC_PASSWORD')
    post(flow, current)
    assert len(rows(flow, 'bindings')) == 1
    assert len(rows(flow, 'binding_history')) == 1


def test_duplicate_and_concurrent_confirmation_archives_once(flow):
    data = challenge(flow)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda eid: post(flow, data, eid=eid), ['same-confirmation', 'same-confirmation', 'other-confirmation']))
    assert not rows(flow, 'bindings') and len(rows(flow, 'binding_history')) == 1
    assert sum(row['job_key'] == 'binding:same-confirmation' for row in rows(flow, 'outbox')) == 1


def test_menu_does_not_bypass_signature_allowlist_or_disabled_binding(flow):
    with pytest.raises(FlowError):
        flow.webhook(b'{"events":[]}', 'INVALID_SIGNATURE')
    flow.allowed_users = frozenset({flow.line.identity})
    assert post(flow, 'binding:cancel', identity='SYNTHETIC_OTHER')['processed'] == 0
    with flow.state.connect() as db:
        db.execute('update bindings set active=0')
    post(flow, 'binding:cancel')
    assert not rows(flow, 'binding_cancellations')
    assert rows(flow, 'bindings')[0]['active'] == 0


def test_cancel_releases_old_account_but_cannot_take_another_lines_account(flow):
    owner = flow.line.identity
    data = challenge(flow)
    flow.line.identity = 'SYNTHETIC_OTHER'
    post(flow, 'binding:start')
    flow.bind(flow.line.token, 'ycc00000050', 'SYNTHETIC_PASSWORD')
    flow.line.identity = owner
    post(flow, data)
    with pytest.raises(FlowError) as conflict:
        flow.bind(flow.line.token, 'ycc00000050', 'SYNTHETIC_PASSWORD')
    assert conflict.value.status == 409
    assert len(rows(flow, 'bindings')) == 1


def test_explicit_v2_upgrade_preserves_binding_and_outbox(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    sql = Path(__file__).resolve().parents[2] / 'backend/nsysu/sql'
    with sqlite3.connect(path) as db:
        db.executescript((sql / 'line_state.sql').read_text())
        db.executescript((sql / 'line_state_v2.sql').read_text())
        db.execute('insert into accounts values(?,?,?,?,?,?,1)', ('hash', 'synthetic', 'study', 'ycc00000001', None, None))
        db.execute('insert into bindings values(?,?,?,?,1)', ('SYNTHETIC_LINE', 'hash', '2026-11-17T23:59:00+08:00', '2026-11-18'))
        db.execute('''insert into outbox(job_key,kind,line_user,due_at,retry_key,payload,status,attempts,uncertainty)
            values('SYNTHETIC_JOB','welcome','SYNTHETIC_LINE','2026-11-18T09:00:00+08:00','SYNTHETIC_RETRY','{}','uncertain',1,1)''')
    backup = tmp_path / 'backup.sqlite3'
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as dest:
        source.backup(dest)
    with pytest.raises(RuntimeError, match='migration'):
        State(path)
    upgraded = State(path, initialize=True)
    State(path, initialize=True)  # Rerun is safe.
    with upgraded.connect() as db:
        assert db.execute('select max(version) from schema_version').fetchone()[0] == 3
        assert db.execute('select bound_at from bindings').fetchone()[0] == '2026-11-17T23:59:00+08:00'
        job = db.execute('select * from outbox').fetchone()
        assert job['status'] == 'uncertain' and job['attempts'] == 1 and job['retry_key'] == 'SYNTHETIC_RETRY'
        assert not db.execute('pragma foreign_key_check').fetchall()
    with sqlite3.connect(backup) as db:
        assert db.execute('select max(version) from schema_version').fetchone()[0] == 2
        assert db.execute('select count(*) from bindings').fetchone()[0] == 1
    with sqlite3.connect(path) as db:
        db.executescript((sql / 'rollback_line_state.sql').read_text())
        assert not db.execute("select name from sqlite_master where type='table'").fetchall()
