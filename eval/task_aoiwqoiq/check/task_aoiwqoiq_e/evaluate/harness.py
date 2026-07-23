from __future__ import annotations

import json
import os
import time
import traceback
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set
from utils import NodeResult, print_summary, save_results, resolve_placeholders
from primitives import execute_primitive
from config import TEST_USERS


def _inject_test_user_placeholders(context: dict) -> None:
    for role, user_info in TEST_USERS.items():
        if not isinstance(user_info, dict):
            continue
        for field, value in user_info.items():
            if isinstance(value, (str, int, float, bool)):
                context[f"{role}_{field}"] = value
                context[f"eval_{role}_{field}"] = value




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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes: list) -> list:
    node_map = {n["id"]: n for n in nodes}
    in_degree = {n["id"]: 0 for n in nodes}
    adjacency = defaultdict(list)

    for node in nodes:
        for prereq in node.get("prereqs", []):
            if prereq in node_map:
                adjacency[prereq].append(node["id"])
                in_degree[node["id"]] += 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    ordered = []

    while queue:
        nid = queue.popleft()
        ordered.append(node_map[nid])
        for neighbor in adjacency[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) != len(nodes):
        visited_ids = {n["id"] for n in ordered}
        missing = [n["id"] for n in nodes if n["id"] not in visited_ids]
        raise ValueError(f"DAG has cycles involving nodes: {missing}")

    return ordered


class ArtifactStore:
    def __init__(self):
        self._evidence: dict[str, list] = defaultdict(list)
        self._stack: list[str] = []

    def push_context(self, node_id: str):
        self._stack.append(node_id)

    def pop_context(self) -> str | None:
        return self._stack.pop() if self._stack else None

    @property
    def _current(self) -> str | None:
        return self._stack[-1] if self._stack else None

    def store(self, key: str, value):
        if self._current:
            self._evidence[self._current].append({"key": key, "value": value})

    def get_evidence(self, node_id: str) -> list:
        return list(self._evidence.get(node_id, []))

    def get_all(self) -> dict[str, list]:
        return dict(self._evidence)


_ALWAYS_OVERWRITE_ID_KEYS = {
    "id", "topic_id", "post_id", "user_id", "category_id",
    "tag_id", "badge_id", "group_id", "review_id", "reviewable_id",
    "notification_id", "upload_id", "draft_sequence",
}


def _put(context: dict, key: str, value):
    if key in _ALWAYS_OVERWRITE_ID_KEYS:
        context[key] = value
    else:
        context.setdefault(key, value)


def _extract_and_store_ids(context: dict, body):
    if not isinstance(body, dict):
        if isinstance(body, list) and body and isinstance(body[0], dict):
            _extract_and_store_ids(context, body[0])
        return

    if "post" in body and isinstance(body["post"], dict):
        post = body["post"]
        if "id" in post:
            context["id"] = post["id"]
            context["post_id"] = post["id"]
        for k, v in post.items():
            if isinstance(v, (str, int, float, bool)):
                _put(context, k, v)

    if "topic" in body and isinstance(body["topic"], dict):
        topic = body["topic"]
        if "id" in topic:
            context["topic_id"] = topic["id"]
        for k, v in topic.items():
            if isinstance(v, (str, int, float, bool)):
                _put(context, f"topic_{k}", v)

    if "user" in body and isinstance(body["user"], dict):
        user = body["user"]
        if "id" in user:
            context["user_id"] = user["id"]

    data = body.get("data")
    if isinstance(data, dict):
        if "id" in data:
            context["id"] = data["id"]
        if isinstance(data.get("attributes"), dict):
            for k, v in data["attributes"].items():
                if isinstance(v, (str, int, float, bool)):
                    _put(context, k, v)
        for envelope_key, envelope_val in data.items():
            if isinstance(envelope_val, dict) and "id" in envelope_val:
                _put(context, f"{envelope_key}_id", envelope_val["id"])
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        if "id" in data[0]:
            context["id"] = data[0]["id"]

    for k, v in body.items():
        if isinstance(v, (str, int, float, bool)):
            _put(context, k, v)
        elif isinstance(v, dict) and "id" in v and isinstance(v["id"], (str, int)):
            _put(context, f"{k}_id", v["id"])

    if "id" in body and isinstance(body["id"], (str, int)) and "post_number" in body:
        context["post_id"] = body["id"]


def execute_dag(
    dag: dict,
    scoring_config: dict,
    only_category: str = None,
    dry_run: bool = False,
    with_llm: bool = False,
) -> list:
    nodes = dag.get("nodes", [])
    if only_category:
        nodes = [n for n in nodes if n.get("scoring", {}).get("category") == only_category]

    sorted_nodes = topological_sort(nodes)

    if dry_run:
        results = []
        for node in sorted_nodes:
            scoring = node.get("scoring", {})
            results.append(NodeResult(
                node_id=node["id"],
                status="DRY_RUN",
                score=0,
                max_score=scoring.get("maxScore", 0),
                category=scoring.get("category", ""),
                subcategory=scoring.get("subcategory", ""),
                complexity_tier=node.get("complexity_tier", ""),
                message="Dry run — not executed",
                evidence=[],
                elapsed=0.0,
            ))
        return results

    context: dict = {}
    _inject_test_user_placeholders(context)
    artifacts = ArtifactStore()
    passed_nodes: set[str] = set()
    results: list = []

    total_nodes = len(sorted_nodes)
    for node_idx, node in enumerate(sorted_nodes, 1):
        node_id = node["id"]
        scoring = node.get("scoring", {})
        max_score = scoring.get("maxScore", 0)
        method = scoring.get("method", "binary")
        category = scoring.get("category", "")
        subcategory = scoring.get("subcategory", "")
        complexity_tier = node.get("complexity_tier", "")
        chain = node.get("primitive_chain", [])

        prereqs = node.get("prereqs", [])
        failed_prereqs = [p for p in prereqs if p not in passed_nodes]
        if failed_prereqs:
            print(f"[{node_idx}/{total_nodes}] {node_id}: SKIPPED (prereq: {failed_prereqs[0]})")
            results.append(NodeResult(
                node_id=node_id,
                status="SKIPPED_DEPENDENCY",
                score=0,
                max_score=max_score,
                category=category,
                subcategory=subcategory,
                complexity_tier=complexity_tier,
                message=f"Skipped: prerequisites not met ({', '.join(failed_prereqs)})",
                evidence=[],
                elapsed=0.0,
            ))
            continue

        print(f"[{node_idx}/{total_nodes}] {node_id}: running...", end="", flush=True)

        artifacts.push_context(node_id)
        t0 = time.time()
        primitive_results = []
        chain_error = None

        context["_chain_screenshot_start_idx"] = len(context.get("screenshots") or [])
        context["_chain_node_id"] = node_id

        try:
            for prim in chain:
                ptype = prim["type"]
                raw_inputs = prim.get("inputs", {})
                resolved_inputs = resolve_placeholders(raw_inputs, context)

                prim_result = execute_primitive(ptype, resolved_inputs, context)
                primitive_results.append((ptype, prim_result))
                ev_data = {
                    "inputs": resolved_inputs,
                    "success": prim_result.success,
                    "message": prim_result.message,
                }
                if prim_result.data:
                    if ptype == "P12":
                        ev_data["output"] = str(prim_result.data.get("output", ""))[:500]
                    if ptype == "P04":
                        body_snippet = prim_result.data.get("body", "")
                        if isinstance(body_snippet, dict):
                            ev_data["resp_body"] = {k: v for i, (k, v) in enumerate(body_snippet.items()) if i < 5}
                        elif isinstance(body_snippet, str):
                            ev_data["resp_body"] = body_snippet[:200]
                artifacts.store(f"primitive_{ptype}", ev_data)

                if prim_result.success and ptype == "P04":
                    body = context.get("last_body")
                    if isinstance(body, dict):
                        _extract_and_store_ids(context, body)

                if not prim_result.success and method == "binary":
                    break
        except Exception as exc:
            chain_error = str(exc)
            artifacts.store("error", {
                "exception": chain_error,
                "traceback": traceback.format_exc(),
            })

        elapsed = time.time() - t0

        passed_count = sum(1 for _, r in primitive_results if r.success)
        total_count = len(chain)

        if chain_error:
            score = 0
            status = "ERROR"
            message = f"Error: {chain_error}"
        elif method == "binary":
            if passed_count == total_count and total_count > 0:
                score = max_score
            else:
                score = 0
            status = "PASSED" if score > 0 else "FAILED"
            failed_prims = [
                pt for pt, r in primitive_results if not r.success
            ]
            message = "All primitives passed" if status == "PASSED" else f"Failed primitives: {failed_prims}"
        elif method == "weighted":
            if total_count > 0:
                score = round((passed_count / total_count) * max_score, 1) if total_count else 0
            else:
                score = 0
            status = "PASSED" if score > 0 else "FAILED"
            message = f"{passed_count}/{total_count} primitives passed"
        elif method == "llm-judge":
            if not with_llm:
                score = 0
                status = "SKIPPED_LLM"
                message = "LLM judge not enabled"
            else:
                llm_result = next(
                    (r for pt, r in primitive_results if pt == "P17"),
                    None,
                )
                if llm_result and isinstance(llm_result.data, dict) and llm_result.data.get("skipped"):
                    score = 0
                    status = "SKIPPED_LLM"
                    message = llm_result.message
                elif llm_result and llm_result.success:
                    score = llm_result.data.get("llm_score", llm_result.data.get("score", 0))
                    status = "PASSED" if score > 0 else "FAILED"
                    message = llm_result.message
                else:
                    score = 0
                    status = "PASSED" if score > 0 else "FAILED"
                    message = llm_result.message if llm_result else "No P17 result"
        else:
            score = 0
            status = "FAILED"
            message = f"Unknown scoring method: {method}"

        print(f" {status} ({elapsed:.1f}s) score={score}/{max_score}")
        if status == "PASSED":
            passed_nodes.add(node_id)

        artifacts.pop_context()

        results.append(NodeResult(
            node_id=node_id,
            status=status,
            score=score,
            max_score=max_score,
            category=category,
            subcategory=subcategory,
            complexity_tier=complexity_tier,
            message=message,
            evidence=artifacts.get_evidence(node_id),
            elapsed=elapsed,
        ))

    return results


def aggregate_results(results: list, scoring_config: dict) -> dict:
    total_score = 0
    total_max = 0
    by_category: dict[str, dict] = defaultdict(lambda: {
        "score": 0, "maxScore": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0,
    })
    by_complexity: dict[str, dict] = defaultdict(lambda: {"score": 0, "maxScore": 0})
    node_details = []

    skipped_llm_max = 0.0
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}

    for r in results:
        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.max_score
            cat = by_category[r.category]
            cat["skipped"] += 1
            continue
        total_score += r.score
        total_max += r.max_score

        cat = by_category[r.category]
        cat["score"] += r.score
        cat["maxScore"] += r.max_score
        if r.status == "PASSED":
            cat["passed"] += 1
        elif r.status in ("SKIPPED_DEPENDENCY", "DRY_RUN"):
            cat["skipped"] += 1
        elif r.status == "ERROR":
            cat["error"] += 1
        else:
            cat["failed"] += 1

        tier = by_complexity[r.complexity_tier]
        tier["score"] += r.score
        tier["maxScore"] += r.max_score

        node_details.append({
            "node_id": r.node_id,
            "status": r.status,
            "score": r.score,
            "maxScore": r.max_score,
            "message": r.message,
        })

    for cat_data in by_category.values():
        ms = cat_data["maxScore"]
        cat_data["pct"] = round((cat_data["score"] / ms) * 100, 1) if ms else 0.0
    for tier_data in by_complexity.values():
        ms = tier_data["maxScore"]
        tier_data["pct"] = round((tier_data["score"] / ms) * 100, 1) if ms else 0.0

    trajectories_cfg = scoring_config.get("trajectories", {})
    result_map = {r.node_id: r for r in results}
    by_trajectory = {}

    for traj_name, traj_info in trajectories_cfg.items():
        traj_node_ids = traj_info.get("node_ids", [])
        traj_max = traj_info.get("maxScore", 0)
        traj_score = sum(result_map[nid].score for nid in traj_node_ids if nid in result_map)
        by_trajectory[traj_name] = {
            "score": traj_score,
            "maxScore": traj_max,
            "pct": round((traj_score / traj_max) * 100, 1) if traj_max else 0.0,
        }

    overall_pct = round((total_score / total_max) * 100, 1) if total_max else 0.0
    config_total_max = scoring_config.get("total_maxScore", total_max)
    normalized = round((total_score / config_total_max) * 100, 1) if config_total_max else 0.0

    return {
        "overall": {
            "score": total_score,
            "maxScore": total_max,
            "pct": overall_pct,
            "normalized_score": normalized,
            "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        },
        "by_category": dict(by_category),
        "by_complexity": dict(by_complexity),
        "by_trajectory": by_trajectory,
        "node_details": node_details,
    }


def generate_report(results: list, scoring_config: dict, output_path: str) -> str:
    report = aggregate_results(results, scoring_config)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    return output_path
