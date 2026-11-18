import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from nsysu import dashboard_flow, staff_auth
from nsysu.cloud import public_config
from nsysu.reminder_routes import public_line_info
from nsysu.store import Store, StoreError


def test_public_cloud_line_notice_has_verified_default_even_without_secret(monkeypatch):
    monkeypatch.setattr(st, 'secrets', {})
    monkeypatch.delenv('LINE_OFFICIAL_ACCOUNT_ID', raising=False)
    assert public_line_info() == {'official_id': '@823bciot', 'join_url': 'https://line.me/R/ti/p/%40823bciot'}
    assert public_config('https://research.example.org/')['line']['official_id'] == '@823bciot'


@pytest.mark.parametrize('value', ['', '@823bciot'])
def test_empty_cloud_line_setting_uses_verified_account(monkeypatch, value):
    monkeypatch.setattr(st, 'secrets', {'LINE_OFFICIAL_ACCOUNT_ID': value})
    assert public_line_info()['official_id'] == '@823bciot'


def test_bad_line_setting_is_not_rendered_as_a_link(monkeypatch):
    monkeypatch.setattr(st, 'secrets', {'LINE_OFFICIAL_ACCOUNT_ID': '<script>'})
    assert public_line_info() == {}


def test_staff_login_password_only_goes_to_the_project_broker(monkeypatch):
    calls = []
    session = {'access_token': 'SYNTHETIC_AUTH', 'refresh_token': 'SYNTHETIC_REFRESH', 'user': {'app_metadata': {'diary_staff': True}}}
    class Response:
        ok = True
        def json(self):
            return session
    monkeypatch.setattr(staff_auth.requests, 'post', lambda url, **options: calls.append((url, options)) or Response())
    assert staff_auth.staff_login('NSYSU_TEST', 'SYNTHETIC_DoCtEr') == session
    assert calls[0][0].endswith('/functions/v1/nsysu-staff-auth/login')
    assert calls[0][1]['json'] == {'account': 'NSYSU_TEST', 'password': 'SYNTHETIC_DoCtEr'}
    assert calls[0][1]['allow_redirects'] is False
    assert 'grant_type=password' not in calls[0][0]


def test_wrong_broker_host_is_rejected_before_password_submission(monkeypatch):
    monkeypatch.setattr(st, 'secrets', {'NSYSU_STAFF_AUTH_URL': 'https://foreign.invalid/'})
    monkeypatch.setattr(staff_auth.requests, 'post', lambda *a, **k: pytest.fail('Password must not leave the project'))
    with pytest.raises(ValueError):
        staff_auth.endpoint()


def test_platform_session_is_recovered_server_side_after_authorization(monkeypatch):
    state = {'supabase_session': {'access_token': 'SYNTHETIC', 'expires_at': 2000000000}}
    monkeypatch.setattr(dashboard_flow.st, 'session_state', state)
    monkeypatch.setattr(Store, 'user', lambda self: {'id': 'SYNTHETIC'})
    monkeypatch.setattr(Store, 'request', lambda *a, **k: True)
    calls = []
    monkeypatch.setattr(dashboard_flow, 'platform_session', lambda token: calls.append(token) or 'SYNTHETIC_DOCTER_TOKEN')
    assert dashboard_flow.research_store()
    assert calls == ['SYNTHETIC']
    assert state['platform_token'] == 'SYNTHETIC_DOCTER_TOKEN'
    assert 'platform_token' not in state['supabase_session']


def test_revoked_role_never_requests_a_docter_session(monkeypatch):
    monkeypatch.setattr(dashboard_flow.st, 'session_state', {'supabase_session': {'access_token': 'SYNTHETIC', 'expires_at': 2000000000}})
    monkeypatch.setattr(Store, 'user', lambda self: {})
    monkeypatch.setattr(Store, 'request', lambda *a, **k: False)
    monkeypatch.setattr(dashboard_flow, 'platform_session', lambda *a: pytest.fail('Not authorized'))
    with pytest.raises(PermissionError):
        dashboard_flow.research_store()


def test_legacy_session_without_docter_proof_requires_the_single_login(monkeypatch):
    state = {'supabase_session': {'access_token': 'SYNTHETIC', 'expires_at': 2000000000}}
    monkeypatch.setattr(dashboard_flow.st, 'session_state', state)
    monkeypatch.setattr(Store, 'user', lambda self: {})
    monkeypatch.setattr(Store, 'request', lambda *a, **k: True)
    def missing(token):
        raise StoreError(401)
    monkeypatch.setattr(dashboard_flow, 'platform_session', missing)
    with pytest.raises(PermissionError):
        dashboard_flow.research_store()
    assert state['_auth_clear'] and 'supabase_session' not in state


def test_signed_in_dashboard_has_no_second_platform_login(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Store, 'user', lambda self: {'id': 'SYNTHETIC'})
    monkeypatch.setattr(Store, 'request', lambda *a, **k: True)
    monkeypatch.setattr(Store, 'rows', lambda self, table, **k: [{'member_id': 'ycc00000001'}] if table == 'research_participants' else [])
    monkeypatch.setattr(dashboard_flow, 'platform_session', lambda token: 'SYNTHETIC_DOCTER')
    monkeypatch.setattr(dashboard_flow.Platform, 'members', lambda *a: [])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / 'streamlit_app.py'))
    app.query_params['view'] = 'dashboard'
    app.session_state['supabase_session'] = {'access_token': 'SYNTHETIC', 'expires_at': 2000000000}
    app.run()
    assert not app.exception
    assert not app.text_input
    assert not any('重新連接' in item.label for item in app.expander)
    assert 'platform_token' in app.session_state


def test_local_login_proxy_preserves_credential_failure_status(monkeypatch):
    from nsysu import server
    def denied(account, password):
        raise StoreError(401)
    monkeypatch.setattr(server, 'staff_login', denied)
    response = server.create_app().test_client().post('/api/staff/login', json={'account': 'NSYSU_TEST', 'password': 'SYNTHETIC_ONLY'})
    assert response.status_code == 401
    assert 'SYNTHETIC_ONLY' not in response.get_data(as_text=True)


def test_local_personal_qr_proxy_rejects_invalid_accounts_before_network(monkeypatch):
    from nsysu.server import create_app
    from nsysu import participant_entry
    monkeypatch.setattr(participant_entry, 'diary_access', lambda *a: pytest.fail('Invalid account must not be forwarded'))
    client = create_app().test_client()
    for account in ['yc00000001', 'ycc00000000', 'ycc00000051']:
        assert client.post('/api/participant/diary-access', json={'account': account, 'password': 'SYNTHETIC_ONLY'}).status_code == 400


def test_local_personal_qr_proxy_preserves_revoked_entry_error(monkeypatch):
    from nsysu.server import create_app
    from nsysu import participant_entry
    def revoked(*args):
        raise StoreError(403)
    monkeypatch.setattr(participant_entry, 'diary_access', revoked)
    assert create_app().test_client().post('/api/participant/diary-access', json={'account': 'ycc00000001', 'password': 'SYNTHETIC_ONLY'}).status_code == 403
