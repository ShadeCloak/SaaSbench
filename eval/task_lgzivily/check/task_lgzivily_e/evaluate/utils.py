from __future__ import annotations

import dataclasses
import json
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from . import config


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class PrimitiveResult:
    primitive: str
    passed: bool
    message: str = ""
    data: dict | None = None
    duration_ms: int = 0


@dataclasses.dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    maxScore: float
    category: str
    subcategory: str = ""
    method: str = "binary"
    message: str = ""
    primitive_results: list[PrimitiveResult] = dataclasses.field(default_factory=list)
    evidence: dict = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def http_request(method: str, url: str, *,
                 headers: dict | None = None,
                 params: dict | None = None,
                 body: dict | str | None = None,
                 body_form: dict | None = None,
                 timeout: int | None = None,
                 allow_redirects: bool = True) -> requests.Response:
    timeout = timeout or config.HTTP_TIMEOUT_SEC
    kwargs: dict[str, Any] = {
        "headers": dict(headers or {}),
        "params": params,
        "timeout": timeout,
        "allow_redirects": allow_redirects,
    }
    if body_form is not None:
        kwargs["data"] = body_form
    elif body is not None:
        if isinstance(body, (dict, list)):
            kwargs["json"] = body
        else:
            kwargs["data"] = body
    return requests.request(method.upper(), url, **kwargs)


def http_response_summary(resp: requests.Response, max_body: int = 500) -> dict:
    try:
        body_preview = resp.text[:max_body]
    except Exception:
        body_preview = "<unreadable>"
    return {
        "url": resp.url,
        "method": resp.request.method if resp.request else "?",
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "body_preview": body_preview,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def docker_exec(container: str, command: str, *,
                workdir: str | None = None,
                timeout: int | None = None) -> tuple[int, str, str]:
    timeout = timeout or config.DOCKER_EXEC_TIMEOUT_SEC
    cmd = ["docker", "exec"]
    if workdir:
        cmd += ["-w", workdir]
    cmd += [container, "sh", "-c", command]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return 127, "", "docker binary not found"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def db_connect():
    import pymysql
    return pymysql.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8mb4", autocommit=True,
        connect_timeout=10, read_timeout=30, write_timeout=30,
        cursorclass=pymysql.cursors.DictCursor,
    )


def db_query(sql: str, params: tuple | None = None) -> list[dict]:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return list(cur.fetchall())


def db_exec(sql: str, params: tuple | None = None) -> int:
    with db_connect() as conn:
        with conn.cursor() as cur:
            n = cur.execute(sql, params or ())
            return n


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def jsonpath_get(obj: Any, path: str) -> Any:
    if not path or path == "$":
        return obj
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]
    cur = obj
    parts: list[tuple[str, str]] = []
    i = 0
    while i < len(path):
        if path[i] == "[":
            j = path.index("]", i)
            inner = path[i + 1:j]
            parts.append(("idx", inner))
            i = j + 1
            if i < len(path) and path[i] == ".":
                i += 1
        else:
            j = i
            while j < len(path) and path[j] not in ".[":
                j += 1
            parts.append(("key", path[i:j]))
            i = j
            if i < len(path) and path[i] == ".":
                i += 1
    for kind, val in parts:
        if cur is None:
            return None
        if kind == "key":
            if isinstance(cur, dict):
                cur = cur.get(val)
            else:
                return None
        elif kind == "idx":
            if val == "*":
                return cur
            try:
                idx = int(val)
            except ValueError:
                return None
            if isinstance(cur, list) and 0 <= idx < len(cur):
                cur = cur[idx]
            else:
                return None
    return cur


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def save_results(results: list[NodeResult], output_path: Path) -> None:
    payload = []
    for r in results:
        payload.append({
            "node_id": r.node_id,
            "status": r.status,
            "score": r.score,
            "maxScore": r.maxScore,
            "category": r.category,
            "subcategory": r.subcategory,
            "method": r.method,
            "message": r.message[:500] if r.message else "",
            "primitive_results": [
                {
                    "primitive": p.primitive,
                    "passed": p.passed,
                    "message": p.message[:300] if p.message else "",
                    "duration_ms": p.duration_ms,
                }
                for p in r.primitive_results
            ],
            "evidence": r.evidence,
        })
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def print_node(r: NodeResult) -> None:
    icon = "✓" if r.score == r.maxScore else ("✗" if r.score == 0 else "≈")
    print(f"  {icon} [{r.status:6s}] {r.node_id:50s} "
          f"{r.score:>5.1f}/{r.maxScore:<5.1f} ({r.category})")
    if r.message and r.score < r.maxScore:
        print(f"        {r.message[:120]}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def substitute_ctx(value: Any, ctx: dict) -> Any:
    if isinstance(value, str):
        out = value
        i = 0
        while True:
            j = out.find("{{ctx.", i)
            if j < 0:
                break
            k = out.find("}}", j)
            if k < 0:
                break
            key = out[j + 6:k]
            replacement = str(ctx.get(key, ""))
            out = out[:j] + replacement + out[k + 2:]
            i = j + len(replacement)
        return out
    if isinstance(value, dict):
        return {k: substitute_ctx(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_ctx(v, ctx) for v in value]
    return value
