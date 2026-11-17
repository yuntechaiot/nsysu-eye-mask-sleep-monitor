"""Real LINE local demo; tunnel only port 64670, NEVER controller 64672."""
import argparse
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from nsysu.live_demo import DemoRuntime, controller_app, public_app
from nsysu.server import RedactedRequestHandler
from run_nsysu import check_port
from werkzeug.serving import make_server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=ROOT / 'private/live-demo')
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    runtime = DemoRuntime(args.directory)
    if args.worker:
        result = runtime.tick(send=True)
        print({'live_local_demo': True, 'jobs': len(result), 'states': [r['status'] for r in result]})
        return
    check_port('127.0.0.1', 64670, 'LINE 測試 gateway')
    check_port('127.0.0.1', 64672, 'LINE 本機控制工具')
    with make_server('127.0.0.1', 64670, public_app(runtime), threaded=True, request_handler=RedactedRequestHandler) as public:
        with make_server('127.0.0.1', 64672, controller_app(runtime), threaded=True, request_handler=RedactedRequestHandler) as local:
            threading.Thread(target=local.serve_forever, daemon=True).start()
            print('Local controller: http://127.0.0.1:64672/ ; tunnel upstream: 127.0.0.1:64670', flush=True)
            try:
                public.serve_forever()
            finally:
                local.shutdown()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit('Local LINE demo failed closed. Check private setup; no simulated success returned.') from None
