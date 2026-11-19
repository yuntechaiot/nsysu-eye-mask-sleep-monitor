"""Private research account checks, verified LINE identity, and durable outbox.

One persistent SQLite volume on one host; external scheduler invokes tick().
No browser/session timers, no implicit test fallback, no patient credential logs.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timedelta
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
from urllib.parse import urlencode, urlsplit
import uuid
from zoneinfo import ZoneInfo

import requests
from werkzeug.security import check_password_hash

from .config import ROOT, setting
from .line_messages import line_text, reminder_text

TZ = ZoneInfo('Asia/Taipei')


class FlowError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def aware(now):
    if now.tzinfo is None:
        raise ValueError('Timezone-aware server clock required')
    return now.astimezone(TZ)


def valid_account(value):
    return isinstance(value, str) and re.fullmatch(r'ycc000000(?:0[1-9]|[1-4][0-9]|50)', value) is not None


@dataclass(frozen=True)
class Schedule:
    start: int = 9
    end: int = 21
    interval: int = 120
    grace: int = 10

    def __post_init__(self):
        if not (0 <= self.start <= self.end <= 23 and self.interval > self.grace and 1 <= self.grace <= 30):
            raise ValueError('Invalid backend reminder schedule')

    def slots(self, day):
        current = datetime.combine(day, time(self.start), TZ)
        last = datetime.combine(day, time(self.end), TZ)
        while current <= last:
            yield current
            current += timedelta(minutes=self.interval)


class State:
    def __init__(self, path, initialize=False):
        self.path = str(Path(path).resolve())
        if initialize:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as db:
                db.executescript((Path(__file__).parent / 'sql/line_state.sql').read_text())
                if db.execute('select max(version) from schema_version').fetchone()[0] < 2:
                    db.executescript((Path(__file__).parent / 'sql/line_state_v2.sql').read_text())
                if db.execute('select max(version) from schema_version').fetchone()[0] < 3:
                    db.executescript((Path(__file__).parent / 'sql/line_state_v3.sql').read_text())
        elif not Path(self.path).is_file():
            raise RuntimeError('Private LINE state has not been initialized')
        with self.connect() as db:
            if db.execute('select max(version) from schema_version').fetchone()[0] != 3:
                raise RuntimeError('Apply the explicit private state migration before starting')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=45)
        db.row_factory = sqlite3.Row
        db.execute('pragma foreign_keys=on')
        db.execute('pragma journal_mode=wal')
        db.execute('pragma busy_timeout=45000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def enroll(self, account, password_hash, study, member, starts=None, ends=None):
        if not valid_account(account) or not re.fullmatch(r'ycc\d{8}', member):
            raise ValueError('Invalid registered account or explicit diary mapping')
        if not password_hash.startswith(('scrypt:', 'pbkdf2:')) or len(password_hash) < 80:
            raise ValueError('A salted Werkzeug password hash is required')
        if not study or len(study) > 80:
            raise ValueError('Study is required')
        for value in (starts, ends):
            if value:
                datetime.strptime(value, '%Y-%m-%d')
        if starts and ends and starts > ends:
            raise ValueError('Invalid study dates')
        with self.connect() as db:
            db.execute('insert into accounts(account_hash,password_hash,study,member,starts,ends) values(?,?,?,?,?,?)',
                       (digest(account), password_hash, study, member, starts, ends))

    def replace_account_credentials(self, changes):
        """Explicit private data repair; never exposed as a website endpoint.

        Caller supplies approved account mappings and salted hashes. Preserve
        member/study, original binding dates, diary capabilities and history.
        """
        prepared = []
        seen_old, seen_new = set(), set()
        for change in changes:
            old, new, password_hash = change['old_account'], change['new_account'], change['password_hash']
            member = change['member']
            if (not isinstance(old, str) or not old or not valid_account(new)
                    or not re.fullmatch(r'ycc\d{8}', member)
                    or not isinstance(password_hash, str)
                    or not password_hash.startswith(('scrypt:', 'pbkdf2:')) or len(password_hash) < 80):
                raise ValueError('Invalid approved credential replacement')
            old_hash, new_hash = digest(old), digest(new)
            if old_hash in seen_old or new_hash in seen_new:
                raise ValueError('Duplicate credential replacement')
            seen_old.add(old_hash)
            seen_new.add(new_hash)
            prepared.append((old_hash, new_hash, password_hash, member))
        changed = 0
        with self.connect() as db:
            db.execute('begin immediate')
            db.execute('pragma defer_foreign_keys=on')
            for old_hash, new_hash, password_hash, member in prepared:
                old = db.execute('select * from accounts where account_hash=?', (old_hash,)).fetchone()
                existing = db.execute('select * from accounts where account_hash=?', (new_hash,)).fetchone()
                if old is None:
                    if existing and existing['member'] == member and existing['password_hash'] == password_hash:
                        continue  # Same approved data repair can safely be rerun.
                    raise ValueError('Registered source account not found')
                if old['member'] != member or (existing and old_hash != new_hash):
                    raise ValueError('Credential replacement conflicts with registered mapping')
                db.execute('update accounts set account_hash=?,password_hash=? where account_hash=?',
                           (new_hash, password_hash, old_hash))
                db.execute('update bindings set account_hash=? where account_hash=?', (new_hash, old_hash))
                changed += 1
            if db.execute('pragma foreign_key_check').fetchall():
                raise ValueError('Credential replacement would break a binding')
        return changed


class LineAPI:
    test = False

    def __init__(self, channel_id=None, access_token=None, allowed_users=None):
        self.channel_id = channel_id
        self.access_token = access_token
        self.allowed_users = frozenset(allowed_users) if allowed_users is not None else None

    def verify(self, token):
        channel = self.channel_id or setting('LINE_LOGIN_CHANNEL_ID')
        if not channel:
            raise RuntimeError('LINE Login channel is missing')
        if not isinstance(token, str) or not 1 <= len(token) <= 10000:
            raise FlowError('請從 LINE 重新開啟「開始綁定」。', 401)
        try:
            response = requests.post('https://api.line.me/oauth2/v2.1/verify',
                                     data={'id_token': token, 'client_id': channel}, timeout=10,
                                     allow_redirects=False)
            if response.status_code != 200:
                raise FlowError('LINE 授權已失效或取消，請回到 LINE 重新開始綁定。', 401)
            value = response.json()
            if (value.get('iss') != 'https://access.line.me' or str(value.get('aud')) != channel
                    or not isinstance(value.get('sub'), str) or not value['sub']
                    or value.get('exp', 0) <= datetime.now(TZ).timestamp()):
                raise FlowError('LINE 身分驗證未通過，請重新登入 LINE。', 401)
            if self.allowed_users is not None and value['sub'] not in self.allowed_users:
                raise FlowError('此入口僅開放已指定的本次 Demo 測試者。', 403)
            return value['sub']
        except requests.RequestException:
            raise FlowError('LINE 暫時無法驗證，請稍後重試；尚未綁定。', 503) from None

    def push(self, payload, retry_key):
        if self.allowed_users is not None and payload.get('to') not in self.allowed_users:
            return 'failed', None, 'demo_recipient_not_allowed'
        token = self.access_token or setting('LINE_CHANNEL_ACCESS_TOKEN')
        if not token:
            raise RuntimeError('LINE Messaging API token is missing')
        try:
            r = requests.post('https://api.line.me/v2/bot/message/push',
                              headers={'Authorization': 'Bearer ' + token, 'X-Line-Retry-Key': retry_key},
                              json=payload, timeout=10, allow_redirects=False)
        except requests.RequestException:
            return 'uncertain', None, 'network'
        if 200 <= r.status_code < 300 or (r.status_code == 409 and r.headers.get('x-line-accepted-request-id')):
            return 'accepted', r.headers.get('x-line-accepted-request-id') or r.headers.get('x-line-request-id'), None
        if r.status_code >= 500:
            return 'retry', None, 'upstream_5xx'
        # LINE documents 4xx as nonretryable, including rate/quota 429.
        return 'failed', None, 'rate_or_quota' if r.status_code == 429 else 'http_' + str(r.status_code)


class DiarySource:
    """Read-only existing Supabase records; never bypass diary submission RPC."""
    def snapshot(self, account, day):
        dsn = setting('LINE_READONLY_DATABASE_URL')
        if not dsn:
            raise RuntimeError('Read-only diary database is not configured')
        import psycopg
        with psycopg.connect(dsn, connect_timeout=10) as conn:
            conn.execute('set transaction read only')
            conn.execute("set local statement_timeout='10s'")
            row = conn.execute('select nsysu_private.line_diary_snapshot(%s,%s::date)', (account['member'], day)).fetchone()
        snapshot = row[0] if row else None
        if not snapshot or snapshot.get('study') != account['study']:
            return {'active': False, 'completed': False, 'invite': None}
        return snapshot



class ReminderService:
    def __init__(self, state, line, diaries, base_url, liff_id='', secret='', schedule=None, clock=None, allowed_users=None, message_prefix=''):
        self.state, self.line, self.diaries = state, line, diaries
        self.base_url, self.liff_id, self.secret = base_url, liff_id, secret
        self.schedule = schedule or Schedule()
        self.clock = clock or (lambda: datetime.now(TZ))
        self.allowed_users = frozenset(allowed_users) if allowed_users is not None else None
        self.message_prefix = message_prefix
        parsed = urlsplit(base_url)
        if (parsed.scheme != 'https' and not (line.test and parsed.hostname in ('localhost', '127.0.0.1'))
                or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('Public diary base must be HTTPS (loopback allowed only in explicit tests)')

    def limited(self, buckets, now, limit=5):
        # Persist BEFORE checking credentials/identity; failures survive restarts.
        with self.state.connect() as db:
            db.execute('begin immediate')
            db.execute('delete from attempts where at<?', (now.timestamp() - 900,))
            for bucket in buckets:
                count = db.execute('select count(*) from attempts where bucket=?', (bucket,)).fetchone()[0]
                if count >= limit:
                    raise FlowError('嘗試次數較多，請 15 分鐘後再試。', 429)
            db.executemany('insert into attempts values(?,?)', [(b, now.timestamp()) for b in buckets])

    def bind(self, token, account, password, ip='local'):
        now = aware(self.clock())
        self.limited(['ip:' + digest(ip)], now, 30)
        identity = self.line.verify(token)
        self.limited(['line:' + digest(identity), 'account:' + digest(str(account))], now)
        with self.state.connect() as db:
            db.execute('begin immediate')
            record = db.execute('select * from accounts where account_hash=? and active=1', (digest(str(account)),)).fetchone()
            if (not valid_account(account) or not isinstance(password, str) or len(password) > 256
                    or not record or not check_password_hash(record['password_hash'], password)):
                raise FlowError(line_text('bad_credentials'), 401)
            friend = db.execute('select active from friends where line_user=?', (identity,)).fetchone()
            if not friend or not friend['active']:
                raise FlowError('請先加入官方 LINE，再傳送「開始綁定」後重試。', 403)
            if record['ends'] and record['ends'] < str(now.date()):
                raise FlowError('此研究已結束，請聯絡研究團隊。', 403)
            prior = db.execute('select * from bindings where account_hash=? or line_user=?', (record['account_hash'], identity)).fetchall()
            if prior:
                if len(prior) != 1 or prior[0]['line_user'] != identity or prior[0]['account_hash'] != record['account_hash']:
                    raise FlowError('此帳號或 LINE 已有其他綁定。更換本人帳號請先回聊天室「取消綁定」並確認；他人綁定請聯絡研究團隊。', 409)
                if not prior[0]['active']:
                    raise FlowError(line_text('binding_disabled'), 403)
                bound, start = prior[0]['bound_at'], prior[0]['reminder_start']
            else:
                start = str(now.date() + timedelta(days=1))
                if record['starts']:
                    start = max(start, record['starts'])
                if record['ends'] and start > record['ends']:
                    raise FlowError('此研究已無後續提醒日期，請聯絡研究團隊。', 403)
                bound = now.isoformat()
                db.execute('insert into bindings values(?,?,?,?,1)', (identity, record['account_hash'], bound, start))
                # A confirmation from any earlier binding must never unlink this one.
                db.execute('update binding_cancellations set used_at=? where line_user=? and used_at is null',
                           (now.isoformat(), identity))
            first = start + 'T' + f'{self.schedule.start:02}:00:00+08:00'
        return {'status': 'bound', 'bound_at': bound, 'first_reminder_at': first,
                'verification': 'local_research', 'simulated': self.line.test}

    def binding_message(self, text, actions):
        return {'type': 'template', 'altText': text,
                'template': {'type': 'buttons', 'text': self.message_prefix + text, 'actions': actions}}

    def binding_entry(self):
        if not self.liff_id:
            raise RuntimeError('LIFF binding entry is not configured')
        url = self.base_url.rstrip('/') + '/line' if self.line.test else 'https://liff.line.me/' + self.liff_id
        return {'type': 'uri', 'label': '開始綁定', 'uri': url}

    def manage_binding(self, db, identity, action, now):
        """Only called for a signature-verified, private-user webhook event."""
        binding = db.execute('''select b.*,a.study,a.member from bindings b
            join accounts a using(account_hash) where b.line_user=?''', (identity,)).fetchone()
        entry = self.binding_entry()
        cancel = {'type': 'postback', 'label': '取消綁定', 'data': 'binding:cancel', 'displayText': '取消綁定'}
        if action in ('start', 'rebind'):
            if not binding:
                return self.binding_message(line_text('start'), [entry])
            entry['label'] = '重新綁定'
            return self.binding_message(line_text('bound_entry', member=binding['member']), [entry, cancel])
        if action == 'cancel':
            if not binding:
                return self.binding_message(line_text('not_bound'), [entry])
            if not binding['active']:
                return self.binding_message(line_text('binding_disabled'), [entry])
            token = secrets.token_hex(32)
            db.execute('update binding_cancellations set used_at=? where line_user=? and used_at is null',
                       (now.isoformat(), identity))
            db.execute('insert into binding_cancellations values(?,?,?,?,?,null)',
                       (digest(token), identity, binding['account_hash'], binding['bound_at'], (now + timedelta(minutes=10)).isoformat()))
            return self.binding_message(line_text('cancel_confirm', member=binding['member']), [
                {'type': 'postback', 'label': '確認取消', 'data': 'binding:confirm:' + token, 'displayText': '確認取消綁定'},
                {'type': 'postback', 'label': '保留綁定', 'data': 'binding:keep:' + token, 'displayText': '保留目前綁定'}])
        operation, token = action.split(':', 1)
        request = db.execute('''select * from binding_cancellations
            where token_hash=? and line_user=? and used_at is null''', (digest(token), identity)).fetchone()
        if (not request or now > datetime.fromisoformat(request['expires_at']) or not binding
                or not binding['active'] or binding['account_hash'] != request['account_hash'] or binding['bound_at'] != request['bound_at']):
            return self.binding_message(line_text('cancel_expired'), [cancel])
        db.execute('update binding_cancellations set used_at=? where line_user=? and used_at is null', (now.isoformat(), identity))
        if operation == 'keep':
            return self.binding_message(line_text('cancel_kept', member=binding['member']), [entry])
        db.execute('insert into binding_history values(?,?,?,?,?,?,?,?)',
                   (str(uuid.uuid4()), identity, binding['account_hash'], binding['study'], binding['member'],
                    binding['bound_at'], binding['reminder_start'], now.isoformat()))
        db.execute('delete from bindings where line_user=?', (identity,))
        db.execute("update outbox set status='cancelled',processed_at=? where line_user=? and kind='diary' and status in ('pending','retry','uncertain')",
                   (now.isoformat(), identity))
        return self.binding_message(line_text('cancel_done'), [entry])

    def webhook(self, raw, signature, on_enqueued=None):
        if not self.secret or not isinstance(signature, str):
            raise FlowError('Webhook signature required', 401)
        expected = base64.b64encode(hmac.new(self.secret.encode(), raw, hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(expected, signature):
            raise FlowError('Invalid webhook signature', 401)
        try:
            events = json.loads(raw)['events']
        except (ValueError, KeyError, TypeError):
            raise FlowError('Invalid webhook body') from None
        if not isinstance(events, list) or len(events) > 100:
            raise FlowError('Invalid webhook events')
        now = aware(self.clock())
        processed = 0
        enqueued = []
        with self.state.connect() as db:
            db.execute('begin immediate')
            for event in events:
                eid = event.get('webhookEventId')
                identity = event.get('source', {}).get('userId')
                stamp = event.get('timestamp')
                if self.allowed_users is not None and identity not in self.allowed_users:
                    continue  # A live local demo must never contact other followers.
                if not isinstance(eid, str) or not isinstance(stamp, int):
                    raise FlowError('Event ID and timestamp required')
                if not db.execute('insert or ignore into events values(?,?)', (eid, now.isoformat())).rowcount:
                    continue
                processed += 1
                if not isinstance(identity, str) or event.get('source', {}).get('type') != 'user':
                    continue
                kind = event.get('type')
                action = None
                if kind == 'follow':
                    action = 'start'
                elif kind == 'message':
                    action = {'開始綁定': 'start', '綁定': 'start', 'bind': 'start', '重新綁定': 'rebind', '取消綁定': 'cancel'}.get(event.get('message', {}).get('text', '').strip())
                elif kind == 'postback':
                    data = event.get('postback', {}).get('data', '')
                    if isinstance(data, str) and re.fullmatch(r'binding:(?:start|rebind|cancel|(?:confirm|keep):[0-9a-f]{64})', data):
                        action = data.removeprefix('binding:')
                if kind != 'unfollow' and action is None:
                    continue
                old = db.execute('select * from friends where line_user=?', (identity,)).fetchone()
                if old and (old['event_ms'] > stamp or (old['event_ms'] == stamp and not old['active'])):
                    continue
                db.execute('insert into friends values(?,?,?) on conflict(line_user) do update set active=excluded.active,event_ms=excluded.event_ms',
                           (identity, int(kind != 'unfollow'), stamp))
                if kind == 'unfollow':
                    db.execute("update outbox set status='cancelled' where line_user=? and status in ('pending','retry','uncertain')", (identity,))
                    db.execute('update binding_cancellations set used_at=? where line_user=? and used_at is null', (now.isoformat(), identity))
                    continue
                payload = {'to': identity, 'messages': [self.manage_binding(db, identity, action, now)]}
                category = 'welcome' if action in ('start', 'rebind') else 'binding'
                key = category + ':' + eid
                self.enqueue(db, key, category, identity, now, payload)
                enqueued.append(key)
        # The durable transaction must commit before an immediate sender runs.
        # Redelivered events enqueue no new keys and cannot trigger another send.
        if enqueued and on_enqueued:
            on_enqueued(tuple(enqueued))
        return {'processed': processed}

    def enqueue(self, db, key, kind, identity, due, payload, account=None, slot=None):
        record = account or {}
        db.execute('''insert or ignore into outbox(job_key,kind,study,member,target_date,slot,line_user,due_at,retry_key,payload)
            values(?,?,?,?,?,?,?,?,?,?)''',
                   (key, kind, record.get('study'), record.get('member'), str(due.date()) if account else None,
                    slot, identity, due.isoformat(), str(uuid.uuid5(uuid.NAMESPACE_URL, 'nsysu-line-v1:' + key)),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True)))

    def eligible(self, db, identity, day):
        row = db.execute('''select a.*, b.bound_at,b.reminder_start from bindings b
            join accounts a on a.account_hash=b.account_hash join friends f on f.line_user=b.line_user
            where b.line_user=? and b.active=1 and a.active=1 and f.active=1''', (identity,)).fetchone()
        if not row:
            return None
        a = dict(row)
        if day < a['reminder_start'] or (a['starts'] and day < a['starts']) or (a['ends'] and day > a['ends']):
            return None
        snapshot = self.diaries.snapshot(a, day)
        if not snapshot['active'] or snapshot['completed'] or not re.fullmatch(r'[a-f0-9]{64}', snapshot.get('invite') or ''):
            return None
        return a, snapshot

    def tick(self, send=False):
        now = aware(self.clock())
        # Commit immutable intent first, so a crash during HTTP retains retry identity.
        with self.state.connect() as db:
            db.execute('begin immediate')
            for binding in db.execute('select line_user from bindings').fetchall():
                eligible = self.eligible(db, binding['line_user'], str(now.date()))
                if not eligible:
                    continue
                account, snap = eligible
                for due in self.schedule.slots(now.date()):
                    if not due <= now <= due + timedelta(minutes=self.schedule.grace):
                        continue
                    slot = due.strftime('%H:%M')
                    key = json.dumps([account['study'], account['member'], str(now.date()), slot], separators=(',', ':'))
                    url = self.base_url.rstrip('/') + '/?' + urlencode({'member': account['member'], 'invite': snap['invite'], 'date': str(now.date())})
                    body = self.message_prefix + reminder_text(account['member'], str(now.date()), slot)
                    payload = {'to': binding['line_user'], 'messages': [{'type': 'template', 'altText': body,
                        'template': {'type': 'buttons', 'text': body,
                                     'actions': [{'type': 'uri', 'label': '填寫睡眠日誌', 'uri': url}]}}]}
                    self.enqueue(db, key, 'diary', binding['line_user'], due, payload, account, slot)
        with self.state.connect() as db:
            keys = [r['job_key'] for r in db.execute("select job_key from outbox where status in ('pending','retry','uncertain') order by due_at")]
        return self.dispatch(keys, send=send)

    def dispatch(self, keys, send=False):
        """Dispatch only committed intents; shared by immediate chat and timer."""
        results = []
        for key in keys:
            # Each intent/attempt/result is durable independently. A claimed attempt
            # starts uncertain before HTTP; concurrent workers respect its 60s lease.
            now = aware(self.clock())
            with self.state.connect() as db:
                db.execute('begin immediate')
                job = db.execute('select * from outbox where job_key=?', (key,)).fetchone()
                if not job or job['status'] not in ('pending', 'retry', 'uncertain'):
                    continue
                due = datetime.fromisoformat(job['due_at'])
                if (job['kind'] == 'diary' and due.date() != now.date()) or now > due + timedelta(minutes=self.schedule.grace):
                    final = 'uncertain_final' if job['uncertainty'] else 'skipped'
                    db.execute('update outbox set status=?,processed_at=? where job_key=?', (final, now.isoformat(), key))
                    continue
                if now < due or (job['retry_at'] and now < datetime.fromisoformat(job['retry_at'])):
                    continue
                if job['attempts'] >= 3:
                    db.execute("update outbox set status='uncertain_final' where job_key=?", (key,))
                    continue
                if not self.job_eligible(db, job, now):
                    db.execute("update outbox set status='cancelled',processed_at=? where job_key=?", (now.isoformat(), key))
                    continue
                if not send:
                    results.append({'kind': job['kind'], 'status': 'dry_run'})
                    continue
                attempts = job['attempts'] + 1
                prior_unknown = bool(job['uncertainty'])
                lease = (now + timedelta(seconds=60)).isoformat()
                db.execute("update outbox set status='uncertain',uncertainty=1,attempts=?,retry_at=?,processed_at=?,error_code='dispatch_intent' where job_key=?",
                           (attempts, lease, now.isoformat(), key))
            with self.state.connect() as db:
                db.execute('begin immediate')
                current = db.execute('select * from outbox where job_key=?', (key,)).fetchone()
                if current['status'] != 'uncertain' or current['attempts'] != attempts or current['retry_at'] != lease:
                    continue
                now = aware(self.clock())
                if ((current['kind'] == 'diary' and due.date() != now.date()) or now > due + timedelta(minutes=self.schedule.grace)
                        or not self.job_eligible(db, current, now)):
                    db.execute("update outbox set status='cancelled',uncertainty=?,processed_at=? where job_key=?", (int(prior_unknown), now.isoformat(), key))
                    continue
                now = aware(self.clock())
                if (current['kind'] == 'diary' and due.date() != now.date()) or now > due + timedelta(minutes=self.schedule.grace):
                    db.execute('update outbox set status=?,uncertainty=?,processed_at=? where job_key=?',
                               ('uncertain_final' if prior_unknown else 'skipped', int(prior_unknown), now.isoformat(), key))
                    continue
                status, request_id, error = self.line.push(json.loads(current['payload']), current['retry_key'])
                finished = aware(self.clock())
                unknown = status in ('retry', 'uncertain') or (status != 'accepted' and prior_unknown)
                if status == 'failed' and unknown:
                    status = 'uncertain_final'
                if status in ('retry', 'uncertain') and attempts >= 3:
                    status = 'uncertain_final'
                retry_at = (finished + timedelta(seconds=30 * 2 ** (attempts - 1))).isoformat() if status in ('retry', 'uncertain') else None
                db.execute('update outbox set status=?,uncertainty=?,retry_at=?,processed_at=?,request_id=?,error_code=? where job_key=?',
                           (status, int(unknown), retry_at, finished.isoformat(), request_id, error, key))
                results.append({'kind': current['kind'], 'status': status})

        return results


    def job_eligible(self, db, job, now):
        friend = db.execute('select active from friends where line_user=?', (job['line_user'],)).fetchone()
        if not friend or not friend['active']:
            return False
        if job['kind'] != 'diary':
            return True
        eligible = self.eligible(db, job['line_user'], job['target_date'])
        if not eligible or eligible[0]['member'] != job['member'] or eligible[0]['study'] != job['study']:
            return False
        action = json.loads(job['payload'])['messages'][0]['template']['actions'][0]['uri']
        return urlencode({'invite': eligible[1]['invite']}) in action


def configured_service():
    if setting('RESEARCH_AUTH_MODE', 'local_research') != 'local_research':
        raise RuntimeError('No authorized Docter+ authentication adapter is configured; no local fallback')
    path = setting('LINE_STATE_PATH', str(ROOT / 'private/line-state.sqlite3'))
    return ReminderService(State(path), LineAPI(), DiarySource(), setting('LINE_PUBLIC_URL'),
                           setting('LINE_LIFF_ID'), setting('LINE_CHANNEL_SECRET'),
                           Schedule(int(setting('LINE_START_HOUR', '9')), int(setting('LINE_LAST_HOUR', '21')),
                                    int(setting('LINE_INTERVAL_MINUTES', '120')), int(setting('LINE_GRACE_MINUTES', '10'))))
