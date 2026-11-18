"""Research account -> its existing fixed diary capability; no administrator session."""
import requests

from .store import StoreError, settings


def diary_access(account, password):
    url, _ = settings()
    try:
        response = requests.post(url + '/functions/v1/nsysu-line/diary-access',
                                 json={'account': account, 'password': password}, timeout=30, allow_redirects=False)
        if not response.ok:
            raise StoreError(response.status_code)
        value = response.json()
        if not isinstance(value, dict) or value.get('status') != 'verified_research_account':
            raise StoreError(503)
        return value
    except (requests.RequestException, ValueError) as error:
        if isinstance(error, StoreError):
            raise
        raise StoreError(503) from None
