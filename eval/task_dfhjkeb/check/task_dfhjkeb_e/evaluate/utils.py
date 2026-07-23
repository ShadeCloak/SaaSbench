import json
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import requests

from config import APP_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    maxScore: float
    category: str = ""
    subcategory: str = ""
    message: str = ""
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PrimitiveResult:
    passed: bool
    data: Any = None
    message: str = ""


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_session = requests.Session()


def _url(path: str) -> str:
    if path.startswith("http"):
        return path
    return APP_BASE_URL.rstrip("/") + ("" if path.startswith("/") else "/") + path


def http_get(path: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return _session.get(_url(path), headers=headers or {}, timeout=timeout, **kw)


def http_post(path: str, json_body: Any = None, headers: dict | None = None,
              timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return _session.post(_url(path), json=json_body, headers=headers or {}, timeout=timeout, **kw)


def http_delete(path: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return _session.delete(_url(path), headers=headers or {}, timeout=timeout, **kw)


def http_patch(path: str, json_body: Any = None, headers: dict | None = None,
               timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return _session.patch(_url(path), json=json_body, headers=headers or {}, timeout=timeout, **kw)


def set_auth_header(token: str | None):
    if token:
        _session.headers["Authorization"] = f"Bearer {token}"
    else:
        _session.headers.pop("Authorization", None)


def clear_auth():
    _session.headers.pop("Authorization", None)
    _session.cookies.clear()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def docker_exec(command: str, container: str = APP_CONTAINER,
                timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", container] + command.split()
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def save_results(results: list[dict], path: str):
    with open(path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)


def print_result(nr: NodeResult):
    if nr.status == "PASSED":
        icon = "✓"
    elif nr.status.startswith("SKIPPED"):
        icon = "⊘"
    else:
        icon = "✗"
    print(f"  [{icon}] {nr.node_id}: {nr.score}/{nr.maxScore} — {nr.message}")


def wait_for_app(max_wait: int = 120, interval: int = 3) -> bool:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(APP_BASE_URL, timeout=5)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False
