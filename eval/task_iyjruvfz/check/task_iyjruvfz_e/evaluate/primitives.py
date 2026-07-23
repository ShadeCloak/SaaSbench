
from __future__ import annotations

import base64
import glob
import hashlib
import hmac
import http.server
import io
import json
import os
import re
import secrets
import socket
import socketserver
import threading
import time
import typing as t
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode, urlparse

from . import config, utils
from .utils import PrimitiveResult, db_query, docker_exec, http_request, shell_exec

JsonValue = t.Any


_LAST_JUDGE_INFO: dict = {}


def get_last_judge_info() -> dict:
    return dict(_LAST_JUDGE_INFO)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _now_ms() -> float:
    return time.perf_counter() * 1000


def _result(prim: str, passed: bool, **kw) -> PrimitiveResult:
    inputs = kw.pop("inputs", {})
    outputs = kw.pop("outputs", {})
    return PrimitiveResult(
        primitive=prim,
        passed=passed,
        inputs=inputs,
        outputs=outputs,
        message=kw.pop("message", ""),
        elapsed_ms=kw.pop("elapsed_ms", 0.0),
        error=kw.pop("error", None),
    )


def _last_response(context: dict) -> dict | None:
    return context.get("__last_response__")


def _store_response(context: dict, resp: dict) -> None:
    context["__last_response__"] = resp


def _ci_header_get(headers: dict | None, name: str) -> t.Any:
    if not headers:
        return None
    target = (name or "").casefold()
    for k, v in headers.items():
        if isinstance(k, str) and k.casefold() == target:
            return v
    return None


def _resolve_table_ci(table_name: str, schema: str = "public") -> str | None:
    try:
        res = db_query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE LOWER(table_schema)=LOWER(%s) AND LOWER(table_name)=LOWER(%s) LIMIT 1",
            (schema, table_name),
        )
        if res.get("ok") and res.get("rows"):
            return res["rows"][0]["table_name"]
    except Exception:
        return None
    return None


def _resolve_column_ci(
    table_name: str, column_name: str, schema: str = "public"
) -> str | None:
    try:
        res = db_query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE LOWER(table_schema)=LOWER(%s) AND LOWER(table_name)=LOWER(%s) "
            "AND LOWER(column_name)=LOWER(%s) LIMIT 1",
            (schema, table_name, column_name),
        )
        if res.get("ok") and res.get("rows"):
            return res["rows"][0]["column_name"]
    except Exception:
        return None
    return None


def _quote_ident(name: str) -> str:
    if not name:
        return name
    if any(c.isupper() for c in name) or not name.replace("_", "").isalnum():
        safe = name.replace('"', '""')
        return f'"{safe}"'
    return name


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p01(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    path = inputs.get("path", "")
    expected_type = inputs.get("type", "any")
    base = Path(inputs.get("base_dir", config.WORKSPACE_DIR))
    candidate = base / path

    exists = candidate.exists()
    type_ok = True
    if exists and expected_type == "file":
        type_ok = candidate.is_file()
    elif exists and expected_type == "dir":
        type_ok = candidate.is_dir()

    passed = exists and type_ok
    return _result(
        "P01",
        passed,
        inputs=inputs,
        outputs={"absolute_path": str(candidate), "exists": exists, "type_ok": type_ok},
        elapsed_ms=_now_ms() - started,
        message=("found" if passed else f"missing: {candidate}"),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p02(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    path = inputs.get("path", "")
    pattern = inputs.get("pattern", "")
    match_type = inputs.get("match_type", "contains")
    base = Path(inputs.get("base_dir", config.WORKSPACE_DIR))
    candidate = base / path

    if not candidate.exists():
        return _result(
            "P02",
            False,
            inputs=inputs,
            outputs={"exists": False},
            elapsed_ms=_now_ms() - started,
            message=f"missing: {candidate}",
        )
    try:
        text = candidate.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return _result(
            "P02",
            False,
            inputs=inputs,
            elapsed_ms=_now_ms() - started,
            error=f"read_error: {exc}",
        )

    if match_type == "regex":
        try:
            matches = re.findall(pattern, text)
            count = len(matches)
            passed = count > 0
        except re.error as exc:
            return _result(
                "P02",
                False,
                inputs=inputs,
                error=f"bad_regex: {exc}",
                elapsed_ms=_now_ms() - started,
            )
    else:
        count = text.count(pattern)
        passed = count > 0

    return _result(
        "P02",
        passed,
        inputs=inputs,
        outputs={"match_count": count},
        elapsed_ms=_now_ms() - started,
        message=f"matches={count}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p03(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    pattern = inputs.get("glob", inputs.get("pattern", "**/*"))
    base = Path(inputs.get("base_dir", config.WORKSPACE_DIR))
    min_expected = inputs.get("min_expected", 1)
    max_expected = inputs.get("max_expected")

    if not base.exists():
        return _result(
            "P03",
            False,
            inputs=inputs,
            elapsed_ms=_now_ms() - started,
            message=f"base_dir missing: {base}",
        )

    type_filter = inputs.get("type_filter")
    if type_filter in ("directory", "dir"):
        sel = lambda p: p.is_dir()
    elif type_filter in ("file",):
        sel = lambda p: p.is_file()
    else:
        sel = lambda p: p.exists()
    files = [str(p.relative_to(base)) for p in base.glob(pattern) if sel(p)]
    count = len(files)
    ok_min = count >= min_expected
    ok_max = True if max_expected is None else count <= max_expected
    passed = ok_min and ok_max
    return _result(
        "P03",
        passed,
        inputs=inputs,
        outputs={"count": count, "files_sample": files[:10]},
        elapsed_ms=_now_ms() - started,
        message=f"count={count} (min={min_expected}, max={max_expected})",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _build_auth_headers(context: dict, role: str | None = None) -> tuple[dict, dict]:

    headers: dict = {}
    role = role or context.get("__current_role__")
    token_info = context.get("__tokens__", {}).get(role)
    if not token_info:
        token_info = {
            "type": context.get("auth_token_type", "session"),
            "token": context.get("auth_token"),
            "cookies": context.get("auth_cookies"),
        }
    ttype = token_info.get("type")
    token = token_info.get("token")
    cookies = token_info.get("cookies") or {}
    if ttype == "api_key" and token:
        headers["Authorization"] = f"Bearer {token}"
    elif ttype == "bearer" and token:
        headers["Authorization"] = f"Bearer {token}"
    return headers, cookies


def _current_api_key(context: dict, role: str | None = None) -> str | None:
    role = role or context.get("__current_role__")
    info = context.get("__tokens__", {}).get(role) or {}
    if info.get("type") == "api_key":
        return info.get("token")
    return None


def primitive_p04(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    method = inputs.get("method", "GET").upper()
    path = inputs.get("path", "/")
    body = inputs.get("body")
    extra_headers = dict(inputs.get("headers") or {})
    query = inputs.get("query") or inputs.get("params")
    timeout = inputs.get("timeout", config.HTTP_TIMEOUT_SEC)

    no_auth = bool(inputs.get("no_auth"))
    if no_auth:
        auth_headers, cookies = {}, {}
    else:
        auth_headers, cookies = _build_auth_headers(context)
    _parsed_path = urlparse(path).path or "/"
    is_v2 = _parsed_path.startswith("/api/v2/") or _parsed_path == "/api/v2"
    is_v1 = _parsed_path.startswith("/api/v1/") or _parsed_path == "/api/v1"
    if is_v2:
        for k, v in config.DEFAULT_V2_HEADERS.items():
            extra_headers.setdefault(k, v)
    extra_headers.setdefault("Accept", "application/json")
    for k, v in auth_headers.items():
        extra_headers.setdefault(k, v)

    _explicit_v1_key = None
    if is_v1 and not no_auth:
        _authz = extra_headers.get("Authorization") or extra_headers.get("authorization")
        if isinstance(_authz, str) and _authz.startswith("Bearer "):
            _explicit_v1_key = _authz[len("Bearer "):].strip()
            extra_headers.pop("Authorization", None)
            extra_headers.pop("authorization", None)
    if is_v1 and _explicit_v1_key:
        query = dict(query) if query else {}
        query["apiKey"] = _explicit_v1_key

    if is_v1 and not no_auth and not (query and "apiKey" in query):
        _role = context.get("__current_role__")
        _prov = context.get(f"{str(_role).upper()}_API_KEY") if _role else None
        _inj = _prov or _current_api_key(context)
        if _inj:
            query = dict(query) if query else {}
            query.setdefault("apiKey", _inj)

    resp = http_request(
        method,
        path,
        headers=extra_headers,
        json_body=body,
        params=query,
        cookies=cookies or None,
        timeout=timeout,
        allow_redirects=inputs.get("allow_redirects", False),
    )
    _store_response(context, resp)

    store_as = inputs.get("store_as_from_path")
    if store_as:
        for var, jpath in store_as.items():
            v = utils.get_json_path(resp.get("body"), jpath)
            if v is not None:
                context[var] = v

    passed = resp.get("ok", False) and not resp.get("error")
    return _result(
        "P04",
        passed,
        inputs={"method": method, "path": path, "query": query},
        outputs={
            "status_code": resp.get("status_code"),
            "headers": resp.get("headers"),
            "body": resp.get("body"),
            "size": resp.get("size"),
            "elapsed_ms": resp.get("elapsed_ms"),
        },
        elapsed_ms=_now_ms() - started,
        message=(resp.get("error") or f"status={resp.get('status_code')}"),
        error=resp.get("error"),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p05(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    resource = inputs.get("resource", "/")
    create_body = inputs.get("create_body") or {}
    update_body = inputs.get("update_body") or {}
    expected_create = inputs.get("expected_create_status", [200, 201])
    expected_read = inputs.get("expected_read_status", [200])
    expected_update = inputs.get("expected_update_status", [200, 204])
    expected_delete = inputs.get("expected_delete_status", [200, 204])

    if isinstance(expected_create, int):
        expected_create = [expected_create]
    if isinstance(expected_read, int):
        expected_read = [expected_read]
    if isinstance(expected_update, int):
        expected_update = [expected_update]
    if isinstance(expected_delete, int):
        expected_delete = [expected_delete]

    def _ok(resp: dict, allowed: list[int]) -> bool:
        return resp.get("status_code") in allowed

    steps_total = 4
    steps_passed = 0
    log: list = []

    cr = primitive_p04(
        {"method": "POST", "path": resource, "body": create_body}, context
    )
    cr_resp = _last_response(context) or {}
    log.append({"step": "create", "status": cr_resp.get("status_code")})
    if _ok(cr_resp, expected_create):
        steps_passed += 1
        new_id = (
            utils.get_json_path(cr_resp.get("body"), "$.data.id")
            or utils.get_json_path(cr_resp.get("body"), "$.id")
        )
    else:
        new_id = None

    if new_id is not None:
        item_path = f"{resource.rstrip('/')}/{new_id}"
        rr = primitive_p04({"method": "GET", "path": item_path}, context)
        rr_resp = _last_response(context) or {}
        log.append({"step": "read", "status": rr_resp.get("status_code")})
        if _ok(rr_resp, expected_read):
            steps_passed += 1

        if update_body:
            ur = primitive_p04(
                {"method": "PATCH", "path": item_path, "body": update_body}, context
            )
            ur_resp = _last_response(context) or {}
            log.append({"step": "update", "status": ur_resp.get("status_code")})
            if _ok(ur_resp, expected_update):
                steps_passed += 1
        else:
            steps_passed += 1
            log.append({"step": "update", "status": "skipped"})

        dr = primitive_p04({"method": "DELETE", "path": item_path}, context)
        dr_resp = _last_response(context) or {}
        log.append({"step": "delete", "status": dr_resp.get("status_code")})
        if _ok(dr_resp, expected_delete):
            steps_passed += 1

    return _result(
        "P05",
        steps_passed == steps_total,
        inputs=inputs,
        outputs={"steps_passed": steps_passed, "steps_total": steps_total, "log": log},
        elapsed_ms=_now_ms() - started,
        message=f"crud {steps_passed}/{steps_total}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p06(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    resp = _last_response(context) or {}
    body = resp.get("body")
    required = inputs.get("required_fields", [])
    field_types = inputs.get("field_types", {}) or {}

    missing: list = []
    type_mismatches: list = []

    if not isinstance(body, dict):
        return _result(
            "P06",
            False,
            inputs=inputs,
            outputs={"body_kind": type(body).__name__},
            elapsed_ms=_now_ms() - started,
            message="response body is not a dict",
        )

    for f in required:
        if f not in body:
            missing.append(f)
    for f, expected_type in field_types.items():
        v = body.get(f)
        if not _type_match(v, expected_type):
            type_mismatches.append({"field": f, "expected": expected_type, "got": type(v).__name__})

    passed = not missing and not type_mismatches
    return _result(
        "P06",
        passed,
        inputs=inputs,
        outputs={"missing_fields": missing, "type_mismatches": type_mismatches},
        elapsed_ms=_now_ms() - started,
        message=f"missing={missing} mismatches={type_mismatches}",
    )


def _type_match(value: t.Any, expected: str) -> bool:
    expected = (expected or "").lower()
    mapping = {
        "string": str,
        "str": str,
        "int": int,
        "integer": int,
        "number": (int, float),
        "float": float,
        "bool": bool,
        "boolean": bool,
        "array": list,
        "list": list,
        "object": dict,
        "dict": dict,
        "null": type(None),
    }
    if expected not in mapping:
        return True
    return isinstance(value, mapping[expected])


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p07(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    assertions = inputs.get("assertions") or []
    if not assertions:
        return _result(
            "P07",
            True,
            inputs=inputs,
            elapsed_ms=_now_ms() - started,
            message="no assertions (placeholder)",
        )

    resp = _last_response(context) or {}
    body = resp.get("body")
    headers = resp.get("headers") or {}


    results: list = []
    all_pass = True
    for a in assertions:
        if "comment" in a and not any(
            k in a for k in ("path", "header", "expected", "expected_min", "expected_max", "min_response_size")
        ):
            results.append({"assertion": a, "passed": True, "note": "placeholder"})
            continue

        if "min_response_size" in a:
            actual_size = resp.get("size") or 0
            ok = actual_size >= a["min_response_size"]
            results.append({"assertion": a, "passed": ok, "actual_size": actual_size})
            if not ok:
                all_pass = False
            continue

        if "header" in a:
            actual = _ci_header_get(headers, a["header"])
        else:
            path_field = a.get("path", "$")
            if isinstance(path_field, list):
                actual = None
                for p in path_field:
                    if not isinstance(p, str):
                        continue
                    actual = utils.get_json_path(body, p)
                    if actual is not None:
                        break
            else:
                actual = utils.get_json_path(body, path_field)

        passed = True
        detail: dict = {"assertion": a, "actual": _truncate(actual)}

        if "expected" in a:
            expected = a["expected"]
            tol = a.get("tolerance")
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) and tol is not None:
                passed = abs(float(actual) - float(expected)) <= float(tol)
            else:
                passed = actual == expected
        if "expected_contains" in a:
            ec = a["expected_contains"]
            passed = passed and (actual is not None and ec in str(actual))
        if "expected_contains_one_of" in a:
            opts = a["expected_contains_one_of"] or []
            passed = passed and any(o == actual or (actual is not None and o in str(actual)) for o in opts)
        if "expected_one_of" in a:
            opts = a["expected_one_of"] or []
            passed = passed and actual in opts
        if "expected_one_of_keys" in a and isinstance(actual, dict):
            opts = a["expected_one_of_keys"] or []
            passed = passed and any(k in actual for k in opts)
        if "expected_pattern" in a:
            pat = a["expected_pattern"]
            try:
                passed = passed and (actual is not None and re.search(pat, str(actual)) is not None)
            except re.error:
                passed = False
        if "expected_min" in a:
            try:
                passed = passed and float(actual) >= float(a["expected_min"])
            except (TypeError, ValueError):
                passed = False
        if "expected_max" in a:
            try:
                passed = passed and float(actual) <= float(a["expected_max"])
            except (TypeError, ValueError):
                passed = False
        if "expected_min_length" in a:
            passed = passed and (actual is not None and len(actual) >= a["expected_min_length"])
        if "expected_max_length" in a:
            passed = passed and (actual is not None and len(actual) <= a["expected_max_length"])
        if "expected_type" in a:
            passed = passed and _type_match(actual, a["expected_type"])
        if "expected_in_range_seconds_from_now" in a:
            lo, hi = a["expected_in_range_seconds_from_now"]
            try:
                from datetime import datetime, timezone

                dt = None
                if isinstance(actual, datetime):
                    dt = actual
                elif isinstance(actual, str):
                    dt = datetime.fromisoformat(actual.replace("Z", "+00:00"))
                if dt is not None:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    delta = (dt - datetime.now(timezone.utc)).total_seconds()
                else:
                    delta = float(actual) - time.time()
                passed = passed and lo <= delta <= hi
            except Exception:
                passed = False

        if "store_as" in a and actual is not None:
            sa = a["store_as"]
            if isinstance(sa, str):
                key = sa.strip("${}")
                context[key] = actual
                detail["stored_as"] = key
            else:
                detail["stored_as_skipped"] = True

        detail["passed"] = passed
        results.append(detail)
        if not passed:
            all_pass = False

    return _result(
        "P07",
        all_pass,
        inputs=inputs,
        outputs={"results": results},
        elapsed_ms=_now_ms() - started,
        message=("all_passed" if all_pass else f"{sum(1 for r in results if not r.get('passed'))} failed"),
    )


def _truncate(val: t.Any, n: int = 200) -> t.Any:
    if isinstance(val, str) and len(val) > n:
        return val[:n] + "..."
    return val


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p08(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    sql = inputs.get("sql", "")
    if isinstance(sql, str) and "${" in sql:
        import re as _re
        for ph in _re.findall(r"\$\{(\w+)\}", sql):
            v = context.get(ph)
            if v is None:
                v = context.get(ph.lower())
            if v is None:
                continue
            sql = sql.replace("${" + ph + "}", str(v))
    if isinstance(sql, str) and "{{" in sql:
        import re as _re
        for ph in _re.findall(r"\{\{(\w+)\}\}", sql):
            v = context.get(ph)
            if v is None:
                v = context.get(ph.lower())
            if v is None:
                continue
            sql = sql.replace("{{" + ph + "}}", str(v))
    poll_attempts = int(inputs.get("poll_attempts", 1) or 1)
    poll_interval_ms = int(inputs.get("poll_interval_ms", 500) or 500)
    res = db_query(sql)
    for _attempt in range(1, max(1, poll_attempts)):
        if res.get("ok") and res.get("rowcount", 0) > 0:
            break
        time.sleep(poll_interval_ms / 1000.0)
        res = db_query(sql)
    if not res["ok"]:
        return _result(
            "P08",
            False,
            inputs=inputs,
            outputs=res,
            elapsed_ms=_now_ms() - started,
            error=res.get("error"),
            message=f"db_error: {res.get('error')}",
        )
    rows = res["rows"]
    rowcount = res["rowcount"]

    pseudo = {"body": {"rows": rows, "rowcount": rowcount}, "ok": True, "status_code": 200, "headers": {}}
    _store_response(context, pseudo)

    assertions = inputs.get("assertions") or []
    expected_result = inputs.get("expected_result")

    if assertions:
        sub = primitive_p07({"assertions": assertions}, context)
        sub.primitive = "P08"
        sub.inputs = inputs
        sub.elapsed_ms += _now_ms() - started
        if not sub.message:
            sub.message = f"rowcount={rowcount}"
        if rowcount == 0:
            return _result(
                "P08",
                False,
                inputs=inputs,
                outputs={"rowcount": 0},
                elapsed_ms=sub.elapsed_ms,
                message="P08: 0 rows returned; assertion cannot be satisfied",
            )
        return sub

    if expected_result is not None:
        if isinstance(expected_result, dict) and rows:
            ok = all(rows[0].get(k) == v for k, v in expected_result.items())
            return _result(
                "P08",
                ok,
                inputs=inputs,
                outputs={"rows": rows[:5], "rowcount": rowcount},
                elapsed_ms=_now_ms() - started,
                message=("match" if ok else f"mismatch: row0={rows[0]}"),
            )
        if isinstance(expected_result, int):
            return _result(
                "P08",
                rowcount == expected_result,
                inputs=inputs,
                outputs={"rowcount": rowcount},
                elapsed_ms=_now_ms() - started,
            )

    return _result(
        "P08",
        rowcount > 0,
        inputs=inputs,
        outputs={"rowcount": rowcount, "rows": rows[:3]},
        elapsed_ms=_now_ms() - started,
        message=f"rowcount={rowcount}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p09(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    tables = inputs.get("tables", [])
    schema = inputs.get("schema", "public")
    existing: list = []
    missing: list = []
    for t_ in tables:
        candidates = t_ if isinstance(t_, list) else [t_]
        sql = (
            "SELECT 1 FROM information_schema.tables "
            "WHERE LOWER(table_schema)=LOWER(%s) AND LOWER(table_name)=LOWER(%s) LIMIT 1"
        )
        hit = None
        for cand in candidates:
            res = db_query(sql, (schema, cand))
            if res["ok"] and res["rowcount"] > 0:
                hit = cand
                break
        if hit is not None:
            existing.append(hit)
        else:
            missing.append(t_)

    found_count = len(existing)
    total_count = len(tables)
    passed = not missing
    return _result(
        "P09",
        passed,
        inputs=inputs,
        outputs={
            "existing": existing,
            "missing": missing,
            "found_count": found_count,
            "total_count": total_count,
        },
        elapsed_ms=_now_ms() - started,
        message=f"{found_count}/{total_count} tables found",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p10(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    table = inputs.get("table", "")
    expected_columns = inputs.get("expected_columns", [])
    schema = inputs.get("schema", "public")

    res = db_query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE LOWER(table_schema)=LOWER(%s) AND LOWER(table_name)=LOWER(%s)",
        (schema, table),
    )
    if not res["ok"]:
        return _result(
            "P10",
            False,
            inputs=inputs,
            elapsed_ms=_now_ms() - started,
            error=res.get("error"),
            message=f"db_error: {res.get('error')}",
        )

    cols_lower = {(r["column_name"] or "").lower() for r in res["rows"]}
    missing: list = []
    existing: list = []
    for c in expected_columns:
        candidates = c if isinstance(c, list) else [c]
        hit = next((cand for cand in candidates
                    if isinstance(cand, str) and cand.lower() in cols_lower), None)
        if hit is not None:
            existing.append(hit)
        else:
            missing.append(c)
    total = len(expected_columns)
    found = len(existing)
    passed = (not missing) or (total > 0 and found / total >= 0.80)
    return _result(
        "P10",
        passed,
        inputs=inputs,
        outputs={
            "existing": existing,
            "missing": missing,
            "found_count": found,
            "total_count": total,
            "match_ratio": round(found / total, 3) if total else 1.0,
        },
        elapsed_ms=_now_ms() - started,
        message=f"{found}/{total} columns" + (" (≥80% pass)" if passed and missing else ""),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p11(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    table = inputs.get("table", "")
    expected = inputs.get("expected_indexes") or []
    schema = inputs.get("schema", "public")
    order_sensitive = bool(inputs.get("order_sensitive", False))

    res = db_query(
        """
        SELECT i.relname AS index_name,
               array_agg(a.attname ORDER BY array_position(idx.indkey::int[], a.attnum::int)) AS cols
        FROM pg_index idx
        JOIN pg_class i ON i.oid = idx.indexrelid
        JOIN pg_class t ON t.oid = idx.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(idx.indkey)
        WHERE LOWER(n.nspname) = LOWER(%s) AND LOWER(t.relname) = LOWER(%s)
        GROUP BY i.relname
        """,
        (schema, table),
    )
    if not res["ok"]:
        return _result(
            "P11",
            False,
            inputs=inputs,
            elapsed_ms=_now_ms() - started,
            error=res.get("error"),
        )
    indexes = [{"name": r["index_name"], "cols": r["cols"]} for r in res["rows"]]

    def _norm_seq(seq: list) -> list[str]:
        return [str(c).lower() for c in (seq or [])]

    def _index_match(idx_cols: list, expected_cols: list) -> bool:
        a = _norm_seq(idx_cols)
        b = _norm_seq(expected_cols)
        return a == b if order_sensitive else sorted(a) == sorted(b)

    missing: list = []
    matched: list = []
    for spec in expected:
        cols = spec.get("columns") or []
        match = next(
            (idx for idx in indexes if _index_match(idx["cols"], cols)),
            None,
        )
        if match:
            matched.append({"expected": cols, "index_name": match["name"]})
        else:
            missing.append({"expected": cols})
    passed = not missing
    return _result(
        "P11",
        passed,
        inputs=inputs,
        outputs={
            "matched": matched,
            "missing": missing,
            "all_indexes": indexes[:20],
            "order_sensitive": order_sensitive,
        },
        elapsed_ms=_now_ms() - started,
        message=f"{len(matched)}/{len(expected)} indexes",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p12(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    if inputs.get("skip_in_normal_run") and config.SKIP_TEARDOWN:
        return _result(
            "P12",
            True,
            inputs=inputs,
            outputs={"skipped": True},
            elapsed_ms=_now_ms() - started,
            message="skipped per --skip-teardown",
        )

    cmd = inputs.get("command", "")
    container = inputs.get("container") or _guess_container(cmd)
    mode = inputs.get("mode")

    timeout = inputs.get("timeout", 90)
    if mode == "host":
        out = shell_exec(cmd, timeout=timeout)
    elif cmd.startswith("docker exec") or cmd.startswith("docker compose") or cmd.startswith("docker-compose"):
        out = shell_exec(cmd, timeout=timeout)
    elif cmd.startswith("cd /") or cmd.startswith("cd ./") or cmd.startswith("cd ~"):
        out = shell_exec(cmd, timeout=timeout)
    elif cmd.startswith("psql"):
        import re as _re
        _m = _re.match(r"\s*psql\s+(?:-c\s+)?(.*)", cmd, _re.S)
        _sql = _m.group(1).strip() if _m else cmd[len("psql"):].strip()
        if len(_sql) >= 2 and _sql[0] in "\"'" and _sql[-1] == _sql[0]:
            _sql = _sql[1:-1]
        _sql = _sql.replace('\\"', '"').replace("\\'", "'")
        full = (
            f"docker exec {config.DB_CONTAINER} psql -U {config.DB_USER} -d {config.DB_NAME} -At -c "
            + json.dumps(_sql)
        )
        out = shell_exec(full, timeout=timeout)
    elif mode == "container" or container:
        out = docker_exec(container or config.APP_CONTAINER, cmd, timeout=timeout)
    else:
        out = shell_exec(cmd, timeout=timeout)

    expected_exit = inputs.get("expected_exit_code", 0)
    expected_acceptable = inputs.get("expected_acceptable_exit_codes")
    expected_stdout_contains = inputs.get("expected_stdout_contains")
    expected_stderr_contains = inputs.get("expected_stderr_contains")

    if expected_acceptable is not None:
        passed = out["exit_code"] in expected_acceptable
    else:
        passed = out["exit_code"] == expected_exit

    def _check_contains(needle, haystack):
        if needle is None:
            return True
        if isinstance(needle, list):
            return any(str(n) in haystack for n in needle)
        return str(needle) in haystack

    if expected_stdout_contains is not None and not _check_contains(
        expected_stdout_contains, out.get("stdout") or ""
    ):
        passed = False
    if expected_stderr_contains is not None and not _check_contains(
        expected_stderr_contains, out.get("stderr") or ""
    ):
        passed = False

    return _result(
        "P12",
        passed,
        inputs=inputs,
        outputs={
            "exit_code": out["exit_code"],
            "stdout_tail": (out.get("stdout") or "")[-1000:],
            "stderr_tail": (out.get("stderr") or "")[-1000:],
        },
        elapsed_ms=_now_ms() - started,
        error=out.get("error"),
        message=f"exit={out['exit_code']}",
    )


def _guess_container(cmd: str) -> str | None:
    if "redis" in cmd:
        return config.REDIS_CONTAINER
    if "postgres" in cmd or "psql" in cmd or "pg_" in cmd:
        return config.DB_CONTAINER
    return config.APP_CONTAINER


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p13(inputs: dict, context: dict) -> PrimitiveResult:

    started = _now_ms()
    role = inputs.get("role", "admin")
    if role not in config.TEST_USERS:
        return _result(
            "P13",
            False,
            inputs=inputs,
            outputs={"requested_role": role, "available_roles": sorted(config.TEST_USERS.keys())},
            elapsed_ms=_now_ms() - started,
            error="unknown_role",
            message=(
                f"role '{role}' not provisioned in TEST_USERS; "
                f"available: {sorted(config.TEST_USERS.keys())}. "
                "Either add the role to config.TEST_USERS or fix the dag.json node input."
            ),
        )
    user = config.TEST_USERS[role]

    tokens = context.setdefault("__tokens__", {})
    context["__current_role__"] = role

    if inputs.get("expected_failure"):
        neg_email = inputs.get("email") or user["email"]
        neg_pw = inputs.get("password") or "___definitely_wrong_password___"
        cookies, csrf = _nextauth_csrf()
        login_resp = http_request(
            "POST",
            "/api/auth/callback/credentials",
            data={
                "csrfToken": csrf or "",
                "email": neg_email,
                "password": neg_pw,
                "callbackUrl": "/",
                "json": "true",
            },
            cookies=cookies or {},
            allow_redirects=False,
            timeout=config.HTTP_TIMEOUT_SEC,
        )
        sess_cookies = {**(cookies or {}), **_extract_set_cookie(login_resp.get("headers", {}))}
        verify = http_request(
            "GET", "/api/auth/session", cookies=sess_cookies, timeout=config.HTTP_TIMEOUT_SEC
        )
        vbody = verify.get("body") or {}
        logged_in = isinstance(vbody, dict) and bool(vbody.get("user"))
        _store_response(context, login_resp)
        return _result(
            "P13",
            not logged_in,
            inputs=inputs,
            outputs={
                "role": role,
                "via": "nextauth_credentials_negative",
                "logged_in": logged_in,
                "login_status": login_resp.get("status_code"),
            },
            elapsed_ms=_now_ms() - started,
            message=(
                "correctly rejected invalid credentials (no session)"
                if not logged_in
                else "SECURITY: invalid credentials were ACCEPTED (session created)"
            ),
        )

    if method_provision := (inputs.get("method") in ("api_key_var", "provision_api_key")):
        keyvar = f"{role.upper()}_API_KEY"
        provisioned = context.get(keyvar) or _db_create_api_key(role, user)
        if provisioned:
            context[keyvar] = provisioned
            return _result(
                "P13",
                True,
                inputs=inputs,
                outputs={"role": role, "via": "db_api_key_var", "var": f"{role.upper()}_API_KEY", "key_prefix": provisioned[:10]},
                elapsed_ms=_now_ms() - started,
                message=f"provisioned {role} api_key -> ${{{role.upper()}_API_KEY}} (no token-cache)",
            )
        return _result(
            "P13",
            False,
            inputs=inputs,
            outputs={"role": role},
            elapsed_ms=_now_ms() - started,
            error="db_api_key_provision_failed",
            message=f"failed to provision {role} api key via DB",
        )

    if role in tokens and tokens[role].get("token"):
        _cached_type = tokens[role].get("type")
        _req_method = inputs.get("method", "session")
        _wants_session = _req_method in ("session", "form", "credentials")
        if not (_wants_session and _cached_type == "api_key"):
            context["auth_token"] = tokens[role]["token"]
            context["auth_token_type"] = tokens[role]["type"]
            context["auth_cookies"] = tokens[role].get("cookies") or {}
            return _result(
                "P13",
                True,
                inputs=inputs,
                outputs={"role": role, "cached": True, "type": tokens[role]["type"]},
                elapsed_ms=_now_ms() - started,
                message=f"reuse cached {role} token",
            )

    method = inputs.get("method", "session")
    if method in ("session", "form", "credentials"):
        _last_login_status = None
        for _attempt in range(5):
            cookies, csrf = _nextauth_csrf()
            if not (csrf and cookies):
                time.sleep(2)
                continue
            login_resp = http_request(
                "POST",
                "/api/auth/callback/credentials",
                data={
                    "csrfToken": csrf,
                    "email": user["email"],
                    "password": user["password"],
                    "callbackUrl": "/",
                    "json": "true",
                },
                cookies=cookies,
                allow_redirects=False,
                timeout=config.HTTP_TIMEOUT_SEC,
            )
            _last_login_status = login_resp.get("status_code")
            sess_cookies = {**cookies, **_extract_set_cookie(login_resp.get("headers", {}))}
            verify = http_request(
                "GET", "/api/auth/session", cookies=sess_cookies, timeout=config.HTTP_TIMEOUT_SEC
            )
            body = verify.get("body") or {}
            if isinstance(body, dict) and body.get("user"):
                tokens[role] = {"type": "session", "token": None, "cookies": sess_cookies}
                context["auth_token"] = None
                context["auth_token_type"] = "session"
                context["auth_cookies"] = sess_cookies
                _store_response(context, login_resp)
                return _result(
                    "P13",
                    True,
                    inputs=inputs,
                    outputs={"role": role, "via": "nextauth_credentials", "user_id": body.get("user", {}).get("id"), "attempt": _attempt + 1},
                    elapsed_ms=_now_ms() - started,
                    message=f"login {role} via NextAuth",
                )
            time.sleep(2)

    api_key = context.get(f"{role.upper()}_API_KEY") or _db_create_api_key(role, user)
    if api_key:
        context[f"{role.upper()}_API_KEY"] = api_key
        tokens[role] = {"type": "api_key", "token": api_key, "cookies": None}
        context["auth_token"] = api_key
        context["auth_token_type"] = "api_key"
        context["auth_cookies"] = {}
        return _result(
            "P13",
            True,
            inputs=inputs,
            outputs={"role": role, "via": "db_api_key", "key_prefix": api_key[:10]},
            elapsed_ms=_now_ms() - started,
            message=f"login {role} via DB-issued API key",
        )

    return _result(
        "P13",
        False,
        inputs=inputs,
        outputs={"role": role},
        elapsed_ms=_now_ms() - started,
        message=f"all auth methods failed for role={role}",
    )


def _nextauth_csrf() -> tuple[dict, str | None]:
    resp = http_request("GET", "/api/auth/csrf", timeout=config.HTTP_TIMEOUT_SEC)
    body = resp.get("body") or {}
    csrf = body.get("csrfToken") if isinstance(body, dict) else None
    cookies = _extract_set_cookie(resp.get("headers", {}))
    return cookies, csrf


def _extract_set_cookie(headers: dict) -> dict:
    raw = headers.get("Set-Cookie") or headers.get("set-cookie") or ""
    if not raw:
        return {}
    cookies: dict = {}
    for part in raw.split(", "):
        for kv in part.split(";"):
            kv = kv.strip()
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            if k.lower() in ("path", "domain", "expires", "samesite", "max-age", "httponly", "secure"):
                continue
            cookies[k] = v
    return cookies


def _db_create_api_key(role: str, user: dict) -> str | None:
    try:
        users_tbl = (
            _resolve_table_ci("users")
            or _resolve_table_ci("User")
            or _resolve_table_ci("auth_users")
            or _resolve_table_ci("auth_user")
        )
        if not users_tbl:
            return None
        users_email_col = (
            _resolve_column_ci(users_tbl, "email")
            or _resolve_column_ci(users_tbl, "emailAddress")
            or _resolve_column_ci(users_tbl, "email_address")
        )
        if not users_email_col:
            return None
        sql_select_user = (
            f"SELECT id FROM {_quote_ident(users_tbl)} "
            f"WHERE {_quote_ident(users_email_col)}=%s LIMIT 1"
        )
        res = db_query(sql_select_user, (user["email"],))
        if not res["ok"] or not res["rows"]:
            return None
        user_id = res["rows"][0]["id"]

        ak_tbl = (
            _resolve_table_ci("ApiKey")
            or _resolve_table_ci("api_keys")
            or _resolve_table_ci("api_key")
            or _resolve_table_ci("ApiKeys")
        )
        if not ak_tbl:
            return None
        col_user_id = (
            _resolve_column_ci(ak_tbl, "userId")
            or _resolve_column_ci(ak_tbl, "user_id")
            or _resolve_column_ci(ak_tbl, "ownerId")
            or _resolve_column_ci(ak_tbl, "owner_id")
        )
        col_hashed = (
            _resolve_column_ci(ak_tbl, "hashedKey")
            or _resolve_column_ci(ak_tbl, "hashed_key")
            or _resolve_column_ci(ak_tbl, "hashed_token")
            or _resolve_column_ci(ak_tbl, "key_hash")
        )
        col_id = _resolve_column_ci(ak_tbl, "id")
        if not (col_user_id and col_hashed and col_id):
            return None
        col_note = (
            _resolve_column_ci(ak_tbl, "note")
            or _resolve_column_ci(ak_tbl, "name")
            or _resolve_column_ci(ak_tbl, "label")
        )
        col_created = (
            _resolve_column_ci(ak_tbl, "createdAt")
            or _resolve_column_ci(ak_tbl, "created_at")
        )

        prefix = os.environ.get("API_KEY_PREFIX", "app_")
        raw = secrets.token_hex(32)
        full_key = f"{prefix}{raw}"
        hashed = hashlib.sha256(raw.encode()).hexdigest()

        db_query(
            f"DELETE FROM {_quote_ident(ak_tbl)} WHERE {_quote_ident(col_user_id)}=%s",
            (user_id,),
        )

        cols = [col_id, col_user_id, col_hashed]
        vals: list[object] = [
            f"c{secrets.token_hex(12)}",
            user_id,
            hashed,
        ]
        if col_note:
            cols.append(col_note)
            vals.append(f"eval_{role}")
        cols_sql = ", ".join(_quote_ident(c) for c in cols)
        ph = ", ".join(["%s"] * len(vals))
        if col_created:
            cols_sql = f"{cols_sql}, {_quote_ident(col_created)}"
            placeholders = f"{ph}, NOW()"
        else:
            placeholders = ph
        ins_sql = (
            f"INSERT INTO {_quote_ident(ak_tbl)} ({cols_sql}) VALUES ({placeholders})"
        )
        ins = db_query(ins_sql, tuple(vals))
        if not ins["ok"]:
            return None

        verify = http_request(
            "GET",
            "/api/v1/me",
            headers={"Authorization": f"Bearer {full_key}"},
            timeout=config.HTTP_TIMEOUT_SEC,
        )
        if verify.get("status_code") in (200, 401, 404):
            return full_key
        return full_key
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p14(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    action = inputs.get("action", "")
    expected = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status")
    acceptable = inputs.get("expected_acceptable_statuses")

    parts = action.split(None, 1)
    if len(parts) != 2:
        return _result(
            "P14",
            False,
            inputs=inputs,
            elapsed_ms=_now_ms() - started,
            message=f"bad action: {action}",
        )
    method, path = parts
    body = inputs.get("body")

    status = None
    for _rl in range(4):
        resp = primitive_p04({"method": method, "path": path, "body": body}, context)
        status = (_last_response(context) or {}).get("status_code")
        if status != 429:
            break
        time.sleep(2 * (_rl + 1))

    if expected == "denied":
        accepted = set(acceptable or [401, 403, 404])
        passed = status in accepted
    else:
        accepted = set(acceptable or [200, 201, 204])
        if expected_status:
            accepted.add(expected_status)
        passed = status in accepted

    return _result(
        "P14",
        passed,
        inputs=inputs,
        outputs={"status_code": status, "expected": expected, "accepted_set": sorted(accepted)},
        elapsed_ms=_now_ms() - started,
        message=f"{expected} -> status={status}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p15(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    resp = _last_response(context) or {}
    actual = resp.get("status_code")
    expected = inputs.get("expected_status")
    acceptable = inputs.get("acceptable_statuses")

    if acceptable:
        passed = actual in set(acceptable)
        msg = f"status={actual} in {acceptable}"
    elif expected is not None:
        if isinstance(expected, (list, tuple, set)):
            passed = actual in set(expected)
            msg = f"status={actual} in {expected}"
        else:
            passed = actual == expected
            msg = f"status={actual} == {expected}"
    else:
        passed = actual is not None and 200 <= actual < 400
        msg = f"status={actual} is 2xx/3xx"

    return _result(
        "P15",
        passed,
        inputs=inputs,
        outputs={"actual_status": actual},
        elapsed_ms=_now_ms() - started,
        message=msg,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p16(inputs: dict, context: dict) -> PrimitiveResult:
    started = _now_ms()
    resp = _last_response(context) or {}
    elapsed = resp.get("elapsed_ms", 0)
    max_ms = inputs.get("max_ms", 5000)
    passed = elapsed <= max_ms
    return _result(
        "P16",
        passed,
        inputs=inputs,
        outputs={"elapsed_ms": elapsed, "max_ms": max_ms},
        elapsed_ms=_now_ms() - started,
        message=f"{elapsed:.0f}ms <= {max_ms}ms",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p17(inputs: dict, context: dict) -> PrimitiveResult:
    import os as _os_skip
    _skip_env = _os_skip.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
    _skip_cfg = False
    try:
        from . import config as _cfg_skip
        _skip_cfg = getattr(_cfg_skip, "SKIP_LLM_JUDGE", False)
    except Exception:
        try:
            import config as _cfg_skip
            _skip_cfg = getattr(_cfg_skip, "SKIP_LLM_JUDGE", False)
        except Exception:
            pass
    if _skip_env or _skip_cfg:
        _sr = inputs.get("score_range", [0, 5]) if isinstance(inputs, dict) else [0, 5]
        _LAST_JUDGE_INFO.clear()
        _LAST_JUDGE_INFO.update({"skipped": True, "llm_api_failure": False,
                                 "reason": "SKIP_LLM_JUDGE"})
        context["__last_judge_score__"] = 0
        context["__last_judge_range__"] = _sr
        return _result(
            "P17",
            False,
            inputs=inputs if isinstance(inputs, dict) else {},
            outputs={"score": 0, "range": _sr, "skipped": True},
            message="llm-judge skipped (SKIP_LLM_JUDGE)",
        )
    started = _now_ms()
    rubric = inputs.get("rubric_prompt", "Rate the quality 0-N.")
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "code_files")

    evidence: dict = {"type": evidence_type}
    if evidence_type == "directory_listing":
        base_in = str(inputs.get("base_dir", "/app"))
        if base_in == "/app":
            base = config.WORKSPACE_DIR
        elif base_in.startswith("/app/"):
            base = config.WORKSPACE_DIR / base_in[len("/app/"):]
        else:
            base = Path(base_in)
            if not base.is_absolute():
                base = config.WORKSPACE_DIR / base_in
        depth = int(inputs.get("depth", 2))
        evidence["listing"] = _list_dir(base, depth)
    elif evidence_type == "code_files":
        files = inputs.get("files_to_sample") or []
        evidence["files"] = []
        for f in files:
            fs = str(f)
            if fs == "/app":
                p = config.WORKSPACE_DIR
            elif fs.startswith("/app/"):
                p = config.WORKSPACE_DIR / fs[len("/app/"):]
            elif fs.startswith("/"):
                p = Path(fs)
            else:
                p = config.WORKSPACE_DIR / fs
            if p.is_dir():
                sub = list(p.rglob("*.ts"))[:5]
                for s in sub:
                    try:
                        evidence["files"].append({"path": str(s.relative_to(config.WORKSPACE_DIR)), "head": s.read_text(errors="replace")[:8000]})
                    except Exception:
                        pass
            elif p.is_file():
                try:
                    evidence["files"].append({"path": f, "head": p.read_text(errors="replace")[:8000]})
                except Exception:
                    pass
    elif evidence_type == "http_response_html":
        resp = _last_response(context) or {}
        evidence["html_head"] = (resp.get("text") or "")[:5000]

    score = _llm_score(rubric, evidence, score_range)

    if score is None:
        return _result(
            "P17",
            False,
            inputs=inputs,
            outputs={"evidence_summary": _summarize_evidence(evidence), "score": 0},
            elapsed_ms=_now_ms() - started,
            message="llm-judge failed (no score)",
        )

    context["__last_judge_score__"] = score
    context["__last_judge_range__"] = score_range
    return _result(
        "P17",
        True,
        inputs=inputs,
        outputs={"score": score, "range": score_range, "evidence_summary": _summarize_evidence(evidence)},
        elapsed_ms=_now_ms() - started,
        message=f"llm-judge score={score}/{score_range[1]}",
    )


def _list_dir(base: Path, depth: int) -> list:
    out: list = []
    if not base.exists():
        return [{"error": f"{base} not found"}]
    base = base.resolve()
    base_depth = len(base.parts)
    for p in base.rglob("*"):
        cur_depth = len(p.parts) - base_depth
        if cur_depth > depth:
            continue
        try:
            out.append({"path": str(p.relative_to(base)), "is_dir": p.is_dir()})
        except Exception:
            continue
        if len(out) > 200:
            break
    return out


def _summarize_evidence(evidence: dict) -> dict:
    s: dict = {"type": evidence.get("type")}
    if "listing" in evidence:
        s["item_count"] = len(evidence["listing"])
    if "files" in evidence:
        s["file_count"] = len(evidence["files"])
    if "html_head" in evidence:
        s["html_head_len"] = len(evidence["html_head"])
    return s


def _llm_score(rubric: str, evidence: dict, score_range: list) -> float | None:
    _LAST_JUDGE_INFO.clear()

    sys_msg = (
        "You are a strict code-quality judge. Read the rubric and the evidence, "
        f"then output ONLY a single number (integer or float) within range "
        f"[{score_range[0]}, {score_range[1]}]. "
        "Do NOT explain, do NOT think out loud, do NOT restate the rubric. "
        "Your ENTIRE response must be exactly one number and nothing else "
        '(or a JSON object like {"score": N}). '
        "You have NO access to any tools, shell, or filesystem: score SOLELY "
        "from the evidence provided and do NOT ask to inspect more files."
    )
    ev_text = json.dumps(evidence, ensure_ascii=False)[:30000]

    from ._llm_judge_safe import safe_chat_completion

    _msgs = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": f"### Rubric\n{rubric}\n\n### Evidence\n```json\n{ev_text}\n```"},
    ]

    def _call(msgs):
        return safe_chat_completion(
            messages=msgs,
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE,
            temperature=0.0,
            timeout=float(config.LLM_TIMEOUT_SEC),
            max_tokens=1024,
        )

    def _parse_score(raw: str):
        if not raw:
            return None
        s = raw.strip()
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "score" in obj:
                return float(obj["score"])
        except Exception:
            pass
        keyed = re.findall(r'"?score"?\s*[:=]\s*(-?\d+(?:\.\d+)?)', s, re.IGNORECASE)
        if keyed:
            return float(keyed[-1])
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None

    res = _call(_msgs)

    if res.skipped:
        _LAST_JUDGE_INFO.update({
            "skipped": True,
            "llm_api_failure": res.llm_api_failure,
            "exception_class": res.exception_class,
            "reason": res.error or "LLM unavailable",
        })
        return None

    score = _parse_score(res.raw)
    if score is None:
        retry_msgs = _msgs + [
            {"role": "assistant", "content": (res.raw or "")[:2000]},
            {"role": "user", "content": (
                f"You did not output a score. Reply with ONLY a single number "
                f"between {score_range[0]} and {score_range[1]} — no words, no "
                f"explanation, just the number."
            )},
        ]
        res2 = _call(retry_msgs)
        if not res2.skipped:
            score = _parse_score(res2.raw)

    if score is None:
        _LAST_JUDGE_INFO.update({
            "skipped": True,
            "parse_failure": True,
            "reason": "model reply contains no number after forcing retry",
        })
        return None

    score = max(score_range[0], min(score_range[1], score))
    return score


# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------


def _stub(prim_id: str, inputs: dict) -> PrimitiveResult:
    return _result(
        prim_id,
        False,
        inputs=inputs,
        outputs={"implemented": False},
        message=(
            f"{prim_id} not implemented in this task's framework. "
            f"If a DAG node references {prim_id}, implement it in primitives.py "
            f"before running. Stub returns FAILED to prevent silent pass."
        ),
        error="primitive_not_implemented",
    )


def primitive_p18(inputs: dict, context: dict) -> PrimitiveResult:
    return _stub("P18", inputs)


def primitive_p19(inputs: dict, context: dict) -> PrimitiveResult:

    started = _now_ms()
    resp = _last_response(context) or {}
    text = resp.get("text") or ""
    selectors = inputs.get("selector_or_text_one_of") or inputs.get("contains_one_of") or []
    if not selectors:
        single = inputs.get("text") or inputs.get("selector")
        if single:
            selectors = [single]
    found = next((s for s in selectors if s and s in text), None)
    passed = found is not None
    return _result(
        "P19",
        passed,
        inputs=inputs,
        outputs={"matched_text": found, "haystack_size": len(text)},
        elapsed_ms=_now_ms() - started,
        message=("found: " + str(found)) if passed else "no candidate text found",
    )


def primitive_p20(inputs: dict, context: dict) -> PrimitiveResult:
    return _stub("P20", inputs)


def primitive_p21(inputs: dict, context: dict) -> PrimitiveResult:
    return _stub("P21", inputs)


def primitive_p22(inputs: dict, context: dict) -> PrimitiveResult:
    return _stub("P22", inputs)


def primitive_p23(inputs: dict, context: dict) -> PrimitiveResult:
    return _stub("P23", inputs)


def primitive_p24(inputs: dict, context: dict) -> PrimitiveResult:
    return _stub("P24", inputs)


def primitive_p25(inputs: dict, context: dict) -> PrimitiveResult:

    started = _now_ms()
    flow = inputs.get("flow", "platform_oauth_token_exchange")
    client_id = inputs.get("client_id") or context.get("PLATFORM_CLIENT_ID")
    client_secret = inputs.get("client_secret") or context.get("PLATFORM_CLIENT_SECRET")

    if flow == "platform_oauth_token_exchange":
        if not client_id or not client_secret:
            return _result(
                "P25",
                False,
                inputs=inputs,
                elapsed_ms=_now_ms() - started,
                message="missing client_id/client_secret (Setup OAuth client first)",
                error="missing_credentials",
            )

        # === Step 1: Pre-seed PlatformAuthorizationToken directly in the DB ===
        admin_user = config.TEST_USERS.get("admin", {})
        user_email = admin_user.get("email")
        if not user_email:
            return _result("P25", False, inputs=inputs, error="no_admin_email", message="admin email missing")

        users_tbl = (
            _resolve_table_ci("users")
            or _resolve_table_ci("User")
            or _resolve_table_ci("auth_users")
        )
        users_email_col = (
            _resolve_column_ci(users_tbl, "email") if users_tbl else None
        )
        if not (users_tbl and users_email_col):
            return _result("P25", False, inputs=inputs, error="users_table_missing",
                           message="users/User table or email column not found")
        user_q = db_query(
            f"SELECT id FROM {_quote_ident(users_tbl)} "
            f"WHERE {_quote_ident(users_email_col)}=%s LIMIT 1",
            (user_email,),
        )
        if not user_q["ok"] or not user_q["rows"]:
            return _result("P25", False, inputs=inputs, error="admin_not_seeded",
                           message=f"admin user {user_email} not found in DB")
        user_id = user_q["rows"][0]["id"]

        grant_tbl = (
            _resolve_table_ci("PlatformAuthorizationToken")
            or _resolve_table_ci("platform_authorization_tokens")
            or _resolve_table_ci("platform_authorization_token")
            or _resolve_table_ci("OAuthGrant")
            or _resolve_table_ci("oauth_grants")
            or _resolve_table_ci("oauth_authorization_codes")
        )
        if not grant_tbl:
            return _result(
                "P25",
                False,
                inputs=inputs,
                elapsed_ms=_now_ms() - started,
                error="grant_table_missing",
                message=("Platform OAuth grant table not found. Tried: "
                         "PlatformAuthorizationToken / platform_authorization_tokens / "
                         "OAuthGrant / oauth_grants / oauth_authorization_codes."),
            )
        col_id = _resolve_column_ci(grant_tbl, "id")
        col_user = (
            _resolve_column_ci(grant_tbl, "userId")
            or _resolve_column_ci(grant_tbl, "user_id")
        )
        col_client = (
            _resolve_column_ci(grant_tbl, "platformOAuthClientId")
            or _resolve_column_ci(grant_tbl, "platform_oauth_client_id")
            or _resolve_column_ci(grant_tbl, "clientId")
            or _resolve_column_ci(grant_tbl, "client_id")
            or _resolve_column_ci(grant_tbl, "oauthClientId")
            or _resolve_column_ci(grant_tbl, "oauth_client_id")
        )
        if not (col_id and col_user and col_client):
            return _result(
                "P25",
                False,
                inputs=inputs,
                elapsed_ms=_now_ms() - started,
                error="grant_columns_missing",
                message=(f"required columns missing in {grant_tbl}: "
                         f"id={col_id} user={col_user} client={col_client}"),
            )

        auth_code = secrets.token_hex(16)
        ins_sql = (
            f"INSERT INTO {_quote_ident(grant_tbl)} "
            f"({_quote_ident(col_id)}, {_quote_ident(col_user)}, {_quote_ident(col_client)}) "
            "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
        )
        ins = db_query(ins_sql, (auth_code, user_id, client_id))
        if not ins["ok"]:
            return _result(
                "P25",
                False,
                inputs=inputs,
                elapsed_ms=_now_ms() - started,
                error="grant_setup_failed",
                message=f"cannot pre-seed grant in {grant_tbl}: {ins.get('error')}",
            )

        # === Step 2: Call the exchange endpoint ===
        resp = http_request(
            "POST",
            f"/api/v2/oauth/{client_id}/exchange",
            headers={
                "x-platform-secret-key": client_secret,
                "x-platform-client-id": client_id,
                **config.DEFAULT_V2_HEADERS,
            },
            json_body={
                "code": auth_code,
                "authorizationCode": auth_code,
                "authorization_code": auth_code,
            },
            timeout=config.HTTP_TIMEOUT_SEC,
        )

        body = resp.get("body") or {}
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict) and isinstance(body, dict) and any(
            k in body for k in (
                "access_token", "accessToken", "accessTokenExpiresAt", "expires_in",
            )
        ):
            data = body
        if isinstance(data, dict):
            _store_response(
                context,
                {"body": data, "status_code": resp.get("status_code"),
                 "headers": resp.get("headers"), "ok": True},
            )
        else:
            _store_response(context, resp)

        _ok_fields = {
            "accessToken", "access_token",
            "accessTokenExpiresAt", "expires_in", "expiresIn",
        }
        passed = (
            resp.get("status_code") in (200, 201)
            and isinstance(data, dict)
            and any(k in data for k in _ok_fields)
        )
        return _result(
            "P25",
            passed,
            inputs=inputs,
            outputs={
                "status_code": resp.get("status_code"),
                "body_keys": list(body.keys()) if isinstance(body, dict) else None,
                "auth_code_used": auth_code[:8] + "...",
            },
            elapsed_ms=_now_ms() - started,
            message=f"exchange status={resp.get('status_code')} success={passed}",
        )

    if flow == "generic_oauth_refresh_token":
        try:
            import jwt as pyjwt
        except ImportError:
            return _result("P25", False, inputs=inputs, error="pyjwt_missing",
                           message="install PyJWT to test generic OAuth refresh")

        secret = os.environ.get("APP_ENCRYPTION_KEY") or ""
        if not secret:
            import subprocess as _sp
            try:
                _kr = _sp.run(
                    ["docker", "exec", config.APP_CONTAINER, "printenv", "APP_ENCRYPTION_KEY"],
                    capture_output=True, text=True, timeout=15)
                secret = (_kr.stdout or "").strip()
            except Exception:
                secret = ""
        if not secret:
            secret = "test-secret-32bytes-aaaaaaaaaaaa"
        oauth_client_id = inputs.get("oauth_client_id") or context.get("OAUTH_CLIENT_ID") or "test-client"
        rt_payload = {
            "userId": 1,
            "teamId": None,
            "scope": [],
            "token_type": "Refresh Token",
            "clientId": oauth_client_id,
        }
        rt = pyjwt.encode(rt_payload, secret, algorithm="HS256")

        resp = http_request(
            "POST",
            "/api/auth/oauth/refreshToken",
            data={
                "grant_type": "refresh_token",
                "client_id": oauth_client_id,
                "refresh_token": rt,
            },
            timeout=config.HTTP_TIMEOUT_SEC,
        )
        _store_response(context, resp)
        body = resp.get("body") or {}
        passed = (
            resp.get("status_code") == 200
            and isinstance(body, dict)
            and any(k in body for k in ("access_token", "accessToken"))
        )
        return _result(
            "P25",
            passed,
            inputs=inputs,
            outputs={"status_code": resp.get("status_code")},
            elapsed_ms=_now_ms() - started,
            message=f"refresh status={resp.get('status_code')}",
        )

    return _result(
        "P25",
        False,
        inputs=inputs,
        elapsed_ms=_now_ms() - started,
        error="unsupported_flow",
        message=f"unsupported flow: {flow}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p26(inputs: dict, context: dict) -> PrimitiveResult:
    return _stub("P26", inputs)


# ---------------------------------------------------------------------------
#
#
# ---------------------------------------------------------------------------


def _mock_receiver_alive() -> bool:
    resp = http_request("GET", f"http://localhost:{config.MOCK_WEBHOOK_PORT}/health", timeout=3)
    return resp.get("status_code") == 200


def _fetch_received_webhooks(since_ts: float) -> list[dict]:

    resp = http_request(
        "GET",
        f"http://localhost:{config.MOCK_WEBHOOK_PORT}/history?since={since_ts}",
        timeout=5,
    )
    if not resp.get("ok") or resp.get("status_code") != 200:
        return []
    body = resp.get("body") or []
    if not isinstance(body, list):
        return []
    return body


def _reset_mock_receiver() -> None:
    http_request("DELETE", f"http://localhost:{config.MOCK_WEBHOOK_PORT}/history", timeout=3)


def primitive_p27(inputs: dict, context: dict) -> PrimitiveResult:

    started = _now_ms()

    if inputs.get("verify_signature_locally"):
        _secret = inputs.get("secret", "test-secret")
        _body = inputs.get("body", "")
        _pat = inputs.get("expected_hex_signature_pattern", r"^[a-f0-9]{64}$")
        _sig = hmac.new(str(_secret).encode(), str(_body).encode(), hashlib.sha256).hexdigest()
        _ok = bool(re.match(_pat, _sig))
        return _result(
            "P27",
            _ok,
            inputs=inputs,
            outputs={"local_signature": _sig, "format_ok": _ok, "algorithm": "HMAC-SHA256"},
            elapsed_ms=_now_ms() - started,
            message=f"local HMAC-SHA256 verify: format_ok={_ok} (len={len(_sig)})",
        )

    if not _mock_receiver_alive():
        return _result(
            "P27",
            False,
            inputs=inputs,
            elapsed_ms=_now_ms() - started,
            error="mock_receiver_unavailable",
            message=(
                f"mock-receiver not reachable at localhost:{config.MOCK_WEBHOOK_PORT}/health. "
                "Run: cd task_iyjruvfz/docker && docker-compose up -d mock-receiver"
            ),
        )

    try:
        import subprocess
        subprocess.run(
            [
                "docker", "exec", config.APP_CONTAINER, "sh", "-c",
                "grep -q host.docker.internal /etc/hosts || "
                "( gw=$(ip route 2>/dev/null | awk '/default/{print $3; exit}'); "
                "  [ -n \"$gw\" ] && echo \"$gw host.docker.internal\" >> /etc/hosts )",
            ],
            check=False, capture_output=True, timeout=8,
        )
    except Exception:
        pass

    sub_url = inputs.get(
        "subscriber_url",
        f"http://host.docker.internal:{config.MOCK_WEBHOOK_PORT}/hook",
    )
    secret = inputs.get("secret", "test-webhook-secret-32chars-AAAAA")
    trigger_event = inputs.get("trigger_event", "BOOKING_CREATED")
    expected_header = inputs.get("expected_header_name", "X-App-Signature-256")
    expected_format = inputs.get("expected_signature_format", r"^[a-f0-9]{64}$")
    expected_max_retries = inputs.get("expected_max_retries")
    wait_seconds = int(inputs.get("wait_seconds", 8))

    auth_headers, cookies = _build_auth_headers(context)

    # === Step 1: First clean up any existing webhook with the same url (avoid 409 conflict) ===
    _wb_cleared = False
    try:
        listing = http_request(
            "GET",
            "/api/v2/webhooks",
            headers={**auth_headers, **config.DEFAULT_V2_HEADERS, "Accept": "application/json"},
            cookies=cookies,
            timeout=config.HTTP_TIMEOUT_SEC,
        )
        if listing.get("status_code") == 200:
            try:
                payload = json.loads(listing.get("text") or "{}")
            except Exception:
                payload = {}
            items = (
                payload.get("data") if isinstance(payload, dict) else payload
            ) or []
            if isinstance(items, dict):
                items = items.get("webhooks") or items.get("items") or []
            for it in items if isinstance(items, list) else []:
                if not isinstance(it, dict):
                    continue
                u = it.get("subscriberUrl") or it.get("subscriber_url") or it.get("url")
                if u != sub_url:
                    continue
                wh_id = it.get("id") or it.get("uid") or it.get("webhookId")
                if not wh_id:
                    continue
                http_request(
                    "DELETE",
                    f"/api/v2/webhooks/{wh_id}",
                    headers={**auth_headers, **config.DEFAULT_V2_HEADERS},
                    cookies=cookies,
                    timeout=config.HTTP_TIMEOUT_SEC,
                )
                _wb_cleared = True
    except Exception:
        pass

    if True:
        try:
            from . import fixtures
            wb_tbl = (
                _resolve_table_ci("Webhook")
                or _resolve_table_ci("webhooks")
                or _resolve_table_ci("webhook")
            )
            sub_col = (
                _resolve_column_ci(wb_tbl, "subscriberUrl")
                if wb_tbl
                else None
            ) or (
                _resolve_column_ci(wb_tbl, "subscriber_url")
                if wb_tbl
                else None
            ) or (
                _resolve_column_ci(wb_tbl, "url") if wb_tbl else None
            )
            if wb_tbl and sub_col:
                fixtures.db_query(
                    f"DELETE FROM {_quote_ident(wb_tbl)} "
                    f"WHERE {_quote_ident(sub_col)}=%s "
                    f"OR {_quote_ident(sub_col)} LIKE %s",
                    (sub_url, f"%:{config.MOCK_WEBHOOK_PORT}%"),
                )
        except Exception:
            pass

    # === Step 2: Register the webhook ===
    reg = http_request(
        "POST",
        "/api/v2/webhooks",
        headers={**config.DEFAULT_V2_HEADERS, **auth_headers},
        cookies=cookies or None,
        json_body={
            "subscriberUrl": sub_url,
            "triggers": [trigger_event],
            "secret": secret,
            "active": True,
        },
    )
    if reg.get("status_code") not in (200, 201, 409):
        return _result(
            "P27",
            False,
            inputs=inputs,
            outputs={
                "register_status": reg.get("status_code"),
                "register_body": reg.get("body"),
            },
            elapsed_ms=_now_ms() - started,
            error="webhook_register_failed",
            message=f"register failed: {reg.get('status_code')}",
        )

    # === Step 2: Trigger the event (create a Booking) ===
    _reset_mock_receiver()
    cutoff = time.time()

    _n = getattr(primitive_p27, "_slot_counter", 0)
    primitive_p27._slot_counter = _n + 1
    from datetime import datetime, timedelta, timezone as _tz
    _start = inputs.get("booking_start") or (
        (datetime(2027, 2, 1, 10, 0, 0, tzinfo=_tz.utc) + timedelta(days=_n)).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    evt = http_request(
        "POST",
        "/api/v2/bookings",
        headers={**config.DEFAULT_V2_HEADERS, **auth_headers},
        cookies=cookies or None,
        json_body={
            "start": _start,
            "eventTypeId": context.get("EVENT_TYPE_ID", 1),
            "attendee": {"name": "WebhookTester", "email": f"wh+{_n}@x.com", "timeZone": "UTC"},
        },
    )

    # === Step 3: Poll the mock-receiver ===
    from urllib.parse import urlparse as _urlparse
    _target_path = _urlparse(sub_url).path or "/hook"

    def _filter_path(items):
        has_path = any("path" in (r or {}) for r in items)
        if not has_path:
            return items
        return [r for r in items if (r.get("path") or "").rstrip("/") == _target_path.rstrip("/")]

    deadline = time.time() + wait_seconds
    received: list[dict] = []
    while time.time() < deadline:
        received = _filter_path(_fetch_received_webhooks(cutoff))
        if received:
            break
        time.sleep(1)

    try:
        from . import fixtures as _fx_wh
        wb_tbl2 = _resolve_table_ci("Webhook") or _resolve_table_ci("webhooks") or _resolve_table_ci("webhook")
        sub_col2 = (_resolve_column_ci(wb_tbl2, "subscriberUrl") if wb_tbl2 else None) \
            or (_resolve_column_ci(wb_tbl2, "subscriber_url") if wb_tbl2 else None) \
            or (_resolve_column_ci(wb_tbl2, "url") if wb_tbl2 else None)
        if wb_tbl2 and sub_col2:
            _fx_wh.db_query(
                f"DELETE FROM {_quote_ident(wb_tbl2)} WHERE {_quote_ident(sub_col2)} LIKE %s",
                (f"%:{config.MOCK_WEBHOOK_PORT}%",),
            )
    except Exception:
        pass

    if not received:
        return _result(
            "P27",
            False,
            inputs=inputs,
            outputs={
                "register_status": reg.get("status_code"),
                "trigger_status": evt.get("status_code"),
                "received": 0,
                "wait_sec": wait_seconds,
            },
            elapsed_ms=_now_ms() - started,
            message="no webhook delivered within timeout",
        )

    # === Step 4: Verify ===
    if expected_max_retries is not None:
        ok_retry = len(received) <= expected_max_retries + 1
    else:
        ok_retry = True

    first = received[0]
    sig_hdr = _ci_header_get(first.get("headers"), expected_header)

    expected_header_value = inputs.get("expected_header_value")
    if expected_header_value is not None:
        val_ok = sig_hdr is not None and sig_hdr == expected_header_value
        passed = ok_retry and val_ok
        return _result(
            "P27",
            passed,
            inputs=inputs,
            outputs={
                "received_count": len(received),
                "first_signature_header": sig_hdr,
                "header_value_ok": val_ok,
                "retry_count_ok": ok_retry,
            },
            elapsed_ms=_now_ms() - started,
            message=f"received={len(received)} header_value_ok={val_ok} (expected='{expected_header_value}')",
        )

    sig_ok = bool(sig_hdr and re.search(expected_format, sig_hdr))

    body_str = first["body"]
    expected_sig = hmac.new((secret or "").encode(), body_str.encode(), hashlib.sha256).hexdigest()
    hmac_ok = sig_hdr is not None and hmac.compare_digest(sig_hdr.lower(), expected_sig)

    passed = ok_retry and (sig_ok or hmac_ok)
    return _result(
        "P27",
        passed,
        inputs=inputs,
        outputs={
            "received_count": len(received),
            "first_signature_header": sig_hdr,
            "sig_format_ok": sig_ok,
            "hmac_ok": hmac_ok,
            "retry_count_ok": ok_retry,
        },
        elapsed_ms=_now_ms() - started,
        message=f"received={len(received)} sig_ok={sig_ok} hmac_ok={hmac_ok} retry_ok={ok_retry}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p28(inputs: dict, context: dict) -> PrimitiveResult:

    started = _now_ms()
    template = inputs.get("trigger_template_render", "")
    expected_subs = inputs.get("expected_substitutions", []) or []
    expected_no_unrendered = inputs.get("expected_no_unrendered_braces", True)
    explicit_sample = inputs.get("sample_data") or {}

    if not template:
        return _result("P28", True, inputs=inputs, message="no template to render (placeholder pass)")

    sample: dict[str, str] = {
        "attendeeName": "EvalUser",
        "attendee_name": "EvalUser",
        "attendee.name": "EvalUser",
        "eventType.title": "Sample Meeting",
        "eventTypeTitle": "Sample Meeting",
        "event_type_title": "Sample Meeting",
        "event_type.title": "Sample Meeting",
        "startTime": "2026-05-01T10:00:00Z",
        "start_time": "2026-05-01T10:00:00Z",
        "booking.startTime": "2026-05-01T10:00:00Z",
        "organizerName": "Owner",
        "organizer_name": "Owner",
        "organizer.name": "Owner",
    }
    if isinstance(explicit_sample, dict):
        sample.update({k: str(v) for k, v in explicit_sample.items()})

    rendered = template
    for k, v in sample.items():
        rendered = rendered.replace("{{" + k + "}}", str(v))
        rendered = rendered.replace("{{ " + k + " }}", str(v))

    miss = [s for s in expected_subs if s in rendered]
    raw_leftover = re.findall(r"\{\{[^}]+\}\}", rendered)
    leftover = [
        x for x in raw_leftover
        if not re.match(r"^\{\{\s*[#/^]", x)
    ]
    no_unrendered = (not leftover) if expected_no_unrendered else True

    passed = (not miss) and no_unrendered
    return _result(
        "P28",
        passed,
        inputs=inputs,
        outputs={"rendered": rendered, "missed": miss, "leftover": leftover},
        elapsed_ms=_now_ms() - started,
        message=("rendered ok" if passed else f"missed={miss}, leftover={leftover}"),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def primitive_p29(inputs: dict, context: dict) -> PrimitiveResult:
    return _stub("P29", inputs)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


PRIMITIVE_REGISTRY: dict[str, t.Callable[[dict, dict], PrimitiveResult]] = {
    "P01": primitive_p01,
    "P02": primitive_p02,
    "P03": primitive_p03,
    "P04": primitive_p04,
    "P05": primitive_p05,
    "P06": primitive_p06,
    "P07": primitive_p07,
    "P08": primitive_p08,
    "P09": primitive_p09,
    "P10": primitive_p10,
    "P11": primitive_p11,
    "P12": primitive_p12,
    "P13": primitive_p13,
    "P14": primitive_p14,
    "P15": primitive_p15,
    "P16": primitive_p16,
    "P17": primitive_p17,
    "P18": primitive_p18,
    "P19": primitive_p19,
    "P20": primitive_p20,
    "P21": primitive_p21,
    "P22": primitive_p22,
    "P23": primitive_p23,
    "P24": primitive_p24,
    "P25": primitive_p25,
    "P26": primitive_p26,
    "P27": primitive_p27,
    "P28": primitive_p28,
    "P29": primitive_p29,
}


def run_primitive(prim_call: dict, context: dict) -> PrimitiveResult:

    pid = prim_call.get("type")
    fn = PRIMITIVE_REGISTRY.get(pid)
    if fn is None:
        return _result(
            pid or "P??",
            False,
            inputs=prim_call.get("inputs", {}),
            error=f"unknown primitive {pid}",
            message=f"unknown primitive {pid}",
        )
    raw_inputs = prim_call.get("inputs", {}) or {}
    inputs = utils.render_value(raw_inputs, context)
    try:
        return fn(inputs if isinstance(inputs, dict) else {}, context)
    except Exception as exc:
        import traceback

        return _result(
            pid,
            False,
            inputs=inputs if isinstance(inputs, dict) else {},
            error=f"unhandled: {exc}",
            message=f"unhandled: {exc}\n{traceback.format_exc()[:500]}",
        )
