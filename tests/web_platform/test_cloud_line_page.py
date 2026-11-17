"""Cloud-only account link UI never claims success before LINE confirms."""
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setenv('NSYSU_LINE_FUNCTION_URL', 'https://cloud.example.org/functions/v1/nsysu-line')
    app = AppTest.from_file(str(ROOT / 'streamlit_app.py'))
    app.query_params['view'] = 'line'
    app.query_params['link_token'] = 'SYNTHETIC_LINK'
    return app


def submit(app):
    app.run()
    next(field for field in app.text_input if field.label == '研究帳號').set_value('ycc00000001')
    next(field for field in app.text_input if field.label == '研究密碼').set_value('SYNTHETIC_PASSWORD')
    next(button for button in app.button if button.label == '核對帳號').click().run()


def test_requires_line_entry_without_showing_admin_login(monkeypatch):
    monkeypatch.setattr(requests, 'post', lambda *a, **k: pytest.fail('No link token means no network call'))
    app = AppTest.from_file(str(ROOT / 'streamlit_app.py'))
    app.query_params['view'] = 'line'
    app.run()
    assert not app.exception and not app.text_input
    assert '官方 LINE' in app.info[0].value


def test_account_verification_only_offers_official_line_confirmation(page, monkeypatch):
    seen = []
    target = 'https://access.line.me/dialog/bot/accountLink?linkToken=SYNTHETIC_LINK&nonce=' + 'a' * 64
    class Reply:
        ok = True
        def json(self):
            return {'status': 'pending_line_confirmation', 'link_url': target}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: seen.append((a, k)) or Reply())
    submit(page)
    assert not page.exception and not page.success
    assert seen[0][0][0] == 'https://cloud.example.org/functions/v1/nsysu-line/prepare-link'
    assert seen[0][1]['json']['password'] == 'SYNTHETIC_PASSWORD'
    link = page.get('link_button')[0].proto.url
    assert link == target and 'SYNTHETIC_PASSWORD' not in link and 'ycc00000001' not in link
    assert 'LINE 完成最後確認' in page.info[0].value


@pytest.mark.parametrize('target', ['https://untrusted.invalid/bind', 'https://access.line.me.evil.invalid/dialog/bot/accountLink'])
def test_untrusted_redirect_is_rejected(page, monkeypatch, target):
    class Reply:
        ok = True
        def json(self):
            return {'status': 'pending_line_confirmation', 'link_url': target}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Reply())
    submit(page)
    assert not page.exception and page.error and not page.get('link_button')


def test_cloud_unavailable_never_falls_back_to_local_success(page, monkeypatch):
    def unavailable(*a, **k):
        raise requests.ConnectionError('SYNTHETIC_NETWORK')
    monkeypatch.setattr(requests, 'post', unavailable)
    submit(page)
    assert not page.exception and not page.success and page.error
    assert not page.get('link_button')
