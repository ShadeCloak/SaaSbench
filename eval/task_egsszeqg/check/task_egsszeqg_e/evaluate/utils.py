from __future__ import annotations
import json, subprocess, time, dataclasses, os
from typing import Any
import requests

from config import APP_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT


@dataclasses.dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    maxScore: float
    category: str = ""
    subcategory: str = ""
    message: str = ""
    evidence: dict | None = None


def _url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return APP_BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def http_get(path: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return requests.get(_url(path), headers=headers or {}, timeout=timeout, allow_redirects=False, **kw)


def http_post(path: str, json_body: Any = None, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return requests.post(_url(path), json=json_body, headers=headers or {}, timeout=timeout, allow_redirects=False, **kw)


def http_patch(path: str, json_body: Any = None, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return requests.patch(_url(path), json=json_body, headers=headers or {}, timeout=timeout, allow_redirects=False, **kw)


def http_put(path: str, json_body: Any = None, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return requests.put(_url(path), json=json_body, headers=headers or {}, timeout=timeout, allow_redirects=False, **kw)


def http_delete(path: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return requests.delete(_url(path), headers=headers or {}, timeout=timeout, allow_redirects=False, **kw)


def http_options(path: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return requests.options(_url(path), headers=headers or {}, timeout=timeout, allow_redirects=False, **kw)


def http_head(path: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT, **kw) -> requests.Response:
    return requests.head(_url(path), headers=headers or {}, timeout=timeout, allow_redirects=False, **kw)


def http_request(method: str, path: str, headers: dict | None = None,
                 body: Any = None, query: dict | None = None,
                 timeout: int = HTTP_TIMEOUT) -> requests.Response:
    url = _url(path)
    return requests.request(
        method, url,
        headers=headers or {},
        json=body,
        params=query,
        timeout=timeout,
        allow_redirects=False,
    )


def docker_exec(command: str, container: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    ctr = container or APP_CONTAINER
    return subprocess.run(
        ["docker", "exec", ctr, "bash", "-lc", command],
        capture_output=True, text=True, timeout=timeout,
    )


def save_results(results: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)


def print_summary(results: dict) -> None:
    total = results.get("total_score", 0)
    max_total = results.get("total_maxScore", 0)
    pct = (total / max_total * 100) if max_total else 0
    print(f"\n{'='*60}")
    print(f"  TOTAL: {total:.2f} / {max_total:.2f} ({pct:.1f}%)")
    print(f"{'='*60}")
    for cat in results.get("categories", []):
        print(f"  {cat['category']:30s} {cat['score']:.2f} / {cat['maxScore']:.2f}")
