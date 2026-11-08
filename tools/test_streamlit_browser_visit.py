"""Browser regressions against local fixtures; no production services are used."""

import base64
from contextlib import redirect_stdout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from io import StringIO
from pathlib import Path
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

from streamlit_browser_visit import load_targets, visit_once, visit_target, write_report


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/_stcore/stream":
            digest = hashlib.sha1(
                (self.headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
            ).digest()
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", base64.b64encode(digest).decode())
            self.end_headers()
            if not parse_qs(parsed.query).get("empty"):
                self.wfile.write(b"\x82\x02ok")
                self.wfile.flush()
            self.connection.settimeout(30)
            try:
                self.rfile.read(1)
            except TimeoutError:
                pass
            self.close_connection = True
            return

        socket_script = "<script>window.ws = new WebSocket('ws://' + location.host + '/_stcore/stream');</script>"
        home = '<section id="home-page">Public sleep diary homepage</section>'
        app = '<div data-testid="stApp" data-test-script-state="notRunning">'
        routes = {
            "/ready": app + '<iframe src="/home"></iframe></div>' + socket_script,
            "/~/+/": app + '<iframe src="/home"></iframe></div>' + socket_script,
            "/native-app": app + "Public app ready</div>" + socket_script,
            "/still-running": app.replace("notRunning", "running") + home + "</div>" + socket_script,
            "/stalled-wrapper": '<iframe style="display:none" src="/~/+/"></iframe>',
            "/hidden-app": '<iframe style="display:none" src="/native-app"></iframe>',
            "/home": home,
            "/sleep": '<button onclick="location.href=\'/ready\'">Yes, get this app back up!</button>',
            "/embedded-sleep": '<iframe src="/sleep"></iframe>',
            "/no-socket": home,
            "/no-message": home + socket_script.replace("/_stcore/stream", "/_stcore/stream?empty=1"),
            "/not-ready": "This page returns HTTP 200, but the app is not loaded.",
            "/error": '<div data-testid="stException">Fixture app failure</div>',
        }
        content = ("<!doctype html><html><body>" + routes.get(parsed.path, "Missing") + "</body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_):
        pass


class BrowserVisitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def visit(self, path, timeout=10):
        # Give loaded shared CI runners time to start an iframe and its socket.
        # Negative cases below retain explicit short deadlines.
        return visit_once(self.browser, {"name": "fixture", "url": self.base + path}, timeout, hold=0)

    def test_rendered_iframe_and_live_socket_pass(self):
        result = self.visit("/ready")
        self.assertEqual(result["status"], "passed", result)
        self.assertFalse(result["woke_app"])

    def test_native_app_does_not_depend_on_custom_homepage_layout(self):
        result = self.visit("/native-app")
        self.assertEqual(result["status"], "passed", result)
        self.assertFalse(result["homepage_visible"])
        self.assertTrue(result["websocket_open_at_finish"])

    def test_hidden_wrapper_does_not_hide_a_completed_live_session(self):
        result = self.visit("/hidden-app")
        self.assertEqual(result["status"], "passed", result)
        self.assertFalse(result["homepage_visible"])

    def test_running_script_is_not_treated_as_completed(self):
        self.assertEqual(self.visit("/still-running", timeout=1)["status"], "failed")

    def test_sleep_page_is_woken_and_verified(self):
        result = self.visit("/sleep")
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["woke_app"])

    def test_sleep_page_inside_hosting_iframe_is_woken(self):
        result = self.visit("/embedded-sleep")
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["woke_app"])

    def test_stalled_hosting_wrapper_opens_its_same_origin_app_frame(self):
        result = visit_once(self.browser, {"name": "fixture", "url": self.base + "/stalled-wrapper"},
                            timeout=10, hold=0, frame_fallback_after=0)
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["opened_hosted_app_frame"])
        self.assertTrue(result["websocket_received"])

    def test_http_200_without_app_is_not_success(self):
        self.assertEqual(self.visit("/not-ready", timeout=1)["status"], "failed")

    def test_homepage_without_app_socket_is_not_success(self):
        self.assertEqual(self.visit("/no-socket", timeout=1)["status"], "failed")

    def test_open_socket_without_received_data_is_not_success(self):
        self.assertEqual(self.visit("/no-message", timeout=1)["status"], "failed")

    def test_application_exception_is_failure(self):
        result = self.visit("/error")
        self.assertEqual(result["status"], "failed")
        self.assertIn("application exception", result["reason"])

    def test_failed_visits_retry_and_report_failure(self):
        target = {"name": "fixture", "url": self.base + "/not-ready"}
        with redirect_stdout(StringIO()):
            result = visit_target(self.browser, target, timeout=1, hold=0, attempts=2)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["status"], "failed")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "report.json"
            with redirect_stdout(StringIO()), patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
                self.assertFalse(write_report([result], output))
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(report["authenticated"])
            self.assertEqual(report["application_forms_submitted"], 0)


class TargetConfigTests(unittest.TestCase):
    def load(self, targets):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "targets.json"
            path.write_text(json.dumps(targets), encoding="utf-8")
            return load_targets(path)

    def test_public_root_url_is_allowed(self):
        targets = [{"name": "fixture", "url": "https://example.streamlit.app/"}]
        self.assertEqual(self.load(targets), targets)

    def test_private_routes_queries_and_other_hosts_are_rejected(self):
        urls = [
            "http://example.streamlit.app/",
            "https://example.streamlit.app/?token=secret",
            "https://example.streamlit.app/?view=dashboard",
            "https://example.streamlit.app/#token",
            "https://example.streamlit.app/admin",
            "https://example.streamlit.app.evil.example/",
            "https://user:secret@example.streamlit.app/",
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.load([{"name": "fixture", "url": url}])

    def test_empty_or_duplicate_targets_are_rejected(self):
        with self.assertRaises(ValueError):
            self.load([])
        target = {"name": "fixture", "url": "https://example.streamlit.app/"}
        with self.assertRaises(ValueError):
            self.load([target, target])


if __name__ == "__main__":
    unittest.main(verbosity=2)
