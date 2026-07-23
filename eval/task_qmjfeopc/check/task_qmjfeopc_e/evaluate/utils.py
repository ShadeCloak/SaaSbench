import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import requests

from config import APP_BASE_URL, API_BASE_URL, HTTP_TIMEOUT, RESULTS_DIR


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

    def to_dict(self):
        return asdict(self)


@dataclass
class PrimitiveResult:
    passed: bool
    data: Any = None
    message: str = ""


class ArtifactStore:
    def __init__(self):
        self._store: dict[str, list] = {}
        self._current: Optional[str] = None

    def push_context(self, node_id: str):
        self._current = node_id
        self._store.setdefault(node_id, [])

    def pop_context(self):
        self._current = None

    def record(self, artifact_type: str, data: Any):
        if self._current:
            self._store[self._current].append({"type": artifact_type, "data": data})

    def get_evidence(self, node_id: str) -> list:
        return self._store.get(node_id, [])

    def get_all(self) -> dict:
        return dict(self._store)


def http_request(method: str, path: str, headers: dict | None = None,
                 body: Any = None, timeout: int = HTTP_TIMEOUT,
                 base_url: str | None = None) -> requests.Response:
    url = (base_url or APP_BASE_URL) + path
    try:
        resp = requests.request(
            method, url, json=body if body is not None else None,
            headers=headers or {}, timeout=timeout, allow_redirects=False,
        )
        return resp
    except requests.RequestException:
        raise


def docker_exec(container: str, command: str, timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", container, "bash", "-c", command]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def save_results(results: dict, filename: str = "results.json"):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, filename)
    with open(path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    return path


def print_summary(results: list[NodeResult]):
    total = sum(r.max_score for r in results)
    earned = sum(r.score for r in results)
    passed = sum(1 for r in results if r.status == "PASSED")
    failed = sum(1 for r in results if r.status == "FAILED")
    errored = sum(1 for r in results if r.status == "ERROR")
    skipped = sum(1 for r in results if r.status == "SKIPPED_DEPENDENCY")
    pct = (earned / total * 100) if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"  Total Score: {earned:.1f} / {total:.1f}  ({pct:.1f}%)")
    print(f"  Nodes: {passed} passed, {failed} failed, {errored} error, {skipped} skipped")
    print(f"{'='*60}")
