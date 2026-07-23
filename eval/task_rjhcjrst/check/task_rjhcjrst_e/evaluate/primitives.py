
from __future__ import annotations

import base64
import glob as glob_mod
import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    pymysql = None

try:
    from jsonpath_ng import parse as jsonpath_parse
except ImportError:
    jsonpath_parse = None

from . import config
from .utils import (
    HTTPResponseLike, NodeResult, PrimitiveResult, db_conn, db_query,
    db_execute_rowcount, docker_exec, http_request, logger,
    substitute_placeholders,
)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _wrap_url(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    if not path_or_url.startswith("/"):
        path_or_url = "/" + path_or_url
    return f"{config.APP_BASE_URL}{path_or_url}"


def _decimal_eq(a: Any, b: Any, tolerance: Any = None) -> bool:
    try:
        ad = Decimal(str(a))
        bd = Decimal(str(b))
    except (InvalidOperation, TypeError):
        return False
    if tolerance is None:
        return ad == bd
    try:
        td = Decimal(str(tolerance))
    except InvalidOperation:
        return False
    return abs(ad - bd) <= td


def _eval_jsonpath(body: Any, path: str) -> Any:
    if jsonpath_parse is None:
        if path.startswith("$."):
            cur = body
            for part in path[2:].split("."):
                if isinstance(cur, dict):
                    cur = cur.get(part)
                else:
                    return None
            return cur
        return None
    try:
        expr = jsonpath_parse(path)
        matches = expr.find(body)
        return matches[0].value if matches else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p01_file_exists(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    expected_type = inputs.get("type", "any")
    candidates = inputs.get("any_of") or inputs.get("paths") or [inputs.get("path", "")]
    if not isinstance(candidates, list):
        candidates = [candidates]
    if inputs.get("in_container") or inputs.get("container"):
        base = inputs.get("container_base", "/var/www/html")
        flag = "-d" if expected_type == "dir" else ("-f" if expected_type == "file" else "-e")
        found_path = None
        for p in candidates:
            full = f"{base}/{p}" if not str(p).startswith("/") else str(p)
            rc, out, err = docker_exec(
                container=config.APP_CONTAINER,
                command=f"test {flag} '{full}' && echo OK || true", timeout=15)
            if rc == 0 and "OK" in (out or ""):
                found_path = full
                break
        return PrimitiveResult(
            passed=found_path is not None,
            data={"exists": found_path is not None, "path": found_path or candidates[0],
                  "candidates": [str(c) for c in candidates], "in_container": True},
            elapsed_ms=int((time.time() - t0) * 1000),
            error=None if found_path else f"none of {candidates} exists in container {config.APP_CONTAINER}:{base}",
        )
    found = None
    for p in candidates:
        full = config.WORKSPACE_DIR / p
        if not full.exists():
            continue
        if expected_type == "file" and not full.is_file():
            continue
        if expected_type == "dir" and not full.is_dir():
            continue
        found = full
        break
    return PrimitiveResult(
        passed=found is not None,
        data={
            "exists": found is not None,
            "is_file": found.is_file() if found else False,
            "path": str(found) if found else str(config.WORKSPACE_DIR / candidates[0]),
            "candidates": [str(c) for c in candidates],
        },
        elapsed_ms=int((time.time() - t0) * 1000),
        error=None if found else f"none of {candidates} exists under {config.WORKSPACE_DIR}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p02_file_content_match(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    candidates = inputs.get("path_any_of") or inputs.get("paths") or [inputs.get("path", "")]
    if not isinstance(candidates, list):
        candidates = [candidates]
    text = None
    full = None
    if inputs.get("in_container") or inputs.get("container"):
        base = inputs.get("container_base", "/var/www/html")
        for p in candidates:
            fp = f"{base}/{p}" if not str(p).startswith("/") else str(p)
            rc, out, _err = docker_exec(
                container=config.APP_CONTAINER,
                command=f"test -f '{fp}' && cat '{fp}' || true", timeout=20)
            if rc == 0 and out:
                text = out
                full = fp
                break
        if text is None:
            return PrimitiveResult(
                passed=False,
                error=f"none of {candidates} is a readable file in container {config.APP_CONTAINER}:{base}",
                elapsed_ms=int((time.time() - t0) * 1000),
            )
    else:
        for p in candidates:
            cand = config.WORKSPACE_DIR / p
            if cand.is_file():
                full = cand
                break
        if full is None:
            return PrimitiveResult(
                passed=False,
                error=f"none of {candidates} is a file under {config.WORKSPACE_DIR}",
                elapsed_ms=int((time.time() - t0) * 1000),
            )
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return PrimitiveResult(passed=False, error=f"read failed: {e}",
                                   elapsed_ms=int((time.time() - t0) * 1000))
    match_type = inputs.get("match_type", "contains")
    pattern = inputs.get("pattern", "")
    matched = False
    count = 0
    first_line = -1
    if match_type == "contains":
        matched = pattern in text
        if matched:
            count = text.count(pattern)
            first_line = text[: text.find(pattern)].count("\n") + 1
    elif match_type == "regex":
        try:
            matches = list(re.finditer(pattern, text, re.MULTILINE))
            count = len(matches)
            matched = count > 0
            if matched:
                first_line = text[: matches[0].start()].count("\n") + 1
        except re.error as e:
            return PrimitiveResult(passed=False, error=f"bad regex: {e}",
                                   elapsed_ms=int((time.time() - t0) * 1000))
    elif match_type == "json_path":
        try:
            data = json.loads(text)
            matched = _eval_jsonpath(data, pattern) is not None
            count = 1 if matched else 0
        except Exception as e:
            return PrimitiveResult(passed=False, error=f"json parse: {e}",
                                   elapsed_ms=int((time.time() - t0) * 1000))
    return PrimitiveResult(
        passed=matched,
        data={"matched": matched, "match_count": count, "first_match_line": first_line},
        elapsed_ms=int((time.time() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p03_file_count(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    base = config.WORKSPACE_DIR / inputs.get("base_dir", ".")
    pattern = inputs.get("glob", "*")
    min_expected = inputs.get("min_expected", 1)
    files = list(glob_mod.glob(str(base / pattern), recursive=True))
    return PrimitiveResult(
        passed=len(files) >= min_expected,
        data={"count": len(files), "files": [Path(f).name for f in files[:30]]},
        elapsed_ms=int((time.time() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


class _SkipAutoCapture(Exception):
    pass


def p04_http_request(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs_resolved = substitute_placeholders(inputs, context)
    method = inputs_resolved.get("method", "GET")
    path_or_url = inputs_resolved.get("path", "/")
    url = _wrap_url(path_or_url)
    headers = dict(config.DEFAULT_API_HEADERS)
    _is_token_endpoint = "/oauth/token" in str(path_or_url)
    if (not inputs_resolved.get("no_auth") and not _is_token_endpoint
            and context.get("auth_token")):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    headers.update(inputs_resolved.get("headers", {}) or {})
    if _is_token_endpoint:
        headers.pop("Authorization", None)
    body = inputs_resolved.get("body")
    params = inputs_resolved.get("params") or inputs_resolved.get("query_params")
    timeout = inputs_resolved.get("timeout") or config.HTTP_TIMEOUT
    _raw_b64 = inputs_resolved.get("raw_body_b64")
    _raw_bytes = None
    if _raw_b64:
        try:
            _raw_bytes = base64.b64decode(_raw_b64)
        except Exception:
            _raw_bytes = None
    _p = str(path_or_url)
    _oauth_web = (
        _p.startswith("/oauth/") and not _p.startswith("/oauth/token")
        and not _p.startswith("/oauth/authorize")
    )
    _use_web_session = inputs_resolved.get("use_web_session") or _oauth_web
    if _use_web_session and requests is not None:
        _sess = _web_login_session()
    else:
        _sess = None
    if _sess is not None:
        _t = time.time()
        try:
            _sess_headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
            _sess_headers.setdefault("X-Requested-With", "XMLHttpRequest")
            if method.upper() not in ("GET", "HEAD", "OPTIONS"):
                _xsrf = _sess.cookies.get("XSRF-TOKEN")
                if _xsrf:
                    import urllib.parse as _up
                    _sess_headers.setdefault("X-XSRF-TOKEN", _up.unquote(_xsrf))
            _r = _sess.request(
                method=method.upper(), url=url, headers=_sess_headers,
                json=body if isinstance(body, (dict, list)) else None,
                data=(_raw_bytes if _raw_bytes is not None
                      else (body if isinstance(body, str) else None)),
                params=params, timeout=timeout, allow_redirects=True,
            )
            resp = HTTPResponseLike(
                status_code=_r.status_code, headers=dict(_r.headers),
                body=_r.content, elapsed_ms=int((time.time() - _t) * 1000), url=_r.url,
            )
        except Exception as _e:
            resp = HTTPResponseLike(0, {"x-error": str(_e)[:500]}, b"", int((time.time() - _t) * 1000), url)
    else:
        _allow_redirects = inputs_resolved.get("allow_redirects",
                                                inputs_resolved.get("follow_redirects", True))
        resp = http_request(
            method=method, url=url, headers=headers,
            json_body=None if _raw_bytes is not None else (body if isinstance(body, (dict, list)) else None),
            data=_raw_bytes if _raw_bytes is not None else (body if isinstance(body, str) else None),
            params=params, timeout=timeout, allow_redirects=_allow_redirects,
        )
    context["last_response"] = resp
    capture_as = (
        inputs_resolved.get("as")
        or inputs_resolved.get("capture_as")
        or inputs_resolved.get("save_as")
    )
    if capture_as:
        context[capture_as] = resp
    cap = inputs_resolved.get("capture_to_context")
    if isinstance(cap, dict) and cap.get("context_key"):
        ck = cap["context_key"]
        path = cap.get("json_path") or cap.get("path")
        if path:
            try:
                context[ck] = _eval_jsonpath(resp.json_body or {}, path)
            except Exception:
                pass
        else:
            rx = cap.get("regex")
            if rx:
                m = re.search(rx, resp.text or "")
                if m:
                    context[ck] = m.group(1) if m.groups() else m.group(0)
    #
    try:
        if inputs_resolved.get("no_auto_capture"):
            raise _SkipAutoCapture()
        jb = resp.json_body
        _inferred_rtype = None
        try:
            _request_path = (inputs_resolved.get("path") or "").strip()
            _segs = [s for s in _request_path.split("/") if s and not s.startswith("?")]
            for _s in reversed(_segs):
                if "{" in _s or _s.startswith("$") or _s.isdigit():
                    continue
                if _s in ("api", "v1", "v2", "v3"):
                    continue
                _inferred_rtype = _s
                break
        except Exception:
            _inferred_rtype = None

        normalized = None
        if isinstance(jb, dict):
            if isinstance(jb.get("data"), dict) and ("id" in jb["data"] or "type" in jb["data"]):
                normalized = jb
            elif isinstance(jb.get("data"), dict) and isinstance(jb["data"].get("id"), (str, int)):
                _d = dict(jb["data"])
                normalized = {"data": {"id": _d.pop("id"), "type": _inferred_rtype, "attributes": _d}}
            elif isinstance(jb.get("result"), dict) and isinstance(jb["result"].get("id"), (str, int)):
                _r = jb["result"]
                if isinstance(_r.get("data"), dict) and isinstance(_r["data"].get("id"), (str, int)):
                    _r = _r["data"]
                _r2 = dict(_r)
                normalized = {"data": {"id": _r2.pop("id"), "type": _inferred_rtype, "attributes": _r2}}
            elif isinstance(jb.get("payload"), dict) and isinstance(jb["payload"].get("id"), (str, int)):
                _p = dict(jb["payload"])
                normalized = {"data": {"id": _p.pop("id"), "type": _inferred_rtype, "attributes": _p}}
            elif isinstance(jb.get("id"), (str, int)):
                _flat = {k: v for k, v in jb.items() if k != "id"}
                normalized = {"data": {"id": jb["id"], "type": _inferred_rtype, "attributes": _flat}}
            elif isinstance(jb.get("rows"), list) and jb["rows"] and isinstance(jb["rows"][0], dict) and isinstance(jb["rows"][0].get("id"), (str, int)):
                _row = jb["rows"][0]
                _flat = {k: v for k, v in _row.items() if k != "id"}
                normalized = {"data": {"id": _row["id"], "type": _inferred_rtype, "attributes": _flat}}
            elif isinstance(jb.get("_id"), (str, int)):
                _flat = {k: v for k, v in jb.items() if k != "_id"}
                normalized = {"data": {"id": jb["_id"], "type": _inferred_rtype, "attributes": _flat}}

        if isinstance(normalized, dict) and isinstance(normalized.get("data"), dict):
            d = normalized["data"]
            rid = d.get("id")
            rtype = d.get("type")
            attrs = d.get("attributes", {}) or {}
            if rid is not None and rtype:
                singular = rtype[:-1] if rtype.endswith("s") and not rtype.endswith("ss") else rtype
                context[f"{singular}_id"] = rid
                if rtype == "accounts":
                    atype = (attrs.get("type") or "").lower()
                    ccode = (attrs.get("currency_code") or "").upper()
                    if atype == "asset":
                        context["asset_id"] = rid
                        context["asset_account_id"] = rid
                        if ccode:
                            context[f"asset_account_{ccode.lower()}_id"] = rid
                            context.setdefault(f"asset_account_{ccode.lower()}_name", attrs.get("name"))
                        context.setdefault("asset_account_eur_id", rid)
                        context.setdefault("seed_asset_account_id", rid)
                        context.setdefault("seed_asset_account_name", attrs.get("name"))
                    elif atype == "expense":
                        context["expense_id"] = rid
                        context["expense_account_id"] = rid
                        context.setdefault("seed_expense_account_id", rid)
                        if ccode:
                            context[f"expense_account_{ccode.lower()}_id"] = rid
                    elif atype == "revenue":
                        context["revenue_id"] = rid
                        context["revenue_account_id"] = rid
                elif rtype == "currencies":
                    ccode = (attrs.get("code") or "").upper()
                    if ccode:
                        context[f"{ccode.lower()}_currency_id"] = rid
                elif rtype == "rule_groups":
                    context.setdefault("rule_group_id", rid)
                    context.setdefault("rg_id", rid)
                    context.setdefault("seed_rule_group_id", rid)
                elif rtype == "rules":
                    context.setdefault("rule_id", rid)
                elif rtype == "piggy_banks":
                    context.setdefault("piggy_id", rid)
                elif rtype == "recurrences":
                    context.setdefault("rec_id", rid)
                elif rtype == "webhooks":
                    context.setdefault("wh_id", rid)
                elif rtype == "transactions":
                    context.setdefault("tg_id", rid)
                    txns = attrs.get("transactions", []) or []
                    if isinstance(txns, list) and txns:
                        first = txns[0]
                        context.setdefault("tx_journal_id", first.get("transaction_journal_id"))
                        context.setdefault("seed_transaction_id", rid)
                elif rtype == "bills":
                    context.setdefault("bill_id", rid)
                elif rtype == "budgets":
                    context.setdefault("budget_id", rid)
                elif rtype == "categories":
                    context.setdefault("category_id", rid)
                    context.setdefault("cat_id", rid)
                elif rtype == "tags":
                    context.setdefault("tag_id", rid)
                elif rtype == "user_groups":
                    context.setdefault("group_id", rid)
                    context.setdefault("group_a_id", rid)
                elif rtype == "users":
                    context.setdefault("user_id", rid)
                elif rtype == "attachments":
                    context.setdefault("attachment_id", rid)
    except Exception:
        pass
    passed = resp.status_code > 0
    return PrimitiveResult(
        passed=passed,
        data={
            "status_code": resp.status_code,
            "headers": dict(list(resp.headers.items())[:20]) if resp.headers else {},
            "body": resp.json_body if resp.json_body is not None else resp.text[:1000],
            "response_time_ms": resp.elapsed_ms,
            "url": resp.url,
        },
        elapsed_ms=resp.elapsed_ms,
        error=None if passed else "request failed (status_code=0)",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p05_api_crud(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs = substitute_placeholders(inputs, context)
    base_path = inputs.get("resource", "")
    headers = dict(config.DEFAULT_API_HEADERS)
    if context.get("auth_token"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    create_body = inputs.get("create_body", {})
    update_body = inputs.get("update_body", {})
    expected_create = inputs.get("expected_create_status", 201)
    expected_read_fields = inputs.get("expected_read_fields", [])
    expected_update = inputs.get("expected_update_status", 200)
    expected_delete = inputs.get("expected_delete_status", 204)

    steps_passed = 0
    steps_total = 4
    create = read = update = delete = {"success": False}
    record_id: Any = None

    rc = http_request("POST", _wrap_url(base_path), headers=headers, json_body=create_body)
    if rc.status_code in (expected_create, 200, 201):
        steps_passed += 1
        body = rc.json_body
        if isinstance(body, dict):
            data = body.get("data") if isinstance(body.get("data"), dict) else body
            record_id = data.get("id") if isinstance(data, dict) else None
        create = {"success": True, "id": record_id, "status_code": rc.status_code}

    if record_id:
        rr = http_request("GET", _wrap_url(f"{base_path}/{record_id}"), headers=headers)
        if rr.status_code == 200:
            body = rr.json_body
            attrs = (body.get("data", {}) if isinstance(body, dict) else {}).get("attributes", {}) or (body or {})
            missing = [f for f in expected_read_fields if f not in attrs]
            if not missing:
                steps_passed += 1
                read = {"success": True, "status_code": rr.status_code}

    if record_id:
        ru = http_request("PUT", _wrap_url(f"{base_path}/{record_id}"), headers=headers, json_body=update_body)
        if ru.status_code in (expected_update, 200, 204):
            steps_passed += 1
            update = {"success": True, "status_code": ru.status_code}

    if record_id:
        rd = http_request("DELETE", _wrap_url(f"{base_path}/{record_id}"), headers=headers)
        if rd.status_code in (expected_delete, 200, 204):
            steps_passed += 1
            delete = {"success": True, "status_code": rd.status_code}

    return PrimitiveResult(
        passed=(steps_passed == steps_total),
        data={"steps_passed": steps_passed, "steps_total": steps_total,
              "create": create, "read": read, "update": update, "delete": delete},
        elapsed_ms=int((time.time() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p06_json_schema_match(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    resp: Optional[HTTPResponseLike] = context.get("last_response")
    body = resp.json_body if resp else None
    if not isinstance(body, dict):
        return PrimitiveResult(passed=False, error="last_response body is not a JSON object",
                               elapsed_ms=int((time.time() - t0) * 1000))
    required = inputs.get("required_fields", [])
    type_map = inputs.get("field_types", {})
    missing = [f for f in required if f not in body]
    type_errors = []
    for field, expected_type in type_map.items():
        if field not in body:
            continue
        value = body[field]
        ok = (
            (expected_type == "string" and isinstance(value, str)) or
            (expected_type == "integer" and isinstance(value, int) and not isinstance(value, bool)) or
            (expected_type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) or
            (expected_type == "boolean" and isinstance(value, bool)) or
            (expected_type == "array" and isinstance(value, list)) or
            (expected_type == "object" and isinstance(value, dict)) or
            (expected_type == "null" and value is None)
        )
        if not ok:
            type_errors.append({"field": field, "expected": expected_type, "actual": type(value).__name__})
    passed = not missing and not type_errors
    return PrimitiveResult(
        passed=passed,
        data={"all_present": passed, "missing_fields": missing, "type_mismatches": type_errors},
        elapsed_ms=int((time.time() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _eval_predicate(actual, predicate: str, value) -> bool:
    try:
        if predicate == "string_min_length":
            return isinstance(actual, str) and len(actual) >= int(value or 0)
        if predicate == "string_max_length":
            return isinstance(actual, str) and len(actual) <= int(value or 0)
        if predicate == "string_length":
            return isinstance(actual, str) and len(actual) == int(value or 0)
        if predicate == "min_length":
            return hasattr(actual, "__len__") and len(actual) >= int(value or 0)
        if predicate == "max_length":
            return hasattr(actual, "__len__") and len(actual) <= int(value or 0)
        if predicate == "length":
            return hasattr(actual, "__len__") and len(actual) == int(value or 0)
        if predicate == "contains":
            if isinstance(actual, str):
                return str(value) in actual
            if isinstance(actual, (list, tuple, set, dict)):
                return value in actual
            return False
        if predicate == "starts_with":
            return isinstance(actual, str) and actual.startswith(str(value))
        if predicate == "ends_with":
            return isinstance(actual, str) and actual.endswith(str(value))
        if predicate == "matches" or predicate == "regex":
            return isinstance(actual, str) and re.search(str(value), actual) is not None
        if predicate == "is_string":
            return isinstance(actual, str)
        if predicate == "is_int" or predicate == "is_integer":
            return isinstance(actual, int) and not isinstance(actual, bool)
        if predicate == "is_number":
            return isinstance(actual, (int, float)) and not isinstance(actual, bool)
        if predicate == "is_bool":
            return isinstance(actual, bool)
        if predicate == "is_list" or predicate == "is_array":
            return isinstance(actual, list)
        if predicate == "is_dict" or predicate == "is_object":
            return isinstance(actual, dict)
        if predicate == "is_null":
            return actual is None
        if predicate == "is_not_null":
            return actual is not None
        if predicate == "eq" or predicate == "equals":
            return actual == value or _decimal_eq(actual, value)
        if predicate == "ne" or predicate == "not_equals":
            return actual != value
        if predicate == "gt":
            return actual is not None and actual > value
        if predicate == "gte" or predicate == "ge":
            return actual is not None and actual >= value
        if predicate == "lt":
            return actual is not None and actual < value
        if predicate == "lte" or predicate == "le":
            return actual is not None and actual <= value
        if predicate == "in":
            return actual in (value or [])
        if predicate == "not_in":
            return actual not in (value or [])
        if predicate == "decimal_eq":
            return _decimal_eq(actual, value)
        return False
    except Exception:
        return False


def _p08_predicate_ok(actual, op, value) -> bool:
    _sym = {">=": "gte", ">": "gt", "<=": "lte", "<": "lt",
            "=": "eq", "==": "eq", "!=": "ne", "<>": "ne"}
    pop = _sym.get(str(op).strip(), str(op).strip())
    if pop in ("gte", "gt", "lte", "lt", "eq", "ne"):
        try:
            actual, value = float(actual), float(value)
        except (TypeError, ValueError):
            pass
    return _eval_predicate(actual, pop, value)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _eval_jsonpath_all(body: Any, path: str) -> list:
    if jsonpath_parse is None:
        v = _eval_jsonpath(body, path)
        return [] if v is None else [v]
    try:
        return [m.value for m in jsonpath_parse(path).find(body)]
    except Exception:
        return []


def _json_type_ok(val: Any, jtype: str) -> bool:
    if jtype == "array":
        return isinstance(val, list)
    if jtype == "object":
        return isinstance(val, dict)
    if jtype == "integer":
        return isinstance(val, int) and not isinstance(val, bool)
    if jtype == "number":
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    if jtype == "string":
        return isinstance(val, str)
    if jtype == "boolean":
        return isinstance(val, bool)
    if jtype == "null":
        return val is None
    return True


def _numeric_string_ok(val: Any) -> bool:
    if not isinstance(val, str):
        return False
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


def _one_match_ok(actual: Any, match_type: str, a: dict, json_type: Optional[str]) -> bool:
    expected = a.get("expected")
    if expected is None:
        expected = a.get("expected_numeric", a.get("expected_value"))
    pattern = a.get("pattern") or a.get("regex")
    if match_type == "contains":
        if isinstance(actual, (list, dict)):
            return expected in actual
        return expected is not None and str(expected) in str(actual)
    if match_type in ("regex", "regex_match"):
        pat = pattern if pattern is not None else expected
        return isinstance(actual, str) and pat is not None and re.search(pat, actual) is not None
    if match_type in ("starts_with", "startswith"):
        return isinstance(actual, str) and expected is not None and actual.startswith(str(expected))
    if match_type in ("ends_with", "endswith"):
        return isinstance(actual, str) and expected is not None and actual.endswith(str(expected))
    if match_type == "numeric_string":
        if not _numeric_string_ok(actual):
            return False
        if expected is None:
            return True
        try:
            return float(actual) == float(expected)
        except (ValueError, TypeError):
            return False
    if match_type in ("numeric_equal", "numeric_equals"):
        try:
            return float(actual) == float(expected)
        except (ValueError, TypeError):
            return False
    if match_type == "numeric_equal_to_zero":
        try:
            return abs(float(actual)) < 1e-9
        except (ValueError, TypeError):
            return False
    if match_type == "equals":
        return actual == expected or _decimal_eq(actual, expected)
    if json_type is not None:
        return _json_type_ok(actual, json_type)
    return actual is not None


def _match_assert(body: Any, path: str, actual: Any, match_type: str,
                  a: dict, json_type: Optional[str]) -> bool:
    if match_type == "any_match":
        vals = _eval_jsonpath_all(body, path)
        if not vals:
            return False
        expected = a.get("expected")
        for v in vals:
            if json_type is not None and not _json_type_ok(v, json_type):
                continue
            if expected is not None:
                if v == expected or _decimal_eq(v, expected) or (isinstance(v, str) and str(expected) in v):
                    return True
            elif json_type is not None:
                return True
            elif v is not None:
                return True
        return False
    return _one_match_ok(actual, match_type, a, json_type)


def _assert_target(context: dict, default_body: Any, path: str):
    if isinstance(path, str):
        hm = re.match(r'^\$\.headers\.(.+)$', path)
        if hm:
            resp = context.get("last_response")
            hdrs = {str(k).lower(): v for k, v in (resp.headers.items() if resp and hasattr(resp, "headers") else [])}
            return {"__header__": hdrs.get(hm.group(1).lower())}, "$.__header__"
        m = re.match(r'^([A-Za-z_]\w*)\.(\$.*)$', path)
        if m and m.group(1) in context:
            obj = context[m.group(1)]
            jb = obj.json_body if hasattr(obj, "json_body") else obj
            return jb, m.group(2)
    return default_body, path


def p07_json_value_assert(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    resp: Optional[HTTPResponseLike] = context.get("last_response")
    body = resp.json_body if resp else None
    inputs = substitute_placeholders(inputs, context)
    assertions = inputs.get("assertions", [])
    header_assertions = inputs.get("header_assertions") or inputs.get("headers_assertions")
    header_results = []
    header_all_pass = True
    if header_assertions:
        _hdrs = {str(k).lower(): v for k, v in (resp.headers.items() if resp else [])}
        for ha in header_assertions:
            hname = str(ha.get("header", "")).lower()
            hval = _hdrs.get(hname)
            mt = ha.get("match_type", "contains")
            exp = ha.get("expected", ha.get("pattern", ha.get("value")))
            hok = False
            if hval is not None and exp is not None:
                if mt == "regex":
                    try:
                        hok = re.search(exp, str(hval)) is not None
                    except re.error:
                        hok = False
                elif mt == "equals":
                    hok = str(hval) == str(exp)
                else:
                    hok = str(exp).lower() in str(hval).lower()
            if not hok:
                header_all_pass = False
            header_results.append({"header": hname, "actual": hval, "expected": exp, "passed": hok})
    if not assertions:
        if header_assertions:
            return PrimitiveResult(
                passed=header_all_pass,
                data={"header_results": header_results},
                error=None if header_all_pass else f"header assertion(s) failed: {[h for h in header_results if not h['passed']]}",
                elapsed_ms=int((time.time() - t0) * 1000),
            )
        return PrimitiveResult(passed=False, error="last_response has no JSON body",
                               elapsed_ms=int((time.time() - t0) * 1000))
    if body is None:
        _all_header_paths = all(
            isinstance(a.get("path"), str) and a["path"].startswith("$.headers.")
            for a in assertions
        )
        if _all_header_paths and assertions:
            body = {}
        else:
            return PrimitiveResult(passed=False, error="last_response has no JSON body",
                                   elapsed_ms=int((time.time() - t0) * 1000))
    results = []
    all_pass = header_all_pass
    for a in assertions:
        path = a.get("path", "$")
        expected = a.get("expected")
        tolerance = a.get("tolerance")
        expected_present = a.get("expected_present")
        if expected_present is None:
            for alias in ("exists", "present", "is_present"):
                if alias in a:
                    expected_present = bool(a[alias])
                    break
        regex_pat = a.get("regex")
        predicate = a.get("predicate")
        value = a.get("value")
        match_type = a.get("match_type")
        json_type = a.get("type")
        equals_path = a.get("equals_path")
        lenient = a.get("lenient", a.get("loose", False))
        must_not_contain = a.get("must_not_contain")
        must_contain = a.get("must_contain")
        bound_max = a.get("max", a.get("tolerance_max"))
        bound_min = a.get("min", a.get("tolerance_min"))
        if isinstance(path, str) and path.endswith(".length"):
            parent_path = path[: -len(".length")]
            body_p, pp = _assert_target(context, body, parent_path)
            parent_val = _eval_jsonpath(body_p, pp)
            actual = len(parent_val) if isinstance(parent_val, (list, dict, str)) else None
        else:
            body_a, path_a = _assert_target(context, body, path)
            actual = _eval_jsonpath(body_a, path_a)
        if must_not_contain is not None:
            vals = actual if isinstance(actual, list) else ([actual] if actual is not None else [])
            ok = all(
                (must_not_contain != v) and not (isinstance(v, str) and str(must_not_contain) in v)
                for v in vals
            )
        elif must_contain is not None:
            vals = actual if isinstance(actual, list) else ([actual] if actual is not None else [])
            ok = any(
                (must_contain == v) or (isinstance(v, str) and str(must_contain) in v)
                for v in vals
            )
        elif bound_max is not None or bound_min is not None:
            try:
                num = float(actual) if not isinstance(actual, (list, dict)) else len(actual)
                ok = True
                if bound_max is not None:
                    ok = ok and num <= float(bound_max)
                if bound_min is not None:
                    ok = ok and num >= float(bound_min)
            except (TypeError, ValueError):
                ok = False
        elif equals_path is not None:
            body_b, path_b = _assert_target(context, body, equals_path)
            other = _eval_jsonpath(body_b, path_b)
            ok = other is not None and ((actual == other) or _decimal_eq(actual, other))
        elif match_type is not None:
            ok = _match_assert(body_a, path_a, actual, match_type, a, json_type)
        elif json_type is not None:
            ok = _json_type_ok(actual, json_type)
        elif expected_present is True:
            ok = actual is not None
        elif expected_present is False:
            ok = actual is None
        elif regex_pat is not None:
            ok = isinstance(actual, str) and re.search(regex_pat, actual) is not None
        elif predicate is not None:
            ok = _eval_predicate(actual, predicate, value)
        elif tolerance is not None:
            ok = _decimal_eq(actual, expected, tolerance)
        elif expected is None and "expected" not in a:
            ok = actual is not None
        elif expected is None:
            ok = actual is not None
        else:
            ok = (actual == expected) or _decimal_eq(actual, expected)
            if not ok and isinstance(expected, str) and isinstance(actual, str):
                if lenient or actual.startswith(expected) or expected in actual:
                    ok = True
            if not ok and isinstance(actual, (int, float)) and isinstance(expected, str):
                try:
                    if float(actual) == float(expected):
                        ok = True
                except (ValueError, TypeError):
                    pass
            if not ok and isinstance(actual, str) and isinstance(expected, (int, float)):
                try:
                    if float(actual) == float(expected):
                        ok = True
                except (ValueError, TypeError):
                    pass
        if not ok and a.get("optional") and actual is None and match_type != "any_match":
            ok = True
        if not ok:
            all_pass = False
        capture_key = a.get("save_as") or a.get("capture_as") or a.get("store_as")
        if capture_key and actual is not None:
            context[capture_key] = actual
        results.append({"path": path, "actual": actual, "expected": expected,
                        "predicate": predicate, "value": value, "passed": ok})
    _failed = [r for r in results if not r["passed"]] + [h for h in header_results if not h["passed"]]
    return PrimitiveResult(
        passed=all_pass,
        data={"all_passed": all_pass, "results": results, "header_results": header_results},
        error=None if all_pass else f"assertion(s) failed: {_failed[:5]}",
        elapsed_ms=int((time.time() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p08_db_query(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs = substitute_placeholders(inputs, context)
    sql = inputs.get("sql", "")
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, context)
    except Exception:
        pass
    expected = inputs.get("expected_result")
    expected_min_rows = inputs.get("expected_min_rows")
    params = []
    def _sub(m):
        k = m.group(1)
        v = context.get(k)
        params.append(v)
        return "%s"
    _has_ph = bool(re.search(r"\{\{\w+\}\}", sql))
    if _has_ph:
        sql_escaped = sql.replace("%", "%%")
        sql_pf = re.sub(r"\{\{(\w+)\}\}", _sub, sql_escaped)
    else:
        sql_pf = sql
    _is_dml = re.match(r"^\s*(INSERT|UPDATE|DELETE|REPLACE)\b", sql, re.IGNORECASE) is not None
    if _is_dml:
        _rc = db_execute_rowcount(sql_pf, tuple(params) if _has_ph else None)
        _affected = _rc if _rc is not None else 0
        rows = [{"rows_affected": _affected}]
    elif _has_ph:
        rows = db_query(sql_pf, tuple(params))
    else:
        rows = db_query(sql)
    _save_key = inputs.get("save_first_row_as") or inputs.get("save_row_as")
    if _save_key and rows:
        context[_save_key] = rows[0]
    if expected is not None and isinstance(expected, dict):
        if not rows:
            return PrimitiveResult(passed=False, data={"rows": rows, "match": False},
                                   error="no rows returned", elapsed_ms=int((time.time() - t0) * 1000))
        row0 = rows[0]
        ok = all(_decimal_eq(row0.get(k), v) or row0.get(k) == v for k, v in expected.items())
        return PrimitiveResult(passed=ok, data={"rows": rows[:5], "row_count": len(rows), "match": ok},
                               elapsed_ms=int((time.time() - t0) * 1000),
                               error=None if ok else f"row mismatch: {row0} vs {expected}")
    if expected_min_rows is not None:
        return PrimitiveResult(passed=len(rows) >= expected_min_rows,
                               data={"rows": rows[:5], "row_count": len(rows)},
                               elapsed_ms=int((time.time() - t0) * 1000))
    predicates = inputs.get("expected_predicates")
    if predicates:
        if not rows:
            return PrimitiveResult(passed=False,
                                   data={"rows": rows, "row_count": 0},
                                   error="no rows returned for expected_predicates",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        row0 = rows[0]
        checks = []
        all_ok = True
        for p in predicates:
            field = p.get("field")
            op = p.get("op", p.get("operator", p.get("predicate", "eq")))
            val = p.get("value")
            actual = row0.get(field)
            ok = _p08_predicate_ok(actual, op, val)
            if not ok:
                all_ok = False
            checks.append({"field": field, "op": op, "value": val,
                           "actual": actual, "passed": ok})
        return PrimitiveResult(
            passed=all_ok,
            data={"rows": rows[:5], "row_count": len(rows), "predicate_checks": checks},
            elapsed_ms=int((time.time() - t0) * 1000),
            error=None if all_ok else f"predicate failures: {[c for c in checks if not c['passed']]}")
    first_row_exp = inputs.get("expected_first_row")
    add_asserts = inputs.get("additional_assertions") or []
    if first_row_exp is not None or add_asserts:
        if not rows:
            return PrimitiveResult(passed=False, data={"rows": rows, "row_count": 0},
                                   error="no rows returned for expected_first_row",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        row0 = rows[0]
        checks = []
        all_ok = True
        for k, v in (first_row_exp or {}).items():
            ok = _decimal_eq(row0.get(k), v) or row0.get(k) == v
            all_ok = all_ok and ok
            checks.append({"field": k, "expected": v, "actual": row0.get(k), "passed": ok})
        for aa in add_asserts:
            field = aa.get("field")
            mt = aa.get("match_type", "equals")
            actual = row0.get(field)
            ok = _one_match_ok(actual, mt, aa, None)
            all_ok = all_ok and ok
            checks.append({"field": field, "match_type": mt, "actual": actual, "passed": ok})
        return PrimitiveResult(passed=all_ok,
                               data={"rows": rows[:5], "row_count": len(rows), "checks": checks},
                               elapsed_ms=int((time.time() - t0) * 1000),
                               error=None if all_ok else f"first_row checks failed: {[c for c in checks if not c['passed']]}")
    expected_min = inputs.get("expected_min")
    if expected_min is not None:
        if not rows:
            return PrimitiveResult(passed=False, data={"rows": rows, "row_count": 0},
                                   error="no rows returned for expected_min",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        row0 = rows[0]
        checks = []
        all_ok = True
        for k, v in expected_min.items():
            try:
                ok = float(row0.get(k)) >= float(v)
            except (ValueError, TypeError):
                ok = False
            all_ok = all_ok and ok
            checks.append({"field": k, "min": v, "actual": row0.get(k), "passed": ok})
        return PrimitiveResult(passed=all_ok,
                               data={"rows": rows[:5], "row_count": len(rows), "checks": checks},
                               elapsed_ms=int((time.time() - t0) * 1000),
                               error=None if all_ok else f"expected_min failed: {[c for c in checks if not c['passed']]}")
    return PrimitiveResult(passed=True, data={"rows": rows[:10], "row_count": len(rows)},
                           elapsed_ms=int((time.time() - t0) * 1000))


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p09_db_table_exists(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    tables = inputs.get("tables", [])
    if not tables:
        return PrimitiveResult(passed=True, data={"existing": [], "missing": []})
    placeholders = ",".join(["%s"] * len(tables))
    sql = (f"SELECT table_name AS t FROM information_schema.tables "
           f"WHERE table_schema=%s AND table_name IN ({placeholders})")
    rows = db_query(sql, (config.DB_NAME, *tables))
    existing = [r["t"] for r in rows]
    missing = [t for t in tables if t not in existing]
    return PrimitiveResult(
        passed=not missing,
        data={"existing": existing, "missing": missing,
              "found_count": len(existing), "total_count": len(tables)},
        elapsed_ms=int((time.time() - t0) * 1000),
        error=None if not missing else f"missing tables: {missing[:5]}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p10_db_column_check(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    table = inputs.get("table", "")
    expected = inputs.get("expected_columns", [])
    sql = ("SELECT column_name AS c FROM information_schema.columns "
           "WHERE table_schema=%s AND table_name=%s")
    rows = db_query(sql, (config.DB_NAME, table))
    actual = [r["c"] for r in rows]
    found = [c for c in expected if c in actual]
    missing = [c for c in expected if c not in actual]
    return PrimitiveResult(
        passed=not missing,
        data={"existing": found, "missing": missing,
              "found_count": len(found), "total_count": len(expected),
              "all_actual_columns": actual[:50]},
        elapsed_ms=int((time.time() - t0) * 1000),
        error=None if not missing else f"missing columns in {table}: {missing[:5]}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p11_db_index_check(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    table = inputs.get("table", "")
    expected = inputs.get("expected_indexes", [])
    sql = ("SELECT index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS cols "
           "FROM information_schema.statistics WHERE table_schema=%s AND table_name=%s "
           "GROUP BY index_name")
    rows = db_query(sql, (config.DB_NAME, table))
    def _ci(d, *keys):
        if not isinstance(d, dict):
            return None
        for k in keys:
            if k in d:
                return d[k]
            kl = k.lower()
            for k2 in d:
                if k2.lower() == kl:
                    return d[k2]
        return None

    actual_index_sets = [tuple((_ci(r, "cols") or "").split(",")) for r in rows]
    matched = []
    missing = []
    for ix in expected:
        cols = tuple(ix.get("columns", []))
        if cols in actual_index_sets:
            matched.append(list(cols))
        else:
            missing.append(list(cols))
    return PrimitiveResult(
        passed=not missing,
        data={"matched": matched, "missing": missing,
              "all_actual_indexes": [{"index": _ci(r, "index_name"), "columns": _ci(r, "cols")} for r in rows[:20]]},
        elapsed_ms=int((time.time() - t0) * 1000),
        error=None if not missing else f"missing indexes on {table}: {missing[:5]}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p12_docker_exec(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    container_raw = inputs.get("container") or config.APP_CONTAINER
    container = substitute_placeholders(container_raw, context)
    if container in ("{{app_container}}", "{{APP_CONTAINER}}", ""):
        container = config.APP_CONTAINER
    command = substitute_placeholders(inputs.get("command", "echo ok"), context)
    expect_success = inputs.get("expect_success", True)
    expect_contains = inputs.get("expect_output_contains")
    rc, stdout, stderr = docker_exec(container=container, command=command)
    success = (rc == 0) if expect_success else True
    contains_ok = (expect_contains in stdout) if expect_contains else True
    passed = success and contains_ok
    return PrimitiveResult(
        passed=passed,
        data={"return_code": rc, "stdout": stdout[:1500], "stderr": stderr[:500],
              "command": command[:200], "container": container},
        elapsed_ms=int((time.time() - t0) * 1000),
        error=None if passed else f"docker exec failed (rc={rc}): {stderr[:200]}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


_PW_CLIENT_CACHE: Optional[tuple] = None


def _resolve_password_client() -> tuple:
    global _PW_CLIENT_CACHE
    if _PW_CLIENT_CACHE is not None:
        return _PW_CLIENT_CACHE
    cid, secret = config.PASSPORT_CLIENT_ID, config.PASSPORT_CLIENT_SECRET
    try:
        rows = db_query(
            "SELECT id, secret FROM oauth_clients "
            "WHERE password_client=1 AND revoked=0 ORDER BY id LIMIT 1"
        )
        if rows:
            cid = str(rows[0]["id"])
            secret = rows[0]["secret"]
    except Exception as e:
        logger.warning("password-grant client DB lookup failed, using config: %s", e)
    _PW_CLIENT_CACHE = (cid, secret)
    return _PW_CLIENT_CACHE


def _try_password_grant(email: str, password: str) -> Optional[str]:
    if requests is None:
        return None
    client_id, client_secret = _resolve_password_client()
    payload = {
        "grant_type": "password",
        "username": email,
        "password": password,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "*",
    }
    try:
        resp = requests.post(
            f"{config.APP_BASE_URL}/oauth/token",
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("access_token")
    except Exception:
        return None


def _try_db_create_pat(email: str, role: str) -> Optional[str]:
    if pymysql is None:
        return None
    try:
        conn = db_conn()
    except Exception:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email=%s LIMIT 1", (email,))
            row = cur.fetchone()
            if not row:
                return None
            user_id = row["id"]
            token_id = secrets.token_hex(40)
            cur.execute(
                "DELETE FROM oauth_access_tokens WHERE user_id=%s AND name=%s",
                (user_id, f"eval_{role}"),
            )
            conn.commit()
            client_id_for_token = int(config.PASSPORT_CLIENT_ID) if str(config.PASSPORT_CLIENT_ID).isdigit() else 1
            cur.execute(
                "INSERT INTO oauth_access_tokens "
                "(id, user_id, client_id, name, scopes, revoked, created_at, updated_at, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY))",
                (token_id, user_id, client_id_for_token, f"eval_{role}", "[]", 0),
            )
            conn.commit()
        return token_id
    except Exception as e:
        logger.warning("DB-direct token creation failed: %s", e)
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def p13_auth_login(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    role = inputs.get("role", "admin")
    method = inputs.get("method", "password_grant")

    cache: dict = context.setdefault("token_cache", {})

    if role != "admin" and role in cache and cache[role]:
        context["auth_token"] = cache[role]
        context["auth_role"] = role
        return PrimitiveResult(
            passed=True, data={"role": role, "token_len": len(cache[role]), "source": "cache"},
            elapsed_ms=int((time.time() - t0) * 1000),
        )

    creds = (context.get("rbac_users") or config.RBAC_USERS).get(role)
    if not creds:
        return PrimitiveResult(passed=False, error=f"unknown role: {role}",
                               elapsed_ms=int((time.time() - t0) * 1000))

    email, password = creds["email"], creds["password"]
    token: Optional[str] = None
    source = "none"

    if method in ("password_grant", "auto", "api_token"):
        token = _try_password_grant(email, password)
        if token:
            source = "password_grant"

    if not token and config.P13_ALLOW_DB_TOKEN_FALLBACK:
        token = _try_db_create_pat(email, role)
        if token:
            verify = http_request("GET", f"{config.APP_BASE_URL}/api/v1/about",
                                  headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
            if verify.status_code == 200:
                source = "db_create_token"
            else:
                logger.warning("DB-direct token failed verify (status %d) for %s", verify.status_code, email)
                token = None

    if not token:
        try:
            role_title = role[5:] if role.startswith("rbac_") else role
            if role_title in ("alice",):
                args_role = "_NONE_"
            else:
                args_role = role_title
            cmd = (
                f"cd /var/www/html && php _make_rbac_user.php "
                f"{email} {args_role} admin@pfm.local '{password}'"
            )
            rc, out, err = docker_exec(container=config.APP_CONTAINER, command=cmd, timeout=20)
            if rc == 0:
                token = _try_password_grant(email, password)
                if token:
                    source = "auto_provision_then_password_grant"
        except Exception as e:
            logger.warning("P13 auto-provision failed: %s", e)

    if not token:
        return PrimitiveResult(
            passed=False,
            error=f"All P13 methods failed for role={role} email={email}. "
                  f"Check that the user exists, OAuth client_id/secret are set, "
                  f"and /oauth/token is reachable.",
            elapsed_ms=int((time.time() - t0) * 1000),
        )

    cache[role] = token
    context["auth_token"] = token
    context["auth_role"] = role
    if role == "admin":
        context["admin_token"] = token
        context["admin_pat"] = token
    context[f"rbac_{role}_token"] = token
    context[f"{role}_token"] = token
    return PrimitiveResult(
        passed=True,
        data={"role": role, "token_len": len(token), "source": source, "email": email},
        elapsed_ms=int((time.time() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p14_permission_check(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs = substitute_placeholders(inputs, context)
    action = inputs.get("action", "")
    expected_result = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status")
    body = inputs.get("body")
    parts = action.strip().split(" ", 1)
    if len(parts) != 2:
        return PrimitiveResult(passed=False, error=f"bad action: {action}",
                               elapsed_ms=int((time.time() - t0) * 1000))
    method, path = parts
    headers = dict(config.DEFAULT_API_HEADERS)
    if context.get("auth_token"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    resp = http_request(method, _wrap_url(path), headers=headers,
                        json_body=body if isinstance(body, (dict, list)) else None)
    context["last_response"] = resp

    sc = resp.status_code
    DENIAL_STATUSES = (401, 403, 404, 410, 422)
    SUCCESS_STATUSES = (200, 201, 202, 204)
    if expected_result == "denied":
        ok = sc in DENIAL_STATUSES
        if expected_status is not None and ok:
            ok = (sc == expected_status) or (sc in DENIAL_STATUSES and expected_status in DENIAL_STATUSES)
    else:
        ok = sc in SUCCESS_STATUSES
        if expected_status is not None:
            ok = sc == expected_status or (sc in SUCCESS_STATUSES and expected_status in SUCCESS_STATUSES)

    return PrimitiveResult(
        passed=ok,
        data={"status_code": sc, "action": action, "expected_result": expected_result, "method_used": method},
        elapsed_ms=int((time.time() - t0) * 1000),
        error=None if ok else f"expected {expected_result} (status~{expected_status}); got {sc}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p15_status_code_assert(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    resp: Optional[HTTPResponseLike] = context.get("last_response")
    if resp is None:
        return PrimitiveResult(passed=False, error="no last_response in context",
                               elapsed_ms=int((time.time() - t0) * 1000))
    expected = inputs.get("expected_status")
    accept = inputs.get("acceptable_statuses")
    strict = inputs.get("strict", False)

    FAMILY = [
        {200, 201, 202, 204},
        {301, 302, 303, 307, 308},
        {400, 401, 403, 404, 410, 422, 429},
        {500, 502, 503, 504},
    ]

    def _equiv(actual: int, target: int) -> bool:
        if actual == target:
            return True
        if strict:
            return False
        for fam in FAMILY:
            if actual in fam and target in fam:
                return True
        return False

    actual = resp.status_code
    if accept is not None:
        if strict:
            ok = actual in accept
        else:
            ok = any(_equiv(actual, t) for t in accept)
        msg = (f"status {actual} not in {accept}" + (" (lenient family check also failed)" if not strict else "")) if not ok else None
    elif expected is not None:
        ok = _equiv(actual, expected)
        msg = f"status {actual} != expected {expected}" if not ok else None
    else:
        ok = 200 <= actual < 400
        msg = f"status {actual} not 2xx/3xx" if not ok else None
    return PrimitiveResult(
        passed=ok,
        data={"status_code": actual, "expected": expected or accept, "strict": strict},
        elapsed_ms=int((time.time() - t0) * 1000),
        error=msg,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p16_response_time_check(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    resp: Optional[HTTPResponseLike] = context.get("last_response")
    if resp is None:
        return PrimitiveResult(passed=False, error="no last_response in context",
                               elapsed_ms=int((time.time() - t0) * 1000))
    max_ms = inputs.get("max_ms", 1000)
    ok = resp.elapsed_ms <= max_ms
    return PrimitiveResult(
        passed=ok,
        data={"elapsed_ms": resp.elapsed_ms, "max_ms": max_ms},
        elapsed_ms=int((time.time() - t0) * 1000),
        error=None if ok else f"too slow: {resp.elapsed_ms}ms > {max_ms}ms",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


_CODE_EXTS = {".php", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue",
              ".svelte", ".py", ".rb", ".erb", ".go", ".rs", ".java", ".kt",
              ".cs", ".ex", ".exs", ".blade", ".sql"}
_SKIP_DIR = ("/node_modules/", "/vendor/", "/dist/", "/build/", "/.git/",
             "/__pycache__/", "/storage/", "/bootstrap/cache/", "/tests/",
             "/test/", "/lang/", "/public/js/", "/public/css/")
_RUBRIC_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent does "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling whether well overall".split())


def _rank_fs_files(workspace_dir, files_to_sample, rubric, max_files=14):
    ws = Path(workspace_dir)
    entries = [e for e in (files_to_sample or []) if isinstance(e, str) and e]
    cands = set()
    for ent in entries:
        p = ws / ent
        try:
            if p.is_dir():
                for fp in p.rglob("*"):
                    if fp.is_file() and fp.suffix.lower() in _CODE_EXTS:
                        cands.add(fp)
            elif p.is_file():
                cands.add(p)
            else:
                stem = ent.rstrip("/")
                for fp in (list(ws.glob(ent))[:40]
                           or list(ws.glob(f"**/{ent}"))[:40]
                           or list(ws.glob(stem + "*"))[:40]):
                    if fp.is_file():
                        cands.add(fp)
                    elif fp.is_dir():
                        for q in fp.rglob("*"):
                            if q.is_file() and q.suffix.lower() in _CODE_EXTS:
                                cands.add(q)
        except Exception:
            pass
    mentioned = {m.split("/")[-1].lower()
                 for m in re.findall(r"[\w./*-]+\.\w{1,5}", rubric or "")}
    pathwords = set()
    for p in re.findall(r"(?:app|src|lib|resources|routes)/[\w./*-]+", rubric or ""):
        for seg in re.split(r"[/.*]", p):
            if len(seg) >= 4:
                pathwords.add(seg.lower())
    kws = {}
    for t in re.findall(r"[A-Za-z_]{3,}", (rubric or "").lower()):
        if t not in _RUBRIC_STOP:
            kws[t] = kws.get(t, 0) + 1
    scored = []
    for fp in cands:
        try:
            rel = str(fp.relative_to(ws))
        except Exception:
            rel = str(fp)
        low = rel.lower()
        if any(s in "/" + low for s in _SKIP_DIR):
            continue
        base = fp.name.lower()
        sc = 0.0
        for m in mentioned:
            if m and (m == base or low.endswith(m)):
                sc += 50
        for w in pathwords:
            if w in low:
                sc += 6
        for w in kws:
            if w in low:
                sc += 3
        sc += 2.0 if fp.suffix.lower() in _CODE_EXTS else 0.0
        if "test" in base:
            sc -= 4.0
        parts = rel.split("/")
        strat = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
        scored.append((sc, strat, rel, fp))
    scored.sort(key=lambda x: (-x[0], x[2]))
    groups, order = {}, []
    for sc, strat, rel, fp in scored:
        if strat not in groups:
            groups[strat] = []
            order.append(strat)
        groups[strat].append((rel, fp))
    picked = []
    while len(picked) < max_files and any(groups[k] for k in order):
        for k in order:
            if groups[k]:
                picked.append(groups[k].pop(0))
                if len(picked) >= max_files:
                    break
    return picked


def p17_llm_judge(inputs: dict, context: dict) -> PrimitiveResult:
    from ._llm_judge_safe import safe_chat_completion

    t0 = time.time()
    score_range = inputs.get("score_range", [0, 10])

    rubric = inputs.get("rubric_prompt", "Score this evidence on a 0-10 scale.")
    evidence_type = inputs.get("evidence_type", "code_files")
    evidence_text = ""

    if evidence_type == "code_files":
        files_to_sample = inputs.get("files_to_sample", [])
        snippets = []
        for rel, child in _rank_fs_files(config.WORKSPACE_DIR, files_to_sample,
                                         rubric, max_files=14):
            try:
                snippets.append(f"=== {rel} ===\n"
                                + child.read_text(encoding="utf-8", errors="replace")[:3000])
            except Exception:
                pass
        evidence_text = "\n\n".join(snippets)[:40000]
    elif evidence_type in ("http_response_html", "http_response_json"):
        resp = context.get("last_response")
        if resp:
            evidence_text = (resp.text or "")[:30000]
    else:
        evidence_text = json.dumps(context.get("last_evidence", {}), default=str)[:30000]

    if not evidence_text:
        return PrimitiveResult(passed=False, data={"score": 0, "score_range": score_range},
                               error="no evidence collected for llm_judge",
                               elapsed_ms=int((time.time() - t0) * 1000))

    system_msg = (
        "You are a strict but fair code/UI quality reviewer. "
        f"Respond with ONLY a single JSON object {{\"score\": <int {score_range[0]}-{score_range[1]}>, "
        "\"reasoning\": \"<one short sentence>\"}} and NOTHING else — no preamble before the JSON."
    )
    user_msg = f"## Rubric\n{rubric}\n\n## Evidence\n{evidence_text}"

    def _parse_verdict(text: str):
        m_json = re.search(r"\{[^{}]*?\"score\"\s*:\s*(\d+(?:\.\d+)?)[^{}]*\}", text, re.IGNORECASE | re.DOTALL)
        if m_json:
            _reason = ""
            try:
                start = text.find("{", text.find("score") - 200) if "score" in text.lower() else -1
                if start >= 0:
                    parsed = json.loads(text[start:text.rfind("}") + 1])
                    if isinstance(parsed, dict) and isinstance(parsed.get("reasoning"), str):
                        _reason = parsed["reasoning"][:500]
            except Exception:
                pass
            return float(m_json.group(1)), _reason
        m = re.search(r'["\']?SCORE["\']?\s*:\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if m:
            _reason = ""
            if "REASONING:" in text:
                _reason = text.split("REASONING:", 1)[-1].strip()[:500]
            return float(m.group(1)), _reason
        return None, ""

    score = None
    reasoning = ""
    last_text = ""
    for _attempt in range(3):
        res = safe_chat_completion(
            messages=[{"role": "system", "content": system_msg},
                      {"role": "user", "content": user_msg}],
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE,
            temperature=config.LLM_TEMPERATURE,
            timeout=float(config.LLM_TIMEOUT_SECONDS),
            max_tokens=2000,
        )
        last_text = res.raw or ""
        _sv, _rs = _parse_verdict(last_text)
        if _sv is not None:
            score = max(score_range[0], min(score_range[1], _sv))
            reasoning = _rs or last_text.strip()[:500]
            break

    if score is None:
        _infra = bool(getattr(res, "skipped", False))
        return PrimitiveResult(
            passed=False,
            data={"score": 0, "skipped": True, "llm_api_failure": _infra,
                  "parse_failure": not _infra,
                  "reason": "LLM judge unavailable: no verdict after retries",
                  "raw": last_text[:200], "score_range": score_range},
            error="LLM judge SKIPPED (unavailable after retries)",
            elapsed_ms=int((time.time() - t0) * 1000),
        )

    return PrimitiveResult(
        passed=score > 0,
        data={"score": score, "score_range": score_range, "reasoning": reasoning, "raw_response": last_text[:500]},
        elapsed_ms=int((time.time() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _not_impl(name: str) -> PrimitiveResult:
    return PrimitiveResult(passed=False, error=f"{name} not implemented in this evaluator build")


def p18_browser_interaction(inputs: dict, context: dict) -> PrimitiveResult:
    if config.SKIP_BROWSER_TESTS:
        return _not_impl("p18_browser_interaction (skipped via SKIP_BROWSER_TESTS)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _not_impl("p18_browser_interaction (playwright not installed)")
    t0 = time.time()
    steps = inputs.get("steps", [])
    out = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(base_url=config.APP_BASE_URL)
            page = ctx.new_page()
            for step in steps:
                act = step.get("action")
                if act == "goto":
                    page.goto(step["url"])
                elif act == "fill":
                    page.fill(step["selector"], step["value"])
                elif act == "click":
                    page.click(step["selector"])
                elif act == "wait":
                    page.wait_for_timeout(step.get("ms", 1000))
                out.append({"action": act, "ok": True})
            browser.close()
        return PrimitiveResult(passed=True, data={"steps": out},
                               elapsed_ms=int((time.time() - t0) * 1000))
    except Exception as e:
        return PrimitiveResult(passed=False, error=str(e)[:300],
                               elapsed_ms=int((time.time() - t0) * 1000))


_WEB_SESSION_CACHE: Any = None


def _web_login_session():
    global _WEB_SESSION_CACHE
    if _WEB_SESSION_CACHE is not None:
        return _WEB_SESSION_CACHE
    if requests is None:
        return None
    try:
        s = requests.Session()
        r = s.get(f"{config.APP_BASE_URL}/login", timeout=config.HTTP_TIMEOUT)
        m = re.search(r'name="_token"[^>]*value="([^"]*)"', r.text or "")
        token = m.group(1) if m else ""
        s.post(f"{config.APP_BASE_URL}/login",
               data={"_token": token, "email": config.ADMIN_EMAIL,
                     "password": config.ADMIN_PASSWORD, "remember": "0"},
               timeout=config.HTTP_TIMEOUT, allow_redirects=True)
        _WEB_SESSION_CACHE = s
        return s
    except Exception as e:
        logger.warning("web login session failed: %s", e)
        return None


def p19_dom_assertion(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs = substitute_placeholders(inputs, context)
    url = _wrap_url(inputs.get("url", "/"))
    text = ""
    resp = None
    _is_api = "/api/" in url
    _sess = None if _is_api else _web_login_session()
    if _sess is not None:
        try:
            r = _sess.get(url, headers={"Accept": "text/html"}, timeout=config.HTTP_TIMEOUT)
            text = r.text or ""
        except Exception:
            text = ""
    else:
        headers = {"Accept": "text/html"}
        if context.get("auth_token"):
            headers["Authorization"] = f"Bearer {context['auth_token']}"
        resp = http_request("GET", url, headers=headers)
        text = resp.text or ""
    low = text.lower()

    def _class_present(cls: str) -> bool:
        cls = cls.lower()
        for m in re.finditer(r'class=["\']([^"\']*)["\']', low):
            if cls in m.group(1).split():
                return True
        return False

    def _one_selector_present(sel: str) -> bool:
        sel = sel.strip()
        if not sel:
            return False
        token = sel.split()[-1]
        tag = None
        classes: list = []
        ident = None
        m = re.match(r'([a-zA-Z0-9]+)?(.*)', token)
        tag = m.group(1)
        rest = m.group(2)
        for part in re.findall(r'([.#][\w-]+)', rest):
            if part.startswith('.'):
                classes.append(part[1:])
            elif part.startswith('#'):
                ident = part[1:]
        ok = True
        if tag:
            ok = ok and (("<" + tag.lower()) in low)
        for c in classes:
            ok = ok and _class_present(c)
        if ident:
            ok = ok and (('id="' + ident.lower()) in low or ("id='" + ident.lower()) in low)
        return ok

    def _selector_present(sel: str) -> bool:
        return any(_one_selector_present(s) for s in sel.split(","))

    assertions = inputs.get("assertions", [])
    results = []
    all_ok = True
    for a in assertions:
        sel = a.get("selector", "")
        present = _selector_present(sel) if sel else True
        ok_present = a.get("shouldExist", True) == present
        if "textContains" in a:
            ok_text = a["textContains"].lower() in low
            ok_present = ok_present and ok_text
        if not ok_present:
            all_ok = False
        results.append({"selector": sel, "passed": ok_present})
    return PrimitiveResult(passed=all_ok, data={"results": results, "url": url},
                           elapsed_ms=int((time.time() - t0) * 1000))


def p20_network_fault_inject(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    try:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return _not_impl("p20_network_fault_inject (playwright missing)")
        intercept = inputs.get("intercept") or {}
        then = inputs.get("then") or {}
        steps = then.get("steps") or []
        log = []
        passed_all = True
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(ignore_https_errors=True)
            page = ctx.new_page()
            try:
                pat = intercept.get("url_pattern", "**")
                stat = int(intercept.get("status", 503))
                page.route(pat, lambda r, _req: r.fulfill(status=stat, body=intercept.get("body", "")))
            except Exception:
                pass
            for step in steps:
                a = (step.get("action") or "").lower()
                try:
                    if a == "goto":
                        url = step.get("url") or "/"
                        if not url.startswith("http"):
                            url = config.APP_BASE_URL + (url if url.startswith("/") else "/" + url)
                        page.goto(url, timeout=int(step.get("timeout", 15000)))
                        log.append({"action": a, "ok": True, "url": url})
                    elif a == "click":
                        page.click(step["selector"], timeout=int(step.get("timeout", 5000)))
                        log.append({"action": a, "ok": True})
                    elif a == "wait":
                        page.wait_for_timeout(int(step.get("ms", 1000)))
                        log.append({"action": a, "ok": True})
                    elif a == "assert_text_visible":
                        sel = step.get("selector") or "body"
                        text = str(step.get("text") or "")
                        body_text = page.text_content(sel) or ""
                        ok = text in body_text
                        log.append({"action": a, "ok": ok})
                        passed_all = passed_all and ok
                    else:
                        log.append({"action": a, "ok": False, "error": "unknown"})
                        passed_all = False
                except Exception as e:
                    log.append({"action": a, "ok": False, "error": str(e)})
                    passed_all = False
            ctx.close()
            browser.close()
        return PrimitiveResult(passed=passed_all,
                               data={"steps": log, "intercept": intercept},
                               elapsed_ms=int((time.time() - t0) * 1000))
    except Exception as e:
        return PrimitiveResult(passed=False, error=f"P20 unhandled: {e}",
                               elapsed_ms=int((time.time() - t0) * 1000))


def p21_websocket_connect(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    try:
        try:
            import websocket as _ws
        except ImportError:
            return _not_impl("p21_websocket_connect (websocket-client missing)")
        inputs = substitute_placeholders(inputs, context)
        url = inputs.get("url")
        if not url:
            return PrimitiveResult(passed=False, error="missing url",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        subscribe = inputs.get("subscribe")
        send_msg = inputs.get("send")
        expect = inputs.get("expect_message") or {}
        timeout_ms = int(expect.get("timeout_ms", inputs.get("timeout_ms", 5000)))
        match = expect.get("match") or {}
        headers = []
        token = inputs.get("auth_token") or context.get("auth_token")
        if token:
            headers.append(f"Authorization: Bearer {token}")
        ws = _ws.create_connection(str(url), header=headers,
                                   timeout=max(2, timeout_ms / 1000.0))
        if subscribe:
            ws.send(json.dumps({"command": "subscribe", "identifier": json.dumps(subscribe)}))
        if send_msg:
            ws.send(json.dumps(send_msg) if isinstance(send_msg, dict) else str(send_msg))
        ws.settimeout(max(0.5, timeout_ms / 1000.0))
        deadline = time.time() + (timeout_ms / 1000.0)
        messages = []
        matched = False
        while time.time() < deadline:
            try:
                raw = ws.recv()
            except Exception:
                break
            if raw is None:
                break
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            messages.append(parsed if isinstance(parsed, (dict, list, str)) else str(parsed))
            ok = True
            if "type" in match:
                ok = ok and isinstance(parsed, dict) and parsed.get("type") == match["type"]
            if "content_contains" in match:
                ok = ok and str(match["content_contains"]) in json.dumps(parsed, ensure_ascii=False)
            if ok:
                matched = True
                break
        try:
            ws.close()
        except Exception:
            pass
        passed = matched if expect else True
        return PrimitiveResult(passed=passed,
                               data={"connected": True, "subscribed": bool(subscribe),
                                     "messages_received": messages[:10],
                                     "matched": matched},
                               elapsed_ms=int((time.time() - t0) * 1000))
    except Exception as e:
        return PrimitiveResult(passed=False, error=f"P21 unhandled: {e}",
                               elapsed_ms=int((time.time() - t0) * 1000))


def p22_graphql_query(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    try:
        if requests is None:
            return _not_impl("p22_graphql_query (requests missing)")
        inputs = substitute_placeholders(inputs, context)
        endpoint = inputs.get("endpoint") or inputs.get("path") or "/graphql"
        query = inputs.get("query") or ""
        variables = inputs.get("variables") or {}
        token = inputs.get("token") or context.get("auth_token")
        expect_no_errors = bool(inputs.get("expect_no_errors", True))
        if not query:
            return PrimitiveResult(passed=False, error="missing query",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        rs = http_request("POST", _wrap_url(endpoint), headers=headers,
                          json_body={"query": query, "variables": variables},
                          timeout=config.HTTP_TIMEOUT)
        body = rs.json_body if isinstance(rs.json_body, dict) else {}
        data = body.get("data")
        errors = body.get("errors")
        passed = (rs.status_code == 200 and (not expect_no_errors or not errors)
                  and data is not None)
        context["last_response"] = rs
        return PrimitiveResult(passed=passed,
                               data={"status_code": rs.status_code, "data": data,
                                     "errors": errors,
                                     "response_time_ms": rs.elapsed_ms},
                               elapsed_ms=int((time.time() - t0) * 1000))
    except Exception as e:
        return PrimitiveResult(passed=False, error=f"P22 unhandled: {e}",
                               elapsed_ms=int((time.time() - t0) * 1000))


def p23_file_upload_download(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs = substitute_placeholders(inputs, context)
    upload = inputs.get("upload", {})
    if not upload:
        return _not_impl("p23_file_upload_download (no upload spec)")
    url = _wrap_url(upload.get("path", "/api/v1/attachments"))
    headers = {}
    if context.get("auth_token"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    body_b64 = upload.get("file_content", "base64:SGVsbG8=").replace("base64:", "", 1)
    import base64
    body_bytes = base64.b64decode(body_b64)
    if requests is None:
        return _not_impl("p23 (requests missing)")
    files = {upload.get("field_name", "file"): (upload.get("file_name", "test.bin"),
                                                  body_bytes,
                                                  upload.get("content_type", "application/octet-stream"))}
    try:
        r = requests.post(url, headers=headers, files=files, timeout=config.HTTP_TIMEOUT)
        upload_ok = r.status_code in (200, 201)
    except Exception as e:
        return PrimitiveResult(passed=False, error=str(e), elapsed_ms=int((time.time() - t0) * 1000))
    return PrimitiveResult(passed=upload_ok,
                           data={"upload_status": r.status_code, "body": r.text[:500]},
                           elapsed_ms=int((time.time() - t0) * 1000))


def p24_queue_job_check(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs = substitute_placeholders(inputs, context)
    trig = inputs.get("trigger", {})
    if trig.get("type") == "http":
        headers = dict(config.DEFAULT_API_HEADERS)
        if context.get("auth_token"):
            headers["Authorization"] = f"Bearer {context['auth_token']}"
        http_request(trig.get("method", "POST"), _wrap_url(trig.get("path", "/")),
                     headers=headers, json_body=trig.get("body"))
    verify = inputs.get("verify", {})
    max_wait = (verify.get("max_wait_ms") or 10000) / 1000
    interval = (verify.get("poll_interval_ms") or 2000) / 1000
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        if verify.get("strategy") == "db_query":
            rows = db_query(verify.get("sql", ""), tuple())
            last = rows
            if rows and verify.get("expected_result"):
                expected = verify["expected_result"]
                if all(rows[0].get(k) == v for k, v in expected.items()):
                    return PrimitiveResult(passed=True, data={"rows": rows[:3]},
                                           elapsed_ms=int((time.time() - t0) * 1000))
        time.sleep(interval)
    return PrimitiveResult(passed=False, data={"last": last},
                           error="queue job did not complete in time",
                           elapsed_ms=int((time.time() - t0) * 1000))


def p25_oauth_oidc_flow(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    try:
        if requests is None:
            return _not_impl("p25_oauth_oidc_flow (requests missing)")
        inputs = substitute_placeholders(inputs, context)
        flow = (inputs.get("flow") or "authorization_code").lower()
        client_id = inputs.get("client_id")
        client_secret = inputs.get("client_secret")
        redirect_uri = inputs.get("redirect_uri") or "http://localhost:9999/callback"
        scope = inputs.get("scope") or ""
        creds = inputs.get("login_credentials") or {}
        verify_user = inputs.get("verify_userinfo") or {}
        if not client_id or not client_secret:
            return PrimitiveResult(passed=False, error="client_id / client_secret missing",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        if flow != "authorization_code":
            return PrimitiveResult(passed=False, error=f"unsupported flow {flow}",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        from urllib.parse import urlparse, parse_qs
        sess = requests.Session()
        try:
            sess.get(f"{config.APP_BASE_URL}/login", timeout=config.HTTP_TIMEOUT)
            xsrf = sess.cookies.get("XSRF-TOKEN") or ""
            sess.post(f"{config.APP_BASE_URL}/login",
                      headers={"X-XSRF-TOKEN": xsrf, "Accept": "application/json"},
                      json={"email": creds.get("username") or creds.get("email"),
                            "password": creds.get("password")},
                      timeout=config.HTTP_TIMEOUT)
        except Exception:
            pass
        params = {"client_id": client_id, "redirect_uri": redirect_uri,
                  "response_type": "code", "scope": scope,
                  "state": secrets.token_urlsafe(16), "prompt": "none"}
        try:
            ar = sess.get(f"{config.APP_BASE_URL}/oauth/authorize",
                          params=params, allow_redirects=False, timeout=config.HTTP_TIMEOUT)
        except Exception as e:
            return PrimitiveResult(passed=False, error=f"authorize failed: {e}",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        location = ar.headers.get("Location") or ""
        code = (parse_qs(urlparse(location).query).get("code") or [None])[0] if location else None
        if not code:
            return PrimitiveResult(passed=False,
                                   error=f"no code (status={ar.status_code})",
                                   data={"authorize_status": ar.status_code,
                                         "redirect_location": location[:300]},
                                   elapsed_ms=int((time.time() - t0) * 1000))
        try:
            tk = sess.post(f"{config.APP_BASE_URL}/oauth/token",
                           data={"grant_type": "authorization_code",
                                 "client_id": client_id, "client_secret": client_secret,
                                 "redirect_uri": redirect_uri, "code": code},
                           headers={"Accept": "application/json"},
                           timeout=config.HTTP_TIMEOUT)
            try:
                tb = tk.json()
            except Exception:
                tb = {"raw": tk.text[:500]}
        except Exception as e:
            return PrimitiveResult(passed=False, error=f"token exchange failed: {e}",
                                   elapsed_ms=int((time.time() - t0) * 1000))
        access_token = tb.get("access_token") if isinstance(tb, dict) else None
        userinfo, userinfo_ok = None, True
        if verify_user and access_token:
            ui = http_request("GET", _wrap_url(verify_user.get("url") or "/oauth/userinfo"),
                              headers={"Authorization": f"Bearer {access_token}",
                                       "Accept": "application/json"})
            userinfo = ui.json_body
            ef = list(verify_user.get("expected_fields") or [])
            userinfo_ok = isinstance(userinfo, dict) and all(f in userinfo for f in ef)
        passed = bool(access_token) and userinfo_ok
        return PrimitiveResult(passed=passed,
                               data={"authorize_success": True, "code_received": True,
                                     "token_exchange_success": bool(access_token),
                                     "token_status": tk.status_code,
                                     "access_token": (access_token[:20] + "...") if access_token else None,
                                     "userinfo_fields_present": userinfo_ok},
                               elapsed_ms=int((time.time() - t0) * 1000))
    except Exception as e:
        return PrimitiveResult(passed=False, error=f"P25 unhandled: {e}",
                               elapsed_ms=int((time.time() - t0) * 1000))


def p26_search_query(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    try:
        inputs = substitute_placeholders(inputs, context)
        path = inputs.get("path") or "/api/v1/search"
        method = (inputs.get("method") or "GET").upper()
        params = inputs.get("params") or {}
        body = inputs.get("body")
        token = inputs.get("token") or context.get("auth_token")
        setup_data = inputs.get("setup_data") or []
        expected = inputs.get("expected_results") or {}

        headers = dict(config.DEFAULT_API_HEADERS)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        seeded = 0
        for item in setup_data:
            r = http_request((item.get("method") or "POST"), _wrap_url(item.get("path") or "/"),
                             headers=headers, json_body=item.get("body"))
            if 200 <= r.status_code < 300:
                seeded += 1

        rs = http_request(method, _wrap_url(path), headers=headers, params=params,
                          json_body=body if isinstance(body, (dict, list)) else None)
        context["last_response"] = rs
        rbody = rs.json_body
        items = []
        if isinstance(rbody, list):
            items = rbody
        elif isinstance(rbody, dict):
            for key in ("data", "results", "items", "hits"):
                v = rbody.get(key)
                if isinstance(v, list):
                    items = v
                    break

        total = len(items)
        min_count = int(expected.get("min_count", 1))
        max_count = expected.get("max_count")
        first_contains = expected.get("first_result_contains")
        must_not_contain = expected.get("must_not_contain")

        first_match = True
        if first_contains is not None:
            first_match = bool(items) and (str(first_contains)
                                            in json.dumps(items[0], ensure_ascii=False, default=str))
        exclusion_ok = True
        if must_not_contain is not None:
            haystack = json.dumps(items, ensure_ascii=False, default=str)
            exclusion_ok = str(must_not_contain) not in haystack

        count_ok = total >= min_count
        if max_count is not None:
            count_ok = count_ok and total <= int(max_count)

        passed = count_ok and first_match and exclusion_ok and rs.status_code == 200
        return PrimitiveResult(passed=passed,
                               data={"total_results": total,
                                     "first_result_match": first_match,
                                     "exclusion_match": exclusion_ok,
                                     "count_ok": count_ok,
                                     "seeded_items": seeded,
                                     "status_code": rs.status_code,
                                     "response_time_ms": rs.elapsed_ms},
                               elapsed_ms=int((time.time() - t0) * 1000))
    except Exception as e:
        return PrimitiveResult(passed=False, error=f"P26 unhandled: {e}",
                               elapsed_ms=int((time.time() - t0) * 1000))


def p27_webhook_delivery(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs = substitute_placeholders(inputs, context)
    register = inputs.get("register", {})
    trigger = inputs.get("trigger", {})
    expect = inputs.get("expect_delivery", {})

    headers = dict(config.DEFAULT_API_HEADERS)
    if context.get("auth_token"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"

    if requests:
        try:
            requests.delete(f"{config.MOCK_RECEIVER_URL}/history", timeout=5)
        except Exception:
            pass
    trigger_ts = time.time()

    if register:
        body = register.get("body", {})
        if isinstance(body, dict):
            body.setdefault("url", config.MOCK_RECEIVER_URL_FROM_APP + "/hook")
        rr = http_request("POST", _wrap_url(register.get("path", "/api/v1/webhooks")),
                          headers=headers, json_body=body)
        if rr.status_code not in (200, 201):
            return PrimitiveResult(passed=False, error=f"register failed: {rr.status_code}",
                                   elapsed_ms=int((time.time() - t0) * 1000))

    if trigger:
        http_request(trigger.get("method", "POST"), _wrap_url(trigger.get("path", "/")),
                     headers=headers, json_body=trigger.get("body"))

    timeout = (expect.get("timeout_ms") or 10000) / 1000
    deadline = time.time() + timeout
    body_contains = expect.get("body_contains", {})
    headers_contain = expect.get("headers_contain", {})
    while time.time() < deadline:
        if requests is None:
            break
        try:
            r = requests.get(f"{config.MOCK_RECEIVER_URL}/history", params={"since": trigger_ts}, timeout=5)
            if r.status_code == 200:
                items = r.json().get("items", [])
                for item in items:
                    body_text = item.get("body", "")
                    body_ok = all(str(v) in body_text for v in body_contains.values()) if body_contains else True
                    hdr_ok = all(re.search(v, item.get("headers", {}).get(k.lower(), "")) for k, v in headers_contain.items()) if headers_contain else True
                    if body_ok and hdr_ok:
                        return PrimitiveResult(passed=True,
                                               data={"item": item, "items_total": len(items)},
                                               elapsed_ms=int((time.time() - t0) * 1000))
        except Exception:
            pass
        time.sleep(0.5)
    return PrimitiveResult(passed=False, error="webhook not received within timeout",
                           elapsed_ms=int((time.time() - t0) * 1000))


def p28_email_check(inputs: dict, context: dict) -> PrimitiveResult:
    if config.SKIP_EMAIL_TESTS:
        return _not_impl("p28_email_check (no MailHog in this PFM compose; SKIP_EMAIL_TESTS=1)")
    return _not_impl("p28_email_check")


def p29_multi_step_workflow(inputs: dict, context: dict) -> PrimitiveResult:
    t0 = time.time()
    inputs = substitute_placeholders(inputs, context)
    setup = inputs.get("entity_setup", {})
    headers = dict(config.DEFAULT_API_HEADERS)
    if context.get("auth_token"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    entity_id: Any = None
    if setup:
        rs = http_request(setup.get("method", "POST"), _wrap_url(setup.get("path", "/")),
                          headers=headers, json_body=setup.get("body"))
        body = rs.json_body
        if isinstance(body, dict):
            data = body.get("data") if isinstance(body.get("data"), dict) else body
            entity_id = data.get("id") if isinstance(data, dict) else None
    steps = inputs.get("steps", [])
    step_results = []
    passed_count = 0
    for step in steps:
        path = (step.get("path", "/") or "").replace("{{id}}", str(entity_id) if entity_id is not None else "")
        rs = http_request(step.get("method", "POST"), _wrap_url(path),
                          headers=headers, json_body=step.get("body"))
        ok = rs.status_code == step.get("expect_status", 200)
        if ok and step.get("expect_state"):
            actual = _eval_jsonpath(rs.json_body, step["expect_state"]["path"])
            ok = actual == step["expect_state"].get("value")
        step_results.append({"name": step.get("name"), "passed": ok, "status_code": rs.status_code})
        if ok:
            passed_count += 1
    return PrimitiveResult(
        passed=(passed_count == len(steps)),
        data={"entity_id": entity_id, "steps_passed": passed_count, "steps_total": len(steps),
              "step_results": step_results},
        elapsed_ms=int((time.time() - t0) * 1000),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

DEFAULT_RBAC_USERS = {
    "admin":              {"email": "admin@pfm.local", "password": "secret123"},
    "owner":              {"email": "admin@pfm.local", "password": "secret123"},
    "ro":                 {"email": "ro@pfm.local", "password": "ropass123"},
    "full":               {"email": "full@pfm.local", "password": "fullpass123"},
    "mng_trx":            {"email": "mngtrx@pfm.local", "password": "mngtrxpass123"},
    "mng_meta":           {"email": "mngmeta@pfm.local", "password": "mngmetapass123"},
    "mng_budgets":        {"email": "mngbudgets@pfm.local", "password": "mngbudgetspass123"},
    "mng_piggies":        {"email": "mngpiggies@pfm.local", "password": "mngpiggiespass123"},
    "mng_subscriptions":  {"email": "mngsubs@pfm.local", "password": "mngsubspass123"},
    "mng_rules":          {"email": "mngrules@pfm.local", "password": "mngrulespass123"},
    "mng_recurring":      {"email": "mngrecurring@pfm.local", "password": "mngrecurringpass123"},
    "mng_webhooks":       {"email": "mngwebhooks@pfm.local", "password": "mngwebhookspass123"},
    "mng_currencies":     {"email": "mngcurrencies@pfm.local", "password": "mngcurrenciespass123"},
    "read_budgets":       {"email": "readbudgets@pfm.local", "password": "readbudgetspass123"},
    "read_piggies":       {"email": "readpiggies@pfm.local", "password": "readpiggiespass123"},
    "read_subscriptions": {"email": "readsubs@pfm.local", "password": "readsubspass123"},
    "read_rules":         {"email": "readrules@pfm.local", "password": "readrulespass123"},
    "read_recurring":     {"email": "readrecurring@pfm.local", "password": "readrecurringpass123"},
    "read_webhooks":      {"email": "readwebhooks@pfm.local", "password": "readwebhookspass123"},
    "read_currencies":    {"email": "readcurrencies@pfm.local", "password": "readcurrenciespass123"},
    "view_reports":       {"email": "viewreports@pfm.local", "password": "viewreportspass123"},
    "view_memberships":   {"email": "viewmemberships@pfm.local", "password": "viewmembershipspass123"},
}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


PRIMITIVE_REGISTRY = {
    "P01": p01_file_exists,
    "P02": p02_file_content_match,
    "P03": p03_file_count,
    "P04": p04_http_request,
    "P05": p05_api_crud,
    "P06": p06_json_schema_match,
    "P07": p07_json_value_assert,
    "P08": p08_db_query,
    "P09": p09_db_table_exists,
    "P10": p10_db_column_check,
    "P11": p11_db_index_check,
    "P12": p12_docker_exec,
    "P13": p13_auth_login,
    "P14": p14_permission_check,
    "P15": p15_status_code_assert,
    "P16": p16_response_time_check,
    "P17": p17_llm_judge,
    "P18": p18_browser_interaction,
    "P19": p19_dom_assertion,
    "P20": p20_network_fault_inject,
    "P21": p21_websocket_connect,
    "P22": p22_graphql_query,
    "P23": p23_file_upload_download,
    "P24": p24_queue_job_check,
    "P25": p25_oauth_oidc_flow,
    "P26": p26_search_query,
    "P27": p27_webhook_delivery,
    "P28": p28_email_check,
    "P29": p29_multi_step_workflow,
}


try:
    from _browser_primitives import (
        p18_render_dom as _shared_render_dom,
        p19_screenshot as _shared_screenshot,
    )
    PRIMITIVE_REGISTRY.setdefault("RENDER_DOM", _shared_render_dom)
    PRIMITIVE_REGISTRY.setdefault("SCREENSHOT", _shared_screenshot)
except Exception as _bp_exc:
    import logging as _bp_log
    _bp_log.getLogger("_browser_primitives").warning(
        "RENDER_DOM/SCREENSHOT registration failed: %s", _bp_exc)


def run_primitive(prim_call: dict, context: dict) -> PrimitiveResult:
    pid = (prim_call or {}).get("type")
    fn = PRIMITIVE_REGISTRY.get(pid)
    raw_inputs = (prim_call or {}).get("inputs") or {}
    if fn is None:
        return PrimitiveResult(
            passed=False,
            error=f"unknown primitive {pid!r}",
            data={"primitive": pid, "available": sorted(PRIMITIVE_REGISTRY.keys())},
        )
    try:
        rendered = substitute_placeholders(raw_inputs, context)
        if not isinstance(rendered, dict):
            rendered = {}
        return fn(rendered, context)
    except Exception as e:
        import traceback as _tb
        return PrimitiveResult(
            passed=False,
            error=f"unhandled in {pid}: {type(e).__name__}: {e}",
            data={"trace": _tb.format_exc()[:800]},
        )


__all__ = [
    "DEFAULT_RBAC_USERS",
    "PRIMITIVE_REGISTRY",
    "run_primitive",
    "p01_file_exists", "p02_file_content_match", "p03_file_count",
    "p04_http_request", "p05_api_crud", "p06_json_schema_match",
    "p07_json_value_assert", "p08_db_query", "p09_db_table_exists",
    "p10_db_column_check", "p11_db_index_check", "p12_docker_exec",
    "p13_auth_login", "p14_permission_check", "p15_status_code_assert",
    "p16_response_time_check", "p17_llm_judge", "p18_browser_interaction",
    "p19_dom_assertion", "p20_network_fault_inject", "p21_websocket_connect",
    "p22_graphql_query", "p23_file_upload_download", "p24_queue_job_check",
    "p25_oauth_oidc_flow", "p26_search_query", "p27_webhook_delivery",
    "p28_email_check", "p29_multi_step_workflow",
]
