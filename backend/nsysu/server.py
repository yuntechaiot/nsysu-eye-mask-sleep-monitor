"""Serve existing diary and authenticated, atomic research import API."""
import os
import re
from urllib.parse import urlsplit
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from requests import RequestException
from werkzeug.serving import WSGIRequestHandler
from .store import Store, StoreError, settings
from .parsers import parse_sleep_file, docter_sleep, docter_metrics, canonical_metrics
from .platform import Platform
from .staff_auth import staff_login

ROOT = Path(__file__).resolve().parents[2]


class RedactedRequestHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        # Invitations are write capabilities. Never put query strings in logs.
        self.log('info', '%s %s %s', self.command, urlsplit(self.path).path, code)


def create_app():
    app = Flask(__name__)
    from .reminder_routes import bp, public_line_info
    app.register_blueprint(bp)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    @app.get("/")
    def index():
        response = send_from_directory(ROOT / "frontend/source", "睡眠日誌表單.html")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/web/<path:name>")
    def asset(name):
        return send_from_directory(ROOT / "frontend/web", name)

    @app.get("/api/config")
    def config():
        url, key = settings()
        diary_url = os.getenv("VTCA_DIARY_URL", "")
        if diary_url and (urlsplit(diary_url).scheme not in ("http", "https") or not urlsplit(diary_url).netloc):
            diary_url = ""
        return jsonify(line=public_line_info(), supabase_url=url, publishable_key=key, timezone="Asia/Taipei", diary_url=diary_url, dashboard_url=os.getenv("VTCA_DASHBOARD_URL", "http://127.0.0.1:8501"))

    @app.get("/api/participants")
    def participants():
        # Public invitations expose codes only. Names require the caller's RLS grant.
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
        store = Store(token)
        try:
            user = store.user() if token else {}
        except ValueError:
            return jsonify(error="登入已到期，請重新登入"), 401
        except RequestException:
            return jsonify(error="暫時無法驗證登入，請稍後重試"), 503
        try:
            codes = store.rows("participant_invites", select="member_id")
            names = store.rows("research_participants", select="member_id,display_name,archived_at") if token else []
            labels = {row["member_id"]: row.get("display_name") for row in names}
            directory = [row for row in names if request.args.get('include_archived') == '1' or not row.get('archived_at')] if token else [{"member_id": row["member_id"], "display_name": labels.get(row["member_id"])} for row in codes]
            return jsonify(participants=directory,
                           can_manage=user.get("app_metadata", {}).get("participant_admin") is True)
        except (ValueError, KeyError, RequestException):
            return jsonify(error="無法載入受試者清單，請確認連線與資料庫更新後重試"), 503

    @app.post("/api/participants")
    def register_participant():
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify(error="請先登入已開通的受試者管理員帳號"), 401
        store = Store(auth[7:])
        try:
            user = store.user()
        except ValueError:
            return jsonify(error="登入已到期，請重新登入"), 401
        except RequestException:
            return jsonify(error="暫時無法驗證登入，請稍後重試"), 503
        if user.get("app_metadata", {}).get("participant_admin") is not True:
            return jsonify(error="此帳號沒有新增受試者的權限，請聯絡專案管理員開通"), 403
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="請提供受試者編號與姓名"), 400
        member = payload.get("member_id", "")
        label = payload.get("display_name")
        if not isinstance(member, str) or not re.fullmatch(r"ycc[0-9]{8}", member.strip().lower()):
            return jsonify(error="編號須為 ycc 加上 8 位數字，例如 ycc00000051"), 400
        if label is not None and (not isinstance(label, str) or len(label.strip()) > 80):
            return jsonify(error="姓名最多 80 個字，可留空"), 400
        member = member.strip().lower()
        try:
            if store.rows("research_participants", member_id="eq." + member, select="member_id"):
                return jsonify(error="此受試者編號已存在，請選擇既有受試者或使用其他編號"), 409
            result = store.request("POST", "/rest/v1/rpc/register_participant", {
                "p_member_id": member, "p_display_name": (label.strip() or None) if label is not None else None})
            return jsonify(participant=result), 201
        except ValueError:
            # Also handles concurrent duplicate submissions without overwriting data.
            return jsonify(error="新增未完成；請重新整理清單確認編號是否已存在，並確認管理權限"), 409
        except RequestException:
            return jsonify(error="連線中斷，尚未確認新增結果；請重新整理清單確認後再重試"), 503

    @app.get("/health")
    def health():
        return jsonify(status="ok", version="2.0.0")

    @app.post('/api/staff/login')
    def management_login():
        if request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
            return jsonify(error='請在原本的登入頁重試。'), 403
        payload = request.get_json(silent=True)
        if (not isinstance(payload, dict) or not isinstance(payload.get('account'), str)
                or not isinstance(payload.get('password'), str) or len(payload['account']) > 64
                or not 1 <= len(payload['password']) <= 256):
            return jsonify(error='請輸入 DocterCloud 管理者帳號與密碼。'), 400
        try:
            return jsonify(staff_login(payload['account'], payload['password']))
        except StoreError as error:
            return jsonify(error='管理者登入未成功，請核對 DocterCloud 帳密、研究授權與連線。'), error.status
        except Exception:
            return jsonify(error='管理者登入服務暫時無法使用，請稍後重試。'), 503

    @app.post('/api/participant/diary-access')
    def participant_diary_access():
        if request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
            return jsonify(error='請在原本的網頁重試。'), 403
        payload = request.get_json(silent=True)
        if (not isinstance(payload, dict) or not isinstance(payload.get('account'), str)
                or not re.fullmatch(r'ycc000000(?:0[1-9]|[1-4][0-9]|50)', payload['account'])
                or not isinstance(payload.get('password'), str) or not 1 <= len(payload['password']) <= 256):
            return jsonify(error='請輸入研究帳號與密碼。'), 400
        try:
            from .participant_entry import diary_access
            return jsonify(diary_access(payload['account'], payload['password']))
        except StoreError as error:
            return jsonify(error='研究帳號或密碼不正確，或日誌入口目前無法使用。'), error.status
        except Exception:
            return jsonify(error='日誌入口暫時無法取得，請稍後再試。'), 503

    @app.post("/api/import")
    @app.post("/api/sync")
    def import_data():
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify(error="請先使用日誌帳號登入"), 401
        store = Store(auth[7:])
        try:
            store.user()
        except ValueError:
            return jsonify(error="日誌登入已失效"), 401
        payload = request.get_json(silent=True) or {}
        member = payload.get("member_id")
        grants = store.rows("participant_access", member_id="eq." + str(member))
        if not any(g.get("can_write") for g in grants):
            return jsonify(error="沒有此受試者的寫入授權"), 403
        raw = {"operation": request.path}
        source = "doctercloud" if request.path == "/api/sync" or payload.get("adapter") == "doctercloud_v5_4" else "authorized_export"
        try:
            if request.path == "/api/sync":
                # Participant's platform ID comes from administrator-owned mapping.
                participants = store.rows("research_participants", member_id="eq." + str(member))
                external_id = participants[0].get("platform_user_id") if participants else None
                if external_id is None:
                    raise ValueError("尚未建立經核實的平台會員 ID 對應")
                platform_token = request.headers.get("X-Platform-Token")
                if not platform_token:
                    raise ValueError("尚未提供平台登入 Token")
                platform = Platform(platform_token)
                start, end = int(payload["start_ts"]), int(payload["end_ts"])
                raw = {kind: platform.fetch(kind, external_id, start, end) for kind in ("sleep", "hrv", "heart/rate")}
                sessions = [docter_sleep(r) for r in raw["sleep"]]
                metrics = docter_metrics(raw["hrv"]) + docter_metrics(raw["heart/rate"], "hr")
                source = "doctercloud"
            else:
                adapter = payload.get("adapter", "canonical")
                source = "doctercloud" if adapter == "doctercloud_v5_4" else payload.get("source", "authorized_export")
                if not isinstance(source, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,63}", source):
                    raise ValueError("來源識別須為 2–64 個小寫英文字母、數字、底線、句點或減號")
                raw = payload.get("content", "")
                if payload.get("kind") == "physiological":
                    sessions = []
                    metrics = canonical_metrics(raw, payload.get("format", "json"))
                else:
                    sessions = parse_sleep_file(raw, payload.get("format", "json"), adapter)
                    metrics = []
            if not sessions and not metrics:
                return jsonify(status="empty", message="平台未提供區間資料；未建立假 Session")
            result = store.import_data(member, source, sessions, metrics, raw)
            return jsonify(status="success", result=result)
        except (ValueError, KeyError, TypeError) as error:
            # Status stays an error; do not report an empty dataset as a successful sync.
            try:
                saved = store.record_failure(member, source, raw, str(error))
            except Exception:
                saved = False
            return jsonify(status="failed", error=str(error), failure_log_saved=saved), 400
        except Exception:
            message = "平台連線失敗，未確認同步完成；請稍後重試"
            try:
                saved = store.record_failure(member, source, raw, message)
            except Exception:
                saved = False
            return jsonify(status="failed", error=message, failure_log_saved=saved), 502

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


if __name__ == "__main__":
    create_app().run(host=os.getenv("VTCA_HOST", "127.0.0.1"), port=int(os.getenv("VTCA_PORT", "8000")), request_handler=RedactedRequestHandler)
