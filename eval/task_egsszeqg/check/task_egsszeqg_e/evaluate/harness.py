from __future__ import annotations
import json, time, traceback
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from utils import NodeResult
from primitives import execute_primitive, context as global_context
from config import TEST_USERS


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

def load_dag(path: str | Path) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def topological_sort(nodes: list[dict]) -> list[dict]:
    by_id = {n["id"]: n for n in nodes}
    indeg = {n["id"]: len(n.get("prereqs", [])) for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for p in n.get("prereqs", []):
            if p in by_id:
                adj[p].append(n["id"])
    q = deque(nid for nid, d in indeg.items() if d == 0)
    order: list[str] = []
    while q:
        cur = q.popleft()
        order.append(cur)
        for dep in adj[cur]:
            indeg[dep] -= 1
            if indeg[dep] == 0:
                q.append(dep)
    return [by_id[nid] for nid in order if nid in by_id]


def _all_prereqs_passed(prereqs: list[str], results: dict[str, NodeResult]) -> bool:
    for p in prereqs:
        r = results.get(p)
        if r is None or r.status in ("FAILED", "ERROR", "SKIPPED_DEPENDENCY"):
            return False
    return True


def execute_chain(chain: list[dict]) -> tuple[bool, float, list[dict]]:
    step_results: list[dict] = []
    passed_count = 0
    for step in chain:
        ptype = step.get("type", "")
        inputs = step.get("inputs", {})
        try:
            result = execute_primitive(ptype, inputs)
        except Exception as e:
            result = {"passed": False, "error": str(e)}
        step_results.append({"type": ptype, **result})
        if result.get("passed", False):
            passed_count += 1

    total = len(chain) if chain else 1
    ratio = (passed_count / total) if total else 0
    all_passed = passed_count == len(chain) and len(chain) > 0
    return all_passed, ratio, step_results


def score_node(node: dict, all_passed: bool, pass_ratio: float,
               step_results: list[dict]) -> float:
    scoring = node.get("scoring", {})
    method = scoring.get("method", "weighted")
    max_score = float(scoring.get("maxScore", 0))

    if method == "binary":
        return max_score if all_passed else 0.0
    elif method == "weighted":
        return round(pass_ratio * max_score, 4)
    elif method == "llm-judge":
        llm_steps = [s for s in step_results if s.get("type") == "P17"]
        if llm_steps:
            llm_score = llm_steps[-1].get("score", 0)
            llm_max = llm_steps[-1].get("max", max_score)
            return round((llm_score / llm_max) * max_score, 4) if llm_max else 0.0
        return 0.0
    return 0.0


def execute_dag(dag: dict, *, with_llm: bool = False,
                only_category: str | None = None) -> dict[str, NodeResult]:
    all_nodes = dag.get("nodes", [])

    if only_category:
        target_ids = {n["id"] for n in all_nodes
                      if n.get("scoring", {}).get("category") == only_category}
        prereq_ids: set[str] = set()
        by_id_map = {n["id"]: n for n in all_nodes}
        queue = list(target_ids)
        while queue:
            nid = queue.pop()
            for p in by_id_map.get(nid, {}).get("prereqs", []):
                if p not in target_ids and p not in prereq_ids and p in by_id_map:
                    prereq_ids.add(p)
                    queue.append(p)
        needed_ids = target_ids | prereq_ids
        nodes = [n for n in all_nodes if n["id"] in needed_ids]
    else:
        nodes = all_nodes

    ordered = topological_sort(nodes)
    _inject_test_user_placeholders(global_context)
    results: dict[str, NodeResult] = {}

    for node in ordered:
        nid = node["id"]
        scoring = node.get("scoring", {})
        category = scoring.get("category", "")
        subcategory = scoring.get("subcategory", "")
        max_score = float(scoring.get("maxScore", 0))
        prereqs = node.get("prereqs", [])

        if not _all_prereqs_passed(prereqs, results):
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0,
                maxScore=max_score, category=category, subcategory=subcategory,
                message=f"Prereqs not met: {prereqs}",
            )
            continue

        if scoring.get("method") == "llm-judge" and not with_llm:
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_LLM", score=0,
                maxScore=max_score, category=category, subcategory=subcategory,
                message="LLM judge skipped (--with-llm not set)",
            )
            continue

        try:
            all_passed, ratio, step_results = execute_chain(node.get("primitive_chain", []))
            llm_skipped_step = next(
                (s for s in step_results
                 if s.get("type") == "P17" and isinstance(s, dict) and s.get("skipped")
                 and s.get("llm_api_failure") is not None),
                None,
            )
            if scoring.get("method") == "llm-judge" and llm_skipped_step is not None:
                score = 0.0
                status = "SKIPPED_LLM"
                evidence = {"steps": step_results, "llm_judge_skipped": True,
                            "llm_api_failure": llm_skipped_step.get("llm_api_failure", False),
                            "exception_class": llm_skipped_step.get("exception_class", "")}
                msg = f"LLM judge skipped: {llm_skipped_step.get('reason', '')}"
            else:
                score = score_node(node, all_passed, ratio, step_results)
                status = "PASSED" if score > 0 else "FAILED"
                evidence = {"steps": step_results}
                msg = ""
            results[nid] = NodeResult(
                node_id=nid, status=status, score=score,
                maxScore=max_score, category=category, subcategory=subcategory,
                evidence=evidence, message=msg,
            )
        except Exception as e:
            results[nid] = NodeResult(
                node_id=nid, status="ERROR", score=0,
                maxScore=max_score, category=category, subcategory=subcategory,
                message=traceback.format_exc()[:500],
            )

    return results


def aggregate_results(results: dict[str, NodeResult],
                      scoring_config: dict) -> dict:
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}
    cat_scores: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "maxScore": 0.0, "nodes": 0,
                                                        "passed": 0, "failed": 0, "skipped": 0, "error": 0})
    for r in results.values():
        cat = r.category or "Unknown"
        cat_scores[cat]["nodes"] += 1
        if r.status == "PASSED":
            cat_scores[cat]["passed"] += 1
        elif r.status == "FAILED":
            cat_scores[cat]["failed"] += 1
        elif r.status.startswith("SKIPPED"):
            cat_scores[cat]["skipped"] += 1
        else:
            cat_scores[cat]["error"] += 1
        if r.status in SKIP_FROM_TOTAL:
            continue
        cat_scores[cat]["score"] += r.score
        cat_scores[cat]["maxScore"] += r.maxScore

    total_score = sum(r.score for r in results.values() if r.status not in SKIP_FROM_TOTAL)
    total_max = sum(r.maxScore for r in results.values() if r.status not in SKIP_FROM_TOTAL)
    skipped_llm_max = sum(r.maxScore for r in results.values() if r.status in SKIP_FROM_TOTAL)
    pct = (total_score / total_max * 100) if total_max else 0

    categories_list = []
    for cat, info in sorted(cat_scores.items()):
        categories_list.append({"category": cat, **info})

    trajectory_results = {}
    for tname, tdata in scoring_config.get("trajectories", {}).items():
        t_ids = tdata.get("node_ids", [])
        t_score = sum(results[nid].score for nid in t_ids
                      if nid in results and results[nid].status not in SKIP_FROM_TOTAL)
        t_max = sum(results[nid].maxScore for nid in t_ids
                    if nid in results and results[nid].status not in SKIP_FROM_TOTAL)
        trajectory_results[tname] = {
            "score": round(t_score, 2), "maxScore": round(t_max, 2),
            "percentage": round(t_score / t_max * 100, 1) if t_max else 0,
        }

    return {
        "total_score": round(total_score, 2),
        "total_maxScore": round(total_max, 2),
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "percentage": round(pct, 1),
        "categories": categories_list,
        "trajectories": trajectory_results,
        "node_count": len(results),
        "passed": sum(1 for r in results.values() if r.status == "PASSED"),
        "failed": sum(1 for r in results.values() if r.status == "FAILED"),
        "skipped": sum(1 for r in results.values() if r.status.startswith("SKIPPED")),
        "error": sum(1 for r in results.values() if r.status == "ERROR"),
    }
