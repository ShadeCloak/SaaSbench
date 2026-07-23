
from __future__ import annotations

import importlib
import json
import time
import traceback
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from . import config
from .utils import NodeResult, logger


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------




try:
    from ._dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

class ArtifactStore:

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, Any]] = {}
        self._stack: list[str] = []

    def push_context(self, node_id: str) -> None:
        self._stack.append(node_id)
        self._buckets.setdefault(node_id, {})

    def pop_context(self) -> str | None:
        return self._stack.pop() if self._stack else None

    def current_node_id(self) -> str | None:
        return self._stack[-1] if self._stack else None

    def add_evidence(self, key: str, value: Any) -> None:
        nid = self.current_node_id()
        if nid is None:
            return
        self._buckets[nid][key] = value

    def get_evidence(self, node_id: str) -> dict[str, Any]:
        return self._buckets.get(node_id, {})

    def all_evidence(self) -> dict[str, dict[str, Any]]:
        return dict(self._buckets)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def load_dag(path: Path | str | None = None) -> dict:
    p = Path(path) if path else config.DAG_FILE
    with open(p, "r", encoding="utf-8") as f:
        dag = json.load(f)
    assert "nodes" in dag and isinstance(dag["nodes"], list), "dag.json malformed"
    return dag


def load_scoring_config(path: Path | str | None = None) -> dict:
    p = Path(path) if path else config.SCORING_CONFIG_FILE
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes: list[dict]) -> list[dict]:
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = {nid: 0 for nid in id_to_node}
    adj: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for pq in n.get("prereqs", []):
            if pq in id_to_node:
                adj[pq].append(n["id"])
                in_degree[n["id"]] += 1
    q: deque[str] = deque([nid for nid, d in in_degree.items() if d == 0])
    out: list[dict] = []
    while q:
        nid = q.popleft()
        out.append(id_to_node[nid])
        for nxt in adj[nid]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                q.append(nxt)
    if len(out) < len(nodes):
        unvisited = [nid for nid in id_to_node if nid not in {n["id"] for n in out}]
        raise RuntimeError(f"DAG contains a cycle; unvisited: {unvisited[:10]}")
    return out


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _category_to_module(category: str) -> str:
    import re
    if re.match(r"^[a-z][A-Z]", category):
        category = category[0].upper() + category[1:]
    parts: list[str] = []
    for seg in category.split("_"):
        if not seg:
            continue
        if seg.isupper() or seg.isdigit():
            parts.append(seg.lower())
            continue
        s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", seg)
        s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
        parts.append(s.lower())
    snake = re.sub(r"_+", "_", "_".join(parts).replace("/", "_")).strip("_")
    return f"test_{snake}"


def dispatch_test(node: dict, context: dict) -> NodeResult:
    category = node.get("scoring", {}).get("category", "Unknown")
    mod_name = _category_to_module(category)
    func_name = f"test_{node['id']}"

    t0 = time.time()
    try:
        mod = importlib.import_module(f"tests.{mod_name}", package="evaluate" if __package__ else None)
    except ImportError:
        try:
            mod = importlib.import_module(f"{__package__}.tests.{mod_name}") if __package__ else None
        except Exception as e:
            return NodeResult(
                node_id=node["id"], status="ERROR", score=0, maxScore=node["scoring"]["maxScore"],
                category=category, subcategory=node["scoring"].get("subcategory", ""),
                message=f"Could not import tests.{mod_name}: {e}", elapsed_ms=int((time.time() - t0) * 1000),
            )
    try:
        fn = getattr(mod, func_name)
    except AttributeError:
        return NodeResult(
            node_id=node["id"], status="ERROR", score=0, maxScore=node["scoring"]["maxScore"],
            category=category, subcategory=node["scoring"].get("subcategory", ""),
            message=f"Module tests.{mod_name} has no function {func_name}",
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    try:
        result = fn(context)
        if not isinstance(result, NodeResult):
            result = NodeResult(**result) if isinstance(result, dict) else NodeResult(
                node_id=node["id"], status="ERROR", score=0, maxScore=node["scoring"]["maxScore"],
                category=category, subcategory=node["scoring"].get("subcategory", ""),
                message="test function returned non-NodeResult",
            )
        result.elapsed_ms = int((time.time() - t0) * 1000)
        return result
    except Exception as e:
        logger.exception("Exception in test_%s", node["id"])
        return NodeResult(
            node_id=node["id"], status="ERROR", score=0, maxScore=node["scoring"]["maxScore"],
            category=category, subcategory=node["scoring"].get("subcategory", ""),
            message=f"Exception: {e}\n{traceback.format_exc()[:500]}",
            elapsed_ms=int((time.time() - t0) * 1000),
        )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def execute_dag(
    dag: dict,
    *,
    only_category: str | None = None,
    only_trajectory: str | None = None,
    scoring_config: dict | None = None,
    skip_nodes: set[str] | None = None,
) -> list[NodeResult]:
    nodes = dag["nodes"]
    id_to_node = {n["id"]: n for n in nodes}
    ordered = topological_sort(nodes)

    trajectory_ids: set[str] | None = None
    if only_trajectory and scoring_config:
        traj = scoring_config.get("trajectories", {}).get(only_trajectory, {})
        trajectory_ids = set(traj.get("node_ids", []))

    skip = set(skip_nodes or ())
    artifact_store = ArtifactStore()
    import datetime as _dt
    _now = _dt.datetime.utcnow()
    _run_id = str(int(time.time()))
    try:
        from .primitives import _resolve_password_client
        _pw_client_id, _pw_client_secret = _resolve_password_client()
    except Exception:
        _pw_client_id, _pw_client_secret = config.PASSPORT_CLIENT_ID, config.PASSPORT_CLIENT_SECRET
    context: dict[str, Any] = {
        "run_id": _run_id,
        "token_cache": {},
        "auth_token": None,
        "auth_role": None,
        "rbac_users": config.RBAC_USERS,
        "rbac_users_group_b": config.RBAC_USER_GROUP_B,
        "last_response": None,
        "static_cron_token": config.STATIC_CRON_TOKEN,
        "artifact_store": artifact_store,
        "_start_ts": time.time(),
        "app_container": config.APP_CONTAINER,
        "APP_CONTAINER": config.APP_CONTAINER,
        "db_container": config.DB_CONTAINER,
        "DB_CONTAINER": config.DB_CONTAINER,
        "mock_receiver_container": config.MOCK_RECEIVER_CONTAINER,
        "first_day_of_current_month": _now.replace(day=1).strftime("%Y-%m-%d"),
        "first_of_current_month": _now.replace(day=1).strftime("%Y-%m-%d"),
        "today": _now.strftime("%Y-%m-%d"),
        "today_iso": _now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "yesterday_iso": (_now - _dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        "tomorrow_iso": (_now + _dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        "three_days_ahead_iso": (_now + _dt.timedelta(days=3)).strftime("%Y-%m-%d"),
        "four_days_ago_iso": (_now - _dt.timedelta(days=4)).strftime("%Y-%m-%d"),
        "previous_month_15th": (_now.replace(day=1) - _dt.timedelta(days=1)).replace(day=15).strftime("%Y-%m-%d"),
        "current_year": _now.strftime("%Y"),
        "current_month": _now.strftime("%m"),
        "webhook_port": str(config.MOCK_RECEIVER_PORT),
        "admin_email": config.ADMIN_EMAIL,
        "admin_password": config.ADMIN_PASSWORD,
        "password_client_id": _pw_client_id,
        "password_client_secret": _pw_client_secret,
        "eval_password_client_id": _pw_client_id,
        "eval_password_client_secret": _pw_client_secret,
        "rbac_pass": config._EVAL_RBAC_PASS,
        "eval_rbac_pass": config._EVAL_RBAC_PASS,
        "wrong_password": "wrong-password-xx",
        "new_password": "newpass456",
    }
    for _role, _user_info in config.RBAC_USERS.items():
        if not isinstance(_user_info, dict):
            continue
        for _field, _value in _user_info.items():
            if isinstance(_value, (str, int, float, bool)):
                context[f"rbac_{_role}_{_field}"] = _value
                context[f"{_role}_{_field}"] = _value
    _mon = _now - _dt.timedelta(days=_now.weekday())
    context["most_recent_monday_iso"] = _mon.strftime("%Y-%m-%d")
    _sat_offset = (_now.weekday() - 5) % 7
    _recent_sat = _now - _dt.timedelta(days=_sat_offset)
    context["recent_saturday_iso"] = _recent_sat.strftime("%Y-%m-%d")
    context["weekend_recurrence_first_date"] = (_recent_sat - _dt.timedelta(days=28)).strftime("%Y-%m-%d")
    context["friday_before_recent_saturday"] = (_recent_sat - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    _first_dom = _now.replace(day=1)
    _first_mon = _first_dom + _dt.timedelta(days=(7 - _first_dom.weekday()) % 7)
    context["first_monday_of_current_month"] = _first_mon.strftime("%Y-%m-%d")
    try:
        import subprocess as _sub
        _sub.run(
            ["docker", "exec", config.APP_CONTAINER,
             "php", "/var/www/html/_reset_smoke_data.php"],
            check=False, capture_output=True, timeout=60,
        )
    except Exception:
        pass

    try:
        from .utils import db_query as _dbq
        for code, key in (("EUR", "eur_currency_id"), ("USD", "usd_currency_id"),
                          ("JPY", "jpy_currency_id"), ("BTC", "btc_currency_id")):
            row = _dbq("SELECT id FROM transaction_currencies WHERE code=%s LIMIT 1", (code,))
            if row:
                context[key] = row[0]["id"]
        for typ, key in (("Asset account", "asset_account_eur_id"),
                         ("Expense account", "expense_account_id"),
                         ("Expense account", "expense_account_eur_id"),
                         ("Revenue account", "revenue_account_id")):
            row = _dbq(
                "SELECT a.id FROM accounts a "
                "JOIN account_types at ON at.id=a.account_type_id "
                "WHERE at.type=%s AND a.deleted_at IS NULL "
                "ORDER BY a.id LIMIT 1",
                (typ,),
            )
            if row:
                context[key] = row[0]["id"]
        from .primitives import p13_auth_login as _p13, p04_http_request as _p04
        _login = _p13({"role": "admin"}, context)
        if _login.passed:
            context.pop("asset_account_eur_id", None)
            context.pop("seed_asset_account_id", None)
            context.pop("seed_asset_account_name", None)
            _p04({"method": "POST", "path": "/api/v1/currencies/JPY/enable",
                  "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                  "no_auto_capture": True, "body": {}}, context)
            _btc_rows = _dbq("SELECT id FROM transaction_currencies WHERE code='BTC' LIMIT 1")
            if not _btc_rows:
                _p04({"method": "POST", "path": "/api/v1/currencies",
                      "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                      "no_auto_capture": True,
                      "body": {"code": "BTC", "name": "Bitcoin", "symbol": "B",
                               "decimal_places": 8, "enabled": True}}, context)
            else:
                _p04({"method": "POST", "path": "/api/v1/currencies/BTC/enable",
                      "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                      "no_auto_capture": True, "body": {}}, context)
            for _c, _k in (("JPY", "jpy_currency_id"), ("BTC", "btc_currency_id")):
                _cr = _dbq("SELECT id FROM transaction_currencies WHERE code=%s LIMIT 1", (_c,))
                if _cr:
                    context[_k] = _cr[0]["id"]
            for code, name_suffix in (("EUR", "EvalEURAsset"),
                                      ("USD", "EvalUSDAsset"),
                                      ("JPY", "EvalJPYAsset"),
                                      ("BTC", "EvalBTCAsset")):
                key = f"asset_account_{code.lower()}_id"
                if context.get(key):
                    continue
                _r = _p04({
                    "method": "POST",
                    "path": "/api/v1/accounts",
                    "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                    "body": {
                        "name": f"{name_suffix} {_run_id}",
                        "type": "asset",
                        "currency_code": code,
                        "account_role": "defaultAsset",
                    },
                }, context)
        if not context.get("expense_account_eur_id"):
            _r = _p04({
                "method": "POST",
                "path": "/api/v1/accounts",
                "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                "body": {
                    "name": f"EvalExpenseEUR {_run_id}",
                    "type": "expense",
                    "currency_code": "EUR",
                },
            }, context)
        if not context.get("asset_account_eur_id_2"):
            _r2 = _p04({
                "method": "POST",
                "path": "/api/v1/accounts",
                "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                "no_auto_capture": True,
                "capture_to_context": {"json_path": "$.data.id", "context_key": "asset_account_eur_id_2"},
                "body": {
                    "name": f"EvalEURAsset2 {_run_id}",
                    "type": "asset",
                    "currency_code": "EUR",
                    "account_role": "defaultAsset",
                },
            }, context)
        context["auth_role"] = None
        context["auth_token"] = None
        context["last_response"] = None
    except Exception as _e:
        logger.warning("populate_known_ids failed: %s", _e)

    results: dict[str, NodeResult] = {}
    total = len(ordered)

    for idx, node in enumerate(ordered, start=1):
        nid = node["id"]

        if only_category and node["scoring"]["category"] != only_category:
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_FILTER", score=0,
                maxScore=node["scoring"]["maxScore"],
                category=node["scoring"]["category"],
                subcategory=node["scoring"].get("subcategory", ""),
                message=f"Skipped: filter only_category={only_category}",
            )
            continue

        if trajectory_ids is not None and nid not in trajectory_ids:
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_FILTER", score=0,
                maxScore=node["scoring"]["maxScore"],
                category=node["scoring"]["category"],
                subcategory=node["scoring"].get("subcategory", ""),
                message=f"Skipped: filter only_trajectory={only_trajectory}",
            )
            continue

        if nid in skip:
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_FILTER", score=0,
                maxScore=node["scoring"]["maxScore"],
                category=node["scoring"]["category"],
                subcategory=node["scoring"].get("subcategory", ""),
                message="Skipped: in --skip-nodes list",
            )
            continue

        _passthrough_prereq = (
            "EXECUTED",
        )
        failed_prereqs: list[str] = []
        for pq in node.get("prereqs", []):
            pr = results.get(pq)
            if pr is None:
                continue
            if pr.status == "EXPECTED_REFERENCE_FAIL":
                continue
            if pr.status not in _passthrough_prereq:
                failed_prereqs.append(pq)
                continue
            if pr.score < pr.maxScore * 0.5:
                failed_prereqs.append(pq)
        if failed_prereqs:
            results[nid] = NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0,
                maxScore=node["scoring"]["maxScore"],
                category=node["scoring"]["category"],
                subcategory=node["scoring"].get("subcategory", ""),
                message=f"Skipped: failed prereqs = {failed_prereqs[:3]}",
            )
            continue

        logger.info("[%3d/%3d] Executing %s (%s)", idx, total, nid, node["scoring"]["category"])
        artifact_store.push_context(nid)
        try:
            r = dispatch_test(node, context)
        finally:
            artifact_store.pop_context()
        results[nid] = r

        last_resp = context.get("last_response")
        if last_resp is not None:
            artifact_store._buckets.setdefault(nid, {})["http"] = {
                "status_code": getattr(last_resp, "status_code", None),
                "headers": dict(list(getattr(last_resp, "headers", {}).items())[:10]),
                "body_preview": (getattr(last_resp, "text", "") or "")[:1000],
            }
        _extract_entity_ids(node, r, context)

    return list(results.values())


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


_ENTITY_KEYWORDS = {
    "account":    ("account_id", "asset_id", "asset_account_id", "expense_id", "expense_account_id", "revenue_id", "revenue_account_id"),
    "transaction": ("tx_id", "txn_id", "journal_id", "tg_id"),
    "budget":     ("budget_id", "bid"),
    "category":   ("cat_id", "cid"),
    "tag":        ("tag_id", "tid"),
    "bill":       ("bill_id",),
    "piggy":      ("piggy_id",),
    "recurrence": ("recurrence_id",),
    "rule":       ("rule_id",),
    "rulegroup":  ("rg_id",),
    "webhook":    ("webhook_id",),
    "attachment": ("attachment_id",),
    "currency":   ("currency_id",),
    "user":       ("user_id",),
    "group":      ("user_group_id", "group_id"),
}


def _extract_entity_ids(node: dict, result: NodeResult, context: dict) -> None:
    if result.status != "EXECUTED" or result.score <= 0:
        return
    resp = context.get("last_response")
    if resp is None:
        return
    body = getattr(resp, "json_body", None)
    if not isinstance(body, dict):
        return
    data_id = None
    if isinstance(body.get("data"), dict):
        data_id = body["data"].get("id")
    if data_id is None:
        data_id = body.get("id")
    if data_id is None:
        return
    nid_lower = node["id"].lower()
    for keyword, context_keys in _ENTITY_KEYWORDS.items():
        if keyword in nid_lower:
            for k in context_keys:
                context.setdefault(k, data_id)
            break


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate_results(results: list[NodeResult], scoring_config: dict) -> dict:
    total_score = 0.0
    total_max = 0.0
    skipped_llm_max = 0.0
    for r in results:
        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.maxScore
            continue
        total_score += r.score
        total_max += r.maxScore
    pct = (total_score / total_max * 100) if total_max else 0

    cat_acc: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "maxScore": 0.0, "nodes": 0,
                                                     "skipped_llm": 0,
                                                     "skipped_llm_maxScore": 0.0})
    for r in results:
        c = cat_acc[r.category]
        c["nodes"] += 1
        if r.status in SKIP_FROM_TOTAL:
            c["skipped_llm"] += 1
            c["skipped_llm_maxScore"] += r.maxScore
            continue
        c["score"] += r.score
        c["maxScore"] += r.maxScore
    categories_report = {
        cat: {
            "score": round(v["score"], 2),
            "maxScore": round(v["maxScore"], 2),
            "nodes": v["nodes"],
            "skipped_llm": v["skipped_llm"],
            "skipped_llm_maxScore": round(v["skipped_llm_maxScore"], 3),
            "percent": round(100 * v["score"] / v["maxScore"], 2) if v["maxScore"] else 0,
        } for cat, v in cat_acc.items()
    }

    status_counts = defaultdict(int)
    for r in results:
        status_counts[r.status] += 1

    trajectories_report = {}
    for traj_name, traj_data in (scoring_config.get("trajectories", {}) or {}).items():
        if not isinstance(traj_data, dict) or "node_ids" not in traj_data:
            continue
        ids = set(traj_data["node_ids"])
        subset = [r for r in results if r.node_id in ids]
        t_score = 0.0
        t_max = 0.0
        t_skipped_llm_max = 0.0
        for r in subset:
            if r.status in SKIP_FROM_TOTAL:
                t_skipped_llm_max += r.maxScore
                continue
            t_score += r.score
            t_max += r.maxScore
        trajectories_report[traj_name] = {
            "score": round(t_score, 2),
            "maxScore": round(t_max, 2),
            "llm_judge_skipped_maxScore": round(t_skipped_llm_max, 3),
            "percent": round(100 * t_score / t_max, 2) if t_max else 0,
            "node_count": len(subset),
        }

    return {
        "total_score": round(total_score, 2),
        "max_score": round(total_max, 2),
        "percentage": round(pct, 2),
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "categories": categories_report,
        "status_counts": dict(status_counts),
        "trajectories": trajectories_report,
        "node_count": len(results),
    }
