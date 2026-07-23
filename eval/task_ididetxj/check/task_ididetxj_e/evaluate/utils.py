from __future__ import annotations

import dataclasses
import json
import logging
import subprocess
import time
from typing import Any

import requests

import config

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("eval")


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
@dataclasses.dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    maxScore: float
    category: str = ""
    subcategory: str = ""
    method: str = "binary"
    message: str = ""
    evidence: dict | None = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        if d["evidence"] is None:
            d["evidence"] = {}
        return d


@dataclasses.dataclass
class PrimitiveResult:
    type: str
    passed: bool
    message: str = ""
    data: dict | None = None
    response_time_ms: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
def http_request(method: str, path: str, *, headers: dict | None = None,
                 body: dict | str | None = None,
                 timeout: int = config.DEFAULT_HTTP_TIMEOUT,
                 base_url: str = config.APP_BASE_URL) -> dict:
    url = base_url + path if path.startswith("/") else f"{base_url}/{path}"
    headers = headers or {}
    if isinstance(body, dict):
        headers.setdefault("Content-Type", "application/json")
        data = json.dumps(body)
    else:
        data = body
    headers.setdefault("Connection", "close")

    last_err = None
    t0 = time.time()
    for attempt in range(3):
        try:
            resp = requests.request(method.upper(), url, headers=headers, data=data,
                                     timeout=timeout)
            elapsed = int((time.time() - t0) * 1000)
            try:
                payload = resp.json()
            except Exception:
                payload = resp.text
            return {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": payload,
                "response_time_ms": elapsed,
            }
        except requests.exceptions.Timeout as e:
            last_err = ("timeout", e)
        except requests.exceptions.ConnectionError as e:
            last_err = ("connection_error", e)
        except Exception as e:
            last_err = ("error", e)
        time.sleep(0.2 * (attempt + 1))

    msg, e = last_err
    return {
        "status_code": -1,
        "error": f"{msg}: {e}",
        "response_time_ms": int((time.time() - t0) * 1000),
        "body": None,
        "headers": {},
    }


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
def docker_exec(container: str, command: str, *, timeout: int = 60) -> dict:
    cmd = ["docker", "exec", container, "bash", "-lc", command]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": out.returncode, "stdout": out.stdout, "stderr": out.stderr}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"timeout after {timeout}s"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
def db_query(sql: str, *, timeout: int = 15) -> dict:
    safe_sql = sql.replace("\n", " ")
    cmd = ["docker", "exec", config.DB_CONTAINER,
           "psql", "-U", config.DB_USER, "-d", config.DB_NAME,
           "-A", "-t", "-F", "|", "-P", "pager=off", "-c", safe_sql]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            return {"ok": False, "rows": [], "error": out.stderr.strip(), "raw_stdout": out.stdout}
        rows = []
        for line in out.stdout.strip().split("\n"):
            if not line.strip():
                continue
            cells = line.split("|")
            rows.append(cells)
        return {"ok": True, "rows": rows, "raw_stdout": out.stdout}
    except Exception as e:
        return {"ok": False, "rows": [], "error": str(e)}


def db_query_dict(sql: str, columns: list[str] | None = None, **kw) -> dict:
    res = db_query(sql, **kw)
    if not res["ok"]:
        return res
    if columns is None:
        m = sql.strip().lstrip("(").upper().split("SELECT", 1)
        if len(m) > 1:
            cols_part = m[1].split("FROM", 1)[0].strip()
            if cols_part != "*":
                columns = [c.split(" AS ")[-1].strip().strip('"') for c in cols_part.split(",")]
    if columns:
        res["dict_rows"] = [dict(zip(columns, row)) for row in res["rows"]]
    return res


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
def jsonpath_get(obj: Any, path: str) -> Any:
    if path == "$":
        return obj
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        while "[" in part:
            key, _, rest = part.partition("[")
            idx_str, _, after = rest.partition("]")
            if key:
                cur = cur.get(key) if isinstance(cur, dict) else None
            try:
                cur = cur[int(idx_str)]
            except (TypeError, IndexError, ValueError):
                return None
            part = after.lstrip(".")
            if not part:
                break
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
def fmt_result(r: NodeResult) -> str:
    icon = {"PASSED": "✓", "PARTIAL": "~", "FAILED": "✗", "ERROR": "!", "SKIPPED_DEPENDENCY": "·"}.get(r.status, "?")
    return f"  {icon} {r.node_id:60s}  {r.score:5.1f}/{r.maxScore:5.1f}  {r.status:8s}  {r.message[:60]}"


def save_results(results: list[NodeResult], path: str) -> None:
    total_score = sum(float(r.score) for r in results)
    total_max = sum(float(r.maxScore) for r in results)
    pct = (100.0 * total_score / total_max) if total_max else 0.0
    payload = {
        "version": "1.0",
        "total_score": round(total_score, 2),
        "total_maxScore": round(total_max, 2),
        "percentage": round(pct, 2),
        "results": [r.to_dict() for r in results],
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    log.info("Wrote %d node results → %s", len(results), path)
