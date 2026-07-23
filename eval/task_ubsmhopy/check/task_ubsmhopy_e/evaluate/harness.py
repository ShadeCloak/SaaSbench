import json
import sys
import time
from collections import defaultdict
from typing import Any

import config
import primitives
import utils




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
    with open(path) as f:
        return json.load(f)


def topological_sort(nodes: list[dict]) -> list[dict]:
    graph = {n["id"]: n for n in nodes}
    in_degree = defaultdict(int)
    adj = defaultdict(list)
    for n in nodes:
        in_degree.setdefault(n["id"], 0)
        for p in n["prereqs"]:
            adj[p].append(n["id"])
            in_degree[n["id"]] += 1
    queue = [nid for nid in in_degree if in_degree[nid] == 0]
    order = []
    deferred = []
    while queue:
        queue.sort()
        nid = queue.pop(0)
        if graph[nid].get("_run_last"):
            deferred.append(graph[nid])
        else:
            order.append(graph[nid])
        for child in adj[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    order.extend(deferred)
    if len(order) != len(nodes):
        raise ValueError("DAG has cycles!")
    return order


def _auto_store_id(ctx: utils.EvalContext, node_id: str, prim: dict, body: dict):
    entity_id = body.get("id") or body.get("uuid")
    if not entity_id:
        return
    path = prim.get("inputs", {}).get("path", "")
    if "/ciphers" in path and "cipher_id" not in ctx.entity_ids:
        ctx.store_id("cipher_id", str(entity_id))
    elif "/ciphers" in path:
        ctx.store_id("cipher2_id", str(entity_id))
    if "/organizations" in path and "/users" not in path and "/collections" not in path:
        ctx.store_id("org_id", str(entity_id))
        ctx.store_id("org2_id", str(entity_id))
    if "/collections" in path:
        ctx.store_id("collection_id", str(entity_id))
    if "/sends" in path:
        ctx.store_id("send_id", str(entity_id))
        if "accessId" in body:
            ctx.store_id("send_access_id", body["accessId"])
        else:
            ctx.store_send_access_id(str(entity_id))
    if "/folders" in path:
        ctx.store_id("folder_id", str(entity_id))
    if "/users/invite" in path or "/users_organizations" in path:
        ctx.store_id("member_id", str(entity_id))
    if "/emergency-access" in path:
        ctx.store_id("emer_id", str(entity_id))
    if "/groups" in path:
        ctx.store_id("group_id", str(entity_id))
    if "data" in body and isinstance(body["data"], list):
        for item in body["data"]:
            if isinstance(item, dict) and item.get("id"):
                if item.get("type") == 0:
                    ctx.store_id("owner_member_id", str(item["id"]))
                    ctx.store_id("owner_mid", str(item["id"]))


def execute_chain(node: dict, ctx: utils.EvalContext) -> dict:
    chain = node["primitive_chain"]
    chain_results = []
    all_passed = True
    pass_count = 0

    for prim in chain:
        ptype = prim["type"]
        inputs = prim.get("inputs", {})
        func = primitives.PRIMITIVE_MAP.get(ptype)
        if not func:
            chain_results.append({"type": ptype, "passed": False, "error": f"Unknown primitive {ptype}"})
            all_passed = False
            continue

        result = func(inputs, ctx)

        if ptype == "P04" and "response" in result:
            ctx._last_response = result["response"]
            resp = result["response"]
            hdrs = resp.get("headers", {})
            cookie_val = hdrs.get("set-cookie", hdrs.get("Set-Cookie", ""))
            if cookie_val and "/admin" in prim.get("inputs", {}).get("path", ""):
                ctx.entity_ids["admin_cookie"] = cookie_val.split(";")[0]
            if resp.get("status_code") in [200, 201] and isinstance(resp.get("body"), dict):
                body = resp["body"]
                if "id" in body:
                    ctx.store_id("_last_id", str(body["id"]))
                    _auto_store_id(ctx, node["id"], prim, body)
                if "accessId" in body:
                    ctx.store_id("_last_access_id", str(body["accessId"]))

        if ptype == "P13":
            if result.get("passed"):
                pass_count += 1
            else:
                all_passed = False
            chain_results.append({"type": ptype, **result})
            continue

        passed = result.get("passed", False)
        if passed:
            pass_count += 1
        else:
            all_passed = False
        chain_results.append({"type": ptype, **result})

    return {
        "all_passed": all_passed,
        "pass_ratio": pass_count / len(chain) if chain else 0,
        "chain_results": chain_results,
    }


def score_node(node: dict, chain_result: dict) -> float:
    method = node["scoring"]["method"]
    max_score = node["scoring"]["maxScore"]

    if method == "binary":
        return max_score if chain_result["all_passed"] else 0
    elif method == "weighted":
        return round(chain_result["pass_ratio"] * max_score, 2)
    elif method == "llm-judge":
        for cr in chain_result["chain_results"]:
            if cr.get("type") == "P17":
                return min(cr.get("score", 0), max_score)
        return 0
    return 0


def llm_judge_skipped_info(chain_result: dict) -> dict | None:
    for cr in chain_result.get("chain_results", []):
        if cr.get("type") == "P17" and cr.get("skipped"):
            return {
                "llm_api_failure": cr.get("llm_api_failure", False),
                "exception_class": cr.get("exception_class", ""),
                "reason": cr.get("reason", ""),
            }
    return None


def aggregate(results: dict[str, utils.NodeResult], scoring_config: dict) -> dict:
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}
    categories = {}
    for nid, nr in results.items():
        cat = nr.evidence.get("category", "Unknown")
        if cat not in categories:
            categories[cat] = {"total_score": 0, "max_score": 0, "nodes": []}
        categories[cat]["nodes"].append({
            "id": nid, "status": nr.status, "score": nr.score,
            "max_score": nr.max_score, "message": nr.message
        })
        if nr.status in SKIP_FROM_TOTAL:
            continue
        categories[cat]["total_score"] += nr.score
        categories[cat]["max_score"] += nr.max_score

    total_score = sum(nr.score for nr in results.values() if nr.status not in SKIP_FROM_TOTAL)
    total_max = sum(nr.max_score for nr in results.values() if nr.status not in SKIP_FROM_TOTAL)
    skipped_llm_max = sum(nr.max_score for nr in results.values() if nr.status in SKIP_FROM_TOTAL)
    percentage = (total_score / total_max * 100) if total_max > 0 else 0

    return {
        "total_score": total_score,
        "total_max_score": total_max,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "percentage": round(percentage, 1),
        "categories": [
            {"category": cat, **data} for cat, data in sorted(categories.items())
        ],
        "node_results": {nid: {"status": nr.status, "score": nr.score, "max_score": nr.max_score, "message": nr.message,
                                "evidence": getattr(nr, "evidence", None)}
                         for nid, nr in results.items()},
    }


def run_dag(dag_path: str, output_path: str = None):
    dag = load_dag(dag_path)
    scoring_config = dag.get("scoring_config", {})
    nodes = dag["nodes"]
    ordered = topological_sort(nodes)

    ctx = utils.EvalContext()
    results: dict[str, utils.NodeResult] = {}

    print(f"Running {len(ordered)} nodes...")
    start = time.time()

    for i, node in enumerate(ordered):
        nid = node["id"]
        max_score = node["scoring"]["maxScore"]
        cat = node["scoring"]["category"]

        prereqs_ok = all(
            results.get(p, utils.NodeResult(p, "MISSING", 0, 0)).status in ["PASSED", "EXECUTED"]
            for p in node["prereqs"]
        )
        if not prereqs_ok:
            results[nid] = utils.NodeResult(nid, "SKIPPED_DEPENDENCY", 0, max_score,
                                             evidence={"category": cat}, message="Prerequisite failed")
            print(f"  [{i+1}/{len(ordered)}] {nid}: SKIPPED (dependency)")
            continue

        try:
            chain_result = execute_chain(node, ctx)
            method = node["scoring"]["method"]
            llm_skipped = llm_judge_skipped_info(chain_result) if method == "llm-judge" else None
            if llm_skipped is not None:
                score = 0
                status = "SKIPPED_LLM"
            else:
                score = score_node(node, chain_result)
                status = "PASSED" if chain_result["all_passed"] else "FAILED"
            safe_chain = []
            for cr in chain_result.get("chain_results", []):
                sc = dict(cr)
                if "response" in sc and isinstance(sc["response"], dict):
                    sc["response"] = {
                        "status_code": sc["response"].get("status_code"),
                        "body_preview": str(sc["response"].get("body", ""))[:200]
                    }
                safe_chain.append(sc)
            evidence_dict = {"category": cat, "chain": safe_chain}
            if llm_skipped:
                evidence_dict["llm_judge_skipped"] = True
                evidence_dict.update(llm_skipped)
            fail_info = ""
            if status == "FAILED":
                for cr in chain_result.get("chain_results", []):
                    if not cr.get("passed", True):
                        t = cr.get("type", "?")
                        err = cr.get("error") or cr.get("message") or ""
                        fail_info += f"{t}: {err}\n"
            elif status == "SKIPPED_LLM":
                fail_info = f"LLM judge skipped: {llm_skipped.get('reason', '')}"
            results[nid] = utils.NodeResult(
                nid, status, score, max_score,
                evidence=evidence_dict,
                message=fail_info.strip() if fail_info else ""
            )
            symbol = "✅" if status == "PASSED" else ("⊘" if status == "SKIPPED_LLM" else "❌")
            fail_info = ""
            if status == "SKIPPED_LLM" and llm_skipped:
                fail_info = f" [LLM skipped: {llm_skipped.get('reason', '')[:60]}]"
            elif status == "FAILED":
                for cr in chain_result.get("chain_results", []):
                    if not cr.get("passed", True):
                        t = cr.get("type", "?")
                        if t == "P04":
                            r = cr.get("response", {})
                            fail_info = f" [P04 HTTP {r.get('status_code',0)}: {str(r.get('body',''))[:80]}]"
                        elif t == "P07":
                            for a in cr.get("results", []):
                                if not a.get("passed"):
                                    fail_info = f" [P07 {a.get('path')}: expected={a.get('expected')}, got={a.get('actual')}]"
                                    break
                        elif t == "P08":
                            fail_info = f" [P08 rows={cr.get('rows',[])}]"
                        elif t == "P15":
                            fail_info = f" [P15 got={cr.get('actual_status')}, want={cr.get('expected')}]"
                        elif t == "P29":
                            fail_info = f" [P29 {cr.get('steps_passed')}/{cr.get('steps_total')} steps]"
                        else:
                            fail_info = f" [{t}]"
                        break
            print(f"  [{i+1}/{len(ordered)}] {nid}: {symbol} {score}/{max_score}{fail_info}")
        except Exception as e:
            results[nid] = utils.NodeResult(nid, "ERROR", 0, max_score,
                                             evidence={"category": cat}, message=str(e))
            print(f"  [{i+1}/{len(ordered)}] {nid}: 💥 ERROR: {e}")

    elapsed = time.time() - start
    report = aggregate(results, scoring_config)
    report["elapsed_seconds"] = round(elapsed, 1)

    print(f"\n{'='*60}")
    print(f"Total: {report['total_score']}/{report['total_max_score']} ({report['percentage']}%)")
    print(f"Time: {elapsed:.1f}s")
    for cat in report["categories"]:
        print(f"  {cat['category']}: {cat['total_score']}/{cat['max_score']}")
    print(f"{'='*60}")

    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        print(f"Report saved to {output_path}")

    return report
