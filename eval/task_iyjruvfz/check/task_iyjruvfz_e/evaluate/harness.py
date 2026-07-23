
from __future__ import annotations

import json
import os
import time
import typing as t
from collections import defaultdict, deque
from pathlib import Path

from . import config, primitives, utils
from .utils import NodeResult, PrimitiveResult


def _inject_test_user_placeholders(context: dict) -> None:
    test_users = getattr(config, "TEST_USERS", None)
    if not isinstance(test_users, dict):
        return
    for role, user_info in test_users.items():
        if not isinstance(user_info, dict):
            continue
        for field, value in user_info.items():
            if isinstance(value, (str, int, float, bool)):
                key_main = f"USER_{role}_{field}".upper()
                key_short_upper = f"{role}_{field}".upper()
                key_short_lower = f"{role}_{field}".lower()
                context.setdefault(key_main, value)
                context.setdefault(key_short_upper, value)
                context.setdefault(key_short_lower, value)
    default_pw = getattr(config, "_DEFAULT_USER_PASSWORD", None)
    if default_pw:
        context.setdefault("DEFAULT_USER_PASSWORD", default_pw)
        context.setdefault("default_user_password", default_pw)

    rnd = getattr(config, "RANDOM_SUFFIX", None)
    if rnd:
        context.setdefault("RANDOM_SUFFIX", rnd)
        context.setdefault("random_suffix", rnd)

    try:
        from datetime import datetime, timedelta, timezone

        _now = datetime.now(timezone.utc).replace(microsecond=0)
        _fmt = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        context.setdefault("NOW", _fmt(_now))
        context.setdefault("NOW_PLUS_30M", _fmt(_now + timedelta(minutes=30)))
        context.setdefault("NOW_PLUS_2H", _fmt(_now + timedelta(hours=2)))
        context.setdefault("NOW_DATE", _now.strftime("%Y-%m-%d"))
        context.setdefault("NOW_DATE_PLUS_2D", (_now + timedelta(days=2)).strftime("%Y-%m-%d"))
    except Exception:
        pass

    try:
        for role, user_info in test_users.items():
            if not isinstance(user_info, dict):
                continue
            email = user_info.get("email")
            key_id = f"USER_{role}_ID".upper()
            if not email or key_id in context:
                continue
            res = None
            for tbl in ('users', '"User"', '"users"'):
                try:
                    res = utils.db_query(
                        f"SELECT id FROM {tbl} WHERE email=%s LIMIT 1", (email,)
                    )
                except Exception:
                    res = None
                if res and res.get("ok") and res.get("rows"):
                    break
            if res and res.get("ok") and res.get("rows"):
                context.setdefault(key_id, res["rows"][0]["id"])
    except Exception:
        pass

    try:
        from . import fixtures as _fx
        for role in test_users:
            keyvar = f"{role}_API_KEY".upper()
            if keyvar in context:
                continue
            k = _fx.ensure_api_key(role)
            if k:
                context[keyvar] = k
    except Exception:
        pass

    try:
        from . import fixtures as _fx2
        _fx2.cleanup_eval_bookings()
    except Exception:
        pass

    try:
        from . import fixtures as _fx3
        _fx3.db_query(
            'DELETE FROM "Webhook" WHERE "subscriberUrl" LIKE %s',
            (f"%:{config.MOCK_WEBHOOK_PORT}%",),
        )
    except Exception:
        pass

    try:
        from . import fixtures as _fx4
        _fx4.db_query("DELETE FROM \"ApiKey\" WHERE id LIKE 'eval\\_%'")
    except Exception:
        pass


try:
    from ._dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

SKIP_FROM_TOTAL = {"SKIPPED_LLM", "SKIPPED_TEARDOWN"}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def load_dag(path: str | os.PathLike | None = None) -> dict:
    p = Path(path or config.DAG_FILE)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_scoring_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path or config.SCORING_CONFIG_FILE)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def topological_sort(nodes: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {n["id"]: n for n in nodes}
    indeg: dict[str, int] = {nid: 0 for nid in by_id}
    out_edges: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for p in n.get("prereqs") or []:
            if p in by_id:
                out_edges[p].append(n["id"])
                indeg[n["id"]] += 1
    queue = deque([nid for nid, d in indeg.items() if d == 0])
    result: list[str] = []
    while queue:
        nid = queue.popleft()
        result.append(nid)
        for nxt in out_edges[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)

    if len(result) != len(nodes):
        seen = set(result)
        remaining = [n["id"] for n in nodes if n["id"] not in seen]
        print(f"[harness] WARNING: cycle detected; unsorted remainder appended: {remaining[:10]}...")
        result.extend(remaining)
    return [by_id[i] for i in result]


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


_ENTITY_KEYWORDS = {
    "team": ["TEAM_ID"],
    "booking": ["BOOKING_ID", "BOOKING_UID"],
    "event_type": ["EVENT_TYPE_ID"],
    "eventtype": ["EVENT_TYPE_ID"],
    "user": ["USER_ID"],
    "membership": ["MEMBERSHIP_ID"],
    "webhook": ["WEBHOOK_ID"],
    "workflow": ["WORKFLOW_ID"],
    "schedule": ["SCHEDULE_ID"],
    "api_key": ["OWNER_API_KEY", "API_KEY"],
    "apikey": ["API_KEY"],
    "platform_oauth_client": ["PLATFORM_CLIENT_ID", "PLATFORM_CLIENT_SECRET"],
    "platformoauthclient": ["PLATFORM_CLIENT_ID", "PLATFORM_CLIENT_SECRET"],
    "oauth_client": ["OAUTH_CLIENT_ID"],
}

_ENTITY_RESOURCE_NAME = {
    "team":                   ("team",                "team"),
    "booking":                ("booking",             "booking"),
    "event_type":             ("eventType",           "event_type"),
    "eventtype":              ("eventType",           "event_type"),
    "user":                   ("user",                "user"),
    "membership":             ("membership",          "membership"),
    "webhook":                ("webhook",             "webhook"),
    "workflow":               ("workflow",            "workflow"),
    "schedule":               ("schedule",            "schedule"),
    "api_key":                ("apiKey",              "api_key"),
    "apikey":                 ("apiKey",              "api_key"),
    "platform_oauth_client":  ("platformOauthClient", "platform_oauth_client"),
    "platformoauthclient":    ("platformOauthClient", "platform_oauth_client"),
    "oauth_client":           ("oauthClient",         "oauth_client"),
}


def _extract_entity_ids(node_id: str, last_resp: dict | None, context: dict) -> None:

    if not last_resp:
        return
    body = last_resp.get("body") or {}
    if not isinstance(body, (dict, list)):
        return

    nid = node_id.lower()

    matched_kw = next((kw for kw in _ENTITY_KEYWORDS if kw in nid), None)
    res_pair = _ENTITY_RESOURCE_NAME.get(matched_kw) if matched_kw else None
    res_camel, res_snake = res_pair if res_pair else (None, None)

    # ---- ID candidate paths (by priority) ----
    paths_id = [
        "$.data.id",
        "$.id",
        "$.rows[0].id",
    ]
    if res_camel:
        paths_id += [f"$.{res_camel}.id", f"$.data.{res_camel}.id"]
    if res_snake and res_snake != res_camel:
        paths_id += [f"$.{res_snake}.id", f"$.data.{res_snake}.id"]
    paths_id += [
        "$[0].result.data.id",
        "$[0].result.json.id",
        "$.result.data.id",
        "$.result.json.id",
    ]
    candidates_id = None
    for p in paths_id:
        v = utils.get_json_path(body, p)
        if v is not None:
            candidates_id = v
            break

    # ---- UID candidate paths ----
    paths_uid = ["$.data.uid", "$.uid"]
    if res_camel:
        paths_uid += [f"$.{res_camel}.uid", f"$.data.{res_camel}.uid"]
    candidates_uid = None
    for p in paths_uid:
        v = utils.get_json_path(body, p)
        if v is not None:
            candidates_uid = v
            break

    # ---- Secret candidate paths (snake_case + camelCase compatible) ----
    paths_secret = [
        "$.data.clientSecret",  "$.clientSecret",
        "$.data.client_secret", "$.client_secret",
        "$.data.secret",        "$.secret",
    ]
    candidates_secret = None
    for p in paths_secret:
        v = utils.get_json_path(body, p)
        if v is not None:
            candidates_secret = v
            break

    # ---- Write into context (setdefault: does not overwrite existing values, including dag.json explicit extracts) ----
    for kw, vars_ in _ENTITY_KEYWORDS.items():
        if kw in nid:
            for v in vars_:
                if "SECRET" in v and candidates_secret is not None:
                    context.setdefault(v, candidates_secret)
                elif "UID" in v and candidates_uid is not None:
                    context.setdefault(v, candidates_uid)
                elif candidates_id is not None:
                    context.setdefault(v, candidates_id)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def execute_node(node: dict, results: dict[str, NodeResult], context: dict) -> NodeResult:
    started = time.perf_counter()
    nid = node["id"]
    scoring = node.get("scoring", {})
    category = scoring.get("category", "Other")
    subcat = scoring.get("subcategory", "")
    method = scoring.get("method", "binary")
    max_score = float(scoring.get("maxScore", 1))
    complexity_tier = node.get("complexity_tier", "")

    if (
        category == "Teardown"
        and config.SKIP_TEARDOWN
    ):
        nr = NodeResult(
            node_id=nid,
            status="SKIPPED_TEARDOWN",
            score=0.0,
            max_score=max_score,
            category=category,
            subcategory=subcat,
            method=method,
            message="skipped (teardown not run by default)",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            complexity_tier=complexity_tier,
        )
        return nr


    def _is_prereq_satisfied(nr) -> bool:
        if nr.status in ("PASSED", "SKIPPED_TEARDOWN"):
            return True
        if nr.method in ("weighted", "llm-judge") and nr.score > 0:
            return True
        return False

    prereqs = node.get("prereqs") or []
    failed_prereqs = [
        p for p in prereqs
        if p in results and not _is_prereq_satisfied(results[p])
    ]
    if failed_prereqs:
        nr = NodeResult(
            node_id=nid,
            status="SKIPPED_DEPENDENCY",
            score=0.0,
            max_score=max_score,
            category=category,
            subcategory=subcat,
            method=method,
            message=f"skipped, failed prereqs: {failed_prereqs[:3]}",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            complexity_tier=complexity_tier,
        )
        return nr

    chain = node.get("primitive_chain") or []
    chain_results: list[PrimitiveResult] = []
    last_resp_after_p04: dict | None = None
    chain_extracts_spec = node.get("extracts") or {}

    for call in chain:
        try:
            res = primitives.run_primitive(call, context)
        except Exception as exc:
            res = PrimitiveResult(
                primitive=call.get("type", "P??"),
                passed=False,
                inputs=call.get("inputs", {}),
                error=f"unhandled: {exc}",
                message=f"unhandled: {exc}",
            )
        chain_results.append(res)
        if call.get("type") == "P04" and res.outputs:
            last_resp_after_p04 = {
                "body": res.outputs.get("body"),
                "status_code": res.outputs.get("status_code"),
                "headers": res.outputs.get("headers"),
            }
            if res.passed:
                body_for_chain = res.outputs.get("body")
                if body_for_chain is not None:
                    context["PREVIOUS"] = body_for_chain
                if isinstance(chain_extracts_spec, dict) and chain_extracts_spec:
                    for var_name, json_path_or_list in chain_extracts_spec.items():
                        if not isinstance(var_name, str) or var_name in context:
                            continue
                        if isinstance(json_path_or_list, str):
                            paths_to_try = [json_path_or_list]
                        elif isinstance(json_path_or_list, list):
                            paths_to_try = [p for p in json_path_or_list if isinstance(p, str)]
                        else:
                            continue
                        for p in paths_to_try:
                            v = utils.get_json_path(body_for_chain, p)
                            if v is not None:
                                context[var_name] = v
                                break
                _extract_entity_ids(nid, last_resp_after_p04, context)

    pass_count = sum(1 for r in chain_results if r.passed)
    total = len(chain_results) or 1

    if method == "binary":
        score = max_score if pass_count == total else 0.0
        status = "PASSED" if pass_count == total else "FAILED"
    elif method == "weighted":
        ratio = pass_count / total
        score = round(ratio * max_score, 3)
        status = "PASSED" if pass_count == total else ("PASSED" if ratio >= 0.5 else "FAILED")
    elif method == "llm-judge":
        score = float(context.get("__last_judge_score__", 0))
        rng = context.get("__last_judge_range__", [0, max_score])
        if rng and rng[1] > 0:
            score = round(score / float(rng[1]) * max_score, 3)
        judge_info = primitives.get_last_judge_info()
        if judge_info.get("skipped"):
            status = "SKIPPED_LLM"
            score = 0.0
        else:
            status = "PASSED" if score >= 0.5 * max_score else "FAILED"
    else:
        score = max_score if pass_count == total else 0.0
        status = "PASSED" if pass_count == total else "FAILED"

    if status != "SKIPPED_LLM" and all(not r.passed for r in chain_results) and chain_results:
        if any(r.error for r in chain_results):
            status = "ERROR"

    if status == "PASSED" and last_resp_after_p04:
        explicit_extracts = node.get("extracts") or {}
        if isinstance(explicit_extracts, dict) and explicit_extracts:
            body_for_extract = last_resp_after_p04.get("body") or {}
            for var_name, json_path_or_list in explicit_extracts.items():
                if not isinstance(var_name, str) or var_name in context:
                    continue
                if isinstance(json_path_or_list, str):
                    paths_to_try = [json_path_or_list]
                elif isinstance(json_path_or_list, list):
                    paths_to_try = [p for p in json_path_or_list if isinstance(p, str)]
                else:
                    continue
                for p in paths_to_try:
                    v = utils.get_json_path(body_for_extract, p)
                    if v is not None:
                        context.setdefault(var_name, v)
                        break
        _extract_entity_ids(nid, last_resp_after_p04, context)

    nr = NodeResult(
        node_id=nid,
        status=status,
        score=score,
        max_score=max_score,
        category=category,
        subcategory=subcat,
        method=method,
        message=" | ".join(
            (r.message or f"{r.primitive}:{('ok' if r.passed else 'fail')}") for r in chain_results
        )[:500],
        primitive_results=[r.to_dict() for r in chain_results],
        elapsed_ms=(time.perf_counter() - started) * 1000,
        complexity_tier=complexity_tier,
    )
    return nr


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def execute_dag(
    dag: dict,
    *,
    only_categories: list[str] | None = None,
    only_node_ids: list[str] | None = None,
    on_node_done: t.Callable[[NodeResult], None] | None = None,
) -> dict[str, NodeResult]:
    nodes = dag.get("nodes") or []
    if only_categories:
        nodes = [n for n in nodes if n.get("scoring", {}).get("category") in only_categories]
    if only_node_ids:
        wanted = set(only_node_ids)
        nodes = [n for n in nodes if n["id"] in wanted]

    sorted_nodes = topological_sort(nodes)
    context: dict = {}
    _inject_test_user_placeholders(context)
    results: dict[str, NodeResult] = {}

    for node in sorted_nodes:
        nr = execute_node(node, results, context)
        results[node["id"]] = nr
        if on_node_done:
            try:
                on_node_done(nr)
            except Exception:
                pass
    return results


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def aggregate_results(
    results: dict[str, NodeResult],
    dag: dict,
    scoring_config: dict,
) -> dict:
    countable = [r for r in results.values() if r.status not in SKIP_FROM_TOTAL]
    skipped_llm_max = sum(r.max_score for r in results.values() if r.status in SKIP_FROM_TOTAL)
    total_score = sum(r.score for r in countable)
    max_score = sum(r.max_score for r in countable)
    pct = (total_score / max_score * 100) if max_score else 0.0

    cat_summary: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "max": 0.0, "nodes": [], "skipped_llm_max": 0.0})
    sub_summary: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "max": 0.0, "nodes": [], "skipped_llm_max": 0.0})
    tier_summary: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "max": 0.0, "node_count": 0, "skipped_llm_max": 0.0})
    judge_summary = {"score": 0.0, "max": 0.0, "node_count": 0, "skipped_llm_max": 0.0, "skipped_llm_count": 0}

    for r in results.values():
        skey = f"{r.category}/{r.subcategory}"
        is_skipped_llm = r.status in SKIP_FROM_TOTAL

        if is_skipped_llm:
            cat_summary[r.category]["skipped_llm_max"] += r.max_score
            sub_summary[skey]["skipped_llm_max"] += r.max_score
            if r.complexity_tier:
                tier_summary[r.complexity_tier]["skipped_llm_max"] += r.max_score
        else:
            cat_summary[r.category]["score"] += r.score
            cat_summary[r.category]["max"] += r.max_score
            sub_summary[skey]["score"] += r.score
            sub_summary[skey]["max"] += r.max_score
            if r.complexity_tier:
                tier_summary[r.complexity_tier]["score"] += r.score
                tier_summary[r.complexity_tier]["max"] += r.max_score

        cat_summary[r.category]["nodes"].append(r.node_id)
        sub_summary[skey]["nodes"].append(r.node_id)
        if r.complexity_tier:
            tier_summary[r.complexity_tier]["node_count"] += 1

        if r.method == "llm-judge":
            if is_skipped_llm:
                judge_summary["skipped_llm_max"] += r.max_score
                judge_summary["skipped_llm_count"] += 1
            else:
                judge_summary["score"] += r.score
                judge_summary["max"] += r.max_score
            judge_summary["node_count"] += 1

    trajectories_in_cfg = (scoring_config or {}).get("trajectories", {})
    trajectories_report: dict = {}
    for tname, tdef in trajectories_in_cfg.items():
        ids = tdef.get("node_ids", [])
        sc = sum(
            results[i].score for i in ids
            if i in results and results[i].status not in SKIP_FROM_TOTAL
        )
        mx = sum(
            results[i].max_score for i in ids
            if i in results and results[i].status not in SKIP_FROM_TOTAL
        )
        skip_mx = sum(
            results[i].max_score for i in ids
            if i in results and results[i].status in SKIP_FROM_TOTAL
        )
        trajectories_report[tname] = {
            "description": tdef.get("description"),
            "score": round(sc, 3),
            "max_score": round(mx, 3),
            "llm_judge_skipped_maxScore": round(skip_mx, 3),
            "percentage": round(sc / mx * 100, 2) if mx else 0.0,
            "node_count": len(ids),
        }

    status_counts: dict = defaultdict(int)
    for r in results.values():
        status_counts[r.status] += 1

    pct_excl_judge = (
        round(
            (total_score - judge_summary["score"])
            / (max_score - judge_summary["max"])
            * 100,
            2,
        )
        if (max_score - judge_summary["max"])
        else 0.0
    )

    categories_report = {
        cat: {
            "score": round(d["score"], 3),
            "max_score": round(d["max"], 3),
            "llm_judge_skipped_maxScore": round(d.get("skipped_llm_max", 0.0), 3),
            "percentage": round(d["score"] / d["max"] * 100, 2) if d["max"] else 0.0,
            "node_count": len(d["nodes"]),
        }
        for cat, d in sorted(cat_summary.items())
    }
    subcategories_report = {
        skey: {
            "score": round(d["score"], 3),
            "max_score": round(d["max"], 3),
            "llm_judge_skipped_maxScore": round(d.get("skipped_llm_max", 0.0), 3),
            "percentage": round(d["score"] / d["max"] * 100, 2) if d["max"] else 0.0,
            "node_count": len(d["nodes"]),
        }
        for skey, d in sorted(sub_summary.items())
    }

    return {
        "meta": dag.get("meta", {}),
        "total_score": round(total_score, 3),
        "max_score": round(max_score, 3),
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "percentage": round(pct, 2),
        "percentage_excluding_llm_judge": pct_excl_judge,
        "categories": categories_report,
        "subcategories": subcategories_report,
        "complexity_tiers": {
            k: {
                "score": round(v["score"], 3),
                "max_score": round(v["max"], 3),
                "llm_judge_skipped_maxScore": round(v.get("skipped_llm_max", 0.0), 3),
                "percentage": round(v["score"] / v["max"] * 100, 2) if v["max"] else 0.0,
                "node_count": v["node_count"],
            }
            for k, v in tier_summary.items()
        },
        "trajectories": trajectories_report,
        "judge_summary": {
            "score": round(judge_summary["score"], 3),
            "max_score": round(judge_summary["max"], 3),
            "llm_judge_skipped_maxScore": round(judge_summary["skipped_llm_max"], 3),
            "node_count": judge_summary["node_count"],
            "skipped_llm_count": judge_summary["skipped_llm_count"],
        },
        "status_counts": dict(status_counts),
        "node_results": [r.to_dict() for r in results.values()],
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def print_summary(report: dict) -> None:
    print()
    print("=" * 78)
    print(f"  TOTAL: {report['total_score']:.1f} / {report['max_score']:.1f}  "
          f"= {report['percentage']:.1f}%   "
          f"(excl. llm-judge: {report['percentage_excluding_llm_judge']:.1f}%)")
    print("=" * 78)
    print()
    print("By Category:")
    for cat, d in report["categories"].items():
        bar = "#" * int(d["percentage"] / 5)
        print(f"  {cat:<28} {d['score']:>6.1f}/{d['max_score']:<6.1f} ({d['percentage']:>5.1f}%) {bar}")
    print()
    print("By Complexity Tier:")
    for tier, d in report["complexity_tiers"].items():
        print(f"  {tier:<28} {d['score']:>6.1f}/{d['max_score']:<6.1f} ({d['percentage']:>5.1f}%)")
    print()
    print("By Trajectory:")
    for tn, d in report["trajectories"].items():
        print(f"  {tn:<28} {d['score']:>6.1f}/{d['max_score']:<6.1f} ({d['percentage']:>5.1f}%)")
    print()
    print("Status Counts:", report["status_counts"])
    print()
