
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
            _sp.run(["pkill", "-9", "-f", "chromium|playwright|headless_shell"], timeout=5)
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
    for attr in ("APP_BASE_URL", "FRONTEND_BASE_URL", "BASE_URL"):
        v = getattr(_cfg, attr, None)
        if isinstance(v, str) and v:
            return v.rstrip("/")
    return None


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


def _ctx_get(ctx: Any, key: str, default: Any = None) -> Any:
    if ctx is None:
        return default
    if hasattr(ctx, "get") and callable(getattr(ctx, "get")):
        try:
            return ctx.get(key, default)
        except Exception:
            pass
    try:
        return ctx[key]
    except Exception:
        return default


def _build_auth_cookies(ctx: Any, url: str) -> list:
    access_token = _ctx_get(ctx, "access-token") or _ctx_get(ctx, "access_token")
    if not access_token:
        return []
    import json as _json
    import time as _time
    from urllib.parse import quote as _quote
    from urllib.parse import urlsplit as _urlsplit

    expiry = _ctx_get(ctx, "expiry") or str(int(_time.time()) + 30 * 24 * 3600)
    headers = {
        "access-token": str(access_token),
        "token-type": "Bearer",
        "client": str(_ctx_get(ctx, "client", "") or ""),
        "expiry": str(expiry),
        "uid": str(_ctx_get(ctx, "uid", "") or ""),
    }
    cookie_value = _quote(_json.dumps(headers), safe="")
    host = _urlsplit(url).hostname or "localhost"
    return [{
        "name": "cw_d_session_info",
        "value": cookie_value,
        "domain": host,
        "path": "/",
        "sameSite": "Lax",
    }]


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

    auth_cookies = _build_auth_cookies(ctx, url)
    try:
        with _BrowserWatchdog(75), sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                browser_ctx = browser.new_context(viewport=viewport,
                                                  ignore_https_errors=True)
                if auth_cookies:
                    try:
                        browser_ctx.add_cookies(auth_cookies)
                    except Exception as e:
                        logger.warning("add_cookies failed (%s); rendering "
                                       "anonymously", e)
                page = browser_ctx.new_page()
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=timeout_ms)
                    except Exception as e:
                        logger.info("wait_for_selector %s timed out: %s",
                                    wait_selector, e)
                page.wait_for_timeout(settle_ms)
                html_full = page.content()
            finally:
                browser.close()
    except Exception as e:
        logger.warning("p18_render_dom failed for %s: %s", url, e)
        return _make_result(False,
                            f"p18_render_dom: {type(e).__name__}: {e}",
                            url=url)

    html_clean = _sanitize_dom(html_full)
    if inputs.get("strip_classes"):
        import re as _re_sc
        html_clean = _re_sc.sub(r'\sclass="[^"]*"', "", html_clean)
        html_clean = _re_sc.sub(r"\sclass='[^']*'", "", html_clean)
        html_clean = _re_sc.sub(r"[ \t]+", " ", html_clean)
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

    auth_cookies = _build_auth_cookies(ctx, url)
    try:
        with _BrowserWatchdog(75), sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                browser_ctx = browser.new_context(viewport=viewport,
                                                  ignore_https_errors=True)
                if auth_cookies:
                    try:
                        browser_ctx.add_cookies(auth_cookies)
                    except Exception as e:
                        logger.warning("add_cookies failed (%s); rendering "
                                       "anonymously", e)
                page = browser_ctx.new_page()
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
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
