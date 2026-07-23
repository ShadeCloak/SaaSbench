from __future__ import annotations

import json
import re
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from typing import Any

from . import config
from .primitives import run_primitive
from .utils import (NodeResult, PrimitiveResult, db_query,
                       print_node, save_results)


def _inject_test_user_placeholders(ctx: dict) -> None:
    test_users = getattr(config, "TEST_USERS", None) or {}
    for role, info in test_users.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx.setdefault(f"{role}_{field}", value)
                ctx.setdefault(f"eval_{role}_{field}", value)


try:
    from ._dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)



# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def load_dag(path: Path | None = None) -> dict:
    p = path or config.DAG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def topological_sort(nodes: list[dict]) -> list[str]:
    indeg = {n["id"]: 0 for n in nodes}
    edges: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for pre in n.get("prereqs") or []:
            if pre in indeg:
                edges[pre].append(n["id"])
                indeg[n["id"]] += 1
    queue = deque([nid for nid, d in indeg.items() if d == 0])
    out = []
    while queue:
        nid = queue.popleft()
        out.append(nid)
        for nxt in edges[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(out) != len(nodes):
        cyclic = [nid for nid, d in indeg.items() if d > 0]
        raise ValueError(f"Cycle detected in DAG; offending nodes: {cyclic[:10]}")
    return out


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _all_prereqs_passed(prereqs: list[str], results: dict[str, NodeResult]) -> bool:
    for pre in prereqs:
        r = results.get(pre)
        if not r or r.status != "EXECUTED":
            return False
    return True


def execute_node(node: dict, ctx: dict) -> NodeResult:
    chain = node.get("primitive_chain") or []
    method = node["scoring"]["method"]
    max_score = node["scoring"]["maxScore"]
    category = node["scoring"]["category"]
    subcategory = node["scoring"].get("subcategory", "")
    primitive_results: list[PrimitiveResult] = []

    overall_passed = True
    pass_count = 0
    llm_score: float | None = None
    judge_skipped = False

    for i, step in enumerate(chain):
        try:
            res = run_primitive(step, ctx)
        except Exception as e:
            res = PrimitiveResult(step.get("type", "??"), False,
                                    f"unhandled in harness: {e}")
        primitive_results.append(res)
        if step.get("type") == "P17":
            data = res.data or {}
            if data.get("skipped"):
                judge_skipped = True
            elif res.passed:
                llm_score = data.get("score")
        if res.passed:
            pass_count += 1
        else:
            overall_passed = False

        _harvest_ids_from_response(node, res, ctx)

    if method == "binary":
        score = max_score if overall_passed else 0.0
    elif method == "weighted":
        explicit_ratio = None
        for res in primitive_results:
            if res.data and "pass_ratio" in res.data:
                explicit_ratio = res.data["pass_ratio"]
        if explicit_ratio is not None:
            score = round(explicit_ratio * max_score, 2)
        else:
            ratio = pass_count / max(1, len(chain))
            score = round(ratio * max_score, 2)
    elif method == "llm-judge":
        score_range = None
        for step in chain:
            if step.get("type") == "P17":
                score_range = (step.get("inputs") or {}).get("score_range")
                break
        if llm_score is not None and score_range:
            lo, hi = float(score_range[0]), float(score_range[1])
            ratio = (llm_score - lo) / max(0.001, hi - lo)
            ratio = max(0.0, min(1.0, ratio))
            score = round(ratio * max_score, 2)
        else:
            score = max_score if overall_passed else 0.0
    else:
        score = max_score if overall_passed else 0.0

    status = "EXECUTED"
    if method == "llm-judge" and judge_skipped:
        status = "SKIPPED_LLM"
        score = 0.0
    msg = "; ".join(r.message for r in primitive_results if not r.passed)[:300] \
        if not overall_passed else "OK"

    return NodeResult(
        node_id=node["id"],
        status=status,
        score=score,
        maxScore=float(max_score),
        category=category,
        subcategory=subcategory,
        method=method,
        message=msg,
        primitive_results=primitive_results,
        evidence={
            "ctx_keys": [k for k in ctx if not k.startswith("__")][:20],
        },
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

ENTITY_ID_RULES = [
    ("PATIENT",      {"puuid": ["data.uuid", "uuid"],
                       "pid":   ["data.pid", "data.id", "pid"]}),
    ("ENCOUNTER",    {"euuid": ["data.euuid", "data.uuid", "euuid", "uuid"],
                       "eid":   ["data.eid", "data.id", "eid"]}),
    ("APPOINTMENT",  {"pc_eid": ["data.pc_eid", "data.id", "pc_eid", "id"]}),
    ("PRACTITIONER", {"pruuid": ["data.uuid", "uuid"]}),
    ("FACILITY",     {"fuuid": ["data.uuid", "uuid"],
                       "fid":   ["data.id", "id"]}),
    ("INSURANCE_COMPANY", {"icuuid": ["data.uuid", "uuid"],
                            "icid":  ["data.id", "id"]}),
    ("PRESCRIPTION", {"rx_uuid": ["data.uuid", "uuid"],
                       "rx_id":  ["data.id", "id"]}),
    ("DOCUMENT",     {"doc_uuid": ["data.uuid", "uuid"],
                       "doc_id":  ["data.id", "id"]}),
    ("CLIENT_REGISTRATION", {"client_id": ["client_id"],
                              "client_secret": ["client_secret"]}),
    ("AUTHORIZATION_CODE",  {"access_token": ["access_token"],
                              "refresh_token": ["refresh_token"]}),
]


def _resolve_json_path(body: Any, path: str) -> Any:
    cur = body
    parts = path.split(".")
    for idx, part in enumerate(parts):
        if isinstance(cur, list) and len(cur) == 1:
            cur = cur[0]
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif idx == len(parts) - 1 and isinstance(cur, (str, int)) and part in ("uuid", "id", "pid", "eid", "pc_eid"):
            pass
        else:
            return None
    if isinstance(cur, list) and len(cur) == 1:
        cur = cur[0]
    return cur


def _harvest_ids_from_response(node: dict, res: PrimitiveResult, ctx: dict) -> None:
    nid = node["id"]
    body = ctx.get("__last_response_json")
    if not isinstance(body, (dict, list)):
        return
    last_status = ctx.get("last_status")
    if isinstance(last_status, int) and not (200 <= last_status < 300):
        return
    for keyword, key_paths in ENTITY_ID_RULES:
        if keyword not in nid:
            continue
        for ck, candidate_paths in key_paths.items():
            if ck in ctx:
                continue
            for jp in candidate_paths:
                val = _resolve_json_path(body, jp)
                if val is not None and val != "" and not isinstance(val, (dict, list)):
                    ctx[ck] = val
                    break

    if "BULK_EXPORT_INIT" in nid:
        last_summary = ctx.get("__last_response_summary") or {}
        cl = (last_summary.get("headers") or {}).get("Content-Location")
        if cl:
            ctx["bulk_export_status_url"] = cl


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def execute_dag(dag: dict, *, only_category: str | None = None,
                dry_run: bool = False, only_node_ids: set[str] | None = None,
                ) -> list[NodeResult]:
    nodes_by_id = {n["id"]: n for n in dag["nodes"]}
    ordered = topological_sort(dag["nodes"])
    ctx: dict[str, Any] = {}
    _inject_test_user_placeholders(ctx)
    results: dict[str, NodeResult] = {}

    for nid in ordered:
        n = nodes_by_id[nid]
        if only_category and n["scoring"]["category"] != only_category:
            results[nid] = NodeResult(
                node_id=nid, status="EXECUTED",
                score=0, maxScore=0,
                category=n["scoring"]["category"],
                subcategory=n["scoring"].get("subcategory", ""),
                method=n["scoring"]["method"],
                message="filtered out by --only-category",
            )
            continue
        if only_node_ids and nid not in only_node_ids:
            continue
        if not _all_prereqs_passed(n.get("prereqs") or [], results):
            r = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY",
                score=0, maxScore=float(n["scoring"]["maxScore"]),
                category=n["scoring"]["category"],
                subcategory=n["scoring"].get("subcategory", ""),
                method=n["scoring"]["method"],
                message="prereq did not pass",
            )
            results[nid] = r
            print_node(r)
            continue

        if dry_run:
            r = NodeResult(
                node_id=nid, status="EXECUTED",
                score=n["scoring"]["maxScore"], maxScore=float(n["scoring"]["maxScore"]),
                category=n["scoring"]["category"],
                subcategory=n["scoring"].get("subcategory", ""),
                method=n["scoring"]["method"],
                message="dry-run pretend pass",
            )
            results[nid] = r
            print_node(r)
            continue
        r = execute_node(n, ctx)
        results[nid] = r
        print_node(r)

    return [results[nid] for nid in ordered if nid in results]


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate(results: list[NodeResult]) -> dict:
    by_cat = defaultdict(lambda: {"score": 0.0, "max": 0.0, "n": 0,
                                     "executed": 0, "skipped": 0,
                                     "skipped_llm": 0, "errored": 0})
    total_score = total_max = 0.0
    skipped_llm_max = 0.0
    for r in results:
        c = by_cat[r.category]
        c["n"] += 1
        if r.status == "EXECUTED":
            c["executed"] += 1
        elif r.status == "SKIPPED_DEPENDENCY":
            c["skipped"] += 1
        elif r.status == "SKIPPED_LLM":
            c["skipped_llm"] += 1
        else:
            c["errored"] += 1

        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.maxScore
            continue
        c["score"] += r.score
        c["max"] += r.maxScore
        total_score += r.score
        total_max += r.maxScore

    cats = OrderedDict()
    for k in sorted(by_cat.keys()):
        v = by_cat[k]
        cats[k] = {
            "score": round(v["score"], 2),
            "max": round(v["max"], 2),
            "pct": round(100.0 * v["score"] / max(1, v["max"]), 1),
            "node_count": v["n"],
            "executed": v["executed"],
            "skipped": v["skipped"],
            "skipped_llm": v["skipped_llm"],
            "errored": v["errored"],
        }

    return {
        "total_score": round(total_score, 2),
        "total_max": round(total_max, 2),
        "percentage": round(100.0 * total_score / max(1, total_max), 1),
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "category_breakdown": cats,
        "node_count": len(results),
        "executed": sum(1 for r in results if r.status == "EXECUTED"),
        "skipped": sum(1 for r in results if r.status == "SKIPPED_DEPENDENCY"),
        "skipped_llm": sum(1 for r in results if r.status == "SKIPPED_LLM"),
    }
