import json
from datetime import datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest

from nsysu.server import create_app
from nsysu.store import Store
from nsysu.parsers import canonical_metrics
from nsysu.sleep import TZ

DASHBOARD = str(Path(__file__).resolve().parents[2] / 'frontend/source/數據監控室.py')


def test_api_import_auth_grant_validation_and_upsert(monkeypatch):
    saved = []
    failures = []
    monkeypatch.setattr(Store, 'user', lambda self: {'id': 'test-user'})
    monkeypatch.setattr(Store, 'rows', lambda self, table, **filters: [{'can_write': filters.get('member_id') == 'eq.ycc00000001'}])
    monkeypatch.setattr(Store, 'import_data', lambda self, *args: saved.append(args) or {'sessions': len(args[2])})
    monkeypatch.setattr(Store, 'record_failure', lambda self, *args: failures.append(args) or True)
    client = create_app().test_client()
    headers = {'Authorization': 'Bearer SYNTHETIC'}
    assert client.post('/api/import', headers=headers, json={'member_id': 'ycc00000002'}).status_code == 403
    payload = {'member_id': 'ycc00000001', 'adapter': 'canonical', 'content': json.dumps([{'external_session_id': 'synthetic', 'start_at': '2026-10-18T00:00+08:00', 'end_at': '2026-10-18T07:00+08:00', 'tst_minutes': 390}])}
    assert client.post('/api/import', headers=headers, json=payload).json['status'] == 'success'
    assert len(saved) == 1
    assert saved[0][2][0]['tst_minutes'] == 390
    payload['content'] = 'invalid JSON'
    response = client.post('/api/import', headers=headers, json=payload)
    assert response.status_code == 400
    assert response.json['failure_log_saved'] is True
    assert len(failures) == 1
    assert len(saved) == 1


def test_store_uses_real_primary_keys(monkeypatch):
    queries = []
    monkeypatch.setattr(Store, 'request', lambda self, method, path, payload=None, params=None: queries.append(params) or [])
    Store().rows('research_participants')
    Store().rows('participant_access')
    Store().rows('sleep_logs')
    Store().rows('participant_invites', select='member_id')
    assert [r['order'] for r in queries] == ['member_id.asc', 'member_id.asc', 'id.asc', 'member_id.asc']
    assert queries[-1]['select'] == 'member_id'


def test_participant_directory_only_public_codes_and_authorized_names(monkeypatch):
    queries = []
    def rows(self, table, **filters):
        queries.append((table, filters))
        return ([{'member_id': 'ycc00000001'}, {'member_id': 'ycc00000051'}] if table == 'participant_invites'
                else [{'member_id': 'ycc00000051', 'display_name': 'SYNTHETIC name'}])
    monkeypatch.setattr(Store, 'rows', rows)
    monkeypatch.setattr(Store, 'user', lambda self: {'app_metadata': {'participant_admin': True}})
    client = create_app().test_client()
    response = client.get('/api/participants')
    assert response.status_code == 200
    assert [p['display_name'] for p in response.json['participants']] == [None, None]
    assert response.json['can_manage'] is False
    assert all(table != 'research_participants' for table, _ in queries)
    response = client.get('/api/participants', headers={'Authorization': 'Bearer SYNTHETIC'})
    assert response.json['can_manage'] is True
    assert response.json['participants'][0]['display_name'] == 'SYNTHETIC name'
    assert response.headers['Cache-Control'] == 'no-store'


def test_register_participant_requires_admin_and_atomic_rpc(monkeypatch):
    client = create_app().test_client()
    payload = {'member_id': 'ycc00000051', 'display_name': 'SYNTHETIC name'}
    headers = {'Authorization': 'Bearer SYNTHETIC'}
    assert client.post('/api/participants', json=payload).status_code == 401
    monkeypatch.setattr(Store, 'user', lambda self: {'app_metadata': {}, 'user_metadata': {'participant_admin': True}})
    assert client.post('/api/participants', json=payload, headers=headers).status_code == 403
    monkeypatch.setattr(Store, 'user', lambda self: {'app_metadata': {'participant_admin': True}})
    monkeypatch.setattr(Store, 'rows', lambda *args, **kwargs: [])
    saved = []
    monkeypatch.setattr(Store, 'request', lambda self, method, path, payload=None, params=None: saved.append((method, path, payload)) or {'member_id': payload['p_member_id']})
    response = client.post('/api/participants', json=payload, headers=headers)
    assert response.status_code == 201
    assert saved == [('POST', '/rest/v1/rpc/register_participant', {'p_member_id': 'ycc00000051', 'p_display_name': 'SYNTHETIC name'})]
    for invalid in [{'member_id': 'wrong'}, {'member_id': ['ycc00000051']}, {'member_id': 'ycc00000051', 'display_name': 'x'*81}, []]:
        assert client.post('/api/participants', json=invalid, headers=headers).status_code == 400
    monkeypatch.setattr(Store, 'rows', lambda *args, **kwargs: [{'member_id': 'ycc00000051'}])
    assert client.post('/api/participants', json=payload, headers=headers).status_code == 409
    assert len(saved) == 1


def test_participant_directory_failure_is_not_fake_success(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError('not available')
    monkeypatch.setattr(Store, 'rows', fail)
    client = create_app().test_client()
    assert client.get('/api/participants').status_code == 503
    monkeypatch.setattr(Store, 'user', fail)
    assert client.get('/api/participants', headers={'Authorization': 'Bearer INVALID'}).status_code == 401


def test_canonical_b20_metrics_preserve_unit_signal_version():
    raw = [{'external_record_id': 'window-1', 'metric': 'RMSSD', 'value': 32, 'unit': 'ms', 'signal_type': 'PPG', 'algorithm_version': 'existing-b20-prv', 'measured_at': '2026-10-18T07:00+08:00'}]
    result = canonical_metrics(json.dumps(raw))
    assert result[0]['signal_type'] == 'PPG'
    assert result[0]['unit'] == 'ms'
    assert result[0]['algorithm_version'] == 'existing-b20-prv'
    assert result[0]['value'] == 32


def test_streamlit_empty_dashboard_runs():
    app = AppTest.from_file(DASHBOARD, default_timeout=30).run()
    assert len(app.exception) == 0
    assert len(app.tabs) == 0
    assert [x.label for x in app.text_input] == ['管理者帳號', '管理者密碼']
    next(x for x in app.radio if x.label == '我要查看').set_value('睡眠日誌與研究資料').run()
    assert [x.label for x in app.text_input] == ['管理者帳號', '管理者密碼']
    assert not app.exception


def test_query_is_explicit_and_changed_dates_do_not_show_stale_data(monkeypatch):
    requested = []
    def rows(self, table, **filters):
        requested.append(table)
        return [{'member_id': 'ycc00000001'}] if table == 'research_participants' else []
    monkeypatch.setattr(Store, 'rows', rows)
    monkeypatch.setattr(Store, 'request', lambda self, *args, **kwargs: True if args[1] == '/rest/v1/rpc/diary_staff_status' else None)
    app = AppTest.from_file(DASHBOARD, default_timeout=30)
    app.session_state['supabase_session'] = {'access_token': 'SYNTHETIC', 'expires_at': datetime(2030, 1, 1, tzinfo=TZ).timestamp()}
    app.run()
    assert 'sleep_logs' not in requested
    next(x for x in app.button if x.label == '查看資料').click().run()
    assert 'sleep_logs' in requested and len(app.tabs) == 8
    next(x for x in app.radio if x.label == '日期範圍').set_value('近 30 天').run()
    assert len(app.tabs) == 0
    assert any('選項已變更' in x.value for x in app.info)
    next(x for x in app.button if x.label == '登出目前資料來源').click().run()
    assert 'dashboard_data' not in app.session_state
    assert len(app.tabs) == 0 and not app.exception


def test_data_management_opens_without_fetching_clinical_data(monkeypatch):
    monkeypatch.setattr(Store, 'request', lambda self, *args, **kwargs: True)
    requested = []
    def rows(self, table, **filters):
        requested.append(table)
        if table == 'research_participants':
            return [{'member_id': 'ycc00000001'}]
        if table == 'participant_access':
            return [{'can_write': True}]
        return []
    monkeypatch.setattr(Store, 'rows', rows)
    app = AppTest.from_file(DASHBOARD, default_timeout=30)
    app.session_state['supabase_session'] = {'access_token': 'SYNTHETIC', 'expires_at': datetime(2030, 1, 1, tzinfo=TZ).timestamp()}
    app.run()
    next(x for x in app.radio if x.label == '功能').set_value('資料管理').run()
    next(x for x in app.button if x.label == '開啟資料管理').click().run()
    assert not any(table in requested for table in ['sleep_logs', 'sleep_sessions', 'physiological_metrics'])
    next(x for x in app.radio if x.label == '資料取得方式').set_value('匯入已授權檔案').run()
    assert next(x for x in app.button if x.label == '核對並匯入').disabled
    assert not app.exception


def test_streamlit_authorized_data_and_all_three_chart_modes(monkeypatch):
    monkeypatch.setattr(Store, 'request', lambda self, *args, **kwargs: True)
    diary = {'id': 1, 'member_id': 'ycc00000001', 'date': '2026-10-18', 'date_definition': 'wake_date', 'sleep_onset_min': 19, 'bedtime_at': '2026-10-17T22:30:00+08:00', 'lights_out_at': '2026-10-17T23:45:00+08:00', 'out_of_bed_at': '2026-10-18T07:15:00+08:00', 'morning_wake_time': '07:00', 'wake_time': '07:15', 'wore_watch': False, 'sleep_medication': None, 'drank_alcohol': True}
    session = {'id': 'synthetic', 'external_session_id': 'synthetic', 'sleep_date': '2026-10-18', 'source': 'SYNTHETIC', 'tst_minutes': 390, 'light_minutes': 200, 'deep_minutes': 100, 'rem_minutes': 90, 'other_sleep_minutes': 0, 'sleep_onset_at': '2026-10-18T00:00:00+08:00', 'final_wake_at': '2026-10-18T07:00:00+08:00', 'algorithm_version': 'test', 'quality_status': 'valid', 'stages': []}
    session['stages'] = [{'stage': 'light', 'start_at': '2026-10-18T00:00:00+08:00', 'end_at': '2026-10-18T03:20:00+08:00', 'duration_minutes': 200}, {'stage': 'deep', 'start_at': '2026-10-18T03:20:00+08:00', 'end_at': '2026-10-18T05:00:00+08:00', 'duration_minutes': 100}, {'stage': 'rem', 'start_at': '2026-10-18T05:00:00+08:00', 'end_at': '2026-10-18T06:30:00+08:00', 'duration_minutes': 90}]
    metrics = [{'id': str(i), 'metric': name, 'value': value, 'unit': unit, 'measured_at': '2026-10-18T06:00:00+08:00', 'source': 'SYNTHETIC', 'signal_type': 'PPG', 'algorithm_version': 'test'} for i, (name, value, unit) in enumerate([('TP', 9000, 'ms²'), ('LF/HF', 1.2, 'ratio'), ('RMSSD', 32, 'ms'), ('stress', 120, None), ('fatigue', 0, None), ('HR', 63, 'bpm')])]
    tables = {'research_participants': [{'member_id': 'ycc00000001'}], 'sleep_logs': [diary], 'sleep_sessions': [session], 'physiological_metrics': metrics, 'data_imports': []}
    monkeypatch.setattr(Store, 'rows', lambda self, table, **filters: tables[table])
    app = AppTest.from_file(DASHBOARD, default_timeout=30)
    app.session_state['supabase_session'] = {'access_token': 'SYNTHETIC', 'expires_at': datetime(2030, 1, 1, tzinfo=TZ).timestamp()}
    app.run()
    assert len(app.exception) == 0
    assert not app.tabs
    next(x for x in app.button if x.label == '查看資料').click().run()
    assert len(app.tabs) == 8
    assert app.tabs[3].label == '睡眠參數'
    assert any(m.label == '入睡所需時間（客觀 SOL）' and m.value == '15 分鐘' for m in app.metric)
    assert any(m.label == 'Fatigue Index 疲倦指數' and m.value == '0' for m in app.metric)
    next(x for x in app.selectbox if x.label == '睡眠區段生理對照').set_value('3. rem 05:00–06:30').run()
    assert len(app.exception) == 0
    assert any('區段平均' in x.value.columns for x in app.dataframe)
    next(x for x in app.radio if x.label == '圖表模式').set_value('雙 Y 軸比較').run()
    assert len(app.exception) == 0
    next(x for x in app.radio if x.label == '圖表模式').set_value('標準化比較').run()
    assert len(app.exception) == 0
    next(x for x in app.radio if x.label == '圖表模式').set_value('獨立圖表').run()
    next(x for x in app.multiselect if x.label == '顯示指標').set_value(['stress', 'fatigue']).run()
    assert len(app.exception) == 0
