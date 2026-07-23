
from __future__ import annotations

import dataclasses
import json
import os
import re
import shlex
import subprocess
import time
import typing as t
from dataclasses import dataclass, field

import requests

from . import config

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


@dataclass
class PrimitiveResult:

    primitive: str
    passed: bool
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    message: str = ""
    elapsed_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class NodeResult:

    node_id: str
    status: str
    score: float
    max_score: float
    category: str
    subcategory: str
    method: str
    message: str = ""
    primitive_results: list[dict] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0
    complexity_tier: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _normalize_url(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    if not path_or_url.startswith("/"):
        path_or_url = "/" + path_or_url
    return f"{config.APP_BASE_URL}{path_or_url}"


def http_request(
    method: str,
    path_or_url: str,
    *,
    headers: dict | None = None,
    json_body: t.Any = None,
    data: t.Any = None,
    params: dict | None = None,
    cookies: dict | None = None,
    timeout: float | None = None,
    allow_redirects: bool = False,
) -> dict:

    url = _normalize_url(path_or_url)
    final_headers = dict(headers or {})

    started = time.perf_counter()
    out: dict = {
        "method": method.upper(),
        "url": url,
        "status_code": 0,
        "headers": {},
        "body": None,
        "text": "",
        "elapsed_ms": 0.0,
        "ok": False,
        "error": None,
    }

    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=final_headers,
            json=json_body if data is None else None,
            data=data,
            params=params,
            cookies=cookies,
            timeout=timeout if timeout is not None else config.HTTP_TIMEOUT_SEC,
            allow_redirects=allow_redirects,
        )
    except requests.RequestException as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["elapsed_ms"] = (time.perf_counter() - started) * 1000
        return out

    elapsed_ms = (time.perf_counter() - started) * 1000
    out["elapsed_ms"] = elapsed_ms
    out["status_code"] = resp.status_code
    out["headers"] = dict(resp.headers)
    out["text"] = resp.text
    try:
        out["body"] = resp.json()
    except (ValueError, json.JSONDecodeError):
        out["body"] = None
    out["ok"] = True
    out["size"] = len(resp.content)
    return out


def http_get(path: str, **kwargs) -> dict:
    return http_request("GET", path, **kwargs)


def http_post(path: str, **kwargs) -> dict:
    return http_request("POST", path, **kwargs)


def http_patch(path: str, **kwargs) -> dict:
    return http_request("PATCH", path, **kwargs)


def http_put(path: str, **kwargs) -> dict:
    return http_request("PUT", path, **kwargs)


def http_delete(path: str, **kwargs) -> dict:
    return http_request("DELETE", path, **kwargs)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def shell_exec(
    command: str | list[str],
    *,
    timeout: float = 60.0,
    cwd: str | None = None,
    env: dict | None = None,
    shell: bool | None = None,
) -> dict:

    started = time.perf_counter()
    out: dict = {
        "command": command,
        "exit_code": -1,
        "stdout": "",
        "stderr": "",
        "elapsed_ms": 0.0,
        "ok": False,
        "error": None,
    }
    try:
        if isinstance(command, str) and shell is None:
            shell_flag = True
            cmd_arg = command
        elif isinstance(command, str):
            shell_flag = bool(shell)
            cmd_arg = command if shell_flag else shlex.split(command)
        else:
            shell_flag = bool(shell)
            cmd_arg = command

        proc = subprocess.run(
            cmd_arg,
            shell=shell_flag,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out["exit_code"] = proc.returncode
        out["stdout"] = proc.stdout
        out["stderr"] = proc.stderr
        out["ok"] = True
    except subprocess.TimeoutExpired as exc:
        out["error"] = f"TimeoutExpired: {exc}"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    out["elapsed_ms"] = (time.perf_counter() - started) * 1000
    return out


def docker_exec(
    container: str,
    command: str | list[str],
    *,
    timeout: float = 90.0,
) -> dict:

    if isinstance(command, list):
        full = ["docker", "exec", container, *command]
    else:
        full = ["docker", "exec", container, "sh", "-lc", command]
    return shell_exec(full, timeout=timeout, shell=False)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def db_query(sql: str, params: tuple | dict | None = None) -> dict:

    out: dict = {
        "sql": sql,
        "rows": [],
        "rowcount": 0,
        "ok": False,
        "error": None,
    }
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError as exc:
        out["error"] = f"psycopg2 not installed: {exc}"
        return out

    try:
        with psycopg2.connect(**config.db_connection_kwargs()) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                if cur.description:
                    out["rows"] = [dict(r) for r in cur.fetchall()]
                    out["rowcount"] = cur.rowcount
                else:
                    out["rowcount"] = cur.rowcount
            conn.commit()
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def db_table_exists_in_pg(table_name: str) -> bool:

    res = db_query(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=%s LIMIT 1",
        (table_name,),
    )
    return res["ok"] and res["rowcount"] > 0


def db_columns_of(table_name: str) -> list[str]:
    res = db_query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s",
        (table_name,),
    )
    if not res["ok"]:
        return []
    return [r["column_name"] for r in res["rows"]]


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


_PATH_RE = re.compile(r"\$|\.|\[(\d+)\]|([a-zA-Z_][a-zA-Z0-9_-]*)")


def get_json_path(obj: t.Any, path: str) -> t.Any:

    if path in ("", "$"):
        return obj

    if not path.startswith("$"):
        path = "$." + path.lstrip(".")

    cur = obj
    tokens: list[t.Any] = []
    i = 1
    while i < len(path):
        ch = path[i]
        if ch == ".":
            i += 1
            continue
        if ch == "[":
            j = path.find("]", i)
            if j < 0:
                return None
            inside = path[i + 1 : j]
            if inside.isdigit() or (inside.startswith("-") and inside[1:].isdigit()):
                tokens.append(int(inside))
            else:
                tokens.append(inside.strip("'\""))
            i = j + 1
            continue
        j = i
        while j < len(path) and path[j] not in (".", "["):
            j += 1
        tokens.append(path[i:j])
        i = j

    for tok in tokens:
        if cur is None:
            return None
        if isinstance(tok, int):
            if isinstance(cur, list):
                if -len(cur) <= tok < len(cur):
                    cur = cur[tok]
                else:
                    return None
            else:
                return None
        else:
            if isinstance(cur, dict):
                cur = cur.get(tok)
            else:
                return None
    return cur


_TEMPLATE_RE = re.compile(r"\$\{([A-Za-z0-9_\.]+)\}")


def render_value(val: t.Any, context: dict) -> t.Any:

    if isinstance(val, str):
        m_full = re.fullmatch(r"\$\{([A-Za-z0-9_\.]+)\}", val)
        if m_full:
            key = m_full.group(1)
            return _resolve_context_key(key, context, default=val)
        def repl(m: re.Match) -> str:
            key = m.group(1)
            v = _resolve_context_key(key, context, default="${" + key + "}")
            return str(v)

        return _TEMPLATE_RE.sub(repl, val)

    if isinstance(val, dict):
        return {k: render_value(v, context) for k, v in val.items()}
    if isinstance(val, list):
        return [render_value(v, context) for v in val]
    return val


def _resolve_context_key(key: str, context: dict, default: t.Any = None) -> t.Any:
    if "." in key:
        head, *rest = key.split(".")
        cur = context.get(head, default)
        for r in rest:
            if isinstance(cur, dict):
                cur = cur.get(r, default)
            else:
                return default
        return cur
    return context.get(key, default)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def print_result(node_result: NodeResult) -> None:
    icon = {
        "PASSED": "[PASS]",
        "FAILED": "[FAIL]",
        "SKIPPED_DEPENDENCY": "[SKIP-DEP]",
        "SKIPPED_TEARDOWN": "[SKIP-TD]",
        "ERROR": "[ERR ]",
    }.get(node_result.status, "[ ?  ]")
    print(
        f"{icon} {node_result.node_id:<55} "
        f"{node_result.score:>5.1f}/{node_result.max_score:<5.1f} "
        f"({node_result.category}/{node_result.subcategory})"
        + (f" — {node_result.message}" if node_result.message else "")
    )


def save_results(results: dict, output_path: str | os.PathLike) -> None:
    output_path = str(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=_json_default)


def _json_default(o: t.Any) -> t.Any:
    if dataclasses.is_dataclass(o):
        return dataclasses.asdict(o)
    if isinstance(o, (set, frozenset)):
        return list(o)
    if isinstance(o, bytes):
        try:
            return o.decode("utf-8", errors="replace")
        except Exception:
            return repr(o)
    return str(o)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def safe_int(x: t.Any, default: int | None = None) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def category_to_filename(category: str) -> str:

    if re.match(r"^[a-z][A-Z]", category):
        category = category[0].upper() + category[1:]

    parts = []
    for seg in category.split("_"):
        if not seg:
            continue
        if seg.isupper():
            parts.append(seg.lower())
            continue
        s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", seg)
        s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
        parts.append(s.lower())

    final = "_".join(parts).replace("/", "_")
    final = re.sub(r"_+", "_", final).strip("_")
    return f"test_{final}.py"


def category_to_modname(category: str) -> str:
    return category_to_filename(category)[:-3]
