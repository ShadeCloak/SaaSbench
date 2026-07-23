from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import APP_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT, RESULTS_DIR


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    max_score: float
    category: str = ""
    subcategory: str = ""
    complexity_tier: str = ""
    message: str = ""
    evidence: Any = field(default_factory=dict)
    elapsed: float = 0.0

    def to_dict(self):
        return asdict(self)


def http_request(method: str, path: str, headers: Optional[dict] = None,
                 body: Any = None, timeout: int = HTTP_TIMEOUT,
                 base_url: Optional[str] = None) -> requests.Response:
    url = (base_url or APP_BASE_URL).rstrip("/") + path
    merged_headers = {"Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=merged_headers,
            json=body if body and method.upper() != "GET" else None,
            params=body if body and method.upper() == "GET" else None,
            timeout=timeout,
            allow_redirects=False,
        )
        return resp
    except requests.exceptions.RequestException:
        raise


def http_get(path, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("GET", path, headers=headers, timeout=timeout)


def http_post(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("POST", path, headers=headers, body=body, timeout=timeout)


def http_put(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("PUT", path, headers=headers, body=body, timeout=timeout)


def http_delete(path, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("DELETE", path, headers=headers, timeout=timeout)


def docker_exec(container: str, command: str, timeout: int = 30) -> Tuple[int, str]:
    try:
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c", command],
            capture_output=True, text=True, timeout=timeout,
        )
        output = result.stdout + result.stderr
        return result.returncode, output.strip()
    except subprocess.TimeoutExpired:
        return -1, "Command timed out"
    except Exception as e:
        return -1, str(e)


def _candidate_app_containers() -> list:
    seen = []
    def _add(n):
        if n and n not in seen:
            seen.append(n)
    _add(APP_CONTAINER)
    _add(APP_CONTAINER.replace("_", "-"))
    _add(APP_CONTAINER.replace("-", "_"))
    _add("task_aoiwqoiq-app")
    _add("task_aoiwqoiq_app")
    _add("task-aoiwqoiq-app")
    _add("task-aoiwqoiq_app")
    _add("app")
    return seen


def docker_exec_app(command: str, timeout: int = 30) -> Tuple[int, str]:
    last_code, last_out = -1, ""
    for cname in _candidate_app_containers():
        code, out = docker_exec(cname, command, timeout)
        if not (code != 0 and "No such container" in out):
            return code, out
        last_code, last_out = code, out
    return last_code, last_out


def resolve_placeholders(template: Any, context: dict) -> Any:
    if isinstance(template, str):
        result = template
        for key, val in context.items():
            result = result.replace("{{" + key + "}}", str(val))
        import re
        for match in re.findall(r"\{\{(\w+)\.(\w+)\}\}", result):
            parent, child = match
            parent_val = context.get(parent)
            if isinstance(parent_val, dict) and child in parent_val:
                result = result.replace("{{" + parent + "." + child + "}}", str(parent_val[child]))
                continue
            flat_key = f"{parent}_{child}"
            if flat_key in context:
                result = result.replace(
                    "{{" + parent + "." + child + "}}",
                    str(context[flat_key]),
                )
        return result
    if isinstance(template, dict):
        return {k: resolve_placeholders(v, context) for k, v in template.items()}
    if isinstance(template, list):
        return [resolve_placeholders(item, context) for item in template]
    return template


def save_results(results: List[NodeResult], filepath: str = ""):
    if not filepath:
        filepath = os.path.join(RESULTS_DIR, "eval_results.json")
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    path = filepath
    data = [r.to_dict() for r in results]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def print_summary(results: List[NodeResult], scoring_config: dict):
    total_score = sum(r.score for r in results)
    total_max = sum(r.max_score for r in results)
    pct = (total_score / total_max * 100) if total_max else 0

    print(f"\n{'='*60}")
    print(f"EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total Score: {total_score:.1f} / {total_max:.1f} ({pct:.1f}%)")
    print(f"Normalized:  {total_score / total_max * 100:.1f} / 100" if total_max else "")

    cats = {}
    for r in results:
        cat = r.category or "Uncategorized"
        if cat not in cats:
            cats[cat] = {"score": 0, "max": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0}
        cats[cat]["score"] += r.score
        cats[cat]["max"] += r.max_score
        if r.status == "PASSED":
            cats[cat]["passed"] += 1
        elif r.status == "FAILED":
            cats[cat]["failed"] += 1
        elif r.status == "SKIPPED_DEPENDENCY":
            cats[cat]["skipped"] += 1
        else:
            cats[cat]["error"] += 1

    print(f"\n{'Category':<25} {'Score':>8} {'Max':>6} {'%':>6}  {'P':>3} {'F':>3} {'S':>3} {'E':>3}")
    print("-" * 70)
    for cat in sorted(cats.keys()):
        c = cats[cat]
        p = (c["score"] / c["max"] * 100) if c["max"] else 0
        print(f"{cat:<25} {c['score']:>8.1f} {c['max']:>6.1f} {p:>5.1f}%  "
              f"{c['passed']:>3} {c['failed']:>3} {c['skipped']:>3} {c['error']:>3}")

    statuses = {"PASSED": 0, "FAILED": 0, "SKIPPED_DEPENDENCY": 0, "ERROR": 0}
    for r in results:
        statuses[r.status] = statuses.get(r.status, 0) + 1

    print(f"\nNode Status: {statuses}")
