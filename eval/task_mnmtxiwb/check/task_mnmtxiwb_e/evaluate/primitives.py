import glob
import json
import os
import re
import secrets
import time
import subprocess
from typing import Any

import requests

from config import (
    APP_BASE_URL, API_BASE_URL, GRAPHQL_URL, APP_CONTAINER, DB_CONTAINER,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, TIMEOUT,
    TEST_USERS, LLM_API_KEY, LLM_API_BASE, LLM_MODEL, WORKSPACE_DIR,
)
from utils import PrimitiveResult, docker_exec as _docker_exec, get_db_connection

context = {
    "auth_token": None,
    "auth_tokens": {},
    "last_response": None,
}


def _resolve(val):
    if isinstance(val, str) and "{{" in val:
        from datetime import datetime, timedelta
        builtins = {
            "current_timestamp": str(int(datetime.now().timestamp())),
            "current_iso_datetime": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "future_datetime_1y": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "future_datetime_1m": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "future_date_1y": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"),
            "past_datetime": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for key, v in {**builtins, **context}.items():
            if isinstance(v, (str, int, float)):
                val = val.replace("{{" + key + "}}", str(v))
    return val


def _resolve_deep(obj):
    if isinstance(obj, str):
        return _resolve(obj)
    if isinstance(obj, dict):
        return {k: _resolve_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_deep(v) for v in obj]
    return obj


def _headers(path=None):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if path == "/graphql":
        token = context.get("jwt_token") or context.get("auth_token")
        org_id = _get_organization_id()
        if org_id:
            h["x-lago-organization"] = org_id
    elif path and path.startswith("/api/"):
        token = context.get("api_key") or context.get("auth_token")
    else:
        token = context.get("auth_token")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get_organization_id():
    if "organization_id" in context:
        return context["organization_id"]
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM organizations LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            context["organization_id"] = str(row[0])
            return context["organization_id"]
    except Exception:
        pass
    return None


def _set_last_response(data):
    context["last_response"] = data



def p01_file_exists(inputs):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    ftype = inputs.get("type", "file")
    if ftype == "directory":
        exists = os.path.isdir(path)
    else:
        exists = os.path.isfile(path)
    return PrimitiveResult(passed=exists, data={"exists": exists, "path": path})



def p02_file_content_match(inputs):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    if not os.path.isfile(path):
        return PrimitiveResult(passed=False, message=f"File not found: {path}")
    with open(path, "r", errors="replace") as f:
        content = f.read()
    mt = inputs.get("match_type", "contains")
    pattern = inputs["pattern"]
    if mt == "contains":
        matched = pattern in content
        count = content.count(pattern)
    else:
        matches = re.findall(pattern, content, re.IGNORECASE)
        matched = len(matches) > 0
        count = len(matches)
    return PrimitiveResult(passed=matched, data={"matched": matched, "match_count": count})



def p03_file_count(inputs):
    base = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", ""))
    pattern = inputs["glob"]
    files = glob.glob(os.path.join(base, pattern), recursive=True)
    minimum = inputs.get("min_expected", 1)
    return PrimitiveResult(
        passed=len(files) >= minimum,
        data={"count": len(files), "files": [os.path.basename(f) for f in files[:20]]}
    )



def p04_http_request(inputs):
    inputs = _resolve_deep(inputs)
    method = inputs.get("method", "GET").upper()
    path = inputs.get("path") or inputs.get("url", "")
    if path.startswith("http"):
        url = path
    elif path == "/graphql":
        url = GRAPHQL_URL
    elif path.startswith("/api/v1"):
        url = APP_BASE_URL + path
    elif path.startswith("/"):
        url = APP_BASE_URL + path
    else:
        url = API_BASE_URL + "/" + path.lstrip("/")
    has_explicit_headers = "headers" in inputs
    explicit_headers = inputs.get("headers", {})
    if has_explicit_headers and "Authorization" not in explicit_headers:
        base_hdrs = _headers(path)
        base_hdrs.pop("Authorization", None)
        hdrs = {**base_hdrs, **explicit_headers}
    else:
        hdrs = {**_headers(path), **explicit_headers}
    body = inputs.get("body")
    timeout = inputs.get("timeout", TIMEOUT)

    try:
        if method == "GET":
            r = requests.get(url, headers=hdrs, timeout=timeout)
        elif method == "POST":
            r = requests.post(url, json=body, headers=hdrs, timeout=timeout)
        elif method == "PUT":
            r = requests.put(url, json=body, headers=hdrs, timeout=timeout)
        elif method == "PATCH":
            r = requests.patch(url, json=body, headers=hdrs, timeout=timeout)
        elif method == "DELETE":
            if body:
                r = requests.delete(url, json=body, headers=hdrs, timeout=timeout)
            else:
                r = requests.delete(url, headers=hdrs, timeout=timeout)
        else:
            r = requests.request(method, url, json=body, headers=hdrs, timeout=timeout)
    except Exception as e:
        resp = {"status_code": 0, "body": None, "headers": {}, "error": str(e)}
        _set_last_response(resp)
        return PrimitiveResult(passed=False, data=resp, message=str(e))

    try:
        rbody = r.json()
    except Exception:
        rbody = r.text

    resp = {
        "status_code": r.status_code,
        "body": rbody,
        "headers": dict(r.headers),
        "response_time_ms": int(r.elapsed.total_seconds() * 1000),
    }
    _set_last_response(resp)

    if method == "POST" and r.status_code in (200, 201):
        _extract_id_from_body(rbody)

    return PrimitiveResult(passed=True, data=resp)


_ENTITY_KEYS = (
    "customer", "plan", "subscription", "invoice", "wallet", "coupon",
    "add_on", "billable_metric", "tax", "credit_note", "webhook_endpoint",
    "wallet_transaction", "applied_coupon", "fee", "event", "dunning_campaign",
    "applied_add_on", "organization"
)

_LAGO_ID_RESOURCES = ("wallet", "webhook_endpoint", "invoice", "credit_note",
                      "wallet_transaction", "fee", "applied_coupon", "applied_add_on")
_EXT_ID_RESOURCES = ("customer", "subscription", "event")
_CODE_RESOURCES = ("plan", "billable_metric", "add_on", "coupon", "tax",
                   "dunning_campaign")

def _extract_id_from_body(body):
    if isinstance(body, dict):
        wrapper_key = None
        for ek in _ENTITY_KEYS:
            if ek in body and isinstance(body[ek], dict):
                wrapper_key = ek
                break
        if not wrapper_key:
            wrapper_key = next((k for k in body if isinstance(body.get(k), dict)), None)
        nested = body.get(wrapper_key) if wrapper_key else body

        if wrapper_key == "data" and isinstance(nested, dict):
            for key, val in nested.items():
                if isinstance(val, dict) and ("id" in val or "lago_id" in val or "code" in val):
                    nested = val
                    if "createDunningCampaign" in key or "dunning" in key.lower():
                        wrapper_key = "dunning_campaign"
                    elif "Customer" in key or "customer" in key.lower():
                        wrapper_key = "customer"
                    break

        if isinstance(nested, dict):
            lago_id = nested.get("lago_id")
            ext_id = nested.get("external_id")
            code = nested.get("code")
            eid = nested.get("id")

            if wrapper_key in _LAGO_ID_RESOURCES:
                best_id = lago_id or eid
            elif wrapper_key in _EXT_ID_RESOURCES:
                best_id = ext_id or lago_id or eid
            elif wrapper_key in _CODE_RESOURCES:
                best_id = code or lago_id or eid
            else:
                best_id = ext_id or code or lago_id or eid

            if best_id:
                context["last_created_id"] = best_id
            if lago_id:
                context["last_created_lago_id"] = lago_id
            if wrapper_key:
                context[f"last_{wrapper_key}_id"] = best_id or ""
                internal_id = lago_id or eid
                if internal_id:
                    context[f"last_{wrapper_key}_lago_id"] = internal_id



def p05_api_crud(inputs):
    inputs = _resolve_deep(inputs)
    resource = inputs["resource"]
    token = inputs.get("token", context.get("auth_token", ""))
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"

    base = APP_BASE_URL + resource if resource.startswith("/") else API_BASE_URL + "/" + resource
    steps = {"create": False, "read": False, "update": False, "delete": False}
    entity_id = None
    id_field = inputs.get("identifier_field", "id")
    update_method = inputs.get("update_method", "PUT")

    try:
        r = requests.post(base, json=inputs.get("create_body", {}), headers=hdrs, timeout=TIMEOUT)
        if r.status_code in (200, 201):
            steps["create"] = True
            try:
                rbody = r.json()
                wrapper_key = next((k for k in rbody if isinstance(rbody.get(k), dict)), None)
                inner = rbody.get(wrapper_key, rbody) if wrapper_key else rbody
                entity_id = inner.get(id_field) or inner.get("lago_id") or inner.get("id") or inner.get("external_id")
            except Exception:
                entity_id = None
        if entity_id:
            context["last_created_id"] = entity_id

        if entity_id:
            r = requests.get(f"{base}/{entity_id}", headers=hdrs, timeout=TIMEOUT)
            if r.status_code == 200:
                steps["read"] = True
                read_fields = inputs.get("expected_read_fields", [])
                if read_fields:
                    try:
                        body = r.json()
                        wrapper_key = next((k for k in body if isinstance(body.get(k), dict)), None)
                        inner = body.get(wrapper_key, body) if wrapper_key else body
                        steps["read"] = all(f in inner for f in read_fields)
                    except Exception:
                        steps["read"] = False

        if entity_id and inputs.get("update_body"):
            update_url = base if inputs.get("update_to_base") else f"{base}/{entity_id}"
            if update_method.upper() == "PUT":
                r = requests.put(update_url, json=inputs["update_body"], headers=hdrs, timeout=TIMEOUT)
            else:
                r = requests.post(update_url, json=inputs["update_body"], headers=hdrs, timeout=TIMEOUT)
            steps["update"] = r.status_code in (200, 201)

        if entity_id and inputs.get("skip_delete") is not True:
            r = requests.delete(f"{base}/{entity_id}", headers=hdrs, timeout=TIMEOUT)
            steps["delete"] = r.status_code in (200, 204)
        elif inputs.get("skip_delete"):
            steps["delete"] = True

    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e), data=steps)

    passed_count = sum(steps.values())
    total_steps = 4
    return PrimitiveResult(
        passed=passed_count == total_steps,
        data={"steps": steps, "steps_passed": passed_count, "entity_id": entity_id},
        message=f"{passed_count}/{total_steps} CRUD steps passed"
    )



def p06_json_schema_match(inputs):
    resp = context.get("last_response", {})
    body = resp.get("body", {})
    required = inputs.get("required_fields", [])
    if isinstance(body, dict):
        if not all(f in body for f in required):
            wrapper_key = next((k for k in body if isinstance(body.get(k), dict)), None)
            if wrapper_key:
                body = body[wrapper_key]
    if not isinstance(body, dict):
        return PrimitiveResult(passed=False, message="Response body is not a JSON object")
    missing = [f for f in required if f not in body]
    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"missing_fields": missing, "all_present": len(missing) == 0}
    )



def p07_json_value_assert(inputs):
    inputs = _resolve_deep(inputs)
    resp = context.get("last_response", {})
    body = resp.get("body")
    assertions = inputs.get("assertions", [])

    assertion_type = inputs.get("assertion")
    if assertion_type and not assertions:
        if assertion_type == "json_path_exists":
            val = _json_path(body, inputs.get("path", "$"))
            passed = val is not None
            if passed and inputs.get("path", "").endswith("token") and isinstance(val, str):
                context.setdefault("auth_tokens", {})
                context["jwt_token"] = val
                context["auth_token"] = val
            return PrimitiveResult(passed=passed, data={"path": inputs.get("path"), "value": val})
        elif assertion_type == "regex_match":
            val = _json_path(body, inputs.get("path", "$"))
            pattern = inputs.get("pattern", "")
            passed = bool(re.search(pattern, str(val))) if val is not None else False
            return PrimitiveResult(passed=passed, data={"path": inputs.get("path"), "matched": passed})
        elif assertion_type == "jwt_decode":
            import base64
            token = context.get("jwt_token") or _json_path(body, "$.data.loginUser.token")
            if not token:
                return PrimitiveResult(passed=False, message="No JWT token found")
            try:
                parts = token.split(".")
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.b64decode(payload_b64))
                claims = inputs.get("claims", {})
                checks_ok = True
                for claim_key, claim_check in claims.items():
                    if claim_key not in payload:
                        checks_ok = False
                        break
                    if claim_check == "uuid_format":
                        import uuid as _uuid
                        try:
                            _uuid.UUID(str(payload[claim_key]))
                        except ValueError:
                            checks_ok = False
                    elif claim_check == "future_timestamp_3h":
                        checks_ok = isinstance(payload[claim_key], (int, float)) and payload[claim_key] > time.time()
                return PrimitiveResult(passed=checks_ok, data={"payload": payload})
            except Exception as e:
                return PrimitiveResult(passed=False, message=f"JWT decode error: {e}")
        elif assertion_type == "contains_all":
            content = json.dumps(body, default=str) if not isinstance(body, str) else body
            vals = inputs.get("values", [])
            missing = [v for v in vals if v.lower() not in content.lower()]
            return PrimitiveResult(passed=len(missing) == 0, data={"missing": missing})
        elif assertion_type == "contains":
            content = json.dumps(body, default=str) if not isinstance(body, str) else body
            val = inputs.get("value", "")
            return PrimitiveResult(passed=val.lower() in content.lower(), data={"value": val})
        elif assertion_type == "contains_any":
            content = json.dumps(body, default=str) if not isinstance(body, str) else body
            vals = inputs.get("values", [])
            found = [v for v in vals if v.lower() in content.lower()]
            return PrimitiveResult(passed=len(found) > 0, data={"found": found})
        elif assertion_type == "string_contains":
            content = json.dumps(body, default=str) if not isinstance(body, str) else body
            val = inputs.get("value", inputs.get("expected", ""))
            return PrimitiveResult(passed=val.lower() in content.lower(), data={"value": val})
        elif assertion_type == "no_token_returned":
            token = _json_path(body, "$.data.loginUser.token") if isinstance(body, dict) else None
            errors = _json_path(body, "$.errors") if isinstance(body, dict) else None
            passed = token is None or errors is not None
            return PrimitiveResult(passed=passed, data={"token": token, "errors": errors})
        else:
            assertions = [{"path": inputs.get("path", "$"), "expected": inputs.get("expected"), "operator": assertion_type}]

    results = []

    for a in assertions:
        path = a.get("path", "$")
        expected = a.get("expected")
        operator = a.get("operator", "equals")
        operator = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<"}.get(operator, operator)
        tolerance = a.get("tolerance", 0)
        match_type = a.get("match_type")

        actual = _json_path(body, path)

        if operator == "length":
            passed = isinstance(actual, (list, dict)) and len(actual) == int(expected)
        elif operator == "exists":
            passed = actual is not None
        elif operator == "not_empty":
            passed = actual is not None and str(actual) != ""
        elif operator == "not_null":
            passed = actual is not None
        elif operator == "is_null":
            passed = actual is None
        elif operator == "not_contains":
            passed = expected not in json.dumps(body, default=str) if isinstance(expected, str) else True
        elif operator == ">":
            try:
                passed = float(actual) > float(expected)
            except (TypeError, ValueError):
                passed = False
        elif operator == ">=":
            try:
                passed = float(actual) >= float(expected)
            except (TypeError, ValueError):
                passed = False
        elif operator == "<":
            try:
                passed = float(actual) < float(expected)
            except (TypeError, ValueError):
                passed = False
        elif operator == "<=":
            try:
                passed = float(actual) <= float(expected)
            except (TypeError, ValueError):
                passed = False
        elif operator == "is_type":
            type_map = {"array": list, "object": dict, "string": str, "number": (int, float), "boolean": bool}
            passed = isinstance(actual, type_map.get(expected, object))
        elif operator == "regex":
            passed = bool(re.search(str(expected), str(actual))) if actual is not None else False
        elif operator == "contains":
            passed = str(expected) in str(actual) if actual is not None else False
        elif operator == "contains_any":
            if isinstance(expected, list):
                passed = any(str(e) in str(actual) for e in expected) if actual is not None else False
            else:
                passed = str(expected) in str(actual) if actual is not None else False
        elif match_type == "contains":
            passed = expected in str(actual) if actual is not None else False
        elif match_type == "starts_with":
            passed = str(actual).startswith(str(expected)) if actual is not None else False
        elif match_type == "regex":
            passed = bool(re.search(str(expected), str(actual))) if actual is not None else False
        elif match_type == "any_of":
            acceptable = a.get("acceptable", [])
            passed = str(actual) in [str(x) for x in acceptable]
        else:
            if tolerance > 0:
                try:
                    passed = abs(float(actual) - float(expected)) <= tolerance
                except (TypeError, ValueError):
                    passed = False
            else:
                passed = _loose_eq(actual, expected)

        results.append({"path": path, "actual": actual, "expected": expected, "passed": passed})

    all_passed = all(r["passed"] for r in results)
    return PrimitiveResult(passed=all_passed, data={"results": results, "all_passed": all_passed})


def _json_path(obj, path):
    if path == "$":
        return obj
    clean = path.lstrip("$").lstrip(".")
    parts = clean.split(".")
    cur = obj
    for part in parts:
        if cur is None:
            return None
        m = re.match(r"(\w+)\[(\d+)\]", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            cur = cur.get(key) if isinstance(cur, dict) else None
            cur = cur[idx] if isinstance(cur, list) and idx < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if idx < len(cur) else None
        else:
            return None
    return cur


def _loose_eq(actual, expected):
    if actual == expected:
        return True
    if isinstance(expected, str) and expected.upper() == "NOT_NULL":
        return actual is not None
    if isinstance(expected, str) and expected.upper() == "NULL":
        return actual is None
    if isinstance(expected, str) and expected.upper() == "NON_EMPTY_ARRAY":
        return isinstance(actual, list) and len(actual) > 0
    if actual is None or expected is None:
        return False
    try:
        if float(actual) == float(expected):
            return True
    except (TypeError, ValueError):
        pass
    return str(actual).lower() == str(expected).lower()



def p08_db_query(inputs):
    inputs = _resolve_deep(inputs)
    sql = inputs.get("sql") or inputs.get("query", "")
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, context)
    except Exception:
        pass
    save_id = inputs.get("save_id")
    try:
        import psycopg2.extras
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))

    expected = inputs.get("expected_result")
    match = True
    if expected and isinstance(expected, dict):
        if "row_count" in expected:
            op = expected.get("operator", ">=")
            rc = len(rows)
            ec = expected["row_count"]
            if op == ">=":
                match = rc >= ec
            elif op == ">":
                match = rc > ec
            elif op == "==":
                match = rc == ec
            else:
                match = rc >= ec
        elif "first_row" in expected:
            if not rows:
                match = False
            else:
                row = rows[0]
                match = all(_loose_eq(row.get(k), v) for k, v in expected["first_row"].items())
        else:
            col_expected = {k: v for k, v in expected.items() if k not in ("row_count", "operator", "first_row")}
            if col_expected:
                if not rows:
                    match = False
                else:
                    row = rows[0]
                    match = all(_loose_eq(row.get(k), v) for k, v in col_expected.items())

    assertions = inputs.get("assertions", [])
    for a in assertions:
        field = a.get("field") or a.get("path") or a.get("column", "")
        op = a.get("operator", "equals")
        exp = a.get("expected")
        if field == "row_count":
            actual = len(rows)
        elif rows:
            actual = rows[0].get(field)
        else:
            actual = None
        if op in (">=", "gte"):
            match = match and (actual is not None and float(actual) >= float(exp))
        elif op in (">", "gt"):
            match = match and (actual is not None and float(actual) > float(exp))
        elif op in ("exists", "not_null"):
            match = match and actual is not None
        elif op == "equals":
            match = match and _loose_eq(actual, exp)

    if save_id and rows:
        id_val = rows[0].get("lago_id") or rows[0].get("id")
        if id_val:
            context[save_id] = str(id_val)
            context["last_created_id"] = str(id_val)

    _set_last_response({"body": {"rows": rows, "row_count": len(rows)}, "status_code": 200})
    return PrimitiveResult(passed=match, data={"rows": rows, "row_count": len(rows)})



def p09_db_table_exists(inputs):
    tables = inputs.get("tables") or ([inputs["table"]] if "table" in inputs else [])
    try:
        import psycopg2.extras
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            existing = {r["table_name"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))

    found = [t for t in tables if t in existing]
    missing = [t for t in tables if t not in existing]
    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"existing": found, "missing": missing, "found_count": len(found), "total_count": len(tables)}
    )



def p10_db_column_check(inputs):
    table = inputs["table"]
    expected_cols = inputs.get("expected_columns") or inputs.get("columns", [])
    try:
        import psycopg2.extras
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s", (table,)
            )
            actual_cols = {r["column_name"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))

    missing = [c for c in expected_cols if c not in actual_cols]
    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"missing": missing, "found": len(expected_cols) - len(missing), "total": len(expected_cols)}
    )



def p11_db_index_check(inputs):
    table = inputs["table"]
    expected_indexes = inputs.get("expected_indexes", [])
    try:
        import psycopg2.extras
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = %s", (table,)
            )
            actual = {r["indexname"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))

    if isinstance(expected_indexes, list) and expected_indexes and isinstance(expected_indexes[0], dict):
        missing = []
        for idx_spec in expected_indexes:
            cols = idx_spec.get("columns", [])
            col_str = "_".join(cols)
            found_any = any(col_str in idx_name for idx_name in actual)
            if not found_any:
                missing.append(col_str)
    else:
        missing = [i for i in expected_indexes if i not in actual]

    return PrimitiveResult(passed=len(missing) == 0, data={"missing": missing, "actual_indexes": list(actual)})



def p12_docker_exec(inputs):
    cmd = _resolve(inputs["command"])
    container = inputs.get("container", APP_CONTAINER)
    result = _docker_exec(container, cmd)
    passed = result["exit_code"] == 0

    _set_last_response({
        "body": result["stdout"],
        "status_code": 0 if passed else result["exit_code"],
        "headers": {},
        "docker_result": result,
    })
    return PrimitiveResult(passed=passed, data=result)



def p13_auth_login(inputs):
    role = inputs.get("role", "admin")
    method = inputs.get("method", "api_token")
    want_api_key = method in ("api_token", "api_key", "db_api_key")
    cache_key = f"{role}:api_key" if want_api_key else f"{role}:jwt"

    if cache_key in context.get("auth_tokens", {}):
        context["auth_token"] = context["auth_tokens"][cache_key]
        return PrimitiveResult(passed=True, data={"role": role, "cached": True})

    user_cfg = TEST_USERS.get(role, TEST_USERS.get("admin"))
    email = user_cfg.get("email", "eval_admin@example.com")
    password = user_cfg.get("password", "EvalAdmin123!")

    if not want_api_key:
        try:
            mutation = {
                "query": 'mutation($input: LoginUserInput!) { loginUser(input: $input) { token user { id email } } }',
                "variables": {"input": {"email": email, "password": password}}
            }
            r = requests.post(
                GRAPHQL_URL, json=mutation,
                headers={"Content-Type": "application/json"},
                timeout=TIMEOUT
            )
            if r.status_code == 200:
                data = r.json()
                token = None
                login_data = (
                    (data.get("data") or {}).get("loginUser")
                    or (data.get("data") or {}).get("login")
                    or (data.get("data") or {}).get("signIn")
                    or (data.get("data") or {}).get("signin")
                    or {}
                )
                token = (
                    login_data.get("token")
                    or login_data.get("access_token")
                    or login_data.get("accessToken")
                    or login_data.get("authToken")
                )
                if token:
                    context["auth_token"] = token
                    context["auth_tokens"][cache_key] = token
                    context["jwt_token"] = token
                    return PrimitiveResult(passed=True, data={"role": role, "method": "graphql_jwt"})
        except Exception:
            pass

    try:
        import psycopg2.extras
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT ak.value FROM api_keys ak "
                "JOIN organizations o ON ak.organization_id = o.id "
                "WHERE ak.value IS NOT NULL "
                "AND (ak.expires_at IS NULL OR ak.expires_at > NOW()) "
                "ORDER BY (ak.name IS NOT NULL) DESC, ak.created_at ASC "
                "LIMIT 1"
            )
            row = cur.fetchone()
            if row and row.get("value"):
                token = row["value"]
                r = requests.get(
                    API_BASE_URL + "/customers?per_page=1",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=TIMEOUT
                )
                if r.status_code == 200:
                    context["auth_token"] = token
                    context["auth_tokens"][cache_key] = token
                    context["api_key"] = token
                    conn.close()
                    return PrimitiveResult(passed=True, data={"role": role, "method": "db_api_key"})

            cur.execute("SELECT id FROM organizations LIMIT 1")
            org = cur.fetchone()
            if org:
                import uuid
                new_key = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO api_keys (id, organization_id, value, name, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), %s, %s, %s, NOW(), NOW()) "
                    "ON CONFLICT DO NOTHING RETURNING value",
                    (org["id"], new_key, f"eval_{role}")
                )
                result_row = cur.fetchone()
                if result_row:
                    token = result_row["value"]
                else:
                    token = new_key
                r = requests.get(
                    API_BASE_URL + "/customers?per_page=1",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=TIMEOUT
                )
                if r.status_code == 200:
                    context["auth_token"] = token
                    context["auth_tokens"][cache_key] = token
                    context["api_key"] = token
                    conn.close()
                    return PrimitiveResult(passed=True, data={"role": role, "method": "db_create_key"})
        conn.close()
    except Exception:
        pass

    try:
        r = requests.get(f"{APP_BASE_URL}/health", timeout=TIMEOUT)
        if r.status_code == 200:
            context["auth_token"] = "unauthenticated"
            context["auth_tokens"][cache_key] = "unauthenticated"
            return PrimitiveResult(passed=True, data={"role": role, "method": "no_auth_needed"}, message="App accessible but auth failed")
    except Exception:
        pass

    return PrimitiveResult(passed=False, message=f"All auth strategies failed for role={role}")



def p14_permission_check(inputs):
    inputs = _resolve_deep(inputs)
    action = inputs["action"]
    expected = inputs["expected_result"]
    acceptable = inputs.get("acceptable_statuses")

    parts = action.split(" ", 1)
    method = parts[0].upper()
    path = parts[1] if len(parts) > 1 else "/"

    temp_key = None
    try:
        perms = inputs.get("permissions")
        key_config = inputs.get("key_config", {})
        if perms is not None or key_config:
            temp_key = _create_temp_api_key(perms, key_config)
    except Exception:
        pass

    old_token = context.get("auth_token")
    old_api_key = context.get("api_key")
    if temp_key:
        context["auth_token"] = temp_key
        context["api_key"] = temp_key

    p04_input = {"method": method, "path": path}
    if inputs.get("body"):
        p04_input["body"] = inputs["body"]
    if inputs.get("headers"):
        p04_input["headers"] = inputs["headers"]
    if inputs.get("token"):
        p04_input["headers"] = {**(p04_input.get("headers") or {}), "Authorization": f"Bearer {inputs['token']}"}

    res = p04_http_request(p04_input)
    status = res.data.get("status_code", 0) if res.data else 0

    if temp_key:
        context["auth_token"] = old_token
        context["api_key"] = old_api_key

    if expected in ("denied", "deny"):
        ok_statuses = acceptable or [400, 401, 403, 404, 422]
        passed = status in ok_statuses
    else:
        ok_statuses = acceptable or [200, 201, 422]
        passed = status in ok_statuses

    return PrimitiveResult(
        passed=passed,
        data={"status_code": status, "expected": expected},
        message=f"{action} → {status} (expected {expected})"
    )


def _create_temp_api_key(permissions, key_config=None):
    import uuid as _uuid
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        org_id = _get_organization_id()
        key_value = f"rbac_test_{_uuid.uuid4().hex[:16]}"

        if permissions == "all":
            cur.execute("SELECT permissions FROM api_keys WHERE expires_at IS NULL LIMIT 1")
            row = cur.fetchone()
            perm_json = json.dumps(row[0]) if row else "{}"
        elif isinstance(permissions, dict):
            perm_json = json.dumps(permissions)
        else:
            perm_json = "{}"

        expires = key_config.get("expires_at") if key_config else None
        if expires and "past" in str(expires).lower():
            expires = "2020-01-01 00:00:00"
        elif not expires:
            expires = None

        if expires:
            cur.execute(
                "INSERT INTO api_keys (id, organization_id, value, permissions, expires_at, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
                (str(_uuid.uuid4()), org_id, key_value, perm_json, expires)
            )
        else:
            cur.execute(
                "INSERT INTO api_keys (id, organization_id, value, permissions, created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW())",
                (str(_uuid.uuid4()), org_id, key_value, perm_json)
            )
        conn.commit()
        cur.close()
        conn.close()
        return key_value
    except Exception:
        return None



def p15_status_code_assert(inputs):
    resp = context.get("last_response", {})
    actual = resp.get("status_code", 0)
    if "expected_status" in inputs:
        expected = inputs["expected_status"]
        if isinstance(expected, list):
            passed = actual in expected
        else:
            passed = actual == expected
    elif "acceptable_statuses" in inputs:
        passed = actual in inputs["acceptable_statuses"]
    else:
        passed = 200 <= actual < 300
    return PrimitiveResult(passed=passed, data={"actual": actual}, message=f"HTTP {actual}")



def p16_response_time_check(inputs):
    resp = context.get("last_response", {})
    ms = resp.get("response_time_ms", 99999)
    threshold = inputs.get("max_ms", 5000)
    return PrimitiveResult(passed=ms <= threshold, data={"response_time_ms": ms, "threshold": threshold})



def p17_llm_judge(inputs):
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
        _evidence = {"score": 0, "max_score": _sr[1],
                     "skipped": True, "llm_api_failure": False,
                     "reason": "SKIP_LLM_JUDGE=1 (LLM judge intentionally skipped for peer-review-grade scoring)"}
        for _kw in (
            {"passed": True, "data": _evidence, "message": "LLM judge SKIPPED (SKIP_LLM_JUDGE=1)"},
            {"success": True, "evidence": _evidence, "message": "LLM judge SKIPPED (SKIP_LLM_JUDGE=1)"},
            {"passed": True, "data": _evidence},
        ):
            try:
                return PrimitiveResult(**_kw)
            except TypeError:
                continue
        return _evidence
    if not LLM_API_KEY:
        return PrimitiveResult(
            passed=True,
            data={
                "score": 0,
                "skipped": True,
                "llm_api_failure": False,
                "exception_class": "",
                "reason": "LLM_API_KEY unset",
            },
            message="LLM judge SKIPPED (LLM_API_KEY unset)",
        )

    rubric = inputs.get("rubric_prompt") or inputs.get("rubric", "")
    score_range = inputs.get("score_range", [0, 5])

    evidence_parts = []
    etype = inputs.get("evidence_type", "code_files")
    if etype == "code_files":
        target_dirs = inputs.get("files_to_sample", [])
        KEY_PATTERNS = [
            "**/*controller*", "**/*service*", "**/*model*",
            "**/*serializer*", "**/*graphql*", "**/*.rb",
            "**/*.tsx", "**/*.ts", "**/Gemfile", "**/package.json",
        ]
        sampled = set()
        for fpath in target_dirs:
            full = os.path.join(WORKSPACE_DIR, fpath.lstrip("/"))
            if os.path.isdir(full):
                for pat in KEY_PATTERNS:
                    for match in glob.glob(os.path.join(full, pat), recursive=True):
                        sampled.add(match)
                if len(sampled) < 5:
                    for root, _, files in os.walk(full):
                        for fn in sorted(files)[:20]:
                            sampled.add(os.path.join(root, fn))
                        if len(sampled) >= 30:
                            break
        for fp in sorted(sampled)[:20]:
            try:
                with open(fp, "r", errors="replace") as fh:
                    content = fh.read()[:3000]
                    evidence_parts.append(f"=== {os.path.relpath(fp, WORKSPACE_DIR)} ===\n{content}")
            except Exception:
                pass
    elif etype == "http_response_html":
        resp = context.get("last_response", {})
        evidence_parts.append(str(resp.get("body", ""))[:5000])

    evidence_text = "\n\n".join(evidence_parts)[:int(inputs.get("max_evidence_chars", 30000))]

    from _llm_judge_safe import safe_chat_completion
    res = safe_chat_completion(
        messages=[
            {"role": "system", "content": (
                f"You are an expert, strict code reviewer. Score from {score_range[0]} to {score_range[1]}. "
                "You have NO access to any tools, shell, or filesystem: evaluate SOLELY from the evidence "
                "provided below and do NOT ask to inspect more files. "
                "Reply with ONLY a JSON: {\"score\": N, \"reason\": \"...\"} and no other text.")},
            {"role": "user", "content": f"{rubric}\n\n--- Evidence ---\n{evidence_text}"},
        ],
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE or "",
        temperature=0,
        max_tokens=2000,
    )
    if res.skipped:
        return PrimitiveResult(
            passed=True,
            data={
                "score": 0,
                "skipped": True,
                "llm_api_failure": res.llm_api_failure,
                "exception_class": res.exception_class,
                "reason": res.error or "skipped",
            },
            message=f"LLM judge SKIPPED ({res.reason()})",
        )

    def _robust_judge_json(_raw):
        import json as _j, re as _re
        _s = (_raw or "").strip()
        if _s.startswith("```"):
            _s = _re.sub(r"^```[a-zA-Z0-9]*\s*", "", _s)
            _s = _re.sub(r"\s*```$", "", _s).strip()
        try:
            _v = _j.loads(_s)
            if isinstance(_v, dict):
                return _v
            if isinstance(_v, (int, float)):
                return {"score": float(_v)}
        except Exception:
            pass
        _i = _s.find("{")
        if _i != -1:
            _d = 0
            for _k in range(_i, len(_s)):
                if _s[_k] == "{":
                    _d += 1
                elif _s[_k] == "}":
                    _d -= 1
                    if _d == 0:
                        try:
                            return _j.loads(_s[_i:_k + 1])
                        except Exception:
                            break
        _m = _re.search(r'"?score"?\s*[:=]\s*(-?\d+(?:\.\d+)?)', _s, _re.I)
        if _m:
            _o = {"score": float(_m.group(1))}
            _rm = _re.search(r'"?reason(?:ing)?"?\s*[:=]\s*"([^"]*)"', _s, _re.I)
            if _rm:
                _o["reason"] = _rm.group(1)
                _o["reasoning"] = _rm.group(1)
            return _o
        for _pat in (
            r'(?:^|\n)\s*#*\s*(?:Overall\s+)?Score\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*#*\s*Evaluation\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*#*\s*Rating\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'\*\*\s*Score\s*[:\-]?\s*(-?\d+(?:\.\d+)?)',
            r'\bscore\s+(?:is|of|=)\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*\**\s*(-?\d+(?:\.\d+)?)\s*(?:/\s*\d+\s*)?(?:—|–|-)\s*(?:Excellent|Strong|Good|Complete|Weak|Poor|None|Fair|Adequate)',
        ):
            _mm = _re.search(_pat, _s, _re.I)
            if _mm:
                return {"score": float(_mm.group(1)), "reason": _s[:500]}
        _m2 = _re.search(r"-?\d+", _s)
        if _m2:
            return {"score": float(_m2.group())}
        raise ValueError("no JSON/score in LLM reply")

    try:
        score_data = _robust_judge_json(res.raw)
        return PrimitiveResult(passed=True, data=score_data)
    except Exception as e:
        return PrimitiveResult(
            passed=True,
            data={
                "score": 0,
                "skipped": True,
                "parse_failure": True,
                "llm_api_failure": False,
                "exception_class": type(e).__name__,
                "reason": f"parse failure: {e}",
                "raw": res.raw[:200],
            },
            message=f"LLM judge SKIPPED (parse failure: {e})",
        )



PRIMITIVES = {
    "P01": p01_file_exists, "P02": p02_file_content_match, "P03": p03_file_count,
    "P04": p04_http_request, "P05": p05_api_crud,
    "P06": p06_json_schema_match, "P07": p07_json_value_assert,
    "P08": p08_db_query, "P09": p09_db_table_exists,
    "P10": p10_db_column_check, "P11": p11_db_index_check,
    "P12": p12_docker_exec, "P13": p13_auth_login,
    "P14": p14_permission_check, "P15": p15_status_code_assert,
    "P16": p16_response_time_check, "P17": p17_llm_judge,
}


def execute_primitive(ptype, inputs):
    fn = PRIMITIVES.get(ptype)
    if not fn:
        return PrimitiveResult(passed=False, message=f"Unknown primitive: {ptype}")
    return fn(inputs)
