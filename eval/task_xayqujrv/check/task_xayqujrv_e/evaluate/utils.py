"""Shared utilities for the Stage 6 harness.

Includes:
  - NodeResult dataclass (the unit returned by every test/primitive)
  - HTTP helpers (with auto-merging of context auth headers)
  - docker_exec wrappers
  - placeholder template resolver ({{var}} / {{var.field}})
  - results saver + summary printer
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import APP_BASE_URL, APP_CONTAINER, DB_CONTAINER, HTTP_TIMEOUT, RESULTS_DIR


# ============================================================
# ============================================================
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
    evidence: Any = field(default_factory=list)
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# ============================================================
def http_request(
    method: str,
    path: str,
    headers: Optional[dict] = None,
    body: Any = None,
    timeout: int = HTTP_TIMEOUT,
    base_url: Optional[str] = None,
    files: Any = None,
) -> requests.Response:
    if path.startswith("http://") or path.startswith("https://"):
        url = path
    else:
        url = (base_url or APP_BASE_URL).rstrip("/") + path

    merged = {"Accept": "application/json"}
    if headers:
        merged.update({k: v for k, v in headers.items() if v is not None})

    json_body = None
    data_body = None
    if body is not None and method.upper() != "GET":
        if files is not None:
            data_body = body
        else:
            json_body = body
    params = body if (body is not None and method.upper() == "GET") else None

    resp = requests.request(
        method=method.upper(),
        url=url,
        headers=merged,
        json=json_body,
        data=data_body,
        params=params,
        files=files,
        timeout=timeout,
        allow_redirects=False,
    )
    return resp


def http_get(path, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("GET", path, headers=headers, timeout=timeout)


def http_post(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("POST", path, headers=headers, body=body, timeout=timeout)


def http_patch(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("PATCH", path, headers=headers, body=body, timeout=timeout)


def http_put(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("PUT", path, headers=headers, body=body, timeout=timeout)


def http_delete(path, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("DELETE", path, headers=headers, timeout=timeout)


# ============================================================
# ============================================================
def docker_exec(container: str, command: str, timeout: int = 60) -> Tuple[int, str]:
    try:
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-lc", command],
            capture_output=True, text=True, timeout=timeout,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return result.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return -1, f"docker exec timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "docker binary not found on host"
    except Exception as e:
        return -1, f"docker exec error: {e}"


def docker_exec_app(command: str, timeout: int = 60) -> Tuple[int, str]:
    return docker_exec(APP_CONTAINER, command, timeout)


def docker_exec_db(command: str, timeout: int = 30) -> Tuple[int, str]:
    return docker_exec(DB_CONTAINER, command, timeout)


# ============================================================
# ============================================================
_PH_DOTTED_RE = re.compile(r"\{\{(\w+)\.(\w+)\}\}")
_PH_DEFAULT_RE = re.compile(
    r"\{\{\s*(\w+)\s*\|\s*default\(\s*([^)]*?)\s*\)\s*\}\}"
)
_PH_LEFTOVER_RE = re.compile(r"\{\{[^{}]+\}\}")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def resolve_placeholders(template: Any, context: dict) -> Any:
    if isinstance(template, str):
        result = template
        for key, val in context.items():
            if not isinstance(val, (str, int, float, bool)):
                continue
            result = result.replace("{{" + str(key) + "}}", str(val))
        for parent_key, child_key in _PH_DOTTED_RE.findall(result):
            parent = context.get(parent_key)
            if isinstance(parent, dict) and child_key in parent:
                result = result.replace(
                    "{{" + parent_key + "." + child_key + "}}",
                    str(parent[child_key]),
                )

        def _replace_default(match: "re.Match[str]") -> str:
            var_name = match.group(1)
            fallback = _strip_quotes(match.group(2))
            value = context.get(var_name)
            if isinstance(value, (str, int, float, bool)):
                return str(value)
            return fallback

        result = _PH_DEFAULT_RE.sub(_replace_default, result)
        if "{{" in result:
            result = _PH_LEFTOVER_RE.sub("", result)
        return result
    if isinstance(template, dict):
        return {k: resolve_placeholders(v, context) for k, v in template.items()}
    if isinstance(template, list):
        return [resolve_placeholders(item, context) for item in template]
    return template


# ============================================================
# ============================================================
def save_results(results: List[NodeResult], filepath: str = "") -> str:
    if not filepath:
        filepath = os.path.join(RESULTS_DIR, "node_results.json")
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    data = [r.to_dict() for r in results]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return filepath


def print_summary(results: List[NodeResult], scoring_config: dict) -> None:
    total_score = sum(r.score for r in results)
    total_max = sum(r.max_score for r in results)
    pct = (total_score / total_max * 100) if total_max else 0

    print(f"\n{'='*70}")
    print(f"  EVALUATION SUMMARY")
    print(f"{'='*70}")
    print(f"  Total: {total_score:.1f} / {total_max:.1f} ({pct:.1f}%)")

    cats: Dict[str, Dict[str, float]] = {}
    for r in results:
        cat = r.category or "Uncategorized"
        c = cats.setdefault(cat, {"score": 0.0, "max": 0.0,
                                   "P": 0, "F": 0, "S": 0, "E": 0})
        c["score"] += r.score
        c["max"] += r.max_score
        if r.status == "PASSED":
            c["P"] += 1
        elif r.status == "FAILED":
            c["F"] += 1
        elif r.status in ("SKIPPED_DEPENDENCY", "SKIPPED_LLM", "DRY_RUN"):
            c["S"] += 1
        else:
            c["E"] += 1

    print(f"\n  {'Category':<32} {'Score':>9} {'Max':>7} {'%':>6}  {'P':>3} {'F':>3} {'S':>3} {'E':>3}")
    print(f"  {'-'*32} {'-'*9} {'-'*7} {'-'*6}  {'-'*3} {'-'*3} {'-'*3} {'-'*3}")
    for cat in sorted(cats.keys()):
        c = cats[cat]
        p = (c["score"] / c["max"] * 100) if c["max"] else 0
        print(f"  {cat:<32} {c['score']:>9.1f} {c['max']:>7.1f} {p:>5.1f}%  "
              f"{int(c['P']):>3} {int(c['F']):>3} {int(c['S']):>3} {int(c['E']):>3}")

    statuses: Dict[str, int] = {}
    for r in results:
        statuses[r.status] = statuses.get(r.status, 0) + 1
    print(f"\n  Node statuses: {statuses}")


# ============================================================
# ============================================================
def wait_until(predicate, timeout_s: float = 10.0, interval_s: float = 0.5):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            last = predicate()
            if last:
                return last
        except Exception:
            last = None
        time.sleep(interval_s)
    return last
