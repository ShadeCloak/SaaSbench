
from __future__ import annotations

import logging
import os
import threading
import subprocess
import signal
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("browser_primitives")


def _proc_descendants(pid: int) -> set:
    seen: set = set()
    stack = [pid]
    while stack:
        p = stack.pop()
        try:
            out = subprocess.check_output(
                ["pgrep", "-P", str(p)], text=True,
                stderr=subprocess.DEVNULL)
        except Exception:
            continue
        for tok in out.split():
            try:
                k = int(tok)
            except ValueError:
                continue
            if k not in seen:
                seen.add(k)
                stack.append(k)
    return seen


class _BrowserWatchdog:

    def __init__(self, seconds=75.0):
        self.seconds = seconds
        self._old = None
        self._armed = False

    def _handler(self, _signum, _frame):
        try:
            logger.warning("browser watchdog fired after %ss — killing chromium",
                           self.seconds)
        except Exception:
            pass
        for k in _proc_descendants(os.getpid()):
            try:
                os.kill(k, signal.SIGKILL)
            except Exception:
                pass
        try:
            import subprocess as _sp
            _sp.run(["pkill", "-9", "-f", "chromium|playwright|headless_shell"],
                    timeout=5)
        except Exception:
            pass
        raise TimeoutError(
            f"browser watchdog: render exceeded {self.seconds}s")

    def __enter__(self):
        try:
            self._old = signal.signal(signal.SIGALRM, self._handler)
            signal.setitimer(signal.ITIMER_REAL, self.seconds, 15.0)
            self._armed = True
        except (ValueError, AttributeError, OSError):
            self._armed = False
        return self

    def __exit__(self, *_exc):
        if not self._armed:
            return
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if self._old is not None:
                signal.signal(signal.SIGALRM, self._old)
        except Exception:
            pass

DEFAULT_VIEWPORT = {"width": 1440, "height": 900}
DEFAULT_TIMEOUT_MS = 15000
DEFAULT_SETTLE_MS = 800
DEFAULT_MAX_HTML_CHARS = 200_000
DEFAULT_SCREENSHOT_DIR = "/tmp/saasbench_screenshots"


def _config_base_url() -> Optional[str]:
    try:
        import config as _cfg
    except Exception:
        return None
    for attr in ("FRONTEND_BASE_URL", "APP_BASE_URL", "BASE_URL"):
        v = getattr(_cfg, attr, None)
        if isinstance(v, str) and v:
            return v.rstrip("/")
    return None


_AUTH_COOKIE_CACHE: Dict[str, list] = {}


def _auth_cookies(url: str) -> list:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin in _AUTH_COOKIE_CACHE:
        return _AUTH_COOKIE_CACHE[origin]
    cookies: list = []
    login = None
    try:
        import config as _cfg
        login = getattr(_cfg, "FRONTEND_LOGIN", None)
    except Exception:
        login = None
    if login and login.get("url"):
        try:
            import requests
            lurl = login["url"].replace("{{base_url}}", origin)
            kw: Dict[str, Any] = {"timeout": 15}
            _data = dict(login["data"]) if isinstance(login.get("data"), dict) \
                else login.get("data")
            _json = dict(login["json"]) if isinstance(login.get("json"), dict) \
                else login.get("json")
            _headers = {k: (v.replace("{{base_url}}", origin)
                            if isinstance(v, str) else v)
                        for k, v in (login.get("headers") or {}).items()}
            sess = requests.Session()
            _csrf = login.get("csrf")
            if _csrf:
                try:
                    _curl = (_csrf.get("url") or lurl).replace("{{base_url}}", origin)
                    _cr = sess.get(_curl, timeout=15)
                    _tok = ""
                    if _csrf.get("cookie"):
                        _tok = sess.cookies.get(_csrf["cookie"], "") or ""
                    elif _csrf.get("regex"):
                        import re as _re
                        _m = _re.search(_csrf["regex"], _cr.text)
                        _tok = _m.group(1) if _m else ""
                    if _tok:
                        if _csrf.get("header"):
                            _headers[_csrf["header"]] = _tok
                        if _csrf.get("field"):
                            if isinstance(_data, dict):
                                _data[_csrf["field"]] = _tok
                            elif isinstance(_json, dict):
                                _json[_csrf["field"]] = _tok
                except Exception as _ce:
                    logger.info("csrf seed failed: %s", _ce)
            if _json is not None:
                kw["json"] = _json
            if _data is not None:
                kw["data"] = _data
            if _headers:
                kw["headers"] = _headers
            for _attempt in range(3):
                try:
                    sess.request(login.get("method", "POST").upper(), lurl, **kw)
                    if len(sess.cookies) > 0:
                        break
                except Exception:
                    pass
                import time as _t; _t.sleep(2)
            for _step in (login.get("post_login") or []):
                try:
                    import re as _re2
                    _surl = _step["url"].replace("{{base_url}}", origin)
                    _meth = _step.get("method", "GET").upper()
                    if _meth == "FORM_POST":
                        _pg = sess.get(_surl, timeout=15)
                        _fm = _re2.search(r"<form\b[^>]*>.*?</form>", _pg.text,
                                          _re2.DOTALL | _re2.IGNORECASE)
                        _html = _fm.group(0) if _fm else _pg.text
                        _am = _re2.search(r'<form\b[^>]*action="([^"]*)"',
                                          _html, _re2.IGNORECASE)
                        _post_url = _am.group(1) if (_am and _am.group(1)) else _surl
                        if _post_url.startswith("/"):
                            _post_url = origin + _post_url
                        elif not _post_url.startswith("http"):
                            _post_url = _surl
                        _fields: Dict[str, str] = {}
                        for _im in _re2.finditer(r"<input\b[^>]*>", _html,
                                                 _re2.IGNORECASE):
                            _tag = _im.group(0)
                            _nm = _re2.search(r'name="([^"]*)"', _tag)
                            if not _nm:
                                continue
                            _vm = _re2.search(r'value="([^"]*)"', _tag)
                            _fields[_nm.group(1)] = _vm.group(1) if _vm else ""
                        for _sm in _re2.finditer(
                                r'<select\b[^>]*name="([^"]*)"[^>]*>(.*?)</select>',
                                _html, _re2.DOTALL | _re2.IGNORECASE):
                            _sb = _sm.group(2)
                            _op = (_re2.search(
                                       r'<option\b[^>]*selected[^>]*value="([^"]*)"',
                                       _sb, _re2.IGNORECASE)
                                   or _re2.search(r'<option\b[^>]*value="([^"]*)"',
                                                  _sb, _re2.IGNORECASE))
                            _fields[_sm.group(1)] = _op.group(1) if _op else ""
                        sess.post(_post_url, data=_fields,
                                  headers={"Content-Type":
                                           "application/x-www-form-urlencoded"},
                                  timeout=15)
                    else:
                        sess.request(_meth, _surl, timeout=15)
                except Exception as _se:
                    logger.info("post_login step failed: %s", _se)
            for c in sess.cookies:
                cookies.append({"name": c.name, "value": c.value, "url": origin})
            if cookies:
                logger.info("frontend auth: %d cookie(s) for %s", len(cookies), origin)
        except Exception as e:
            logger.warning("frontend auth login failed for %s: %s", origin, e)
    if cookies:
        _AUTH_COOKIE_CACHE[origin] = cookies
    return cookies


def _login_cfg():
    try:
        import config as _cfg
        return getattr(_cfg, "FRONTEND_LOGIN", None)
    except Exception:
        return None


def _open_authed_page(browser: Any, url: str, viewport: dict):
    from urllib.parse import urlsplit
    login = _login_cfg()
    mode = (login or {}).get("mode", "cookie")
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"

    if login and mode == "basic":
        try:
            context = browser.new_context(
                viewport=viewport, ignore_https_errors=True,
                http_credentials={"username": login.get("user", ""),
                                  "password": login.get("password", "")})
            return context.new_page()
        except Exception as e:
            logger.warning("basic-auth context failed (%s); plain page", e)

    if login and mode == "browser":
        try:
            context = browser.new_context(viewport=viewport,
                                          ignore_https_errors=True)
            page = context.new_page()
            lurl = (login.get("url") or origin).replace("{{base_url}}", origin)
            page.goto(lurl, wait_until="domcontentloaded",
                      timeout=login.get("timeout_ms", 30000))
            page.wait_for_timeout(800)
            if login.get("user_selector"):
                page.fill(login["user_selector"], login.get("user", ""))
            if login.get("pass_selector"):
                page.fill(login["pass_selector"], login.get("password", ""))
            if login.get("submit_selector"):
                page.click(login["submit_selector"])
            wait_after = login.get("wait_after", "networkidle")
            try:
                if isinstance(wait_after, str) and wait_after.startswith("sel:"):
                    page.wait_for_selector(wait_after[4:],
                                           timeout=login.get("timeout_ms", 30000))
                else:
                    _w = min(login.get("timeout_ms", 30000), 8000) \
                        if wait_after == "networkidle" \
                        else login.get("timeout_ms", 30000)
                    page.wait_for_load_state(wait_after, timeout=_w)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            logger.info("frontend browser-login done for %s", origin)
            return page
        except Exception as e:
            logger.warning("browser login failed (%s); plain page", e)

    cookies = _auth_cookies(url)
    if cookies:
        try:
            context = browser.new_context(viewport=viewport,
                                          ignore_https_errors=True)
            context.add_cookies(cookies)
            return context.new_page()
        except Exception as e:
            logger.warning("authed context failed (%s); using plain page", e)
    return browser.new_page(viewport=viewport, ignore_https_errors=True)


def _resolve_url(url: str, ctx: Optional[Any]) -> str:
    if "{" not in url:
        return url
    out = url
    if ctx is not None:
        if hasattr(ctx, "resolve") and callable(getattr(ctx, "resolve")):
            try:
                resolved = ctx.resolve(url)
                if isinstance(resolved, str):
                    out = resolved
            except Exception:
                pass
        if isinstance(ctx, dict):
            for k, v in ctx.items():
                if isinstance(v, str):
                    out = out.replace("{{" + k + "}}", v)
    if "{{base_url}}" in out:
        base = _config_base_url()
        if base:
            out = out.replace("{{base_url}}", base)
    return out


def _resolve_ctx(ctx: Any) -> Any:
    if ctx is not None:
        return ctx
    try:
        from utils import context as _global_ctx
        return _global_ctx
    except Exception:
        return None


def _ctx_set(ctx: Any, key: str, value: Any) -> None:
    if ctx is None:
        return
    if hasattr(ctx, "set") and callable(getattr(ctx, "set")):
        try:
            ctx.set(key, value)
            return
        except Exception:
            pass
    try:
        ctx[key] = value
    except Exception:
        pass


def _ctx_append(ctx: Any, key: str, value: Any) -> None:
    if ctx is None:
        return
    if hasattr(ctx, "append") and callable(getattr(ctx, "append")):
        try:
            ctx.append(key, value)
            return
        except Exception:
            pass
    try:
        existing = ctx.get(key) if hasattr(ctx, "get") else ctx[key]
    except Exception:
        existing = None
    if existing is None:
        existing = []
    if not isinstance(existing, list):
        existing = [existing]
    existing.append(value)
    _ctx_set(ctx, key, existing)


class _BrowserResultShim(dict):

    @property
    def success(self) -> bool:
        return bool(self.get("passed", False))

    @property
    def message(self) -> str:
        return self.get("message", "")

    @property
    def data(self):
        return self.get("data", {})

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        if name in self:
            return self[name]
        if name in ("evidence", "data", "details", "context", "extra"):
            return {}
        if name in ("message", "error", "reason"):
            return ""
        if name in ("passed", "ok", "success", "skipped"):
            return False
        return None


def _make_result(passed: bool, message: str, **data: Any) -> Dict[str, Any]:
    return _BrowserResultShim(passed=passed, data=dict(data), message=message)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _sanitize_dom(html: str) -> str:
    import re as _re
    try:
        for _tag in ("style", "script", "noscript", "svg", "template"):
            html = _re.sub(r"<%s\b[^>]*>.*?</%s>" % (_tag, _tag), " ", html,
                           flags=_re.DOTALL | _re.IGNORECASE)
        html = _re.sub(r"<!--.*?-->", " ", html, flags=_re.DOTALL)
        html = _re.sub(r"<link\b[^>]*>", " ", html, flags=_re.IGNORECASE)
        html = _re.sub(r'\s(style|on\w+)="[^"]*"', "", html,
                       flags=_re.IGNORECASE)
        html = _re.sub(r"\s(style|on\w+)='[^']*'", "", html,
                       flags=_re.IGNORECASE)
        html = _re.sub(r'(src|href)="data:[^"]*"', r'\1="data:..."', html,
                       flags=_re.IGNORECASE)
        html = _re.sub(r"[ \t\r\f\v]+", " ", html)
        html = _re.sub(r"\n\s*\n+", "\n", html)
        return html.strip()
    except Exception:
        return html


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p18_render_dom(inputs: dict, ctx: Any = None) -> Dict[str, Any]:
    url_template = inputs.get("url")
    if not url_template:
        return _make_result(False, "p18_render_dom: missing 'url' input")

    import os as _os
    if not (_os.environ.get("LLM_API_KEY", "ak-default") or "").strip():
        return _make_result(True, "p18_render_dom SKIPPED (LLM_API_KEY blank)",
                            url=url_template, skipped=True)

    ctx = _resolve_ctx(ctx)
    url = _resolve_url(url_template, ctx)
    wait_until = inputs.get("wait_until", "networkidle")
    timeout_ms = int(inputs.get("timeout_ms", DEFAULT_TIMEOUT_MS))
    settle_ms = int(inputs.get("settle_ms", DEFAULT_SETTLE_MS))
    viewport = inputs.get("viewport", DEFAULT_VIEWPORT)
    max_chars = int(inputs.get("max_chars", DEFAULT_MAX_HTML_CHARS))
    wait_selector = inputs.get("wait_for_selector")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        logger.warning("playwright import failed: %s", e)
        return _make_result(False, f"p18_render_dom: playwright unavailable ({e})")

    try:
        with _BrowserWatchdog(75), sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = _open_authed_page(browser, url, viewport)
                try:
                    _ni = wait_until == "networkidle"
                    page.goto(url, wait_until=wait_until,
                              timeout=min(timeout_ms, 8000) if _ni else timeout_ms)
                except Exception as _ge:
                    logger.info("goto %s wait=%s failed (%s); retry domcontentloaded",
                                url, wait_until, _ge)
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=timeout_ms)
                    except Exception as e:
                        logger.info("wait_for_selector %s timed out: %s",
                                    wait_selector, e)
                page.wait_for_timeout(settle_ms)
                try:
                    _prev = -1
                    _stable = 0
                    for _ in range(24):
                        _cur = page.evaluate(
                            "document.documentElement.outerHTML.length")
                        if _cur > 0 and 0.99 * _prev <= _cur <= 1.01 * _prev:
                            _stable += 1
                            if _stable >= 2:
                                break
                        else:
                            _stable = 0
                        _prev = _cur
                        page.wait_for_timeout(500)
                except Exception as _he:
                    logger.info("hydration wait skipped: %s", _he)
                html_full = page.content()
            finally:
                browser.close()
    except Exception as e:
        logger.warning("p18_render_dom failed for %s: %s", url, e)
        return _make_result(False,
                            f"p18_render_dom: {type(e).__name__}: {e}",
                            url=url)

    html_clean = _sanitize_dom(html_full)
    truncated = len(html_clean) > max_chars
    html = html_clean[:max_chars]

    _ctx_set(ctx, "rendered_dom", html)
    _ctx_set(ctx, "rendered_dom_url", url)
    _ctx_set(ctx, "rendered_dom_length", len(html_full))

    passed = bool(html.strip()) and len(html) > 200
    return _make_result(passed,
                        f"rendered {len(html_full)} chars from {url}"
                        + (" (truncated)" if truncated else ""),
                        url=url, length=len(html_full),
                        returned_chars=len(html), truncated=truncated)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p19_screenshot(inputs: dict, ctx: Any = None) -> Dict[str, Any]:
    url_template = inputs.get("url")
    if not url_template:
        return _make_result(False, "p19_screenshot: missing 'url' input")

    import os as _os
    if not (_os.environ.get("LLM_API_KEY", "ak-default") or "").strip():
        return _make_result(True, "p19_screenshot SKIPPED (LLM_API_KEY blank)",
                            url=url_template, skipped=True)

    ctx = _resolve_ctx(ctx)
    url = _resolve_url(url_template, ctx)
    name = inputs.get("name", "shot")
    wait_until = inputs.get("wait_until", "networkidle")
    timeout_ms = int(inputs.get("timeout_ms", DEFAULT_TIMEOUT_MS))
    settle_ms = int(inputs.get("settle_ms", DEFAULT_SETTLE_MS))
    viewport = inputs.get("viewport", DEFAULT_VIEWPORT)
    full_page = bool(inputs.get("full_page", True))
    wait_selector = inputs.get("wait_for_selector")
    out_dir = inputs.get("out_dir", DEFAULT_SCREENSHOT_DIR)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    ts = int(time.time() * 1000)
    out_path = os.path.join(out_dir, f"{safe_name}_{ts}.png")
    os.makedirs(out_dir, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        logger.warning("playwright import failed: %s", e)
        return _make_result(False, f"p19_screenshot: playwright unavailable ({e})")

    try:
        with _BrowserWatchdog(75), sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                page = _open_authed_page(browser, url, viewport)
                try:
                    _ni = wait_until == "networkidle"
                    page.goto(url, wait_until=wait_until,
                              timeout=min(timeout_ms, 8000) if _ni else timeout_ms)
                except Exception as _ge:
                    logger.info("goto %s wait=%s failed (%s); retry domcontentloaded",
                                url, wait_until, _ge)
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=timeout_ms)
                    except Exception as e:
                        logger.info("wait_for_selector %s timed out: %s",
                                    wait_selector, e)
                page.wait_for_timeout(settle_ms)
                try:
                    html = _sanitize_dom(page.content())[:DEFAULT_MAX_HTML_CHARS]
                    _ctx_set(ctx, "rendered_dom", html)
                    _ctx_set(ctx, "rendered_dom_url", url)
                except Exception:
                    pass
                page.screenshot(path=out_path, full_page=full_page)
            finally:
                browser.close()
    except Exception as e:
        logger.warning("p19_screenshot failed for %s: %s", url, e)
        return _make_result(False,
                            f"p19_screenshot: {type(e).__name__}: {e}",
                            url=url)

    if not os.path.isfile(out_path):
        return _make_result(False,
                            f"p19_screenshot: PNG file not created at {out_path}",
                            url=url)
    size = os.path.getsize(out_path)
    if size < 1024:
        return _make_result(False,
                            f"p19_screenshot: PNG suspiciously small ({size} bytes)",
                            url=url, path=out_path, size_bytes=size)

    _ctx_append(ctx, "screenshots", out_path)
    _ctx_append(ctx, "screenshot_urls", url)
    return _make_result(True,
                        f"screenshot {size} bytes from {url} → {out_path}",
                        url=url, path=out_path, size_bytes=size,
                        full_page=full_page)


__all__ = ["p18_render_dom", "p19_screenshot"]
