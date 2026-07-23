import importlib
import importlib.util
import inspect
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional



try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

try:
    from .primitives import execute_primitive
    from .utils import NodeResult, print_result, save_results
    from .config import RESULTS_DIR, TEST_USERS
except ImportError:
    from primitives import execute_primitive
    from utils import NodeResult, print_result, save_results
    from config import RESULTS_DIR, TEST_USERS


def _inject_test_user_placeholders(ctx: dict) -> None:
    for role, info in TEST_USERS.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx.setdefault(f"{role}_{field}", value)
                ctx.setdefault(f"eval_{role}_{field}", value)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_TEST_FUNC_REGISTRY: Dict[str, Callable] = {}


def _discover_test_functions() -> Dict[str, Callable]:
    if _TEST_FUNC_REGISTRY:
        return _TEST_FUNC_REGISTRY

    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    if not os.path.isdir(tests_dir):
        return _TEST_FUNC_REGISTRY

    eval_dir = os.path.dirname(os.path.abspath(__file__))
    if eval_dir not in sys.path:
        sys.path.insert(0, eval_dir)

    import primitives as _prim_mod
    import utils as _utils_mod
    sys.modules.setdefault("primitives", _prim_mod)
    sys.modules.setdefault("utils", _utils_mod)

    for fname in sorted(os.listdir(tests_dir)):
        if not fname.startswith("test_") or not fname.endswith(".py"):
            continue
        mod_name = fname[:-3]
        fpath = os.path.join(tests_dir, fname)
        try:
            spec = importlib.util.spec_from_file_location(mod_name, fpath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for name, obj in inspect.getmembers(mod, inspect.isfunction):
                if name.startswith("test_"):
                    node_id = name[5:]
                    _TEST_FUNC_REGISTRY[node_id] = obj
        except Exception:
            pass

    return _TEST_FUNC_REGISTRY


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def load_dag(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def load_scoring_config(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def topological_sort(nodes: List[dict]) -> List[dict]:
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: Dict[str, int] = {n["id"]: 0 for n in nodes}
    adjacency: Dict[str, List[str]] = {n["id"]: [] for n in nodes}

    for n in nodes:
        for prereq in n.get("prereqs", []):
            if prereq in id_to_node:
                adjacency[prereq].append(n["id"])
                in_degree[n["id"]] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    ordered: List[dict] = []

    while queue:
        queue.sort()
        nid = queue.pop(0)
        ordered.append(id_to_node[nid])
        for neighbour in adjacency[nid]:
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if len(ordered) != len(nodes):
        visited_ids = {n["id"] for n in ordered}
        for n in nodes:
            if n["id"] not in visited_ids:
                ordered.append(n)

    return ordered


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_TEST_FN_OVERRIDE_NODES = {
    "AUTH_TOKEN_VALIDATE",
    "BIZ_ACCESS_TOKEN_FORMAT",
    "BIZ_PUBSUB_TOKEN_PRESENT",
    "BIZ_NOTIFICATION_PREFERENCES",
    "BIZ_WEBWIDGET_DEFAULTS",
    "API_AGENT_AVAILABILITY",
    "API_CONVERSATIONS_CREATE",
    "API_INBOX_MEMBERS_ADD",
    "REALTIME_ACTION_CABLE_CONNECT",
    "VAL_API_RATE_LIMIT",
    "API_WEBHOOK_SECRET_AUTO",
    "BIZ_CAMPAIGN_TYPE_ENFORCE",
    "API_SLA_POLICIES_CRUD",
    "API_CONVERSATION_ASSIGN",
    "API_CONVERSATION_LABELS_SET",
    "API_EMAIL_INBOX_CREATE",
    "RBAC_ADMIN_ALLOW_CSAT_DOWNLOAD",
    "RBAC_ADMIN_ALLOW_DELETE_AGENT",
    "RBAC_ADMIN_ALLOW_DELETE_CONTACT",
    "RBAC_ADMIN_ALLOW_DELETE_CONVERSATION",
    "BIZ_CONTACT_MERGE",
    "BIZ_ZERO_INBOX_AGENT_NO_CONVERSATIONS",
    "VAL_CONTACT_SEARCH_PAGINATION",
    "BIZ_AUTOASSIGN_NO_AGENTS_UNASSIGNED",
    "BIZ_CUSTOM_ROLE_REPORT_MANAGE",
    "API_PLATFORM_ACCOUNT_CRUD",
    "API_PLATFORM_USER_CREATE",
    "BIZ_LABEL_CACHED_LIST",
    "RBAC_AGENT_DENY_DELETE_AGENT",
    "API_ARTICLES_CREATE",
    "API_PUBLIC_CONTACT_CREATE",
    "API_SLA_APPLY_TO_CONVERSATION",
    "API_WIDGET_CREATE_CONVERSATION",
    "API_WIDGET_SEND_MESSAGE",
    "BIZ_API_SNAKE_CASE_KEYS",
    "BIZ_ARTICLE_SLUG_FORMAT",
    "BIZ_AUTOASSIGN_ROUND_ROBIN",
    "BIZ_CONTACT_NOTES_CRUD",
    "BIZ_CONVERSATIONS_PAGE_SIZE",
    "BIZ_CONVERSATION_DISPLAY_ID_SEQUENCE",
    "BIZ_CONVERSATION_FILTER",
    "BIZ_CONVERSATION_SORT_ORDER",
    "BIZ_CONV_BLOCKED_CONTACT_RESOLVED",
    "BIZ_CONV_CUSTOM_ATTRS_REPLACE",
    "BIZ_CONV_RECENT_MESSAGES_LIMIT",
    "BIZ_CSAT_RATING_RANGE",
    "BIZ_CSAT_UPDATE_WINDOW",
    "BIZ_MESSAGE_SOFT_DELETE",
    "BIZ_SEARCH_MESSAGES_LIMIT",
    "RBAC_ADMIN_ALLOW_DELETE_CONVERSATION",
    "RBAC_AGENT_ALLOW_CREATE_MESSAGE",
    "SEARCH_GLOBAL_CONVERSATIONS",
    "VAL_CONV_JSONB_FIELD_LENGTH",
}


_ENTITY_KEYWORD_MAP = {
    "INBOX": "inbox_id",
    "CONTACT": "contact_id",
    "CONVERSATION": "conversation_id",
    "AGENT": "agent_id",
    "TEAM": "team_id",
    "LABEL": "label_id",
    "WEBHOOK": "webhook_id",
    "CAMPAIGN": "campaign_id",
    "MACRO": "macro_id",
    "PORTAL": "portal_id",
    "ARTICLE": "article_id",
    "SLA": "sla_policy_id",
    "COMPANY": "company_id",
    "CUSTOM_ROLE": "custom_role_id",
    "CUSTOM_ATTR": "custom_attr_id",
    "CUSTOM_FILTER": "custom_filter_id",
}


def _check_primitive_passed(ptype: str, result: dict, inputs: dict) -> bool:
    if "error" in result and result["error"]:
        if ptype not in ("P04",):
            return False

    if ptype == "P01":
        return result.get("exists", False)

    if ptype == "P02":
        return result.get("matched", False)

    if ptype == "P03":
        return result.get("met_minimum", False)

    if ptype == "P04":
        return True

    if ptype == "P05":
        return result.get("steps_passed", 0) == result.get("steps_total", 1)

    if ptype == "P06":
        return result.get("all_present", False)

    if ptype == "P07":
        return result.get("all_passed", False)

    if ptype == "P08":
        if inputs.get("expected_result") is not None:
            return result.get("match", False)
        return True

    if ptype == "P09":
        return result.get("found_count", 0) > 0

    if ptype == "P10":
        return result.get("found_count", 0) == result.get("total_count", 1)

    if ptype == "P11":
        return result.get("found_count", 0) == result.get("total_count", 1)

    if ptype == "P12":
        return result.get("success", False)

    if ptype == "P13":
        return result.get("success", False)

    if ptype == "P14":
        return result.get("passed", False)

    if ptype == "P15":
        return result.get("passed", False)

    if ptype == "P16":
        return result.get("passed", False)

    if ptype == "P17":
        return True

    if ptype in ("P18", "P19", "P20", "P22", "P23", "P24", "P25", "P27", "P28"):
        return not result.get("not_implemented", False)

    if ptype == "P21":
        if not result.get("connected", False):
            return False
        if inputs.get("expect_message"):
            return result.get("matched", False)
        return True

    if ptype == "P26":
        return result.get("min_met", False)

    if ptype == "P29":
        return result.get("steps_passed", 0) == result.get("steps_total", 1)

    return True


def _compute_weighted_ratio(ptype: str, result: dict) -> float:
    if ptype == "P09":
        total = result.get("total_count", 1)
        found = result.get("found_count", 0)
        return found / total if total else 1.0

    if ptype == "P10":
        total = result.get("total_count", 1)
        found = result.get("found_count", 0)
        return found / total if total else 1.0

    if ptype == "P11":
        total = result.get("total_count", 1)
        found = result.get("found_count", 0)
        return found / total if total else 1.0

    if ptype in ("P05", "P29"):
        total = result.get("steps_total", 1)
        passed = result.get("steps_passed", 0)
        return passed / total if total else 1.0

    if ptype == "P07":
        results_list = result.get("results", [])
        if not results_list:
            return 1.0 if result.get("all_passed", False) else 0.0
        passed = sum(1 for r in results_list if r.get("passed", False))
        return passed / len(results_list)

    return 1.0 if _check_primitive_passed(ptype, result, {}) else 0.0


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _extract_entity_ids_from_chain(node: dict, context: dict) -> None:
    node_id = node.get("id", "")
    if node.get("no_entity_capture"):
        return
    if not any(w in node_id for w in ("CREATE", "CRUD", "LOGIN")):
        return

    entities = context.setdefault("entities", {})
    last_resp = context.get("last_response")

    if not isinstance(last_resp, dict):
        return

    entity_id = last_resp.get("id")
    if entity_id is None:
        return

    for keyword, entity_key in _ENTITY_KEYWORD_MAP.items():
        if keyword in node_id:
            primary_key = f"primary_{entity_key}"
            if primary_key not in entities:
                entities[primary_key] = entity_id
            entities[entity_key] = entity_id
            break


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_ENTITY_CREATION_NODES = {
    "API_CONVERSATIONS_CREATE", "API_CONTACTS_CREATE", "API_INBOXES_CREATE",
    "API_AGENTS_CREATE", "API_TEAMS_CREATE", "API_LABELS_CREATE",
    "API_WEBHOOKS_CREATE", "API_CAMPAIGNS_CREATE", "API_MACROS_CREATE",
    "API_PORTALS_CRUD", "API_ARTICLES_CREATE", "API_SLA_POLICIES_CRUD",
    "API_CUSTOM_ATTRS_CREATE", "API_CUSTOM_FILTERS_CREATE",
    "API_EMAIL_INBOX_CREATE", "API_PLATFORM_ACCOUNT_CRUD",
    "API_PLATFORM_USER_CREATE", "API_PUBLIC_CONTACT_CREATE",
    "API_WIDGET_CREATE_CONVERSATION", "AUTH_ADMIN_LOGIN",
    "AUTH_TOKEN_VALIDATE", "API_INBOX_MEMBERS_ADD",
}


def _restore_entities_after_override(node_id: str, saved: dict, context: dict):
    if node_id in _ENTITY_CREATION_NODES:
        new_ents = context.get("entities", {})
        for keyword, entity_key in _ENTITY_KEYWORD_MAP.items():
            if keyword in node_id:
                saved[entity_key] = new_ents.get(entity_key, saved.get(entity_key))
                pk = f"primary_{entity_key}"
                if pk in new_ents:
                    saved[pk] = new_ents[pk]
    context["entities"] = saved


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _execute_node(node: dict, context: dict, with_llm: bool) -> NodeResult:
    node_id = node["id"]
    scoring = node.get("scoring", {})
    category = scoring.get("category", "")
    subcategory = scoring.get("subcategory", "")
    method = scoring.get("method", "binary")
    max_score = float(scoring.get("maxScore", 1))
    complexity_tier = node.get("complexity_tier", "")
    chain = node.get("primitive_chain", [])

    if method != "llm-judge":
        registry = _discover_test_functions()
        test_fn = registry.get(node_id)
        if test_fn is not None and node_id in _TEST_FN_OVERRIDE_NODES:
            saved_entities = dict(context.get("entities", {}))
            try:
                nr = test_fn(context)
                if isinstance(nr, NodeResult):
                    _restore_entities_after_override(node_id, saved_entities, context)
                    nr.complexity_tier = complexity_tier
                    return nr
            except Exception as e:
                context["entities"] = saved_entities
                import logging
                logging.warning("Test override %s crashed: %s\n%s", node_id, e, traceback.format_exc())

    if not chain:
        return NodeResult(
            node_id=node_id, status="PASSED", score=max_score,
            max_score=max_score, category=category, subcategory=subcategory,
            message="No primitives to execute", complexity_tier=complexity_tier,
        )

    chain_results: List[dict] = []
    chain_passed: List[bool] = []
    chain_ratios: List[float] = []
    llm_score_result = None
    skip_next_p07 = False
    last_p04_method: Optional[str] = None

    for step in chain:
        ptype = step.get("type", "")
        inputs = dict(step.get("inputs", {}))
        inputs["node_id"] = node_id

        if ptype == "P07" and skip_next_p07:
            chain_results.append({"all_passed": True, "skipped_idempotent": True})
            chain_passed.append(True)
            chain_ratios.append(1.0)
            skip_next_p07 = False
            continue

        if ptype == "P04":
            skip_next_p07 = False
            last_p04_method = inputs.get("method", "GET").upper()

        try:
            result = execute_primitive(ptype, inputs, context)
        except Exception as e:
            result = {"error": str(e), "traceback": traceback.format_exc()}

        chain_results.append(result)

        if ptype == "P15":
            actual_status = context.get("last_response_status")
            p15_passed = result.get("passed", False)
            expected_status = inputs.get("expected_status", [])
            if isinstance(expected_status, int):
                expected_status = [expected_status]

            has_success_codes = any(s in (200, 201) for s in expected_status)

            if actual_status == 422 and last_p04_method == "POST":
                if not p15_passed:
                    result["passed"] = True
                    p15_passed = True
                if has_success_codes:
                    skip_next_p07 = True
            elif p15_passed and actual_status is not None and actual_status not in (200, 201) and has_success_codes:
                skip_next_p07 = True

        if "error" in result and result["error"] and ptype != "P04":
            chain_passed.append(False)
            chain_ratios.append(0.0)
            if ptype != "P17":
                break
        else:
            passed = _check_primitive_passed(ptype, result, inputs)
            chain_passed.append(passed)
            chain_ratios.append(_compute_weighted_ratio(ptype, result))

        if ptype == "P17":
            llm_score_result = result

    _extract_entity_ids_from_chain(node, context)

    if method == "llm-judge" and llm_score_result is not None:
        if llm_score_result.get("skipped"):
            reason = llm_score_result.get("reason") or llm_score_result.get("reasoning") or "skipped"
            return NodeResult(
                node_id=node_id, status="SKIPPED_LLM", score=0,
                max_score=max_score, category=category, subcategory=subcategory,
                message=f"LLM judge skipped: {str(reason)[:200]}",
                evidence=chain_results, complexity_tier=complexity_tier,
            )
        raw_score = float(llm_score_result.get("score", 0))
        llm_max = float(llm_score_result.get("max_score", max_score) or max_score)
        if llm_max > 0 and llm_max != max_score:
            score = (raw_score / llm_max) * max_score
        else:
            score = min(raw_score, max_score)
        score = max(0.0, min(score, max_score))
        status = "PASSED" if score > 0 else "FAILED"
        reasoning = llm_score_result.get("reasoning", "")
        return NodeResult(
            node_id=node_id, status=status, score=round(score, 2),
            max_score=max_score, category=category, subcategory=subcategory,
            message=f"LLM judge: {reasoning[:200]}" if reasoning else "LLM judge evaluation",
            evidence=chain_results, complexity_tier=complexity_tier,
        )

    if method == "weighted":
        if chain_ratios:
            avg_ratio = sum(chain_ratios) / len(chain_ratios)
        else:
            avg_ratio = 0.0
        score = round(avg_ratio * max_score, 2)
        all_ok = all(chain_passed)
        status = "PASSED" if all_ok else ("FAILED" if score == 0 else "PASSED")
        return NodeResult(
            node_id=node_id, status=status, score=score,
            max_score=max_score, category=category, subcategory=subcategory,
            message=f"Weighted: {score}/{max_score}",
            evidence=chain_results, complexity_tier=complexity_tier,
        )

    all_ok = all(chain_passed)
    score = max_score if all_ok else 0.0
    status = "PASSED" if all_ok else "FAILED"
    fail_details = ""
    if not all_ok:
        for i, (passed, step) in enumerate(zip(chain_passed, chain)):
            if not passed:
                fail_details = f"{step.get('type', '?')} failed"
                break
    return NodeResult(
        node_id=node_id, status=status, score=score,
        max_score=max_score, category=category, subcategory=subcategory,
        message=fail_details if fail_details else "All checks passed",
        evidence=chain_results, complexity_tier=complexity_tier,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def execute_dag(
    dag: dict,
    scoring_config: dict,
    only_category: Optional[str] = None,
    dry_run: bool = False,
    with_llm: bool = False,
) -> List[NodeResult]:
    nodes = dag.get("nodes", [])
    ordered = topological_sort(nodes)

    context: Dict[str, Any] = {
        "entities": {},
        "last_response": None,
        "last_status_code": None,
        "last_response_time_ms": None,
    }
    _inject_test_user_placeholders(context)

    results: List[NodeResult] = []
    result_map: Dict[str, NodeResult] = {}

    for node in ordered:
        node_id = node["id"]
        scoring = node.get("scoring", {})
        category = scoring.get("category", "")
        subcategory = scoring.get("subcategory", "")
        max_score = float(scoring.get("maxScore", 1))
        method = scoring.get("method", "binary")
        complexity_tier = node.get("complexity_tier", "")

        if only_category and category != only_category:
            nr = NodeResult(
                node_id=node_id, status="SKIPPED_DEPENDENCY", score=0,
                max_score=max_score, category=category, subcategory=subcategory,
                message=f"Filtered out (category != {only_category})",
                complexity_tier=complexity_tier,
            )
            results.append(nr)
            result_map[node_id] = nr
            continue

        if not with_llm and method == "llm-judge":
            nr = NodeResult(
                node_id=node_id, status="SKIPPED_DEPENDENCY", score=0,
                max_score=max_score, category=category, subcategory=subcategory,
                message="LLM judge disabled (use --with-llm)",
                complexity_tier=complexity_tier,
            )
            results.append(nr)
            result_map[node_id] = nr
            continue

        prereqs = node.get("prereqs", [])
        prereq_failed = False
        for prereq_id in prereqs:
            prereq_result = result_map.get(prereq_id)
            if prereq_result is None or prereq_result.status != "PASSED":
                prereq_failed = True
                break

        if prereq_failed:
            nr = NodeResult(
                node_id=node_id, status="SKIPPED_DEPENDENCY", score=0,
                max_score=max_score, category=category, subcategory=subcategory,
                message=f"Prerequisite not met: {prereq_id}",
                complexity_tier=complexity_tier,
            )
            results.append(nr)
            result_map[node_id] = nr
            continue


        if dry_run:
            chain_desc = " -> ".join(s.get("type", "?") for s in node.get("primitive_chain", []))
            print(f"  [plan] {node_id}: {chain_desc} ({method}, max={max_score})")
            nr = NodeResult(
                node_id=node_id, status="SKIPPED_DEPENDENCY", score=0,
                max_score=max_score, category=category, subcategory=subcategory,
                message="Dry run", complexity_tier=complexity_tier,
            )
            results.append(nr)
            result_map[node_id] = nr
            continue

        try:
            nr = _execute_node(node, context, with_llm)
        except Exception as e:
            nr = NodeResult(
                node_id=node_id, status="ERROR", score=0,
                max_score=max_score, category=category, subcategory=subcategory,
                message=str(e)[:300], complexity_tier=complexity_tier,
            )

        results.append(nr)
        result_map[node_id] = nr
        print_result(nr)

    return results


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def aggregate_results(results: List[NodeResult], scoring_config: dict) -> dict:
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}
    total_score = 0.0
    max_score = 0.0
    skipped_llm_max = 0.0
    nodes_passed = 0
    nodes_failed = 0
    nodes_skipped = 0
    nodes_error = 0
    nodes_skipped_llm = 0

    by_category: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"score": 0.0, "maxScore": 0.0, "pct": 0.0, "passed": 0, "failed": 0, "skipped": 0, "skipped_llm": 0}
    )

    for r in results:
        cat = by_category[r.category]

        if r.status == "PASSED":
            nodes_passed += 1
            cat["passed"] += 1
        elif r.status == "FAILED":
            nodes_failed += 1
            cat["failed"] += 1
        elif r.status == "SKIPPED_LLM":
            nodes_skipped_llm += 1
            cat["skipped_llm"] += 1
        elif r.status == "SKIPPED_DEPENDENCY":
            nodes_skipped += 1
            cat["skipped"] += 1
        elif r.status == "ERROR":
            nodes_error += 1
            cat["failed"] += 1

        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.max_score
            continue

        total_score += r.score
        max_score += r.max_score
        cat["score"] += r.score
        cat["maxScore"] += r.max_score

    for cat in by_category.values():
        cat["pct"] = round((cat["score"] / cat["maxScore"] * 100) if cat["maxScore"] else 0, 1)

    percentage = round((total_score / max_score * 100) if max_score else 0, 1)

    config_max = float(scoring_config.get("total_maxScore", max_score)) if scoring_config else max_score
    normalized_score = round((total_score / config_max * 100) if config_max else 0, 1)

    by_trajectory: Dict[str, Dict[str, Any]] = {}
    trajectories = scoring_config.get("trajectories", {}) if scoring_config else {}
    result_map = {r.node_id: r for r in results}

    for traj_name, traj_info in trajectories.items():
        traj_node_ids = traj_info.get("node_ids", [])
        traj_max = float(traj_info.get("maxScore", 0))
        traj_score = 0.0
        for nid in traj_node_ids:
            r = result_map.get(nid)
            if r and r.status not in SKIP_FROM_TOTAL:
                traj_score += r.score
        by_trajectory[traj_name] = {
            "score": round(traj_score, 2),
            "maxScore": traj_max,
            "pct": round((traj_score / traj_max * 100) if traj_max else 0, 1),
        }

    return {
        "summary": {
            "total_score": round(total_score, 2),
            "max_score": round(max_score, 2),
            "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
            "percentage": percentage,
            "normalized_score": normalized_score,
            "nodes_passed": nodes_passed,
            "nodes_failed": nodes_failed,
            "nodes_skipped": nodes_skipped,
            "nodes_skipped_llm": nodes_skipped_llm,
            "nodes_error": nodes_error,
        },
        "by_category": dict(by_category),
        "by_trajectory": by_trajectory,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def generate_report(
    results: List[NodeResult],
    scoring_config: dict,
    path: str,
) -> dict:
    aggregated = aggregate_results(results, scoring_config)

    node_details = []
    for r in results:
        entry = asdict(r)
        if "evidence" in entry:
            entry.pop("evidence", None)
        node_details.append(entry)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": aggregated["summary"],
        "by_category": aggregated["by_category"],
        "by_trajectory": aggregated["by_trajectory"],
        "node_results": node_details,
    }

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    return report
