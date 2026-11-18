"""單一 Streamlit 入口、公開設定與嵌入資料的安全邊界。"""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from nsysu.cloud import diary_document, public_config
from nsysu.config import public_url
from nsysu.store import settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cloud_config(monkeypatch):
    monkeypatch.setattr(st, 'secrets', {})
    monkeypatch.setenv('SUPABASE_URL', 'https://ztsyxnrnemvcladbaaem.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_SYNTHETIC')
    monkeypatch.setenv('PUBLIC_APP_URL', 'https://research.example.org/')
    monkeypatch.setenv('SUPABASE_ADMIN_KEY', 'PRIVATE_MUST_NOT_REACH_BROWSER')
    return public_config('https://research.example.org/')


def test_document_preserves_latest_form_assets_and_cloud_deep_link(cloud_config):
    html = diary_document(cloud_config, {'member': 'ycc00000051'})
    assert 'window.NSYSU_EMBED=' in html
    assert 'member=ycc00000051' in html
    assert '關燈' in html and 'f-wore-watch' in html and 'f-drank-alcohol' in html
    assert '<script src="/web/' not in html
    assert '<link rel="stylesheet" href="/web/' not in html
    assert 'PRIVATE_MUST_NOT_REACH_BROWSER' not in html
    assert 'https://research.example.org/?view=dashboard' in html


def test_untrusted_link_cannot_inject_html(cloud_config):
    with pytest.raises(ValueError):
        diary_document(cloud_config, {'member': '</script><script>alert(1)</script>'})
    html = diary_document(cloud_config, {'view': '</script><script>alert(1)</script>'})
    assert 'alert(1)' not in html


def test_invitation_deep_link_is_validated_and_preserved(cloud_config):
    token = 'a' * 64
    html = diary_document(cloud_config, {'member': 'ycc00000051', 'invite': token})
    assert 'invite=' + token in html
    assert 'submit_invited_diary' in html
    assert 'name="referrer" content="no-referrer"' in html
    for query in ({'member': 'ycc00000051', 'invite': '</script>'}, {'invite': token}):
        with pytest.raises(ValueError):
            diary_document(cloud_config, query)


def test_cloud_home_preserves_only_the_non_secret_return_marker(cloud_config):
    html = diary_document(cloud_config, {'auth_return': '1', 'access_token': 'NEVER_IN_URL'})
    assert 'auth_return=1' in html
    assert 'NEVER_IN_URL' not in html
    html = diary_document(cloud_config, {'auth_return': '<script>bad</script>'})
    assert 'auth_return=' not in html


def test_streamlit_home_renders_without_running_flask_or_querying_research_data(cloud_config, monkeypatch):
    import requests
    monkeypatch.setattr(requests, 'request', lambda *a, **k: pytest.fail('首頁不應由伺服器查詢研究資料'))
    app = AppTest.from_file(str(ROOT / 'streamlit_app.py')).run()
    assert not app.exception
    assert len(app.get('iframe')) == 1
    assert '填寫睡眠日誌' in app.get('iframe')[0].proto.srcdoc


def test_cloud_dashboard_uses_one_docter_management_login_for_both_views(cloud_config):
    app = AppTest.from_file(str(ROOT / 'streamlit_app.py'))
    app.query_params['view'] = 'dashboard'
    app.run()
    assert not app.exception
    assert [field.label for field in app.text_input] == ['管理者帳號', '管理者密碼']
    next(r for r in app.radio if r.label == '我要查看').set_value('手錶平台').run()
    assert [field.label for field in app.text_input] == ['管理者帳號', '管理者密碼']
    assert all('127.0.0.1:8000' not in button.proto.url for button in app.get('link_button'))


def test_dashboard_home_link_uses_browser_handoff_without_credentials(cloud_config, monkeypatch):
    from nsysu import auth_bridge
    calls = []
    monkeypatch.setattr(auth_bridge, '_home_component', lambda **args: calls.append(args))
    app = AppTest.from_file(str(ROOT / 'streamlit_app.py'))
    app.query_params['view'] = 'dashboard'
    app.run()
    assert not app.exception
    assert calls == [{'diary_url': 'https://research.example.org/', 'key': 'research_home_link', 'default': None}]


def test_invalid_member_shows_error(cloud_config):
    app = AppTest.from_file(str(ROOT / 'streamlit_app.py'))
    app.query_params['member'] = '<invalid>'
    app.run()
    assert not app.exception
    assert len(app.error) == 1
    assert not app.get('iframe')


def test_secrets_take_priority_and_private_key_is_rejected(monkeypatch):
    monkeypatch.setattr(st, 'secrets', {'SUPABASE_URL': 'https://ztsyxnrnemvcladbaaem.supabase.co',
                                     'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_FROM_SECRETS'})
    assert settings()[1] == 'sb_publishable_FROM_SECRETS'
    monkeypatch.setattr(st, 'secrets', {'SUPABASE_PUBLISHABLE_KEY': 'sb_secret_FORBIDDEN'})
    with pytest.raises(ValueError):
        settings()


def test_public_url_removes_existing_query_and_rejects_credentials(monkeypatch):
    monkeypatch.setattr(st, 'secrets', {})
    monkeypatch.delenv('PUBLIC_APP_URL', raising=False)
    assert public_url('https://research.example.org/?view=dashboard&member=x#fragment') == 'https://research.example.org/'
    monkeypatch.setenv('PUBLIC_APP_URL', 'https://user:password@example.org/')
    with pytest.raises(ValueError):
        public_url()
