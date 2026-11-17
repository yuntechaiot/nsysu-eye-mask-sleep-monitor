"""Import an explicitly prepared PRIVATE roster; never generate credentials.

JSON array: account,password_hash,study,member[,starts,ends]. Passwords must
already be hashed with Werkzeug scrypt or PBKDF2. No plaintext input/logging.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from nsysu.reminders import State


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--roster', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.roster.read_text(encoding='utf-8-sig'))
    state = State(args.state)
    # Validate all inputs in a disposable copy first; duplicate imports abort.
    import tempfile
    import sqlite3
    with tempfile.TemporaryDirectory() as temp:
        check = State(Path(temp) / 'validate.sqlite3', initialize=True)
        for record in records:
            check.enroll(**record)
        with state.connect() as dest, check.connect() as source:
            dest.execute('begin immediate')
            for row in source.execute('select * from accounts'):
                dest.execute('insert into accounts values(?,?,?,?,?,?,?)', tuple(row))
    print('Private roster imported; no credentials printed.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Import aborted. Check private roster, hashes, dates and duplicate mappings; no details logged.') from None
