import json
import os
import re
from collections import defaultdict, deque
from typing import Optional

import primitives
from primitives import context as prim_context, execute_primitive
from utils import NodeResult
from config import TEST_USERS
from _result_compat import _result_passed, _result_message, _result_data


ROLE_ALIASES: dict[str, list[str]] = {
    "admin": ["admin", "Admin", "administrator", "Administrator",
              "system_admin", "system_administrator", "SystemAdmin",
              "superuser", "root"],
    "user":  ["user", "User", "member", "Member",
              "channel_user", "regular_user", "registered_user"],
    "guest": ["guest", "Guest", "channel_guest", "anonymous", "visitor"],
}


LOCAL_ADMIN_SOCKET_PATH = os.environ.get("LOCAL_ADMIN_SOCKET_PATH", "/tmp/mm_local.sock")
LOCAL_ADMIN_SOCKET_FALLBACKS = [
    "/tmp/mm_local.sock",
    "/tmp/admin_local.sock",
    "/tmp/app_local.sock",
    "/var/run/admin.sock",
    "/var/run/admin_local.sock",
]


def _inject_test_user_placeholders(ctx: dict) -> None:
    for role, info in TEST_USERS.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx.setdefault(f"{role}_{field}", value)
                ctx.setdefault(f"eval_{role}_{field}", value)
    ctx.setdefault("local_admin_socket_path", LOCAL_ADMIN_SOCKET_PATH)
    ctx.setdefault("local_admin_socket_fallbacks", " ".join(LOCAL_ADMIN_SOCKET_FALLBACKS))




try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

_ENTITY_KEYWORDS = [
    ("TEAMS_CREATE", "evalteam_id"),
    ("CHANNELS_CREATE_PRIVATE", "eval_priv_id"),
    ("CHANNELS_DIRECT_CREATE", "eval_dm_id"),
    ("CHANNELS_GROUP_CREATE", "eval_gm_id"),
    ("CHANNELS_CREATE", "eval_pub_id"),
    ("INCOMING_WEBHOOK_CREATE", "webhook_id"),
    ("OUTGOING_WEBHOOK_CREATE", "outgoing_webhook_id"),
    ("POSTS_CREATE", "post_id"),
    ("POSTS_EDIT", "edited_post_id"),
    ("SCHEDULED_POST_CREATE", "scheduled_post_id"),
    ("REACTIONS_CREATE", "reaction_id"),
    ("FILES_UPLOAD", "file_id"),
    ("PAT_CREATE", "pat_token_id"),
    ("OAUTH_APP_CREATE", "oauth_app_id"),
    ("COMMAND_CREATE", "command_id"),
    ("BOT_CREATE", "bot_user_id"),
    ("EMOJI_CREATE", "emoji_id"),
    ("PLUGIN_INSTALL", "plugin_id"),
    ("ROLE_CREATE", "role_id"),
    ("SCHEME_CREATE", "scheme_id"),
    ("GROUP_CREATE", "group_id"),
    ("DRAFT_CREATE", "draft_id"),
    ("CPA_FIELD_CREATE", "cpa_field_id"),
    ("PROPERTY_FIELD_CREATE", "property_field_id"),
    ("ACCESS_CONTROL_POLICY_CREATE", "policy_id"),
    ("RETENTION_POLICY_CREATE", "retention_policy_id"),
    ("REMOTE_CLUSTER_CREATE", "remote_cluster_id"),
    ("AUTH_CREATE_FIRST_USER", "admin_user_id"),
    ("AUTH_CREATE_REGULAR_USER", "eval_user_id"),
    ("AUTH_CREATE_GUEST", "eval_guest_id"),
    ("UPLOAD_SESSION_CREATE", "upload_session_id"),
    ("CHANNEL_BOOKMARK_CREATE", "bookmark_id"),
    ("SIDEBAR_CATEGORY_CREATE", "sidebar_category_id"),
]


def _extract_entity_ids(node_id: str, response_body):
    if not isinstance(response_body, dict):
        if isinstance(response_body, dict) and "file_infos" in response_body:
            arr = response_body.get("file_infos", [])
            if arr and isinstance(arr[0], dict) and "id" in arr[0]:
                prim_context["file_id"] = arr[0]["id"]
        return
    rid = response_body.get("id")
    if not rid:
        return
    for keyword, var_name in _ENTITY_KEYWORDS:
        if keyword in node_id:
            prim_context[var_name] = rid
            break


class CycleDetectedError(RuntimeError):
    pass


def topological_sort(nodes, *, raise_on_cycle: bool = True):
    id_to_node = {n["id"]: n for n in nodes}
    in_deg = {n["id"]: 0 for n in nodes}
    adj = defaultdict(list)
    for n in nodes:
        for p in n.get("prereqs", []):
            if p in id_to_node:
                adj[p].append(n["id"])
                in_deg[n["id"]] += 1
    queue = deque(nid for nid, d in in_deg.items() if d == 0)
    order = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for nb in adj[nid]:
            in_deg[nb] -= 1
            if in_deg[nb] == 0:
                queue.append(nb)
    if len(order) != len(nodes):
        unsorted_ids = [nid for nid in id_to_node if nid not in set(order)]
        if raise_on_cycle:
            raise CycleDetectedError(
                f"DAG cycle detected — {len(unsorted_ids)} nodes unsortable: "
                f"{unsorted_ids[:8]}{'...' if len(unsorted_ids) > 8 else ''}"
            )
        order.extend(unsorted_ids)
    return [id_to_node[nid] for nid in order]


def execute_dag(dag, scoring_config, *, only_category=None, with_llm=False, dry_run=False,
                only_nodes: Optional[list[str]] = None):
    nodes = dag["nodes"]
    ordered = topological_sort(nodes)
    results: dict[str, NodeResult] = {}
    out: list[NodeResult] = []

    primitives.reset_context()
    _inject_test_user_placeholders(prim_context)

    for node in ordered:
        nid = node["id"]
        scoring = node["scoring"]
        category = scoring["category"]
        sub = scoring.get("subcategory", "")
        method = scoring["method"]
        max_score = scoring["maxScore"]

        if only_nodes is not None and nid not in only_nodes:
            continue
        if only_category and category.lower() != only_category.lower():
            continue
        if method == "llm-judge" and not with_llm:
            r = NodeResult(nid, "SKIPPED_LLM", 0, max_score, category, sub, "llm-judge skipped")
            results[nid] = r; out.append(r); continue

        if dry_run:
            r = NodeResult(nid, "DRY_RUN", 0, max_score, category, sub, "dry run")
            results[nid] = r; out.append(r); continue

        deps_ok = True
        bad_deps = []
        for dep_id in node.get("prereqs", []):
            dep = results.get(dep_id)
            if dep is None:
                deps_ok = False
                bad_deps.append(f"{dep_id}=missing")
                break
            if dep.status != "PASSED":
                deps_ok = False
                bad_deps.append(f"{dep_id}={dep.status}")
                break
        if not deps_ok:
            r = NodeResult(nid, "SKIPPED_DEPENDENCY", 0, max_score, category, sub,
                           f"prereqs not satisfied: {bad_deps}")
            results[nid] = r; out.append(r); continue

        chain = node.get("primitive_chain", [])
        prim_results = []
        passed_count = 0
        all_passed = True
        try:
            for spec in chain:
                pr = execute_primitive(spec)
                prim_results.append(pr.to_dict() if hasattr(pr, "to_dict") else dict(pr) if isinstance(pr, dict) else {"passed": _result_passed(pr), "message": _result_message(pr), "data": _result_data(pr)})
                if _result_passed(pr):
                    passed_count += 1
                else:
                    all_passed = False
                    if method == "binary":
                        break
            last_resp = prim_context.get("__last_response", {})
            if last_resp.get("body") is not None and 200 <= last_resp.get("status", 0) < 300:
                _extract_entity_ids(nid, last_resp["body"])
        except Exception as e:
            r = NodeResult(nid, "ERROR", 0, max_score, category, sub, f"exception: {e}",
                           evidence={"prim_results": prim_results})
            results[nid] = r; out.append(r); continue

        if method == "binary":
            score = max_score if all_passed else 0
            status = "PASSED" if all_passed else "FAILED"
        elif method == "weighted":
            ratio = passed_count / max(1, len(chain))
            score = round(ratio * max_score, 2)
            if ratio == 1.0:
                status = "PASSED"
            elif ratio > 0:
                status = "PARTIAL"
            else:
                status = "FAILED"
        elif method == "llm-judge":
            score = 0
            status = "FAILED"
            for pr in prim_results:
                if pr.get("type") != "P17":
                    continue
                out_ = pr.get("output") or {}
                extras = pr.get("extras") or {}
                if out_.get("skipped") or extras.get("skipped"):
                    status = "SKIPPED_LLM"
                    score = 0
                    break
                llm_score = out_.get("score", 0)
                score_max = out_.get("max", 5)
                score = round(max_score * llm_score / max(1, score_max), 2)
                if score >= max_score * 0.6:
                    status = "PASSED"
                elif score > 0:
                    status = "PARTIAL"
                else:
                    status = "FAILED"
                break
        else:
            score = 0
            status = "ERROR"

        msg = f"{passed_count}/{len(chain)} primitives passed"
        r = NodeResult(nid, status, score, max_score, category, sub, msg,
                       evidence={"prim_results": prim_results})
        results[nid] = r
        out.append(r)

    return out


SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate_results(results, scoring_config):
    by_cat = defaultdict(lambda: {"score": 0, "max": 0, "count": 0,
                                   "passed": 0, "skipped_llm": 0})
    total_score = 0
    total_max = 0
    skipped_llm_max = 0
    counts = defaultdict(int)
    for r in results:
        is_skipped_llm = r.status in SKIP_FROM_TOTAL
        by_cat[r.category]["count"] += 1
        if r.status == "PASSED":
            by_cat[r.category]["passed"] += 1
        if is_skipped_llm:
            by_cat[r.category]["skipped_llm"] += 1
            skipped_llm_max += r.maxScore
        else:
            by_cat[r.category]["score"] += r.score
            by_cat[r.category]["max"] += r.maxScore
            total_score += r.score
            total_max += r.maxScore
        counts[r.status] += 1

    pct = round(100 * total_score / total_max, 1) if total_max else 0

    happy = scoring_config.get("trajectories", {}).get("happy_path", {})
    advanced = scoring_config.get("trajectories", {}).get("advanced_workflows", {})
    happy_ids = set(happy.get("node_ids", []))
    adv_ids = set(advanced.get("node_ids", []))

    def _traj_totals(ids):
        s = 0.0
        m = 0.0
        skipped = 0
        for r in results:
            if r.node_id not in ids:
                continue
            if r.status in SKIP_FROM_TOTAL:
                skipped += 1
                continue
            s += r.score
            m += r.maxScore
        return s, m, skipped

    happy_score, happy_max, happy_skipped = _traj_totals(happy_ids)
    adv_score, adv_max, adv_skipped = _traj_totals(adv_ids)

    return {
        "total_score": total_score,
        "total_max": total_max,
        "percentage": pct,
        "status_counts": dict(counts),
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "categories": {c: {"score": v["score"], "max": v["max"],
                            "pct": round(100 * v["score"] / v["max"], 1) if v["max"] else 0,
                            "node_count": v["count"], "passed": v["passed"],
                            "skipped_llm": v["skipped_llm"]}
                       for c, v in by_cat.items()},
        "trajectories": {
            "happy_path": {"score": happy_score, "max": happy_max,
                            "pct": round(100 * happy_score / happy_max, 1) if happy_max else 0,
                            "skipped_llm": happy_skipped},
            "advanced_workflows": {"score": adv_score, "max": adv_max,
                                    "pct": round(100 * adv_score / adv_max, 1) if adv_max else 0,
                                    "skipped_llm": adv_skipped},
        },
    }
