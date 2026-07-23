import importlib.util
import json
import os
import re
import sys
import traceback
from collections import defaultdict, deque

from utils import NodeResult, context, resolve_placeholders
from config import DAG_PATH, SCORING_CONFIG_PATH, TEST_USERS


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

def load_dag(path=None) -> dict:
    p = path or DAG_PATH
    with open(p) as f:
        return json.load(f)


def load_scoring_config(path=None) -> dict:
    p = path or SCORING_CONFIG_PATH
    with open(p) as f:
        return json.load(f)


def category_to_module_name(category: str) -> str:
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", category).lower()
    return s


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
                tid = n["id"]
                in_degree[tid] -= 1
                if in_degree[tid] == 0:
                    queue.append(tid)

    return order


def all_prereqs_passed(prereqs: list[str], results: dict[str, NodeResult]) -> bool:
    for p in prereqs:
        r = results.get(p)
        if r is None or r.score <= 0:
            return False
    return True


def execute_node(node: dict, results: dict[str, NodeResult]) -> NodeResult:
    scoring = node.get("scoring", {})
    category = scoring.get("category", "Unknown")
    subcategory = scoring.get("subcategory", "")
    max_score = scoring.get("maxScore", 0)
    node_id = node["id"]

    eval_dir = os.path.dirname(os.path.abspath(__file__))
    if eval_dir not in sys.path:
        sys.path.insert(0, eval_dir)

    mod_name = f"tests.test_{category_to_module_name(category)}"
    func_name = f"test_{node_id}"

    try:
        spec = importlib.util.find_spec(mod_name)
        if spec is None:
            raise ModuleNotFoundError(f"No module named '{mod_name}'")

        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)

        func = getattr(module, func_name, None)
        if func is None:
            raise AttributeError(f"'{mod_name}' has no attribute '{func_name}'")

        return func(node, results, context)
    except Exception as e:
        return NodeResult(
            node_id=node_id,
            status="ERROR",
            score=0.0,
            max_score=float(max_score),
            category=category,
            subcategory=subcategory,
            message=traceback.format_exc(),
            evidence={},
        )


def execute_dag(
    dag: dict,
    scoring_config: dict,
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
            r = NodeResult(
                node_id=node_id,
                status="SKIPPED_LLM_DISABLED",
                score=0.0,
                max_score=float(max_score),
                category=category,
                subcategory=subcategory,
                message="LLM judge disabled",
                evidence={},
            )
            results[node_id] = r
            all_results.append(r)
            continue

        if not all_prereqs_passed(node.get("prereqs", []), results):
            r = NodeResult(
                node_id=node_id,
                status="SKIPPED_DEPENDENCY",
                score=0.0,
                max_score=float(max_score),
                category=category,
                subcategory=subcategory,
                message="Prerequisites not met",
                evidence={},
            )
            results[node_id] = r
            all_results.append(r)
            continue

        if dry_run:
            r = NodeResult(
                node_id=node_id,
                status="DRY_RUN",
                score=0.0,
                max_score=float(max_score),
                category=category,
                subcategory=subcategory,
                message="Would execute",
                evidence={},
            )
        else:
            r = execute_node(node, results)

        results[node_id] = r
        all_results.append(r)

    return all_results


def aggregate_results(results: list[NodeResult], scoring_config: dict, dag: dict | None = None) -> dict:
    SKIP_FROM_TOTAL = {"SKIPPED_LLM", "SKIPPED_LLM_DISABLED"}
    total_score = sum(r.score for r in results if r.status not in SKIP_FROM_TOTAL)
    total_max_score = sum(r.max_score for r in results if r.status not in SKIP_FROM_TOTAL)
    skipped_llm_max = sum(r.max_score for r in results if r.status in SKIP_FROM_TOTAL)
    percentage = (total_score / total_max_score * 100) if total_max_score > 0 else 0.0

    by_category: dict[str, list[NodeResult]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)

    categories = []
    for cat, nodes in sorted(by_category.items()):
        cat_score = sum(r.score for r in nodes if r.status not in SKIP_FROM_TOTAL)
        cat_max = sum(r.max_score for r in nodes if r.status not in SKIP_FROM_TOTAL)
        cat_pct = (cat_score / cat_max * 100) if cat_max > 0 else 0.0
        categories.append(
            {
                "category": cat,
                "total_score": cat_score,
                "max_score": cat_max,
                "percentage": round(cat_pct, 2),
                "nodes": [
                    {
                        "node_id": r.node_id,
                        "status": r.status,
                        "score": r.score,
                        "max_score": r.max_score,
                        "message": r.message,
                    }
                    for r in nodes
                ],
            }
        )

    node_by_id = {n["id"]: n for n in dag.get("nodes", [])} if dag else {}
    complexity_distribution: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "max_score": 0.0})
    for r in results:
        if r.status in SKIP_FROM_TOTAL:
            continue
        tier = node_by_id.get(r.node_id, {}).get("complexity_tier", "unknown")
        complexity_distribution[tier]["score"] += r.score
        complexity_distribution[tier]["max_score"] += r.max_score

    result_by_id = {r.node_id: r for r in results}
    trajectories_cfg = scoring_config.get("trajectories", {})
    trajectories = {}
    for traj_name, traj_cfg in trajectories_cfg.items():
        if isinstance(traj_cfg, dict) and "node_ids" in traj_cfg:
            traj_score = 0.0
            traj_max = 0.0
            for nid in traj_cfg["node_ids"]:
                if nid in result_by_id:
                    r = result_by_id[nid]
                    if r.status in SKIP_FROM_TOTAL:
                        continue
                    traj_score += r.score
                    traj_max += r.max_score
            trajectories[traj_name] = {"score": traj_score, "max_score": traj_max}

    node_results = [
        {
            "node_id": r.node_id,
            "status": r.status,
            "score": r.score,
            "max_score": r.max_score,
            "message": r.message,
        }
        for r in results
    ]

    return {
        "total_score": total_score,
        "total_max_score": total_max_score,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "percentage": round(percentage, 2),
        "categories": categories,
        "complexity_distribution": dict(complexity_distribution),
        "trajectories": trajectories,
        "node_results": node_results,
    }
