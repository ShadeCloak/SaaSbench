import json
import traceback
from collections import defaultdict

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

def load_dag(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def load_scoring_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes):
    graph = {n["id"]: set(n.get("prereqs", [])) for n in nodes}
    node_map = {n["id"]: n for n in nodes}
    ordered = []
    visited = set()
    temp = set()

    def visit(nid):
        if nid in temp:
            raise ValueError(f"Cycle detected involving {nid}")
        if nid in visited:
            return
        temp.add(nid)
        for dep in graph.get(nid, []):
            visit(dep)
        temp.remove(nid)
        visited.add(nid)
        ordered.append(nid)

    for nid in graph:
        visit(nid)

    return [node_map[nid] for nid in ordered if nid in node_map]


def execute_dag(dag, scoring_config):
    import primitives as P

    nodes = topological_sort(dag["nodes"])
    results = {}
    context = {}
    artifact_store = {}

    def _render_dom_step(inputs):
        from _browser_primitives import p18_render_dom as _shared_render_dom
        return _shared_render_dom(inputs, context)

    def _screenshot_step(inputs):
        from _browser_primitives import p19_screenshot as _shared_screenshot
        return _shared_screenshot(inputs, context)

    primitive_dispatch = {
        "P01": P.P01_file_exists,
        "P02": P.P02_file_content_match,
        "P03": P.P03_file_count,
        "P04": P.P04_http_request,
        "P07": P.P07_json_value_assert,
        "P12": P.P12_docker_exec,
        "P14": P.P14_permission_check,
        "P15": P.P15_status_code_assert,
        "P17": lambda inputs: P.P17_llm_judge(inputs, context),
        "P18": P.P18_browser_interaction,
        "P19": P.P19_dom_assertion,
        "P21": P.P21_websocket_connect,
        "RENDER_DOM": _render_dom_step,
        "SCREENSHOT": _screenshot_step,
    }

    for node in nodes:
        nid = node["id"]
        scoring = node["scoring"]
        context["__current_node_id"] = nid

        if not _all_prereqs_passed(node.get("prereqs", []), results):
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0,
                maxScore=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                method=scoring["method"],
                message="Prerequisite not met"
            )
            continue

        try:
            chain_results = []
            last_output = None

            for step in node["primitive_chain"]:
                ptype = step["type"]
                inputs = dict(step.get("inputs", {}))

                if ptype == "P07" and last_output:
                    inputs.setdefault("response", last_output)
                if ptype == "P15" and last_output:
                    inputs.setdefault("response", last_output)
                if ptype == "P19" and last_output and isinstance(last_output, dict):
                    inputs.setdefault("html", last_output.get("html", last_output.get("text", "")))

                handler = primitive_dispatch.get(ptype)
                if not handler:
                    chain_results.append({"type": ptype, "passed": False, "message": f"Unknown primitive {ptype}"})
                    continue

                result = handler(inputs)
                chain_results.append({"type": ptype, "passed": result.passed, "output": result.output, "message": result.message})

                if result.output and ptype in ("P04", "P12", "P18", "P21", "P01", "P03", "P05"):
                    last_output = result.output

            all_passed = all(r["passed"] for r in chain_results)
            pass_count = sum(1 for r in chain_results if r["passed"])
            total_count = len(chain_results)
            pass_ratio = pass_count / total_count if total_count > 0 else 0
            _judge_skipped = False

            if scoring["method"] == "binary":
                score = scoring["maxScore"] if all_passed else 0
            elif scoring["method"] == "weighted":
                score = round(pass_ratio * scoring["maxScore"], 1)
            elif scoring["method"] == "llm-judge":
                llm_results = [r for r in chain_results if r.get("type") == "P17"]
                last_output = llm_results[-1].get("output") if llm_results else None
                if isinstance(last_output, dict) and last_output.get("skipped"):
                    _judge_skipped = True
                    score = 0
                elif last_output:
                    llm_score = last_output.get("score", 0)
                    score = min(llm_score, scoring["maxScore"])
                else:
                    score = 0
            else:
                score = scoring["maxScore"] if all_passed else 0

            status = "PASSED" if score > 0 else "FAILED"
            if _judge_skipped:
                status = "SKIPPED_LLM"
            msg = ""
            results[nid] = NodeResult(
                node_id=nid, status=status, score=score,
                maxScore=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                method=scoring["method"],
                message=msg,
                evidence={"chain_results": chain_results}
            )

        except Exception as e:
            results[nid] = NodeResult(
                node_id=nid, status="ERROR", score=0,
                maxScore=scoring["maxScore"], category=scoring["category"],
                subcategory=scoring.get("subcategory", ""),
                method=scoring["method"],
                message=f"Exception: {e}\n{traceback.format_exc()}"
            )

    return results


SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate_results(results, scoring_config):
    report = {
        "total_score": 0.0,
        "total_max": 0.0,
        "llm_judge_skipped_maxScore": 0.0,
        "normalized_score": 0,
        "by_category": {},
        "by_status": defaultdict(int),
        "trajectories": {},
    }

    skipped_llm_max = 0.0
    for r in results.values():
        report["by_status"][r.status] += 1
        cat = r.category
        if cat not in report["by_category"]:
            report["by_category"][cat] = {"score": 0, "maxScore": 0, "nodes": 0,
                                          "skipped_llm": 0}
        report["by_category"][cat]["nodes"] += 1
        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.maxScore
            report["by_category"][cat]["skipped_llm"] += 1
            continue
        report["total_score"] += r.score
        report["total_max"] += r.maxScore
        report["by_category"][cat]["score"] += r.score
        report["by_category"][cat]["maxScore"] += r.maxScore

    report["llm_judge_skipped_maxScore"] = round(skipped_llm_max, 3)
    total_max = report["total_max"]
    if total_max > 0:
        report["normalized_score"] = round(report["total_score"] / total_max * 100, 1)

    if "trajectories" in scoring_config:
        for tname, tdata in scoring_config["trajectories"].items():
            t_nodes = tdata.get("nodes", [])
            t_score = 0.0
            t_max = 0.0
            t_skipped_llm_max = 0.0
            for nid in t_nodes:
                if nid not in results:
                    continue
                nr = results[nid]
                if nr.status in SKIP_FROM_TOTAL:
                    t_skipped_llm_max += nr.maxScore
                    continue
                t_score += nr.score
                t_max += nr.maxScore
            report["trajectories"][tname] = {
                "score": t_score, "maxScore": t_max,
                "llm_judge_skipped_maxScore": round(t_skipped_llm_max, 3),
                "pct": round(t_score / t_max * 100, 1) if t_max > 0 else 0,
            }

    return report


def _all_prereqs_passed(prereqs, results):
    for pid in prereqs:
        if pid not in results:
            return False
        if results[pid].status != "PASSED":
            return False
    return True
