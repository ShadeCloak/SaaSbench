
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    pymysql = None

from . import config

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

logger = logging.getLogger("pfm.eval")
if not logger.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


@dataclass
class PrimitiveResult:

    passed: bool = False
    data: Any = None
    error: Optional[str] = None
    elapsed_ms: int = 0
    evidence: dict = field(default_factory=dict)


@dataclass
class NodeResult:

    node_id: str
    status: str
    score: float
    maxScore: float
    category: str
    subcategory: str = ""
    message: str = ""
    evidence: dict = field(default_factory=dict)
    elapsed_ms: int = 0


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


class HTTPResponseLike:

    def __init__(self, status_code: int, headers: dict, body: bytes, elapsed_ms: int, url: str):
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.elapsed_ms = elapsed_ms
        self.url = url

    @property
    def text(self) -> str:
        try:
            return self.body.decode("utf-8", errors="replace")
        except Exception:
            return ""

    @property
    def json_body(self) -> Any:
        try:
            return json.loads(self.text)
        except Exception:
            return None


def http_request(
    method: str,
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    json_body: Any = None,
    data: Any = None,
    files: Any = None,
    timeout: Optional[int] = None,
    allow_redirects: bool = True,
) -> HTTPResponseLike:
    if requests is None:
        return HTTPResponseLike(0, {}, b"", 0, url)
    start = time.time()
    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            params=params,
            json=json_body,
            data=data,
            files=files,
            timeout=timeout or config.HTTP_TIMEOUT,
            allow_redirects=allow_redirects,
        )
        elapsed = int((time.time() - start) * 1000)
        return HTTPResponseLike(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            body=resp.content,
            elapsed_ms=elapsed,
            url=resp.url,
        )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        logger.warning("http_request %s %s failed: %s", method, url, e)
        return HTTPResponseLike(0, {"x-error": str(e)[:500]}, b"", elapsed, url)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def db_conn():
    if pymysql is None:
        raise RuntimeError("pymysql is not installed; `pip install pymysql`")
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=config.DB_TIMEOUT,
        read_timeout=config.DB_TIMEOUT,
        write_timeout=config.DB_TIMEOUT,
        charset="utf8mb4",
    )


def db_query(sql: str, params: tuple | list | None = None) -> list[dict]:
    try:
        conn = db_conn()
    except Exception as e:
        logger.warning("db_query: connection failed: %s", e)
        return []
    try:
        with conn.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchall()
            return list(rows)
    except Exception as e:
        logger.warning("db_query exception: %s | sql=%s", e, sql[:200])
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def db_execute(sql: str, params: tuple | list | None = None) -> bool:
    try:
        conn = db_conn()
    except Exception as e:
        logger.warning("db_execute: connection failed: %s", e)
        return False
    try:
        with conn.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            conn.commit()
            return True
    except Exception as e:
        logger.warning("db_execute exception: %s | sql=%s", e, sql[:200])
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def db_execute_rowcount(sql: str, params: tuple | list | None = None):
    try:
        conn = db_conn()
    except Exception as e:
        logger.warning("db_execute_rowcount: connection failed: %s", e)
        return None
    try:
        with conn.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rc = cur.rowcount
            conn.commit()
            return rc
    except Exception as e:
        logger.warning("db_execute_rowcount exception: %s | sql=%s", e, sql[:200])
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def docker_exec(
    container: Optional[str] = None,
    command: str = "echo ok",
    *,
    timeout: Optional[int] = None,
    user: Optional[str] = None,
) -> tuple[int, str, str]:
    cont = container or config.APP_CONTAINER
    cmd = ["docker", "exec"]
    if user:
        cmd += ["-u", user]
    cmd += [cont, "bash", "-lc", command]
    try:
        proc = subprocess.run(
            cmd,
            timeout=timeout or config.DOCKER_EXEC_TIMEOUT,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return 124, "", f"Timeout after {e.timeout}s"
    except FileNotFoundError:
        return 127, "", "docker CLI not found on PATH"
    except Exception as e:
        return 1, "", f"docker exec failed: {e}"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import re as _re

_PLACEHOLDER_RE = _re.compile(r"\{\{([A-Za-z_][\w.\[\]]*)\}\}")


def _resolve_dotted(root: Any, dotted: str) -> Any:
    cur = root
    for token in _re.findall(r"[A-Za-z_]\w*|\[[^\]]+\]", dotted):
        if cur is None:
            return None
        if token.startswith("["):
            inner = token[1:-1].strip().strip("'\"")
            try:
                if inner.lstrip("-").isdigit():
                    cur = cur[int(inner)]
                else:
                    cur = cur[inner]
            except (KeyError, IndexError, TypeError):
                return None
        else:
            if isinstance(cur, dict):
                cur = cur.get(token)
            else:
                cur = getattr(cur, token, None)
    return cur


def substitute_placeholders(payload: Any, context: dict) -> Any:
    if isinstance(payload, str):
        def _sub(m: _re.Match) -> str:
            expr = m.group(1)
            if "." in expr or "[" in expr:
                head, _, rest = expr.partition(".")
                root = context.get(head)
                if root is None:
                    return m.group(0)
                json_body = getattr(root, "json_body", None)
                if json_body is not None and rest and not rest.startswith("json_body"):
                    val = _resolve_dotted(json_body, rest)
                else:
                    val = _resolve_dotted(root, rest) if rest else root
            else:
                val = context.get(expr)
            if val is None:
                return m.group(0)
            return str(val)
        return _PLACEHOLDER_RE.sub(_sub, payload)
    if isinstance(payload, list):
        return [substitute_placeholders(x, context) for x in payload]
    if isinstance(payload, dict):
        return {k: substitute_placeholders(v, context) for k, v in payload.items()}
    return payload


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def save_results(results: list[NodeResult], out_path: Path | str) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "results": [asdict(r) for r in results],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": config.dump(),
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    logger.info("Saved %d results to %s", len(results), out)


def print_result(r: NodeResult) -> None:
    mark = "OK" if r.score >= r.maxScore else ("PARTIAL" if r.score > 0 else "FAIL")
    if r.status == "SKIPPED_DEPENDENCY":
        mark = "SKIP"
    print(f"  [{mark:^7}] {r.node_id:<45} {r.score:>6.2f}/{r.maxScore:<5}  {r.category:<32}  {r.message[:120]}")
