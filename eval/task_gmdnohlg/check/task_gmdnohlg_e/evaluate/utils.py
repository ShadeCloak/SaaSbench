import requests
import subprocess
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from config import APP_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT, RESULTS_DIR


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


def http_request(method, path, headers=None, body=None, timeout=HTTP_TIMEOUT, base_url=None):
    url = (base_url or APP_BASE_URL) + path
    _headers = {"Accept": "application/json"}
    if headers:
        _headers.update(headers)
    try:
        resp = requests.request(
            method=method, url=url, headers=_headers,
            json=body if isinstance(body, dict) else None,
            data=body if isinstance(body, str) else None,
            timeout=timeout, allow_redirects=False, verify=False
        )
        try:
            resp_json = resp.json()
        except Exception:
            resp_json = None
        return {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp_json,
            "body_text": resp.text[:5000],
            "response_time_ms": int(resp.elapsed.total_seconds() * 1000)
        }
    except requests.exceptions.Timeout:
        return {"status_code": 0, "headers": {}, "body": None, "body_text": "TIMEOUT", "response_time_ms": timeout * 1000}
    except Exception as e:
        return {"status_code": 0, "headers": {}, "body": None, "body_text": str(e), "response_time_ms": 0}


def docker_exec(container, command, timeout=30):
    try:
        result = subprocess.run(
            ["docker", "exec", container] + (command if isinstance(command, list) else command.split()),
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "TIMEOUT"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def db_query(sql, fetch=True):
    import psycopg2
    from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    try:
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        if fetch and cur.description:
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            result = [dict(zip(columns, row)) for row in rows]
            cur.close()
            conn.close()
            return result
        cur.close()
        conn.close()
        return []
    except Exception as e:
        return {"error": str(e)}


def save_results(results, filename="evaluation_results.json"):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    return path


def print_result(result: NodeResult):
    icon = "[OK]" if result.status == "PASSED" else "[FAIL]" if result.status == "FAILED" else "[SKIP]"
    msg = f"  {icon} {result.node_id}: {result.score}/{result.maxScore} ({result.status}) {result.message}"
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode())
