import json
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import psycopg2
import requests

try:
    from .config import (
        APP_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
        DB_CONNECT_TIMEOUT, HTTP_TIMEOUT, RESULTS_DIR,
    )
except ImportError:
    from config import (
        APP_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
        DB_CONNECT_TIMEOUT, HTTP_TIMEOUT, RESULTS_DIR,
    )


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float = 0.0
    max_score: float = 1.0
    category: str = ""
    subcategory: str = ""
    message: str = ""
    evidence: Any = None
    complexity_tier: str = ""


_PATH_PREFIX_DEFAULTS = {
    "API_V1_PREFIX": "/api/v1",
    "API_V2_PREFIX": "/api/v2",
    "PLATFORM_API_PREFIX": "/platform/api/v1",
    "PUBLIC_API_PREFIX": "/public/api/v1",
    "WIDGET_API_PREFIX": "/api/v1/widget",
}


def _expand_path_prefixes(path: str) -> str:
    for var, default in _PATH_PREFIX_DEFAULTS.items():
        path = path.replace("${" + var + "}", os.environ.get(var, default))
    return path


def _build_url(path: str) -> str:
    base = APP_BASE_URL.rstrip("/")
    path = _expand_path_prefixes(path)
    path = path if path.startswith("/") else f"/{path}"
    return f"{base}{path}"


def _apply_auth_headers(
    headers: Optional[Dict[str, str]], context: Optional[Dict[str, Any]]
) -> Dict[str, str]:
    h = dict(headers) if headers else {}
    if context:
        for key in ("access-token", "client", "uid"):
            if key in context and key not in h:
                h[key] = context[key]
    return h


def http_get(
    path: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = HTTP_TIMEOUT,
    context: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    h = _apply_auth_headers(headers, context)
    return requests.get(_build_url(path), headers=h, params=params, timeout=timeout)


def http_post(
    path: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Any] = None,
    timeout: int = HTTP_TIMEOUT,
    context: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    h = _apply_auth_headers(headers, context)
    return requests.post(_build_url(path), headers=h, json=json_body, timeout=timeout)


def http_put(
    path: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Any] = None,
    timeout: int = HTTP_TIMEOUT,
    context: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    h = _apply_auth_headers(headers, context)
    return requests.put(_build_url(path), headers=h, json=json_body, timeout=timeout)


def http_patch(
    path: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Any] = None,
    timeout: int = HTTP_TIMEOUT,
    context: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    h = _apply_auth_headers(headers, context)
    return requests.patch(_build_url(path), headers=h, json=json_body, timeout=timeout)


def http_delete(
    path: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Any] = None,
    timeout: int = HTTP_TIMEOUT,
    context: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    h = _apply_auth_headers(headers, context)
    return requests.delete(_build_url(path), headers=h, json=json_body, timeout=timeout)


def docker_exec(container: str, command: str) -> tuple:
    result = subprocess.run(
        ["docker", "exec", container, "bash", "-c", command],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=DB_CONNECT_TIMEOUT,
    )


def resolve_placeholders(text: str, context: Dict[str, Any]) -> str:
    def replacer(match):
        key = match.group(1).strip()
        entities = context.get("entities", {})
        if key in entities:
            return str(entities[key])
        if key in context:
            return str(context[key])
        return match.group(0)

    return re.sub(r"\{\{(.+?)\}\}", replacer, text)


def print_result(result: NodeResult) -> None:
    icon = {"PASSED": "✓", "FAILED": "✗", "ERROR": "⚠", "SKIPPED_DEPENDENCY": "⊘"}.get(
        result.status, "?"
    )
    print(
        f"  [{icon}] {result.node_id}: {result.status} "
        f"({result.score}/{result.max_score}) — {result.message}"
    )


def save_results(results: List[NodeResult], path: Optional[str] = None) -> str:
    import os

    if path is None:
        path = os.path.join(RESULTS_DIR, "results.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = [asdict(r) for r in results]
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return path
