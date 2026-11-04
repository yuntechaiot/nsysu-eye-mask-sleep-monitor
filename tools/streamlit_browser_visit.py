"""Visit public Streamlit homepages without logging in or submitting app data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WAKE_BUTTON = re.compile(r"^Yes, get this app back up!?$", re.IGNORECASE)


def load_targets(path: Path) -> list[dict[str, str]]:
    """Only permit anonymous root-page visits to explicitly listed Cloud apps."""
    targets = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(targets, list) or not targets:
        raise ValueError("Configure at least one public Streamlit app.")
    names = set()
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("Each target must have a name and URL.")
        name, url = target.get("name", ""), target.get("url", "")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("Target names must contain lowercase letters, numbers or hyphens.")
        if name in names or not isinstance(url, str):
            raise ValueError("Target names must be unique and URLs must be strings.")
        names.add(name)
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not re.fullmatch(r"[a-z0-9-]+\.streamlit\.app", parsed.netloc)
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Only HTTPS Streamlit root URLs without credentials or queries are allowed.")
    return targets


def visit_once(browser, target: dict[str, str], timeout: int, hold: int, frame_fallback_after: int = 30) -> dict:
    """Require a completed native app execution and a live, receiving WebSocket."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.bring_to_front()
    app_sockets = []
    woke_app = False
    promoted_app_frame = False
    result = {"woke_app": False, "homepage_visible": False,
              "status": "failed", "reason": "App did not become ready."}
    started = time.monotonic()
    target_url = urlsplit(target["url"])
    host = target_url.netloc

    def on_socket(socket):
        parsed = urlsplit(socket.url)
        if parsed.netloc == host and parsed.path.endswith("/_stcore/stream"):
            state = {"socket": socket, "received": False}
            socket.on("framereceived", lambda _: state.update(received=True))
            app_sockets.append(state)

    def connected():
        return any(state["received"] and not state["socket"].is_closed() for state in app_sockets)

    page.on("websocket", on_socket)
    page.set_default_timeout(3000)
    try:
        # Own the readiness deadline: module downloads can delay DOMContentLoaded,
        # and networkidle is inappropriate for Streamlit's persistent WebSocket.
        page.goto(target["url"], wait_until="commit", timeout=min(timeout, 60) * 1000)
        while time.monotonic() - started < timeout:
            if not promoted_app_frame and time.monotonic() - started >= frame_fallback_after:
                # If the hosting wrapper stalls, open its observed app iframe.
                # Never follow arbitrary frames, auth redirects or query URLs.
                for frame in list(page.frames):
                    candidate = urlsplit(frame.url)
                    if (
                        frame != page.main_frame
                        and candidate.scheme == target_url.scheme
                        and candidate.netloc == host
                        and candidate.path == "/~/+/"
                        and not candidate.query
                        and not candidate.fragment
                    ):
                        promoted_app_frame = True
                        remaining = max(1, timeout - (time.monotonic() - started))
                        page.goto(frame.url, wait_until="commit", timeout=min(30, remaining) * 1000)
                        break
            for frame in list(page.frames):
                if frame.is_detached():
                    continue
                try:
                    # This is the only click: the hosting platform's wake button.
                    wake = frame.get_by_role("button", name=WAKE_BUTTON)
                    if not woke_app and wake.count() and wake.first.is_visible():
                        wake.first.click()
                        woke_app = True
                    if frame.locator('[data-testid="stException"]').count():
                        result["reason"] = "Streamlit rendered an application exception."
                        return result
                    app = frame.locator('[data-testid="stApp"][data-test-script-state="notRunning"]')
                    if app.count() and connected():
                        # Keep the real browser session open briefly after rendering.
                        page.wait_for_timeout(hold * 1000)
                        if not app.count() or not connected():
                            continue
                        # Homepage layout is informative, not the keep-awake signal.
                        result["homepage_visible"] = any(
                            child.locator("#home-page").first.is_visible()
                            for child in list(page.frames) if not child.is_detached()
                        )
                        result.update(status="passed", reason="App execution completed and Streamlit session stayed connected.")
                        return result
                except PlaywrightError:
                    # Cloud can replace its startup iframe while the app wakes.
                    if page.is_closed():
                        raise
            page.wait_for_timeout(500)
    except PlaywrightError:
        # Do not log page contents, cookies or authentication redirect URLs.
        result["reason"] = "Browser navigation or session failed."
    finally:
        result["woke_app"] = woke_app
        result["opened_hosted_app_frame"] = promoted_app_frame
        result["websocket_received"] = any(state["received"] for state in app_sockets)
        result["websocket_open_at_finish"] = connected()
        result["elapsed_seconds"] = round(time.monotonic() - started, 1)
        context.close()
    return result


def visit_target(browser, target: dict[str, str], timeout: int, hold: int, attempts: int) -> dict:
    result = {**target, "status": "failed", "attempts": []}
    for number in range(1, attempts + 1):
        print(f"Visiting {target['name']} (attempt {number}/{attempts})", flush=True)
        attempt = visit_once(browser, target, timeout, hold)
        result["attempts"].append(attempt)
        print(f"{target['name']}: {attempt['status']} - {attempt['reason']}", flush=True)
        if attempt["status"] == "passed":
            result["status"] = "passed"
            break
    return result


def write_report(results: list[dict], output: Path) -> bool:
    passed = all(result["status"] == "passed" for result in results)
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "authenticated": False,
        "application_forms_submitted": 0,
        "targets": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        rows = ["## Streamlit browser visit", "", "| App | Session | Homepage visible | Wake button clicked | Attempts |",
                "| --- | --- | --- | --- | --- |"]
        for result in results:
            woke = any(attempt["woke_app"] for attempt in result["attempts"])
            homepage = any(attempt["homepage_visible"] for attempt in result["attempts"])
            rows.append(f"| [{result['name']}]({result['url']}) | {result['status']} | {homepage} | {woke} | {len(result['attempts'])} |")
        rows.extend(["", "Only public homepages were visited. No app login or form submission.",
                     "Best-effort visits reduce idle time; they do not guarantee uninterrupted hosting.", ""])
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(rows))
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "tools/streamlit_sites.json")
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/streamlit-browser-visit/report.json")
    parser.add_argument("--timeout-seconds", type=int, default=150, choices=range(1, 301), metavar="1..300")
    parser.add_argument("--hold-seconds", type=int, default=15, choices=range(0, 61), metavar="0..60")
    parser.add_argument("--attempts", type=int, default=2, choices=range(1, 4))
    parser.add_argument("--headed", action="store_true", help="Run a full Chromium window (CI uses Xvfb).")
    args = parser.parse_args()
    targets = load_targets(args.config)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        try:
            results = [visit_target(browser, target, args.timeout_seconds, args.hold_seconds, args.attempts)
                       for target in targets]
        finally:
            browser.close()
    return 0 if write_report(results, args.output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
