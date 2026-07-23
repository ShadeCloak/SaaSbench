import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import requests

from config import APP_BASE_URL, API_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT, RESULTS_DIR


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    maxScore: float
    category: str = ""
    subcategory: str = ""
    method: str = "binary"
    message: str = ""
    evidence: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class PrimitiveResult:
    passed: bool
    data: Any = None
    message: str = ""
    evidence: dict = field(default_factory=dict)


class ArtifactStore:
    def __init__(self):
        self._store: Dict[str, list] = {}
        self._context_stack: List[str] = []

    def push_context(self, node_id: str):
        self._context_stack.append(node_id)
        if node_id not in self._store:
            self._store[node_id] = []

    def pop_context(self):
        if self._context_stack:
            self._context_stack.pop()

    def add_evidence(self, evidence: dict):
        if self._context_stack:
            self._store[self._context_stack[-1]].append(evidence)

    def get_evidence(self, node_id: str) -> list:
        return self._store.get(node_id, [])


context: Dict[str, Any] = {}


def http_get(path: str, headers: Optional[dict] = None, timeout: int = HTTP_TIMEOUT, base_url: str = None) -> requests.Response:
    url = (base_url or APP_BASE_URL) + path
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    if "auth_token" in context and "x-api-key" not in (headers or {}):
        h.setdefault("Authorization", f"Bearer {context['auth_token']}")
    try:
        return requests.get(url, headers=h, timeout=timeout, allow_redirects=False)
    except Exception as e:
        return _error_response(str(e))


def http_post(path: str, body: Any = None, headers: Optional[dict] = None, timeout: int = HTTP_TIMEOUT, base_url: str = None) -> requests.Response:
    url = (base_url or APP_BASE_URL) + path
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    if "auth_token" in context and "x-api-key" not in (headers or {}):
        h.setdefault("Authorization", f"Bearer {context['auth_token']}")
    try:
        return requests.post(url, json=body, headers=h, timeout=timeout, allow_redirects=False)
    except Exception as e:
        return _error_response(str(e))


def http_put(path: str, body: Any = None, headers: Optional[dict] = None, timeout: int = HTTP_TIMEOUT) -> requests.Response:
    url = APP_BASE_URL + path
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    if "auth_token" in context and "x-api-key" not in (headers or {}):
        h.setdefault("Authorization", f"Bearer {context['auth_token']}")
    try:
        return requests.put(url, json=body, headers=h, timeout=timeout, allow_redirects=False)
    except Exception as e:
        return _error_response(str(e))


def http_patch(path: str, body: Any = None, headers: Optional[dict] = None, timeout: int = HTTP_TIMEOUT) -> requests.Response:
    url = APP_BASE_URL + path
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    if "auth_token" in context and "x-api-key" not in (headers or {}):
        h.setdefault("Authorization", f"Bearer {context['auth_token']}")
    try:
        return requests.patch(url, json=body, headers=h, timeout=timeout, allow_redirects=False)
    except Exception as e:
        return _error_response(str(e))


def http_delete(path: str, headers: Optional[dict] = None, timeout: int = HTTP_TIMEOUT) -> requests.Response:
    url = APP_BASE_URL + path
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    if "auth_token" in context and "x-api-key" not in (headers or {}):
        h.setdefault("Authorization", f"Bearer {context['auth_token']}")
    try:
        return requests.delete(url, headers=h, timeout=timeout, allow_redirects=False)
    except Exception as e:
        return _error_response(str(e))


def docker_exec(command: str, container: str = APP_CONTAINER, timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["docker", "exec", container] + shlex.split(command),
            capture_output=True, text=True, timeout=timeout
        )
    except Exception as e:
        return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr=str(e))


def _error_response(msg: str) -> requests.Response:
    r = requests.Response()
    r.status_code = 0
    r._content = json.dumps({"error": msg}).encode()
    return r


def resolve_placeholders(obj: Any, ctx: dict) -> Any:
    if isinstance(obj, str):
        for key, val in ctx.items():
            obj = obj.replace("{{" + key + "}}", str(val))
        return obj
    elif isinstance(obj, dict):
        return {k: resolve_placeholders(v, ctx) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [resolve_placeholders(item, ctx) for item in obj]
    return obj


def save_results(results: dict, filename: str = "evaluation_results.json"):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    if os.path.dirname(filename):
        path = filename
        os.makedirs(os.path.dirname(path), exist_ok=True)
    else:
        path = os.path.join(RESULTS_DIR, filename)
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {path}")


def print_result(result: NodeResult):
    status_icon = {"PASSED": "✅", "FAILED": "❌", "SKIPPED_DEPENDENCY": "⏭️", "ERROR": "💥"}.get(result.status, "❓")
    print(f"  {status_icon} {result.node_id}: {result.score}/{result.maxScore} [{result.status}] {result.message}")
