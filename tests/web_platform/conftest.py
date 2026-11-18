"""AppTest cannot run component JavaScript; emulate its documented reply only.

The real cross-origin handshake is exercised separately in the browser suite.
"""
import pytest


@pytest.fixture(autouse=True)
def streamlit_component_adapter(monkeypatch):
    from nsysu import auth_bridge
    def component(**args):
        if args.get('operation') == 'clear':
            return {'ready': True, 'cleared': True, 'session': None}
        return {'ready': True, 'session': args.get('session')}
    monkeypatch.setattr(auth_bridge, '_component', component)
    from nsysu import dashboard_flow
    from nsysu.store import StoreError
    def unavailable_platform(token):
        raise StoreError(503)
    monkeypatch.setattr(dashboard_flow, 'platform_session', unavailable_platform)
