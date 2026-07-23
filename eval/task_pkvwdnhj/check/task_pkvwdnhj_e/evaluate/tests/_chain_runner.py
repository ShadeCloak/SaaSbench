import json
import re
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from primitives import PRIMITIVES
from utils import NodeResult

logger = logging.getLogger(__name__)

_PATH_KEY = {
    "/api/lists": "list_id",
    "/api/subscribers": "sub_id",
    "/api/campaigns": "camp_id",
    "/api/templates": "tpl_id",
    "/api/media": "media_id",
    "/api/roles/users": "role_id",
    "/api/roles/lists": "list_role_id",
    "/api/users": "user_id",
}

_CHAIN_LOCAL = {
    "_last_status_code", "_last_response_body", "_last_response_headers",
    "_last_response_raw", "_last_response_time_ms", "_last_entity_id",
    "_last_entity_uuid", "_last_db_id",
}
_ENTITY_RE = re.compile(
    r"^(list_id|sub_id|camp_id|tpl_id|media_id|role_id|user_id|sub_uuid|list_role_id)\d*$"
)


def _resolve_key(key, ctx):
    if key in ctx:
        return ctx[key]
    if "_last_db_id" in ctx:
        return ctx["_last_db_id"]
    for base in ("list_id", "sub_id", "camp_id", "tpl_id", "role_id",
                 "user_id", "media_id"):
        if key.endswith(base) and base in ctx:
            return ctx[base]
    return None


def deep_resolve(obj, ctx):
    if isinstance(obj, str):
        m = re.fullmatch(r"\{\{(\w+)\}\}", obj.strip())
        if m:
            return _resolve_key(m.group(1), ctx)

        def _repl(match):
            v = _resolve_key(match.group(1), ctx)
            return str(v) if v is not None else match.group(0)
        return re.sub(r"\{\{(\w+)\}\}", _repl, obj)
    elif isinstance(obj, dict):
        return {k: deep_resolve(v, ctx) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_resolve(v, ctx) for v in obj]
    return obj


def _store_entity(path, data, ctx):
    if not isinstance(data, dict):
        return
    eid = data.get("id")
    euuid = data.get("uuid")
    if eid is not None:
        ctx["_last_entity_id"] = eid
        for prefix, key in _PATH_KEY.items():
            if path.startswith(prefix):
                if key not in ctx:
                    ctx[key] = eid
                else:
                    for i in range(2, 20):
                        nk = f"{key}{i}"
                        if nk not in ctx:
                            ctx[nk] = eid
                            break
                break
    if euuid is not None:
        ctx["_last_entity_uuid"] = euuid
        if path.startswith("/api/subscribers"):
            ctx["sub_uuid"] = euuid
        elif path.startswith("/api/campaigns"):
            ctx["camp_uuid"] = euuid
        elif path.startswith("/api/lists"):
            ctx["list_uuid"] = euuid


def execute_chain(node, results, ctx):
    scoring = node.get("scoring", {})
    max_score = float(scoring.get("maxScore", 0))
    method = scoring.get("method", "binary")
    node_id = node["id"]
    chain = node.get("primitive_chain", [])

    creates = set()
    for step in chain:
        if step.get("type") == "P04":
            inp = step.get("inputs", {})
            if inp.get("method", "GET").upper() == "POST":
                for prefix, key in _PATH_KEY.items():
                    if inp.get("path", "").startswith(prefix):
                        creates.add(key)
                        break
        if step.get("type") == "P05":
            resource = step.get("inputs", {}).get("resource", "")
            for prefix, key in _PATH_KEY.items():
                if resource.startswith(prefix):
                    creates.add(key)
                    break

    for k in list(ctx.keys()):
        if k in _CHAIN_LOCAL or k.startswith("_db_"):
            del ctx[k]
        elif _ENTITY_RE.match(k):
            base = _ENTITY_RE.match(k).group(1)
            if base in creates:
                del ctx[k]

    passed_count = 0
    total = len(chain)
    last_err = ""
    last_result = {}

    for i, step in enumerate(chain):
        ptype = step["type"]
        inputs = deep_resolve(step.get("inputs", {}), ctx)

        fn = PRIMITIVES.get(ptype)
        if fn is None:
            last_err = f"Unknown primitive {ptype}"
            break

        result = fn(inputs, ctx)
        last_result = result

        if ptype == "P04":
            ctx["_last_status_code"] = result.get("status_code", 0)
            ctx["_last_response_body"] = result.get("body")
            ctx["_last_response_headers"] = result.get("headers", {})
            raw = result.get("body")
            ctx["_last_response_raw"] = raw if isinstance(raw, str) else ""
            ctx["_last_response_time_ms"] = result.get("response_time_ms", 0)

            body = result.get("body")
            if isinstance(body, dict):
                data = body.get("data", body)
                if inputs.get("method", "").upper() == "POST" and isinstance(data, dict):
                    _store_entity(inputs.get("path", ""), data, ctx)

        elif ptype == "P05":
            eid = result.get("entity_id")
            if eid is not None:
                ctx["_last_entity_id"] = eid
                resource = inputs.get("resource", "")
                for prefix, key in _PATH_KEY.items():
                    if resource.startswith(prefix):
                        ctx[key] = eid
                        break

        elif ptype == "P08":
            rows = result.get("rows", [])
            if rows and isinstance(rows[0], dict):
                row = rows[0]
                if "id" in row:
                    ctx["_last_db_id"] = row["id"]
                for k, v in row.items():
                    ctx[f"_db_{k}"] = v

        if result.get("passed"):
            passed_count += 1
        else:
            last_err = (
                f"Step {i}({ptype}): "
                f"{str(result.get('error', result.get('message', '')))[:300]}"
            )
            if method == "binary":
                break

    status: str | None = None
    skipped_evidence: dict = {}
    if method == "binary":
        score = max_score if passed_count == total else 0.0
    elif method == "weighted":
        score = round(max_score * passed_count / max(total, 1), 2)
    elif method == "llm-judge":
        if isinstance(last_result, dict) and last_result.get("skipped"):
            score = 0.0
            status = "SKIPPED_LLM"
            skipped_evidence = {
                "llm_judge_skipped": True,
                "llm_api_failure": last_result.get("llm_api_failure", False),
                "exception_class": last_result.get("exception_class", ""),
                "reason": last_result.get("reason", ""),
            }
        else:
            score = float(last_result.get("score", 0))
    else:
        score = max_score if passed_count == total else 0.0

    if status is None:
        status = "PASS" if score > 0 else "FAIL"
    return NodeResult(
        node_id=node_id,
        status=status,
        score=score,
        max_score=max_score,
        category=scoring.get("category", ""),
        subcategory=scoring.get("subcategory", ""),
        message=(f"{passed_count}/{total}" if status == "PASS"
                 else (skipped_evidence.get("reason", "skipped") if status == "SKIPPED_LLM" else last_err)),
        evidence=skipped_evidence,
    )
