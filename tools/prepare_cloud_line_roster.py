"""Validate an explicitly approved private PBKDF2 roster; produce private SQL.

No implicit enrollment, plaintext passwords or credential-generation rules.
Do not apply this output until the target cloud project is confirmed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def prepare(records):
    if not isinstance(records, list) or not records:
        raise ValueError('Approved private roster required')
    accounts, members = set(), set()
    statements = ['begin;']
    def literal(value):
        return 'null' if value is None else "'" + str(value).replace("'", "''") + "'"
    for row in records:
        account, member, study, password_hash = (row.get(key) for key in ('account', 'member', 'study', 'password_hash'))
        if (not isinstance(account, str) or re.fullmatch(r'ycc000000(?:0[1-9]|[1-4][0-9]|50)', account) is None
                or not isinstance(member, str) or re.fullmatch(r'ycc\d{8}', member) is None
                or not isinstance(study, str) or not 1 <= len(study) <= 80
                or not isinstance(password_hash, str)
                or re.fullmatch(r'pbkdf2:sha256:(?:[6-9]\d{5}|1\d{6}|2000000)\$[^$]{8,64}\$[a-f0-9]{64}', password_hash) is None):
            raise ValueError('Invalid approved roster row')
        if account in accounts or member in members:
            raise ValueError('Duplicate account or member')
        accounts.add(account)
        members.add(member)
        from datetime import date
        start, end = row.get('starts'), row.get('ends')
        for value in (start, end):
            if value:
                date.fromisoformat(value)
        if start and end and start > end:
            raise ValueError('Invalid research dates')
        fields = (hashlib.sha256(account.encode()).hexdigest(), password_hash, study, member, start, end)
        statements.append('insert into nsysu_line.accounts(account_hash,password_hash,study,member,starts,ends) values('
                          + ','.join(literal(value) for value in fields) + ');')
    statements.append('commit;')
    return '\n'.join(statements) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--roster', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # The resulting salted hashes and mappings remain private.
    root = Path(__file__).resolve().parents[1] / 'private'
    output = args.output.resolve()
    if not output.is_relative_to(root.resolve()):
        raise ValueError('Output must remain in the ignored private directory')
    sql = prepare(json.loads(args.roster.read_text(encoding='utf-8-sig')))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sql, encoding='utf-8')
    print('Approved private roster validated; private SQL prepared, nothing deployed.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Roster preparation aborted; no credentials logged.') from None
