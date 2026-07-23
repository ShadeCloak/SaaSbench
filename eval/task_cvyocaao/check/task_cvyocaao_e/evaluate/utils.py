import requests
import subprocess
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, List
from config import APP_BASE_URL, APP_CONTAINER, REQUEST_TIMEOUT


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

    def to_dict(self):
        return asdict(self)


@dataclass
class PrimitiveResult:
    passed: bool
    data: Any = None
    message: str = ""


context = {}


def http_request(method, path, headers=None, body=None, body_form=None, timeout=REQUEST_TIMEOUT):
    url = path if path.startswith("http") else APP_BASE_URL + path
    h = {"Content-Type": "application/json"}
    if context.get("auth_token"):
        h["Authorization"] = f"Bearer {context['auth_token']}"
    if headers:
        h.update(headers)
    if h.get("Authorization") == "":
        del h["Authorization"]

    kwargs = {"headers": h, "timeout": timeout, "allow_redirects": False}

    if body_form:
        h["Content-Type"] = "application/x-www-form-urlencoded"
        kwargs["data"] = body_form
    elif body is not None:
        kwargs["json"] = body

    resp = requests.request(method.upper(), url, **kwargs)
    return resp


def http_get(path, **kwargs):
    return http_request("GET", path, **kwargs)


def http_post(path, **kwargs):
    return http_request("POST", path, **kwargs)


def http_put(path, **kwargs):
    return http_request("PUT", path, **kwargs)


def http_delete(path, **kwargs):
    return http_request("DELETE", path, **kwargs)


def docker_exec(command, container=APP_CONTAINER):
    try:
        result = subprocess.run(
            ["docker", "exec", container] + (command if isinstance(command, list) else command.split()),
            capture_output=True, text=True, timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def resolve_placeholders(value, ctx=None, _depth=0):
    if _depth > 5:
        return value
    if ctx is None:
        ctx = context
    if isinstance(value, str):
        for k, v in ctx.items():
            placeholder = "{{" + k + "}}"
            if placeholder in value:
                if isinstance(v, str) and "{{" not in v:
                    value = value.replace(placeholder, v)
                elif isinstance(v, (int, float, bool)):
                    value = value.replace(placeholder, str(v))
        return value
    elif isinstance(value, dict):
        return {k: resolve_placeholders(v, ctx, _depth + 1) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_placeholders(i, ctx, _depth + 1) for i in value]
    return value


def print_result(result: NodeResult):
    icon = "✅" if result.status == "PASSED" else "❌" if result.status == "FAILED" else "⏭️" if result.status == "SKIPPED_DEPENDENCY" else "💥"
    print(f"  {icon} {result.node_id}: {result.score}/{result.maxScore} - {result.message}")


def save_results(results: List[NodeResult], output_path: str):
    data = {
        "results": [r.to_dict() for r in results],
        "summary": aggregate_summary(results),
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data


def aggregate_summary(results: List[NodeResult]):
    total_score = sum(r.score for r in results)
    total_max = sum(r.maxScore for r in results)
    categories = {}
    for r in results:
        cat = r.category
        if cat not in categories:
            categories[cat] = {"total_score": 0, "max_score": 0, "nodes": 0, "passed": 0}
        categories[cat]["total_score"] += r.score
        categories[cat]["max_score"] += r.maxScore
        categories[cat]["nodes"] += 1
        if r.status == "PASSED":
            categories[cat]["passed"] += 1

    return {
        "total_score": total_score,
        "total_max": total_max,
        "percentage": round(total_score / total_max * 100, 1) if total_max > 0 else 0,
        "categories": [
            {"category": k, **v}
            for k, v in sorted(categories.items())
        ],
    }
