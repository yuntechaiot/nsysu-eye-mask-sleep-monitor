"""Private credential repair preserves identity mapping and original binding."""
from datetime import datetime
import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from nsysu.reminders import FlowError, State, TZ, digest, valid_account
from nsysu.acceptance_adapter import RecordingLine, SyntheticDiary
from nsysu.reminders import ReminderService


def legacy_state(tmp_path):
    state = State(tmp_path / 'state.sqlite3', initialize=True)
    source = SyntheticDiary(state)
    with state.connect() as db:
        db.execute('insert into accounts values(?,?,?,?,?,?,1)',
                   (digest('yc00000001'), generate_password_hash('OLD_SYNTHETIC_PASSWORD'), 'study-A', 'ycc00000001', None, None))
        db.execute('insert into friends values(?,?,?)', ('SYNTHETIC_LINE_A', 1, 1))
        db.execute('insert into bindings values(?,?,?,?,1)',
                   ('SYNTHETIC_LINE_A', digest('yc00000001'), '2026-11-17T23:59:00+08:00', '2026-11-18'))
        db.execute('insert into acceptance_invites values(?,?)', ('ycc00000001', 'a' * 64))
        db.execute('insert into acceptance_logs(member,date,entry) values(?,?,?)', ('ycc00000001', '2026-11-16', '{}'))
    return state, source


def approved_change():
    return {'old_account': 'yc00000001', 'new_account': 'ycc00000001',
            'password_hash': generate_password_hash('NEW_SYNTHETIC_PASSWORD'), 'member': 'ycc00000001'}


def test_repair_preserves_dates_diaries_and_capability_and_is_idempotent(tmp_path):
    state, source = legacy_state(tmp_path)
    change = approved_change()
    assert state.replace_account_credentials([change]) == 1
    assert state.replace_account_credentials([change]) == 0
    with state.connect() as db:
        row = db.execute('select * from accounts').fetchone()
        assert row['account_hash'] == digest('ycc00000001') and row['member'] == 'ycc00000001'
        assert check_password_hash(row['password_hash'], 'NEW_SYNTHETIC_PASSWORD')
        assert not check_password_hash(row['password_hash'], 'OLD_SYNTHETIC_PASSWORD')
        binding = db.execute('select * from bindings').fetchone()
        assert binding['account_hash'] == row['account_hash']
        assert binding['bound_at'] == '2026-11-17T23:59:00+08:00' and binding['reminder_start'] == '2026-11-18'
        assert db.execute('select invite from acceptance_invites').fetchone()[0] == 'a' * 64
        assert db.execute('select count(*) from acceptance_logs').fetchone()[0] == 1
        assert not db.execute('pragma foreign_key_check').fetchall()
    line = RecordingLine()
    service = ReminderService(state, line, source, 'http://127.0.0.1:64670/', clock=lambda: datetime(2026, 11, 18, 0, 0, tzinfo=TZ))
    result = service.bind(line.token, 'ycc00000001', 'NEW_SYNTHETIC_PASSWORD')
    assert result['first_reminder_at'] == '2026-11-18T09:00:00+08:00'
    with pytest.raises(FlowError) as old:
        service.bind(line.token, 'yc00000001', 'OLD_SYNTHETIC_PASSWORD')
    assert old.value.status == 401


def test_missing_or_conflicting_mapping_rolls_back_entire_repair(tmp_path):
    state, _ = legacy_state(tmp_path)
    changes = [approved_change(), {'old_account': 'yc00000050', 'new_account': 'ycc00000050',
                                  'password_hash': generate_password_hash('OTHER_SYNTHETIC_PASSWORD'), 'member': 'ycc00000050'}]
    with pytest.raises(ValueError):
        state.replace_account_credentials(changes)
    with state.connect() as db:
        assert db.execute('select account_hash from accounts').fetchone()[0] == digest('yc00000001')
        assert db.execute('select account_hash from bindings').fetchone()[0] == digest('yc00000001')


@pytest.mark.parametrize('value,expected', [('ycc00000001', True), ('ycc00000050', True), ('ycc00000000', False),
    ('ycc00000051', False), ('yc00000001', False), ('ycc0000001', False), ('YCC00000001', False)])
def test_corrected_account_boundaries(value, expected):
    assert valid_account(value) is expected
