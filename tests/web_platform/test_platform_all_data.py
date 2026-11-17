"""Synthetic contracts for complete pagination, identity binding, and one login."""
from datetime import date, datetime

import pytest
from streamlit.testing.v1 import AppTest

from nsysu.platform import Platform, PlatformError, KINDS
from nsysu.platform_data import combine_participants, normalize_metrics, load_platform_bundle, merge_records
from nsysu.store import Store
from nsysu.sleep import TZ
from pathlib import Path

DASHBOARD = str(Path(__file__).resolve().parents[2] / 'frontend/source/數據監控室.py')


def test_sports_uses_only_the_verified_read_only_portal_route_when_legacy_api_is_missing(monkeypatch):
    import requests
    calls = []

    class Response:
        def __init__(self, status):
            self.status_code, self.ok = status, status == 200

        def json(self):
            return {'success': True, 'data': {'current_page': 1, 'last_page': 1, 'total': 0, 'list': []}}

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response(404 if '/app/' in url else 200)

    monkeypatch.setattr(requests, 'request', request)
    api = Platform('SYNTHETIC')
    assert api.fetch('sports', 1, 1, 100) == []
    assert api.fetch('sports', 1, 1, 100) == []
    assert len(calls) == 3
    assert all(method == 'GET' for method, _, _ in calls)
    assert calls[1][1] == calls[2][1] == 'https://icare.docter.pro/back-end/web/physiologic/sports'
    assert all(call[2]['headers']['Authorization'] == 'Bearer SYNTHETIC' for call in calls)
    assert all(not call[2].get('data') for call in calls)


def test_other_missing_api_routes_never_switch_hosts_or_login_routes(monkeypatch):
    import requests
    calls = []

    class Missing:
        status_code = 404
        ok = False

    monkeypatch.setattr(requests, 'request', lambda method, url, **k: calls.append(url) or Missing())
    with pytest.raises(PlatformError):
        Platform('SYNTHETIC').fetch('hrv', 1, 1, 100)
    assert calls == ['https://icare.docter.pro/back-end/app/physiologic/hrv']


def test_all_api_pages_are_followed_and_arrays_do_not_receive_paging_parameters(monkeypatch):
    calls = []

    def call(self, method, path, params=None, data=None):
        calls.append(params)
        assert 'per_page' not in params
        page = params.get('page', 1)
        if page == 1:
            assert 'page' not in params
        return {'current_page': page, 'last_page': 3, 'total': 5,
                'list': [{'id': i} for i in range(2 * (page - 1), min(2 * page, 5))]}

    monkeypatch.setattr(Platform, 'call', call)
    assert len(Platform('SYNTHETIC').fetch('rri', 1, 1, 100)) == 5
    assert len(calls) == 3
    monkeypatch.setattr(Platform, 'call', lambda self, *a, **k: [{'id': 9, 'value': 0}])
    assert Platform('SYNTHETIC').fetch('calories', 1, 1, 100)[0]['value'] == 0


@pytest.mark.parametrize('shape', ['repeated', 'short', 'bad'])
def test_incomplete_pages_are_errors_instead_of_successful_empty_data(monkeypatch, shape):
    def call(self, method, path, params=None, data=None):
        if shape == 'bad':
            return {'unexpected': []}
        page = params.get('page', 1)
        return {'current_page': 1 if shape == 'repeated' else page, 'last_page': 2,
                'total': 5, 'list': [{'id': 1}] if page == 1 else []}

    monkeypatch.setattr(Platform, 'call', call)
    with pytest.raises(PlatformError):
        Platform('SYNTHETIC').fetch('heart/rate', 1, 1, 100)


def test_long_range_is_chunked_without_gaps_or_duplicate_boundary_records(monkeypatch):
    chunks = []

    def fetch(self, kind, member, start, end):
        chunks.append((start, end))
        assert end - start <= 90 * 86400
        return [{'id': 1, 'value': len(chunks)}]

    monkeypatch.setattr(Platform, 'fetch', fetch)
    rows = Platform('SYNTHETIC').fetch_range('step', 1, 0, 180 * 86400)
    assert len(chunks) == 3 and chunks[0][0] == 0 and chunks[-1][1] == 180 * 86400
    assert all(left[1] == right[0] for left, right in zip(chunks, chunks[1:]))
    assert rows == [{'id': 1, 'value': 3}]


def test_identity_mapping_never_uses_names_or_duplicate_identifiers():
    research = [{'member_id': 'ycc00000001', 'display_name': 'SAME NAME'}]
    unrelated = {'id': 2, 'identifier': 'other', 'name': 'SAME NAME'}
    result = combine_participants(research, [unrelated])
    assert 'platform_profile' not in result[0]
    assert result[1]['platform_only'] is True
    profiles = [{'id': i, 'identifier': 'ycc00000001'} for i in [3, 4]]
    result = combine_participants(research, profiles)
    assert result[0]['platform_mapping_error'] is True
    assert 'platform_profile' not in result[0] and len(result) == 3
    result = combine_participants([dict(research[0], platform_user_id=9)], profiles[:1])
    assert result[0]['platform_mapping_error'] is True and 'platform_profile' not in result[0]


def test_all_documented_kinds_have_an_explicit_status_and_raw_records_survive_parse_errors(monkeypatch):
    when = int(datetime(2026, 10, 20, 7, tzinfo=TZ).timestamp())
    called = []

    def fetch(self, kind, member, start, end):
        called.append(kind)
        if kind == 'sports':
            raise PlatformError('平台回應 HTTP 404', status=404)
        if kind == 'sleep':
            return [{'id': 99, 'start_time': None}]
        if kind == 'rri':
            return [{'id': i, 'occur_time': when, 'value': i} for i in range(40)]
        return []

    monkeypatch.setattr(Platform, 'fetch_range', fetch)
    bundle = load_platform_bundle('SYNTHETIC', {'id': 1}, date(2026, 10, 20), date(2026, 10, 20))
    assert set(called) == set(KINDS) and len(called) == 18
    assert bundle['statuses']['sports']['count'] is None
    assert bundle['statuses']['weight']['count'] == 0 and bundle['statuses']['weight']['state'] == 'success'
    assert len(bundle['raw']['sleep']) == 1 and len(bundle['parse_issues']) == 1
    assert len(bundle['metrics']) == 40
    assert all(m['unit'] is None for m in bundle['metrics'])


def test_additional_metrics_preserve_zero_signed_indices_and_unknown_units():
    when = int(datetime(2026, 10, 20, 7, tzinfo=TZ).timestamp())
    raw = {'id': 1, 'occur_time': when, 'bg': 0, 'value': 99}
    records = normalize_metrics('blood/glucose', raw)
    assert len(records) == 1 and records[0]['value'] == 0 and records[0]['unit'] is None
    records = normalize_metrics('heart/vessel', dict(raw, heart=-2, elasticity=0))
    assert {r['value'] for r in records} == {-2, 0}
    assert all(r['raw_payload']['id'] == 1 for r in records)
    records = normalize_metrics('hrv', dict(raw, fatigue=0, data={'compressive_ability': -1, 'adjustment_ability': 0}))
    assert {'fatigue', 'StressTolerance', 'Adaptability'} <= {r['metric'] for r in records}


def test_saved_and_live_records_match_across_timezones_without_duplicate_charts():
    saved = {'source': 'doctercloud', 'external_record_id': '1', 'metric': 'HR', 'value': 60,
             'measured_at': '2026-10-19T23:00:00+00:00'}
    live = dict(saved, measured_at='2026-10-20T07:00:00+08:00', value=61)
    assert merge_records([saved], [live], metric=True) == [live]


def test_admin_login_does_not_reuse_credentials_and_platform_requires_separate_authorization(monkeypatch):
    from nsysu import dashboard_flow
    calls = []
    monkeypatch.setattr(dashboard_flow, 'login', lambda account, password: {
        'access_token': 'RESEARCH_SYNTHETIC', 'expires_at': 2000000000})
    monkeypatch.setattr(Store, 'request', lambda self, *a, **k: True)
    monkeypatch.setattr(Store, 'rows', lambda self, table, **k: [{'member_id': 'ycc00000001'}] if table == 'research_participants' else [])
    monkeypatch.setattr(Platform, 'login', lambda self, account, password: calls.append(('login', account)) or {'access_token': 'PLATFORM_SYNTHETIC'})
    monkeypatch.setattr(Platform, 'members', lambda self, keyword: [{'id': 1, 'identifier': 'ycc00000001', 'name': 'SYNTHETIC'}])
    monkeypatch.setattr(Platform, 'fetch_range', lambda self, kind, *a: calls.append(('fetch', kind)) or [])
    app = AppTest.from_file(DASHBOARD, default_timeout=30).run()
    app.text_input[0].set_value('RESEARCH_TEST')
    app.text_input[1].set_value('SYNTHETIC')
    next(b for b in app.button if b.label == '登入管理工作區').click().run()
    assert calls == []
    assert 'platform_token' not in app.session_state and not app.exception
    app.text_input[0].set_value('PLATFORM_TEST')
    app.text_input[1].set_value('PLATFORM_PASSWORD')
    next(b for b in app.button if b.label == '連接 DocterCloud').click().run()
    assert calls == [('login', 'PLATFORM_TEST')]
    assert 'platform_token' in app.session_state
    next(b for b in app.button if b.label == '查看資料').click().run()
    assert len(app.tabs) == 8 and not app.exception
    assert {kind for action, kind in calls if action == 'fetch'} == set(KINDS)
    assert any('原始筆數' in frame.value.columns for frame in app.dataframe)


def test_revoked_staff_does_not_keep_a_platform_token_or_cached_records(monkeypatch):
    monkeypatch.setattr(Store, 'request', lambda self, *a, **k: False)
    monkeypatch.setattr(Platform, 'members', lambda *a: pytest.fail('Revoked staff must not read platform data'))
    app = AppTest.from_file(DASHBOARD, default_timeout=30)
    app.session_state['supabase_session'] = {'access_token': 'SYNTHETIC', 'expires_at': 2000000000}
    app.session_state['platform_token'] = 'SYNTHETIC'
    app.session_state['dashboard_data'] = {'private': 'SYNTHETIC'}
    app.run()
    assert not app.tabs and not app.exception
    assert 'platform_token' not in app.session_state and 'dashboard_data' not in app.session_state


def test_background_read_rechecks_permissions_before_any_platform_request(monkeypatch):
    from nsysu import dashboard_flow
    state = {'platform_token': 'SYNTHETIC', 'dashboard_data': {'private': True},
             'supabase_session': {'access_token': 'SYNTHETIC'}}
    monkeypatch.setattr(dashboard_flow.st, 'session_state', state)
    monkeypatch.setattr(Store, 'request', lambda self, *a, **k: False)
    monkeypatch.setattr(Store, 'rows', lambda *a, **k: pytest.fail('Unauthorized read'))
    monkeypatch.setattr(Platform, 'fetch_range', lambda *a, **k: pytest.fail('Unauthorized platform read'))
    with pytest.raises(PermissionError):
        dashboard_flow.load_records(dashboard_flow.RESEARCH,
            {'member_id': 'ycc00000001', 'platform_profile': {'id': 1}}, date(2026, 10, 20), date(2026, 10, 20), Store('SYNTHETIC'))
    assert state == {'_auth_clear': True}


def test_platform_connection_failure_preserves_working_diary_login(monkeypatch):
    from nsysu import dashboard_flow
    monkeypatch.setattr(dashboard_flow, 'login', lambda *a: {'access_token': 'SYNTHETIC', 'expires_at': 2000000000})
    monkeypatch.setattr(Store, 'request', lambda self, *a, **k: True)
    monkeypatch.setattr(Store, 'rows', lambda self, table, **k: [{'member_id': 'ycc00000001'}] if table == 'research_participants' else [])

    def unavailable(*args):
        raise PlatformError('平台回應 HTTP 503', status=503)

    monkeypatch.setattr(Platform, 'login', unavailable)
    app = AppTest.from_file(DASHBOARD, default_timeout=30).run()
    app.text_input[0].set_value('RESEARCH_TEST')
    app.text_input[1].set_value('SYNTHETIC')
    next(b for b in app.button if b.label == '登入管理工作區').click().run()
    assert 'supabase_session' in app.session_state and 'platform_token' not in app.session_state
    assert not app.exception and any('尚未連線' in item.value for item in app.info)
