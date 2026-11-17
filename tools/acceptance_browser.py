"""Automated Edge browser acceptance against isolated instances of real code."""
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from flask import Response
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from tools.preview_acceptance import build
from nsysu.server import RedactedRequestHandler

OUT = ROOT / 'artifacts/acceptance'
BASELINE = '7e2deb8897a29e3cdd677b19ba41b88dbe704022'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix='nsysu-acceptance-') as temporary:
        directory = Path(temporary)
        app = build(64665, 64666, directory)
        cache = {}
        def original(path):
            if path not in cache:
                cache[path] = subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT)
            return cache[path]

        @app.get('/acceptance/before')
        def before():
            return Response(original('frontend/source/睡眠日誌表單.html').replace(b'/web/', b'/acceptance/baseline/web/'), mimetype='text/html')

        @app.get('/acceptance/baseline/web/<name>')
        def before_asset(name):
            return Response(original('frontend/web/' + name), mimetype='text/css' if name.endswith('.css') else 'application/javascript')

        server = make_server('127.0.0.1', 64665, app, threaded=True, request_handler=RedactedRequestHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        baseline = directory / 'baseline_flow.py'
        baseline.write_bytes(original('backend/nsysu/dashboard_flow.py'))
        entry = directory / 'baseline_entry.py'
        entry.write_text("import sys,importlib.util\nsys.path.insert(0," + repr(str(ROOT / 'backend')) + ")\ns=importlib.util.spec_from_file_location('nsysu.baseline_flow'," + repr(str(baseline)) + ")\nm=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\nm.main()\n", encoding='utf-8')
        env = dict(os.environ, NSYSU_ACCEPTANCE_MODE='1', NSYSU_ACCEPTANCE_API='http://127.0.0.1:64665/acceptance/supabase',
                   VTCA_DIARY_URL='http://127.0.0.1:64665/', PYTHONIOENCODING='utf-8')
        children = []
        log = (OUT / 'browser-server.log').open('w', encoding='utf-8')
        for port, script in [(64666, ROOT / 'tools/acceptance_dashboard.py'), (64667, entry)]:
            children.append(subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(script), '--server.address', '127.0.0.1',
                '--server.port', str(port), '--server.headless', 'true', '--browser.gatherUsageStats', 'false'], env=env, cwd=ROOT,
                stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        try:
            import requests
            for port in (64666, 64667):
                for _ in range(120):
                    try:
                        if requests.get(f'http://127.0.0.1:{port}/_stcore/health', timeout=.5).status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(.25)
                else:
                    raise RuntimeError('Local Streamlit test server did not start')
            access = json.loads((directory / 'access.json').read_text())
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge')
                context = browser.new_context(reduced_motion='reduce', viewport={'width': 1440, 'height': 1000})
                outside, errors = [], []
                def guard(route):
                    if urlsplit(route.request.url).hostname not in ('127.0.0.1', 'localhost'):
                        outside.append(route.request.url.split('?')[0]);route.abort()
                    else:
                        route.continue_()
                context.route('**/*', guard)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto('http://127.0.0.1:64665/acceptance/before')
                page.locator('#loading-screen').wait_for(state='hidden')
                page.locator('#admin-login-button').click()
                page.screenshot(path=OUT / 'before-home-login-1440.png')
                baseline_page = context.new_page()
                baseline_page.goto('http://127.0.0.1:64667/')
                baseline_page.get_by_text('登入日誌與研究資料', exact=True).wait_for()
                baseline_page.screenshot(path=OUT / 'before-dashboard-login-1440.png')
                baseline_page.close()

                page.goto('http://127.0.0.1:64665/?view=workspace')
                page.locator('#auth-dialog').wait_for(state='visible')
                expect(page.get_by_label('管理者帳號', exact=True)).to_be_visible()
                expect(page.get_by_label('管理者密碼', exact=True)).to_be_visible()
                page.screenshot(path=OUT / 'after-admin-login-1440.png')
                page.locator('#auth-email').fill(access['admin_account'])
                page.locator('#auth-password').fill(access['admin_password'])
                page.locator('#auth-submit').click()
                page.locator('#workspace-page.active').wait_for()
                checks.append('Management login uses required labels and enters workspace')
                visible=page.locator('body').inner_text()
                assert not any(word in visible for word in ('LINE 已綁定','LINE 未綁定','LINE User ID','Webhook','LIFF','Channel Secret','提醒時間表','發送紀錄'))
                checks.append('Ordinary workspace exposes only the official LINE join notice')
                page.screenshot(path=OUT / 'workspace-1440.png')
                page.get_by_role('button', name='產生受試者日誌 QR Code', exact=True).click()
                page.locator('#member-entry').click()
                page.get_by_role('option').filter(has_text='ycc00000001').click()
                expect(page.locator('#participant-link')).not_to_have_value('')
                first = page.locator('#participant-link').input_value()
                page.locator('#member-entry').click()
                page.locator('#member-entry').fill('50')
                page.locator('#member-entry').press('ArrowDown')
                page.locator('#member-entry').press('Enter')
                expect(page.locator('#participant-link')).to_have_value(__import__('re').compile('member=ycc00000050'))
                second = page.locator('#participant-link').input_value()
                assert first != second
                page.reload()
                expect(page.locator('#participant-link')).to_have_value(second)
                page.screenshot(path=OUT / 'qr-1440.png')
                checks.append('Distinct QR capabilities retain the selected participant after refresh')
                page.goto('http://127.0.0.1:64665/?view=workspace')
                with page.expect_popup() as popup:
                    page.get_by_role('button', name='查看研究資料', exact=True).click()
                dashboard = popup.value
                dashboard.get_by_text('管理者已登入', exact=True).wait_for(timeout=25000)
                assert dashboard.get_by_label('管理者帳號', exact=True).count() == 0
                dashboard.get_by_role('button', name='查看資料', exact=True).click()
                dashboard.get_by_role('tab', name='健康總覽', exact=True).wait_for()
                checks.append('Real Streamlit handoff reuses management session and renders eight research tabs')
                assert dashboard.get_by_role('tab').count() == 8
                dashboard.screenshot(path=OUT / 'after-dashboard-no-second-login-1440.png', full_page=True)
                dashboard.get_by_text('重新連接 DocterCloud', exact=True).click()
                dashboard.get_by_label('平台帳號', exact=True).fill('SYNTHETIC_PLATFORM')
                dashboard.get_by_label('平台密碼', exact=True).fill('SYNTHETIC_PASSWORD')
                dashboard.get_by_role('button', name='連接 DocterCloud', exact=True).click()
                dashboard.get_by_text('登入未成功，請確認帳密、管理權限與連線。', exact=True).wait_for()
                checks.append('Acceptance DocterCloud authorization is explicitly disabled and fails closed')
                dashboard.close()
                page.bring_to_front()
                for width in (320, 390, 430, 1440):
                    page.locator('#workspace-page.active').wait_for()
                    page.set_viewport_size({'width': width, 'height': 900})
                    page.screenshot(path=OUT / f'workspace-{width}.png', full_page=True, animations='disabled')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.get_by_role('button', name='產生受試者日誌 QR Code', exact=True).click()
                    expect(page.locator('#participant-link')).to_have_value(second)
                    page.screenshot(path=OUT / f'qr-{width}.png', full_page=True, animations='disabled')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.goto('http://127.0.0.1:64665/?view=workspace')
                checks.append('Workspace and QR layouts have no overflow at 320/390/430/1440px')

                api = context.request
                def action(name, **values):
                    result = api.post('http://127.0.0.1:64665/acceptance/action', data={'action': name, **values})
                    assert result.ok
                    return result.json()
                action('follow', event_id='browser-follow')
                action('follow', event_id='browser-follow')
                action('tick')
                subject = browser.new_context(reduced_motion='reduce', viewport={'width': 390, 'height': 844})
                subject.route('**/*', guard)
                binding = subject.new_page()
                binding.goto('http://127.0.0.1:64665/line')
                expect(binding.locator('#bind-button')).to_be_enabled()
                for width in (320, 390, 430, 1440):
                    binding.set_viewport_size({'width': width, 'height': 900})
                    binding.screenshot(path=OUT / f'binding-{width}.png', full_page=True, animations='disabled')
                    assert binding.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                binding.set_viewport_size({'width': 390, 'height': 844})
                binding.locator('#account').fill(access['research_account'])
                binding.locator('#password').fill(access['research_password'])
                binding.locator('#password').press('Enter')
                binding.locator('#success').wait_for(state='visible')
                expect(binding.locator('#first-reminder')).to_contain_text('2026/11/18')
                binding.screenshot(path=OUT / 'binding-success-390.png', full_page=True, animations='disabled')
                checks.append('Signed follow deduplicates; dedicated binding confirms the actual next-day first reminder')
                action('clock', value='2026-11-18T09:00')
                action('tick')
                state = api.get('http://127.0.0.1:64665/acceptance/state').json()
                message = [j for j in state['jobs'] if j['kind'] == 'diary'][-1]
                diary_url = json.loads(message['payload'])['messages'][0]['template']['actions'][0]['uri']
                diary = subject.new_page()
                diary.goto(diary_url)
                expect(diary.locator('#member-page.active')).to_be_visible()
                assert diary.locator('#f-date').input_value() == '2026-11-18'
                action('clock', value='2026-11-18T11:00')
                action('tick')
                assert len([j for j in api.get('http://127.0.0.1:64665/acceptance/state').json()['jobs'] if j['kind'] == 'diary']) == 2
                action('clock', value='2026-11-18T11:30')
                diary.locator('#f-name').fill('合成受試者')
                diary.locator('#f-headphone').fill('0')
                diary.locator('#next-step').click()
                diary.locator('#f-sleep-onset').fill('15')
                diary.locator('#next-step').click()
                diary.locator('#f-wakeups').fill('0')
                diary.locator('#f-wakeups').press('Tab')
                diary.locator('#cg-disturbance input[value="無"]').check()
                diary.locator('#scale-quality [data-v="4"]').click()
                diary.locator('#next-step').click()
                diary.screenshot(path=OUT / 'diary-review-390.png', full_page=True, animations='disabled')
                diary.locator('#submit-btn').click()
                diary.locator('#success-page.active').wait_for()
                diary.screenshot(path=OUT / 'diary-submitted-390.png', full_page=True, animations='disabled')
                action('clock', value='2026-11-18T13:00')
                action('tick')
                assert len([j for j in api.get('http://127.0.0.1:64665/acceptance/state').json()['jobs'] if j['kind'] == 'diary']) == 2
                action('clock', value='2026-11-19T09:00')
                action('tick')
                assert len([j for j in api.get('http://127.0.0.1:64665/acceptance/state').json()['jobs'] if j['kind'] == 'diary']) == 3
                checks.append('Opened diary still reminds; original four-step final submission stops same-day work; next day targets new diary')
                assert not errors, errors
                # Streamlit may request optional CDN fonts; no official data APIs.
                assert not any('docter' in url.lower() or 'api.line.me' in url for url in outside), outside
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.goto('http://127.0.0.1:64665/?view=qr&member=ycc00000050')
                expect(page.locator('#participant-link')).to_have_value(second)
                action('revoke_session')
                page.reload()
                page.locator('#auth-dialog').wait_for(state='visible')
                page.locator('#auth-email').fill(access['admin_account'])
                page.locator('#auth-password').fill(access['admin_password'])
                page.locator('#auth-submit').click()
                expect(page.locator('#participant-link')).to_have_value(second)
                checks.append('Revoked management session requires login and returns to the selected QR')
                page.goto('http://127.0.0.1:64665/?view=workspace')
                with page.expect_popup() as popup:
                    page.get_by_role('button', name='查看研究資料', exact=True).click()
                dashboard = popup.value
                dashboard.get_by_text('管理者已登入', exact=True).wait_for(timeout=25000)
                dashboard.get_by_role('button', name='登出目前資料來源').click()
                dashboard.get_by_label('管理者帳號', exact=True).wait_for()
                expect(page.locator('#account-chip')).to_have_text('')
                expect(page.locator('#participant-link')).to_have_value('')
                checks.append('Dashboard logout clears website identity and cached QR capability')
                checks.append('No page JavaScript errors or real LINE/DocterCloud calls')
                browser.close()
        finally:
            for child in children:
                child.terminate()
                child.wait(timeout=10)
            server.shutdown()
            log.close()
    (OUT / 'browser-results.json').write_text(json.dumps({'checks': checks, 'passed': len(checks), 'real_line_messages': 0, 'real_device': False}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': len(checks), 'screenshots': len(list(OUT.glob('*.png'))), 'real_line_messages': 0}))


if __name__ == '__main__':
    main()
