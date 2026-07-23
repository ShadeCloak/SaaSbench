from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from . import config as cfg

logger = logging.getLogger("evaluate.utils")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(h)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
@dataclass
class PrimitiveResult:
    primitive: str
    passed: bool
    score_hint: float
    evidence: Dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primitive": self.primitive,
            "passed": self.passed,
            "score_hint": round(self.score_hint, 4),
            "message": self.message[:500],
            "evidence_keys": sorted(self.evidence.keys()),
        }


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    maxScore: float
    category: str
    subcategory: str
    method: str
    complexity_tier: str
    chain_results: List[Dict[str, Any]] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    elapsed_ms: int = 0

    @property
    def pct(self) -> float:
        return 0.0 if self.maxScore == 0 else round(100 * self.score / self.maxScore, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "score": round(self.score, 3),
            "maxScore": self.maxScore,
            "pct": self.pct,
            "category": self.category,
            "subcategory": self.subcategory,
            "method": self.method,
            "complexity_tier": self.complexity_tier,
            "elapsed_ms": self.elapsed_ms,
            "message": self.message[:1000],
            "chain_results": self.chain_results,
            "evidence_keys": sorted(self.evidence.keys()),
        }


# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
ctx: Dict[str, Any] = {}


def seed_static_ctx() -> None:
    ctx.setdefault("auth_token_by_role", {})
    ctx.setdefault("entities", {})
    ctx["ts"] = str(int(time.time()))
    ctx["app_container"]   = cfg.APP_CONTAINER
    ctx["db_container"]    = cfg.DB_CONTAINER
    ctx["cache_container"] = cfg.CACHE_CONTAINER
    ctx["APP_CONTAINER"]   = cfg.APP_CONTAINER
    ctx["DB_CONTAINER"]    = cfg.DB_CONTAINER
    ctx["CACHE_CONTAINER"] = cfg.CACHE_CONTAINER
    ctx["app_base_url"] = cfg.APP_BASE_URL
    ctx["api_base_url"] = cfg.API_BASE_URL
    ctx["db_host"]      = cfg.DB_HOST
    ctx["db_port"]      = cfg.DB_PORT
    ctx["db_name"]      = cfg.DB_NAME
    ctx["db_user"]      = cfg.DB_USER
    ctx["cache_host"]   = cfg.CACHE_HOST
    ctx["cache_port"]   = cfg.CACHE_PORT
    for role, info in cfg.TEST_USERS.items():
        for k, v in info.items():
            if isinstance(v, (str, int, bool)):
                ctx[f"{role}_{k}"] = v
    ctx["token_prefix"] = cfg.TOKEN_PREFIX


seed_static_ctx()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def substitute(value: Any, lookup: Optional[Dict[str, Any]] = None) -> Any:
    import secrets as _sec
    import random as _rand
    src = lookup if lookup is not None else ctx

    if isinstance(value, str):
        stripped = value.strip()
        m_full = PLACEHOLDER_RE.fullmatch(stripped)
        if m_full:
            key = m_full.group(1)
            if key == "rand":
                return _sec.token_hex(4)
            if key == "rand4":
                return _rand.randint(1000, 9999)
            if key in src:
                return src[key]
            return value
        def repl(m):
            key = m.group(1)
            if key == "rand":
                return _sec.token_hex(4)
            if key == "rand4":
                return str(_rand.randint(1000, 9999))
            if key in src:
                return str(src[key])
            return m.group(0)
        return PLACEHOLDER_RE.sub(repl, value)

    if isinstance(value, list):
        return [substitute(v, src) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, src) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _fmt_body(body: Any) -> Tuple[Optional[str], bool]:
    if body is None:
        return None, False
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False), True
    return str(body), False


def http_request(
    method: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    body: Any = None,
    timeout: Optional[int] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    method = method.upper()
    base = base_url or cfg.APP_BASE_URL
    if path.startswith("http"):
        url = path
    elif path.startswith("/"):
        url = base.rstrip("/") + path
    else:
        url = base.rstrip("/") + "/" + path

    hdrs = dict(headers or {})
    serialised, is_json = _fmt_body(body)
    if is_json:
        hdrs.setdefault("Content-Type", "application/json")

    if "Authorization" not in hdrs and ctx.get("auth_token"):
        hdrs["Authorization"] = f"Token {ctx['auth_token']}"

    t0 = time.perf_counter()
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=hdrs,
            data=serialised,
            timeout=timeout or cfg.HTTP_TIMEOUT,
            allow_redirects=True,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        text = resp.text
        ctype = resp.headers.get("content-type", "")
        body_obj: Any = None
        if "application/json" in ctype.lower():
            try:
                body_obj = resp.json()
            except (ValueError, json.JSONDecodeError):
                body_obj = text
        else:
            body_obj = text
        return {
            "url": url,
            "method": method,
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": body_obj,
            "body_text": text[:8000],
            "response_time_ms": elapsed,
        }
    except requests.RequestException as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "url": url,
            "method": method,
            "status_code": 0,
            "headers": {},
            "body": None,
            "body_text": "",
            "response_time_ms": elapsed,
            "error": f"{type(exc).__name__}: {exc}",
        }


def http_get(path: str, **kw) -> Dict[str, Any]:
    return http_request("GET", path, **kw)


def http_post(path: str, body: Any = None, **kw) -> Dict[str, Any]:
    return http_request("POST", path, body=body, **kw)


def http_patch(path: str, body: Any = None, **kw) -> Dict[str, Any]:
    return http_request("PATCH", path, body=body, **kw)


def http_delete(path: str, **kw) -> Dict[str, Any]:
    return http_request("DELETE", path, **kw)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_SHELL_CACHE: Dict[str, str] = {}


def _pick_shell(container: str) -> str:
    forced = os.environ.get("DOCKER_EXEC_SHELL")
    if forced in ("sh", "bash"):
        return forced
    if container in _SHELL_CACHE:
        return _SHELL_CACHE[container]
    try:
        r = subprocess.run(
            ["docker", "exec", container, "sh", "-c", "command -v bash >/dev/null 2>&1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        shell = "bash" if r.returncode == 0 else "sh"
    except Exception:
        shell = "sh"
    _SHELL_CACHE[container] = shell
    return shell


def docker_exec(container: str, command: str, expect_success: bool = True, timeout: int = 60) -> Dict[str, Any]:
    shell = _pick_shell(container)
    cmd = ["docker", "exec", container, shell, "-c", command]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        success = (r.returncode == 0) if expect_success else True
        return {
            "command": command,
            "container": container,
            "shell_used": shell,
            "returncode": r.returncode,
            "stdout": r.stdout[:16000],
            "stderr": r.stderr[:8000],
            "success": success,
        }
    except subprocess.TimeoutExpired:
        return {"command": command, "container": container, "shell_used": shell, "returncode": -1, "stdout": "", "stderr": f"timeout after {timeout}s", "success": False}
    except FileNotFoundError as e:
        return {"command": command, "container": container, "shell_used": shell, "returncode": -1, "stdout": "", "stderr": str(e), "success": False}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
JSONPATH_TOKEN = re.compile(r"(\.[A-Za-z_][\w]*)|(\[(-?\d+)\])")


def json_get(data: Any, path: str, default: Any = None) -> Any:
    if path == "$" or path == "":
        return data
    if not path.startswith("$"):
        path = "$." + path.lstrip(".")
    cur = data
    rest = path[1:]
    for m in JSONPATH_TOKEN.finditer(rest):
        if m.group(1):
            key = m.group(1)[1:]
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
        elif m.group(3) is not None:
            idx = int(m.group(3))
            if isinstance(cur, list) and -len(cur) <= idx < len(cur):
                cur = cur[idx]
            else:
                return default
    return cur


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_ASCII_BADGES = {
    "PASSED": "[OK]",
    "FAILED": "[XX]",
    "SKIPPED_DEPENDENCY": "[->]",
    "SKIPPED_LLM": "[L?]",
    "ERROR": "[!!]",
}
_UNICODE_BADGES = {
    "PASSED": "\u2713",
    "FAILED": "\u2717",
    "SKIPPED_DEPENDENCY": "\u2192",
    "SKIPPED_LLM": "\u26a0",
    "ERROR": "\u26a0",
}


def _use_ascii() -> bool:
    if os.environ.get("EVALUATE_ASCII_ONLY") == "1":
        return True
    enc = (sys.stdout.encoding or "").lower() if sys.stdout else ""
    return enc not in ("utf-8", "utf8")


def print_result(r: NodeResult) -> None:
    badges = _ASCII_BADGES if _use_ascii() else _UNICODE_BADGES
    badge = badges.get(r.status, "?")
    logger.info(f"{badge} {r.node_id:50s} {r.status:20s} {r.score:>6.2f}/{r.maxScore:<6.0f} {r.pct:>6.2f}%  ({r.elapsed_ms}ms) {r.message[:80]}")
