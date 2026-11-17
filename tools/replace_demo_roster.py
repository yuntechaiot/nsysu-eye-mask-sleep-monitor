"""Apply an approved PRIVATE account/hash replacement file with a DB backup.

Each JSON row: old_account,new_account,password_hash,member. No password
generation rules or real credential lists are stored in this tool.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from nsysu.reminders import State


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--changes', type=Path, required=True)
    args = parser.parse_args()
    state = State(args.state)
    changes = json.loads(args.changes.read_text(encoding='utf-8-sig'))
    if not isinstance(changes, list) or not changes:
        raise ValueError('Approved replacement list required')
    directory = args.state.resolve().parent / 'backups'
    directory.mkdir(exist_ok=True)
    backup_path = directory / ('before-roster-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.sqlite3')
    with state.connect() as source, sqlite3.connect(backup_path) as dest:
        source.backup(dest)
    changed = state.replace_account_credentials(changes)
    print({'replaced_accounts': changed, 'backup_created': True, 'binding_dates_preserved': True})


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Private roster replacement aborted. Check approved mappings, hashes and conflicts; credentials not logged.') from None
