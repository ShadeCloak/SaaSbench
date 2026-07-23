import json
import os
import sys
import traceback
from collections import defaultdict
from primitives import PRIMITIVE_MAP, PrimitiveResult
from utils import NodeResult, context
from config import TEST_USERS

SKIPPED_AS_PASSTHROUGH = set()


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

def load_dag(path):
    with open(path) as f:
        return json.load(f)


def load_scoring_config(path):
    with open(path) as f:
        return json.load(f)


def topological_sort(nodes):
    id_to_node = {n["id"]: n for n in nodes}
    in_degree = {n["id"]: 0 for n in nodes}
    adj = defaultdict(list)
    for n in nodes:
        for p in n.get("prereqs", []):
            if p in id_to_node:
                adj[p].append(n["id"])
                in_degree[n["id"]] += 1
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    ordered = []
    while queue:
        nid = queue.pop(0)
        ordered.append(id_to_node[nid])
        for child in adj[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    if len(ordered) != len(nodes):
        missing = set(id_to_node.keys()) - {n["id"] for n in ordered}
        print(f"WARNING: Cycle detected or orphan nodes: {missing}")
        for nid in missing:
            ordered.append(id_to_node[nid])
    return ordered


def execute_chain(primitive_chain):
    results = []
    all_passed = True
    for step in primitive_chain:
        ptype = step["type"]
        inputs = step.get("inputs", {})
        resolved_inputs = _resolve_placeholders(inputs)
        func = PRIMITIVE_MAP.get(ptype)
        if not func:
            results.append(PrimitiveResult(passed=False, message=f"Unknown primitive: {ptype}"))
            all_passed = False
            continue
        try:
            result = func(resolved_inputs)
            results.append(result)
            if not result.passed:
                all_passed = False
        except Exception as e:
            results.append(PrimitiveResult(passed=False, message=f"Exception in {ptype}: {e}"))
            all_passed = False
    pass_count = sum(1 for r in results if r.passed)
    pass_ratio = pass_count / len(results) if results else 0
    return type("ChainResult", (), {
        "all_passed": all_passed,
        "pass_ratio": pass_ratio,
        "results": results,
        "evidence": [{"type": r.message, "passed": r.passed, "evidence": r.evidence} for r in results]
    })()


def _resolve_placeholders(obj):
    if isinstance(obj, str):
        import re
        def replacer(m):
            key = m.group(1)
            return str(context.get(key, m.group(0)))
        return re.sub(r'\{\{(\w+)\}\}', replacer, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_placeholders(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_placeholders(v) for v in obj]
    return obj


def execute_dag(dag, scoring_config=None, only_category=None, with_llm=True):
    nodes = dag["nodes"]
    if only_category:
        nodes = [n for n in nodes if n["scoring"]["category"] == only_category]
    ordered = topological_sort(nodes)
    _inject_test_user_placeholders(context)
    results = {}
    for node in ordered:
        nid = node["id"]
        scoring = node["scoring"]
        prereqs = node.get("prereqs", [])
        filtered_ids = {n["id"] for n in nodes}
        prereqs_met = True
        for nid_p in prereqs:
            if nid_p in filtered_ids:
                if nid_p not in results:
                    prereqs_met = False
                    break
                r_p = results[nid_p]
                if r_p.status == "PASSED":
                    continue
                if r_p.status in SKIPPED_AS_PASSTHROUGH:
                    continue
                if getattr(r_p, "score", 0) > 0:
                    continue
                prereqs_met = False
                break
        if not prereqs_met:
            failed_deps = [p for p in prereqs if p in results and results[p].status != "PASSED"]
            missing_deps = [p for p in prereqs if p not in results]
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0,
                max_score=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                message=f"Deps failed: {failed_deps + missing_deps}"
            )
            continue

        try:
            chain_result = execute_chain(node["primitive_chain"])
            PARTIAL_MIN_RATIO = float(os.environ.get("PARTIAL_MIN_RATIO", "0.5"))
            if scoring["method"] == "binary":
                pcf = node.get("partial_credit_factor")
                if pcf is not None and isinstance(pcf, (int, float)) and 0 < pcf < 1 \
                        and chain_result.results:
                    pass_ratio = chain_result.pass_ratio
                    score = round(scoring["maxScore"] * (pass_ratio ** float(pcf)), 2)
                    if pass_ratio >= 1.0:
                        status = "PASSED"
                    elif score > 0 and pass_ratio >= PARTIAL_MIN_RATIO:
                        status = "PARTIAL"
                    elif score > 0:
                        status = "PARTIAL"
                    else:
                        status = "FAILED"
                else:
                    score = scoring["maxScore"] if chain_result.all_passed else 0
                    status = "PASSED" if chain_result.all_passed else "FAILED"
            elif scoring["method"] == "weighted":
                score = round(chain_result.pass_ratio * scoring["maxScore"], 2)
                ratio = (score / scoring["maxScore"]) if scoring["maxScore"] else 0
                if ratio >= 1.0:
                    status = "PASSED"
                elif ratio >= PARTIAL_MIN_RATIO:
                    status = "PASSED"
                elif score > 0:
                    status = "PARTIAL"
                else:
                    status = "FAILED"
            elif scoring["method"] == "llm-judge" and any(
                    isinstance(r.evidence, dict) and r.evidence.get("skipped")
                    for r in chain_result.results):
                score = 0
                status = "SKIPPED_LLM"
            elif scoring["method"] == "llm-judge":
                llm_results = [r for r in chain_result.results
                               if isinstance(r.evidence, dict)
                               and r.evidence.get("score") is not None]
                LLM_THR_ENV = os.environ.get("LLM_JUDGE_PASS_THRESHOLD")
                if llm_results:
                    llm_score = llm_results[-1].evidence["score"]
                    score = min(llm_score, scoring["maxScore"])
                    if LLM_THR_ENV is not None:
                        ratio = (score / scoring["maxScore"]) if scoring["maxScore"] else 0
                        thr = float(LLM_THR_ENV)
                        if ratio >= thr:
                            status = "PASSED"
                        elif score > 0:
                            status = "PARTIAL"
                        else:
                            status = "FAILED"
                    else:
                        status = "PASSED" if score > 0 else "FAILED"
                else:
                    score = scoring["maxScore"] * chain_result.pass_ratio
                    status = "PASSED" if score > 0 else "FAILED"
            else:
                score = 0
                status = "ERROR"

            results[nid] = NodeResult(
                node_id=nid, status=status, score=score,
                max_score=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                evidence={"chain": chain_result.evidence}
            )
        except Exception as e:
            results[nid] = NodeResult(
                node_id=nid, status="ERROR", score=0,
                max_score=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                message=f"Error: {traceback.format_exc()}"
            )
    return results


def aggregate_results(results, scoring_config):
    categories = defaultdict(lambda: {"score": 0, "maxScore": 0, "nodes": 0, "passed": 0, "failed": 0, "skipped": 0})
    total_score = 0
    total_max = 0
    skipped_llm_max = 0.0
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}
    for nid, r in results.items():
        cat = r.category
        categories[cat]["nodes"] += 1
        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.max_score
            categories[cat]["skipped"] += 1
            continue
        categories[cat]["score"] += r.score
        categories[cat]["maxScore"] += r.max_score
        if r.status == "PASSED":
            categories[cat]["passed"] += 1
        elif r.status in ("FAILED", "ERROR"):
            categories[cat]["failed"] += 1
        else:
            categories[cat]["skipped"] += 1
        total_score += r.score
        total_max += r.max_score

    trajectories = {}
    if scoring_config and "trajectories" in scoring_config:
        for tname, tdef in scoring_config["trajectories"].items():
            t_score = sum(results[nid].score for nid in tdef["node_ids"]
                          if nid in results and results[nid].status not in SKIP_FROM_TOTAL)
            t_max = tdef["maxScore"]
            trajectories[tname] = {"score": t_score, "maxScore": t_max,
                                   "rate": round(t_score / t_max * 100, 1) if t_max else 0}

    normalized = round(total_score / total_max * 100, 2) if total_max else 0
    return {
        "total_score": total_score,
        "total_maxScore": total_max,
        "normalized_score": normalized,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "categories": dict(categories),
        "trajectories": trajectories,
        "node_count": len(results),
        "passed": sum(1 for r in results.values() if r.status == "PASSED"),
        "failed": sum(1 for r in results.values() if r.status in ("FAILED", "ERROR")),
        "skipped": sum(1 for r in results.values() if r.status.startswith("SKIPPED")),
    }
