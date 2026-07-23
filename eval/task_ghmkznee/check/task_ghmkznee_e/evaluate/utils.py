import json
import os
import subprocess
import requests
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from config import APP_BASE_URL, API_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT, RESULTS_DIR


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    max_score: float
    category: str = ""
    subcategory: str = ""
    message: str = ""
    evidence: dict = field(default_factory=dict)


context = {
    "auth_token": None,
    "auth_headers": {},
}


def get_auth_headers():
    if context.get("auth_token"):
        return {"Authorization": f"Bearer {context['auth_token']}"}
    return context.get("auth_headers", {})


def http_get(path, params=None, headers=None, timeout=HTTP_TIMEOUT):
    url = path if path.startswith("http") else API_BASE_URL + path
    h = {**get_auth_headers(), **(headers or {})}
    try:
        return requests.get(url, params=params, headers=h, timeout=timeout)
    except Exception as e:
        return _error_response(str(e))


def http_post(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = path if path.startswith("http") else API_BASE_URL + path
    h = {"Content-Type": "application/json", **get_auth_headers(), **(headers or {})}
    try:
        return requests.post(url, json=body, headers=h, timeout=timeout)
    except Exception as e:
        return _error_response(str(e))


def http_put(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = path if path.startswith("http") else API_BASE_URL + path
    h = {"Content-Type": "application/json", **get_auth_headers(), **(headers or {})}
    try:
        return requests.put(url, json=body, headers=h, timeout=timeout)
    except Exception as e:
        return _error_response(str(e))


def http_patch(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = path if path.startswith("http") else API_BASE_URL + path
    h = {"Content-Type": "application/json", **get_auth_headers(), **(headers or {})}
    try:
        return requests.patch(url, json=body, headers=h, timeout=timeout)
    except Exception as e:
        return _error_response(str(e))


def http_delete(path, headers=None, timeout=HTTP_TIMEOUT):
    url = path if path.startswith("http") else API_BASE_URL + path
    h = {**get_auth_headers(), **(headers or {})}
    try:
        return requests.delete(url, headers=h, timeout=timeout)
    except Exception as e:
        return _error_response(str(e))


def _error_response(msg):
    class FakeResp:
        status_code = 0
        text = msg
        def json(self):
            return {"error": msg}
    return FakeResp()


def docker_exec(command, container=APP_CONTAINER):
    try:
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c", command],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)


def save_results(results, filename="results.json"):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, filename)
    data = [asdict(r) if isinstance(r, NodeResult) else r for r in results]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def print_result(result: NodeResult):
    status_icon = {"PASSED": "✓", "FAILED": "✗", "SKIPPED_DEPENDENCY": "⊘", "ERROR": "⚠"}.get(result.status, "?")
    print(f"  [{status_icon}] {result.node_id}: {result.score}/{result.max_score} — {result.message}")
