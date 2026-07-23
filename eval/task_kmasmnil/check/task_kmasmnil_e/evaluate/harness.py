import json
import traceback
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

from primitives import PRIMITIVE_MAP
from utils import NodeResult, ArtifactStore, PrimitiveResult, context, resolve_placeholders
from config import (
    TEST_USERS,
    EVAL_READ_API_KEY,
    EVAL_WRITE_API_KEY,
    EVAL_WRONG_ENV_API_KEY,
)


def _inject_test_user_placeholders(ctx: dict) -> None:
    for role, info in TEST_USERS.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx.setdefault(f"{role}_{field}", value)
                ctx.setdefault(f"eval_{role}_{field}", value)

    ctx.setdefault("read_api_key", EVAL_READ_API_KEY)
    ctx.setdefault("write_api_key", EVAL_WRITE_API_KEY)
    ctx.setdefault("wrong_env_api_key", EVAL_WRONG_ENV_API_KEY)
    ctx.setdefault("long_password", "A1!" + ("a" * 9997))




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
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_scoring_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes: List[dict]) -> List[dict]:
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: Dict[str, int] = defaultdict(int)
    adj: Dict[str, List[str]] = defaultdict(list)

    for n in nodes:
        nid = n["id"]
        if nid not in in_degree:
            in_degree[nid] = 0
        for p in n.get("prereqs", []):
            adj[p].append(nid)
            in_degree[nid] += 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    ordered = []

    while queue:
        nid = queue.popleft()
        if nid in id_to_node:
            ordered.append(id_to_node[nid])
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) != len(nodes):
        missing = set(n["id"] for n in nodes) - set(n["id"] for n in ordered)
        raise ValueError(f"Cycle detected or missing nodes: {missing}")

    return ordered


def all_prereqs_passed(prereqs: List[str], results: Dict[str, NodeResult]) -> bool:
    for p in prereqs:
        r = results.get(p)
        if r is None or r.status not in ("PASSED",):
            return False
    return True


def execute_chain(chain: List[dict], artifact_store: ArtifactStore) -> PrimitiveResult:
    all_passed = True
    total_steps = len(chain)
    passed_steps = 0
    chain_evidence = []
    llm_score = None
    llm_skipped = False
    llm_skipped_info = None

    for step in chain:
        ptype = step["type"]
        inputs = resolve_placeholders(step.get("inputs", {}), context)

        primitive_fn = PRIMITIVE_MAP.get(ptype)
        if primitive_fn is None:
            chain_evidence.append({"type": ptype, "error": f"Unknown primitive: {ptype}"})
            all_passed = False
            continue

        try:
            result = primitive_fn(inputs)
        except Exception as e:
            result = PrimitiveResult(passed=False, message=f"Exception: {e}")
            traceback.print_exc()

        if result.passed:
            passed_steps += 1
        else:
            all_passed = False

        evidence_entry = {
            "type": ptype,
            "passed": result.passed,
            "message": result.message,
            "data": result.data,
        }
        chain_evidence.append(evidence_entry)
        artifact_store.add_evidence(evidence_entry)

        if ptype == "P17" and result.data:
            if result.data.get("skipped"):
                llm_skipped = True
                llm_skipped_info = {
                    "llm_api_failure": result.data.get("llm_api_failure", False),
                    "exception_class": result.data.get("exception_class", ""),
                    "reason": result.data.get("reason", ""),
                }
            elif "score" in result.data:
                llm_score = result.data["score"]

    combined = PrimitiveResult(
        passed=all_passed,
        data={
            "all_passed": all_passed,
            "pass_ratio": passed_steps / total_steps if total_steps > 0 else 0,
            "passed_steps": passed_steps,
            "total_steps": total_steps,
            "llm_score": llm_score,
            "llm_skipped": llm_skipped,
            "llm_skipped_info": llm_skipped_info,
        },
        evidence={"chain": chain_evidence},
    )
    return combined


def execute_dag(dag: dict, scoring_config: dict, with_llm: bool = False, only_category: str = None) -> Dict[str, NodeResult]:
    all_nodes = dag["nodes"]

    if only_category:
        filtered_ids = {n["id"] for n in all_nodes if n["scoring"]["category"] == only_category}
        ordered = topological_sort(all_nodes)
        nodes = ordered
    else:
        ordered = topological_sort(all_nodes)
        filtered_ids = None
        nodes = ordered

    _inject_test_user_placeholders(context)
    artifact_store = ArtifactStore()
    results: Dict[str, NodeResult] = {}

    for node in nodes:
        nid = node["id"]
        scoring = node["scoring"]

        if filtered_ids is not None and nid not in filtered_ids:
            results[nid] = NodeResult(
                node_id=nid, status="PASSED", score=0,
                maxScore=0, category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                method=scoring["method"],
                message="Auto-passed (outside target category filter)",
            )
            continue

        if scoring["method"] == "llm-judge" and not with_llm:
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_LLM", score=0,
                maxScore=scoring["maxScore"],
                category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                method=scoring["method"],
                message="LLM judge skipped (use --with-llm to enable)",
            )
            continue

        prereqs = node.get("prereqs", [])
        if not all_prereqs_passed(prereqs, results):
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0,
                maxScore=scoring["maxScore"],
                category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                method=scoring["method"],
                message=f"Dependency not met: {[p for p in prereqs if results.get(p, NodeResult('','FAILED',0,0)).status != 'PASSED']}",
            )
            continue

        artifact_store.push_context(nid)
        context.pop("_response_history", None)

        try:
            chain_result = execute_chain(node["primitive_chain"], artifact_store)

            status = None
            if scoring["method"] == "binary":
                score = scoring["maxScore"] if chain_result.data.get("all_passed") else 0
            elif scoring["method"] == "weighted":
                ratio = chain_result.data.get("pass_ratio", 0)
                score = round(ratio * scoring["maxScore"], 2)
            elif scoring["method"] == "llm-judge":
                if chain_result.data.get("llm_skipped"):
                    score = 0
                    status = "SKIPPED_LLM"
                else:
                    llm_score = chain_result.data.get("llm_score", 0)
                    if llm_score is not None:
                        score = min(llm_score, scoring["maxScore"])
                    else:
                        score = 0
            else:
                score = 0

            if status is None:
                status = "PASSED" if score > 0 else "FAILED"

            results[nid] = NodeResult(
                node_id=nid, status=status, score=score,
                maxScore=scoring["maxScore"],
                category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                method=scoring["method"],
                evidence=chain_result.evidence,
                message=chain_result.message,
            )

        except Exception as e:
            results[nid] = NodeResult(
                node_id=nid, status="ERROR", score=0,
                maxScore=scoring["maxScore"],
                category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                method=scoring["method"],
                message=f"Execution error: {e}",
            )
            traceback.print_exc()

        artifact_store.pop_context()

    return results


def aggregate_results(results: Dict[str, NodeResult], scoring_config: dict) -> dict:
    category_scores = defaultdict(lambda: {"total_score": 0, "max_score": 0, "nodes": 0, "passed": 0, "failed": 0, "skipped": 0})
    tier_scores = defaultdict(lambda: {"total_score": 0, "max_score": 0, "nodes": 0})

    total_score = 0
    total_max = 0
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    skipped_llm_max = 0.0
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}

    for nid, r in results.items():
        if r.maxScore == 0 and r.message and "outside target category" in r.message:
            continue
        cat = r.category
        category_scores[cat]["nodes"] += 1
        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.maxScore
            category_scores[cat]["skipped"] += 1
            total_skipped += 1
            continue
        category_scores[cat]["total_score"] += r.score
        category_scores[cat]["max_score"] += r.maxScore
        if r.status == "PASSED":
            category_scores[cat]["passed"] += 1
            total_passed += 1
        elif r.status in ("FAILED", "ERROR"):
            category_scores[cat]["failed"] += 1
            total_failed += 1
        else:
            category_scores[cat]["skipped"] += 1
            total_skipped += 1

        total_score += r.score
        total_max += r.maxScore

    percentage = (total_score / total_max * 100) if total_max > 0 else 0

    return {
        "total_score": total_score,
        "total_max": total_max,
        "percentage": round(percentage, 2),
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "total_nodes": len(results),
        "passed": total_passed,
        "failed": total_failed,
        "skipped": total_skipped,
        "categories": [
            {
                "category": cat,
                "total_score": info["total_score"],
                "max_score": info["max_score"],
                "percentage": round(info["total_score"] / info["max_score"] * 100, 2) if info["max_score"] > 0 else 0,
                "nodes": info["nodes"],
                "passed": info["passed"],
                "failed": info["failed"],
                "skipped": info["skipped"],
            }
            for cat, info in sorted(category_scores.items())
        ],
        "node_results": [r.to_dict() for r in results.values()],
    }
