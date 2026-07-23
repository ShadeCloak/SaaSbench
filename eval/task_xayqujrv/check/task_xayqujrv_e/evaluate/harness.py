"""Stage 6.1 — DAG execution engine.

Loads dag.json + scoring_config.json, performs topological sort, executes each
node's primitive_chain in order, applies the configured scoring method, and
reports per-node + per-category + per-trajectory results.

P1-9: Each node has a wall-clock timeout (default 60s). A node that exceeds
its budget is marked status=ERROR with message='wall-clock timeout' so a
single hung primitive cannot freeze the whole evaluation.
"""
from __future__ import annotations

import json
import os
import signal
import time
import traceback
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Any

from primitives import execute_primitive
from utils import NodeResult, resolve_placeholders
from config import TEST_USERS
from _result_compat import _result_passed, _result_message, _result_data


def _inject_test_user_placeholders(ctx: dict) -> None:
    for role, info in TEST_USERS.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx.setdefault(f"{role}_{field}", value)
                ctx.setdefault(f"eval_{role}_{field}", value)


# ============================================================
# ============================================================


try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

class NodeTimeout(Exception):
    pass


@contextmanager
def _node_timeout(seconds: int):
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):
        raise NodeTimeout(f"node exceeded {seconds}s wall-clock budget")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(int(seconds))
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


DEFAULT_NODE_TIMEOUT_S = int(os.environ.get("NODE_TIMEOUT_S", "60"))


# ============================================================
# ============================================================
def _expand_env_placeholders(obj):
    import re
    _ENV_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")

    def _sub(text: str) -> str:
        def _repl(m: "re.Match[str]") -> str:
            var, dflt = m.group(1), m.group(2)
            val = os.environ.get(var)
            if val is not None and val != "":
                return val
            if dflt is not None:
                return dflt
            return m.group(0)
        return _ENV_RE.sub(_repl, text)

    if isinstance(obj, str):
        return _sub(obj) if "${" in obj else obj
    if isinstance(obj, list):
        return [_expand_env_placeholders(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand_env_placeholders(v) for k, v in obj.items()}
    return obj


def load_dag(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        dag = json.load(f)
    return _expand_env_placeholders(dag)


def topological_sort(nodes: list) -> list:
    node_map = {n["id"]: n for n in nodes}
    in_deg = {n["id"]: 0 for n in nodes}
    adj = defaultdict(list)
    for n in nodes:
        for p in n.get("prereqs", []) or []:
            if p in node_map:
                adj[p].append(n["id"])
                in_deg[n["id"]] += 1
    q = deque(nid for nid, d in in_deg.items() if d == 0)
    ordered = []
    while q:
        nid = q.popleft()
        ordered.append(node_map[nid])
        for nb in adj[nid]:
            in_deg[nb] -= 1
            if in_deg[nb] == 0:
                q.append(nb)
    if len(ordered) != len(nodes):
        visited = {n["id"] for n in ordered}
        missing = [n["id"] for n in nodes if n["id"] not in visited]
        raise ValueError(f"DAG has cycle(s) involving: {missing[:5]}")
    return ordered


# ============================================================
# ============================================================
class ArtifactStore:

    def __init__(self):
        self._evidence: dict[str, list] = defaultdict(list)
        self._stack: list[str] = []

    def push(self, node_id: str):
        self._stack.append(node_id)

    def pop(self):
        return self._stack.pop() if self._stack else None

    @property
    def current(self):
        return self._stack[-1] if self._stack else None

    def store(self, key: str, value: Any):
        if self.current:
            self._evidence[self.current].append({"key": key, "value": value})

    def get(self, node_id: str) -> list:
        return list(self._evidence.get(node_id, []))

    def all(self) -> dict:
        return dict(self._evidence)


# ============================================================
# ============================================================
_ENTITY_KEY_MAP = [
    ("feature_segment_override", ("feature_segment_id", "fso_id")),
    ("feature_segment", ("feature_segment_id", "fs_id")),
    ("change_request",  ("change_request_id", "cr_id")),
    ("master_api_key",  ("master_api_key_id", "mk_id")),
    ("user_permission_group", ("user_permission_group_id", "upg_id")),
    ("organisation", ("org_id", "organisation_id")),
    ("environment",  ("env_id", "environment_id")),
    ("multivariate", ("mv_option_id",)),
    ("project",      ("project_id", "pid")),
    ("identity",     ("identity_id",)),
    ("segment",      ("segment_id", "sid")),
    ("feature",      ("feature_id", "fid")),
    ("webhook",      ("webhook_id", "wh_id")),
    ("trait",        ("trait_id",)),
    ("invite",       ("invite_id",)),
    ("tag",          ("tag_id",)),
    ("group",        ("group_id",)),
    ("user",         ("user_id",)),
]


def _drf_unwrap(body: Any) -> dict | None:
    if isinstance(body, dict):
        if "results" in body and isinstance(body["results"], list) and body["results"]:
            first = body["results"][0]
            if isinstance(first, dict):
                return first
        return body
    if isinstance(body, list) and body and isinstance(body[0], dict):
        return body[0]
    return None


def _maybe_extract_ids(node_id: str, body: Any, context: dict):
    obj = _drf_unwrap(body)
    if obj is None:
        return
    nid_lower = node_id.lower()
    nid_parts = set(p for p in nid_lower.replace("-", "_").split("_") if p)

    if "id" in obj and isinstance(obj["id"], (int, str)):
        context["id"] = obj["id"]
        for key_kw, target_keys in _ENTITY_KEY_MAP:
            tokens = key_kw.split("_")
            if all(tok in nid_parts for tok in tokens):
                for tk in target_keys:
                    context[tk] = obj["id"]
                break
    if "uuid" in obj:
        context["uuid"] = obj["uuid"]
    if "api_key" in obj:
        context["last_created_env_api_key"] = obj["api_key"]
        context.setdefault("env_api_key", obj["api_key"])
        context.setdefault("server_env_key", obj["api_key"])
        context.setdefault("_initial_env_api_key", obj["api_key"])


# ============================================================
# ============================================================
def execute_dag(
    dag: dict,
    scoring_config: dict,
    only_category: str | None = None,
    dry_run: bool = False,
    with_llm: bool = False,
) -> list:
    nodes = dag.get("nodes", [])
    if only_category:
        nodes = [n for n in nodes
                 if n.get("scoring", {}).get("category") == only_category]

    sorted_nodes = topological_sort(nodes)

    if dry_run:
        results = []
        for n in sorted_nodes:
            sc = n.get("scoring", {})
            results.append(NodeResult(
                node_id=n["id"], status="DRY_RUN", score=0,
                max_score=sc.get("maxScore", 0),
                category=sc.get("category", ""),
                subcategory=sc.get("subcategory", ""),
                complexity_tier=n.get("complexity_tier", ""),
                message="Dry run", evidence=[], elapsed=0.0,
            ))
        return results

    context: dict = {"_dag_total": len(sorted_nodes)}
    _inject_test_user_placeholders(context)
    artifacts = ArtifactStore()
    passed: set[str] = set()
    results: list = []
    total = len(sorted_nodes)

    for idx, n in enumerate(sorted_nodes, 1):
        nid = n["id"]
        sc = n.get("scoring", {})
        max_score = sc.get("maxScore", 0)
        method = sc.get("method", "binary")
        cat = sc.get("category", "")
        sub = sc.get("subcategory", "")
        tier = n.get("complexity_tier", "")
        chain = n.get("primitive_chain", []) or []

        print(f"[{idx}/{total}] {nid}: running...", end="", flush=True)
        artifacts.push(nid)
        t0 = time.time()
        prim_results = []
        chain_error = None

        node_timeout = int(n.get("_timeout_s", DEFAULT_NODE_TIMEOUT_S))
        try:
          with _node_timeout(node_timeout):
            for prim in chain:
                ptype = prim["type"]
                resolved = resolve_placeholders(prim.get("inputs", {}) or {}, context)
                pr = execute_primitive(ptype, resolved, context)
                prim_results.append((ptype, pr))

                _passed = _result_passed(pr)
                _data = _result_data(pr)
                ev = {"primitive": ptype, "success": _passed, "message": _result_message(pr)}
                if _data and isinstance(_data, dict):
                    snippet = {}
                    for k, v in _data.items():
                        if isinstance(v, (str, int, float, bool)) or v is None:
                            snippet[k] = v
                        elif isinstance(v, (list, dict)):
                            try:
                                snippet[k] = json.loads(json.dumps(v, default=str)[:1000])
                            except Exception:
                                snippet[k] = str(v)[:300]
                    ev["data"] = snippet
                artifacts.store(f"{ptype}_step", ev)

                if ptype == "P04" and _passed:
                    body = context.get("last_body")
                    if isinstance(body, dict):
                        _maybe_extract_ids(nid, body, context)

                if not _passed and method == "binary":
                    break
        except NodeTimeout as to_exc:
            chain_error = f"WALL_CLOCK_TIMEOUT: {to_exc}"
            artifacts.store("timeout", {
                "node_timeout_s": node_timeout,
                "primitives_completed": len(prim_results),
                "primitives_pending": len(chain) - len(prim_results),
            })
        except Exception as exc:
            chain_error = str(exc)
            artifacts.store("error", {
                "exception": chain_error,
                "trace": traceback.format_exc(limit=5),
            })

        elapsed = time.time() - t0
        passed_n = sum(1 for _, r in prim_results if r.success)
        total_n = len(chain)

        if chain_error:
            score = 0
            status = "ERROR"
            msg = f"Error: {chain_error}"
        elif method == "binary":
            score = max_score if (passed_n == total_n and total_n > 0) else 0
            status = "PASSED" if score > 0 else "FAILED"
            failed_steps = [pt for pt, r in prim_results if not r.success]
            msg = ("All primitives passed" if status == "PASSED"
                   else f"Failed primitives: {failed_steps}")
        elif method == "weighted":
            score = round((passed_n / total_n) * max_score, 1) if total_n else 0
            status = "PASSED" if score > 0 else "FAILED"
            msg = f"{passed_n}/{total_n} primitives passed"
        elif method == "llm-judge":
            p17 = next((r for pt, r in prim_results if pt == "P17"), None)
            if p17 and isinstance(p17.data, dict) and p17.data.get("skipped"):
                score = 0
                status = "SKIPPED_LLM"
                msg = p17.message
            elif p17 and p17.success:
                score = p17.data.get("llm_score", p17.data.get("score", 0))
                status = "PASSED" if score > 0 else "FAILED"
                msg = p17.message
            else:
                score = 0
                status = "FAILED"
                msg = (p17.message if p17 else "No P17 result")
        else:
            score = 0
            status = "FAILED"
            msg = f"unknown scoring method: {method}"

        print(f" {status} ({elapsed:.1f}s) score={score}/{max_score}")
        if status == "PASSED":
            passed.add(nid)

        artifacts.pop()
        results.append(NodeResult(
            node_id=nid, status=status, score=score, max_score=max_score,
            category=cat, subcategory=sub, complexity_tier=tier,
            message=msg, evidence=artifacts.get(nid), elapsed=round(elapsed, 2),
        ))

    return results


# ============================================================
# ============================================================
SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate_results(results: list, scoring_config: dict) -> dict:
    total_score = 0.0
    total_max = 0.0
    skipped_llm_max = 0.0
    by_cat: dict[str, dict] = defaultdict(
        lambda: {"score": 0.0, "maxScore": 0.0, "passed": 0, "failed": 0,
                 "skipped": 0, "skipped_llm": 0, "error": 0}
    )
    by_tier: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "maxScore": 0.0,
                                                     "skipped_llm": 0})
    node_details = []

    for r in results:
        c = by_cat[r.category]
        t = by_tier[r.complexity_tier]
        is_skipped_llm = r.status in SKIP_FROM_TOTAL
        if is_skipped_llm:
            c["skipped_llm"] += 1
            c["skipped"] += 1
            t["skipped_llm"] += 1
            skipped_llm_max += r.max_score
        else:
            c["score"] += r.score
            c["maxScore"] += r.max_score
            t["score"] += r.score
            t["maxScore"] += r.max_score
            total_score += r.score
            total_max += r.max_score
            if r.status == "PASSED":
                c["passed"] += 1
            elif r.status == "FAILED":
                c["failed"] += 1
            elif r.status in ("SKIPPED_DEPENDENCY", "DRY_RUN"):
                c["skipped"] += 1
            else:
                c["error"] += 1
        node_details.append({
            "node_id": r.node_id, "status": r.status,
            "score": r.score, "maxScore": r.max_score,
            "message": r.message[:200], "elapsed_s": r.elapsed,
        })

    for c in by_cat.values():
        c["pct"] = round(c["score"] / c["maxScore"] * 100, 1) if c["maxScore"] else 0.0
    for t in by_tier.values():
        t["pct"] = round(t["score"] / t["maxScore"] * 100, 1) if t["maxScore"] else 0.0

    traj_cfg = scoring_config.get("trajectories", {}) or {}
    rmap = {r.node_id: r for r in results}
    by_traj = {}
    for tname, tinfo in traj_cfg.items():
        ids = tinfo.get("node_ids", [])
        tmax = 0.0
        tscore = 0.0
        tskipped = 0
        for i in ids:
            r = rmap.get(i)
            if r is None:
                continue
            if r.status in SKIP_FROM_TOTAL:
                tskipped += 1
                continue
            tmax += r.max_score
            tscore += r.score
        by_traj[tname] = {
            "score": tscore, "maxScore": tmax,
            "pct": round(tscore / tmax * 100, 1) if tmax else 0.0,
            "skipped_llm": tskipped,
        }

    pct = round(total_score / total_max * 100, 1) if total_max else 0.0
    cfg_max_raw = scoring_config.get("total_maxScore", total_max)
    cfg_max = max(0.0, cfg_max_raw - skipped_llm_max)
    normalized = round(total_score / cfg_max * 100, 1) if cfg_max else 0.0

    return {
        "overall": {
            "score": total_score,
            "maxScore": total_max,
            "pct": pct,
            "normalized_score": normalized,
        },
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "by_category": dict(by_cat),
        "by_complexity": dict(by_tier),
        "by_trajectory": by_traj,
        "node_details": node_details,
    }


def generate_report(results: list, scoring_config: dict, output_path: str) -> str:
    report = aggregate_results(results, scoring_config)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    return output_path
