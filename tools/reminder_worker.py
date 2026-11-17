"""Run once under cron/systemd timer. Dry-run unless --send AND flag enabled."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from nsysu.config import ROOT, setting
from nsysu.reminders import State, configured_service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--init-state', action='store_true')
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()
    if args.init_state:
        State(setting('LINE_STATE_PATH', str(ROOT / 'private/line-state.sqlite3')), initialize=True)
        print('Private SQLite schema initialized; no external database changed.')
        return
    if args.send and setting('LINE_PUSH_ENABLED', 'false') != 'true':
        raise SystemExit('LINE_PUSH_ENABLED is false; no API requests sent.')
    try:
        results = configured_service().tick(send=args.send)
        print({'processed': len(results), 'states': [row['status'] for row in results], 'dry_run': not args.send})
    except Exception:
        raise SystemExit('Worker failed closed. Check private configuration and connectivity; no success claimed.') from None


if __name__ == '__main__':
    main()
