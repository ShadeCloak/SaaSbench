from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

import psycopg2
import psycopg2.extras
import requests

import config

logger = logging.getLogger("eval")



@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float = 0.0
    max_score: float = 0.0
    evidence: dict = field(default_factory=dict)
    message: str = ""


@dataclass
class ChainResult:
    all_passed: bool = True
    pass_count: int = 0
    total_count: int = 0
    evidence: dict = field(default_factory=dict)
    captured: dict = field(default_factory=dict)

    @property
    def pass_ratio(self) -> float:
        return self.pass_count / self.total_count if self.total_count else 0.0



class EvalContext:

    def __init__(self):
        self.auth_tokens: dict[str, str] = {}
        self.active_role: str | None = None
        self.captured: dict[str, Any] = {}
        self.last_response: requests.Response | None = None
        self.last_response_json: Any = None
        self.webhook_port: int = config.WEBHOOK_LISTEN_PORT
        self.captured["webhook_port"] = str(self.webhook_port)

    @property
    def current_token(self) -> str | None:
        if self.active_role:
            return self.auth_tokens.get(self.active_role)
        return self.auth_tokens.get("admin")

    def resolve(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._resolve_str(value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    def _resolve_str(self, s):
        import re
        m = re.fullmatch(r"\{\{(\w+)\}\}", s)
        if m:
            val = self.captured.get(m.group(1))
            return val if val is not None else s
        def _replace(m):
            key = m.group(1)
            val = self.captured.get(key)
            if val is None:
                return m.group(0)
            return str(val)
        return re.sub(r"\{\{(\w+)\}\}", _replace, s)



def http_request(
    method: str,
    path: str,
    *,
    ctx: EvalContext,
    body: Any = None,
    headers: dict | None = None,
    timeout: int | None = None,
) -> requests.Response:
    url = path if path.startswith("http") else f"{config.BASE_URL}{path}"
    url = ctx.resolve(url)

    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if ctx.current_token and not (headers and "X-Auth-Token" in headers):
        hdrs["X-Auth-Token"] = ctx.current_token
    if headers:
        resolved = ctx.resolve(headers)
        hdrs.update(resolved)

    resolved_body = ctx.resolve(body) if body else None
    tout = timeout or config.HTTP_TIMEOUT

    try:
        resp = requests.request(
            method, url,
            json=resolved_body,
            headers=hdrs,
            timeout=tout,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        logger.warning("HTTP %s %s failed: %s", method, url, exc)
        raise

    ctx.last_response = resp
    try:
        ctx.last_response_json = resp.json()
    except (ValueError, json.JSONDecodeError):
        ctx.last_response_json = None

    return resp



def db_connect():
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        connect_timeout=config.DB_QUERY_TIMEOUT,
    )


def db_query(sql: str, ctx: EvalContext | None = None) -> list[dict]:
    resolved = ctx.resolve(sql) if ctx else sql
    try:
        conn = db_connect()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(resolved)
            if cur.description:
                rows = [dict(r) for r in cur.fetchall()]
            else:
                rows = []
        conn.close()
        return rows
    except Exception as exc:
        logger.warning("DB query failed: %s — %s", resolved[:120], exc)
        return []


def db_query_with_retry(sql: str, expected: dict, ctx: EvalContext, retry_ms: int = 5000) -> list[dict]:
    deadline = time.time() + retry_ms / 1000.0
    rows = []
    while time.time() < deadline:
        rows = db_query(sql, ctx)
        if rows and _row_matches(rows[0], expected):
            return rows
        time.sleep(1)
    return rows


def _row_matches(row: dict, expected: dict) -> bool:
    for k, v in expected.items():
        actual = row.get(k)
        if isinstance(v, dict) and "op" in v:
            if not _compare_op(actual, v):
                return False
        elif actual != v:
            if isinstance(v, bool) and actual in (0, 1):
                if bool(actual) != v:
                    return False
            elif actual != v:
                return False
    return True


def _compare_op(actual, spec: dict) -> bool:
    op = spec.get("op", "==")
    val = spec.get("value", spec.get("expected"))
    if op == ">=":
        return actual is not None and actual >= val
    if op == "<=":
        return actual is not None and actual <= val
    if op == ">":
        return actual is not None and actual > val
    if op == "not_null":
        return actual is not None
    return actual == val



def docker_exec(command: str, ctx: EvalContext, timeout: int = 60) -> tuple[int, str, str]:
    resolved = ctx.resolve(command)
    container = config.APP_CONTAINER
    docker_dir = config.DOCKER_COMPOSE_DIR

    use_script = '"' in resolved and "'" in resolved

    if use_script:
        import base64
        encoded = base64.b64encode(resolved.encode()).decode()
        shell_cmd = f"echo {encoded} | base64 -d > /tmp/_eval_cmd.sh && bash /tmp/_eval_cmd.sh"
    else:
        shell_cmd = resolved

    if docker_dir:
        cmd = ["docker", "compose", "-f", f"{docker_dir}/docker-compose.yml",
               "exec", "-T", container, "bash", "-c", shell_cmd]
    else:
        cmd = ["docker", "exec", container, "bash", "-c", shell_cmd]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode != 0 and docker_dir:
            cmd_alt = ["docker", "exec", container, "bash", "-c", shell_cmd]
            proc = subprocess.run(
                cmd_alt, capture_output=True, text=True, timeout=timeout
            )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        logger.warning("docker exec timed out: %s", resolved[:100])
        return -1, "", "timeout"
    except FileNotFoundError:
        try:
            cmd_alt = ["docker", "exec", container, "bash", "-c", shell_cmd]
            proc = subprocess.run(
                cmd_alt, capture_output=True, text=True, timeout=timeout
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except Exception as exc:
            logger.warning("docker exec failed: %s", exc)
            return -1, "", str(exc)



def json_path_get(data: Any, path: str) -> Any:
    if data is None:
        return None
    parts = _parse_path(path)
    current = data
    for part in parts:
        if current is None:
            return None
        if isinstance(part, int):
            if isinstance(current, list) and 0 <= part < len(current):
                current = current[part]
            else:
                return None
        elif part == "length":
            return len(current) if isinstance(current, (list, dict)) else None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
    return current


def _parse_path(path: str) -> list:
    import re
    path = path.lstrip("$").lstrip(".")
    if not path:
        return []
    parts = []
    for token in re.split(r"\.|\[", path):
        token = token.rstrip("]")
        if not token:
            continue
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(token)
    return parts
