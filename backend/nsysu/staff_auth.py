"""DocterCloud is the only password authority; the cloud broker issues RLS sessions."""
import requests

from .config import setting
from .store import StoreError, settings


def endpoint():
    url, _ = settings()
    expected = url + '/functions/v1/nsysu-staff-auth'
    configured = setting('NSYSU_STAFF_AUTH_URL', expected).rstrip('/')
    if configured != expected:
        raise ValueError('管理者登入服務與研究專案不一致')
    return configured


def call(path, payload=None, token=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    try:
        response = requests.post(endpoint() + path, json=payload or {}, headers=headers,
                                 timeout=45, allow_redirects=False)
        if not response.ok:
            raise StoreError(response.status_code)
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError('Invalid staff response')
        return value
    except (requests.RequestException, ValueError) as error:
        if isinstance(error, StoreError):
            raise
        raise StoreError(503) from None


def staff_login(account, password):
    result = call('/login', {'account': account, 'password': password})
    if (not isinstance(result.get('access_token'), str) or not isinstance(result.get('refresh_token'), str)
            or result.get('user', {}).get('app_metadata', {}).get('diary_staff') is not True):
        raise StoreError(403)
    return result


def platform_session(access_token):
    result = call('/session', token=access_token)
    token = result.get('access_token')
    if not isinstance(token, str) or not token:
        raise StoreError(503)
    return token
