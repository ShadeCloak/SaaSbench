import json
import os
import re
import time
from collections import defaultdict

from utils import NodeResult, print_result
from primitives import execute_primitive, context as prim_context




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
    with open(path, "r") as f:
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

    def _topo_key(nid):
        if "SUPER_ADMIN_CREATE" in nid:
            return (0, nid)
        if nid.startswith("DEPLOY_"):
            return (1, nid)
        return (2, nid)

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    result = []
    while queue:
        queue.sort(key=_topo_key)
        nid = queue.pop(0)
        result.append(id_to_node[nid])
        for child in adj[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(result) != len(nodes):
        remaining = set(id_to_node.keys()) - {n["id"] for n in result}
        print(f"WARNING: Cycle detected, unreachable nodes: {remaining}")
        for nid in remaining:
            result.append(id_to_node[nid])

    return result


def _store_dual(key_snake, key_camel, value):
    prim_context[key_snake] = value
    prim_context[key_camel] = value


def _extract_entity_ids(node_id, chain_result):
    resp = prim_context.get("last_response", {})
    resp_body = resp.get("body") if isinstance(resp, dict) else None

    created_id = None

    if isinstance(resp_body, dict):
        data = resp_body.get("data", resp_body)
        if isinstance(data, dict) and "id" in data:
            created_id = data["id"]
        elif "id" in resp_body:
            created_id = resp_body["id"]
    elif isinstance(resp_body, (int, float)):
        created_id = int(resp_body)

    if created_id is None:
        return

    nid_lower = node_id.lower()

    if "workspace" in nid_lower and not nid_lower.startswith("rbac_"):
        _store_dual("workspace_id", "workspaceId", created_id)
        _store_dual("ws_id", "wsId", created_id)
    if "application" in nid_lower or "app_" in nid_lower:
        _store_dual("app_id", "appId", created_id)
        _store_dual("application_id", "applicationId", created_id)
    if "page" in nid_lower and "default" not in nid_lower:
        _store_dual("page_id", "pageId", created_id)
    if "action" in nid_lower and "collection" not in nid_lower:
        _store_dual("action_id", "actionId", created_id)
    if "action_collection" in nid_lower or "actioncollection" in nid_lower:
        _store_dual("action_collection_id", "collId", created_id)
    if "datasource" in nid_lower:
        _store_dual("datasource_id", "datasourceId", created_id)
        _store_dual("ds_id", "dsId", created_id)
    if "theme" in nid_lower:
        _store_dual("theme_id", "themeId", created_id)
        prim_context["systemThemeId"] = created_id
    if "user" in nid_lower and "rbac" not in nid_lower:
        _store_dual("test_user_id", "testUserId", created_id)
    if "git" in nid_lower and "connect" in nid_lower:
        _store_dual("git_repo_id", "gitRepoId", created_id)
    if "branch" in nid_lower:
        _store_dual("branch_name", "branchName", created_id)
    if "layout" in nid_lower:
        _store_dual("layout_id", "layoutId", created_id)
    if "plugin" in nid_lower:
        _store_dual("plugin_id", "pluginId", created_id)
        prim_context["mongoPluginId"] = created_id
    if "organization" in nid_lower or "org_" in nid_lower:
        _store_dual("org_id", "orgId", created_id)
    if "invite" in nid_lower:
        _store_dual("invite_id", "inviteId", created_id)
    if "clone" in nid_lower:
        _store_dual("cloned_id", "clonedId", created_id)
    if "src" in nid_lower:
        _store_dual("src_id", "srcId", created_id)
        _store_dual("src_app_id", "srcAppId", created_id)

    _store_dual("last_id", "_last_id", created_id)
    prim_context["last_created_id"] = created_id


def execute_chain(node, results):
    chain = node.get("primitive_chain", [])
    chain_results = []
    all_passed = True
    last_result = None

    for step in chain:
        ptype = step["type"]
        inputs = step.get("inputs", {})
        try:
            result = execute_primitive(ptype, inputs)
            cr_entry = {"type": ptype, "passed": result.passed, "message": result.message}
            if ptype == "P17" and result.data:
                cr_entry["data"] = result.data
            if not result.passed and result.data and ptype in (
                "P07", "P15", "P14", "P05", "P08", "P10", "P11", "P04"
            ):
                cr_entry["data"] = result.data
            chain_results.append(cr_entry)
            if not result.passed:
                all_passed = False
            last_result = result

            if ptype in ("P04", "P05") and result.passed:
                _extract_entity_ids(node["id"], result)

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


def execute_dag(dag, scoring_config=None, only_category=None, dry_run=False):
    nodes = dag.get("nodes", [])
    ordered = topological_sort(nodes)
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
            chain = execute_chain(node, results)

            llm_skipped = False
            llm_skip_msg = ""
            if method == "llm-judge":
                for cr in chain["chain_results"]:
                    if cr.get("type") == "P17" and isinstance(cr.get("data"), dict) and cr["data"].get("skipped"):
                        llm_skipped = True
                        llm_skip_msg = cr.get("message", "")
                        break

            if llm_skipped:
                results[nid] = NodeResult(
                    node_id=nid, status="SKIPPED_LLM", score=0,
                    max_score=max_score, category=category, subcategory=subcategory,
                    message=llm_skip_msg or "LLM judge SKIPPED", evidence=chain
                )
            else:
                if method == "binary":
                    score = max_score if chain["all_passed"] else 0
                elif method == "weighted":
                    score = round(chain["pass_ratio"] * max_score, 2)
                elif method == "llm-judge":
                    score = 0
                    for cr in chain["chain_results"]:
                        if cr.get("type") == "P17" and isinstance(cr.get("data"), dict):
                            score = min(cr["data"].get("score", 0), max_score)
                            break
                    if score == 0:
                        judge_data = prim_context.get("last_response", {})
                        if isinstance(judge_data, dict) and "score" in judge_data:
                            score = min(judge_data["score"], max_score)
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
    tier_scores = defaultdict(lambda: {"score": 0, "max_score": 0, "nodes": 0})
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
            if r.status == "SKIPPED_LLM":
                skipped_llm_max += r.max_score
        if r.status == "PASSED":
            cat_scores[r.category]["passed"] += 1
        statuses[r.status] += 1

    normalized = round(total_score / total_max * 100, 2) if total_max > 0 else 0

    nodes_dump = []
    for nid, r in results.items():
        nodes_dump.append({
            "node_id": nid,
            "status": r.status,
            "score": r.score,
            "max_score": r.max_score,
            "category": r.category,
            "subcategory": getattr(r, "subcategory", ""),
            "method": getattr(r, "method", ""),
            "message": getattr(r, "message", "") or "",
            "evidence": getattr(r, "evidence", None),
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
        "nodes": nodes_dump,
    }

    if scoring_config and "trajectories" in scoring_config:
        trajectories = {}
        for tname, tdata in scoring_config["trajectories"].items():
            node_ids = [nid for nid in tdata["node_ids"] if nid in results]
            t_score = sum(results[nid].score for nid in node_ids if results[nid].status not in SKIP_FROM_TOTAL)
            t_max = sum(results[nid].max_score for nid in node_ids if results[nid].status not in SKIP_FROM_TOTAL)
            trajectories[tname] = {
                "score": t_score, "max_score": t_max,
                "rate": round(t_score / t_max * 100, 2) if t_max > 0 else 0,
                "description": tdata.get("description", "")
            }
        report["trajectories"] = trajectories

    return report
