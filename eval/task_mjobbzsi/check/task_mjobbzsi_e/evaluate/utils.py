import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import requests

from config import APP_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT, RESULTS_DIR


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


@dataclass
class PrimitiveResult:
    passed: bool
    output: Any = None
    message: str = ""


def http_get(path, headers=None, timeout=HTTP_TIMEOUT):
    url = f"{APP_BASE_URL}{path}" if path.startswith("/") else path
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout, allow_redirects=True)
        return {"status_code": r.status_code, "headers": dict(r.headers),
                "body": _try_json(r), "text": r.text, "response_time_ms": int(r.elapsed.total_seconds() * 1000)}
    except Exception as e:
        return {"status_code": 0, "error": str(e), "body": None, "text": "", "headers": {}}


def http_post(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = f"{APP_BASE_URL}{path}" if path.startswith("/") else path
    h = {"Content-Type": "application/json", **(headers or {})}
    try:
        if isinstance(body, str) and body.startswith("<"):
            h["Content-Type"] = "text/xml"
            r = requests.post(url, data=body, headers=h, timeout=timeout)
        else:
            r = requests.post(url, json=body, headers=h, timeout=timeout)
        return {"status_code": r.status_code, "headers": dict(r.headers),
                "body": _try_json(r), "text": r.text}
    except Exception as e:
        return {"status_code": 0, "error": str(e), "body": None, "text": ""}


def docker_exec(container, command, timeout=60):
    try:
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c", command],
            capture_output=True, text=True, timeout=timeout
        )
        return {"exit_code": result.returncode, "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def _try_json(r):
    try:
        return r.json()
    except Exception:
        return None


def save_results(results, filename="results.json"):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, filename)
    data = {nid: asdict(nr) for nid, nr in results.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return path


def print_summary(results, scoring_config):
    total_score = sum(r.score for r in results.values())
    total_max = sum(r.maxScore for r in results.values())
    passed = sum(1 for r in results.values() if r.status == "PASSED")
    failed = sum(1 for r in results.values() if r.status == "FAILED")
    skipped = sum(1 for r in results.values() if r.status == "SKIPPED_DEPENDENCY")
    errors = sum(1 for r in results.values() if r.status == "ERROR")

    print(f"\n{'='*60}")
    print(f"EVALUATION RESULTS")
    print(f"{'='*60}")
    print(f"Total: {total_score:.1f}/{total_max} ({(total_score/total_max*100) if total_max else 0:.1f}%)")
    print(f"Nodes: {passed} passed, {failed} failed, {skipped} skipped, {errors} errors")
    print(f"{'='*60}")

    cats = {}
    for r in results.values():
        c = r.category
        if c not in cats:
            cats[c] = {"score": 0, "max": 0}
        cats[c]["score"] += r.score
        cats[c]["max"] += r.maxScore

    for c in sorted(cats, key=lambda x: -cats[x]["max"]):
        s, m = cats[c]["score"], cats[c]["max"]
        pct = s / m * 100 if m > 0 else 0
        bar = "#" * int(pct / 5) + "-" * (20 - int(pct / 5))
        print(f"  {c:30s} {s:5.1f}/{m:5.1f} {bar} {pct:.0f}%")

    print(f"{'='*60}\n")
