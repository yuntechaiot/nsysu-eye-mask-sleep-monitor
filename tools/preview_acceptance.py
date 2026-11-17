"""Isolated acceptance of the SAME website, binding service and worker.

No production credentials are loaded or copied; loopback only. The optional
official ID is public information verified by a read-only bot-info request.
"""
import argparse
import base64
from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

from flask import jsonify, request, send_from_directory
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from nsysu.acceptance_adapter import RecordingLine, SyntheticDiary, attach
from nsysu.reminders import ReminderService, State, TZ
from nsysu.server import RedactedRequestHandler, create_app


def build(port=64660, dashboard_port=64661, directory=None):
    directory = Path(directory or ROOT / 'private/acceptance')
    directory.mkdir(parents=True, exist_ok=True)
    base = f'http://127.0.0.1:{port}/'
    access_file = directory / 'access.json'
    state = State(directory / 'state.sqlite3', initialize=True)
    diary = SyntheticDiary(state)
    if not access_file.exists():
        password = secrets.token_urlsafe(12)
        data = {'admin_account': 'ACCEPTANCE_ADMIN', 'admin_password': secrets.token_urlsafe(12),
                'research_account': 'ycc00000001', 'research_password': password,
                'boundary_account': 'ycc00000050', 'boundary_password': password,
                'dashboard_url': f'http://127.0.0.1:{dashboard_port}/', 'line': {}}
        official = ROOT / 'private/official-account.json'
        if official.exists():
            from urllib.parse import quote
            account = json.loads(official.read_text())['official_id']
            data['line'] = {'official_id': account, 'join_url': 'https://line.me/R/ti/p/' + quote(account, safe='')}
        access_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
        for number in (1, 50):
            state.enroll(f'ycc{number:08}', generate_password_hash(password), 'SYNTHETIC_STUDY', f'ycc{number:08}')
            with state.connect() as db:
                db.execute('insert into acceptance_invites values(?,?)', (f'ycc{number:08}', secrets.token_hex(32)))
        with state.connect() as db:
            db.execute('insert into acceptance_clock values(?)', ('2026-11-17T23:59:00+08:00',))
    # Ports are local runtime configuration, not credentials.
    access = json.loads(access_file.read_text())
    access['dashboard_url'] = f'http://127.0.0.1:{dashboard_port}/'
    access_file.write_text(json.dumps(access, indent=2), encoding='utf-8')

    def now():
        with state.connect() as db:
            value = db.execute('select value from acceptance_clock').fetchone()[0]
        return datetime.fromisoformat(value)

    service = ReminderService(state, RecordingLine(), diary, base, 'SYNTHETIC_LIFF', 'SYNTHETIC_SECRET', clock=now)
    app = create_app()
    attach(app, service, access_file)

    @app.get('/acceptance')
    def controller():
        return send_from_directory(ROOT / 'frontend/acceptance', 'index.html')

    @app.get('/acceptance/access')
    def test_access():
        return jsonify(access)

    @app.get('/acceptance/state')
    def test_state():
        with state.connect() as db:
            jobs = [dict(r) for r in db.execute('select kind,target_date,slot,status,attempts,uncertainty,payload from outbox order by due_at')]
            bindings = [dict(r) for r in db.execute('select bound_at,reminder_start,active from bindings')]
            logs = [dict(r) for r in db.execute('select member,date from acceptance_logs')]
        return jsonify(simulated=True, clock=now().isoformat(), jobs=jobs, bindings=bindings, submitted=logs)

    @app.post('/acceptance/action')
    def action():
        data = request.get_json(silent=True) or {}
        operation = data.get('action')
        if operation in ('follow', 'unfollow', 'command'):
            event = {'webhookEventId': data.get('event_id') or str(uuid.uuid4()), 'type': 'message' if operation == 'command' else operation,
                     'timestamp': int(now().timestamp() * 1000), 'source': {'type': 'user', 'userId': service.line.identity}}
            if operation == 'command':
                event['message'] = {'type': 'text', 'text': '開始綁定'}
            raw = json.dumps({'events': [event]}).encode()
            signature = base64.b64encode(hmac.new(service.secret.encode(), raw, hashlib.sha256).digest()).decode()
            result = service.webhook(raw, signature)
        elif operation == 'clock':
            try:
                value = datetime.fromisoformat(data.get('value', '')).replace(tzinfo=TZ).isoformat()
            except ValueError:
                return jsonify(error='Invalid clock'), 400
            with state.connect() as db:
                db.execute('update acceptance_clock set value=?', (value,))
            result = {'clock': value}
        elif operation == 'tick':
            result = {'jobs': service.tick(send=True)}
        elif operation == 'revoke_session':
            with state.connect() as db:
                db.execute('update acceptance_sessions set active=0')
            result = {'revoked': True}
        else:
            return jsonify(error='Unknown test action'), 400
        return jsonify(simulated=True, result=result)

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=64660)
    parser.add_argument('--dashboard-port', type=int, default=64661)
    parser.add_argument('--no-dashboard', action='store_true')
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    from run_nsysu import check_port
    check_port('127.0.0.1', args.port, '驗收網站')
    if not args.no_dashboard:
        check_port('127.0.0.1', args.dashboard_port, '驗收研究資料')
    # This factory never constructs the production LINE/DocterCloud adapters.
    app = build(args.port, args.dashboard_port, args.directory)
    child = None
    if not args.no_dashboard:
        env = dict(os.environ, NSYSU_ACCEPTANCE_MODE='1', NSYSU_ACCEPTANCE_API=f'http://127.0.0.1:{args.port}/acceptance/supabase',
                   VTCA_DIARY_URL=f'http://127.0.0.1:{args.port}/')
        child = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'tools/acceptance_dashboard.py'),
                                  '--server.address', '127.0.0.1', '--server.port', str(args.dashboard_port),
                                  '--server.headless', 'true', '--browser.gatherUsageStats', 'false'], cwd=ROOT, env=env,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        print(f'Isolated acceptance: http://127.0.0.1:{args.port}/acceptance', flush=True)
        app.run(host='127.0.0.1', port=args.port, threaded=True, use_reloader=False, request_handler=RedactedRequestHandler)
    finally:
        if child:
            child.terminate()
            child.wait(timeout=10)


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    main()
