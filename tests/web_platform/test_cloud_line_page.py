"""Cloud-only account link UI never claims success before LINE confirms."""
from pathlib import Path
from html.parser import HTMLParser

import pytest
import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


def confirmation(app):
    links = []
    class Links(HTMLParser):
        def handle_starttag(self, tag, attributes):
            attributes = dict(attributes)
            if tag == 'a' and attributes.get('class') == 'line-confirm-button':
                links.append(attributes)
    for block in app.get('html'):
        Links().feed(block.proto.body)
    return links


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
    link = confirmation(page)[0]
    assert link['href'] == target and link['target'] == '_self'
    assert link['referrerpolicy'] == 'no-referrer'
    assert 'SYNTHETIC_PASSWORD' not in link['href'] and 'ycc00000001' not in link['href']
    assert not page.get('link_button')
    assert any('LINE 完成最後確認' in block.proto.body for block in page.get('html'))


@pytest.mark.parametrize('target', ['https://untrusted.invalid/bind', 'https://access.line.me.evil.invalid/dialog/bot/accountLink'])
def test_untrusted_redirect_is_rejected(page, monkeypatch, target):
    class Reply:
        ok = True
        def json(self):
            return {'status': 'pending_line_confirmation', 'link_url': target}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Reply())
    submit(page)
    assert not page.exception and page.error and not confirmation(page)


def test_cloud_unavailable_never_falls_back_to_local_success(page, monkeypatch):
    def unavailable(*a, **k):
        raise requests.ConnectionError('SYNTHETIC_NETWORK')
    monkeypatch.setattr(requests, 'post', unavailable)
    submit(page)
    assert not page.exception and not page.success and page.error
    assert not confirmation(page)


@pytest.mark.parametrize('failure', [False, True])
def test_wait_message_is_visible_before_request_and_clears_on_success_or_failure(page, monkeypatch, failure):
    from nsysu import cloud_line_page
    states, placeholders = [], []
    original_empty = cloud_line_page.st.empty
    class Waiting:
        def __init__(self):
            self.visible = False
            self.actual = original_empty()
        def html(self, message):
            self.visible = '正在核對研究帳號，請稍候' in message
            return self.actual.html(message)
        def empty(self):
            self.visible = False
            return self.actual.empty()
    def placeholder():
        value = Waiting()
        placeholders.append(value)
        return value
    monkeypatch.setattr(cloud_line_page.st, 'empty', placeholder)
    class Reply:
        ok = True
        def json(self):
            return {'status': 'pending_line_confirmation', 'link_url': 'https://access.line.me/dialog/bot/accountLink?linkToken=SYNTHETIC_LINK&nonce=' + 'b' * 64}
    def request(*args, **kwargs):
        states.append(any(slot.visible for slot in placeholders))
        if failure:
            raise requests.Timeout('SYNTHETIC_TIMEOUT')
        return Reply()
    monkeypatch.setattr(requests, 'post', request)
    submit(page)
    assert states == [True] and not any(slot.visible for slot in placeholders) and not page.exception
    assert bool(page.error) == failure


@pytest.mark.parametrize('query', [
    'linkToken=DIFFERENT_LINK&nonce=' + 'a' * 64,
    'linkToken=SYNTHETIC_LINK&nonce=bad',
    'linkToken=SYNTHETIC_LINK&nonce=' + 'a' * 64 + '&nonce=' + 'b' * 64,
    'linkToken=SYNTHETIC_LINK&nonce=' + 'a' * 64 + '&redirect_uri=https://untrusted.invalid',
])
def test_handoff_rejects_mismatched_or_malformed_confirmation(page, monkeypatch, query):
    class Reply:
        ok = True
        def json(self):
            return {'status': 'pending_line_confirmation', 'link_url': 'https://access.line.me/dialog/bot/accountLink?' + query}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Reply())
    submit(page)
    assert not page.exception and page.error and not confirmation(page)


def test_new_line_request_cannot_reuse_previous_confirmation(page, monkeypatch):
    class Reply:
        ok = True
        def json(self):
            return {'status': 'pending_line_confirmation', 'link_url': 'https://access.line.me/dialog/bot/accountLink?linkToken=SYNTHETIC_LINK&nonce=' + 'a' * 64}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Reply())
    submit(page)
    assert confirmation(page)
    page.query_params['link_token'] = 'SYNTHETIC_NEW_LINK'
    page.run()
    assert not confirmation(page)
