import json
import sys
import traceback
from collections import defaultdict
from typing import Any

import primitives
import config
from utils import NodeResult




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
    with open(path, encoding='utf-8', errors='replace') as f:
        return json.load(f)


def load_scoring_config(path: str) -> dict:
    with open(path, encoding='utf-8', errors='replace') as f:
        return json.load(f)


def topological_sort(nodes, context=None):
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
        remaining = [n["id"] for n in nodes if n["id"] not in {o["id"] for o in ordered}]
        print(f"WARNING: {len(remaining)} nodes not reachable (possible cycle): {remaining[:10]}")
        for nid in remaining:
            ordered.append(id_to_node[nid])

    return ordered


def execute_dag(dag, scoring_config, context=None, with_llm=False, only_category=None):
    if context is None:
        context = {}
    try:
        import config as _cfg
        for role, info in (_cfg.TEST_USERS or {}).items():
            for field, val in info.items():
                k = f"{role}_{field}"
                if k not in context:
                    context[k] = val
    except Exception:
        pass
    results = {}
    nodes = topological_sort(dag["nodes"])

    for node in nodes:
        nid = node["id"]
        scoring = node["scoring"]
        cat = scoring["category"]
        subcat = scoring.get("subcategory", "")
        method = scoring["method"]
        max_score = scoring["maxScore"]

        if only_category and cat != only_category:
            continue

        try:
            chain_results = execute_chain(node["primitive_chain"], context, with_llm)
            score = compute_score(chain_results, method, max_score)
            status = "PASSED" if score > 0 else "FAILED"
            if method == "llm-judge" and any(
                isinstance(r, dict) and r.get("skipped") for r in chain_results
            ):
                score = 0
                status = "SKIPPED_LLM"
            msg = summarize_chain(chain_results)
            evidence = {"chain_results": chain_results}

            _extract_entity_ids(chain_results, context, nid)

            results[nid] = NodeResult(nid, status, score, max_score, cat, subcat, msg, evidence)
        except Exception as e:
            results[nid] = NodeResult(nid, "ERROR", 0, max_score, cat, subcat, f"Exception: {e}")
            traceback.print_exc()

    return results


def all_prereqs_passed(prereqs, results):
    for p in prereqs:
        r = results.get(p)
        if r is None or r.status not in ("PASSED",):
            return False
    return True


def execute_chain(chain, context, with_llm=False):
    chain_results = []
    prev_result = None

    def _resolve_placeholders(obj, ctx):
        import re
        if isinstance(obj, str):
            def _sub(m):
                key = m.group(1).strip()
                v = ctx.get(key)
                return str(v) if v is not None else m.group(0)
            return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_\.]*)\s*\}\}", _sub, obj)
        if isinstance(obj, dict):
            return {k: _resolve_placeholders(v, ctx) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_resolve_placeholders(x, ctx) for x in obj]
        return obj

    for step in chain:
        ptype = step["type"]
        inputs = step.get("inputs", {})
        inputs = _resolve_placeholders(inputs, context or {})

        func_map = {
            "P01": lambda i: primitives.p01_file_exists(i),
            "P02": lambda i: primitives.p02_file_content_match(i),
            "P03": lambda i: primitives.p03_file_count(i),
            "P04": lambda i: primitives.p04_http_request(i, context),
            "P05": lambda i: primitives.p05_api_crud(i, context),
            "P06": lambda i: primitives.p06_json_schema_match(i, prev_result),
            "P07": lambda i: primitives.p07_json_value_assert(i, prev_result),
            "P08": lambda i: primitives.p08_db_query(i),
            "P09": lambda i: primitives.p09_db_table_exists(i),
            "P10": lambda i: primitives.p10_db_column_check(i),
            "P11": lambda i: primitives.p11_db_index_check(i),
            "P12": lambda i: primitives.p12_docker_exec(i, context),
            "P13": lambda i: primitives.p13_auth_login(i, context),
            "P14": lambda i: primitives.p14_permission_check(i, context),
            "P15": lambda i: primitives.p15_status_code_assert(i, prev_result),
            "P16": lambda i: primitives.p16_response_time_check(i, prev_result),
            "P17": lambda i: primitives.p17_llm_judge(i, prev_result, context),
        }
        try:
            from _browser_primitives import (
                p18_render_dom as _shared_render_dom,
                p19_screenshot as _shared_screenshot,
            )
            func_map.setdefault("RENDER_DOM", lambda i: _shared_render_dom(i, context))
            func_map.setdefault("SCREENSHOT", lambda i: _shared_screenshot(i, context))
        except Exception:
            pass

        func = func_map.get(ptype)
        if func is None:
            chain_results.append({"type": ptype, "passed": False, "error": f"Unknown primitive {ptype}"})
            continue

        result = func(inputs)
        result["type"] = ptype
        chain_results.append(result)

        if ptype in ("P04", "P05", "P08", "P09", "P10", "P11", "P12", "P13"):
            prev_result = result

    return chain_results


def compute_score(chain_results, method, max_score):
    if not chain_results:
        return 0

    if method == "binary":
        return max_score if all(r.get("passed", False) for r in chain_results) else 0

    elif method == "weighted":
        PLUMBING = {"P04", "P13"}
        scored = [r for r in chain_results if r.get("type") not in PLUMBING]
        if not scored:
            scored = chain_results
        ratios = []
        for r in scored:
            if "ratio" in r:
                ratios.append(r["ratio"])
            elif r.get("passed"):
                ratios.append(1.0)
            else:
                ratios.append(0.0)
        avg = sum(ratios) / len(ratios) if ratios else 0
        return round(avg * max_score, 2)

    elif method == "llm-judge":
        for r in chain_results:
            if r.get("type") == "P17":
                llm_score = r.get("score", 0)
                llm_max = r.get("max_score", max_score)
                return round((llm_score / llm_max) * max_score, 2) if llm_max > 0 else 0
        return 0

    return 0


def summarize_chain(chain_results):
    parts = []
    for r in chain_results:
        status = "OK" if r.get("passed") else "FAIL"
        ptype = r.get("type", "?")
        extra = ""
        if "status_code" in r:
            extra = f" (HTTP {r['status_code']})"
        elif "count" in r:
            extra = f" (count={r['count']})"
        elif "error" in r:
            extra = f" ({r['error'][:60]})"
        parts.append(f"{ptype}:{status}{extra}")
    return " → ".join(parts)


def _extract_entity_ids(chain_results, context, node_id):
    for r in chain_results:
        body = r.get("body")
        if isinstance(body, dict) and "id" in body:
            eid = body["id"]
            if "customer" in node_id.lower() and "cid" not in context:
                context["cid"] = eid
                context["customer_id"] = eid
            elif "project" in node_id.lower() and "pid" not in context:
                context["pid"] = eid
                context["project_id"] = eid
            elif "activit" in node_id.lower() and "aid" not in context:
                context["aid"] = eid
                context["activity_id"] = eid
            elif "timesheet" in node_id.lower() and "ts_id" not in context:
                context["ts_id"] = eid
                context["timesheet_id"] = eid
            elif "team" in node_id.lower() and "tid" not in context:
                context["tid"] = eid
                context["team_id"] = eid
            elif "user" in node_id.lower() and "USERS_CREATE" in node_id and "uid" not in context:
                context["uid"] = eid
                context["user_id"] = eid
        if r.get("type") == "P13" and "token" in r:
            context["auth_token"] = r["token"]


def aggregate_results(results, scoring_config):
    cat_scores = defaultdict(lambda: {"score": 0, "maxScore": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0, "skipped_llm": 0})
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}
    skipped_llm_max = 0.0

    for nid, nr in results.items():
        cat = nr.category
        if nr.status in SKIP_FROM_TOTAL:
            skipped_llm_max += nr.maxScore
            cat_scores[cat]["skipped_llm"] += 1
            continue
        cat_scores[cat]["score"] += nr.score
        cat_scores[cat]["maxScore"] += nr.maxScore
        if nr.status == "PASSED":
            cat_scores[cat]["passed"] += 1
        elif nr.status == "FAILED":
            cat_scores[cat]["failed"] += 1
        elif nr.status == "SKIPPED_DEPENDENCY":
            cat_scores[cat]["skipped"] += 1
        elif nr.status == "ERROR":
            cat_scores[cat]["error"] += 1

    categories = []
    total_score = 0
    total_max = 0
    for cat in sorted(cat_scores.keys()):
        d = cat_scores[cat]
        categories.append({"category": cat, "score": round(d["score"], 2), "maxScore": d["maxScore"],
                           "passed": d["passed"], "failed": d["failed"], "skipped": d["skipped"],
                           "skipped_llm": d["skipped_llm"], "error": d["error"]})
        total_score += d["score"]
        total_max += d["maxScore"]

    percentage = (total_score / total_max * 100) if total_max > 0 else 0

    return {
        "task_id": scoring_config.get("task_id", "timetracker"),
        "total_score": round(total_score, 2),
        "total_maxScore": total_max,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "percentage": round(percentage, 1),
        "categories": categories,
        "node_results": {nid: nr.to_dict() for nid, nr in results.items()},
    }
