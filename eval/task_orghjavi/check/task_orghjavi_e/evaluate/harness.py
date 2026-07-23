from __future__ import annotations

import copy
import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
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
    return json.loads(Path(path).read_text())


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
# ---------------------------------------------------------------------------
ENTITY_KEYWORDS: List[Tuple[re.Pattern, List[str]]] = [
    (re.compile(r"site", re.I), ["site_id", "site_pk"]),
    (re.compile(r"team", re.I), ["team_id"]),
    (re.compile(r"user", re.I), ["user_id"]),
    (re.compile(r"goal", re.I), ["goal_id"]),
    (re.compile(r"segment", re.I), ["segment_id"]),
    (re.compile(r"funnel", re.I), ["funnel_id"]),
    (re.compile(r"shared[_-]?link", re.I), ["shared_link_id"]),
    (re.compile(r"plugin[_-]?token", re.I), ["plugin_token_id"]),
    (re.compile(r"api[_-]?key", re.I), ["api_key_id"]),
    (re.compile(r"subscription", re.I), ["subscription_id"]),
    (re.compile(r"shield", re.I), ["shield_rule_id"]),
]


def extract_entity_ids(node_id: str,
                          response_body: Any,
                          node: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(response_body, (dict, list)):
        return {}

    def _extract_pk(body: Any) -> Any:
        if isinstance(body, dict):
            for k in ("id", "pk", "uuid", "ID", "Id"):
                if k in body:
                    return body[k]
            for k in body:
                if isinstance(k, str) and (
                    k.endswith("_id") or k.endswith("Id") or k.endswith("-id")
                ):
                    return body[k]
            for envelope in ("data", "result", "payload"):
                inner = body.get(envelope)
                if isinstance(inner, dict):
                    inner_pk = _extract_pk(inner)
                    if inner_pk is not None:
                        return inner_pk
                elif isinstance(inner, list) and inner:
                    return _extract_pk(inner[0])
            return None
        if isinstance(body, list) and body:
            return _extract_pk(body[0])
        return None

    pk = _extract_pk(response_body)
    if pk is None:
        return {}

    extracted: Dict[str, Any] = {}

    explicit_keys: List[str] = []
    if node:
        prod = node.get("inputs", {}).get("produces_entity")
        if isinstance(prod, str):
            explicit_keys = [prod]
        elif isinstance(prod, list):
            explicit_keys = [str(x) for x in prod]

    if explicit_keys:
        for k in explicit_keys:
            ctx[k] = pk
            extracted[k] = pk
    else:
        for pat, keys in reversed(ENTITY_KEYWORDS):
            if pat.search(node_id):
                for k in keys:
                    ctx[k] = pk
                    extracted[k] = pk
                break

    ctx["_last_pk"] = pk
    extracted["_last_pk"] = pk
    return extracted


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def execute_node(node: Dict[str, Any], store: ArtifactStore) -> NodeResult:
    nid = node["id"]
    method = node["scoring"]["method"]
    max_score = float(node["scoring"]["maxScore"])
    cat = node["scoring"]["category"]
    sub = node["scoring"].get("subcategory", "")
    tier = node.get("complexity_tier", "linear_crud")

    store.push(nid)
    chain = node.get("primitive_chain", []) or []
    chain_dicts: List[Dict[str, Any]] = []
    primitive_results: List[PrimitiveResult] = []
    t0 = time.perf_counter()

    short_circuit_after = None
    for step in chain:
        if short_circuit_after is not None and step.get("type") in ("P08", "P10", "P11"):
            skip_msg = f"skipped (short-circuit after {short_circuit_after} failed)"
            r = PrimitiveResult(
                primitive=step.get("type", "?"),
                passed=False,
                score_hint=0.0,
                evidence={"skipped_due_to": short_circuit_after, "step": step},
                message=skip_msg,
            )
            primitive_results.append(r)
            chain_dicts.append(r.to_dict())
            store.emit(r.evidence)
            continue

        r = execute_primitive(step)
        primitive_results.append(r)
        chain_dicts.append(r.to_dict())
        store.emit(r.evidence)

        if step.get("type") == "P09" and not r.passed:
            short_circuit_after = "P09"

        if step.get("type") in ("P04", "P05"):
            body = None
            if isinstance(r.evidence.get("response"), dict):
                body = r.evidence["response"].get("body")
            if body is None and isinstance(r.evidence.get("create"), dict):
                body = r.evidence["create"].get("body")
            if body is not None:
                extract_entity_ids(nid, body, step)

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
        ratio = (sum(pr.score_hint for pr in primitive_results) / len(primitive_results)) if primitive_results else 0.0
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
def all_prereqs_passed(prereqs: List[str],
                          results: Dict[str, NodeResult],
                          node_strict: bool = False) -> bool:
    strict = node_strict or cfg.STRICT_PREREQ_PASSED_ONLY
    accepted = ({"PASSED", "SKIPPED_LLM"} if strict
                  else {"PASSED", "PARTIAL", "SKIPPED_LLM"})
    for p in prereqs:
        r = results.get(p)
        if r is None or r.status not in accepted:
            return False
    return True


_RBAC_PREFIXES = ("RBAC_",)


#
_DEFAULT_ANON_PREFIXES = (
    "/api/event", "/api/error", "/api/system/health/", "/api/health",
    "/api/system/", "/js/",
    "/login", "/logout", "/register", "/password/",
    "/non-existent", "/",
)
ANON_PREFIXES = _DEFAULT_ANON_PREFIXES


def load_anonymous_endpoints_from_meta(dag: Dict[str, Any]) -> Tuple[str, ...]:
    extras = dag.get("meta", {}).get("anonymous_endpoints") or []
    if not isinstance(extras, (list, tuple)):
        return _DEFAULT_ANON_PREFIXES
    extras_clean = tuple(str(p) for p in extras if isinstance(p, str) and p)
    seen = set(_DEFAULT_ANON_PREFIXES)
    deduped = list(_DEFAULT_ANON_PREFIXES)
    for p in extras_clean:
        if p not in seen:
            deduped.append(p)
            seen.add(p)
    return tuple(deduped)


def ensure_admin_context_first_step(node: Dict[str, Any]) -> Dict[str, Any]:
    nid = node["id"]
    if nid.startswith(_RBAC_PREFIXES):
        return node

    explicit = node.get("requires_admin")
    if explicit is False:
        return node

    chain = node.get("primitive_chain", [])
    if chain and chain[0].get("type") == "P13":
        return node

    if explicit is True:
        new_node = copy.deepcopy(node)
        new_node["primitive_chain"] = (
            [{"type": "P13", "inputs": {"method": "session", "role": "admin"}}]
            + new_node["primitive_chain"]
        )
        return new_node

    needs_admin = False
    for step in chain:
        if step.get("type") not in ("P04", "P05", "P14", "P22"):
            continue
        ins = step.get("inputs", {})
        auth_mode = ins.get("auth_mode") or ""
        if auth_mode and not auth_mode.startswith("session_"):
            continue
        path = ins.get("path") or ""
        if any(path.startswith(p) or path == p for p in ANON_PREFIXES) and not auth_mode.startswith("session_"):
            continue
        needs_admin = True
        break

    if not needs_admin:
        return node

    new_node = copy.deepcopy(node)
    new_node["primitive_chain"] = (
        [{"type": "P13", "inputs": {"method": "session", "role": "admin"}}]
        + new_node["primitive_chain"]
    )
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

    global ANON_PREFIXES
    ANON_PREFIXES = load_anonymous_endpoints_from_meta(dag)

    if only_node_ids:
        wanted = set(only_node_ids)
        order = [nid for nid in order if nid in wanted]
    if only_category:
        order = [nid for nid in order if by_id[nid]["scoring"]["category"] == only_category]

    store = ArtifactStore()
    results: Dict[str, NodeResult] = {}
    for nid in order:
        node = by_id[nid]
        node_strict = bool(node.get("prereq_strict", False))
        if not all_prereqs_passed(node.get("prereqs", []), results, node_strict=node_strict):
            r = NodeResult(
                node_id=nid,
                status="SKIPPED_DEPENDENCY",
                score=0.0,
                maxScore=float(node["scoring"]["maxScore"]),
                category=node["scoring"]["category"],
                subcategory=node["scoring"].get("subcategory", ""),
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
                subcategory=node["scoring"].get("subcategory", ""),
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
    skipped_dep_max = 0.0

    for r in results.values():
        by_status[r.status] += 1
        if r.status == "SKIPPED_LLM":
            skipped_llm_max += r.maxScore
            continue
        if r.status == "SKIPPED_DEPENDENCY":
            skipped_dep_max += r.maxScore
        by_cat[r.category]["score"] += r.score
        by_cat[r.category]["max"] += r.maxScore
        by_cat[r.category]["node_count"] += 1
        by_tier[r.complexity_tier]["score"] += r.score
        by_tier[r.complexity_tier]["max"] += r.maxScore
        by_tier[r.complexity_tier]["node_count"] += 1

    total_score = sum(c["score"] for c in by_cat.values())
    total_max = sum(c["max"] for c in by_cat.values())

    _SKIP_STATUSES = {"SKIPPED_LLM"}
    trajectory_block: Dict[str, Any] = {}
    for tname, tdef in scoring_config.get("trajectories", {}).items():
        ids = set(tdef.get("node_ids", []))
        score = sum(r.score for r in results.values()
                      if r.node_id in ids and r.status not in _SKIP_STATUSES)
        mx = sum(r.maxScore for r in results.values()
                   if r.node_id in ids and r.status not in _SKIP_STATUSES)
        trajectory_block[tname] = {
            "node_count": len(ids),
            "score": round(score, 3),
            "maxScore": mx,
            "pct": round(100 * score / mx, 2) if mx else 0.0,
        }

    return {
        "total_score": round(total_score, 3),
        "total_maxScore": total_max,
        "total_pct": round(100 * total_score / total_max, 2) if total_max else 0.0,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "skipped_dependency_maxScore": round(skipped_dep_max, 3),
        "node_status_counts": dict(by_status),
        "by_category": {
            k: {
                "score": round(v["score"], 3),
                "maxScore": round(v["max"], 3),
                "pct": round(100 * v["score"] / v["max"], 2) if v["max"] else 0.0,
                "node_count": int(v["node_count"]),
            } for k, v in sorted(by_cat.items())
        },
        "by_complexity_tier": {
            k: {
                "score": round(v["score"], 3),
                "maxScore": round(v["max"], 3),
                "pct": round(100 * v["score"] / v["max"], 2) if v["max"] else 0.0,
                "node_count": int(v["node_count"]),
            } for k, v in sorted(by_tier.items())
        },
        "trajectories": trajectory_block,
    }


def generate_report(results: Dict[str, NodeResult], scoring_config: Dict[str, Any]) -> Dict[str, Any]:
    summary = aggregate(results, scoring_config)
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        "nodes": [r.to_dict() for r in results.values()],
    }
