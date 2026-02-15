"""
Browser server: holds a single Selenium Safari session and serves actions over HTTP.

Run once (e.g. in background or a separate terminal) so the Telegram bot's browser
tool can drive Safari. Requires: safaridriver --enable (one-time, admin auth).

Usage:
  python tools/browser/browser_server.py

Listens on localhost only. Port from env BROWSER_SERVER_PORT (default 19527).
"""

import json
import logging
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PORT = int(os.environ.get("BROWSER_SERVER_PORT", "19527"))
HOST = "127.0.0.1"

_driver = None
_driver_lock = Lock()


def _is_session_invalid(exc: BaseException) -> bool:
    """True if the exception indicates the Selenium session is invalid (browser closed, etc.)."""
    msg = (getattr(exc, "msg", None) or str(exc)).lower()
    if "invalid session" in msg or "session id" in msg and "invalid" in msg:
        return True
    try:
        from selenium.common.exceptions import InvalidSessionIdException
        if type(exc) is InvalidSessionIdException:
            return True
    except ImportError:
        pass
    return False


def _ensure_valid_driver():
    """If _driver exists but session is invalid, quit and clear so get_driver() will create a new one."""
    global _driver
    if _driver is None:
        return
    try:
        _driver.current_url  # cheap check that session is alive
    except Exception as e:
        if _is_session_invalid(e):
            try:
                _driver.quit()
            except Exception as qe:
                logger.warning("Driver quit during cleanup: %s", qe)
            _driver = None
            logger.info("Cleared invalid Selenium session; next action will start a new one.")


def get_driver():
    """Lazy-init Safari WebDriver. Validates existing session; recreates if invalid. Call with _driver_lock held when used from handlers."""
    global _driver
    _ensure_valid_driver()
    if _driver is not None:
        return _driver
    try:
        from selenium import webdriver
        from selenium.webdriver.safari.options import Options
    except ImportError as e:
        raise RuntimeError("selenium not installed: pip install selenium") from e
    opts = Options()
    # Safari doesn't support headless; leave as default (visible window)
    _driver = webdriver.Safari(options=opts)
    logger.info("Safari WebDriver started")
    return _driver


def _strip_html(html: str, max_chars: int = 50000) -> str:
    """Remove script/style, collapse whitespace, truncate. Keeps structure for readability."""
    if not html:
        return ""
    # Remove script and style elements
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<noscript[^>]*>[\s\S]*?</noscript>", "", html, flags=re.IGNORECASE)
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html)
    html = html.strip()
    if len(html) > max_chars:
        html = html[:max_chars] + "\n... [truncated]"
    return html


def handle_navigate(body: dict) -> dict:
    url = body.get("url")
    if not url:
        return {"ok": False, "error": "Missing url"}
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    driver = get_driver()
    driver.get(url)
    return {"ok": True, "url": driver.current_url, "title": driver.title}


def handle_snapshot(body: dict) -> dict:
    max_chars = int(body.get("max_chars", 50000))
    driver = get_driver()
    title = driver.title
    raw = driver.page_source
    content = _strip_html(raw, max_chars=max_chars)
    return {"ok": True, "title": title, "url": driver.current_url, "content": content}


def _find_element(driver, body: dict):
    selector = body.get("selector")
    if not selector:
        raise ValueError("Missing selector")
    by = body.get("by", "css")  # css, xpath, id, name
    from selenium.webdriver.common.by import By
    by_map = {"css": By.CSS_SELECTOR, "xpath": By.XPATH, "id": By.ID, "name": By.NAME}
    by_enum = by_map.get(by.lower(), By.CSS_SELECTOR)
    return driver.find_element(by_enum, selector)


def handle_click(body: dict) -> dict:
    if not body.get("selector"):
        return {"ok": False, "error": "Missing selector"}
    driver = get_driver()
    el = _find_element(driver, body)
    el.click()
    return {"ok": True, "message": "Clicked"}


def handle_type(body: dict) -> dict:
    if not body.get("selector"):
        return {"ok": False, "error": "Missing selector"}
    text = body.get("text", "")
    driver = get_driver()
    el = _find_element(driver, body)
    el.clear()
    el.send_keys(text)
    return {"ok": True, "message": "Typed"}


def handle_upload(body: dict) -> dict:
    """Upload a file to a file input element."""
    selector = body.get("selector")
    file_path = body.get("file_path", "")
    if not selector:
        return {"ok": False, "error": "Missing selector"}
    if not file_path:
        return {"ok": False, "error": "Missing file_path"}
    by = body.get("by", "css")
    driver = get_driver()
    from selenium.webdriver.common.by import By
    import os
    # Convert to absolute path if relative
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        return {"ok": False, "error": f"File not found: {abs_path}"}
    by_map = {"css": By.CSS_SELECTOR, "xpath": By.XPATH, "id": By.ID, "name": By.NAME}
    by_enum = by_map.get(by.lower(), By.CSS_SELECTOR)
    el = driver.find_element(by_enum, selector)
    el.send_keys(abs_path)
    return {"ok": True, "message": f"Uploaded: {abs_path}"}


def handle_screenshot(body: dict) -> dict:
    import base64
    driver = get_driver()
    png = driver.get_screenshot_as_png()
    b64 = base64.standard_b64encode(png).decode("ascii")
    return {"ok": True, "image_base64": b64}


def handle_close(body: dict) -> dict:
    global _driver
    # Caller (do_POST) already holds _driver_lock
    if _driver is not None:
        try:
            _driver.quit()
        except Exception as e:
            logger.warning("Driver quit: %s", e)
        _driver = None
    return {"ok": True, "message": "Browser closed. Next action will start a new session."}


def handle_status(body: dict) -> dict:
    if _driver is None:
        return {"ok": True, "status": "no_session", "message": "No browser session. Use navigate to open one."}
    driver = get_driver()
    return {"ok": True, "status": "ready", "url": driver.current_url, "title": driver.title}


_ACTIONS = {
    "navigate": handle_navigate,
    "snapshot": handle_snapshot,
    "click": handle_click,
    "type": handle_type,
    "upload": handle_upload,
    "screenshot": handle_screenshot,
    "close": handle_close,
    "status": handle_status,
}


class BrowserHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/" and self.path != "/action":
            self.send_error(404)
            return
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError as e:
            self._send_json(400, {"ok": False, "error": f"Invalid JSON: {e}"})
            return
        action = data.get("action")
        if not action or action not in _ACTIONS:
            self._send_json(400, {"ok": False, "error": f"Missing or unknown action. Use one of: {list(_ACTIONS.keys())}"})
            return
        with _driver_lock:
            try:
                result = _ACTIONS[action](data)
            except Exception as e:
                if _is_session_invalid(e):
                    global _driver
                    try:
                        if _driver is not None:
                            _driver.quit()
                    except Exception:
                        pass
                    _driver = None
                    logger.info("Invalid session detected; cleared driver. Retrying action once.")
                    try:
                        result = _ACTIONS[action](data)
                    except Exception as e2:
                        logger.exception("Action %s failed after session reset", action)
                        result = {"ok": False, "error": str(e2)}
                else:
                    logger.exception("Action %s failed", action)
                    result = {"ok": False, "error": str(e)}
        self._send_json(200, result)

    def _send_json(self, code: int, obj: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))

    def log_message(self, format, *args):
        logger.debug(format, *args)


def main():
    server = HTTPServer((HOST, PORT), BrowserHandler)
    logger.info("Browser server listening on http://%s:%s (Safari)", HOST, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        with _driver_lock:
            if _driver is not None:
                _driver.quit()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
    sys.exit(0)
