"""Explicit offline provider adapters. Never selected by production factories."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from flask import jsonify, request

from .reminders import FlowError, TZ, digest, valid_account
from werkzeug.security import check_password_hash


class RecordingLine:
    test = True

    def __init__(self):
        self.identity = 'SYNTHETIC_LINE_A'
        self.token = secrets.token_urlsafe(24)
        self.calls = []
        self.result = 'accepted'

    def verify(self, token):
        if token != self.token:
            raise FlowError('LINE 授權已到期或取消，請重新取得綁定入口。', 401)
        return self.identity

    def push(self, payload, retry_key):
        self.calls.append({'payload': payload, 'retry_key': retry_key})
        return self.result, 'SYNTHETIC_ACCEPTED' if self.result == 'accepted' else None, None


class SyntheticDiary:
    def __init__(self, state):
        self.state = state
        with state.connect() as db:
            db.executescript('''create table if not exists acceptance_invites(member text primary key,invite text unique);
                create table if not exists acceptance_logs(id integer primary key,member text,date text,entry text,request_id text unique);
                create table if not exists acceptance_clock(value text);
                create table if not exists acceptance_sessions(token text primary key,refresh text,expires real,active integer);''')

    def snapshot(self, account, day):
        with self.state.connect() as db:
            invite = db.execute('select invite from acceptance_invites where member=?', (account['member'],)).fetchone()
            done = db.execute('select 1 from acceptance_logs where member=? and date=?', (account['member'], day)).fetchone()
        return {'active': True, 'completed': bool(done), 'invite': invite['invite'] if invite else None}


def attach(app, service, access_file):
    """Replace only external identity/data providers in the actual Flask app."""
    app.extensions['reminders'] = service
    access = json.loads(Path(access_file).read_text(encoding='utf-8'))

    def user(token):
        with service.state.connect() as db:
            row = db.execute('select * from acceptance_sessions where token=?', (token,)).fetchone()
        if not row or not row['active'] or row['expires'] < datetime.now(TZ).timestamp():
            raise FlowError('管理者登入已過期，請重新登入。', 401)
        return {'id': 'synthetic-staff', 'app_metadata': {'diary_staff': True, 'participant_admin': True}}

    def saved_session():
        token, refresh = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        expiry = (datetime.now(TZ) + timedelta(hours=1)).timestamp()
        with service.state.connect() as db:
            db.execute('insert into acceptance_sessions values(?,?,?,1)', (token, refresh, expiry))
        return {'access_token': token, 'refresh_token': refresh, 'expires_at': expiry, 'user': user(token)}

    @app.before_request
    def offline_providers():
        if request.remote_addr not in ('127.0.0.1', '::1') or request.host.split(':')[0] not in ('localhost', '127.0.0.1'):
            return jsonify(error='隔離驗收只接受本機連線'), 403
        if request.method != 'GET' and request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
            return jsonify(error='Invalid origin'), 403
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        path = request.path
        payload = request.get_json(silent=True) or {}
        try:
            if path == '/api/config':
                return jsonify(supabase_url=request.host_url.rstrip('/') + '/acceptance/supabase', publishable_key='sb_publishable_SYNTHETIC',
                               diary_url=service.base_url, dashboard_url=access['dashboard_url'], timezone='Asia/Taipei',
                               simulated=True, line=access.get('line', {}))
            if path == '/acceptance/identity':
                return jsonify(id_token=service.line.token)
            if path == '/api/staff/login':
                if not isinstance(payload, dict) or not isinstance(payload.get('account'), str) or payload.get('account', '').strip().upper() != access['admin_account'] or payload.get('password') != access['admin_password']:
                    raise FlowError('管理者帳密不正確', 401)
                return jsonify(saved_session())
            if path == '/api/participant/diary-access':
                if not isinstance(payload, dict) or not valid_account(payload.get('account')) or not isinstance(payload.get('password'), str):
                    raise FlowError('研究帳號或密碼不正確', 401)
                with service.state.connect() as db:
                    account = db.execute('select * from accounts where account_hash=? and active=1', (digest(payload['account']),)).fetchone()
                    if not account or not check_password_hash(account['password_hash'], payload['password']):
                        raise FlowError('研究帳號或密碼不正確', 401)
                    invite = db.execute('select invite from acceptance_invites where member=?', (account['member'],)).fetchone()
                if not invite:
                    raise FlowError('日誌入口未開放', 403)
                from urllib.parse import urlencode
                return jsonify(status='verified_research_account', member_id=account['member'],
                               diary_url=service.base_url + '?' + urlencode({'member': account['member'], 'invite': invite['invite']}))
            if path == '/api/participants':
                current = user(token) if token else None
                with service.state.connect() as db:
                    rows = db.execute('select member from accounts where active=1 order by member').fetchall()
                return jsonify(participants=[{'member_id': r['member'], 'display_name': '合成受試者' if current else None} for r in rows], can_manage=bool(current))
            if path.startswith('/acceptance/supabase/auth/v1/'):
                action = path.rsplit('/', 1)[-1]
                if action == 'token':
                    if request.args.get('grant_type') == 'refresh_token':
                        with service.state.connect() as db:
                            prior = db.execute('select * from acceptance_sessions where refresh=? and active=1', (payload.get('refresh_token'),)).fetchone()
                            if not prior:
                                raise FlowError('Session expired', 401)
                            db.execute('update acceptance_sessions set active=0 where refresh=?', (payload.get('refresh_token'),))
                    elif payload.get('email') != access['admin_account'].lower() + '@diary.nsysu.invalid' or payload.get('password') != access['admin_password']:
                        raise FlowError('管理者帳密不正確', 401)
                    return jsonify(saved_session())
                if action == 'logout':
                    with service.state.connect() as db:
                        db.execute('update acceptance_sessions set active=0 where token=?', (token,))
                    return jsonify({})
                return jsonify(user(token))
            if path.startswith('/acceptance/supabase/rest/v1/'):
                name = path.split('/rest/v1/', 1)[1]
                if name.startswith('rpc/'):
                    name = name[4:]
                    member = payload.get('p_member_id')
                    if name == 'diary_staff_status':
                        user(token)
                        return jsonify(True)
                    if name == 'get_fixed_diary_invitation':
                        user(token)
                        with service.state.connect() as db:
                            row = db.execute('select invite from acceptance_invites where member=?', (member,)).fetchone()
                        if not row:
                            raise FlowError('Unknown subject', 403)
                        return jsonify(member_id=member, invite=row['invite'], fixed=True)
                    if name == 'check_diary_invitation':
                        with service.state.connect() as db:
                            valid = db.execute('select 1 from acceptance_invites where member=? and invite=?', (member, payload.get('p_invite'))).fetchone()
                        return jsonify(bool(valid))
                    if name == 'submit_invited_diary':
                        entry = payload.get('p_entry', {})
                        member = entry.get('member_id')
                        with service.state.connect() as db:
                            valid = db.execute('select 1 from acceptance_invites where member=? and invite=?', (member, payload.get('p_invite'))).fetchone()
                            if not valid:
                                raise FlowError('Invalid subject capability', 403)
                            validate_entry(entry)
                            db.execute('insert or ignore into acceptance_logs(member,date,entry,request_id) values(?,?,?,?)',
                                       (member, entry['date'], json.dumps(entry), payload.get('p_request_id')))
                        return jsonify(status='success')
                    raise FlowError('驗收模式未啟用此管理寫入', 403)
                user(token)
                member = request.args.get('member_id', '').removeprefix('eq.')
                with service.state.connect() as db:
                    if name == 'research_participants':
                        return jsonify([{'member_id': r['member'], 'display_name': '合成受試者', 'archived_at': None} for r in db.execute('select member from accounts')])
                    if name == 'participant_access':
                        return jsonify([{'member_id': member, 'can_write': True}])
                    if name == 'sleep_logs':
                        if request.method != 'GET':
                            raise FlowError('請使用受試者專屬日誌入口進行提交驗收', 403)
                        query = db.execute('select * from acceptance_logs' + (' where member=?' if member else ''), (member,) if member else ())
                        return jsonify([dict(json.loads(r['entry']), id=r['id']) for r in query])
                if name in ('sleep_sessions', 'physiological_metrics'):
                    return jsonify(synthetic_research_records(name, member))
                return jsonify([])
            if path.startswith('/api/') and not path.startswith('/api/line/'):
                return jsonify(error='隔離驗收：未連接正式資料或外部寫入'), 403
        except FlowError as error:
            return jsonify(error=str(error)), error.status
        return None


def validate_entry(row):
    """Local adapter validates required data; production uses unchanged SQL RPC."""
    required = ('member_id', 'name', 'date', 'bedtime_at', 'final_wake_at', 'out_of_bed_at', 'date_definition',
                'headphone_min', 'sleep_onset_min', 'wakeup_count', 'fallback_sleep', 'disturbance',
                'disturbance_scale', 'sleep_quality')
    if any(row.get(k) is None or row.get(k) == '' for k in required) or row['date_definition'] != 'wake_date':
        raise FlowError('請完成日誌必填欄位與醒來日期。')
    if not str(row['name']).strip() or len(str(row['name'])) > 200:
        raise FlowError('請核對姓名。')
    datetime.strptime(row['date'], '%Y-%m-%d')
    for key, low, high in [('headphone_min', 0, 600), ('sleep_onset_min', 0, 300), ('wakeup_count', 0, 20), ('disturbance_scale', 0, 5), ('sleep_quality', 1, 5)]:
        value = row[key]
        if type(value) is not int or not low <= value <= high:
            raise FlowError('請核對日誌數值。')
    bed, wake, out = [datetime.fromisoformat(row[k]) for k in ('bedtime_at', 'final_wake_at', 'out_of_bed_at')]
    if bed.tzinfo is None or wake.tzinfo is None or out.tzinfo is None or not bed < wake <= out:
        raise FlowError('請核對睡眠時間順序。')
    if str(wake.astimezone(TZ).date()) != row['date']:
        raise FlowError('醒來日期不一致。')


class AcceptanceStore:
    """HTTP adapter for the real Streamlit research flow in explicit preview."""
    def __init__(self, token=None):
        import os
        self.base = os.environ['NSYSU_ACCEPTANCE_API']
        if urlsplit(self.base).hostname not in ('localhost', '127.0.0.1'):
            raise ValueError('Acceptance adapter requires loopback')
        self.token = token

    def request(self, method, path, payload=None, params=None):
        import requests
        from .store import StoreError
        r = requests.request(method, self.base + path, json=payload, params=params,
                             headers={'Authorization': 'Bearer ' + self.token} if self.token else {}, timeout=10)
        if not r.ok:
            raise StoreError(r.status_code)
        return r.json()

    def user(self):
        return self.request('GET', '/auth/v1/user')

    def rows(self, table, **filters):
        return self.request('GET', '/rest/v1/' + table, params=filters)


def synthetic_research_records(table, member):
    """Labelled sample measurements for the existing research renderer only."""
    day = str(datetime.now(TZ).date())
    if table == 'physiological_metrics':
        return [{'id': str(index), 'member_id': member, 'external_record_id': 'SYNTHETIC_' + str(index),
                 'metric': metric, 'value': value, 'unit': unit, 'measured_at': day + 'T07:00:00+08:00',
                 'source': 'SYNTHETIC', 'signal_type': 'PPG', 'algorithm_version': 'synthetic-demo',
                 'quality_status': 'valid', 'device_external_id': 'SYNTHETIC_DEVICE'}
                for index, (metric, value, unit) in enumerate([('HR', 63, 'bpm'), ('SDNN', 42, 'ms'),
                    ('RMSSD', 32, 'ms'), ('LF/HF', 1.2, 'ratio'), ('SpO2', 98, '%')])]
    previous = str((datetime.now(TZ) - timedelta(days=1)).date())
    return [{'id': 'SYNTHETIC_SLEEP', 'member_id': member, 'external_session_id': 'SYNTHETIC_SLEEP',
             'sleep_date': day, 'source': 'SYNTHETIC', 'start_at': previous + 'T23:00:00+08:00',
             'end_at': day + 'T07:15:00+08:00', 'sleep_onset_at': previous + 'T23:15:00+08:00',
             'final_wake_at': day + 'T07:00:00+08:00', 'tst_minutes': 450, 'light_minutes': 240,
             'deep_minutes': 120, 'rem_minutes': 90, 'other_sleep_minutes': 0, 'awake_minutes': 30,
             'waso_minutes': 15, 'awakening_count': 1, 'algorithm_version': 'synthetic-demo',
             'quality_status': 'valid', 'device_external_id': 'SYNTHETIC_DEVICE', 'stages': []}]
