from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
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
        }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
ctx: Dict[str, Any] = {}
ctx.setdefault("auth_token_by_role", {})
ctx.setdefault("auth_role", None)
ctx.setdefault("entities", {})

try:
    from . import config as _cfg
except Exception:
    import config as _cfg
for _role, _info in getattr(_cfg, "TEST_USERS", {}).items():
    if isinstance(_info, dict):
        for _field, _value in _info.items():
            if isinstance(_value, (str, int, float, bool)):
                ctx.setdefault(f"{_role}_{_field}", _value)
                ctx.setdefault(f"eval_{_role}_{_field}", _value)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def substitute(value: Any, lookup: Optional[Dict[str, Any]] = None) -> Any:
    src = lookup if lookup is not None else ctx

    if isinstance(value, str):
        def repl(m):
            key = m.group(1)
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
def resolve_auth_headers(auth_mode: Optional[str]) -> Dict[str, str]:
    if not auth_mode:
        return {}
    headers: Dict[str, str] = {}
    if auth_mode == "bearer_eval_key":
        token = _read_token_file(cfg.EVAL_API_KEY_FILE)
        if token:
            ctx["eval_api_key"] = token
            headers["Authorization"] = f"Bearer {token}"
    elif auth_mode == "basic_eval_plugin_token":
        raw = ctx.get("eval_plugin_token_raw") or _read_token_file(cfg.EVAL_PLUGIN_TOKEN_FILE)
        if raw and ":" in raw:
            ctx["eval_plugin_token_raw"] = raw
            import base64
            encoded = base64.b64encode(raw.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
    elif auth_mode.startswith("session_eval_"):
        cookie = ctx.get(auth_mode)
        if cookie:
            headers["Cookie"] = cookie
    return headers


def _read_token_file(path: str) -> str:
    r = docker_exec(cfg.APP_CONTAINER, f"cat {path} 2>/dev/null || true",
                     expect_success=False, timeout=5)
    return (r.get("stdout") or "").strip()


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
    raw_body: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    form: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    base_url: Optional[str] = None,
    follow_redirects: bool = True,
    auth_mode: Optional[str] = None,
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
    auth_hdrs = resolve_auth_headers(auth_mode)
    for k, v in auth_hdrs.items():
        hdrs.setdefault(k, v)

    serialised: Optional[Any] = None
    if raw_body is not None:
        serialised = raw_body
        hdrs.setdefault("Content-Type", "application/json")
    elif form is not None:
        serialised = form
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        s, is_json = _fmt_body(body)
        serialised = s
        if is_json:
            hdrs.setdefault("Content-Type", "application/json")

    t0 = time.perf_counter()
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=hdrs,
            data=serialised,
            params=params,
            timeout=timeout or cfg.HTTP_TIMEOUT,
            allow_redirects=follow_redirects,
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
            "headers": {k.lower(): v for k, v in resp.headers.items()},
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


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def clickhouse_query(sql: str, timeout: Optional[int] = None) -> Dict[str, Any]:
    url = cfg.CH_BASE_URL
    params = {"database": cfg.CH_DATABASE, "user": cfg.CH_USER}
    if cfg.CH_PASSWORD:
        params["password"] = cfg.CH_PASSWORD
    if not sql.strip().lower().endswith("format json"):
        sql_with_format = sql.strip().rstrip(";") + "\nFORMAT JSON"
    else:
        sql_with_format = sql
    t0 = time.perf_counter()
    try:
        resp = requests.post(url, data=sql_with_format, params=params,
                                timeout=timeout or cfg.CH_HTTP_TIMEOUT)
        elapsed = int((time.perf_counter() - t0) * 1000)
        if resp.status_code != 200:
            return {
                "rows": [],
                "row_count": 0,
                "error": f"CH HTTP {resp.status_code}: {resp.text[:300]}",
                "response_time_ms": elapsed,
                "sql": sql[:300],
            }
        try:
            data = resp.json()
        except (ValueError, json.JSONDecodeError):
            return {
                "rows": [],
                "row_count": 0,
                "error": f"non-JSON CH response: {resp.text[:200]}",
                "response_time_ms": elapsed,
                "sql": sql[:300],
            }
        rows = data.get("data", [])
        return {
            "rows": rows,
            "row_count": len(rows),
            "response_time_ms": elapsed,
            "sql": sql[:300],
        }
    except requests.RequestException as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return {
            "rows": [],
            "row_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "response_time_ms": elapsed,
            "sql": sql[:300],
        }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def docker_exec(container: str, command: str, expect_success: bool = True,
                  timeout: int = 60) -> Dict[str, Any]:
    cmd = ["docker", "exec", container, "sh", "-c", command]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        success = (r.returncode == 0) if expect_success else True
        return {
            "command": command,
            "container": container,
            "returncode": r.returncode,
            "stdout": r.stdout[:16000],
            "stderr": r.stderr[:8000],
            "success": success,
        }
    except subprocess.TimeoutExpired:
        return {"command": command, "container": container, "returncode": -1,
                  "stdout": "", "stderr": f"timeout after {timeout}s", "success": False}
    except FileNotFoundError as e:
        return {"command": command, "container": container, "returncode": -1,
                  "stdout": "", "stderr": str(e), "success": False}


def shell_exec(command: str, timeout: int = 60) -> Dict[str, Any]:
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return {
            "command": command,
            "returncode": r.returncode,
            "stdout": r.stdout[:16000],
            "stderr": r.stderr[:8000],
            "success": r.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": command, "returncode": -1, "stdout": "",
                  "stderr": f"timeout after {timeout}s", "success": False}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
JSONPATH_TOKEN = re.compile(r"(\.[A-Za-z_][\w]*)|(\[(-?\d+)\])|(\['([^']+)'\])|(\[\"([^\"]+)\"\])")


def json_get(data: Any, path: str, default: Any = None) -> Any:
    if path == "$" or path == "":
        return data
    if not path.startswith("$"):
        path = "$." + path.lstrip(".")

    if "[*]" in path:
        parts = path.split("[*]", 1)
        prefix, suffix = parts[0], parts[1]
        prefix_val = json_get(data, prefix, default=[])
        if not isinstance(prefix_val, list):
            return default
        if not suffix:
            return prefix_val
        return [json_get(item, "$" + suffix, default) for item in prefix_val]

    filter_match = re.search(r"\[\?\(@\.(\w+)==[\"']?([^\"']+)[\"']?\)\]", path)
    if filter_match:
        before = path[:filter_match.start()]
        after = path[filter_match.end():]
        before_val = json_get(data, before, default=[])
        key, want = filter_match.group(1), filter_match.group(2)
        if not isinstance(before_val, list):
            return default
        try:
            want_typed = type(before_val[0].get(key))(want) if before_val and isinstance(before_val[0], dict) and key in before_val[0] else want
        except (TypeError, ValueError):
            want_typed = want
        filtered = [it for it in before_val if isinstance(it, dict) and (it.get(key) == want or str(it.get(key)) == str(want))]
        if not filtered:
            return default
        if not after:
            return filtered if len(filtered) > 1 else filtered[0]
        return json_get(filtered[0], "$" + after, default)

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
        elif m.group(5):
            key = m.group(5)
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
        elif m.group(7):
            key = m.group(7)
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return default
    return cur


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def print_result(r: NodeResult) -> None:
    badge = {
        "PASSED": "[OK] ",
        "PARTIAL": "[PT] ",
        "FAILED": "[XX] ",
        "SKIPPED_DEPENDENCY": "[SD] ",
        "SKIPPED_LLM": "[SL] ",
        "ERROR": "[ER] ",
    }.get(r.status, "[??] ")
    logger.info(f"{badge} {r.node_id:55s} {r.status:20s} "
                  f"{r.score:>6.2f}/{r.maxScore:<6.0f} {r.pct:>6.2f}%  ({r.elapsed_ms}ms) "
                  f"{r.message[:80]}")
