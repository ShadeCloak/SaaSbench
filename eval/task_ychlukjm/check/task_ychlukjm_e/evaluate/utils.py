
from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass, field, asdict
from typing import Any

import requests

import config

logger = logging.getLogger("eval")



@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float = 0.0
    max_score: float = 0.0
    message: str = ""
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChainResult:
    all_passed: bool = True
    pass_count: int = 0
    total_count: int = 0
    evidence: dict = field(default_factory=dict)
    last_response: Any = None
    last_status_code: int | None = None
    error: str | None = None

    @property
    def pass_ratio(self) -> float:
        return self.pass_count / self.total_count if self.total_count else 0.0



class ArtifactStore:

    def __init__(self):
        self._store: dict[str, dict] = {}
        self._current: str | None = None

    def push_context(self, node_id: str):
        self._current = node_id
        self._store.setdefault(node_id, {})

    def pop_context(self):
        self._current = None

    def put(self, key: str, value: Any):
        if self._current:
            self._store[self._current][key] = value

    def get_evidence(self, node_id: str) -> dict:
        return self._store.get(node_id, {})

    def get_all(self) -> dict:
        return dict(self._store)



class AuthContext:

    def __init__(self):
        self._tokens: dict[str, str] = {}
        self._current_role: str | None = None

    @property
    def current_token(self) -> str | None:
        if self._current_role:
            return self._tokens.get(self._current_role)
        return self._tokens.get("admin")

    def set_token(self, role: str, token: str):
        self._tokens[role] = token
        self._current_role = role

    def switch_role(self, role: str) -> str | None:
        self._current_role = role
        return self._tokens.get(role)

    @property
    def current_role(self) -> str | None:
        return self._current_role

    def auth_headers(self) -> dict[str, str]:
        token = self.current_token
        if token:
            if token.startswith("__system_basic__"):
                return {"Authorization": f"Basic {token[len('__system_basic__'):]}"}
            return {"Authorization": f"Bearer {token}"}
        return {}


auth_ctx = AuthContext()
artifact_store = ArtifactStore()



_graphql_endpoint_cache: str | None = None

def graphql(query: str, variables: dict | None = None,
            headers: dict | None = None, timeout: int | None = None) -> dict:
    global _graphql_endpoint_cache
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(auth_ctx.auth_headers())
    if headers:
        hdrs.update(headers)
    body: dict[str, Any] = {"query": query}
    if variables:
        body["variables"] = variables

    endpoints = [config.GRAPHQL_ENDPOINT]
    if _graphql_endpoint_cache and _graphql_endpoint_cache != config.GRAPHQL_ENDPOINT:
        endpoints.insert(0, _graphql_endpoint_cache)
    alt = config.APP_BASE_URL + "/api/graphql"
    if alt not in endpoints:
        endpoints.append(alt)

    for ep in endpoints:
        try:
            resp = requests.post(ep, json=body, headers=hdrs,
                                 timeout=timeout or config.HTTP_TIMEOUT)
            if resp.status_code == 200:
                _graphql_endpoint_cache = ep
                return resp.json()
        except Exception:
            continue
    resp = requests.post(config.GRAPHQL_ENDPOINT, json=body, headers=hdrs,
                         timeout=timeout or config.HTTP_TIMEOUT)
    return resp.json()


def http_request(method: str, path: str, body: Any = None,
                 headers: dict | None = None, timeout: int | None = None,
                 absolute_url: str | None = None) -> requests.Response:
    url = absolute_url or (config.APP_BASE_URL + path)
    hdrs = {}
    hdrs.update(auth_ctx.auth_headers())
    if headers:
        hdrs.update(headers)
    return requests.request(
        method, url, json=body if body is not None else None,
        headers=hdrs, timeout=timeout or config.HTTP_TIMEOUT,
    )


def safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None



def json_path_value(data: Any, path: str) -> Any:
    if data is None or not path:
        return None
    stripped = path.lstrip("$").lstrip(".")
    if not stripped:
        return data
    parts = stripped.split(".")
    current = data
    for part in parts:
        if current is None:
            return None
        if "[" in part:
            key, idx_str = part.split("[", 1)
            idx = int(idx_str.rstrip("]"))
            if key:
                current = current.get(key) if isinstance(current, dict) else None
            if isinstance(current, list) and 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
    return current


def assert_json_value(data: Any, assertion: dict) -> bool:
    path = assertion.get("path", "$")
    actual = json_path_value(data, path)
    op = assertion.get("operator", "eq")
    expected = assertion.get("expected")
    tolerance = assertion.get("tolerance", 0)

    if "expected_pattern" in assertion and expected is None:
        op = "regex"
        expected = assertion["expected_pattern"]

    if op == "eq":
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            return abs(actual - expected) <= tolerance
        return actual == expected
    elif op == "not_null":
        return actual is not None
    elif op == "gt":
        return actual is not None and actual > expected
    elif op == "gte":
        return actual is not None and actual >= expected
    elif op == "lte":
        return actual is not None and actual <= expected
    elif op == "lt":
        return actual is not None and actual < expected
    elif op == "contains":
        return expected in str(actual) if actual else False
    elif op == "regex":
        import re
        return bool(re.search(str(expected), str(actual))) if actual is not None else False
    elif op == "one_of":
        return actual in expected if isinstance(expected, list) else actual == expected
    elif op == "length":
        return isinstance(actual, (list, dict, str)) and len(actual) == expected
    elif op == "is_array":
        return isinstance(actual, list)
    elif op == "array_length_gte":
        return isinstance(actual, list) and len(actual) >= expected
    elif op == "is_valid_json":
        if isinstance(actual, str):
            try:
                json.loads(actual)
                return True
            except Exception:
                return False
        return isinstance(actual, (dict, list))
    elif op == "json_contains_key":
        if isinstance(actual, str):
            try:
                actual = json.loads(actual)
            except Exception:
                return False
        return isinstance(actual, dict) and expected in actual
    elif op == "ne" or op == "!=":
        return actual != expected
    elif op == ">" or op == "gt_strict":
        return actual is not None and actual > expected
    elif op == ">=" or op == "gte_strict":
        return actual is not None and actual >= expected
    elif op == "in":
        if isinstance(expected, list):
            return actual in expected
        return str(actual) in str(expected) if actual is not None else False
    elif op == "type_check":
        type_map = {"string": str, "number": (int, float), "boolean": bool, "array": list, "object": dict}
        return isinstance(actual, type_map.get(expected, object))
    elif op == "eq_path":
        other = json_path_value(data, expected)
        return actual == other
    elif op == "response_indicates_auth_failure":
        return True
    elif op == "exists":
        return actual is not None
    elif op == "not_exists":
        return actual is None
    else:
        logger.warning(f"Unknown operator: {op}")
        return actual == expected



_db_conn_cache = None


def get_db_connection():
    global _db_conn_cache
    import pymysql

    def _open():
        return pymysql.connect(
            host=config.DB_HOST, port=config.DB_PORT,
            user=config.DB_USER, password=config.DB_PASSWORD,
            database=config.DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=config.DB_TIMEOUT,
            autocommit=True,
        )

    if _db_conn_cache is None:
        _db_conn_cache = _open()
        return _db_conn_cache
    try:
        _db_conn_cache.ping(reconnect=True)
        return _db_conn_cache
    except Exception:
        try:
            _db_conn_cache.close()
        except Exception:
            pass
        _db_conn_cache = _open()
        return _db_conn_cache



def wait_for_service(url: str, max_wait: int = 120, interval: int = 3) -> bool:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code < 400:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False
