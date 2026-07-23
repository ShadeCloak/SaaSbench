import importlib
import json
import os
import re
import sys
import time
from collections import defaultdict

from utils import NodeResult, print_result
from primitives import execute_primitive, context as prim_context
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

def _discover_test_functions():
    registry = {}
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    if not os.path.isdir(tests_dir):
        return registry
    if tests_dir not in sys.path:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for fname in sorted(os.listdir(tests_dir)):
        if fname.startswith("test_") and fname.endswith(".py"):
            mod_name = f"tests.{fname[:-3]}"
            try:
                mod = importlib.import_module(mod_name)
                nodes_dict = getattr(mod, "NODES", {})
                for node_id, fn in nodes_dict.items():
                    registry[node_id] = fn
            except Exception as e:
                print(f"  WARNING: Failed to import {mod_name}: {e}")
    return registry


def load_dag(path):
    with open(path, "r", encoding="utf-8") as f:
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

    queue = sorted([nid for nid, deg in in_degree.items() if deg == 0])
    result = []
    while queue:
        nid = queue.pop(0)
        result.append(id_to_node[nid])
        for child in sorted(adj[nid]):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
        queue.sort()

    if len(result) != len(nodes):
        remaining = set(id_to_node.keys()) - {n["id"] for n in result}
        print(f"WARNING: Cycle detected, unreachable nodes: {remaining}")
        for nid in sorted(remaining):
            result.append(id_to_node[nid])

    return result


def _extract_entity_ids(node_id, chain_result):
    resp = prim_context.get("last_response", {})
    resp_body = resp.get("body") if isinstance(resp, dict) else None

    created_id = None
    if isinstance(resp_body, dict):
        for wrapper in ("customer", "plan", "subscription", "invoice", "wallet",
                        "coupon", "add_on", "billable_metric", "tax", "credit_note",
                        "webhook_endpoint", "wallet_transaction", "applied_coupon",
                        "dunning_campaign", "fee"):
            nested = resp_body.get(wrapper)
            if isinstance(nested, dict):
                created_id = nested.get("id") or nested.get("external_id") or nested.get("lago_id") or nested.get("code")
                break
        if created_id is None:
            created_id = resp_body.get("id") or resp_body.get("external_id") or resp_body.get("lago_id")
        if created_id is None and "data" in resp_body:
            gql_data = resp_body.get("data", {})
            if isinstance(gql_data, dict):
                for mutation_key, mutation_val in gql_data.items():
                    if isinstance(mutation_val, dict) and mutation_val.get("id"):
                        created_id = mutation_val["id"]
                        break
    elif isinstance(resp_body, (int, float)):
        created_id = int(resp_body)

    if isinstance(chain_result, dict) and chain_result.get("data"):
        data = chain_result["data"]
        if isinstance(data, dict) and "entity_id" in data and created_id is None:
            created_id = data["entity_id"]

    if created_id is None:
        return

    nid_lower = node_id.lower()
    if "customer" in nid_lower:
        prim_context["customer_id"] = created_id
        prim_context["cid"] = created_id
    if "plan" in nid_lower and "billing" not in nid_lower:
        prim_context["plan_id"] = created_id
        prim_context["plan_code"] = created_id
    if "subscription" in nid_lower or "sub_" in nid_lower:
        prim_context["subscription_id"] = created_id
        prim_context["sub_id"] = created_id
    if "invoice" in nid_lower:
        prim_context["invoice_id"] = created_id
        prim_context["inv_id"] = created_id
    if "wallet" in nid_lower and "transaction" not in nid_lower:
        prim_context["wallet_id"] = created_id
    if "coupon" in nid_lower:
        prim_context["coupon_id"] = created_id
        prim_context["coupon_code"] = created_id
    if "add_on" in nid_lower or "addon" in nid_lower:
        prim_context["addon_id"] = created_id
    if "metric" in nid_lower or "billable" in nid_lower:
        prim_context["metric_id"] = created_id
        prim_context["metric_code"] = created_id
    if "tax" in nid_lower:
        prim_context["tax_id"] = created_id
        prim_context["tax_code"] = created_id
    if "credit_note" in nid_lower:
        prim_context["credit_note_id"] = created_id
    if "webhook" in nid_lower:
        prim_context["webhook_id"] = created_id
    if "dunning" in nid_lower:
        prim_context["dunning_id"] = created_id
    if "event" in nid_lower:
        prim_context["event_id"] = created_id

    prim_context["last_id"] = created_id
    prim_context["last_created_id"] = created_id


def _process_save_id(step, ptype, result):
    save_key = step.get("inputs", {}).get("save_id")
    if not save_key:
        return
    if ptype in ("P04", "P05"):
        cid = prim_context.get("last_created_id")
        if cid is not None:
            prim_context[save_key] = cid
    elif ptype == "P08" and result.data:
        rows = result.data.get("rows", [])
        if rows:
            first_val = list(rows[0].values())[0] if rows[0] else None
            if first_val is not None:
                prim_context[save_key] = first_val
    elif ptype == "P12" and result.data:
        stdout = result.data.get("stdout", "").strip()
        if stdout:
            prim_context[save_key] = stdout


def execute_chain(node, results, test_fn=None):
    if test_fn is not None:
        old_last_id = prim_context.get("last_created_id")
        try:
            node_result = test_fn()
            new_last_id = prim_context.get("last_created_id")
            if new_last_id is not None and new_last_id != old_last_id:
                from utils import PrimitiveResult
                _extract_entity_ids(node["id"], {"data": {"entity_id": new_last_id}})
            return {
                "all_passed": node_result.status == "PASSED",
                "pass_ratio": node_result.score / node_result.max_score if node_result.max_score > 0 else 0,
                "chain_results": [{"type": "test_fn", "passed": node_result.status in ("PASSED", "PARTIAL"), "message": node_result.message}],
                "pass_count": 1 if node_result.status == "PASSED" else 0,
                "total": 1,
                "node_result": node_result,
            }
        except Exception as e:
            return {
                "all_passed": False, "pass_ratio": 0,
                "chain_results": [{"type": "test_fn", "passed": False, "message": str(e)}],
                "pass_count": 0, "total": 1,
            }

    chain = node.get("primitive_chain", [])
    chain_results = []
    all_passed = True

    for step in chain:
        ptype = step.get("type", "")
        inputs = step.get("inputs", {})
        try:
            result = execute_primitive(ptype, inputs)
            cr_entry = {"type": ptype, "passed": result.passed, "message": result.message}
            if ptype == "P17" and result.data:
                cr_entry["data"] = result.data
            chain_results.append(cr_entry)
            if not result.passed:
                all_passed = False

            if ptype in ("P04", "P05") and result.passed:
                _extract_entity_ids(node["id"], {"data": result.data})

            _process_save_id(step, ptype, result)

        except Exception as e:
            chain_results.append({"type": ptype, "passed": False, "message": str(e)})
            all_passed = False

    pass_count = sum(1 for r in chain_results if r["passed"])
    total = len(chain_results)
    pass_ratio = pass_count / total if total > 0 else 0

    return {
        "all_passed": all_passed,
        "pass_ratio": pass_ratio,
        "chain_results": chain_results,
        "pass_count": pass_count,
        "total": total,
    }


def execute_dag(dag, scoring_config=None, only_category=None, dry_run=False, use_test_fns=True):
    test_functions = _discover_test_functions() if use_test_fns else {}
    if test_functions:
        print(f"  Loaded {len(test_functions)} test functions from tests/ modules")

    nodes = dag.get("nodes", [])
    ordered = topological_sort(nodes)
    _inject_test_user_placeholders(prim_context)
    results = {}

    print(f"\n{'='*60}")
    print(f"  DAG Evaluation: {len(ordered)} nodes")
    print(f"{'='*60}\n")

    for node in ordered:
        nid = node["id"]
        scoring = node["scoring"]
        category = scoring["category"]
        subcategory = scoring.get("subcategory", "")
        method = scoring["method"]
        max_score = scoring["maxScore"]

        if only_category and category != only_category:
            continue

        prereqs = node.get("prereqs", [])
        prereqs_ok = True
        for p in prereqs:
            if p in results and results[p].status not in ("PASSED", "PARTIAL"):
                prereqs_ok = False
                break
            if p not in results and p in {n["id"] for n in nodes}:
                prereqs_ok = False
                break

        if not prereqs_ok:
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0,
                max_score=max_score, category=category, subcategory=subcategory,
                message=f"Prereqs not met: {prereqs}"
            )
            print_result(results[nid])
            continue


        if dry_run:
            results[nid] = NodeResult(
                node_id=nid, status="DRY_RUN", score=0,
                max_score=max_score, category=category, subcategory=subcategory
            )
            continue

        try:
            test_fn = test_functions.get(nid) if use_test_fns else None
            chain = execute_chain(node, results, test_fn=test_fn)

            if "node_result" in chain:
                results[nid] = chain["node_result"]
            else:
                llm_skipped = False
                if method in ("llm-judge", "llm_judge"):
                    for cr in chain["chain_results"]:
                        if cr.get("type") == "P17" and isinstance(cr.get("data"), dict) and cr["data"].get("skipped"):
                            llm_skipped = True
                            break

                if llm_skipped:
                    score = 0
                    status = "SKIPPED_LLM"
                    msg = f"LLM judge SKIPPED ({chain['chain_results'][-1].get('message', '')})"
                else:
                    if method == "binary":
                        score = max_score if chain["all_passed"] else 0
                    elif method == "weighted":
                        score = round(chain["pass_ratio"] * max_score, 2)
                    elif method in ("llm-judge", "llm_judge"):
                        score = 0
                        for cr in chain["chain_results"]:
                            if cr.get("type") == "P17" and isinstance(cr.get("data"), dict):
                                score = min(cr["data"].get("score", 0), max_score)
                                break
                        if score == 0:
                            lr = prim_context.get("last_response", {})
                            if isinstance(lr, dict) and isinstance(lr.get("body"), str):
                                try:
                                    sd = json.loads(lr["body"])
                                    score = min(sd.get("score", 0), max_score)
                                except Exception:
                                    pass
                            elif isinstance(lr, dict) and isinstance(lr.get("body"), dict):
                                score = min(lr["body"].get("score", 0), max_score)
                    else:
                        score = max_score if chain["all_passed"] else 0

                    status = "PASSED" if score == max_score else ("PARTIAL" if score > 0 else "FAILED")
                    msg = f"{chain['pass_count']}/{chain['total']} primitives"

                results[nid] = NodeResult(
                    node_id=nid, status=status, score=score,
                    max_score=max_score, category=category, subcategory=subcategory,
                    message=msg, evidence=chain
                )

        except Exception as e:
            results[nid] = NodeResult(
                node_id=nid, status="ERROR", score=0,
                max_score=max_score, category=category, subcategory=subcategory,
                message=str(e)
            )

        print_result(results[nid])

    return results


SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate_results(results, scoring_config):
    cat_scores = defaultdict(lambda: {"score": 0, "max_score": 0, "nodes": 0, "passed": 0, "skipped_llm": 0})
    total_score = 0
    total_max = 0
    skipped_llm_max = 0.0
    statuses = defaultdict(int)

    for nid, r in results.items():
        in_skip = r.status in SKIP_FROM_TOTAL
        cat_scores[r.category]["nodes"] += 1
        if not in_skip:
            cat_scores[r.category]["score"] += r.score
            cat_scores[r.category]["max_score"] += r.max_score
            total_score += r.score
            total_max += r.max_score
        else:
            cat_scores[r.category]["skipped_llm"] += 1
            skipped_llm_max += r.max_score
        if r.status == "PASSED":
            cat_scores[r.category]["passed"] += 1
        statuses[r.status] += 1

    normalized = round(total_score / total_max * 100, 2) if total_max > 0 else 0

    node_results_list = []
    for nid, r in results.items():
        node_results_list.append({
            "node_id": nid,
            "status": r.status,
            "score": r.score,
            "max_score": r.max_score,
            "category": r.category,
            "subcategory": getattr(r, "subcategory", ""),
            "message": getattr(r, "message", ""),
            "evidence": getattr(r, "evidence", {}) or {},
        })

    report = {
        "summary": {
            "total_score": total_score,
            "total_max_score": total_max,
            "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
            "normalized_score": normalized,
            "total_nodes": len(results),
            "status_counts": dict(statuses),
        },
        "categories": {k: dict(v) for k, v in sorted(cat_scores.items())},
        "node_results": node_results_list,
    }

    if scoring_config and "trajectories" in scoring_config:
        trajectories = {}
        for tname, tdata in scoring_config["trajectories"].items():
            node_ids = [nid for nid in tdata.get("node_ids", []) if nid in results]
            t_score = sum(results[nid].score for nid in node_ids if results[nid].status not in SKIP_FROM_TOTAL)
            t_max = sum(results[nid].max_score for nid in node_ids if results[nid].status not in SKIP_FROM_TOTAL)
            trajectories[tname] = {
                "score": t_score, "max_score": t_max,
                "rate": round(t_score / t_max * 100, 2) if t_max > 0 else 0,
                "description": tdata.get("description", "")
            }
        report["trajectories"] = trajectories

    return report
