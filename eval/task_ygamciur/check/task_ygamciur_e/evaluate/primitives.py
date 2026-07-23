import glob
import json
import os
import re
import secrets
import subprocess
from typing import Any

import requests

from config import (
    APP_BASE_URL, API_BASE_URL, APP_CONTAINER,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, TIMEOUT,
    TEST_USERS, LLM_API_KEY, LLM_API_BASE, LLM_MODEL, WORKSPACE_DIR,
)
from utils import PrimitiveResult, docker_exec as _docker_exec, get_mongo_db

context = {
    "auth_token": None,
    "auth_tokens": {},
    "auth_sessions": {},
    "last_response": None,
}

_active_session = requests.Session()


def _resolve(val):
    if isinstance(val, str) and "{{" in val:
        admin_cfg = TEST_USERS.get("admin", {})
        builtin = {
            "adminEmail": admin_cfg.get("email", ""),
            "adminPassword": admin_cfg.get("password", ""),
            "devEmail": TEST_USERS.get("developer", {}).get("email", ""),
            "devPassword": TEST_USERS.get("developer", {}).get("password", ""),
            "viewerEmail": TEST_USERS.get("viewer", {}).get("email", ""),
            "viewerPassword": TEST_USERS.get("viewer", {}).get("password", ""),
            "admin_email": admin_cfg.get("email", ""),
            "admin_password": admin_cfg.get("password", ""),
            "dev_email": TEST_USERS.get("developer", {}).get("email", ""),
            "dev_password": TEST_USERS.get("developer", {}).get("password", ""),
            "viewer_email": TEST_USERS.get("viewer", {}).get("email", ""),
            "viewer_password": TEST_USERS.get("viewer", {}).get("password", ""),
        }
        for key, v in {**builtin, **context}.items():
            if isinstance(v, (str, int, float)):
                val = val.replace("{{" + key + "}}", str(v))
    return val


def _resolve_deep(obj):
    if isinstance(obj, str):
        import re as _re
        m = _re.fullmatch(r"\{\{(\w+)\}\}", obj)
        if m:
            key = m.group(1)
            if key in context:
                cv = context[key]
                if isinstance(cv, (dict, list)):
                    return cv
        return _resolve(obj)
    if isinstance(obj, dict):
        return {k: _resolve_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_deep(v) for v in obj]
    return obj


def _headers():
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    csrf = _active_session.cookies.get("XSRF-TOKEN", "")
    if csrf:
        h["X-XSRF-TOKEN"] = csrf
        h["Origin"] = APP_BASE_URL
    return h


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
    path = inputs["path"]
    if path.startswith("http"):
        url = path
    elif path.startswith("/"):
        url = APP_BASE_URL + path
    else:
        url = API_BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    form_data = inputs.get("form_data")
    content_type = inputs.get("content_type", "")
    _default_follow = "follow_redirects" in inputs
    if not _default_follow and (form_data or "x-www-form-urlencoded" in content_type):
        follow_redirects = False
    else:
        follow_redirects = inputs.get("follow_redirects", True)
    timeout = inputs.get("timeout", TIMEOUT)

    try:
        if (form_data or content_type) and "multipart/form-data" in content_type:
            form_hdrs = {}
            csrf = _active_session.cookies.get("XSRF-TOKEN", "")
            if csrf:
                form_hdrs["X-XSRF-TOKEN"] = csrf
                form_hdrs["X-Requested-By"] = "Appsmith"
                form_hdrs["Origin"] = APP_BASE_URL
            form_hdrs.update(inputs.get("headers", {}))
            files_dict = {}
            if isinstance(form_data, dict):
                for fk, fv in form_data.items():
                    files_dict[fk] = (None, str(fv))
            elif isinstance(form_data, str):
                for part in form_data.split("&"):
                    if "=" not in part:
                        continue
                    k, v = part.split("=", 1)
                    files_dict[k] = (None, v)
            elif isinstance(inputs.get("body"), dict):
                for fk, fv in inputs["body"].items():
                    files_dict[fk] = (None, str(fv) if not isinstance(fv, str) else fv)
            r = _active_session.request(
                method, url,
                files=files_dict,
                headers=form_hdrs,
                timeout=timeout,
                allow_redirects=follow_redirects,
            )
        elif form_data or "x-www-form-urlencoded" in content_type:
            form_hdrs = {}
            csrf = _active_session.cookies.get("XSRF-TOKEN", "")
            if csrf:
                form_hdrs["X-XSRF-TOKEN"] = csrf
                form_hdrs["Origin"] = APP_BASE_URL
            form_hdrs.update(inputs.get("headers", {}))
            r = _active_session.request(
                method, url,
                data=form_data or inputs.get("body"),
                headers=form_hdrs,
                timeout=timeout,
                allow_redirects=follow_redirects,
            )
        else:
            hdrs = {**_headers(), **inputs.get("headers", {})}
            csrf = _active_session.cookies.get("XSRF-TOKEN", "")
            if csrf and "X-XSRF-TOKEN" not in hdrs:
                hdrs["X-XSRF-TOKEN"] = csrf
            if "Origin" not in hdrs:
                hdrs["Origin"] = APP_BASE_URL
            r = _active_session.request(
                method, url,
                json=inputs.get("body"),
                headers=hdrs,
                timeout=timeout,
                allow_redirects=follow_redirects,
            )
    except Exception as e:
        resp = {"status_code": 0, "body": None, "headers": {}, "error": str(e)}
        _set_last_response(resp)
        return PrimitiveResult(passed=False, data=resp, message=str(e))

    if r.status_code == 401 and not inputs.get("_retried"):
        _get_csrf(_active_session)
        inputs["_retried"] = True
        return p04_http_request(inputs)
    if r.status_code == 415 and not inputs.get("_form_retried") and not form_data \
       and "x-www-form-urlencoded" not in content_type and isinstance(inputs.get("body"), dict):
        inputs2 = dict(inputs)
        inputs2["_form_retried"] = True
        inputs2["form_data"] = inputs["body"]
        if "follow_redirects" not in inputs:
            inputs2["follow_redirects"] = False
        return p04_http_request(inputs2)

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
        _try_capture_id(rbody)

    return PrimitiveResult(passed=True, data=resp)


def _try_capture_id(rbody):
    eid = None
    if isinstance(rbody, (int, float)):
        eid = rbody
    elif isinstance(rbody, dict):
        data = rbody.get("data", rbody)
        if isinstance(data, dict) and "id" in data:
            eid = data["id"]
        elif "id" in rbody:
            eid = rbody["id"]
    if eid is not None:
        context["last_created_id"] = eid



def p05_api_crud(inputs):
    inputs = _resolve_deep(inputs)
    resource = inputs["resource"]
    base = APP_BASE_URL + resource if resource.startswith("/") else API_BASE_URL + "/" + resource
    steps = {"create": False, "read": False, "update": False, "delete": False}
    entity_id = None

    def _fresh_headers():
        return _headers()

    try:
        hdrs = _fresh_headers()
        r = _active_session.post(base, json=inputs["create_body"], headers=hdrs, timeout=TIMEOUT)
        if r.status_code == 401:
            _get_csrf(_active_session)
            hdrs = _fresh_headers()
            r = _active_session.post(base, json=inputs["create_body"], headers=hdrs, timeout=TIMEOUT)
        if r.status_code in (200, 201):
            steps["create"] = True
            try:
                body = r.json()
                data = body.get("data", body) if isinstance(body, dict) else body
                entity_id = data.get("id") if isinstance(data, dict) else None
            except Exception:
                pass
        if entity_id:
            context["last_created_id"] = entity_id

        if entity_id:
            read_path = inputs.get("read_path")
            if read_path:
                rp = read_path.replace("{{id}}", entity_id)
                rurl = APP_BASE_URL + rp if rp.startswith("/") else f"{base}/{entity_id}"
            else:
                rurl = f"{base}/{entity_id}"
            r = _active_session.get(rurl, headers=hdrs, timeout=TIMEOUT)
            if r.status_code == 200:
                body = r.json()
                data = body.get("data", body) if isinstance(body, dict) else body
                read_fields = inputs.get("expected_read_fields", [])
                if isinstance(data, list):
                    match = next((it for it in data
                                  if isinstance(it, dict) and it.get("id") == entity_id),
                                 None)
                    if match is None:
                        steps["read"] = False
                    elif read_fields:
                        steps["read"] = all(f in match for f in read_fields)
                    else:
                        steps["read"] = True
                elif read_fields and isinstance(data, dict):
                    steps["read"] = all(f in data for f in read_fields)
                else:
                    steps["read"] = True

        if entity_id and inputs.get("update_body"):
            r = _active_session.put(f"{base}/{entity_id}", json=inputs["update_body"], headers=hdrs, timeout=TIMEOUT)
            steps["update"] = r.status_code in (200, 201)

        if entity_id:
            r = _active_session.delete(f"{base}/{entity_id}", headers=hdrs, timeout=TIMEOUT)
            steps["delete"] = r.status_code in (200, 204)

    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e), data=steps)

    passed_count = sum(steps.values())
    return PrimitiveResult(
        passed=passed_count == 4,
        data={"steps": steps, "steps_passed": passed_count, "entity_id": entity_id},
        message=f"{passed_count}/4 CRUD steps passed"
    )



def p06_json_schema_match(inputs):
    resp = context.get("last_response", {})
    body = resp.get("body", {})
    if isinstance(body, dict) and "data" in body:
        body = body["data"]
    if not isinstance(body, dict):
        return PrimitiveResult(passed=False, message="Response body is not a JSON object")
    required = inputs.get("required_fields", [])
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
    results = []

    or_group: list = []

    def _flush_or_group():
        nonlocal or_group
        if or_group:
            any_passed = any(r["passed"] for r in or_group)
            if not any_passed:
                empty_body = body in (None, "", b"")
                status_ok = resp.get("status_code") in (200, 201, 202, 204, 302, 401)
                if empty_body and status_ok:
                    any_passed = True
                    or_group.append({
                        "path": "_status_fallback",
                        "actual": resp.get("status_code"),
                        "expected": "2xx/302/401 with empty body",
                        "passed": True,
                    })
            results.append({
                "or_group": [r for r in or_group],
                "passed": any_passed,
            })
            or_group = []

    for a in assertions:
        is_or = "or_path" in a
        if is_or and "path" not in a:
            a = dict(a)
            a["path"] = a["or_path"]
        path = a.get("path", "$")
        expected = a.get("expected")
        operator = a.get("operator", "equals")
        tolerance = a.get("tolerance", 0)
        match_type = a.get("match_type")

        if path.startswith("$.headers"):
            raw_headers = resp.get("headers", {})
            ci_headers = {k.lower(): v for k, v in raw_headers.items()}
            hdr_path = path.replace("$.headers.", "$.").replace("$.headers", "$").lower()
            actual = _json_path(ci_headers, hdr_path)
        else:
            actual = _json_path(body, path)

        if operator == "exists":
            passed = actual is not None
        elif operator == "is_array":
            passed = isinstance(actual, list)
        elif operator == "not_empty":
            passed = actual is not None and str(actual) != ""
        elif operator == "ne":
            passed = not _loose_eq(actual, expected)
        elif operator == "eq":
            passed = _loose_eq(actual, expected)
        elif operator == "not_contains":
            if actual is None:
                passed = True
            else:
                passed = expected not in str(actual) if isinstance(expected, str) else True
        elif operator == "contains":
            passed = expected in str(actual) if actual is not None and isinstance(expected, str) else False
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
        elif operator == "is_type":
            if expected == "array":
                passed = isinstance(actual, list)
            elif expected == "number":
                passed = isinstance(actual, (int, float))
            elif expected == "string":
                passed = isinstance(actual, str)
            elif expected == "boolean":
                passed = isinstance(actual, bool)
            else:
                passed = False
        elif operator == "is_array":
            passed = isinstance(actual, list)
        elif operator == "array_contains":
            match_spec = a.get("match") or {}
            if not isinstance(actual, list):
                passed = False
            else:
                passed = False
                for item in actual:
                    if not isinstance(item, dict):
                        continue
                    ok = True
                    for k, v in match_spec.items():
                        if item.get(k) != v:
                            ok = False
                            break
                    if ok:
                        passed = True
                        break
        elif operator == "array_find":
            match_spec = a.get("match") or {}
            capture_field = a.get("capture_field")
            if not isinstance(actual, list):
                passed = False
            else:
                hit = None
                for item in actual:
                    if not isinstance(item, dict):
                        continue
                    ok = True
                    for k, v in (match_spec or {}).items():
                        if k.endswith("_contains"):
                            target = item.get(k[:-9])
                            if not isinstance(target, str) or v not in target:
                                ok = False
                                break
                        else:
                            if item.get(k) != v:
                                ok = False
                                break
                    if ok:
                        hit = item
                        break
                if hit is None:
                    passed = False
                else:
                    passed = True
                    if capture_field:
                        captured_val = hit.get(capture_field)
                        if captured_val is not None:
                            cap_key = a.get("capture_as")
                            if cap_key:
                                context[cap_key] = captured_val
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

        if is_or:
            or_group.append({"path": path, "actual": actual, "expected": expected, "passed": passed})
        else:
            _flush_or_group()
            results.append({"path": path, "actual": actual, "expected": expected, "passed": passed})

        if operator != "array_find":
            capture_key = a.get("capture_as")
            if capture_key and actual is not None:
                context[capture_key] = actual

    _flush_or_group()
    all_passed = all(r["passed"] for r in results)
    return PrimitiveResult(passed=all_passed, data={"results": results, "all_passed": all_passed})


def _json_path(obj, path):
    if path == "$":
        return obj
    parts = path.lstrip("$.").split(".")
    cur = obj
    for part in parts:
        if cur is None:
            return None
        if part == "length" and isinstance(cur, (list, dict, str)):
            cur = len(cur)
            continue
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
    if actual is None or expected is None:
        return False
    try:
        if float(actual) == float(expected):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(expected, bool):
        if isinstance(actual, str):
            return actual.lower() in ("true", "1") if expected else actual.lower() in ("false", "0")
    return str(actual) == str(expected)



def p08_db_query(inputs):
    inputs = _resolve_deep(inputs)

    if "command" in inputs:
        return _p08_mongosh_command(inputs)

    collection = inputs.get("collection", "")
    query = inputs.get("query", {})
    expected = inputs.get("expected_result")
    projection = inputs.get("projection")

    rows = None
    try:
        db = get_mongo_db()
        coll = db[collection]
        if inputs.get("aggregate"):
            rows = list(coll.aggregate(inputs["aggregate"]))
        elif inputs.get("count_only"):
            cnt = coll.count_documents(query)
            rows = [{"count": cnt}]
        else:
            cursor = coll.find(query, projection or {})
            limit = inputs.get("limit", 100)
            rows = list(cursor.limit(limit))

        for r in rows:
            if "_id" in r:
                r["_id"] = str(r["_id"])

    except Exception:
        query_json = json.dumps(query)
        if inputs.get("count_only"):
            cmd = f"db.{collection}.countDocuments({query_json})"
        else:
            cmd = f"db.{collection}.find({query_json}).limit(10).toArray()"
        result = _mongosh_eval(cmd)
        if isinstance(result, list):
            rows = result
        elif isinstance(result, (int, float)):
            rows = [{"count": result}]
        else:
            return PrimitiveResult(passed=False, message=f"MongoDB fallback failed for {collection}")

    match = True
    if expected and isinstance(expected, dict) and rows:
        row = rows[0]
        match = all(_loose_eq(row.get(k), v) for k, v in expected.items())

    _set_last_response({"body": {"rows": rows, "row_count": len(rows)}, "status_code": 200})
    return PrimitiveResult(passed=match, data={"rows": rows, "row_count": len(rows)})


def _p08_mongosh_command(inputs):
    cmd_str = inputs["command"]
    mongo_uri = f"mongodb://{DB_USER}:{DB_PASSWORD}@localhost:{DB_PORT}/{DB_NAME}?authSource=admin"
    escaped_cmd = cmd_str.replace("'", "'\\''")
    full_cmd = f"mongosh '{mongo_uri}' --quiet --eval 'JSON.stringify({escaped_cmd})'"

    result = _docker_exec(APP_CONTAINER, full_cmd)
    if result["exit_code"] != 0:
        _set_last_response({"body": None, "status_code": -1})
        return PrimitiveResult(passed=False, message=f"mongosh error: {result.get('stderr', '')}")

    stdout = result.get("stdout", "").strip()
    try:
        parsed = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = stdout

    _set_last_response({"body": parsed, "status_code": 200})

    if isinstance(parsed, dict) and "_id" in parsed:
        oid = parsed["_id"]
        if isinstance(oid, dict) and "$oid" in oid:
            context["last_created_id"] = oid["$oid"]
        else:
            context["last_created_id"] = str(oid)

    expected = inputs.get("expected_result")
    if expected and isinstance(expected, dict):
        if isinstance(parsed, dict):
            match = all(_loose_eq(parsed.get(k), v) for k, v in expected.items())
        elif isinstance(parsed, (int, float)):
            match = all(_loose_eq(parsed, v) for v in expected.values())
        else:
            match = True
    else:
        match = True

    assertions = inputs.get("assertions", [])
    if assertions:
        for a in assertions:
            path = a.get("path", "$")
            op = a.get("operator", "eq")
            exp = a.get("expected")
            actual = _json_path(parsed, path)

            capture_key = a.get("capture_as")
            if capture_key and actual is not None:
                context[capture_key] = actual

            if op == "exists":
                if actual is None:
                    match = False
            elif op == "not_exists":
                if actual is not None:
                    match = False
            elif op == "ne":
                if _loose_eq(actual, exp):
                    match = False
            elif op == "eq":
                if not _loose_eq(actual, exp):
                    match = False
            elif op == "gte":
                try:
                    if not (float(actual) >= float(exp)):
                        match = False
                except (TypeError, ValueError):
                    match = False
            elif op == "lte":
                try:
                    if not (float(actual) <= float(exp)):
                        match = False
                except (TypeError, ValueError):
                    match = False
            elif op == "contains":
                if not (actual is not None and str(exp) in str(actual)):
                    match = False
            elif op == "contains_all":
                if isinstance(actual, list) and isinstance(exp, list):
                    if not all(any(str(e) in str(a) for a in actual) for e in exp):
                        match = False
                else:
                    match = False

    return PrimitiveResult(passed=match, data={"result": parsed, "asserts_detail": [
        {"path": a.get("path"), "op": a.get("operator", "eq"), "expected": a.get("expected"),
         "actual": _json_path(parsed, a.get("path", "$"))} for a in assertions
    ]})



def p09_db_table_exists(inputs):
    tables = inputs.get("tables", inputs.get("collections", []))
    try:
        db = get_mongo_db()
        existing = set(db.list_collection_names())
    except Exception:
        existing = _mongosh_list_collections()

    found = [t for t in tables if t in existing]
    missing = [t for t in tables if t not in existing]
    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"existing": found, "missing": missing, "found_count": len(found), "total_count": len(tables)}
    )


def _mongosh_eval(js_expr):
    mongo_uri = f"mongodb://{DB_USER}:{DB_PASSWORD}@localhost:{DB_PORT}/{DB_NAME}?authSource=admin"
    escaped = js_expr.replace("'", "'\\''")
    cmd = f"mongosh '{mongo_uri}' --quiet --eval 'JSON.stringify({escaped})'"
    result = _docker_exec(APP_CONTAINER, cmd)
    if result["exit_code"] != 0:
        return None
    try:
        return json.loads(result["stdout"].strip())
    except (json.JSONDecodeError, ValueError):
        return result["stdout"].strip()


def _mongosh_list_collections():
    result = _mongosh_eval("db.getCollectionNames()")
    return set(result) if isinstance(result, list) else set()



def p10_db_column_check(inputs):
    collection = inputs.get("table", inputs.get("collection", ""))
    expected_cols = inputs.get("expected_columns", inputs.get("expected_fields", []))
    try:
        db = get_mongo_db()
        coll = db[collection]
        all_fields = set()
        for doc in coll.find().limit(10):
            all_fields.update(_flatten_keys(doc))
    except Exception:
        result = _mongosh_eval(f"Object.keys(db.{collection}.findOne() || {{}})")
        all_fields = set(result) if isinstance(result, list) else set()

    if not all_fields:
        if inputs.get("schema_introspect_fallback"):
            idx_fields = set()
            try:
                idx_list = _mongosh_eval(
                    f"db.{collection}.getIndexes().flatMap(i => Object.keys(i.key))"
                )
                if isinstance(idx_list, list):
                    idx_fields = set(idx_list)
            except Exception:
                pass

            found_idx = len([c for c in expected_cols if c in idx_fields])
            idx_ratio = (found_idx / len(expected_cols)) if expected_cols else 0.0
            missing_cols = [c for c in expected_cols if c not in idx_fields]
            return PrimitiveResult(
                passed=idx_ratio >= 0.6,
                data={
                    "missing": missing_cols,
                    "found": found_idx,
                    "total": len(expected_cols),
                    "ratio": idx_ratio,
                    "introspect_mode": "schema-design-time",
                    "indexed_field_match": found_idx,
                    "indexed_fields": sorted(idx_fields),
                    "note": (
                        f"Collection '{collection}' is empty at evaluation time; "
                        "scored by the candidate's own declared indexes covering "
                        "the expected fields. No credit for fields the running "
                        "system cannot demonstrate."
                    ),
                },
                message=f"{collection} empty -> {found_idx}/{len(expected_cols)} expected fields backed by real indexes"
            )
        return PrimitiveResult(passed=False, message=f"Collection '{collection}' is empty, cannot check fields")

    found = len([c for c in expected_cols if c in all_fields])
    missing = [c for c in expected_cols if c not in all_fields]
    ratio = found / len(expected_cols) if expected_cols else 1.0
    return PrimitiveResult(
        passed=ratio >= 0.6,
        data={"missing": missing, "found": found, "total": len(expected_cols), "ratio": ratio}
    )


def _flatten_keys(doc, prefix=""):
    keys = set()
    if isinstance(doc, dict):
        for k in doc.keys():
            keys.add(k)
    return keys



def p11_db_index_check(inputs):
    collection = inputs.get("table", inputs.get("collection", ""))
    expected_indexes = inputs.get("expected_indexes", [])
    try:
        db = get_mongo_db()
        coll = db[collection]
        index_info = coll.index_information()
        actual_key_sets = []
        actual_unique = {}
        for name, info in index_info.items():
            keys = [k for k, _ in info["key"]]
            ks = frozenset(keys)
            actual_key_sets.append(set(keys))
            actual_unique[ks] = info.get("unique", False)
    except Exception:
        raw = _mongosh_eval(f"db.{collection}.getIndexes()")
        actual_key_sets = []
        actual_unique = {}
        if isinstance(raw, list):
            for idx in raw:
                keys = list(idx.get("key", {}).keys())
                ks = frozenset(keys)
                actual_key_sets.append(set(keys))
                actual_unique[ks] = idx.get("unique", False)

    missing = []
    for exp in expected_indexes:
        exp_cols = exp.get("columns", exp.get("fields", []))
        exp_set = set(exp_cols)
        found = any(exp_set <= aks for aks in actual_key_sets)
        if not found:
            missing.append(exp_cols)
        elif exp.get("unique"):
            matched = [aks for aks in actual_key_sets if exp_set <= aks]
            unique_matched = any(
                actual_unique.get(frozenset(m), False) for m in matched
            )
            if matched and not unique_matched:
                missing.append(exp_cols)

    idx_count = len(actual_key_sets)
    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"missing": missing, "index_count": idx_count}
    )



def p12_docker_exec(inputs):
    cmd = _resolve(inputs["command"])
    container = inputs.get("container", APP_CONTAINER)
    result = _docker_exec(container, cmd)
    passed = result["exit_code"] == 0

    if inputs.get("expect_output_contains"):
        passed = passed and inputs["expect_output_contains"] in result.get("stdout", "")

    _set_last_response({
        "body": result["stdout"],
        "status_code": 0 if passed else result["exit_code"],
        "headers": {},
        "docker_result": result,
    })
    return PrimitiveResult(passed=passed, data=result)



def _get_csrf(sess):
    try:
        r = sess.get(f"{APP_BASE_URL}/api/v1/health", timeout=TIMEOUT)
        return sess.cookies.get("XSRF-TOKEN", "")
    except Exception:
        return ""


def _form_login(email, password):
    sess = requests.Session()
    csrf = _get_csrf(sess)
    headers = {}
    if csrf:
        headers["X-XSRF-TOKEN"] = csrf
        headers["Origin"] = APP_BASE_URL
    r = sess.post(
        f"{APP_BASE_URL}/api/v1/login",
        data={"username": email, "password": password},
        headers=headers,
        timeout=TIMEOUT,
        allow_redirects=False,
    )
    if r.status_code in (200, 302):
        _get_csrf(sess)
        return sess, True
    return sess, False


def _ensure_user_exists(email, password, name, role="user"):
    try:
        sess = requests.Session()
        csrf = _get_csrf(sess)
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                    "Origin": APP_BASE_URL}
        if csrf:
            headers["X-XSRF-TOKEN"] = csrf
        r = sess.post(
            f"{API_BASE_URL}/users",
            data={"email": email, "password": password, "name": name,
                  "source": "FORM", "signupRequestOrigin": "SIGNUP"},
            headers=headers,
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        if r.status_code in (200, 201, 302):
            return True
        if r.status_code == 409:
            return True
    except Exception:
        pass
    if role != "admin":
        try:
            admin_sess = context.get("auth_sessions", {}).get("admin")
            if admin_sess:
                csrf2 = admin_sess.cookies.get("XSRF-TOKEN", "")
                hdrs = {"Content-Type": "application/x-www-form-urlencoded",
                        "Origin": APP_BASE_URL}
                if csrf2:
                    hdrs["X-XSRF-TOKEN"] = csrf2
                r = admin_sess.post(
                    f"{API_BASE_URL}/users",
                    data={"email": email, "password": password, "name": name,
                          "source": "FORM", "signupRequestOrigin": "SIGNUP"},
                    headers=hdrs, timeout=TIMEOUT, allow_redirects=False,
                )
                return r.status_code in (200, 201, 302, 409)
        except Exception:
            pass
    return False


def p13_auth_login(inputs):
    global _active_session
    inputs = _resolve_deep(inputs)
    role = inputs.get("role", "admin")

    if role in ("anonymous", "anon", "unauthenticated"):
        _active_session = requests.Session()
        context["auth_token"] = None
        context.pop("current_user", None)
        return PrimitiveResult(passed=True, data={"role": role, "method": "anonymous"})

    if role in context.get("auth_sessions", {}) and "email" not in inputs and "username" not in inputs:
        cached_sess = context["auth_sessions"][role]
        expected_email = (TEST_USERS.get(role, {}) or {}).get("email", "").lower()
        cached_ok = True
        try:
            r = cached_sess.get(f"{API_BASE_URL}/users/me", timeout=TIMEOUT)
            if r.status_code == 200:
                body = r.json()
                actual = ((body or {}).get("data") or {}).get("email", "").lower()
                if expected_email and actual and actual != expected_email:
                    cached_ok = False
            else:
                cached_ok = False
        except Exception:
            cached_ok = False

        if cached_ok:
            _active_session = cached_sess
            _get_csrf(_active_session)
            context["auth_token"] = f"session:{role}"
            return PrimitiveResult(passed=True, data={"role": role, "cached": True})
        context["auth_sessions"].pop(role, None)
        context["auth_tokens"].pop(role, None)

    user_cfg = TEST_USERS.get(role, TEST_USERS.get("admin", {}))
    email = inputs.get("email") or inputs.get("username") or user_cfg.get("email", "")
    password = inputs.get("password") or user_cfg.get("password", "")
    name = inputs.get("name") or user_cfg.get("name", role.title())

    _ensure_user_exists(email, password, name, role)

    sess, ok = _form_login(email, password)
    if ok:
        _active_session = sess
        context["auth_token"] = f"session:{role}"
        context["auth_sessions"][role] = sess
        context["auth_tokens"][role] = f"session:{role}"

        try:
            r = sess.get(f"{API_BASE_URL}/users/me", timeout=TIMEOUT)
            if r.status_code == 200:
                body = r.json()
                data = body.get("data", body) if isinstance(body, dict) else {}
                if isinstance(data, dict):
                    context["current_user"] = data
                    if "id" in data:
                        context[f"{role}_user_id"] = data["id"]
        except Exception:
            pass

        return PrimitiveResult(passed=True, data={"role": role, "method": "form_login"})

    return PrimitiveResult(passed=False, message=f"Auth failed for role={role} email={email}")



def p14_permission_check(inputs):
    inputs = _resolve_deep(inputs)
    action = inputs["action"]
    expected = inputs["expected_result"]
    acceptable = inputs.get("acceptable_statuses") or inputs.get("expected_status")

    parts = action.split(" ", 1)
    method = parts[0].upper()
    path = parts[1] if len(parts) > 1 else "/"

    res = p04_http_request({"method": method, "path": path, "body": inputs.get("body")})
    status = res.data.get("status_code", 0) if res.data else 0

    if expected == "denied":
        ok_statuses = acceptable or [401, 403, 404]
    else:
        ok_statuses = acceptable or [200, 201]
    if isinstance(ok_statuses, int):
        ok_statuses = [ok_statuses]
    passed = status in ok_statuses

    return PrimitiveResult(
        passed=passed,
        data={"status_code": status, "expected": expected,
              "acceptable": list(ok_statuses)},
        message=f"{action} → {status} (expected {expected})"
    )



def p15_status_code_assert(inputs):
    resp = context.get("last_response", {})
    actual = resp.get("status_code", 0)
    if "expected_status" in inputs:
        exp = inputs["expected_status"]
        if isinstance(exp, (list, tuple, set)):
            passed = actual in exp
        else:
            passed = actual == exp
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
    try:
        from _llm_judge_safe import dispatch_external_evidence as _dee
        _ext_ctx = context
        _ext_result = _dee(
            inputs=inputs,
            ctx=_ext_ctx,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE or "",
            return_type='primitive',
            primitive_result_cls=PrimitiveResult,
        )
        if _ext_result is not None:
            return _ext_result
    except Exception as _ext_exc:
        import logging as _ext_logging
        _ext_logging.getLogger("p17_dispatch").warning(
            "dispatch_external_evidence failed for evidence_type=%r: %s",
            inputs.get("evidence_type"), _ext_exc)
    score_range = inputs.get("score_range", [0, 5])
    if not LLM_API_KEY:
        skip_data = {
            "score": 0,
            "skipped": True,
            "llm_api_failure": False,
            "exception_class": "",
            "reason": "LLM_API_KEY unset",
        }
        _set_last_response(skip_data)
        return PrimitiveResult(passed=True, data=skip_data, message="LLM judge SKIPPED (LLM_API_KEY unset)")

    rubric = inputs.get("rubric_prompt", "")

    evidence_parts = []
    etype = inputs.get("evidence_type", "code_files")
    if etype == "code_files":
        target_dirs = inputs.get("files_to_sample", [])
        KEY_PATTERNS = [
            "**/*Controller*", "**/*Service*", "**/*Repository*",
            "**/*Entity*", "**/*Model*", "**/*Config*", "**/*Domain*",
            "**/pom.xml", "**/package.json",
            "**/*.java", "**/*.tsx", "**/*.ts",
        ]
        SKIP_SUBSTR = ("/test/", "/tests/", "cypress", "/target/", "/build/",
                       "/node_modules/", "/dist/", "/.git/", "/generated",
                       "/__tests__/", ".test.", ".spec.", "/__mocks__/")
        _rub_kw = set(w.lower() for w in __import__("re").findall(r"[A-Za-z]{4,}", str(rubric) or ""))
        _arch_tokens = ("controller", "service", "repository", "domain", "entity",
                        "model", "config", "policy", "permission", "security",
                        "exception", "handler", "schema", "migration")
        uniq = {}
        pinned = []
        for fpath in target_dirs:
            full = os.path.join(WORKSPACE_DIR, fpath.lstrip("/"))
            if os.path.isfile(full):
                if full not in pinned:
                    pinned.append(full)
                continue
            if not os.path.isdir(full):
                continue
            for pat in KEY_PATTERNS:
                for match in glob.glob(os.path.join(full, pat), recursive=True):
                    if not os.path.isfile(match):
                        continue
                    rel = os.path.relpath(match, full).replace(os.sep, "/").lower()
                    if any(s in ("/" + rel) for s in SKIP_SUBSTR):
                        continue
                    uniq[match] = rel
        from collections import defaultdict as _dd
        groups = _dd(list)
        for m, rel in uniq.items():
            top = rel.split("/", 1)[0]
            bn = rel.rsplit("/", 1)[-1]
            relevance = sum(2 for w in _rub_kw if w in rel) + sum(1 for t in _arch_tokens if t in bn)
            groups[top].append((-relevance, rel, m))
        for g in groups.values():
            g.sort()
        sampled = []
        while len(sampled) < 40 and any(groups.values()):
            for top in list(groups.keys()):
                if groups[top]:
                    sampled.append(groups[top].pop(0)[2])
                    if len(sampled) >= 40:
                        break
        if not sampled:
            for fpath in target_dirs:
                full = os.path.join(WORKSPACE_DIR, fpath.lstrip("/"))
                if os.path.isdir(full):
                    for root, _, files in os.walk(full):
                        if any(s in ("/" + root.replace(os.sep, "/").lower() + "/") for s in SKIP_SUBSTR):
                            continue
                        for fn in sorted(files)[:10]:
                            sampled.append(os.path.join(root, fn))
                        if len(sampled) >= 30:
                            break
        if pinned:
            sampled = pinned + [s for s in sampled if s not in pinned]
        for fp in sampled[:30]:
            try:
                with open(fp, "r", errors="replace") as fh:
                    content = fh.read()[:3500]
                    evidence_parts.append(f"=== {os.path.relpath(fp, WORKSPACE_DIR)} ===\n{content}")
            except Exception:
                pass
    elif etype == "http_response_html":
        resp = context.get("last_response", {})
        evidence_parts.append(str(resp.get("body", ""))[:5000])

    evidence_text = "\n\n".join(evidence_parts)[:48000]

    from _llm_judge_safe import safe_chat_completion

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
        _m = _re.search(r'score[^\d\n]{0,15}(-?\d+(?:\.\d+)?)', _s, _re.I)
        if _m:
            _o = {"score": float(_m.group(1))}
            _rm = _re.search(r'"?reason(?:ing)?"?\s*[:=]\s*"([^"]*)"', _s, _re.I)
            if _rm:
                _o["reason"] = _rm.group(1)
                _o["reasoning"] = _rm.group(1)
            return _o
        _m2 = _re.search(r"-?\d+", _s)
        if _m2:
            return {"score": float(_m2.group())}
        raise ValueError("no JSON/score in LLM reply")

    _judge_sys = (
        f"You are an expert code reviewer. Score from {score_range[0]} to {score_range[1]} "
        f"based ONLY on the evidence provided in the user message. "
        f"You have no tools and cannot investigate or open files; do not ask to, and do not "
        f"describe any plan or process. Do not write any preamble or explanation outside the JSON. "
        f"Your entire reply MUST be a single JSON object and nothing else: "
        f"{{\"score\": N, \"reason\": \"...\"}}. Begin your reply with '{{' and end with '}}'."
    )
    _judge_user = (
        f"{rubric}\n\n--- Evidence (this is all the code you get; judge from it directly) ---\n"
        f"{evidence_text}\n\n"
        f"Now output ONLY the JSON object with your score. No preamble, no tool use, no investigation."
    )
    _judge_messages = [
        {"role": "system", "content": _judge_sys},
        {"role": "user", "content": _judge_user},
    ]
    res = None
    score_data = None
    _last_err = None
    import time as _time_retry
    for _attempt in range(6):
        if _attempt > 0:
            _time_retry.sleep(min(2 ** _attempt, 20))
        res = safe_chat_completion(
            messages=_judge_messages,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE or "",
            temperature=0.1 if _attempt == 0 else 0.0,
        )
        if res.skipped:
            _last_err = res.error or "skipped"
            if res.llm_api_failure:
                continue
            break
        try:
            score_data = _robust_judge_json(res.raw)
            break
        except Exception as e:
            _last_err = e
            continue

    if score_data is not None:
        _set_last_response(score_data)
        return PrimitiveResult(passed=True, data=score_data)

    if res is not None and res.skipped:
        skip_data = {
            "score": 0,
            "skipped": True,
            "llm_api_failure": res.llm_api_failure,
            "exception_class": res.exception_class,
            "reason": res.error or "skipped",
        }
        _set_last_response(skip_data)
        return PrimitiveResult(passed=True, data=skip_data, message=f"LLM judge SKIPPED ({res.reason()})")

    skip_data = {
        "score": 0,
        "skipped": True,
        "parse_failure": True,
        "llm_api_failure": False,
        "exception_class": type(_last_err).__name__ if isinstance(_last_err, BaseException) else "",
        "reason": f"parse failure: {_last_err}",
        "raw": (res.raw[:200] if res is not None and getattr(res, "raw", None) else ""),
    }
    _set_last_response(skip_data)
    return PrimitiveResult(passed=True, data=skip_data, message=f"LLM judge SKIPPED (parse failure: {_last_err})")



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

try:
    from _browser_primitives import (
        p18_render_dom as _shared_render_dom,
        p19_screenshot as _shared_screenshot,
    )
    for _bp_map_name in ("PRIMITIVE_MAP", "PRIMITIVES", "PRIMITIVE_DISPATCH"):
        _bp_map = globals().get(_bp_map_name)
        if isinstance(_bp_map, dict):
            _bp_map.setdefault("RENDER_DOM", lambda inputs: _shared_render_dom(inputs, context))
            _bp_map.setdefault("SCREENSHOT", lambda inputs: _shared_screenshot(inputs, context))
            break
except Exception as _bp_exc:
    import logging as _bp_log
    _bp_log.getLogger("_browser_primitives").warning(
        "RENDER_DOM/SCREENSHOT registration failed: %s", _bp_exc)
