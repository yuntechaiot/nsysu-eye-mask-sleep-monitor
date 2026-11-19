"""Chat responses start after commit, without waiting for the diary timer."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import hmac
import json
from threading import Event

import pytest
from werkzeug.security import generate_password_hash

from nsysu.acceptance_adapter import RecordingLine, SyntheticDiary
from nsysu.reminders import ReminderService, State, TZ
from nsysu.server import create_app


@pytest.fixture
def flow(tmp_path):
    state = State(tmp_path / 'state.sqlite3', initialize=True)
    diary = SyntheticDiary(state)
    state.enroll('ycc00000001', generate_password_hash('SYNTHETIC_PASSWORD'), 'study-A', 'ycc00000001')
    with state.connect() as db:
        db.execute('insert into acceptance_invites values(?,?)', ('ycc00000001', 'a'*64))
        db.execute('insert into friends values(?,?,?)', ('SYNTHETIC_LINE_A', 1, 1))
    clock = [datetime(2026, 11, 18, 9, tzinfo=TZ)]
    line = RecordingLine()
    line.identity = 'SYNTHETIC_LINE_A'
    service = ReminderService(state, line, diary, 'http://127.0.0.1:64660/', 'TEST_LIFF', 'TEST_SECRET', clock=lambda: clock[0])
    service.bind(line.token, 'ycc00000001', 'SYNTHETIC_PASSWORD')
    clock[0] += timedelta(days=1)  # The diary is now eligible, but chat must not run it.
    return service


def payload(flow, eid='SYNTHETIC_EVENT'):
    raw = json.dumps({'events': [{'type': 'postback', 'webhookEventId': eid, 'timestamp': int(flow.clock().timestamp()*1000),
        'source': {'type': 'user', 'userId': flow.line.identity}, 'postback': {'data': 'binding:cancel'}}]}).encode()
    signature = base64.b64encode(hmac.new(flow.secret.encode(), raw, hashlib.sha256).digest()).decode()
    return raw, signature


def test_dispatch_notification_occurs_after_commit_and_only_for_new_verified_events(flow):
    raw, signature = payload(flow)
    notified = []
    def notify(keys):
        with flow.state.connect() as db:
            assert db.execute('select count(*) from binding_cancellations').fetchone()[0] == 1
            assert db.execute('select status from outbox where job_key=?', (keys[0],)).fetchone()[0] == 'pending'
        notified.append(keys)
    assert flow.webhook(raw, signature, on_enqueued=notify)['processed'] == 1
    assert flow.webhook(raw, signature, on_enqueued=notify)['processed'] == 0
    assert notified == [('binding:SYNTHETIC_EVENT',)]


def test_route_starts_sender_without_tick_and_does_not_wait_for_network(flow):
    app = create_app()
    app.extensions['reminders'] = flow
    app.extensions['line_interaction_sending_enabled'] = lambda: True
    entered, release = Event(), Event()
    original = flow.line.push
    def blocked(payload, retry_key):
        entered.set()
        assert release.wait(5)
        return original(payload, retry_key)
    flow.line.push = blocked
    raw, signature = payload(flow)
    try:
        response = app.test_client().post('/api/line/webhook', data=raw, headers={'X-Line-Signature': signature})
        assert response.status_code == 200
        assert entered.wait(2)  # No timer or explicit tick has run.
        with flow.state.connect() as db:
            assert db.execute("select count(*) from outbox where kind='diary'").fetchone()[0] == 0
        # Even a slow LINE HTTP call cannot hold this webhook response open.
        assert not release.is_set()
    finally:
        release.set()
        executor = app.extensions.get('line_interaction_executor')
        if executor:
            executor.shutdown(wait=True)
    assert len(flow.line.calls) == 1
    flow.tick(send=True)  # The timer does not send the accepted chat message again.
    assert sum(any(a.get('data', '').startswith('binding:confirm:') for a in call['payload']['messages'][0].get('template', {}).get('actions', [])) for call in flow.line.calls) == 1


def test_stopped_sending_and_invalid_signature_cannot_start_background_sender(flow):
    app = create_app()
    app.extensions['reminders'] = flow
    app.extensions['line_interaction_sending_enabled'] = lambda: False
    raw, signature = payload(flow)
    client = app.test_client()
    assert client.post('/api/line/webhook', data=raw, headers={'X-Line-Signature': signature}).status_code == 200
    assert 'line_interaction_executor' not in app.extensions
    app.extensions['line_interaction_sending_enabled'] = lambda: True
    assert client.post('/api/line/webhook', data=raw, headers={'X-Line-Signature': 'INVALID'}).status_code == 401
    assert 'line_interaction_executor' not in app.extensions
    assert not flow.line.calls


def test_network_failure_retains_intent_for_existing_worker(flow):
    raw, signature = payload(flow)
    flow.line.result = 'uncertain'
    keys = []
    flow.webhook(raw, signature, on_enqueued=keys.extend)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: flow.dispatch(keys, send=True), range(2)))
    with flow.state.connect() as db:
        row = db.execute('select * from outbox where job_key=?', (keys[0],)).fetchone()
        assert row['status'] == 'uncertain' and row['attempts'] == 1
        retry_key = row['retry_key']
    flow.clock = lambda: datetime(2026, 11, 19, 9, 1, tzinfo=TZ)
    flow.line.result = 'accepted'
    flow.tick(send=True)
    with flow.state.connect() as db:
        row = db.execute('select * from outbox where job_key=?', (keys[0],)).fetchone()
        assert row['status'] == 'accepted' and row['attempts'] == 2 and row['retry_key'] == retry_key
