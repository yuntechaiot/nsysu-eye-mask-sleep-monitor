"""Synthetic integrations with controlled Taipei clock and durable SQLite."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import hmac
import json
import sqlite3
import uuid

import pytest
from werkzeug.security import generate_password_hash

from nsysu.acceptance_adapter import RecordingLine, SyntheticDiary
from nsysu.reminders import FlowError, LineAPI, ReminderService, Schedule, State, TZ, digest, valid_account
from nsysu.server import create_app


@pytest.fixture
def flow(tmp_path):
    state = State(tmp_path / 'line.sqlite3', initialize=True)
    source = SyntheticDiary(state)
    password = 'SYNTHETIC_RANDOM_PASSWORD'
    for number in (1, 50):
        state.enroll(f'ycc{number:08}', generate_password_hash(password), 'study-A', f'ycc{number:08}')
        with state.connect() as db:
            db.execute('insert into acceptance_invites values(?,?)', (f'ycc{number:08}', f'{number:064x}'))
    clock = [datetime(2026, 11, 17, 23, 59, tzinfo=TZ)]
    service = ReminderService(state, RecordingLine(), source, 'http://127.0.0.1:64660/', 'TEST_LIFF', 'TEST_SECRET', clock=lambda: clock[0])
    service.test_clock = clock
    return service


def event(service, kind='follow', eid=None, stamp=None):
    value = {'type': kind, 'webhookEventId': eid or str(uuid.uuid4()), 'timestamp': stamp if stamp is not None else int(service.clock().timestamp() * 1000),
             'source': {'type': 'user', 'userId': service.line.identity}}
    if kind == 'message':
        value['message'] = {'type': 'text', 'text': '開始綁定'}
    raw = json.dumps({'events': [value]}).encode()
    signature = base64.b64encode(hmac.new(service.secret.encode(), raw, hashlib.sha256).digest()).decode()
    return service.webhook(raw, signature)


def bind(service, account='ycc00000001'):
    event(service)
    return service.bind(service.line.token, account, 'SYNTHETIC_RANDOM_PASSWORD')


def at(service, day=18, hour=9, minute=0):
    service.test_clock[0] = datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def jobs(service, kind='diary'):
    with service.state.connect() as db:
        return [dict(r) for r in db.execute('select * from outbox where kind=?', (kind,))]


@pytest.mark.parametrize('value,valid', [('ycc00000001', True), ('ycc00000050', True), ('ycc00000000', False),
    ('ycc00000051', False), ('ycc1', False), ('yc00000001', False), ('YCC00000001', False), ('ycc000000010', False)])
def test_account_string_boundaries(value, valid):
    assert valid_account(value) is valid


def test_follow_signature_dedup_and_command(flow):
    with pytest.raises(FlowError):
        flow.webhook(b'{invalid', 'bad')  # signature checked before JSON
    assert event(flow, eid='same')['processed'] == 1
    assert event(flow, eid='same')['processed'] == 0
    assert len(jobs(flow, 'welcome')) == 1
    event(flow, 'message')
    assert len(jobs(flow, 'welcome')) == 2
    flow.tick(send=True)
    assert len(flow.line.calls) == 2


@pytest.mark.parametrize('account,password', [('ycc00000000', 'bad'), ('ycc00000051', 'bad'), ('ycc00000001', 'bad'), ('ycc00000002', 'SYNTHETIC_RANDOM_PASSWORD')])
def test_unregistered_bad_password_and_format_rejected(flow, account, password):
    event(flow)
    with pytest.raises(FlowError) as error:
        flow.bind(flow.line.token, account, password)
    assert error.value.status == 401


def test_both_boundaries_bind_without_official_auth_claim(flow):
    result = bind(flow, 'ycc00000050')
    assert result['verification'] == 'local_research'
    assert result['simulated'] is True
    assert 'Docter' not in json.dumps(result)


def test_idempotent_conflict_token_cancellation_and_limits(flow):
    result = bind(flow)
    assert flow.bind(flow.line.token, 'ycc00000001', 'SYNTHETIC_RANDOM_PASSWORD') == result
    flow.line.identity = 'SYNTHETIC_OTHER'
    event(flow)
    with pytest.raises(FlowError) as conflict:
        flow.bind(flow.line.token, 'ycc00000001', 'SYNTHETIC_RANDOM_PASSWORD')
    assert conflict.value.status == 409
    with pytest.raises(FlowError) as expired:
        flow.bind('EXPIRED_TOKEN', 'ycc00000001', 'SYNTHETIC_RANDOM_PASSWORD')
    assert expired.value.status == 401
    for _ in range(7):
        try:
            flow.bind(flow.line.token, 'ycc00000050', 'wrong')
        except FlowError:
            pass
    with pytest.raises(FlowError) as limited:
        flow.bind(flow.line.token, 'ycc00000050', 'wrong')
    assert limited.value.status == 429


def test_next_taipei_day_not_24_hours_and_all_slots(flow):
    result = bind(flow)
    assert result['first_reminder_at'] == '2026-11-18T09:00:00+08:00'
    flow.tick(send=True)
    assert not jobs(flow)
    for hour in range(24):
        at(flow, hour=hour)
        flow.tick(send=True)
        flow.tick(send=True)
    rows = jobs(flow)
    assert sorted(row['slot'] for row in rows) == ['09:00', '11:00', '13:00', '15:00', '17:00', '19:00', '21:00']
    assert all(row['status'] == 'accepted' and row['attempts'] == 1 for row in rows)


def test_click_draft_wrong_date_wrong_study_do_not_complete(flow):
    bind(flow)
    at(flow)
    flow.tick(send=True)
    assert len(jobs(flow)) == 1
    # An opened link has no effect. Only persisted final entries are queried.
    with flow.state.connect() as db:
        db.execute('insert into acceptance_logs(member,date,entry) values(?,?,?)', ('ycc00000001', '2026-11-17', '{}'))
        db.execute('insert into acceptance_logs(member,date,entry) values(?,?,?)', ('ycc00000050', '2026-11-18', '{}'))
    at(flow, hour=11)
    flow.tick(send=True)
    assert len(jobs(flow)) == 2
    with pytest.raises(sqlite3.IntegrityError):
        flow.state.enroll('ycc00000002', generate_password_hash('different'), 'study-B', 'ycc00000001')


def test_formal_commit_at_1030_stops_11_and_next_day_is_new(flow):
    bind(flow)
    at(flow)
    flow.tick(send=True)
    at(flow, hour=10, minute=30)
    with flow.state.connect() as db:
        db.execute('insert into acceptance_logs(member,date,entry) values(?,?,?)', ('ycc00000001', '2026-11-18', '{}'))
    at(flow, hour=11)
    flow.tick(send=True)
    assert len(jobs(flow)) == 1
    at(flow, day=19)
    flow.tick(send=True)
    assert len(jobs(flow)) == 2
    assert jobs(flow)[-1]['target_date'] == '2026-11-19'


def test_friendly_copy_keeps_scheduled_member_date_link_and_evening_greeting(flow):
    from urllib.parse import parse_qs, urlsplit
    bind(flow, 'ycc00000050')
    for hour in (9, 11, 21):
        at(flow, hour=hour)
        flow.tick(send=True)
    planned = jobs(flow)
    assert [job['slot'] for job in planned] == ['09:00', '11:00', '21:00']
    for job in planned:
        body = json.loads(job['payload'])['messages'][0]
        message = body['template']['text']
        assert message.startswith('早安～昨天睡得好嗎？' if job['slot'] == '09:00' else '小小提醒～')
        assert '研究帳號：ycc00000050' in message and '日誌日期：2026/11/18' in message
        assert len(message) <= 160 and body['altText'] == message
        query = parse_qs(urlsplit(body['template']['actions'][0]['uri']).query)
        assert query['member'] == ['ycc00000050'] and query['date'] == ['2026-11-18']
        assert query['invite'] == [f'{50:064x}']


def test_timeout_restart_fixed_retry_key_payload_concurrent_workers(flow):
    bind(flow)
    at(flow)
    flow.line.result = 'uncertain'
    flow.tick(send=True)
    original = jobs(flow)[0]
    assert original['status'] == 'uncertain'
    at(flow, minute=1)
    flow.line.result = 'accepted'
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: flow.tick(send=True), range(4)))
    current = jobs(flow)[0]
    assert current['status'] == 'accepted' and current['attempts'] == 2
    assert current['retry_key'] == original['retry_key'] and current['payload'] == original['payload']
    restarted = ReminderService(State(flow.state.path), flow.line, flow.diaries, flow.base_url, clock=flow.clock)
    restarted.tick(send=True)
    assert jobs(flow)[0]['attempts'] == 2


def test_crash_after_external_acceptance_reuses_durable_intent(flow):
    bind(flow)
    at(flow)
    accepted = set()
    original = flow.line.push
    def crash(payload, retry):
        accepted.add(retry)
        raise RuntimeError('simulated process death before DB commit')
    flow.line.push = crash
    with pytest.raises(RuntimeError):
        flow.tick(send=True)
    assert len(jobs(flow)) == 1 and jobs(flow)[0]['status'] == 'uncertain'
    assert jobs(flow)[0]['retry_key'] in accepted
    flow.line.push = original
    at(flow, minute=2)
    flow.tick(send=True)
    assert len(jobs(flow)) == 1 and jobs(flow)[0]['status'] == 'accepted'


@pytest.mark.parametrize('stop', ['unfollow', 'binding', 'account', 'ended', 'archived', 'invite'])
def test_stop_conditions(flow, stop):
    result = bind(flow)
    at(flow)
    if stop == 'unfollow':
        event(flow, 'unfollow')
    elif stop in ('binding', 'account'):
        with flow.state.connect() as db:
            db.execute('update ' + ('bindings' if stop == 'binding' else 'accounts') + ' set active=0')
    elif stop == 'ended':
        with flow.state.connect() as db:
            db.execute("update accounts set ends='2026-11-17'")
    else:
        flow.diaries.snapshot = lambda a, d: {'active': stop != 'archived', 'completed': False, 'invite': None if stop == 'invite' else '1' * 64}
    flow.tick(send=True)
    assert not jobs(flow)
    if stop == 'unfollow':
        at(flow, day=19)
        event(flow)
        again = flow.bind(flow.line.token, 'ycc00000001', 'SYNTHETIC_RANDOM_PASSWORD')
        assert again['bound_at'] == result['bound_at'] and again['first_reminder_at'] == result['first_reminder_at']
        flow.tick(send=True)
        assert len(jobs(flow)) == 1


def test_out_of_order_follow_does_not_unblock(flow):
    bind(flow)
    at(flow)
    event(flow, 'unfollow')
    event(flow, 'follow', stamp=1)
    flow.tick(send=True)
    assert not jobs(flow)


def test_study_start_and_no_catchup_grace_or_cross_day(flow):
    with flow.state.connect() as db:
        db.execute("update accounts set starts='2026-11-20' where account_hash=?", (digest('ycc00000001'),))
    assert bind(flow)['first_reminder_at'] == '2026-11-20T09:00:00+08:00'
    at(flow, day=20, minute=11)
    flow.tick(send=True)
    assert not jobs(flow)
    at(flow, day=20, hour=15, minute=5)
    flow.tick(send=True)
    assert len(jobs(flow)) == 1
    at(flow, day=21, hour=0)
    flow.tick(send=True)
    assert len(jobs(flow)) == 1


def test_actual_routes_cannot_gain_admin_from_line(flow, monkeypatch):
    from nsysu.store import Store
    monkeypatch.setattr('nsysu.store.settings', lambda: ('https://synthetic.invalid', 'sb_publishable_SYNTHETIC'))
    def invalid_user(self):
        raise ValueError("invalid synthetic token")
    monkeypatch.setattr(Store, "user", invalid_user)
    app = create_app()
    app.extensions['reminders'] = flow
    c = app.test_client()
    event(flow)
    r = c.post('/api/line/bind', json={'id_token': flow.line.token, 'account': 'ycc00000001', 'password': 'SYNTHETIC_RANDOM_PASSWORD'})
    assert r.status_code == 200
    assert 'access_token' not in r.json
    assert c.post('/api/participants', headers={'Authorization': 'Bearer ' + flow.line.token}, json={}).status_code in (401, 503)
    assert c.post('/api/line/bind', headers={'Origin': 'https://evil.invalid'}, json={}).status_code == 403


def test_schema_apply_rollback_and_schedule(tmp_path):
    state = State(tmp_path / 'db', initialize=True)
    State(state.path, initialize=True)
    from pathlib import Path
    with state.connect() as db:
        db.executescript((Path(__file__).resolve().parents[2] / 'backend/nsysu/sql/rollback_line_state.sql').read_text())
        assert not db.execute("select name from sqlite_master where name='bindings'").fetchall()
    assert [d.hour for d in Schedule().slots(datetime(2026, 11, 18).date())] == [9, 11, 13, 15, 17, 19, 21]


@pytest.mark.parametrize('code,headers,expected', [(200, {}, 'accepted'), (409, {'x-line-accepted-request-id': 'accepted'}, 'accepted'),
    (409, {}, 'failed'), (429, {}, 'failed'), (503, {}, 'retry'), (400, {}, 'failed')])
def test_line_response_classification(monkeypatch, code, headers, expected):
    import requests
    monkeypatch.setenv('LINE_CHANNEL_ACCESS_TOKEN', 'SYNTHETIC')
    monkeypatch.setattr(requests, 'post', lambda *a, **k: type('R', (), {'status_code': code, 'headers': headers})())
    assert LineAPI().push({'to': 'SYNTHETIC'}, str(uuid.uuid4()))[0] == expected


def test_line_server_verification_never_accepts_profile(monkeypatch):
    import requests
    monkeypatch.setenv('LINE_LOGIN_CHANNEL_ID', 'SYNTHETIC_CHANNEL')
    values = {'iss': 'https://access.line.me', 'aud': 'wrong-channel', 'sub': 'SYNTHETIC', 'exp': 9999999999}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: type('R', (), {'status_code': 200, 'json': lambda self: values})())
    with pytest.raises(FlowError):
        LineAPI().verify('SYNTHETIC_ID_TOKEN')
    with pytest.raises(FlowError):
        LineAPI().verify({'userId': 'SPOOFED'})


def test_slow_snapshot_cannot_send_after_grace(flow):
    bind(flow)
    at(flow, minute=9)
    original = flow.diaries.snapshot
    calls = [0]
    def slow(account, day):
        calls[0] += 1
        if calls[0] >= 3:
            at(flow, minute=11)
        return original(account, day)
    flow.diaries.snapshot = slow
    flow.tick(send=True)
    assert not [c for c in flow.line.calls if any(a.get('label') == '填寫睡眠日誌' for a in c['payload']['messages'][0].get('template', {}).get('actions', []))]
    assert jobs(flow)[0]['status'] == 'skipped'


def test_later_job_failure_does_not_rollback_earlier_accepted_result(flow):
    bind(flow)
    flow.line.identity = 'SYNTHETIC_LINE_B'
    bind(flow, 'ycc00000050')
    at(flow)
    original = flow.diaries.snapshot
    count = [0]
    def failure(account, day):
        if account['member'] == 'ycc00000050':
            count[0] += 1
            if count[0] >= 2:
                raise RuntimeError('synthetic database outage for second recipient')
        return original(account, day)
    flow.diaries.snapshot = failure
    with pytest.raises(RuntimeError):
        flow.tick(send=True)
    assert jobs(flow)[0]['status'] == 'accepted' and jobs(flow)[0]['attempts'] == 1


def test_crashing_dispatches_still_consume_three_attempt_limit(flow):
    bind(flow)
    at(flow)
    def crash(payload, retry):
        raise RuntimeError('synthetic process crash')
    flow.line.push = crash
    for minute in (0, 2, 4):
        at(flow, minute=minute)
        with pytest.raises(RuntimeError):
            flow.tick(send=True)
    at(flow, minute=6)
    flow.tick(send=True)
    assert jobs(flow)[0]['attempts'] == 3 and jobs(flow)[0]['status'] == 'uncertain_final'


def test_submission_race_cancels_before_dispatch(flow):
    bind(flow)
    at(flow)
    original = flow.diaries.snapshot
    calls = [0]
    def completed(account, day):
        calls[0] += 1
        value = original(account, day)
        if calls[0] >= 2:
            value['completed'] = True
        return value
    flow.diaries.snapshot = completed
    flow.tick(send=True)
    assert jobs(flow)[0]['status'] == 'cancelled'


def test_selected_official_mode_never_falls_back(monkeypatch):
    from nsysu.reminders import configured_service
    monkeypatch.setenv('RESEARCH_AUTH_MODE', 'doctercloud')
    with pytest.raises(RuntimeError, match='no local fallback'):
        configured_service()


def test_study_with_no_future_day_rejects_misleading_success(flow):
    with flow.state.connect() as db:
        db.execute("update accounts set ends='2026-11-17'")
    with pytest.raises(FlowError):
        bind(flow)


def test_midnight_follow_still_gets_its_welcome_within_grace(flow):
    flow.test_clock[0] = datetime(2026, 11, 17, 23, 59, 30, tzinfo=TZ)
    event(flow)
    at(flow, hour=0)
    flow.tick(send=True)
    assert jobs(flow, 'welcome')[0]['status'] == 'accepted'
    assert not jobs(flow)


def test_timeout_then_5xx_retains_unknown_outcome_after_grace(flow):
    bind(flow)
    at(flow)
    flow.line.result = 'uncertain'
    flow.tick(send=True)
    at(flow, minute=1)
    flow.line.result = 'retry'
    flow.tick(send=True)
    assert jobs(flow)[0]['uncertainty'] == 1
    at(flow, minute=11)
    flow.tick(send=True)
    assert jobs(flow)[0]['status'] == 'uncertain_final'


def test_prior_unknown_is_not_erased_by_permanent_failure(flow):
    bind(flow)
    at(flow)
    flow.line.result = 'uncertain'
    flow.tick(send=True)
    at(flow, minute=1)
    flow.line.result = 'failed'
    flow.tick(send=True)
    assert jobs(flow)[0]['status'] == 'uncertain_final' and jobs(flow)[0]['uncertainty'] == 1
