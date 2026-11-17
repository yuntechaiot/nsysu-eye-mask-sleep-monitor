"""A real-LINE, single-recipient gateway over isolated diary storage.

The public app has no admin, controller, test-identity or credential endpoints.
The separate controller binds loopback only and is never a tunnel upstream.
"""
from datetime import datetime
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
import uuid

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from .acceptance_adapter import SyntheticDiary, validate_entry
from .config import ROOT
from .reminders import FlowError, LineAPI, ReminderService, State, TZ
from .server import create_app


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


class DemoRuntime:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.config_path = self.directory / 'config.json'
        self.state = State(self.directory / 'state.sqlite3')
        self.diary = SyntheticDiary(self.state)

    def config(self):
        return read_json(self.config_path)

    def clock(self):
        value = self.config().get('clock')
        if not value:
            return datetime.now(TZ)
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise RuntimeError('Demo clock must include timezone')
        return parsed.astimezone(TZ)

    def service(self):
        cfg = self.config()
        credential = read_json(self.directory / 'secrets.json')
        recipient = cfg.get('allowed_line_user', '')
        origin = cfg.get('public_origin', '').rstrip('/')
        parsed = urlsplit(origin)
        if not re.fullmatch(r'U[0-9a-f]{32}', recipient) or cfg.get('recipient_confirmed') is not True:
            raise RuntimeError('Confirm exactly one authorized demo recipient first')
        if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise RuntimeError('Configure the current HTTPS test tunnel first')
        if not re.fullmatch(r'[0-9a-fA-F]{32}', credential.get('channel_secret', '')):
            raise RuntimeError('Messaging channel secret is missing')
        if not credential.get('access_token') or not re.fullmatch(r'\d{6,20}', str(cfg.get('login_channel_id', ''))):
            raise RuntimeError('Messaging token or Login channel is missing')
        if not re.fullmatch(r'\d{6,20}-[A-Za-z0-9_-]+', cfg.get('liff_id', '')):
            raise RuntimeError('LIFF is missing')
        allowed = {recipient}
        line = LineAPI(str(cfg['login_channel_id']), credential['access_token'], allowed_users=allowed)
        return ReminderService(self.state, line, self.diary, origin + '/', cfg['liff_id'],
                               credential['channel_secret'], clock=self.clock, allowed_users=allowed, message_prefix='【本機 Demo】\n')

    def tick(self, send=False):
        if send and self.config().get('demo_send_enabled') is not True:
            raise RuntimeError('Local demo sending is disabled')
        return self.service().tick(send=send)

    def valid_invite(self, member, token):
        if not isinstance(member, str) or not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{64}', token):
            return False
        cfg = self.config()
        with self.state.connect() as db:
            return bool(db.execute('''select 1 from acceptance_invites i join accounts a on a.member=i.member
                join bindings b on b.account_hash=a.account_hash
                where i.member=? and i.invite=? and a.active=1 and b.active=1 and b.line_user=?''',
                                   (member, token, cfg.get('allowed_line_user'))).fetchone())


def initialize(directory, enrollment):
    """Explicit private setup, with an approved hash/mapping supplied by caller."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    state = State(directory / 'state.sqlite3', initialize=True)
    SyntheticDiary(state)
    for record in enrollment:
        state.enroll(**record)
        with state.connect() as db:
            db.execute('insert into acceptance_invites values(?,?)', (record['member'], secrets.token_hex(32)))
    return state


def public_app(runtime):
    app = create_app()
    app.logger.setLevel('INFO')
    app.extensions['line_interaction_sending_enabled'] = lambda: runtime.config().get('demo_send_enabled') is True
    # Trust only forwarded scheme, not forwarded client/host. cloudflared is
    # the loopback upstream; the configured public Host is checked below.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0)

    @app.before_request
    def demo_boundary():
        cfg = runtime.config()
        public_host = urlsplit(cfg.get('public_origin', '')).netloc
        if request.host != public_host and request.host.split(':')[0] not in ('127.0.0.1', 'localhost'):
            return jsonify(error='Unknown demo host'), 403
        path = request.path
        if path == '/health':
            try:
                runtime.service()
                ready = True
            except (RuntimeError, ValueError):
                ready = False
            return jsonify(mode='local-live-line-demo', ready=ready, production_database=False)
        if path.startswith('/web/') and path.rsplit('.', 1)[-1] in ('js', 'css'):
            return None
        if path in ('/line', '/line/bind.js', '/line/bind.css'):
            return None
        if path == '/api/line/config':
            try:
                app.extensions['reminders'] = runtime.service()
            except (RuntimeError, ValueError):
                return jsonify(error='本機 LINE Demo 尚待完成設定，請回到 LINE 稍後重試。'), 503
            return jsonify(liff_id=cfg['liff_id'], simulated=False, live_demo=True, verification='local_research')
        if path in ('/api/line/bind', '/api/line/webhook'):
            try:
                app.extensions['reminders'] = runtime.service()
            except (RuntimeError, ValueError):
                return jsonify(error='Local LINE demo is not configured'), 503
            return None
        if path == '/api/config':
            origin = cfg.get('public_origin', '').rstrip('/')
            return jsonify(supabase_url=origin + '/demo/storage', publishable_key='sb_publishable_LOCAL_DEMO',
                           diary_url=origin + '/', dashboard_url='', timezone='Asia/Taipei',
                           simulated=False, live_demo=True, line=cfg.get('official_line', {}))
        if path == '/':
            if not runtime.valid_invite(request.args.get('member'), request.args.get('invite')):
                return jsonify(error='請從官方 LINE 的本人日誌提醒連結進入。'), 403
            return None
        if path.startswith('/demo/storage/rest/v1/rpc/'):
            if request.method != 'POST' or not request.is_json:
                return jsonify(error='JSON POST required'), 400
            allowed_origin = cfg.get('public_origin', '').rstrip('/')
            if request.headers.get('Origin') and request.headers['Origin'] not in (allowed_origin, request.host_url.rstrip('/')):
                return jsonify(error='Invalid origin'), 403
            name = path.rsplit('/', 1)[-1]
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return jsonify(error='Invalid request'), 400
            if name == 'check_diary_invitation':
                return jsonify(runtime.valid_invite(payload.get('p_member_id'), payload.get('p_invite')))
            if name == 'submit_invited_diary':
                entry = payload.get('p_entry')
                if not isinstance(entry, dict) or not runtime.valid_invite(entry.get('member_id'), payload.get('p_invite')):
                    return jsonify(error='填寫連結已失效，請回到 LINE 取得本人連結。'), 403
                try:
                    validate_entry(entry)
                    request_id = str(uuid.UUID(payload.get('p_request_id', '')))
                except (FlowError, ValueError, TypeError):
                    return jsonify(error='請核對日誌必填欄位、時間與提交識別。'), 400
                with runtime.state.connect() as db:
                    db.execute('begin immediate')
                    prior = db.execute('select entry from acceptance_logs where request_id=?', (request_id,)).fetchone()
                    canonical = json.dumps(entry, ensure_ascii=False, sort_keys=True)
                    if prior and prior['entry'] != canonical:
                        return jsonify(error='請重新確認日誌後送出。'), 409
                    if not prior:
                        db.execute('insert into acceptance_logs(member,date,entry,request_id) values(?,?,?,?)',
                                   (entry['member_id'], entry['date'], canonical, request_id))
                return jsonify(status='success', live_demo=True, production_database=False)
            return jsonify(error='This demo does not expose management RPCs'), 403
        return jsonify(error='This route is not exposed by the local LINE demo'), 404

    @app.errorhandler(Exception)
    def private_failure(error):
        return jsonify(error='本機 Demo 暫時無法完成操作，請回到 LINE 稍後重試。'), 503

    return app


def controller_app(runtime):
    app = Flask('local-line-demo-controller')
    app.config['MAX_CONTENT_LENGTH'] = 10000

    @app.before_request
    def local_only():
        if request.host.split(':')[0] not in ('127.0.0.1', 'localhost') or request.remote_addr not in ('127.0.0.1', '::1'):
            return jsonify(error='Loopback only'), 403
        if request.method != 'GET' and request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
            return jsonify(error='Invalid origin'), 403

    @app.get('/')
    def index():
        return send_from_directory(ROOT / 'frontend/live-demo', 'index.html')

    @app.get('/state')
    def status():
        cfg = runtime.config()
        secret = read_json(runtime.directory / 'secrets.json')
        with runtime.state.connect() as db:
            jobs = [dict(r) for r in db.execute('select kind,target_date,slot,status,attempts,uncertainty from outbox order by due_at')]
            bindings = [dict(r) for r in db.execute('select bound_at,reminder_start,active from bindings')]
            logs = [dict(r) for r in db.execute('select member,date from acceptance_logs')]
            event_count = db.execute('select count(*) from events').fetchone()[0]
        return jsonify(live_line=True, production_database=False, clock=runtime.clock().isoformat(),
                       jobs=jobs, bindings=bindings, submitted=logs, events=event_count,
                       configured={'channel_secret': bool(secret.get('channel_secret')), 'public_origin': bool(cfg.get('public_origin')),
                                   'recipient': cfg.get('recipient_confirmed') is True, 'sending': cfg.get('demo_send_enabled') is True},
                       public_origin=cfg.get('public_origin'), liff_id=cfg.get('liff_id'))

    @app.get('/access')
    def access():
        return jsonify(read_json(runtime.directory / 'access.json'))

    @app.post('/action')
    def action():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='JSON required'), 400
        operation = data.get('action')
        if operation == 'clock':
            try:
                value = datetime.fromisoformat(data.get('value', ''))
                value = value.replace(tzinfo=TZ) if value.tzinfo is None else value.astimezone(TZ)
            except (ValueError, TypeError):
                return jsonify(error='請選擇台灣測試時間。'), 400
            cfg = runtime.config()
            cfg['clock'] = value.isoformat()
            save_json(runtime.config_path, cfg)
            return jsonify(clock=cfg['clock'])
        if operation == 'tick':
            try:
                return jsonify(live_line=True, jobs=runtime.tick(send=True))
            except Exception:
                return jsonify(error='真實 Demo 尚未完成必要設定或發送尚未開放。'), 503
        return jsonify(error='Unknown action'), 400

    @app.after_request
    def private_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    return app
