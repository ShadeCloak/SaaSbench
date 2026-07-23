import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from config import (
    DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, HTTP_TIMEOUT,
)

logger = logging.getLogger(__name__)

context: dict = {}


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    max_score: float
    category: str
    subcategory: str
    message: str
    evidence: dict = field(default_factory=dict)


class ArtifactStore:

    def __init__(self):
        self._store: dict[str, dict] = {}
        self._current_node: Optional[str] = None

    def push_context(self, node_id: str) -> None:
        self._current_node = node_id
        if node_id not in self._store:
            self._store[node_id] = {"evidence": [], "artifacts": {}}

    def pop_context(self) -> None:
        self._current_node = None

    def record(self, key: str, value: Any) -> None:
        if self._current_node and self._current_node in self._store:
            self._store[self._current_node]["artifacts"][key] = value

    def add_evidence(self, evidence_item: dict) -> None:
        if self._current_node and self._current_node in self._store:
            self._store[self._current_node]["evidence"].append(evidence_item)

    def get_evidence(self, node_id: str) -> list[dict]:
        return self._store.get(node_id, {}).get("evidence", [])

    def get_artifact(self, node_id: str, key: str) -> Any:
        return self._store.get(node_id, {}).get("artifacts", {}).get(key)

    def get_all(self) -> dict:
        return self._store


def store_response(r: dict, ctx: dict) -> None:
    ctx["_last_status_code"] = r.get("status_code", 0)
    ctx["_last_response_body"] = r.get("body")
    ctx["_last_response_headers"] = r.get("headers", {})
    ctx["_last_response_time_ms"] = r.get("response_time_ms", 0)
    cid = r.get("created_id")
    if cid is not None:
        ctx["_last_created_id"] = cid


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
    )


def db_query(sql: str, params: Optional[tuple] = None) -> list[dict]:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("db_query failed: %s", e)
        return []


def docker_exec(container: str, command: str) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["docker", "exec", container, "sh", "-c", command],
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        logger.error("docker_exec failed: %s", e)
        return -1, "", str(e)


def save_results(results: list[NodeResult], filepath: str) -> None:
    with open(filepath, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)


def print_summary(results: list[NodeResult]) -> None:
    by_category: dict[str, list[NodeResult]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)

    total_s, total_m = 0.0, 0.0
    for cat, items in sorted(by_category.items()):
        cat_s = sum(r.score for r in items)
        cat_m = sum(r.max_score for r in items)
        total_s += cat_s
        total_m += cat_m
        pct = (cat_s / cat_m * 100) if cat_m > 0 else 0
        print(f"\n=== {cat} ({cat_s:.0f}/{cat_m:.0f} = {pct:.0f}%) ===")
        for r in items:
            sym = "P" if r.score > 0 else ("S" if "SKIP" in r.status else "F")
            print(f"  [{sym}] {r.node_id}: {r.score:.0f}/{r.max_score:.0f} - {r.message[:120]}")

    pct = (total_s / total_m * 100) if total_m > 0 else 0
    print(f"\n{'='*60}")
    print(f"TOTAL: {total_s:.0f}/{total_m:.0f} = {pct:.1f}%")


def _extract_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    if isinstance(obj, list):
        bracket = re.match(r"^(\w+)\[(\d+)\]$", key)
        if bracket:
            return None
        try:
            return obj[int(key)] if 0 <= int(key) < len(obj) else None
        except (ValueError, TypeError):
            return None
    return None


def resolve_placeholders(s: str, ctx: dict) -> str:
    if not isinstance(s, str):
        return s
    result = []
    i = 0
    while i < len(s):
        if s[i:i+2] == "{{":
            end = s.find("}}", i)
            if end == -1:
                result.append(s[i])
                i += 1
                continue
            key_path = s[i+2:end].strip()
            if "(" in key_path or ")" in key_path:
                result.append(s[i:end+2])
                i = end + 2
                continue
            parts = key_path.split(".")
            val = ctx
            for part in parts:
                bracket = re.match(r"^(\w+)\[(\d+)\]$", part)
                if bracket:
                    val = _extract_value(val, bracket.group(1))
                    if isinstance(val, list):
                        idx = int(bracket.group(2))
                        val = val[idx] if 0 <= idx < len(val) else None
                    else:
                        val = None
                else:
                    val = _extract_value(val, part)
                if val is None:
                    break
            result.append(str(val) if val is not None else "")
            i = end + 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def resolve_deep(obj: Any, ctx: dict) -> Any:
    if isinstance(obj, str):
        m = re.fullmatch(r"\{\{\s*([^}]+?)\s*\}\}", obj)
        if m:
            key_path = m.group(1)
            if "(" in key_path or ")" in key_path:
                return obj
            parts = key_path.split(".")
            val = ctx
            for part in parts:
                bracket = re.match(r"^(\w+)\[(\d+)\]$", part)
                if bracket:
                    val = _extract_value(val, bracket.group(1))
                    if isinstance(val, list):
                        idx = int(bracket.group(2))
                        val = val[idx] if 0 <= idx < len(val) else None
                    else:
                        val = None
                else:
                    val = _extract_value(val, part)
                if val is None:
                    break
            return val if val is not None else obj
        return resolve_placeholders(obj, ctx)
    elif isinstance(obj, dict):
        return {k: resolve_deep(v, ctx) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [resolve_deep(v, ctx) for v in obj]
    return obj
