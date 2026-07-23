from __future__ import annotations

import importlib
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable

import config
from utils import EvalContext, NodeResult


def _inject_test_user_placeholders(ctx_dict: dict) -> None:
    test_users = getattr(config, "TEST_USERS", None) or {}
    for role, info in test_users.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx_dict.setdefault(f"{role}_{field}", value)
                ctx_dict.setdefault(f"eval_{role}_{field}", value)
    account_name = getattr(config, "ACCOUNT_NAME", None)
    if isinstance(account_name, str):
        ctx_dict.setdefault("account_name", account_name)



try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

logger = logging.getLogger("eval")


SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def load_dag(path: str | None = None) -> dict:
    p = path or config.DAG_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_scoring_config(path: str | None = None) -> dict:
    p = path or config.SCORING_CONFIG_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes: list[dict]) -> list[dict]:
    id_map = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)

    for n in nodes:
        for pre in n.get("prereqs", []):
            if pre in id_map:
                adj[pre].append(n["id"])
                in_degree[n["id"]] += 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    ordered = []
    while queue:
        nid = queue.popleft()
        ordered.append(id_map[nid])
        for child in adj[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(ordered) != len(nodes):
        missing = set(id_map.keys()) - {n["id"] for n in ordered}
        logger.error("Cycle detected! Nodes not reachable: %s", missing)
        for nid in missing:
            ordered.append(id_map[nid])

    return ordered


def all_prereqs_passed(prereqs: list[str], results: dict[str, NodeResult]) -> bool:
    for pid in prereqs:
        r = results.get(pid)
        if r is None or r.status in ("FAILED", "SKIPPED_DEPENDENCY", "ERROR"):
            return False
    return True


def execute_chain(chain: list[dict], ctx: EvalContext) -> dict:
    from primitives import execute_primitive, get_last_judge_info

    passed = 0
    total = len(chain)
    evidence = {}
    all_passed = True
    llm_score = None
    llm_judge_info: dict = {}

    for i, step in enumerate(chain):
        ptype = step["type"]
        inputs = step.get("inputs", {})
        step_key = f"step_{i}_{ptype}"

        try:
            ok, ratio = execute_primitive(ptype, inputs, ctx)
            evidence[step_key] = {
                "primitive": ptype,
                "passed": ok,
                "ratio": ratio,
            }
            if ptype == "P17":
                llm_score = ctx.captured.get("_llm_score", 0.0)
                evidence[step_key]["llm_score"] = llm_score
                step_judge_info = get_last_judge_info()
                if step_judge_info:
                    evidence[step_key]["llm_judge_info"] = step_judge_info
                    llm_judge_info = step_judge_info
                passed += 1
            elif ok:
                passed += 1
            else:
                all_passed = False
        except Exception as exc:
            logger.warning("Chain step %d (%s) error: %s", i, ptype, exc)
            evidence[step_key] = {"primitive": ptype, "passed": False, "error": str(exc)}
            all_passed = False

    return {
        "pass_count": passed,
        "total": total,
        "all_passed": all_passed,
        "evidence": evidence,
        "llm_score": llm_score,
        "llm_judge_info": llm_judge_info,
        "llm_judge_skipped": bool(llm_judge_info.get("skipped")),
        "pass_ratio": passed / total if total else 0.0,
    }


def compute_score(node: dict, chain_result: dict) -> float:
    scoring = node["scoring"]
    method = scoring["method"]
    max_score = scoring["maxScore"]

    if method == "binary":
        return float(max_score) if chain_result["all_passed"] else 0.0

    if method == "weighted":
        return round(chain_result["pass_ratio"] * max_score, 2)

    if method == "llm-judge":
        llm_score = chain_result.get("llm_score")
        if llm_score is not None:
            return min(float(llm_score), float(max_score))
        return 0.0

    return 0.0


_WEIGHTED_PLUMBING = {"P04", "P13", "P12"}
_STEP_PTYPE_RE = re.compile(r"_(P\d+|RENDER_DOM|SCREENSHOT)$")


def reweight_verification_only(node: dict, nr: "NodeResult") -> "NodeResult":
    if node.get("scoring", {}).get("method") != "weighted":
        return nr
    if nr.status in ("ERROR", "SKIPPED_DEPENDENCY", "SKIPPED_LLM"):
        return nr
    ev = nr.evidence or {}
    if not isinstance(ev, dict):
        return nr
    verif_total = verif_pass = 0
    for key, val in ev.items():
        m = _STEP_PTYPE_RE.search(key)
        if not m:
            continue
        if m.group(1) in _WEIGHTED_PLUMBING:
            continue
        verif_total += 1
        if isinstance(val, dict) and val.get("passed"):
            verif_pass += 1
    if verif_total == 0:
        return nr
    max_score = float(node["scoring"]["maxScore"])
    new_score = round((verif_pass / verif_total) * max_score, 2)
    if abs(new_score - float(nr.score or 0.0)) < 1e-9:
        return nr
    if verif_pass == verif_total:
        status = "PASSED"
    elif new_score == 0:
        status = "FAILED"
    else:
        status = nr.status
    return NodeResult(
        node_id=nr.node_id,
        status=status,
        score=new_score,
        max_score=nr.max_score,
        evidence=nr.evidence,
        message=(nr.message or "") + f" [verif-only {verif_pass}/{verif_total}]",
    )


def load_test_registry() -> dict[str, Callable]:
    registry: dict[str, Callable] = {}
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    if not os.path.isdir(tests_dir):
        return registry
    for fname in sorted(os.listdir(tests_dir)):
        if fname.startswith("test_") and fname.endswith(".py"):
            mod_name = fname[:-3]
            try:
                mod = importlib.import_module(f"tests.{mod_name}")
                if hasattr(mod, "REGISTRY"):
                    registry.update(mod.REGISTRY)
            except Exception as exc:
                logger.warning("Failed to import tests.%s: %s", mod_name, exc)
    return registry


def run_evaluation(
    dag_path: str | None = None,
    scoring_path: str | None = None,
    node_filter: list[str] | None = None,
    category_filter: list[str] | None = None,
    use_test_files: bool = True,
) -> dict:
    dag = load_dag(dag_path)
    scoring_cfg = load_scoring_config(scoring_path)
    nodes = dag["nodes"]

    if category_filter:
        nodes = [n for n in nodes if n["scoring"]["category"] in category_filter]
    if node_filter:
        nodes = [n for n in nodes if n["id"] in node_filter]

    ordered = topological_sort(nodes)

    test_registry = load_test_registry() if use_test_files else {}
    logger.info("Test registry loaded: %d functions", len(test_registry))

    ctx = EvalContext()
    _inject_test_user_placeholders(ctx.captured)
    results: dict[str, NodeResult] = {}
    start_time = time.time()

    logger.info("Starting evaluation: %d nodes", len(ordered))

    for node in ordered:
        nid = node["id"]
        prereqs = node.get("prereqs", [])

        if not all_prereqs_passed(prereqs, results):
            skipped_by = [p for p in prereqs if results.get(p) and results[p].status != "PASSED"]
            results[nid] = NodeResult(
                node_id=nid,
                status="SKIPPED_DEPENDENCY",
                score=0.0,
                max_score=node["scoring"]["maxScore"],
                message=f"Skipped: prereqs failed {skipped_by}",
            )
            logger.info("[SKIP] %s — prereqs not met", nid)
            continue

        logger.info("[EXEC] %s (%s)", nid, node["scoring"]["method"])
        ctx.current_node_id = nid
        try:
            if nid in test_registry:
                nr = test_registry[nid](ctx)
                method = node["scoring"]["method"]
                if (
                    method == "llm-judge"
                    and nr.status == "FAILED"
                    and (nr.score or 0.0) == 0.0
                ):
                    try:
                        from primitives import get_last_judge_info
                        ji = get_last_judge_info() or {}
                        if ji.get("skipped"):
                            nr = NodeResult(
                                node_id=nid,
                                status="SKIPPED_LLM",
                                score=0.0,
                                max_score=nr.max_score,
                                evidence=nr.evidence,
                                message=("llm-judge skipped: " + (ji.get("reason") or "LLM unavailable"))[:200],
                            )
                    except Exception:
                        pass
                nr = reweight_verification_only(node, nr)
                results[nid] = nr
            else:
                chain_result = execute_chain(node["primitive_chain"], ctx)
                score = compute_score(node, chain_result)
                status = "PASSED" if chain_result["all_passed"] else "FAILED"
                method = node["scoring"]["method"]
                message = f"pass_ratio={chain_result['pass_ratio']:.2f}"
                if method == "llm-judge":
                    if chain_result.get("llm_judge_skipped"):
                        info = chain_result.get("llm_judge_info") or {}
                        status = "SKIPPED_LLM"
                        score = 0.0
                        message = (
                            "llm-judge skipped: "
                            + (info.get("reason") or "LLM unavailable")
                        )[:200]
                    else:
                        status = "PASSED" if score > 0 else "FAILED"

                nr = NodeResult(
                    node_id=nid,
                    status=status,
                    score=score,
                    max_score=node["scoring"]["maxScore"],
                    evidence=chain_result["evidence"],
                    message=message,
                )
                nr = reweight_verification_only(node, nr)
                results[nid] = nr

            logger.info("[%s] %s — %.1f/%.1f", nr.status, nid, nr.score, nr.max_score)
        except Exception as exc:
            logger.error("[ERROR] %s — %s", nid, exc)
            results[nid] = NodeResult(
                node_id=nid,
                status="ERROR",
                score=0.0,
                max_score=node["scoring"]["maxScore"],
                message=str(exc),
            )

    elapsed = time.time() - start_time
    report = aggregate_results(results, scoring_cfg, elapsed)
    return report


def aggregate_results(
    results: dict[str, NodeResult],
    scoring_cfg: dict,
    elapsed: float,
) -> dict:
    category_scores: dict[str, dict] = {}
    for cat, info in scoring_cfg.get("categories", {}).items():
        category_scores[cat] = {
            "maxScore": info["maxScore"],
            "score": 0.0,
            "node_count": info.get("node_count", 0),
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "error": 0,
        }

    node_details = []
    total_score = 0.0
    total_max = 0.0
    skipped_llm_max = 0.0

    for nid, nr in results.items():
        if nr.status in SKIP_FROM_TOTAL:
            skipped_llm_max += nr.max_score
        else:
            total_score += nr.score
            total_max += nr.max_score

        cat = _node_category(nid, nr)
        if cat in category_scores:
            if nr.status not in SKIP_FROM_TOTAL:
                category_scores[cat]["score"] += nr.score
            if nr.status == "PASSED":
                category_scores[cat]["passed"] += 1
            elif nr.status == "FAILED":
                category_scores[cat]["failed"] += 1
            elif nr.status == "SKIPPED_DEPENDENCY":
                category_scores[cat]["skipped"] += 1
            elif nr.status == "SKIPPED_LLM":
                category_scores[cat].setdefault("skipped_llm", 0)
                category_scores[cat]["skipped_llm"] += 1
                category_scores[cat].setdefault("skipped_llm_maxScore", 0.0)
                category_scores[cat]["skipped_llm_maxScore"] = round(
                    category_scores[cat]["skipped_llm_maxScore"] + nr.max_score, 3
                )
                category_scores[cat]["maxScore"] = round(
                    max(category_scores[cat]["maxScore"] - nr.max_score, 0.0), 3
                )
            else:
                category_scores[cat]["error"] += 1

        node_details.append({
            "id": nid,
            "status": nr.status,
            "score": nr.score,
            "maxScore": nr.max_score,
            "message": nr.message,
        })

    normalization = scoring_cfg.get("normalization", "0-100")
    if normalization == "0-100" and total_max > 0:
        normalized = round(total_score / total_max * 100, 2) if total_max else 0
    else:
        normalized = total_score

    return {
        "summary": {
            "total_score": round(total_score, 2),
            "total_maxScore": round(total_max, 2),
            "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
            "normalized_score": normalized,
            "total_nodes": len(results),
            "passed": sum(1 for r in results.values() if r.status == "PASSED"),
            "failed": sum(1 for r in results.values() if r.status == "FAILED"),
            "skipped": sum(1 for r in results.values() if r.status == "SKIPPED_DEPENDENCY"),
            "skipped_llm": sum(1 for r in results.values() if r.status == "SKIPPED_LLM"),
            "errors": sum(1 for r in results.values() if r.status == "ERROR"),
            "elapsed_seconds": round(elapsed, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "categories": category_scores,
        "nodes": node_details,
    }


_node_cat_cache: dict[str, str] = {}


def _node_category(nid: str, nr: NodeResult) -> str:
    if nid in _node_cat_cache:
        return _node_cat_cache[nid]

    try:
        dag = load_dag()
        for n in dag["nodes"]:
            _node_cat_cache[n["id"]] = n["scoring"]["category"]
        return _node_cat_cache.get(nid, "Unknown")
    except Exception:
        return "Unknown"
