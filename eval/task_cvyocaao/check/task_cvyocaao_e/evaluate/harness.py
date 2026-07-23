import json
import sys
import traceback



try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

sys.setrecursionlimit(3000)
from collections import defaultdict
from utils import NodeResult, context, print_result
from primitives import execute_primitive, get_last_response
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


def load_dag(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes):
    node_map = {n["id"]: n for n in nodes}
    in_degree = {n["id"]: 0 for n in nodes}
    adj = defaultdict(list)
    for n in nodes:
        for p in n.get("prereqs", []):
            if p in node_map:
                adj[p].append(n["id"])
                in_degree[n["id"]] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    ordered = []
    while queue:
        queue.sort()
        nid = queue.pop(0)
        ordered.append(nid)
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) != len(nodes):
        missing = set(n["id"] for n in nodes) - set(ordered)
        print(f"WARNING: Cycle detected, missing nodes: {missing}", file=sys.stderr)
        for n in nodes:
            if n["id"] not in ordered:
                ordered.append(n["id"])

    return [node_map[nid] for nid in ordered]


def execute_dag(dag, scoring_config=None, only_category=None, with_llm=True):
    nodes = dag["nodes"]

    if only_category:
        nodes = [n for n in nodes if n["scoring"]["category"] == only_category]
        all_ids = {n["id"] for n in nodes}
        for n in nodes:
            n["prereqs"] = [p for p in n.get("prereqs", []) if p in all_ids]

    ordered = topological_sort(nodes)
    _inject_test_user_placeholders(context)
    results = {}
    passed_ids = set()

    print(f"\n{'='*60}")
    print(f"  Executing {len(ordered)} DAG nodes")
    print(f"{'='*60}\n")

    for node in ordered:
        nid = node["id"]
        scoring = node["scoring"]

        prereqs_ok = all(p in passed_ids for p in node.get("prereqs", []))
        if not prereqs_ok:
            failed_deps = [p for p in node.get("prereqs", []) if p not in passed_ids]
            result = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0,
                maxScore=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                message=f"Skipped: dependencies not met ({failed_deps})"
            )
            results[nid] = result
            print_result(result)
            continue

        if scoring.get("method") == "llm-judge" and not with_llm:
            result = NodeResult(
                node_id=nid, status="SKIPPED_LLM", score=0,
                maxScore=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                message="LLM judge skipped (--no-llm)"
            )
            results[nid] = result
            print_result(result)
            continue

        try:
            result = execute_node(node)
        except Exception as e:
            result = NodeResult(
                node_id=nid, status="ERROR", score=0,
                maxScore=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                message=f"Exception: {str(e)[:200]}",
                evidence={"traceback": traceback.format_exc()[-500:]}
            )

        results[nid] = result
        if result.status == "PASSED" or result.score > 0:
            passed_ids.add(nid)
        print_result(result)

        _extract_entity_ids(node, result)

    return list(results.values())


def execute_node(node):
    nid = node["id"]
    scoring = node["scoring"]
    chain = node.get("primitive_chain", [])
    method = scoring.get("method", "binary")
    max_score = scoring["maxScore"]

    chain_results = []
    all_passed = True
    _last_primitive_data = {}
    skipped_llm = False

    for prim in chain:
        ptype = prim["type"]
        inputs = prim.get("inputs", {})

        pr = execute_primitive(ptype, inputs)
        _passed = _result_passed(pr)
        _msg = _result_message(pr)
        _data = _result_data(pr)
        if ptype in ("P04", "P13"):
            _verif = False
        elif ptype == "P07":
            _asserts = inputs.get("assertions", []) or []
            _verif = any(a.get("operator") != "store_as" for a in _asserts)
        else:
            _verif = True
        chain_results.append({"type": ptype, "passed": _passed, "message": _msg, "data": _data, "verif": _verif})
        _last_primitive_data = {"data": _data, "passed": _passed}

        if not _passed:
            all_passed = False

        if ptype == "P04" and _data and isinstance(_data, dict) and _data.get("body"):
            _store_response_ids(nid, _data["body"])

    if method == "binary":
        score = max_score if all_passed else 0
    elif method == "weighted":
        pass_count = sum(1 for r in chain_results if r["passed"])
        total_items = max(len(chain_results), 1)
        last_data = _last_primitive_data.get("data", {})
        if isinstance(last_data, dict) and "found_count" in last_data and "total_count" in last_data:
            ratio = last_data["found_count"] / max(last_data["total_count"], 1)
        elif isinstance(last_data, dict) and "steps_passed" in last_data and "steps_total" in last_data:
            ratio = last_data["steps_passed"] / max(last_data["steps_total"], 1)
        else:
            _verif_results = [r for r in chain_results if r.get("verif")]
            if _verif_results:
                ratio = sum(1 for r in _verif_results if r["passed"]) / len(_verif_results)
            else:
                ratio = (pass_count / total_items) if total_items else 0
        score = round(ratio * max_score, 1)
    elif method == "llm-judge":
        llm_data = _last_primitive_data.get("data", {})
        if isinstance(llm_data, dict) and llm_data.get("skipped"):
            score = 0
            skipped_llm = True
        elif isinstance(llm_data, dict) and "score" in llm_data:
            llm_score = llm_data["score"]
            score_range = [0, max_score]
            for p in reversed(chain):
                if p["type"] == "P17":
                    score_range = p.get("inputs", {}).get("score_range", [0, max_score])
                    break
            score = round(llm_score / max(score_range[1], 1) * max_score, 1)
        else:
            score = 0
    else:
        score = max_score if all_passed else 0

    if skipped_llm:
        status = "SKIPPED_LLM"
    else:
        status = "PASSED" if score > 0 else "FAILED"

    return NodeResult(
        node_id=nid, status=status, score=score, maxScore=max_score,
        category=scoring["category"], subcategory=scoring.get("subcategory", ""),
        message=f"{sum(1 for r in chain_results if r['passed'])}/{len(chain_results)} primitives passed",
        evidence={"chain_results": chain_results}
    )


def _store_response_ids(node_id, body):
    if isinstance(body, dict):
        if "id" in body:
            nid_lower = node_id.lower()
            context[f"{node_id}_id"] = body["id"]
            if "realm" in nid_lower and "cross" not in nid_lower and "isolation" not in nid_lower:
                context["realm_id"] = body.get("id", "")
            if nid_lower.startswith("crud_user") or nid_lower == "user_":
                context["uid"] = body.get("id", "")
                context["user_id"] = body.get("id", "")
            if nid_lower.startswith("crud_client"):
                context["client_uuid"] = body.get("id", "")
                context["test_client_uuid"] = body.get("id", "")
            if nid_lower.startswith("crud_role"):
                context["eval_role_id"] = body.get("id", "")
            if nid_lower.startswith("crud_group"):
                context["group_id"] = body.get("id", "")
                context["parent_group_id"] = body.get("id", "")
            if "org_create" in nid_lower:
                context["org_id"] = body.get("id", "")

        if "clientId" in body:
            context["test_client_id"] = body.get("clientId", "")
        if "secret" in body:
            context["test_client_secret"] = body.get("secret", "")

    if isinstance(body, list) and body:
        if "Location" in str(context.get("_last_headers", {})):
            pass


def _extract_entity_ids(node, result):
    if result.evidence and "chain_results" in result.evidence:
        pass


def aggregate_results(results, scoring_config):
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}
    categories = defaultdict(lambda: {"total_score": 0, "max_score": 0, "nodes": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0})

    for r in results:
        cat = r.category
        categories[cat]["nodes"] += 1
        if r.status == "PASSED":
            categories[cat]["passed"] += 1
        elif r.status == "FAILED":
            categories[cat]["failed"] += 1
        elif r.status.startswith("SKIPPED"):
            categories[cat]["skipped"] += 1
        else:
            categories[cat]["error"] += 1
        if r.status in SKIP_FROM_TOTAL:
            continue
        categories[cat]["total_score"] += r.score
        categories[cat]["max_score"] += r.maxScore

    total_score = sum(r.score for r in results if r.status not in SKIP_FROM_TOTAL)
    total_max = sum(r.maxScore for r in results if r.status not in SKIP_FROM_TOTAL)
    skipped_llm_max = sum(r.maxScore for r in results if r.status in SKIP_FROM_TOTAL)

    return {
        "total_score": total_score,
        "total_max": total_max,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "percentage": round(total_score / total_max * 100, 1) if total_max > 0 else 0,
        "total_nodes": len(results),
        "passed_nodes": sum(1 for r in results if r.status == "PASSED"),
        "failed_nodes": sum(1 for r in results if r.status == "FAILED"),
        "skipped_nodes": sum(1 for r in results if r.status.startswith("SKIPPED")),
        "error_nodes": sum(1 for r in results if r.status == "ERROR"),
        "categories": [
            {"category": k, **v}
            for k, v in sorted(categories.items())
        ],
    }
