"""Dedicated LINE-only flow; ordinary website receives a small join notice."""
from concurrent.futures import ThreadPoolExecutor
import re
from threading import Lock
from time import perf_counter
from urllib.parse import quote

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from .config import ROOT, setting
from .reminders import FlowError, configured_service

bp = Blueprint('reminders', __name__)
_executor_lock = Lock()


def dispatch_interactions(flow, keys):
    """Wake the durable sender immediately without holding the webhook open."""
    app = current_app._get_current_object()  # type: ignore[attr-defined]
    enabled = app.extensions.get('line_interaction_sending_enabled', lambda: setting('LINE_PUSH_ENABLED', 'false') == 'true')
    if not keys or not enabled():
        return
    with _executor_lock:
        executor = app.extensions.get('line_interaction_executor')
        if executor is None:
            executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='line-chat')
            app.extensions['line_interaction_executor'] = executor

    def send():
        if not enabled():
            return  # Respect a Demo/production stop made after scheduling.
        started = perf_counter()
        try:
            results = flow.dispatch(keys, send=True)
            # Operational timing only: never log IDs, payloads or credentials.
            app.logger.info('LINE chat dispatch completed: jobs=%d accepted=%d elapsed_ms=%d',
                            len(results), sum(row['status'] == 'accepted' for row in results), int((perf_counter() - started) * 1000))
        except Exception:
            # Intents/attempts remain durable; the regular worker handles recovery.
            app.logger.error('LINE chat dispatch deferred to durable worker')
    try:
        executor.submit(send)
    except RuntimeError:
        app.logger.error('LINE chat dispatch deferred to durable worker')


def public_line_info():
    # Verified project official ID; public default also reaches existing cloud apps.
    account = setting('LINE_OFFICIAL_ACCOUNT_ID') or '@823bciot'
    if not re.fullmatch(r'@[A-Za-z0-9._-]{2,64}', account):
        return {}
    return {'official_id': account, 'join_url': 'https://line.me/R/ti/p/' + quote(account, safe='')}


def service():
    configured = current_app.extensions.get('reminders')
    if configured is None:
        configured = configured_service()
        current_app.extensions['reminders'] = configured
    return configured


@bp.get('/line')
def binding_page():
    return send_from_directory(ROOT / 'frontend/line', 'index.html')


@bp.get('/line/<path:name>')
def line_asset(name):
    return send_from_directory(ROOT / 'frontend/line', name)


@bp.get('/api/line/config')
def line_config():
    existing = current_app.extensions.get('reminders')
    return jsonify(liff_id=existing.liff_id if existing else setting('LINE_LIFF_ID'),
                   simulated=bool(existing and existing.line.test), verification='local_research')


@bp.post('/api/line/bind')
def bind():
    # JSON-only + exact origin; no cross-site form/CORS credential submissions.
    if request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
        return jsonify(error='請在原本的綁定頁重試。'), 403
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error='請提供研究帳號與密碼。'), 400
    try:
        result = service().bind(payload.get('id_token'), payload.get('account'), payload.get('password'), request.remote_addr)
        return jsonify(result)
    except FlowError as error:
        return jsonify(error=str(error)), error.status
    except Exception:
        return jsonify(error='服務暫時無法完成綁定，請稍後重試；尚未確認成功。'), 503


@bp.post('/api/line/webhook')
def webhook():
    try:
        flow = service()
        return jsonify(flow.webhook(request.get_data(), request.headers.get('X-Line-Signature'),
                                    on_enqueued=lambda keys: dispatch_interactions(flow, keys)))
    except FlowError as error:
        return jsonify(error=str(error)), error.status
    except Exception:
        return jsonify(error='Webhook unavailable'), 503


@bp.after_request
def private_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response
