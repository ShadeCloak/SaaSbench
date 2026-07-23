import json
import time
from collections import defaultdict
from utils import NodeResult, context, extract_entity_id, print_result
from primitives import execute_primitive
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

def load_dag(path):
    with open(path, encoding="utf-8") as f:
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
        queue.sort()
        nid = queue.pop(0)
        ordered.append(id_to_node[nid])
        for child in adj[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(ordered) != len(nodes):
        remaining = set(n["id"] for n in nodes) - set(n["id"] for n in ordered)
        print(f"WARNING: Cycle detected, {len(remaining)} nodes unreachable: {remaining}")
        for n in nodes:
            if n["id"] in remaining:
                ordered.append(n)

    return ordered


def execute_node(node, results):
    node_id = node["id"]
    scoring = node["scoring"]
    chain = node["primitive_chain"]
    max_score = scoring["maxScore"]

    primitive_results = []
    try:
        for step in chain:
            ptype = step["type"]
            inputs = step.get("inputs", {})
            result = execute_primitive(ptype, inputs)
            pr_entry = {"type": ptype, "passed": result.passed, "message": result.message}
            if ptype == "P17" and result.data:
                pr_entry["data"] = result.data
            primitive_results.append(pr_entry)

            if result.data and isinstance(result.data, dict):
                extract_entity_id(node_id, result.data)

            if result.response and hasattr(result.response, "status_code"):
                context["last_response"] = result.response
                context["last_status_code"] = result.response.status_code
                try:
                    context["last_response_data"] = result.response.json()
                except Exception:
                    context["last_response_data"] = result.response.text

    except Exception as e:
        return NodeResult(
            node_id=node_id, status="ERROR", score=0, maxScore=max_score,
            category=scoring.get("category", ""), subcategory=scoring.get("subcategory", ""),
            message=str(e), evidence={"primitive_results": primitive_results}
        )

    method = scoring.get("method", "binary")
    passed_count = sum(1 for pr in primitive_results if pr["passed"])
    total_count = len(primitive_results)
    pass_ratio = passed_count / max(total_count, 1)

    if method == "binary":
        all_passed = all(pr["passed"] for pr in primitive_results)
        score = max_score if all_passed else 0
        status = "PASSED" if all_passed else "FAILED"
    elif method == "weighted":
        score = round(pass_ratio * max_score, 2)
        status = "PASSED" if score > 0 else "FAILED"
    elif method == "llm-judge":
        llm_score = 0
        judge_skipped = False
        for pr in primitive_results:
            if pr["type"] == "P17" and pr.get("data"):
                if pr["data"].get("skipped"):
                    judge_skipped = True
                llm_score = pr["data"].get("score", 0)
        if judge_skipped:
            score = 0
            status = "SKIPPED_LLM"
        else:
            score = min(llm_score, max_score)
            status = "PASSED" if score > 0 else "FAILED"
    else:
        score = max_score if pass_ratio == 1.0 else 0
        status = "PASSED" if score > 0 else "FAILED"

    return NodeResult(
        node_id=node_id, status=status, score=score, maxScore=max_score,
        category=scoring.get("category", ""), subcategory=scoring.get("subcategory", ""),
        message=f"{passed_count}/{total_count} primitives passed",
        evidence={"primitive_results": primitive_results}
    )


def execute_dag(dag):
    nodes = dag["nodes"]
    ordered = topological_sort(nodes)
    _inject_test_user_placeholders(context)
    results = {}

    print(f"\n{'='*60}")
    print(f"  Executing DAG: {dag['meta']['task_id']}")
    print(f"  Nodes: {len(ordered)} | Categories: {len(dag['scoring_config']['categories'])}")
    print(f"{'='*60}\n")

    for i, node in enumerate(ordered, 1):
        cat = node["scoring"].get("category", "")
        print(f"[{i}/{len(ordered)}] {cat}/{node['id']}")
        start = time.time()
        result = execute_node(node, results)
        elapsed = time.time() - start
        result.evidence["elapsed_ms"] = round(elapsed * 1000)
        results[node["id"]] = result
        print_result(result)

    return results


SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate_results(results, scoring_config):
    categories = {}
    skipped_llm_max = 0.0
    for nid, nr in results.items():
        cat = nr.category
        if cat not in categories:
            categories[cat] = {"category": cat, "total_score": 0, "max_score": 0, "nodes": 0, "passed": 0, "failed": 0, "skipped": 0, "skipped_llm": 0, "errors": 0}
        in_skip = nr.status in SKIP_FROM_TOTAL
        if not in_skip:
            categories[cat]["total_score"] += nr.score
            categories[cat]["max_score"] += nr.maxScore
        else:
            skipped_llm_max += nr.maxScore
        categories[cat]["nodes"] += 1
        if nr.status == "PASSED":
            categories[cat]["passed"] += 1
        elif nr.status == "FAILED":
            categories[cat]["failed"] += 1
        elif nr.status == "SKIPPED_DEPENDENCY":
            categories[cat]["skipped"] += 1
        elif nr.status == "SKIPPED_LLM":
            categories[cat]["skipped_llm"] += 1
        elif nr.status == "ERROR":
            categories[cat]["errors"] += 1

    total_score = sum(c["total_score"] for c in categories.values())
    total_max = sum(c["max_score"] for c in categories.values())
    percentage = (total_score / total_max * 100) if total_max > 0 else 0

    trajectories = {}
    if "trajectories" in scoring_config:
        for tname, tdata in scoring_config["trajectories"].items():
            t_ids = set(tdata.get("node_ids", []))
            t_score = sum(results[nid].score for nid in t_ids if nid in results and results[nid].status not in SKIP_FROM_TOTAL)
            t_max_declared = tdata.get("maxScore", 0)
            t_skipped_max = sum(results[nid].maxScore for nid in t_ids if nid in results and results[nid].status in SKIP_FROM_TOTAL)
            t_max = max(t_max_declared - t_skipped_max, 0)
            trajectories[tname] = {"score": t_score, "maxScore": t_max, "percentage": (t_score / t_max * 100) if t_max > 0 else 0}

    return {
        "total_score": total_score,
        "total_maxScore": total_max,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "percentage": round(percentage, 1),
        "categories": sorted(categories.values(), key=lambda x: -x["total_score"]),
        "trajectories": trajectories,
        "node_results": {nid: nr.to_dict() for nid, nr in results.items()},
        "summary": {
            "total_nodes": len(results),
            "passed": sum(1 for nr in results.values() if nr.status == "PASSED"),
            "failed": sum(1 for nr in results.values() if nr.status == "FAILED"),
            "skipped": sum(1 for nr in results.values() if nr.status == "SKIPPED_DEPENDENCY"),
            "skipped_llm": sum(1 for nr in results.values() if nr.status == "SKIPPED_LLM"),
            "errors": sum(1 for nr in results.values() if nr.status == "ERROR"),
        }
    }
