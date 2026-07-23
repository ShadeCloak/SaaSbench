import importlib.util
import json
import os
import re
import sys
import traceback
from collections import defaultdict, deque

from utils import NodeResult, ArtifactStore, context
from config import DAG_PATH, TEST_USERS


def _inject_test_user_placeholders(ctx: dict) -> None:
    for role, info in TEST_USERS.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx.setdefault(f"{role}_{field}", value)
                ctx.setdefault(f"eval_{role}_{field}", value)



try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

artifact_store = ArtifactStore()


def load_dag(path=None) -> dict:
    with open(path or DAG_PATH, encoding="utf-8") as f:
        return json.load(f)


def category_to_module_name(category: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", category)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


def topological_sort(nodes: list[dict]) -> list[dict]:
    node_map = {n["id"]: n for n in nodes}
    in_degree = {n["id"]: 0 for n in nodes}
    for n in nodes:
        for p in n.get("prereqs", []):
            if p in in_degree:
                in_degree[n["id"]] += 1

    queue = deque(nid for nid, d in in_degree.items() if d == 0)
    order = []
    while queue:
        nid = queue.popleft()
        order.append(node_map[nid])
        for n in nodes:
            if nid in n.get("prereqs", []):
                in_degree[n["id"]] -= 1
                if in_degree[n["id"]] == 0:
                    queue.append(n["id"])
    return order


_SKIPPED_AS_PASSTHROUGH = {
    "SKIPPED_LLM",
    "SKIPPED_LLM_DISABLED",
    "SKIPPED_DEPENDENCY",
}


def all_prereqs_passed(prereqs: list[str], results: dict[str, NodeResult]) -> bool:
    for p in prereqs:
        r = results.get(p)
        if r is None:
            return False
        if r.status in _SKIPPED_AS_PASSTHROUGH:
            continue
        if r.score <= 0:
            return False
    return True


def _store_node_outputs(node_id: str, result: NodeResult, ctx: dict) -> None:
    node_data = {}

    if result.score > 0:
        node_data["passed"] = True

    if ctx.get("_last_created_id") is not None:
        node_data["created_id"] = ctx["_last_created_id"]

    if ctx.get("_last_response_body") is not None:
        body = ctx["_last_response_body"]
        node_data["response_body"] = body
        if isinstance(body, dict):
            if "result" in body and isinstance(body["result"], dict):
                for k, v in body["result"].items():
                    node_data[k] = v
            if "id" in body:
                node_data["id"] = body["id"]

    if ctx.get("_last_status_code"):
        node_data["status_code"] = ctx["_last_status_code"]

    if isinstance(result.evidence, dict):
        node_data.update(result.evidence)

    ctx[node_id] = node_data


def execute_node(node: dict, results: dict[str, NodeResult]) -> NodeResult:
    scoring = node.get("scoring", {})
    category = scoring.get("category", "Unknown")
    subcategory = scoring.get("subcategory", "")
    max_score = node.get("max_score", scoring.get("maxScore", 0))
    node_id = node["id"]

    return _execute_from_dag(node, context, category, subcategory, float(max_score))


def _execute_from_dag(node: dict, ctx: dict, category: str, subcategory: str, max_score: float) -> NodeResult:
    from primitives import PRIMITIVES
    node_id = node["id"]
    chain = node.get("primitive_chain", [])
    if not chain:
        return NodeResult(node_id, "ERROR", 0.0, max_score, category, subcategory, "No primitive_chain")

    try:
        chain_results = []
        llm_skipped = False
        llm_skipped_info: dict | None = None
        ctx["_node_resp_start"] = len(ctx.get("_response_log", []) or [])
        for step in chain:
            prim_name = step.get("primitive", "")
            inputs = dict(step.get("inputs", {}))
            fn = PRIMITIVES.get(prim_name)
            if fn is None:
                chain_results.append({"passed": False, "error": f"Unknown primitive {prim_name}"})
                continue
            r = fn(inputs, ctx)
            chain_results.append(r)
            if prim_name == "P05" and r.get("entity_id") is not None:
                ctx["_last_created_id"] = r["entity_id"]
            if prim_name == "P17" and isinstance(r, dict) and r.get("skipped"):
                llm_skipped = True
                llm_skipped_info = {
                    "llm_api_failure": r.get("llm_api_failure", False),
                    "exception_class": r.get("exception_class", ""),
                    "reason": r.get("reason", ""),
                }

        if llm_skipped:
            ev = {"chain_results": chain_results}
            if llm_skipped_info:
                ev["llm_judge_skipped"] = True
                ev.update(llm_skipped_info)
            return NodeResult(node_id, "SKIPPED_LLM", 0.0, max_score, category, subcategory,
                              f"{node_id}: LLM judge skipped ({llm_skipped_info.get('reason', 'unknown') if llm_skipped_info else 'unknown'})",
                              evidence=ev)

        passed = sum(1 for r in chain_results if r.get("passed", False))
        total = len(chain_results)
        ratio = passed / total if total else 0
        score = round(ratio * max_score, 1)
        node_threshold = node.get("inputs", {}).get("pass_threshold")
        if node_threshold is None:
            node_threshold = float(os.environ.get("EVAL_PASS_THRESHOLD", "0.5"))
        status = "PASS" if ratio >= float(node_threshold) else "FAIL"
        msg = f"{node_id}: {passed}/{total} steps passed"
        return NodeResult(node_id, status, score, max_score, category, subcategory, msg,
                          evidence={"chain_results": chain_results})
    except Exception as e:
        return NodeResult(node_id, "ERROR", 0.0, max_score, category, subcategory,
                          traceback.format_exc()[:500])


def execute_dag(
    dag: dict,
    only_category: str | None = None,
    dry_run: bool = False,
    with_llm: bool = False,
) -> list[NodeResult]:
    nodes = dag.get("nodes", [])
    sorted_nodes = topological_sort(nodes)
    _inject_test_user_placeholders(context)
    results: dict[str, NodeResult] = {}
    all_results: list[NodeResult] = []

    for node in sorted_nodes:
        scoring = node.get("scoring", {})
        category = scoring.get("category", "Unknown")
        subcategory = scoring.get("subcategory", "")
        max_score = scoring.get("maxScore", 0)
        node_id = node["id"]

        if only_category and category != only_category:
            continue

        if not with_llm and scoring.get("method") == "llm-judge":
            r = NodeResult(node_id=node_id, status="SKIPPED_LLM_DISABLED",
                           score=0.0, max_score=float(max_score),
                           category=category, subcategory=subcategory,
                           message="LLM judge disabled")
            results[node_id] = r
            all_results.append(r)
            continue

        if not all_prereqs_passed(node.get("prereqs", []), results):
            r = NodeResult(node_id=node_id, status="SKIPPED_DEPENDENCY",
                           score=0.0, max_score=float(max_score),
                           category=category, subcategory=subcategory,
                           message="Prerequisites not met")
            results[node_id] = r
            all_results.append(r)
            continue

        if dry_run:
            r = NodeResult(node_id=node_id, status="DRY_RUN",
                           score=0.0, max_score=float(max_score),
                           category=category, subcategory=subcategory,
                           message="Would execute")
        else:
            artifact_store.push_context(node_id)
            r = execute_node(node, results)
            _store_node_outputs(node_id, r, context)
            artifact_store.pop_context()

        results[node_id] = r
        all_results.append(r)

    return all_results


def aggregate_results(results: list[NodeResult], dag: dict) -> dict:
    scoring_config = dag.get("scoring_config", {})
    SKIP_FROM_TOTAL = {
        "SKIPPED_LLM",
        "SKIPPED_LLM_DISABLED",
    }
    total_score = sum(r.score for r in results if r.status not in SKIP_FROM_TOTAL)
    total_max = sum(r.max_score for r in results if r.status not in SKIP_FROM_TOTAL)
    skipped_llm_max = sum(r.max_score for r in results if r.status in SKIP_FROM_TOTAL)
    pct = (total_score / total_max * 100) if total_max > 0 else 0.0

    by_cat: dict[str, list[NodeResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)

    categories = []
    for cat, nodes in sorted(by_cat.items()):
        cs = sum(r.score for r in nodes if r.status not in SKIP_FROM_TOTAL)
        cm = sum(r.max_score for r in nodes if r.status not in SKIP_FROM_TOTAL)
        categories.append({
            "category": cat,
            "total_score": cs, "max_score": cm,
            "percentage": round((cs / cm * 100) if cm > 0 else 0, 2),
            "nodes": [{"node_id": r.node_id, "status": r.status,
                       "score": r.score, "max_score": r.max_score,
                       "message": r.message} for r in nodes],
        })

    node_by_id = {n["id"]: n for n in dag.get("nodes", [])}
    complexity: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "max_score": 0.0})
    for r in results:
        if r.status in SKIP_FROM_TOTAL:
            continue
        tier = node_by_id.get(r.node_id, {}).get("complexity_tier", "unknown")
        complexity[tier]["score"] += r.score
        complexity[tier]["max_score"] += r.max_score

    result_by_id = {r.node_id: r for r in results}
    trajectories = {}
    for tname, tcfg in scoring_config.get("trajectories", {}).items():
        if isinstance(tcfg, dict) and "node_ids" in tcfg:
            ts = sum(result_by_id[nid].score for nid in tcfg["node_ids"]
                     if nid in result_by_id and result_by_id[nid].status not in SKIP_FROM_TOTAL)
            tm = sum(result_by_id[nid].max_score for nid in tcfg["node_ids"]
                     if nid in result_by_id and result_by_id[nid].status not in SKIP_FROM_TOTAL)
            trajectories[tname] = {"score": ts, "max_score": tm}

    return {
        "total_score": total_score, "total_max_score": total_max,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "percentage": round(pct, 2),
        "categories": categories,
        "complexity_distribution": dict(complexity),
        "trajectories": trajectories,
        "artifact_store": artifact_store.get_all(),
        "node_results": [{"node_id": r.node_id, "status": r.status,
                          "score": r.score, "max_score": r.max_score,
                          "message": r.message,
                          "evidence": getattr(r, "evidence", None)} for r in results],
    }
