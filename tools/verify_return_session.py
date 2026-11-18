"""Browser regression against an already-running isolated preview only.

Does not start a backend, change clocks/diaries, or contact cloud services.
"""
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
import requests

ROOT = Path(__file__).resolve().parents[1]
HOME = 'http://127.0.0.1:64660/'
DASHBOARD = 'http://127.0.0.1:64661/'
OUT = ROOT / 'artifacts/return-session'


def home_frame(page):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        for frame in page.frames:
            if 'nsysu_auth_return' in frame.url and frame.get_by_role('link', name='← 回到日誌首頁', exact=True).count():
                return frame
        page.wait_for_timeout(100)
    raise AssertionError('Research return link is not ready')


def return_home(context, dashboard):
    frame = home_frame(dashboard)
    with context.expect_page() as popup:
        frame.get_by_role('link', name='← 回到日誌首頁', exact=True).click()
    page = popup.value
    page.locator('#loading-screen').wait_for(state='hidden')
    try:
        expect(page.locator('#account-chip')).to_have_text('管理者已登入')
    except AssertionError:
        print(json.dumps({'home': page.evaluate("({url:location.href,opener:!!opener,sessionPresent:!!sessionStorage.getItem('vtca-session'),messages:window.returnMessages})"),
                          'research': frame.evaluate("({sessionPresent:!!sessionStorage.getItem('vtca-session'),opened:opened.size,clients:clients.size})")}, ensure_ascii=True))
        raise
    assert not page.locator('#auth-dialog').is_visible()
    return page


def main():
    assert requests.get(HOME + 'acceptance/state', timeout=5).json()['simulated'] is True
    access = json.loads((ROOT / 'private/acceptance/access.json').read_text(encoding='utf-8'))
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(reduced_motion='reduce', viewport={'width': 1440, 'height': 1000})
        context.add_init_script("window.returnMessages=[];addEventListener('message',event=>{if(event.data?.type?.startsWith('nsysu:'))window.returnMessages.push({type:event.data.type,origin:event.origin,fromOpener:event.source===opener});});")
        context.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname in ('127.0.0.1', 'localhost') else route.abort())
        try:
            page = context.new_page()
            page.goto(HOME + '?view=workspace')
            page.locator('#auth-email').fill(access['admin_account'])
            page.locator('#auth-password').fill(access['admin_password'])
            page.locator('#auth-submit').click()
            page.locator('#workspace-page.active').wait_for()
            with context.expect_page() as popup:
                page.get_by_role('button', name='查看研究資料', exact=True).click()
            dashboard = popup.value
            dashboard.get_by_text('管理者已登入', exact=True).wait_for(timeout=25000)
            returned = return_home(context, dashboard)
            returned.reload()
            expect(returned.locator('#account-chip')).to_have_text('管理者已登入')
            returned.goto(HOME + '?view=workspace')
            returned.locator('#workspace-page.active').wait_for()
            checks.append('Home -> research -> home -> refresh preserves an authorized login')

            old = returned.evaluate('session.access_token')
            returned.evaluate('async()=>{session.expires_at=0;await authHeaders();}')
            renewed = returned.evaluate('session.access_token')
            assert renewed != old
            dashboard.wait_for_function("token=>JSON.parse(sessionStorage.getItem('vtca-session')||'null')?.access_token===token", arg=renewed)
            dashboard.get_by_role('combobox', name='選擇受試者', exact=True).click()
            dashboard.get_by_role('option').filter(has_text='ycc00000001').click()
            dashboard.get_by_role('button', name='查看資料', exact=True).click()
            dashboard.get_by_role('tab', name='健康總覽', exact=True).wait_for()
            returned_again = return_home(context, dashboard)
            assert returned_again.evaluate('session.access_token') == renewed
            checks.append('Automatic token refresh reaches research and a second return uses the latest token')
            returned_again.screenshot(path=str(OUT / 'home-still-signed-in.png'), full_page=True)

            returned_again.locator('#signout-btn').click()
            dashboard.get_by_label('管理者帳號', exact=True).wait_for()
            expect(page.locator('#account-chip')).to_have_text('')
            checks.append('Explicit logout still clears all linked research/home views')

            direct = context.new_page()
            direct.goto(DASHBOARD)
            direct.get_by_label('管理者帳號', exact=True).fill(access['admin_account'])
            direct.get_by_label('管理者密碼', exact=True).fill(access['admin_password'])
            direct.get_by_role('button', name='登入管理工作區', exact=True).click()
            direct.get_by_text('管理者已登入', exact=True).wait_for()
            returned_direct = return_home(context, direct)
            returned_direct.goto(HOME + '?view=workspace')
            returned_direct.locator('#workspace-page.active').wait_for()
            checks.append('Direct research login can return to home without an original diary tab')
        finally:
            context.close()
            browser.close()
    (OUT / 'checks.json').write_text(json.dumps({'passed': checks}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed_count': len(checks), 'checks': checks}))


if __name__ == '__main__':
    main()
