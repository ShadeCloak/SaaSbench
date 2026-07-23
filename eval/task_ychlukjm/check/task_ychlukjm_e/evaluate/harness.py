
from __future__ import annotations

import importlib
import json
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any

import config
from utils import NodeResult, ArtifactStore, artifact_store



try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

logger = logging.getLogger("eval.harness")


def load_dag(path: str | None = None) -> dict:
    with open(path or config.DAG_PATH) as f:
        return json.load(f)


def load_scoring_config(path: str | None = None) -> dict:
    with open(path or config.SCORING_CONFIG_PATH) as f:
        return json.load(f)


def topological_sort(nodes: list[dict]) -> list[dict]:
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    children: dict[str, list[str]] = defaultdict(list)

    for n in nodes:
        for p in n.get("prereqs", []):
            if p in id_to_node:
                children[p].append(n["id"])
                in_degree[n["id"]] += 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    ordered: list[dict] = []
    while queue:
        nid = queue.popleft()
        ordered.append(id_to_node[nid])
        for child in children[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(ordered) != len(nodes):
        missing = set(n["id"] for n in nodes) - set(n["id"] for n in ordered)
        logger.error("Cycle detected; unreachable nodes: %s", missing)
    return ordered


def _category_to_module(category: str) -> str:
    mapping = {
        "ArchitectureQuality": "test_architecture",
        "Authentication": "test_authentication",
        "Authorization": "test_authorization",
        "BusinessLogic": "test_business_logic",
        "DataModel": "test_data_model",
        "Deployment": "test_deployment",
        "EdgeCases": "test_edge_cases",
        "EntityLifecycle": "test_entity_lifecycle",
        "Frontend": "test_frontend",
        "GraphQLAPI": "test_graphql_api",
        "IngestionCLI": "test_ingestion_cli",
        "Lineage": "test_lineage",
        "OpenAPIRest": "test_openapi_rest",
        "SearchDiscovery": "test_search_discovery",
    }
    return mapping.get(category, f"test_{category.lower()}")


def _node_id_to_func(node_id: str) -> str:
    return f"test_{node_id.lower()}"


def execute_node(node: dict, results: dict[str, NodeResult]) -> NodeResult:
    node_id = node["id"]
    category = node["scoring"]["category"]
    max_score = node["scoring"]["maxScore"]

    for prereq in node.get("prereqs", []):
        pr = results.get(prereq)
        if pr is None or pr.status in ("SKIPPED_DEPENDENCY", "ERROR") or pr.score == 0:
            return NodeResult(
                node_id=node_id, status="SKIPPED_DEPENDENCY",
                score=0, max_score=max_score,
                message=f"Prerequisite {prereq} not satisfied",
            )

    artifact_store.push_context(node_id)
    try:
        mod_name = _category_to_module(category)
        mod = importlib.import_module(f"tests.{mod_name}")
        func_name = _node_id_to_func(node_id)
        func = getattr(mod, func_name, None)
        if func is None:
            return NodeResult(
                node_id=node_id, status="ERROR", score=0, max_score=max_score,
                message=f"Test function {func_name} not found in tests.{mod_name}",
            )

        result: NodeResult = func(node)
        result.max_score = max_score
        return result

    except Exception as exc:
        logger.exception("Node %s raised an exception", node_id)
        return NodeResult(
            node_id=node_id, status="ERROR", score=0, max_score=max_score,
            message=f"Exception: {exc}",
        )
    finally:
        artifact_store.pop_context()


def run_dag(dag: dict, scoring_config: dict) -> dict:
    nodes = dag.get("nodes", [])
    ordered = topological_sort(nodes)
    results: dict[str, NodeResult] = {}

    logger.info("Executing %d nodes …", len(ordered))
    start = time.time()

    for i, node in enumerate(ordered, 1):
        nid = node["id"]
        logger.info("[%d/%d] %s", i, len(ordered), nid)
        result = execute_node(node, results)
        results[nid] = result
        status_icon = "✓" if result.score > 0 else ("⊘" if result.status == "SKIPPED_DEPENDENCY" else "✗")
        logger.info("  %s  %.1f / %.1f  %s", status_icon, result.score, result.max_score, result.message[:80])

    elapsed = time.time() - start
    return aggregate(results, scoring_config, elapsed)


def aggregate(results: dict[str, NodeResult], scoring_config: dict,
              elapsed: float = 0) -> dict:
    categories: dict[str, dict] = defaultdict(lambda: {"score": 0, "max_score": 0, "nodes": []})
    tiers: dict[str, dict] = defaultdict(lambda: {"score": 0, "max_score": 0, "count": 0})

    all_nodes_detail = []
    for nid, nr in results.items():
        all_nodes_detail.append(nr.to_dict())

    sc_cats = scoring_config.get("categories", {})
    for cat_name, cat_info in sc_cats.items():
        categories[cat_name]["max_score"] = cat_info.get("maxScore", 0)

    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}

    for nid, nr in results.items():
        cat = nr.evidence.get("category", "Unknown")
        categories[cat]["nodes"].append(nr.to_dict())
        if nr.status in SKIP_FROM_TOTAL:
            continue
        categories[cat]["score"] += nr.score

    total_score = sum(nr.score for nr in results.values() if nr.status not in SKIP_FROM_TOTAL)
    total_max = sum(nr.max_score for nr in results.values() if nr.status not in SKIP_FROM_TOTAL)
    skipped_llm_max = sum(nr.max_score for nr in results.values() if nr.status in SKIP_FROM_TOTAL)

    trajectories = {}
    for tname, tinfo in scoring_config.get("trajectories", {}).items():
        traj_score = sum(results[nid].score for nid in tinfo["node_ids"]
                         if nid in results and results[nid].status not in SKIP_FROM_TOTAL)
        traj_max = tinfo.get("maxScore", 0)
        trajectories[tname] = {
            "score": traj_score,
            "max_score": traj_max,
            "percentage": (traj_score / traj_max * 100) if traj_max else 0,
        }

    return {
        "total_score": total_score,
        "total_max_score": total_max,
        "percentage": (total_score / total_max * 100) if total_max else 0,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "elapsed_seconds": round(elapsed, 2),
        "categories": [
            {
                "category": cat,
                "total_score": info["score"],
                "max_score": info["max_score"],
                "percentage": (info["score"] / info["max_score"] * 100) if info["max_score"] else 0,
                "nodes": info["nodes"],
            }
            for cat, info in sorted(categories.items())
        ],
        "trajectories": trajectories,
        "node_results": all_nodes_detail,
    }
