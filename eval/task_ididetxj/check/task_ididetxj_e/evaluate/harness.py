from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import config
from primitives import run_primitive
from utils import NodeResult, log


def _inject_test_user_placeholders(ctx: dict) -> None:
    test_users = getattr(config, "TEST_USERS", None) or {}
    for role, info in test_users.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx.setdefault(f"{role}_{field}", value)
                ctx.setdefault(f"eval_{role}_{field}", value)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

def load_dag(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def load_scoring_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def topological_sort(nodes: list[dict]) -> list[str]:
    by_id = {n["id"]: n for n in nodes}
    indeg = {nid: 0 for nid in by_id}
    children = defaultdict(list)
    for n in nodes:
        for p in n["prereqs"]:
            if p in by_id:
                indeg[n["id"]] += 1
                children[p].append(n["id"])
    queue = deque([nid for nid, d in indeg.items() if d == 0])
    order: list[str] = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for c in children[nid]:
            indeg[c] -= 1
            if indeg[c] == 0:
                queue.append(c)
    if len(order) != len(by_id):
        raise ValueError(f"DAG has a cycle (visited {len(order)}/{len(by_id)})")
    return order


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
ENTITY_KEYWORDS = {
    "DOCUMENT": ["documentId", "docId"],
    "COLLECTION": ["collectionId"],
    "USER": ["userId", "otherUserId"],
    "TEAM": ["teamId"],
    "COMMENT": ["commentId"],
    "SHARE": ["shareId"],
    "GROUP": ["groupId"],
    "TOKEN": ["tokenId"],
    "WEBHOOK": ["wh_id"],
    "OAUTH_CLIENT": ["oauthClientId"],
    "INTEGRATION": ["integrationId"],
}


#
#
_ENVELOPE_ID_PATHS = (
    ("data", "id"),
    ("id",),
    ("payload", "id"),
    ("result", "id"),
    ("entity", "id"),
    ("data", "attributes", "id"),
)


def _looks_like_entity_id(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    return 8 <= len(v) <= 64


def _extract_id_from_envelope(body: Any, node_id_upper: str) -> str | None:
    if not isinstance(body, dict):
        return None

    for path in _ENVELOPE_ID_PATHS:
        cur: Any = body
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and _looks_like_entity_id(cur):
            return cur

    data = body.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        cand = data[0].get("id") or (
            data[0].get("attributes", {}).get("id")
            if isinstance(data[0].get("attributes"), dict)
            else None
        )
        if _looks_like_entity_id(cand):
            return cand

    for kw in ENTITY_KEYWORDS:
        resource_key = kw.lower()
        if resource_key in node_id_upper.lower() and isinstance(body.get(resource_key), dict):
            cand = body[resource_key].get("id")
            if _looks_like_entity_id(cand):
                return cand

    return None


def _extract_entity_ids(node_id: str, body: Any, ctx: dict) -> None:
    if not isinstance(body, dict):
        return
    upper = node_id.upper()

    if not (upper.startswith("API_") and (upper.endswith("_CREATE") or upper.endswith("_CREATE_DRAFT"))):
        return

    new_id = _extract_id_from_envelope(body, upper)
    if not new_id:
        return

    for kw, vars_ in ENTITY_KEYWORDS.items():
        for v in vars_:
            if kw in upper:
                ctx.setdefault(v, new_id)
        if kw in upper:
            ctx.setdefault(kw.lower() + "Id", new_id)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
class ArtifactStore:
    def __init__(self):
        self._by_node: dict[str, list[dict]] = defaultdict(list)
        self._cur: str | None = None

    def push_context(self, node_id: str):
        self._cur = node_id

    def pop_context(self):
        self._cur = None

    def add(self, prim_result_dict: dict):
        if self._cur is None:
            return
        self._by_node[self._cur].append(prim_result_dict)

    def get(self, node_id: str) -> list[dict]:
        return self._by_node.get(node_id, [])


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def execute_node(node: dict, ctx: dict, store: ArtifactStore) -> NodeResult:
    node_id = node["id"]
    chain = node.get("primitive_chain", [])
    method = node["scoring"].get("method", "binary")
    maxScore = node["scoring"]["maxScore"]
    cat = node["scoring"]["category"]
    sub = node["scoring"].get("subcategory", "")

    ctx["_node_id"] = node_id

    store.push_context(node_id)

    prim_results = []
    n_pass = 0
    n_total = 0
    last_response_body = None
    for prim in chain:
        t = prim["type"]
        inputs = prim.get("inputs", {})
        try:
            res = run_primitive(t, inputs, ctx)
        except Exception as e:
            log.exception("primitive %s in node %s threw", t, node_id)
            from utils import PrimitiveResult
            res = PrimitiveResult(t, False, message=f"unhandled exception: {e}", data={})
        prim_results.append(res.to_dict())
        store.add(res.to_dict())
        n_total += 1
        if res.passed:
            n_pass += 1

    last_response_body = ctx.get("last_response_body")
    _extract_entity_ids(node_id, last_response_body, ctx)

    judge_skipped = False
    if method == "llm-judge":
        score = 0
        for r in prim_results:
            if r["type"] == "P17":
                p17_data = r.get("data") or {}
                if p17_data.get("skipped"):
                    judge_skipped = True
                    break
                judged = p17_data.get("score", 0)
                score_max = p17_data.get("max", 5)
                score = (judged / score_max) * maxScore if score_max else 0
                break
        all_passed = score > 0
        msg = "llm-judge"
    elif method == "weighted":
        score = (n_pass / max(n_total, 1)) * maxScore
        all_passed = n_pass == n_total
        msg = f"{n_pass}/{n_total} primitives passed"
    else:
        all_passed = n_pass == n_total
        score = maxScore if all_passed else 0
        msg = f"{n_pass}/{n_total} primitives passed"

    if all_passed:
        status = "PASSED"
    elif score > 0:
        status = "PARTIAL"
    else:
        status = "FAILED"

    if judge_skipped:
        status = "SKIPPED_LLM"
        score = 0
        msg = "llm-judge SKIPPED (judge unavailable)"

    store.pop_context()

    return NodeResult(
        node_id=node_id, status=status, score=round(score, 2), maxScore=maxScore,
        category=cat, subcategory=sub, method=method,
        message=msg,
        evidence={"primitive_results": prim_results, "last_status": ctx.get("last_response_status")},
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def execute_dag(dag: dict, *, only_category: str | None = None,
                stop_on_first_root_failure: bool = False,
                dry_run: bool = False) -> tuple[list[NodeResult], dict]:
    nodes = dag["nodes"]
    by_id = {n["id"]: n for n in nodes}
    order = topological_sort(nodes)
    log.info("DAG topological order: %d nodes", len(order))

    ctx: dict = {}
    _inject_test_user_placeholders(ctx)
    store = ArtifactStore()
    results: list[NodeResult] = []
    by_id_result: dict[str, NodeResult] = {}

    for nid in order:
        node = by_id[nid]
        if only_category and node["scoring"]["category"] != only_category:
            continue

        if dry_run:
            r = NodeResult(node_id=nid, status="PASSED", score=node["scoring"]["maxScore"],
                           maxScore=node["scoring"]["maxScore"],
                           category=node["scoring"]["category"],
                           subcategory=node["scoring"].get("subcategory", ""),
                           method=node["scoring"].get("method", "binary"),
                           message="DRY-RUN (not executed)")
            results.append(r)
            by_id_result[nid] = r
            continue

        r = execute_node(node, ctx, store)
        results.append(r)
        by_id_result[nid] = r

        log.info("  %-35s %s  %.1f/%.1f  %s",
                 nid, r.status, r.score, r.maxScore, r.message[:60])

    aggregate = aggregate_results(results)
    return results, aggregate


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate_results(results: list[NodeResult]) -> dict:
    by_cat = defaultdict(lambda: {"score": 0.0, "maxScore": 0.0, "n_passed": 0, "n_failed": 0,
                                    "n_partial": 0, "n_skipped": 0, "n_skipped_llm": 0,
                                    "n_total": 0})
    by_status = defaultdict(int)
    total_score = 0.0
    total_max = 0.0
    skipped_llm_max = 0.0
    for r in results:
        c = by_cat[r.category]
        c["n_total"] += 1
        if r.status == "PASSED":
            c["n_passed"] += 1
        elif r.status == "PARTIAL":
            c["n_partial"] += 1
        elif r.status == "FAILED":
            c["n_failed"] += 1
        elif r.status == "SKIPPED_DEPENDENCY":
            c["n_skipped"] += 1
        elif r.status == "SKIPPED_LLM":
            c["n_skipped_llm"] += 1
        by_status[r.status] += 1

        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.maxScore
            continue
        c["score"] += r.score
        c["maxScore"] += r.maxScore
        total_score += r.score
        total_max += r.maxScore

    return {
        "total_score": round(total_score, 2),
        "total_maxScore": round(total_max, 2),
        "percentage": round(total_score / total_max * 100, 2) if total_max else 0,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "by_status": dict(by_status),
        "by_category": {c: dict(v) for c, v in by_cat.items()},
    }
