import json
import logging
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

from config import (
    DB_CONTAINER,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    HTTP_TIMEOUT,
)

logger = logging.getLogger(__name__)

context: dict = {}


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    max_score: float
    category: str
    subcategory: str
    message: str
    evidence: dict = field(default_factory=dict)


def _http_request(method: str, url: str, **kwargs) -> Optional[requests.Response]:
    timeout = kwargs.pop("timeout", HTTP_TIMEOUT)
    kwargs.setdefault("timeout", timeout)
    try:
        resp = requests.request(method, url, **kwargs)
        return resp
    except Exception as e:
        logger.error("HTTP %s %s failed: %s", method, url, e)
        return None


def http_get(url: str, headers: Optional[dict] = None, timeout: Optional[int] = None) -> Optional[requests.Response]:
    return _http_request("GET", url, headers=headers or {}, timeout=timeout)


def http_post(
    url: str,
    headers: Optional[dict] = None,
    json_body: Optional[dict] = None,
    data: Optional[Any] = None,
    timeout: Optional[int] = None,
) -> Optional[requests.Response]:
    kwargs = {"headers": headers or {}}
    if json_body is not None:
        kwargs["json"] = json_body
    if data is not None:
        kwargs["data"] = data
    kwargs["timeout"] = timeout
    return _http_request("POST", url, **kwargs)


def http_put(
    url: str,
    headers: Optional[dict] = None,
    json_body: Optional[dict] = None,
    data: Optional[Any] = None,
    timeout: Optional[int] = None,
) -> Optional[requests.Response]:
    kwargs = {"headers": headers or {}}
    if json_body is not None:
        kwargs["json"] = json_body
    if data is not None:
        kwargs["data"] = data
    kwargs["timeout"] = timeout
    return _http_request("PUT", url, **kwargs)


def http_delete(url: str, headers: Optional[dict] = None, timeout: Optional[int] = None) -> Optional[requests.Response]:
    return _http_request("DELETE", url, headers=headers or {}, timeout=timeout)


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
    )


def db_query(sql: str, params: Optional[tuple] = None) -> list[dict]:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
    except Exception as e:
        logger.error("db_query failed: %s", e)
        return []


def docker_exec(container: str, command: str) -> tuple[int, str, str]:
    try:
        cmd = ["docker", "exec", container, "sh", "-c", command] if isinstance(command, str) else ["docker", "exec", container] + list(command)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        logger.error("docker_exec failed: %s", e)
        return -1, "", str(e)


def save_results(results: list[NodeResult], filepath: str) -> None:
    with open(filepath, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)


def print_summary(results: list[NodeResult]) -> None:
    by_category: dict[str, list[NodeResult]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)

    for cat, items in sorted(by_category.items()):
        print(f"\n=== {cat} ===")
        for r in items:
            status_sym = "P" if r.status.lower() == "pass" else "F"
            print(f"  [{status_sym}] {r.node_id}: {r.score}/{r.max_score} - {r.message}")


def _extract_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    if isinstance(obj, list):
        try:
            idx = int(key)
            return obj[idx] if 0 <= idx < len(obj) else None
        except (ValueError, TypeError):
            return None
    return None


def store_response(r: dict, ctx: dict) -> None:
    ctx["_last_status_code"] = r.get("status_code", 0)
    ctx["_last_response_body"] = r.get("body")
    ctx["_last_response_headers"] = r.get("headers", {})
    ctx["_last_response_raw"] = r.get("body") if isinstance(r.get("body"), str) else ""


def resolve_placeholders(s: str, ctx: dict) -> str:
    if not isinstance(s, str):
        return s

    result = []
    i = 0
    while i < len(s):
        if s[i : i + 2] == "{{":
            end = s.find("}}", i)
            if end == -1:
                result.append(s[i])
                i += 1
                continue
            key_path = s[i + 2 : end].strip()
            parts = key_path.split(".")
            val = ctx
            for part in parts:
                val = _extract_value(val, part)
                if val is None:
                    break
            result.append(str(val) if val is not None else "")
            i = end + 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)
