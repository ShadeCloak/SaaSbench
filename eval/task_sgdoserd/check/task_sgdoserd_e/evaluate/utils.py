import json
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Any

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


@dataclass
class PrimitiveResult:
    type: str
    passed: bool
    output: Any = None
    error: str = ""
    extras: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


# ---------------- HTTP helpers ----------------
def http_request(method: str, path: str, *, body=None, headers=None, token=None,
                 base_url: str = None, timeout: int = None) -> dict:
    import time
    url = path if path.startswith("http") else (base_url or config.APP_BASE_URL) + path
    if not url.startswith("http"):
        url = config.APP_BASE_URL + path
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
        else:
            data = body if isinstance(body, bytes) else str(body).encode("utf-8")
    t0 = time.monotonic()
    try:
        r = requests.request(method.upper(), url, data=data, headers=h,
                             timeout=timeout or config.HTTP_TIMEOUT, allow_redirects=False)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        try:
            jb = r.json() if r.text else None
        except Exception:
            jb = None
        return {"status": r.status_code, "headers": dict(r.headers), "body": jb,
                "raw": r.text, "error": "", "elapsed_ms": elapsed_ms}
    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return {"status": 0, "headers": {}, "body": None, "raw": "", "error": str(e),
                "elapsed_ms": elapsed_ms}


def docker_exec(container: str, command: str, *, timeout: int = None) -> dict:
    try:
        r = subprocess.run(
            ["docker", "exec", container, "sh", "-c", command],
            capture_output=True, text=True,
            timeout=timeout or config.DOCKER_EXEC_TIMEOUT,
        )
        return {"exit": r.returncode, "stdout": r.stdout, "stderr": r.stderr, "error": ""}
    except subprocess.TimeoutExpired as e:
        return {"exit": -1, "stdout": "", "stderr": "", "error": f"timeout after {e.timeout}s"}
    except Exception as e:
        return {"exit": -1, "stdout": "", "stderr": "", "error": str(e)}


def docker_psql(sql: str, *, container: str = None) -> dict:
    container = container or config.DB_CONTAINER
    cmd = [
        "docker", "exec", "-i",
        "-e", f"PGPASSWORD={config.DB_PASSWORD}",
        container,
        "psql", "-U", config.DB_USER, "-d", config.DB_NAME,
        "-h", "localhost",
        "-A", "-F", "|", "-t",
        "-v", "ON_ERROR_STOP=on",
    ]
    try:
        r = subprocess.run(
            cmd, input=sql, capture_output=True, text=True,
            timeout=config.DB_TIMEOUT,
        )
        out = {"exit": r.returncode, "stdout": r.stdout, "stderr": r.stderr, "error": ""}
    except subprocess.TimeoutExpired as e:
        out = {"exit": -1, "stdout": "", "stderr": "", "error": f"timeout after {e.timeout}s"}
    except Exception as e:
        out = {"exit": -1, "stdout": "", "stderr": "", "error": str(e)}
    rows = []
    if out["exit"] == 0:
        for line in out["stdout"].strip().split("\n"):
            if line.strip():
                rows.append(line.split("|"))
    out["rows"] = rows
    return out


# ---------------- Result helpers ----------------
def print_result(result: NodeResult):
    icon = {"PASSED": "✓", "PARTIAL": "~", "FAILED": "✗", "ERROR": "!",
            "SKIPPED_DEPENDENCY": "○", "SKIPPED_LLM": "L", "DRY_RUN": "·"}.get(result.status, "?")
    pct = f"{result.score:.1f}/{result.maxScore}"
    print(f"  [{icon}] {result.node_id:55s} {pct:>10s} {result.category}/{result.subcategory}")


def save_results(results: list, path: str):
    data = [r.to_dict() if hasattr(r, "to_dict") else r for r in results]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------- JSON path helpers ----------------
def json_path_get(obj, path: str):
    if path in ("$", ""):
        return obj
    if path.startswith("$"):
        path = path[1:].lstrip(".")
    if not path:
        return obj
    cur = obj
    tokens = []
    buf = ""
    i = 0
    while i < len(path):
        c = path[i]
        if c == ".":
            if buf:
                tokens.append(buf)
                buf = ""
        elif c == "[":
            if buf:
                tokens.append(buf)
                buf = ""
            j = path.index("]", i)
            tokens.append(int(path[i+1:j]))
            i = j
        else:
            buf += c
        i += 1
    if buf:
        tokens.append(buf)
    for t in tokens:
        if cur is None:
            return None
        if isinstance(t, int):
            try:
                cur = cur[t]
            except (IndexError, KeyError, TypeError):
                return None
        else:
            if isinstance(cur, dict):
                cur = cur.get(t)
            else:
                return None
    return cur


def render_template(s: str, ctx: dict) -> str:
    if not isinstance(s, str):
        return s
    import re
    def sub(m):
        v = ctx.get(m.group(1))
        return str(v) if v is not None else m.group(0)
    return re.sub(r"\{\{(\w+)\}\}", sub, s)


def render_obj(obj, ctx: dict):
    if isinstance(obj, dict):
        return {k: render_obj(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render_obj(x, ctx) for x in obj]
    if isinstance(obj, str):
        return render_template(obj, ctx)
    return obj
