
import json
import traceback
from collections import defaultdict, deque
from typing import Any

import primitives
from utils import NodeResult, ArtifactStore
from _result_compat import _result_passed, _result_message, _result_data


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


def load_scoring_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def topological_sort(nodes: list[dict]) -> list[dict]:
    id_map = {n["id"]: n for n in nodes}
    indeg = defaultdict(int)
    adj = defaultdict(list)
    for n in nodes:
        indeg.setdefault(n["id"], 0)
        for p in n.get("prereqs", []):
            adj[p].append(n["id"])
            indeg[n["id"]] += 1
    q = deque(nid for nid, d in indeg.items() if d == 0)
    ordered = []
    while q:
        nid = q.popleft()
        ordered.append(id_map[nid])
        for child in adj[nid]:
            indeg[child] -= 1
            if indeg[child] == 0:
                q.append(child)
    if len(ordered) != len(nodes):
        remaining = set(id_map) - {n["id"] for n in ordered}
        raise ValueError(f"Cycle detected among: {remaining}")
    return ordered


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
PRIMITIVES = {
    "P01": lambda inp, ctx, prev: primitives.p01_file_exists(inp),
    "P02": lambda inp, ctx, prev: primitives.p02_file_content_match(inp),
    "P03": lambda inp, ctx, prev: primitives.p03_file_count(inp),
    "P04": lambda inp, ctx, prev: primitives.p04_http_request(inp, ctx),
    "P05": lambda inp, ctx, prev: primitives.p05_api_crud(inp, ctx),
    "P06": lambda inp, ctx, prev: primitives.p06_json_schema_match(inp, prev),
    "P07": lambda inp, ctx, prev: primitives.p07_json_value_assert(inp, prev),
    "P08": lambda inp, ctx, prev: primitives.p08_db_query(inp),
    "P09": lambda inp, ctx, prev: primitives.p09_db_table_exists(inp),
    "P10": lambda inp, ctx, prev: primitives.p10_db_column_check(inp),
    "P11": lambda inp, ctx, prev: primitives.p11_db_index_check(inp),
    "P12": lambda inp, ctx, prev: primitives.p12_docker_exec(inp, ctx),
    "P13": lambda inp, ctx, prev: primitives.p13_auth_login(inp, ctx),
    "P14": lambda inp, ctx, prev: primitives.p14_permission_check(inp, ctx),
    "P15": lambda inp, ctx, prev: primitives.p15_status_code_assert(inp, prev),
    "P16": lambda inp, ctx, prev: primitives.p16_response_time_check(inp, prev),
    "P17": lambda inp, ctx, prev: primitives.p17_llm_judge(inp, ctx),
}


def _shared_render_dom_dispatch(inp, ctx, _prev):
    from _browser_primitives import p18_render_dom as _shared_render_dom
    return _shared_render_dom(inp, ctx)


def _shared_screenshot_dispatch(inp, ctx, _prev):
    from _browser_primitives import p19_screenshot as _shared_screenshot
    return _shared_screenshot(inp, ctx)


PRIMITIVES.setdefault("RENDER_DOM", _shared_render_dom_dispatch)
PRIMITIVES.setdefault("SCREENSHOT", _shared_screenshot_dispatch)


def _execute_chain(chain: list[dict], context: dict,
                   artifact_store: ArtifactStore) -> tuple[bool, float, str, list]:
    results = []
    prev_data: dict = {}
    all_passed = True

    def _resolve_placeholders(obj, ctx):
        import re
        if isinstance(obj, str):
            def _sub(m):
                key = m.group(1).strip()
                if "." in key:
                    head, _, tail = key.partition(".")
                    base = ctx.get(head)
                    if isinstance(base, dict) and tail in base:
                        return str(base[tail])
                v = ctx.get(key)
                return str(v) if v is not None else m.group(0)
            return re.sub(r"\{\{\s*([A-Za-z_][\w\.]*)\s*\}\}", _sub, obj)
        if isinstance(obj, dict):
            return {k: _resolve_placeholders(v, ctx) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_resolve_placeholders(x, ctx) for x in obj]
        return obj

    for step in chain:
        ptype = step["type"]
        inputs = step.get("inputs", {})
        inputs = _resolve_placeholders(inputs, context or {})
        fn = PRIMITIVES.get(ptype)
        if not fn:
            results.append({"type": ptype, "passed": False, "msg": "unknown primitive"})
            all_passed = False
            continue

        try:
            pr = fn(inputs, context, prev_data)
        except Exception as e:
            results.append({"type": ptype, "passed": False, "msg": str(e)})
            all_passed = False
            continue

        _passed = _result_passed(pr)
        _msg = _result_message(pr)
        _data = _result_data(pr)
        results.append({"type": ptype, "passed": _passed, "msg": _msg, "data": _data})
        artifact_store.record(ptype, {"inputs": inputs, "result": _data, "message": _msg})

        if not _passed:
            all_passed = False

        if ptype == "P04" and _data:
            prev_data = _data
            _extract_entity_ids(_data, context)
        elif ptype == "P05" and _data:
            entity_id = _data.get("entity_id") if isinstance(_data, dict) else None
            if entity_id:
                _store_entity_id_from_crud(context, step, entity_id)
            prev_data = _data
        elif ptype == "P12" and _data:
            _stdout = _data.get("stdout", "") if isinstance(_data, dict) else ""
            _parsed = None
            if _stdout and _stdout.strip():
                import json as _json
                import re as _re
                try:
                    _parsed = _json.loads(_stdout.strip())
                except Exception:
                    _m = _re.search(r"\{.*\}", _stdout, _re.DOTALL)
                    if _m:
                        try:
                            _parsed = _json.loads(_m.group(0))
                        except Exception:
                            _parsed = None
            if isinstance(_parsed, (dict, list)):
                prev_data = {"status_code": 200 if _passed else 500,
                             "body": _parsed}
        elif ptype == "P13" and _data:
            pass
        elif ptype in ("P15", "P06", "P07"):
            pass
        elif ptype == "P17" and _data:
            prev_data = _data

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results) or 1
    return all_passed, (passed_count / total) if total else 0, "; ".join(r["msg"][:80] for r in results[-3:]), results


def _extract_entity_ids(resp_data: dict, context: dict):
    body = resp_data.get("body")
    if not isinstance(body, dict):
        return
    data = body.get("data", body)
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    if not isinstance(data, dict):
        return

    eid = data.get("_id") or data.get("id")
    if not eid:
        return
    eid = str(eid)

    if data.get("type") == "habit":
        context["habit_id"] = eid
    elif data.get("type") == "daily":
        context["daily_id"] = eid
    elif data.get("type") == "todo":
        context["todo_id"] = eid
    elif data.get("type") == "reward":
        context["reward_id"] = eid

    if data.get("type") == "party":
        context["party_id"] = eid
    elif data.get("type") == "guild":
        context["guild_id"] = eid

    if "blockSource" in data:
        context["blocker_id"] = eid
    if "publishDate" in data and "credits" in data:
        context["news_id"] = eid

    if "shortName" in data:
        context["challenge_id"] = eid

    if data.get("type") == "taskActivity":
        context["webhook_id"] = eid

    if "name" in data and not data.get("type"):
        if "tag_id" not in context:
            context["tag_id"] = eid

    if data.get("apiToken"):
        role = "user"
        username = data.get("auth", {}).get("local", {}).get("username", "")
        try:
            from config import TEST_USERS as _TU
            for _r, _info in _TU.items():
                if _info.get("username") == username:
                    role = _r
                    break
        except Exception:
            pass
        context[f"{role}_id"] = eid

    if "quest" in data and "key" in data.get("quest", {}):
        context["quest_key"] = data["quest"]["key"]

    if isinstance(data, list) and all(isinstance(x, str) for x in data):
        if len(data) > 0 and len(data[0]) > 5:
            context["coupon_code"] = data[0]


def _store_entity_id_from_crud(context: dict, step: dict, entity_id: str):
    inputs = step.get("inputs", {})
    create_body = inputs.get("create_body", {})
    task_type = create_body.get("type", "")
    if task_type == "habit":
        context["habit_id"] = entity_id
    elif task_type == "daily":
        context["daily_id"] = entity_id
    elif task_type == "todo":
        context["todo_id"] = entity_id
    elif task_type == "reward":
        context["reward_id"] = entity_id


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def execute_dag(dag: dict, scoring_config: dict,
                only_category: str | None = None,
                with_llm: bool = False) -> list[NodeResult]:
    nodes = dag["nodes"]
    ordered = topological_sort(nodes)

    context: dict[str, Any] = {}
    try:
        from config import TEST_USERS as _TU
        for _role, _info in _TU.items():
            for _k, _v in _info.items():
                context[f"{_role}_{_k}"] = _v
    except Exception:
        pass
    import os as _os_cfg
    context.setdefault("API_V3_PREFIX", _os_cfg.environ.get("API_V3_PREFIX", "/api/v3"))
    context.setdefault("API_V4_PREFIX", _os_cfg.environ.get("API_V4_PREFIX", "/api/v4"))
    artifact_store = ArtifactStore()
    results: dict[str, NodeResult] = {}
    result_list: list[NodeResult] = []

    primitives.p13_reset_cache()

    for node in ordered:
        nid = node["id"]
        scoring = node["scoring"]
        category = scoring["category"]
        subcategory = scoring.get("subcategory", "")
        max_score = scoring["maxScore"]
        method = scoring["method"]

        if only_category and category != only_category:
            continue

        if method == "llm-judge" and not with_llm:
            nr = NodeResult(nid, "SKIPPED_LLM", 0, max_score, category, subcategory,
                            "LLM judge skipped (--with-llm not set)")
            results[nid] = nr
            result_list.append(nr)
            continue

        prereqs = node.get("prereqs", [])
        deps_ok = all(
            results.get(p) and results[p].status in ("PASSED",)
            for p in prereqs
        )
        if not deps_ok:
            failed_deps = [p for p in prereqs if not results.get(p) or results[p].status != "PASSED"]
            nr = NodeResult(nid, "SKIPPED_DEPENDENCY", 0, max_score, category, subcategory,
                            f"Blocked by: {', '.join(failed_deps)}")
            results[nid] = nr
            result_list.append(nr)
            continue

        artifact_store.push_context(nid)
        try:
            chain = node.get("primitive_chain", [])
            all_passed, ratio, msg, evidence = _execute_chain(chain, context, artifact_store)

            status = None
            if method == "binary":
                score = max_score if all_passed else 0
            elif method == "weighted":
                score = round(ratio * max_score, 2)
            elif method == "llm-judge":
                llm_data = {}
                for ev in reversed(evidence):
                    if ev.get("type") == "P17" and isinstance(ev.get("data"), dict):
                        llm_data = ev["data"]
                        break
                if llm_data.get("skipped"):
                    score = 0
                    status = "SKIPPED_LLM"
                else:
                    raw_score = llm_data.get("score", 0) if isinstance(llm_data, dict) else 0
                    score = min(raw_score, max_score)
            else:
                score = max_score if all_passed else 0

            if status is None:
                status = "PASSED" if score > 0 else "FAILED"
            nr = NodeResult(nid, status, score, max_score, category, subcategory, msg,
                            evidence={"chain": evidence})

        except Exception as e:
            nr = NodeResult(nid, "ERROR", 0, max_score, category, subcategory,
                            f"Exception: {e}\n{traceback.format_exc()[:500]}")
        finally:
            artifact_store.pop_context()

        results[nid] = nr
        result_list.append(nr)

        status_icon = "✓" if nr.status == "PASSED" else ("⊘" if "SKIP" in nr.status else "✗")
        print(f"  {status_icon} {nid}: {nr.score}/{nr.max_score}  {nr.message[:80]}")

    return result_list


def aggregate_results(results: list[NodeResult], scoring_config: dict) -> dict:
    SKIP_FROM_TOTAL = {"SKIPPED_LLM"}
    total_earned = sum(r.score for r in results if r.status not in SKIP_FROM_TOTAL)
    total_max = sum(r.max_score for r in results if r.status not in SKIP_FROM_TOTAL)
    skipped_llm_max = sum(r.max_score for r in results if r.status in SKIP_FROM_TOTAL)

    by_category: dict[str, dict] = defaultdict(lambda: {"earned": 0, "max": 0, "nodes": 0})
    by_tier: dict[str, dict] = defaultdict(lambda: {"earned": 0, "max": 0, "nodes": 0})
    by_status: dict[str, int] = defaultdict(int)

    for r in results:
        by_category[r.category]["nodes"] += 1
        by_status[r.status] += 1
        if r.status in SKIP_FROM_TOTAL:
            continue
        by_category[r.category]["earned"] += r.score
        by_category[r.category]["max"] += r.max_score

    normalized = round(total_earned / total_max * 100, 2) if total_max else 0

    return {
        "total_score": total_earned,
        "total_max": total_max,
        "normalized_score": normalized,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "by_category": dict(by_category),
        "by_status": dict(by_status),
        "node_results": [r.to_dict() for r in results],
    }
