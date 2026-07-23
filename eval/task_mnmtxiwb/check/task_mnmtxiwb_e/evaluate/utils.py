import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import requests

from config import (
    APP_BASE_URL, API_BASE_URL, APP_CONTAINER, DB_CONTAINER,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, TIMEOUT, RESULTS_DIR
)


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


@dataclass
class PrimitiveResult:
    passed: bool
    data: Any = None
    message: str = ""


def http_get(path, headers=None, timeout=TIMEOUT, base_url=None):
    url = (base_url or API_BASE_URL) + path if not path.startswith("http") else path
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        return _parse(r)
    except Exception as e:
        return {"status_code": 0, "body": None, "headers": {}, "error": str(e)}


def http_post(path, body=None, headers=None, timeout=TIMEOUT, base_url=None):
    url = (base_url or API_BASE_URL) + path if not path.startswith("http") else path
    try:
        r = requests.post(url, json=body, headers=headers or {}, timeout=timeout)
        return _parse(r)
    except Exception as e:
        return {"status_code": 0, "body": None, "headers": {}, "error": str(e)}


def http_put(path, body=None, headers=None, timeout=TIMEOUT, base_url=None):
    url = (base_url or API_BASE_URL) + path if not path.startswith("http") else path
    try:
        r = requests.put(url, json=body, headers=headers or {}, timeout=timeout)
        return _parse(r)
    except Exception as e:
        return {"status_code": 0, "body": None, "headers": {}, "error": str(e)}


def http_delete(path, headers=None, timeout=TIMEOUT, base_url=None):
    url = (base_url or API_BASE_URL) + path if not path.startswith("http") else path
    try:
        r = requests.delete(url, headers=headers or {}, timeout=timeout)
        return _parse(r)
    except Exception as e:
        return {"status_code": 0, "body": None, "headers": {}, "error": str(e)}


def _parse(r):
    try:
        body = r.json()
    except Exception:
        body = r.text
    return {
        "status_code": r.status_code,
        "body": body,
        "headers": dict(r.headers),
        "response_time_ms": int(r.elapsed.total_seconds() * 1000),
    }


def docker_exec(container, command, timeout=30):
    try:
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c", command],
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def get_db_connection():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME
    )
    conn.autocommit = True
    return conn


def db_query(sql):
    try:
        import psycopg2.extras
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return {"rows": rows, "row_count": len(rows), "error": None}
    except Exception as e:
        return {"rows": [], "row_count": 0, "error": str(e)}


def save_results(results, filename="eval_results.json"):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, filename)
    data = [asdict(r) if isinstance(r, NodeResult) else r for r in results]
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return path


def print_result(r: NodeResult):
    icon = "✓" if r.status == "PASSED" else ("⊘" if r.status == "SKIPPED_DEPENDENCY" else "✗")
    print(f"  {icon} {r.node_id}: {r.score}/{r.max_score} [{r.status}] {r.message}")
