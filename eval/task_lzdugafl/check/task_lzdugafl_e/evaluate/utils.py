import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import requests

import config


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


def http_get(path: str, headers: Optional[dict] = None, params: Optional[dict] = None, timeout: int = config.HTTP_TIMEOUT) -> requests.Response:
    url = path if path.startswith("http") else config.APP_BASE_URL + path
    return requests.get(url, headers=headers or {}, params=params, timeout=timeout, allow_redirects=False)


def http_post(path: str, json_data: Any = None, headers: Optional[dict] = None, timeout: int = config.HTTP_TIMEOUT) -> requests.Response:
    url = path if path.startswith("http") else config.APP_BASE_URL + path
    return requests.post(url, json=json_data, headers=headers or {}, timeout=timeout)


def http_patch(path: str, json_data: Any = None, headers: Optional[dict] = None, timeout: int = config.HTTP_TIMEOUT) -> requests.Response:
    url = path if path.startswith("http") else config.APP_BASE_URL + path
    return requests.patch(url, json=json_data, headers=headers or {}, timeout=timeout)


def http_delete(path: str, headers: Optional[dict] = None, timeout: int = config.HTTP_TIMEOUT) -> requests.Response:
    url = path if path.startswith("http") else config.APP_BASE_URL + path
    return requests.delete(url, headers=headers or {}, timeout=timeout)


def docker_exec(command: str, container: str = config.APP_CONTAINER) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", container, "bash", "-c", command],
        capture_output=True, text=True, timeout=60,
    )


def db_query(sql: str) -> list:
    import pymysql
    conn = pymysql.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME, cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        conn.close()


def save_results(results: dict, filename: str = "evaluation_report.json"):
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    path = os.path.join(config.RESULTS_DIR, filename)
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {path}")


def print_summary(report: dict):
    print("\n" + "=" * 60)
    print(f"EVALUATION REPORT — {report.get('task_id', 'unknown')}")
    print("=" * 60)
    total = report.get("total_score", 0)
    max_total = report.get("total_maxScore", 0)
    pct = (total / max_total * 100) if max_total > 0 else 0
    print(f"Total Score: {total:.1f} / {max_total} ({pct:.1f}%)")
    print("-" * 60)
    for cat in report.get("categories", []):
        s = cat["score"]
        m = cat["maxScore"]
        p = (s / m * 100) if m > 0 else 0
        print(f"  {cat['category']:25s} {s:6.1f} / {m:3d}  ({p:5.1f}%)")
    print("=" * 60)
