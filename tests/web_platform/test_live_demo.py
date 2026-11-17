"""Synthetic tests of real-LINE demo boundaries; never sends to LINE."""
import base64
from datetime import datetime
import hashlib
import hmac
import json
import uuid

import pytest
from werkzeug.security import generate_password_hash

from nsysu.live_demo import DemoRuntime, controller_app, initialize, public_app, save_json
from nsysu.reminders import FlowError, LineAPI, TZ


ALLOWED = 'U' + 'a' * 32
OTHER = 'U' + 'b' * 32


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, 'secrets', {})
    initialize(tmp_path, [{'account': 'ycc00000001', 'password_hash': generate_password_hash('SYNTHETIC_PASSWORD'),
                          'study': 'LOCAL_LINE_DEMO', 'member': 'ycc00000001'}])
    save_json(tmp_path / 'config.json', {'allowed_line_user': ALLOWED, 'recipient_confirmed': True,
        'public_origin': 'https://demo.example.test', 'login_channel_id': '1234567890', 'liff_id': '1234567890-demo',
        'clock': '2026-11-17T23:59:00+08:00', 'demo_send_enabled': False})
    save_json(tmp_path / 'secrets.json', {'channel_secret': 'f' * 32, 'access_token': 'SYNTHETIC_TOKEN'})
    save_json(tmp_path / 'access.json', {'account': 'ycc00000001', 'password': 'SYNTHETIC_PASSWORD'})
    return DemoRuntime(tmp_path)


def signed(runtime, identity=ALLOWED):
    data = {'events': [{'webhookEventId': str(uuid.uuid4()), 'type': 'follow', 'timestamp': 1794931140000,
                        'source': {'type': 'user', 'userId': identity}}]}
    raw = json.dumps(data).encode()
    secret = json.loads((runtime.directory / 'secrets.json').read_text())['channel_secret']
    signature = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
    return raw, signature


def test_public_gateway_has_no_controller_credentials_or_admin(runtime):
    client = public_app(runtime).test_client()
    for path in ('/access', '/state', '/action', '/acceptance/access', '/acceptance/identity', '/api/participants',
                 '/api/import', '/web/research.html'):
        assert client.get(path).status_code == 404
    assert client.get('/').status_code == 403
    assert client.get('/line').status_code == 200
    cfg = client.get('/api/line/config').json
    assert cfg['live_demo'] is True and cfg['simulated'] is False
    assert 'access_token' not in json.dumps(cfg)


def test_public_forwarded_https_origin_and_untrusted_hosts(runtime):
    app = public_app(runtime)
    observed = []
    @app.after_request
    def capture_peer(response):
        from flask import request
        observed.append(request.remote_addr)
        return response
    client = app.test_client()
    assert client.get('/health', headers={'Host': 'evil.test'}).status_code == 403
    r = client.get('/api/line/config', headers={'Host': 'demo.example.test', 'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '1.2.3.4'})
    assert r.status_code == 200
    assert observed[-1] == '127.0.0.1'
    r = client.post('/api/line/bind', headers={'Host': 'demo.example.test', 'X-Forwarded-Proto': 'https', 'Origin': 'https://evil.test'}, json={})
    assert r.status_code == 403


def test_signed_other_followers_are_ignored_without_outbox(runtime):
    service = runtime.service()
    raw, signature = signed(runtime, OTHER)
    assert service.webhook(raw, signature)['processed'] == 0
    with runtime.state.connect() as db:
        assert db.execute('select count(*) from friends').fetchone()[0] == 0
        assert db.execute('select count(*) from outbox').fetchone()[0] == 0
    raw, signature = signed(runtime)
    assert service.webhook(raw, signature)['processed'] == 1
    with runtime.state.connect() as db:
        assert db.execute('select count(*) from outbox').fetchone()[0] == 1


def test_real_transport_rejects_nonapproved_recipient_before_network(monkeypatch):
    import requests
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: pytest.fail('No network allowed'))
    api = LineAPI('1234567890', 'SYNTHETIC', {ALLOWED})
    assert api.push({'to': OTHER}, str(uuid.uuid4())) == ('failed', None, 'demo_recipient_not_allowed')


def test_verified_token_must_belong_to_approved_identity(monkeypatch):
    import requests
    value = {'iss': 'https://access.line.me', 'aud': '1234567890', 'sub': OTHER,
             'exp': datetime.now(TZ).timestamp() + 600}
    class Response:
        status_code = 200
        def json(self):
            return value
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Response())
    with pytest.raises(FlowError) as error:
        LineAPI('1234567890', 'SYNTHETIC', {ALLOWED}).verify('SYNTHETIC_ID_TOKEN')
    assert error.value.status == 403


def test_worker_requires_separate_explicit_demo_send_flag(runtime):
    with pytest.raises(RuntimeError, match='disabled'):
        runtime.tick(send=True)


def test_controller_is_separate_and_rejects_public_host(runtime):
    c = controller_app(runtime).test_client()
    assert c.get('/access').json['password'] == 'SYNTHETIC_PASSWORD'
    assert c.get('/access', headers={'Host': 'demo.example.test'}).status_code == 403
    assert c.post('/action', headers={'Origin': 'https://evil.test'}, json={'action': 'clock'}).status_code == 403


def test_missing_secret_or_unconfirmed_recipient_never_returns_simulated_success(runtime):
    cfg = runtime.config()
    cfg['recipient_confirmed'] = False
    save_json(runtime.config_path, cfg)
    assert public_app(runtime).test_client().get('/api/line/config').status_code == 503


def test_scoped_diary_capability_does_not_grant_management(runtime, monkeypatch):
    monkeypatch.setattr(LineAPI, 'verify', lambda self, token: ALLOWED)
    service = runtime.service()
    raw, signature = signed(runtime)
    service.webhook(raw, signature)
    service.bind('SYNTHETIC_TOKEN', 'ycc00000001', 'SYNTHETIC_PASSWORD')
    with runtime.state.connect() as db:
        invite = db.execute('select invite from acceptance_invites').fetchone()[0]
    c = public_app(runtime).test_client()
    assert c.get('/?member=ycc00000001&invite=' + invite).status_code == 200
    assert c.get('/?member=ycc00000050&invite=' + invite).status_code == 403
    assert c.post('/demo/storage/rest/v1/rpc/get_fixed_diary_invitation', json={}).status_code == 403
    assert c.post('/demo/storage/rest/v1/rpc/submit_invited_diary', json={'p_invite': invite, 'p_entry': {'member_id': 'ycc00000050'}}).status_code == 403


def test_shared_binding_diary_submission_and_stop_flow(runtime, monkeypatch):
    calls = []
    monkeypatch.setattr(LineAPI, 'verify', lambda self, token: ALLOWED)
    monkeypatch.setattr(LineAPI, 'push', lambda self, payload, retry: calls.append((payload, retry)) or ('accepted', 'SYNTHETIC_ACCEPTED', None))
    cfg = runtime.config()
    cfg['demo_send_enabled'] = True
    save_json(runtime.config_path, cfg)
    public = public_app(runtime).test_client()
    local = controller_app(runtime).test_client()
    raw, signature = signed(runtime)
    assert public.post('/api/line/webhook', data=raw, headers={'X-Line-Signature': signature, 'Content-Type': 'application/json'}).status_code == 200
    runtime.tick(send=True)
    assert len(calls) == 1
    assert calls[0][0]['messages'][0]['template']['text'].startswith('【本機 Demo】')
    result = public.post('/api/line/bind', headers={'Host':'demo.example.test','X-Forwarded-Proto':'https','Origin':'https://demo.example.test'}, json={'id_token': 'SYNTHETIC', 'account': 'ycc00000001', 'password': 'SYNTHETIC_PASSWORD'})
    assert result.status_code == 200 and result.json['simulated'] is False
    assert local.post('/action', json={'action': 'clock', 'value': '2026-11-18T09:00'}).status_code == 200
    runtime.tick(send=True)
    assert len(calls) == 2 and calls[-1][0]['to'] == ALLOWED
    with runtime.state.connect() as db:
        invite = db.execute('select invite from acceptance_invites').fetchone()[0]
    entry = {'member_id': 'ycc00000001', 'name': 'SYNTHETIC_SUBJECT', 'date': '2026-11-18',
             'headphone_min': 0, 'bedtime_at': '2026-11-17T23:00:00+08:00',
             'final_wake_at': '2026-11-18T07:00:00+08:00', 'out_of_bed_at': '2026-11-18T07:15:00+08:00',
             'date_definition': 'wake_date', 'sleep_onset_min': 15, 'wakeup_count': 0,
             'fallback_sleep': '無', 'disturbance': '無', 'disturbance_scale': 0, 'sleep_quality': 4}
    request_id = str(uuid.uuid4())
    payload = {'p_invite': invite, 'p_entry': entry, 'p_request_id': request_id}
    for _ in range(2):
        assert public.post('/demo/storage/rest/v1/rpc/submit_invited_diary', json=payload).status_code == 200
    with runtime.state.connect() as db:
        assert db.execute('select count(*) from acceptance_logs').fetchone()[0] == 1
    local.post('/action', json={'action': 'clock', 'value': '2026-11-18T11:00'})
    runtime.tick(send=True)
    assert len(calls) == 2
