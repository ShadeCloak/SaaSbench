import json
import math
import os
import time
import traceback
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from primitives import execute_primitive, context as prim_context
from utils import NodeResult
from config import TEST_USERS
from _result_compat import _result_passed, _result_message, _result_data


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

def load_dag(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_scoring_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes: list[dict]) -> list[dict]:
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for p in n.get("prereqs", []):
            if p in id_to_node:
                adj[p].append(n["id"])
                in_degree[n["id"]] += 1
    queue = deque(nid for nid, d in in_degree.items() if d == 0)
    order = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for nb in adj[nid]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)
    return [id_to_node[nid] for nid in order if nid in id_to_node]


def execute_dag(dag: dict, scoring_config: dict,
                only_category: str | None = None,
                with_llm: bool = False,
                dry_run: bool = False) -> list[NodeResult]:
    nodes = dag["nodes"]
    ordered = topological_sort(nodes)

    _inject_test_user_placeholders(prim_context)

    _TRANSIENT_CTX = {"auth_token", "admin_token", "last_response",
                      "last_created_id", "last_entity_id", "last_db_result"}
    _seed_fixtures = {k: v for k, v in prim_context.items()
                      if k not in _TRANSIENT_CTX and not k.endswith("_token")}

    results: dict[str, NodeResult] = {}
    all_results: list[NodeResult] = []

    for node in ordered:
        nid = node["id"]
        scoring = node["scoring"]
        category = scoring["category"]
        subcategory = scoring.get("subcategory", "")
        method = scoring["method"]
        max_score = scoring["maxScore"]

        if only_category and category.lower() != only_category.lower():
            continue

        if method == "llm-judge" and not with_llm:
            nr = NodeResult(nid, "SKIPPED_LLM", 0, max_score, category, subcategory,
                            "LLM judge skipped (use --with-llm)")
            results[nid] = nr
            all_results.append(nr)
            continue

        if dry_run:
            nr = NodeResult(nid, "DRY_RUN", 0, max_score, category, subcategory, "Dry run")
            results[nid] = nr
            all_results.append(nr)
            continue

        prereqs = node.get("prereqs", [])
        deps_ok = True
        for dep_id in prereqs:
            dep = results.get(dep_id)
            if dep is None:
                deps_ok = False
                break
            if dep.status not in ("PASSED", "PARTIAL"):
                deps_ok = False
                break

        if not deps_ok:
            nr = NodeResult(nid, "SKIPPED_DEPENDENCY", 0, max_score, category, subcategory,
                            f"Prereqs not met: {prereqs}")
            results[nid] = nr
            all_results.append(nr)
            continue

        prim_context.update(_seed_fixtures)

        try:
            chain = node.get("primitive_chain", [])
            chain_results = []
            chain_evidence = {}
            all_passed = True
            llm_skipped = False
            llm_steps = []

            for i, step in enumerate(chain):
                ptype = step["type"]
                inputs = step.get("inputs", {})
                pr = execute_primitive(ptype, inputs)
                chain_results.append(pr)
                _passed = _result_passed(pr)
                chain_evidence[f"step_{i}_{ptype}"] = {
                    "passed": _passed, "message": _result_message(pr),
                    "data": _safe_serialize(_result_data(pr)),
                }
                if not _passed:
                    all_passed = False

            passed_count = sum(1 for cr in chain_results if _result_passed(cr))
            total_count = len(chain_results) or 1
            pass_ratio = (passed_count / total_count) if total_count else 0

            if method == "binary":
                score = max_score if all_passed else 0
            elif method == "weighted":
                _PLUMBING = {"P04", "P13", "P18", "P19", "RENDER_DOM", "SCREENSHOT"}
                def _is_plumbing(st):
                    t = st.get("type")
                    if t in _PLUMBING:
                        return True
                    if t == "P07":
                        aa = st.get("inputs", {}).get("assertions", []) or []
                        if aa and all(a.get("store_as") for a in aa):
                            return True
                    return False
                _verif = [cr for st, cr in zip(chain, chain_results)
                          if not _is_plumbing(st)]
                if _verif:
                    _vr = sum(1 for cr in _verif if _result_passed(cr)) / len(_verif)
                else:
                    _vr = pass_ratio
                score = round(_vr * max_score, 2)
            elif method == "llm-judge":
                llm_skipped = any(
                    cr.data and isinstance(cr.data, dict) and cr.data.get("skipped")
                    for cr in chain_results
                )
                llm_steps = [cr for cr in chain_results
                             if cr.data and isinstance(cr.data, dict) and "score" in cr.data
                             and not cr.data.get("skipped")]
                if llm_skipped and not llm_steps:
                    score = 0
                elif llm_steps:
                    llm_data = llm_steps[-1].data
                    sr = node["primitive_chain"][-1]["inputs"].get("score_range", [0, 5])
                    raw = llm_data.get("score", 0)
                    score = round((raw / max(sr[1], 1)) * max_score, 2)
                else:
                    score = 0
            else:
                score = max_score if all_passed else 0

            if method == "llm-judge" and llm_skipped and not llm_steps:
                status = "SKIPPED_LLM"
            else:
                status = "PASSED" if score >= max_score else ("PARTIAL" if score > 0 else "FAILED")
            message = "; ".join(cr.message for cr in chain_results if cr.message)

            nr = NodeResult(nid, status, score, max_score, category, subcategory,
                            message[:500], chain_evidence)
            _extract_entity_ids(nid, chain_results)

        except Exception as e:
            nr = NodeResult(nid, "ERROR", 0, max_score, category, subcategory,
                            f"Exception: {e}\n{traceback.format_exc()[:300]}")

        results[nid] = nr
        all_results.append(nr)

    return all_results


def _extract_entity_ids(node_id: str, chain_results: list):
    nid_lower = node_id.lower()
    for cr in chain_results:
        if not cr.data or not isinstance(cr.data, dict):
            continue
        body = cr.data.get("body") if isinstance(cr.data.get("body"), dict) else cr.data
        if not isinstance(body, dict):
            continue
        for key, val in body.items():
            if isinstance(val, dict) and "id" in val:
                entity_id = val["id"]
                prim_context[f"{key}_id"] = entity_id
                if "customer" in nid_lower and "customer" in key:
                    prim_context["customer_id"] = entity_id
                elif "product" in nid_lower and "product" in key:
                    prim_context["product_id"] = entity_id
                elif "variant" in key:
                    prim_context["variant_id"] = entity_id
                elif "order" in nid_lower and "order" in key:
                    prim_context["order_id"] = entity_id
                elif "cart" in key:
                    prim_context["cart_id"] = entity_id
                elif "region" in key:
                    prim_context["region_id"] = entity_id

        if isinstance(cr.data, dict) and "entity_id" in cr.data:
            prim_context["last_entity_id"] = cr.data["entity_id"]


def _safe_serialize(obj, max_depth=3) -> Any:
    if max_depth <= 0:
        return str(obj)[:200]
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialize(v, max_depth - 1) for k, v in list(obj.items())[:50]}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v, max_depth - 1) for v in obj[:20]]
    return str(obj)[:200]


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def aggregate_results(results: list[NodeResult], scoring_config: dict) -> dict:
    by_category: dict[str, list[NodeResult]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)

    categories_summary = []
    total_score = 0
    total_max = 0
    skipped_llm_max = 0.0
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}

    for cat_name, cat_results in sorted(by_category.items()):
        cat_score = sum(r.score for r in cat_results if r.status not in SKIP_FROM_TOTAL)
        cat_max = sum(r.maxScore for r in cat_results if r.status not in SKIP_FROM_TOTAL)
        cat_skip_max = sum(r.maxScore for r in cat_results if r.status in SKIP_FROM_TOTAL)
        skipped_llm_max += cat_skip_max
        total_score += cat_score
        total_max += cat_max
        categories_summary.append({
            "category": cat_name,
            "total_score": round(cat_score, 2),
            "max_score": cat_max,
            "percentage": round(cat_score / cat_max * 100, 1) if cat_max > 0 else 0,
            "node_count": len(cat_results),
            "passed": sum(1 for r in cat_results if r.status == "PASSED"),
            "failed": sum(1 for r in cat_results if r.status == "FAILED"),
            "errors": sum(1 for r in cat_results if r.status == "ERROR"),
            "skipped": sum(1 for r in cat_results if r.status.startswith("SKIPPED")),
            "llm_judge_skipped_maxScore": round(cat_skip_max, 2),
        })

    trajectories = {}
    for traj_name, traj_info in scoring_config.get("trajectories", {}).items():
        traj_ids = set(traj_info.get("node_ids", []))
        traj_results = [r for r in results if r.node_id in traj_ids and r.status not in SKIP_FROM_TOTAL]
        traj_score = sum(r.score for r in traj_results)
        traj_max = sum(r.maxScore for r in traj_results)
        trajectories[traj_name] = {
            "description": traj_info.get("description", ""),
            "score": round(traj_score, 2),
            "max_score": traj_max,
            "percentage": round(traj_score / traj_max * 100, 1) if traj_max > 0 else 0,
        }

    status_counts = defaultdict(int)
    for r in results:
        status_counts[r.status] += 1

    return {
        "total_score": round(total_score, 2),
        "total_max": total_max,
        "percentage": round(total_score / total_max * 100, 1) if total_max > 0 else 0,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 2),
        "categories": categories_summary,
        "trajectories": trajectories,
        "status_distribution": dict(status_counts),
        "node_count": len(results),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def generate_report(results: list[NodeResult], scoring_config: dict,
                    output_path: str):
    summary = aggregate_results(results, scoring_config)
    summary["node_results"] = [r.to_dict() for r in results]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    return summary
