from __future__ import annotations

import copy
import json
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config as cfg
from .primitives import PRIMITIVES, execute_primitive
from .utils import (
    NodeResult,
    PrimitiveResult,
    ctx,
    json_get,
    logger,
    print_result,
)
from ._result_compat import _result_passed, _result_message, _result_data


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
class ArtifactStore:
    def __init__(self) -> None:
        self._stack: List[str] = []
        self._evidence: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def push(self, node_id: str) -> None:
        self._stack.append(node_id)

    def pop(self) -> None:
        if self._stack:
            self._stack.pop()

    def emit(self, payload: Dict[str, Any]) -> None:
        if self._stack:
            self._evidence[self._stack[-1]].append(payload)

    def for_node(self, node_id: str) -> List[Dict[str, Any]]:
        return list(self._evidence.get(node_id, []))


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def load_dag(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def topological_sort(nodes: List[Dict[str, Any]]) -> List[str]:
    by_id = {n["id"]: n for n in nodes}
    in_deg: Dict[str, int] = {nid: 0 for nid in by_id}
    children: Dict[str, List[str]] = defaultdict(list)
    for n in nodes:
        for p in n.get("prereqs", []):
            if p not in by_id:
                continue
            in_deg[n["id"]] += 1
            children[p].append(n["id"])
    ready = deque(sorted([nid for nid, d in in_deg.items() if d == 0]))
    out: List[str] = []
    while ready:
        nid = ready.popleft()
        out.append(nid)
        for c in sorted(children[nid]):
            in_deg[c] -= 1
            if in_deg[c] == 0:
                ready.append(c)
    if len(out) != len(by_id):
        cyc = sorted([nid for nid, d in in_deg.items() if d > 0])
        raise RuntimeError(f"DAG has cycle (remaining: {cyc[:10]})")
    return out


# ---------------------------------------------------------------------------
#
#
#
# ---------------------------------------------------------------------------
ENTITY_KEYWORDS: List[Tuple[re.Pattern, List[str]]] = [
    (re.compile(r"customer", re.I),                      ["customer_id"]),
    (re.compile(r"company", re.I),                       ["cid", "company_id"]),
    (re.compile(r"supplier(?!part)", re.I),              ["supplier_id"]),
    (re.compile(r"supplierpart", re.I),                  ["supplier_part_id"]),
    (re.compile(r"part(?!category|parameter|testtemplate|relation)", re.I),
                                                         ["pid", "part_id", "any_part_pk"]),
    (re.compile(r"bom", re.I),                           ["bom_id", "bom_item_id"]),
    (re.compile(r"stocklocation|^loc_|location(?!history)", re.I),
                                                         ["loc_pk", "location_id"]),
    (re.compile(r"stock(?!location)", re.I),             ["stock_item_pk", "stock_item_id"]),
    (re.compile(r"build", re.I),                         ["build_id"]),
    (re.compile(r"purchaseorder(?!line)|^po(?!line)", re.I),
                                                         ["po_pk", "purchaseorder_id"]),
    (re.compile(r"po[_-]?line|poline", re.I),            ["poline_pk"]),
    (re.compile(r"salesorder(?!line)|^so(?!line)", re.I),
                                                         ["so_pk", "salesorder_id"]),
    (re.compile(r"so[_-]?line|soline", re.I),            ["soline_pk"]),
    (re.compile(r"shipment", re.I),                      ["ship_pk", "shipment_id"]),
    (re.compile(r"returnorder", re.I),                   ["ro_pk", "returnorder_id"]),
    (re.compile(r"parameter(?!template)", re.I),         ["param_id"]),
    (re.compile(r"parametertemplate|tpl_", re.I),        ["tpl_id"]),
    (re.compile(r"partcategory|^cat_", re.I),            ["cat_id", "category_id"]),
    (re.compile(r"importsession", re.I),                 ["import_session_id"]),
    (re.compile(r"token", re.I),                         ["just_created_token"]),
]


def extract_entity_ids(node: Dict[str, Any], response_body: Any) -> Dict[str, Any]:
    nid = node["id"] if isinstance(node, dict) else str(node)
    if not isinstance(response_body, (dict, list)):
        return {}

    candidates: List[Any] = []
    if isinstance(response_body, dict):
        for k in ("pk", "id", "ID", "key"):
            if k in response_body:
                candidates.append(response_body[k])
    if isinstance(response_body, list) and response_body:
        first = response_body[0]
        if isinstance(first, dict):
            for k in ("pk", "id"):
                if k in first:
                    candidates.append(first[k])

    if not candidates:
        return {}

    pk = candidates[0]
    extracted: Dict[str, Any] = {}

    declared = node.get("extracts_to") if isinstance(node, dict) else None
    if isinstance(declared, list) and declared:
        for k in declared:
            ctx[k] = pk
            extracted[k] = pk
    else:
        for pat, keys in ENTITY_KEYWORDS:
            if pat.search(nid):
                for k in keys:
                    ctx[k] = pk
                    extracted[k] = pk

    ctx["_last_pk"] = pk
    ctx[f"_last_pk_{nid}"] = pk
    extracted["_last_pk"] = pk
    return extracted


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def execute_node(node: Dict[str, Any], store: ArtifactStore) -> NodeResult:
    nid = node["id"]
    method = node["scoring"]["method"]
    max_score = float(node["scoring"]["maxScore"])
    cat = node["scoring"]["category"]
    sub = node["scoring"]["subcategory"]
    tier = node.get("complexity_tier", "linear_crud")

    store.push(nid)
    os.environ["CURRENT_NODE_ID"] = nid
    chain = node.get("primitive_chain", []) or []
    chain_dicts: List[Dict[str, Any]] = []
    primitive_results: List[PrimitiveResult] = []
    t0 = time.perf_counter()

    for step in chain:
        r = execute_primitive(step)
        primitive_results.append(r)
        chain_dicts.append(r.to_dict())
        store.emit(r.evidence)

        if step.get("type") in ("P04", "P05", "P23"):
            body = r.evidence.get("response", {}).get("body") if isinstance(r.evidence.get("response"), dict) else None
            if body is None and "upload_response" in r.evidence:
                body = r.evidence["upload_response"].get("body")
            if body is None and "create" in r.evidence and isinstance(r.evidence["create"], dict):
                body = r.evidence["create"].get("body")
            if body is not None:
                extract_entity_ids(node, body)

    elapsed = int((time.perf_counter() - t0) * 1000)
    store.pop()

    llm_skipped = any(
        pr.primitive == "P17" and pr.evidence.get("llm_judge_skipped") is True
        for pr in primitive_results
    )

    if llm_skipped:
        score = 0.0
    elif method == "binary":
        all_passed = all(_result_passed(pr) for pr in primitive_results) if primitive_results else False
        score = max_score if all_passed else 0.0
    elif method == "weighted":
        _PLUMBING = {"P13", "P04", "P12"}
        verify = [pr for pr in primitive_results if pr.primitive not in _PLUMBING]
        pool = verify if verify else primitive_results
        ratio = (sum(pr.score_hint for pr in pool) / len(pool)) if pool else 0.0
        score = round(ratio * max_score, 3)
    elif method == "llm-judge":
        p17 = [pr for pr in primitive_results if pr.primitive == "P17"]
        if p17:
            score = round(p17[-1].score_hint * max_score, 3)
        else:
            all_passed = all(_result_passed(pr) for pr in primitive_results) if primitive_results else False
            score = max_score if all_passed else 0.0
    else:
        score = 0.0

    msg_parts = [_result_message(pr) for pr in primitive_results if _result_message(pr)]
    if llm_skipped:
        status = "SKIPPED_LLM"
    elif not primitive_results:
        status = "ERROR"
    elif score >= max_score - 1e-6:
        status = "PASSED"
    elif score == 0:
        status = "FAILED"
    else:
        status = "PARTIAL"

    return NodeResult(
        node_id=nid,
        status=status,
        score=score,
        maxScore=max_score,
        category=cat,
        subcategory=sub,
        method=method,
        complexity_tier=tier,
        chain_results=chain_dicts,
        evidence={"chain": chain_dicts},
        message=" | ".join(msg_parts)[:1200],
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def all_prereqs_passed(prereqs: List[str], results: Dict[str, NodeResult]) -> bool:
    accepted = {"PASSED"} if cfg.STRICT_PREREQ_PASSED_ONLY else {"PASSED", "PARTIAL"}
    for p in prereqs:
        r = results.get(p)
        if r is None or r.status not in accepted:
            return False
    return True


_RBAC_USER_PREFIXES = ("RBAC_USER_",)


_INJECTED_MARKER = "_admin_ctx_injected"


def ensure_admin_context_first_step(node: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(node, dict) and node.get(_INJECTED_MARKER):
        return node
    nid = node["id"]
    if nid.startswith(_RBAC_USER_PREFIXES):
        return node
    chain = node.get("primitive_chain", [])
    if chain and chain[0].get("type") == "P13" and chain[0].get("inputs", {}).get("role") == "admin":
        return node
    types_used = {p.get("type") for p in chain}
    if not (types_used & {"P04", "P05", "P14", "P23"}):
        return node
    new_node = copy.deepcopy(node)
    new_node["primitive_chain"] = [{"type": "P13", "inputs": {"role": "admin"}}] + new_node["primitive_chain"]
    new_node[_INJECTED_MARKER] = True
    return new_node


def execute_dag(
    dag: Dict[str, Any],
    only_category: Optional[str] = None,
    only_node_ids: Optional[List[str]] = None,
    dry_run: bool = False,
) -> Dict[str, NodeResult]:
    nodes = dag["nodes"]
    by_id = {n["id"]: n for n in nodes}
    order = topological_sort(nodes)
    if only_node_ids:
        wanted = set(only_node_ids)
        order = [nid for nid in order if nid in wanted]
    if only_category:
        order = [nid for nid in order if by_id[nid]["scoring"]["category"] == only_category]

    store = ArtifactStore()
    results: Dict[str, NodeResult] = {}
    for nid in order:
        node = by_id[nid]
        if not all_prereqs_passed(node.get("prereqs", []), results):
            r = NodeResult(
                node_id=nid,
                status="SKIPPED_DEPENDENCY",
                score=0.0,
                maxScore=float(node["scoring"]["maxScore"]),
                category=node["scoring"]["category"],
                subcategory=node["scoring"]["subcategory"],
                method=node["scoring"]["method"],
                complexity_tier=node.get("complexity_tier", "linear_crud"),
                message=f"prereqs not all passed: {node.get('prereqs', [])}",
            )
            results[nid] = r
            print_result(r)
            continue

        if dry_run:
            r = NodeResult(
                node_id=nid,
                status="PASSED",
                score=float(node["scoring"]["maxScore"]),
                maxScore=float(node["scoring"]["maxScore"]),
                category=node["scoring"]["category"],
                subcategory=node["scoring"]["subcategory"],
                method=node["scoring"]["method"],
                complexity_tier=node.get("complexity_tier", "linear_crud"),
                message="DRY-RUN (would have executed)",
            )
            results[nid] = r
            print_result(r)
            continue

        r = execute_node(ensure_admin_context_first_step(node), store)
        results[nid] = r
        print_result(r)

    return results


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def aggregate(results: Dict[str, NodeResult], scoring_config: Dict[str, Any]) -> Dict[str, Any]:
    by_cat: Dict[str, Dict[str, float]] = defaultdict(lambda: {"score": 0.0, "max": 0.0, "node_count": 0})
    by_tier: Dict[str, Dict[str, float]] = defaultdict(lambda: {"score": 0.0, "max": 0.0, "node_count": 0})
    by_status: Dict[str, int] = defaultdict(int)
    skipped_llm_max = 0.0

    for r in results.values():
        by_status[r.status] += 1
        if r.status == "SKIPPED_LLM":
            skipped_llm_max += r.maxScore
            continue
        by_cat[r.category]["score"] += r.score
        by_cat[r.category]["max"] += r.maxScore
        by_cat[r.category]["node_count"] += 1
        by_tier[r.complexity_tier]["score"] += r.score
        by_tier[r.complexity_tier]["max"] += r.maxScore
        by_tier[r.complexity_tier]["node_count"] += 1

    total_score = sum(c["score"] for c in by_cat.values())
    total_max = sum(c["max"] for c in by_cat.values())

    trajectory_block: Dict[str, Any] = {}
    trajs = scoring_config.get("trajectories", {})
    for tname, tdef in trajs.items():
        ids = set(tdef.get("node_ids", []))
        score = sum(r.score for r in results.values() if r.node_id in ids)
        mx = sum(r.maxScore for r in results.values() if r.node_id in ids)
        trajectory_block[tname] = {
            "node_count": len(ids),
            "score": round(score, 3),
            "maxScore": mx,
            "pct": round(100*score/mx, 2) if mx else 0.0,
        }

    sub_block: Dict[str, Any] = {}
    for sname, sdef in scoring_config.get("sub_trajectories", {}).items():
        ids = set(sdef.get("node_ids", []))
        score = sum(r.score for r in results.values() if r.node_id in ids)
        mx = sum(r.maxScore for r in results.values() if r.node_id in ids)
        sub_block[sname] = {
            "node_count": len(ids),
            "score": round(score, 3),
            "maxScore": mx,
            "pct": round(100*score/mx, 2) if mx else 0.0,
        }

    return {
        "total_score": round(total_score, 3),
        "total_maxScore": total_max,
        "total_pct": round(100*total_score/total_max, 2) if total_max else 0.0,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "node_status_counts": dict(by_status),
        "by_category": {
            k: {
                "score": round(v["score"], 3),
                "maxScore": round(v["max"], 3),
                "pct": round(100*v["score"]/v["max"], 2) if v["max"] else 0.0,
                "node_count": int(v["node_count"]),
            } for k, v in sorted(by_cat.items())
        },
        "by_complexity_tier": {
            k: {
                "score": round(v["score"], 3),
                "maxScore": round(v["max"], 3),
                "pct": round(100*v["score"]/v["max"], 2) if v["max"] else 0.0,
                "node_count": int(v["node_count"]),
            } for k, v in sorted(by_tier.items())
        },
        "trajectories": trajectory_block,
        "sub_trajectories": sub_block,
    }


def generate_report(results: Dict[str, NodeResult], scoring_config: Dict[str, Any]) -> Dict[str, Any]:
    summary = aggregate(results, scoring_config)
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        "nodes": [r.to_dict() for r in results.values()],
    }
    return payload
