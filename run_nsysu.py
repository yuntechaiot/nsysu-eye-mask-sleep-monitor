"""Start the diary and research dashboard with one Python command."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from dotenv import load_dotenv
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from nsysu.server import RedactedRequestHandler, create_app

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "frontend" / "source" / "數據監控室.py"


def check_port(host, port, label):
    """Fail before launching children; never stop an existing service."""
    if not 1 <= port <= 65535:
        raise ValueError(f"{label}連接埠必須介於 1 與 65535")
    # Probe a listener rather than binding: a just-stopped server's TIME_WAIT
    # connections must not prevent an immediate restart on Windows.
    probe_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    try:
        connection = socket.create_connection((probe_host, port), timeout=0.5)
    except OSError:
        return
    connection.close()
    raise RuntimeError(f"{label}連接埠 {port} 已被使用；請先停止原本佔用此連接埠的程式，再重新啟動。")


def stop_dashboard(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_for_dashboard(process, url, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("研究 Dashboard 啟動失敗，請查看上方錯誤訊息。")
        try:
            with urlopen(url, timeout=0.5) as response:
                if response.status == 200 and response.read().strip() == b"ok":
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.2)
    raise RuntimeError("研究 Dashboard 啟動逾時，請查看上方錯誤訊息。")


def main(stop_event=None):
    load_dotenv(ROOT / ".env")
    host = os.getenv("VTCA_HOST", "127.0.0.1")
    port = int(os.getenv("VTCA_PORT", "8000"))
    dashboard_host = os.getenv("VTCA_DASHBOARD_HOST", host)
    dashboard_url = urlsplit(os.getenv("VTCA_DASHBOARD_URL", "http://127.0.0.1:8501/"))
    configured_host = dashboard_url.hostname or ""
    local_url = configured_host in ("localhost", "127.0.0.1", "::1")
    dashboard_port = int(os.getenv("VTCA_DASHBOARD_PORT", str((dashboard_url.port if local_url else None) or 8501)))
    if local_url:
        hostname = f"[{configured_host}]" if ":" in configured_host else configured_host
        os.environ["VTCA_DASHBOARD_URL"] = urlunsplit(dashboard_url._replace(netloc=f"{hostname}:{dashboard_port}"))
    check_port(host, port, "首頁")
    check_port(dashboard_host, dashboard_port, "研究 Dashboard")
    stop_event = stop_event or threading.Event()
    child = None
    web_thread = None
    probe_host = "[::1]" if ":" in dashboard_host else "127.0.0.1"
    if dashboard_host not in ("0.0.0.0", "::"):
        probe_host = f"[{dashboard_host}]" if ":" in dashboard_host else dashboard_host
    print("正在啟動睡眠日誌與研究 Dashboard…", flush=True)
    with make_server(host, port, create_app(), threaded=True, request_handler=RedactedRequestHandler) as web:
        try:
            child = subprocess.Popen([
                sys.executable, "-m", "streamlit", "run", str(DASHBOARD),
                "--server.address", dashboard_host, "--server.port", str(dashboard_port),
                "--server.headless", "true", "--browser.gatherUsageStats", "false",
            ], cwd=ROOT, stdout=sys.stdout, stderr=sys.stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt")
            wait_for_dashboard(child, f"http://{probe_host}:{dashboard_port}/_stcore/health")
            web_thread = threading.Thread(target=web.serve_forever, daemon=True)
            web_thread.start()
            display_host = "127.0.0.1" if host == "0.0.0.0" else f"[{host}]" if ":" in host else host
            print(f"\n首頁：http://{display_host}:{port}/\n研究 Dashboard：{os.getenv('VTCA_DASHBOARD_URL', f'http://{probe_host}:{dashboard_port}/')}\n兩個服務已就緒。按 Ctrl+C 一起停止。\n", flush=True)
            while not stop_event.wait(0.25):
                if child.poll() is not None:
                    raise RuntimeError("研究 Dashboard 已停止；首頁亦已停止，請檢查錯誤後重新啟動。")
                if not web_thread.is_alive():
                    raise RuntimeError("首頁服務已停止。")
        except KeyboardInterrupt:
            print("\n正在停止首頁與研究 Dashboard…", flush=True)
        finally:
            if web_thread is not None:
                web.shutdown()
                web_thread.join(timeout=5)
            stop_dashboard(child)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"啟動失敗：{error}", file=sys.stderr)
        raise SystemExit(1) from error
