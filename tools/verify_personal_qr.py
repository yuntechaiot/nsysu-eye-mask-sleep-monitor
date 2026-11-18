"""Responsive personal-QR UI against an existing loopback preview; synthetic responses only."""
import json
from pathlib import Path
import sys

from playwright.sync_api import expect, sync_playwright

BASE = 'http://127.0.0.1:64660/'
OUT = Path(__file__).resolve().parents[1] / 'artifacts/personal-qr-ui'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(reduced_motion='reduce')

        def mock(route):
            data = route.request.post_data_json
            member = data.get('account')
            allowed = member in ['ycc00000001', 'ycc00000050'] and data.get('password') == 'SYNTHETIC_UI_PASSWORD'
            payload = ({'status': 'verified_research_account', 'member_id': member,
                        'diary_url': BASE + '?member=' + str(member) + '&invite=' + 'a' * 64}
                       if allowed else {'error': 'SYNTHETIC_CREDENTIAL_FAILURE'})
            route.fulfill(status=200 if allowed else 401, json=payload)

        context.route('**/api/participant/diary-access', mock)
        try:
            # Use the actual inline cloud document: config resolves without a network
            # round trip, so this catches feature/startup ordering races.
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
            from nsysu.cloud import diary_document
            document = diary_document({'supabase_url': 'https://synthetic.supabase.co',
                                       'publishable_key': 'sb_publishable_SYNTHETIC',
                                       'diary_url': BASE, 'dashboard_url': BASE + '?view=dashboard',
                                       'line': {'official_id': '@823bciot', 'join_url': 'https://line.me/R/ti/p/%40823bciot'}})
            context.route(BASE + 'acceptance/cloud-bootstrap', lambda route: route.fulfill(content_type='text/html', body=document))
            inline = context.new_page()
            inline.goto(BASE + 'acceptance/cloud-bootstrap')
            expect(inline.locator('#line-notice')).to_be_visible()
            expect(inline.locator('#loading-screen')).to_be_hidden()
            assert not inline.locator('#toast').evaluate("node=>node.classList.contains('error')")
            inline.close()
            for width in [375, 414, 768, 1024, 1440]:
                page = context.new_page()
                page.set_viewport_size({'width': width, 'height': 900})
                page.goto(BASE)
                page.get_by_role('button', name='產生日誌 QR Code', exact=True).click()
                page.locator('#self-qr-account').fill('ycc00000001')
                page.locator('#self-qr-password').fill('SYNTHETIC_UI_PASSWORD')
                page.locator('#self-qr-submit').click()
                expect(page.locator('#self-qr-result')).to_be_visible()
                expect(page.locator('#self-qr-link')).to_have_value(BASE + '?member=ycc00000001&invite=' + 'a' * 64)
                assert page.locator('#self-qr-image canvas').count() == 1
                assert not page.locator('#auth-dialog').is_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert page.locator('#self-qr-dialog').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
                assert page.locator('#self-qr-password').input_value() == ''
                page.screenshot(path=str(OUT / ('personal-qr-' + str(width) + '.png')), full_page=True)
                page.get_by_role('button', name='關閉日誌 QR Code', exact=True).click()
                assert page.locator('#self-qr-link').input_value() == ''
                checks.append({'width': width, 'own_qr': True, 'no_admin_login': True, 'no_overflow': True})
                page.close()
        finally:
            context.close()
            browser.close()
    (OUT / 'checks.json').write_text(json.dumps({'synthetic_response': True, 'cloud_inline_bootstrap': True, 'checks': checks}, indent=2), encoding='utf-8')
    print(json.dumps({'responsive_checks': len(checks), 'cloud_inline_bootstrap': True, 'passed': True, 'synthetic_response': True}))


if __name__ == '__main__':
    main()
