import json
import time
from collections import defaultdict
from utils import NodeResult, print_result
from primitives import execute_primitive
from config import RESULTS_DIR, TEST_USERS


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

class ArtifactStore:
    def __init__(self):
        self._store = {}
        self._context_stack = []

    def push_context(self, node_id):
        self._context_stack.append(node_id)

    def pop_context(self):
        if self._context_stack:
            self._context_stack.pop()

    def store(self, key, value):
        nid = self._context_stack[-1] if self._context_stack else "global"
        self._store.setdefault(nid, {})[key] = value

    def get(self, node_id, key=None):
        data = self._store.get(node_id, {})
        return data.get(key) if key else data


def load_dag(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes):
    id_to_node = {n["id"]: n for n in nodes}
    in_degree = {n["id"]: 0 for n in nodes}
    adjacency = defaultdict(list)

    for n in nodes:
        for prereq in n.get("prereqs", []):
            if prereq in id_to_node:
                adjacency[prereq].append(n["id"])
                in_degree[n["id"]] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    ordered = []

    while queue:
        queue.sort()
        nid = queue.pop(0)
        ordered.append(id_to_node[nid])
        for neighbor in adjacency[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) != len(nodes):
        remaining = set(n["id"] for n in nodes) - set(n["id"] for n in ordered)
        print(f"WARNING: Cycle detected or missing prereqs. Orphaned nodes: {remaining}")
        for n in nodes:
            if n["id"] in remaining:
                ordered.append(n)

    return ordered


def execute_chain(node, context, artifact_store):
    chain = node.get("primitive_chain", [])
    chain_results = []
    all_passed = True
    step_outputs = {}

    for i, step in enumerate(chain):
        ptype = step.get("type", step.get("primitive", ""))
        inputs = dict(step.get("inputs", step.get("params", {})))

        for key, val in inputs.items():
            if isinstance(val, str):
                stripped = val.strip()
                if stripped.startswith("{{") and stripped.endswith("}}") and stripped.count("{{") == 1:
                    ref_key = stripped[2:-2]
                    parts = ref_key.split(".")
                    resolved = step_outputs.get(parts[0], context.get(parts[0]))
                    if resolved is not None:
                        for p in parts[1:]:
                            if isinstance(resolved, dict):
                                resolved = resolved.get(p)
                            else:
                                resolved = None
                                break
                        if resolved is not None:
                            inputs[key] = resolved
                            continue
                inputs[key] = _resolve_step_refs(val, step_outputs, context)
            elif isinstance(val, dict):
                inputs[key] = json.loads(_resolve_step_refs(json.dumps(val), step_outputs, context))
            elif isinstance(val, list):
                inputs[key] = json.loads(_resolve_step_refs(json.dumps(val), step_outputs, context))

        result = execute_primitive(ptype, inputs, context)

        step_key = f"step_{i}"
        step_outputs[step_key] = result
        context[step_key] = result

        context[f"{node['id']}.{step_key}"] = result

        chain_results.append({"type": ptype, "passed": result.get("passed", False), "result": result})

        if not result.get("passed", False):
            if ptype not in ["P13"]:
                all_passed = False

    passed_count = sum(1 for r in chain_results if r["passed"])
    return {
        "all_passed": all_passed,
        "chain_results": chain_results,
        "passed_count": passed_count,
        "total_count": len(chain_results),
        "pass_ratio": passed_count / max(len(chain_results), 1)
    }


def score_node(node, chain_result):
    method = node["scoring"].get("method", "binary")
    max_score = node["scoring"].get("maxScore", 1)

    if method == "binary":
        return max_score if chain_result["all_passed"] else 0
    elif method == "weighted":
        return round(chain_result["pass_ratio"] * max_score, 2)
    elif method == "llm_judge":
        for cr in chain_result["chain_results"]:
            if cr["type"] == "P17":
                return min(cr["result"].get("score", 0), max_score)
        return 0
    return 0


def execute_dag(dag, with_llm=True, only_category=None):
    nodes = dag["nodes"]
    if only_category:
        nodes = [n for n in nodes if n["scoring"]["category"] == only_category]

    ordered = topological_sort(nodes)
    context = {}
    _inject_test_user_placeholders(context)
    artifact_store = ArtifactStore()
    results = {}

    print(f"\n{'='*60}")
    print(f"Executing {len(ordered)} nodes")
    print(f"{'='*60}\n")

    try:
        from utils import docker_exec as _dexec
        from config import APP_CONTAINER as _ac
        _dexec(_ac, ["php", "occ", "security:bruteforce:reset", "127.0.0.1"], timeout=30)
        _dexec(_ac, ["php", "/app/occ", "security:bruteforce:reset", "127.0.0.1"], timeout=30)
    except:
        pass

    for node in ordered:
        nid = node["id"]
        category = node["scoring"]["category"]
        max_score = node["scoring"]["maxScore"]
        method = node["scoring"].get("method", "binary")

        prereqs = node.get("prereqs", [])
        prereqs_ok = True
        _passthrough = {"PASSED"}
        for prereq in prereqs:
            if prereq in results:
                if results[prereq].status not in _passthrough:
                    prereqs_ok = False
                    break

        if not prereqs_ok:
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0, maxScore=max_score,
                category=category, subcategory=node["scoring"].get("subcategory", ""),
                message=f"Skipped: prereq {prereq} not passed"
            )
            print_result(results[nid])
            continue

        try:
            artifact_store.push_context(nid)
            chain_result = execute_chain(node, context, artifact_store)

            score = score_node(node, chain_result)
            status = "PASSED" if score > 0 else "FAILED"
            if method == "llm-judge" and any(
                    isinstance(cr.get("result"), dict) and cr["result"].get("skipped")
                    for cr in chain_result["chain_results"]):
                score = 0
                status = "SKIPPED_LLM"
            msg = f"{chain_result['passed_count']}/{chain_result['total_count']} steps passed"
            artifact_store.pop_context()

            evidence = {cr["type"]: cr["result"] for cr in chain_result["chain_results"]}

            results[nid] = NodeResult(
                node_id=nid, status=status, score=score, maxScore=max_score,
                category=category, subcategory=node["scoring"].get("subcategory", ""),
                message=msg,
                evidence=evidence
            )
        except Exception as e:
            results[nid] = NodeResult(
                node_id=nid, status="ERROR", score=0, maxScore=max_score,
                category=category, subcategory=node["scoring"].get("subcategory", ""),
                message=f"Exception: {str(e)}"
            )

        print_result(results[nid])

    return results


def aggregate_results(results, scoring_config):
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}
    categories = defaultdict(lambda: {"total_score": 0, "max_score": 0, "nodes": [], "passed": 0, "failed": 0, "skipped": 0, "errors": 0})
    skipped_llm_max = 0.0

    for nid, result in results.items():
        cat = result.category
        categories[cat]["nodes"].append(result.to_dict())
        if result.status == "PASSED":
            categories[cat]["passed"] += 1
        elif result.status == "FAILED":
            categories[cat]["failed"] += 1
        elif result.status.startswith("SKIPPED"):
            categories[cat]["skipped"] += 1
        else:
            categories[cat]["errors"] += 1
        if result.status in SKIP_FROM_TOTAL:
            skipped_llm_max += result.maxScore
            continue
        categories[cat]["total_score"] += result.score
        categories[cat]["max_score"] += result.maxScore

    total_score = sum(c["total_score"] for c in categories.values())
    total_max = sum(c["max_score"] for c in categories.values())

    report = {
        "summary": {
            "total_score": total_score,
            "total_max": total_max,
            "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
            "percentage": round(total_score / max(total_max, 1) * 100, 1),
            "total_nodes": len(results),
            "passed": sum(c["passed"] for c in categories.values()),
            "failed": sum(c["failed"] for c in categories.values()),
            "skipped": sum(c["skipped"] for c in categories.values()),
            "errors": sum(c["errors"] for c in categories.values()),
        },
        "categories": [
            {
                "category": cat,
                "total_score": data["total_score"],
                "max_score": data["max_score"],
                "percentage": round(data["total_score"] / max(data["max_score"], 1) * 100, 1),
                "passed": data["passed"],
                "failed": data["failed"],
                "skipped": data["skipped"],
                "errors": data["errors"],
            }
            for cat, data in sorted(categories.items())
        ],
        "nodes": [r.to_dict() for r in results.values()]
    }
    return report


def _resolve_step_refs(text, step_outputs, context):
    if not isinstance(text, str):
        return text
    import re

    def replacer(match):
        key = match.group(1)
        parts = key.split(".")
        if parts[0] in step_outputs:
            val = step_outputs[parts[0]]
            for p in parts[1:]:
                if isinstance(val, dict):
                    val = val.get(p, match.group(0))
                else:
                    return match.group(0)
            return str(val) if not isinstance(val, (dict, list)) else json.dumps(val)
        val = context
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p, match.group(0))
            else:
                return match.group(0)
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val) if val != match.group(0) else match.group(0)

    return re.sub(r'\{\{([^}]+)\}\}', replacer, text)
