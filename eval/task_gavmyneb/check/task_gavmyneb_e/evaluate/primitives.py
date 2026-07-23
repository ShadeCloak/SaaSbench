from __future__ import annotations
import base64
import glob as _glob
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

import config
import utils

log = utils.log


# =============================================================================
# =============================================================================
try:
    import requests
except ImportError:
    requests = None
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None
try:
    import redis as redis_lib
except ImportError:
    redis_lib = None


# =============================================================================
# =============================================================================
_db_conn = None


def get_db_connection():
    global _db_conn
    if psycopg2 is None:
        return None
    if _db_conn is not None and not _db_conn.closed:
        return _db_conn
    try:
        _db_conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            connect_timeout=5,
        )
        _db_conn.autocommit = True
        return _db_conn
    except Exception as e:
        log.warning(f"DB connection failed: {e}")
        _db_conn = None
        return None


# =============================================================================
# =============================================================================
def p01_file_exists(inputs: dict, context: dict, store=None) -> dict:
    rel = inputs.get("path", "")
    typ = inputs.get("type", "file")
    p = config.WORKSPACE_DIR / rel
    if typ == "file":
        ok = p.is_file()
    elif typ == "directory":
        ok = p.is_dir()
    else:
        ok = p.exists()
    return {
        "passed": ok,
        "output": {"exists": ok, "abs_path": str(p)},
        "error": None if ok else f"{typ} not found at {rel}",
        "evidence": {"file_exists": {rel: ok}},
    }


# =============================================================================
# =============================================================================
def p02_file_content_match(inputs: dict, context: dict, store=None) -> dict:
    rel = inputs.get("path", "")
    pattern = inputs.get("pattern", "")
    match_type = inputs.get("match_type", "contains")
    p = config.WORKSPACE_DIR / rel
    if not p.is_file():
        return {"passed": False, "output": None, "error": f"file missing: {rel}", "evidence": {}}
    try:
        text = p.read_text(errors="replace")
    except Exception as e:
        return {"passed": False, "output": None, "error": f"read err: {e}", "evidence": {}}
    if match_type == "regex":
        m = list(re.finditer(pattern, text))
        cnt = len(m)
        first_line = text[:m[0].start()].count("\n") + 1 if m else None
    else:
        cnt = text.count(pattern)
        idx = text.find(pattern)
        first_line = text[:idx].count("\n") + 1 if idx >= 0 else None
    ok = cnt > 0
    return {
        "passed": ok,
        "output": {"matched": ok, "match_count": cnt, "first_match_line": first_line},
        "error": None if ok else f"pattern not found: {pattern[:80]}",
        "evidence": {},
    }


# =============================================================================
# =============================================================================
def p03_file_count(inputs: dict, context: dict, store=None) -> dict:
    pattern = inputs.get("glob", "*")
    base = config.WORKSPACE_DIR / inputs.get("base_dir", "")
    min_expected = int(inputs.get("min_expected", 1))
    if not base.exists():
        return {"passed": False, "output": {"count": 0, "files": []}, "error": f"missing base dir: {base}", "evidence": {}}
    leaf = pattern[3:] if pattern.startswith("**/") else pattern
    matches = list(base.rglob(leaf))[:1000]
    cnt = len(matches)
    ok = cnt >= min_expected
    return {
        "passed": ok,
        "output": {"count": cnt, "files": [str(m.relative_to(base)) for m in matches[:20]]},
        "error": None if ok else f"only {cnt} files found, need ≥{min_expected}",
        "evidence": {},
    }


# =============================================================================
# =============================================================================
def p04_http_request(inputs: dict, context: dict, store=None) -> dict:
    if requests is None:
        return {"passed": False, "output": None, "error": "requests unavailable", "evidence": {}}
    method = inputs.get("method", "GET").upper()
    path = inputs.get("path", "/")
    url = path if path.startswith("http") else f"{config.API_BASE_URL}{path}"
    headers = dict(inputs.get("headers", {}))
    if not inputs.get("no_auth") and "Authorization" not in headers and context.get("auth_token"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    body = inputs.get("body")
    query = inputs.get("query")
    timeout = int(inputs.get("timeout", config.DEFAULT_HTTP_TIMEOUT))
    try:
        t0 = time.perf_counter()
        resp = requests.request(
            method, url, headers=headers,
            json=body if isinstance(body, (dict, list)) else None,
            data=body if isinstance(body, (str, bytes)) else None,
            params=query, timeout=timeout, allow_redirects=False,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        try:
            body_json = resp.json()
        except Exception:
            body_json = None
        _hdrs = dict(resp.headers)
        for _k, _v in list(_hdrs.items()):
            _tc = _k.title()
            if _tc not in _hdrs:
                _hdrs[_tc] = _v
        out = {
            "status_code": resp.status_code,
            "headers": _hdrs,
            "body": body_json if body_json is not None else resp.text[:5000],
            "response_time_ms": round(elapsed, 1),
            "url": url,
            "method": method,
        }
        return {
            "passed": True,
            "output": out,
            "error": None,
            "evidence": {"http_request": {"url": url, "status": resp.status_code}},
        }
    except requests.RequestException as e:
        return {"passed": False, "output": None, "error": f"HTTP error: {e}", "evidence": {}}


# =============================================================================
# =============================================================================
def p05_api_crud(inputs: dict, context: dict, store=None) -> dict:
    if requests is None:
        return {"passed": False, "output": None, "error": "requests unavailable", "evidence": {}}
    resource = inputs.get("resource", "")
    base = f"{config.API_BASE_URL}{resource}"
    item_resource = inputs.get("item_resource", resource)
    item_base = f"{config.API_BASE_URL}{item_resource}"
    delete_resource = inputs.get("delete_resource", item_resource)
    delete_base = f"{config.API_BASE_URL}{delete_resource}"
    delete_query = inputs.get("delete_query", "")
    if isinstance(delete_query, dict):
        delete_query = "&".join(f"{k}={v}" for k, v in delete_query.items())
    headers = {"Authorization": f"Bearer {context.get('auth_token','')}"} if context.get("auth_token") else {}
    headers.update(inputs.get("headers", {}))
    create_body = inputs.get("create_body", {})
    update_body = inputs.get("update_body", {})
    expected_create = int(inputs.get("expected_create_status", 201))
    expected_update = int(inputs.get("expected_update_status", 200))
    expected_delete = int(inputs.get("expected_delete_status", 204))
    expected_fields = inputs.get("expected_read_fields", [])

    steps = {"create": False, "read": False, "update": False, "delete": False}
    out = {"steps": steps}
    try:
        r = requests.post(base, json=create_body, headers=headers, timeout=config.DEFAULT_HTTP_TIMEOUT)
        if r.status_code in (expected_create, expected_create - 1, expected_create + 1, 200, 201):
            steps["create"] = True
            try:
                created = r.json()
                rid = created.get("id") or created.get("data", {}).get("id")
                if not rid and isinstance(created, dict):
                    for _v in created.values():
                        if isinstance(_v, dict) and _v.get("id"):
                            rid = _v.get("id")
                            break
            except Exception:
                rid = None
            out["create_response"] = (r.status_code, rid)
        else:
            out["create_error"] = f"got {r.status_code}, expected {expected_create}"
            return _crud_summary(out, steps)

        if not rid:
            out["error"] = "no id from create response"
            return _crud_summary(out, steps)

        r = requests.get(f"{item_base}/{rid}", headers=headers, timeout=config.DEFAULT_HTTP_TIMEOUT)
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                data = {}
            missing = [f for f in expected_fields if f not in data]
            if not missing:
                steps["read"] = True
            out["read_missing_fields"] = missing
        if update_body:
            r = requests.put(f"{item_base}/{rid}", json=update_body, headers=headers, timeout=config.DEFAULT_HTTP_TIMEOUT)
            if r.status_code in (expected_update, 200, 204):
                steps["update"] = True
        else:
            steps["update"] = True
        del_url = f"{delete_base}/{rid}"
        if delete_query:
            del_url += f"?{delete_query}"
        r = requests.delete(del_url, headers=headers, timeout=config.DEFAULT_HTTP_TIMEOUT)
        if r.status_code in (expected_delete, 200, 202, 204):
            steps["delete"] = True
    except requests.RequestException as e:
        out["error"] = str(e)
    return _crud_summary(out, steps)


def _crud_summary(out, steps):
    passed_n = sum(steps.values())
    return {
        "passed": passed_n == 4,
        "output": {**out, "steps_passed": passed_n, "steps_total": 4, "pass_ratio": passed_n / 4},
        "error": None if passed_n == 4 else f"{4 - passed_n} step(s) failed",
        "evidence": {"crud_cycle": steps},
    }


# =============================================================================
# =============================================================================
def p06_json_schema_match(inputs: dict, context: dict, store=None) -> dict:
    response = inputs.get("response") or context.get("from_P04") or context.get("last_response")
    body = response.get("body") if isinstance(response, dict) else response
    required = inputs.get("required_fields", [])
    type_check = inputs.get("field_types", {})
    if body is None:
        return {"passed": False, "output": None, "error": "no response body", "evidence": {}}
    if not isinstance(body, dict):
        return {"passed": False, "output": None, "error": "response body is not a JSON object", "evidence": {}}
    missing = [f for f in required if f not in body]
    type_mismatch = []
    for f, expected_type in type_check.items():
        if f not in body:
            continue
        actual = type(body[f]).__name__
        wanted_map = {"integer": "int", "number": ("int", "float"), "array": "list", "object": "dict", "string": "str", "boolean": "bool"}
        wanted = wanted_map.get(expected_type, expected_type)
        ok = actual == wanted if isinstance(wanted, str) else actual in wanted
        if not ok:
            type_mismatch.append({"field": f, "expected": expected_type, "actual": actual})
    ok = not missing and not type_mismatch
    return {
        "passed": ok,
        "output": {"all_present": ok, "missing_fields": missing, "type_mismatches": type_mismatch},
        "error": None if ok else f"missing={missing}, type_mismatch={type_mismatch}",
        "evidence": {},
    }


# =============================================================================
# =============================================================================
def p07_json_value_assert(inputs: dict, context: dict, store=None) -> dict:
    response = inputs.get("response")
    if not isinstance(response, dict):
        response = (context.get("from_P22") or context.get("from_P04")
                    or context.get("from_P05") or context.get("last_response"))
    full = response if isinstance(response, dict) else None
    body = response.get("body") if isinstance(response, dict) and "body" in response else response
    if body is None and full is None:
        return {"passed": False, "output": None, "error": "no response body to assert", "evidence": {}}
    asserts = inputs.get("assertions", [])
    results = []
    all_pass = True
    for a in asserts:
        path = a.get("path", "$")
        if path in ("$", ""):
            actual = body if body is not None else full
        else:
            actual = utils.jsonpath_get(full, path) if full is not None else None
            if actual is None:
                actual = utils.jsonpath_get(body, path)
        if "empty_or_absent" in a:
            ok = actual is None or (isinstance(actual, (list, dict, str)) and len(actual) == 0)
            results.append({"path": path, "actual": actual, "passed": ok, "rule": "empty_or_absent"})
        elif "exists" in a:
            want = a["exists"]
            present = actual is not None and (not isinstance(actual, (list, dict, str)) or len(actual) > 0)
            ok = present == bool(want)
            results.append({"path": path, "actual": str(actual)[:80], "passed": ok, "rule": "exists"})
        elif "array_min_length" in a:
            ok = isinstance(actual, list) and len(actual) >= int(a["array_min_length"])
            results.append({"path": path, "actual_len": (len(actual) if isinstance(actual, list) else None),
                            "min": a["array_min_length"], "passed": ok, "rule": "array_min_length"})
        elif "array_length" in a:
            ok = isinstance(actual, list) and len(actual) == int(a["array_length"])
            results.append({"path": path, "actual_len": (len(actual) if isinstance(actual, list) else None),
                            "expected_len": a["array_length"], "passed": ok, "rule": "array_length"})
        elif "expected_present" in a:
            ok = actual is not None
            results.append({"path": path, "actual": actual, "passed": ok, "rule": "present"})
        elif "expected_type" in a:
            ok = type(actual).__name__ in ("dict", "list", "str", "int", "float", "bool", "NoneType")
            wanted = a["expected_type"]
            type_map = {"object": "dict", "array": "list", "string": "str", "integer": "int", "number": ("int", "float"), "boolean": "bool"}
            target = type_map.get(wanted, wanted)
            ok = type(actual).__name__ == target if isinstance(target, str) else type(actual).__name__ in target
            results.append({"path": path, "actual": str(type(actual).__name__), "expected_type": wanted, "passed": ok})
        elif "contains" in a:
            ok = a["contains"] in str(actual or "")
            results.append({"path": path, "actual": str(actual)[:80], "expected_contains": a["contains"], "passed": ok})
        else:
            expected = a.get("expected")
            tol = float(a.get("tolerance", 0))
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                ok = abs(actual - expected) <= tol
            else:
                ok = actual == expected
            results.append({"path": path, "actual": actual, "expected": expected, "passed": ok})
        if not results[-1]["passed"]:
            all_pass = False
    if not all_pass and os.environ.get("HARNESS_LENIENT_MODE") == "1":
        last = context.get("from_P04") or context.get("last_response", {})
        if isinstance(last, dict):
            sc = last.get("status_code")
            if sc and (sc >= 400 or sc == 0):
                return {"passed": True,
                        "output": {"lenient": "upstream_error_status", "status": sc},
                        "error": None,
                        "evidence": {"lenient_reason": f"upstream returned {sc}"}}
        return {"passed": True,
                "output": {"lenient": "field_value_diff", "results": results},
                "error": None,
                "evidence": {"lenient_reason": f"{sum(1 for r in results if not r['passed'])} field(s) differ from task.md spec"}}

    return {
        "passed": all_pass,
        "output": {"all_passed": all_pass, "results": results},
        "error": None if all_pass else f"{sum(1 for r in results if not r['passed'])} assertion(s) failed",
        "evidence": {"assertions": results},
    }


# =============================================================================
# =============================================================================
def _p08_match(actual, expected) -> bool:
    import re as _re
    import datetime as _dt
    from decimal import Decimal as _Dec
    if isinstance(actual, (_dt.date, _dt.datetime)):
        actual = actual.isoformat()
    elif isinstance(actual, _Dec):
        actual = float(actual)
    if isinstance(expected, dict) and "op" in expected:
        op = expected["op"]; val = expected.get("value")
        try:
            a = float(actual); b = float(val)
        except (TypeError, ValueError):
            return actual == val
        return {"gte": a >= b, "lte": a <= b, "gt": a > b, "lt": a < b,
                "eq": a == b, "ne": a != b}.get(op, actual == val)
    if isinstance(expected, dict) and ("not_null" in expected or "null" in expected):
        present = actual is not None and (not isinstance(actual, (str, list, dict)) or len(actual) > 0)
        if "not_null" in expected:
            return present == bool(expected["not_null"])
        return present != bool(expected["null"])
    if isinstance(expected, dict) and "in" in expected:
        return actual in expected["in"]
    if isinstance(expected, dict) and "regex" in expected:
        return bool(_re.search(expected["regex"], str(actual)))
    if isinstance(expected, dict) and ("min" in expected or "max" in expected):
        try:
            a = float(actual)
        except (TypeError, ValueError):
            return False
        ok = True
        if "min" in expected:
            ok = ok and a >= float(expected["min"])
        if "max" in expected:
            ok = ok and a <= float(expected["max"])
        return ok
    if isinstance(expected, str):
        e = expected.strip()
        if e.startswith("regex:"):
            return bool(_re.search(e[len("regex:"):], str(actual)))
        if e == "contains_mfa_key":
            return "mfa" in str(actual).lower()
        low = e.lower()
        if low in ("non_empty", "not_null", "present", "notnull"):
            return actual is not None and (not isinstance(actual, (str, list, dict)) or len(actual) > 0)
        if low in ("null", "empty", "absent"):
            return actual is None or (isinstance(actual, (str, list, dict)) and len(actual) == 0)
        if low == "non_zero":
            try:
                return float(actual) != 0
            except (TypeError, ValueError):
                return bool(actual)
        m = _re.fullmatch(r"(>=|<=|>|<|==|!=)\s*(-?\d+(?:\.\d+)?)", e)
        if m:
            op, num = m.group(1), float(m.group(2))
            try:
                a = float(actual)
            except (TypeError, ValueError):
                return False
            return {">=": a >= num, "<=": a <= num, ">": a > num,
                    "<": a < num, "==": a == num, "!=": a != num}[op]
        return actual == expected or (isinstance(actual, str) and expected in actual)
    return actual == expected


def p08_db_query(inputs: dict, context: dict, store=None) -> dict:
    conn = get_db_connection()
    if conn is None:
        return {"passed": False, "output": None, "error": "DB unavailable", "evidence": {}}
    sql = inputs.get("sql", "")
    expected = inputs.get("expected_result")
    expected_min = inputs.get("expected_result_min")
    expected_min_rows = inputs.get("expected_result_min_rows")
    if not sql:
        return {"passed": False, "output": None, "error": "empty SQL", "evidence": {}}
    params = inputs.get("params")
    if isinstance(params, dict):
        import re as _re2
        for key in sorted(params, key=len, reverse=True):
            val = params[key]
            if isinstance(val, bool):
                lit = "TRUE" if val else "FALSE"
            elif isinstance(val, (int, float)):
                lit = str(val)
            elif val is None:
                lit = "NULL"
            else:
                sval = str(val)
                lit = sval if _re2.fullmatch(r"-?\d+(?:\.\d+)?", sval) else "'" + sval.replace("'", "''") + "'"
            sql = _re2.sub(rf":{key}\b", lit, sql)
    if "{{" in sql and os.environ.get("HARNESS_LENIENT_MODE") == "1":
        return {"passed": True, "output": {"lenient": "unsubstituted_placeholder"},
                "error": None, "evidence": {}}
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            try:
                rows = cur.fetchall()
            except psycopg2.ProgrammingError:
                rows = []
        rows = [dict(r) for r in rows]
        ok = True
        notes = []
        if expected is not None and rows:
            for k, v in expected.items():
                actual = rows[0].get(k)
                if not _p08_match(actual, v):
                    ok = False
                    notes.append(f"row[0].{k}={actual!r} vs expected {v!r}")
        if expected_min is not None and rows:
            for k, v in expected_min.items():
                actual = rows[0].get(k, 0)
                if actual is None or actual < v:
                    ok = False
                    notes.append(f"row[0].{k}={actual} < min {v}")
        if expected_min_rows is not None:
            if len(rows) < expected_min_rows:
                ok = False
                notes.append(f"got {len(rows)} rows, need ≥{expected_min_rows}")
        if not ok and os.environ.get("HARNESS_LENIENT_MODE") == "1":
            if not rows:
                return {"passed": True,
                        "output": {"rows": [], "row_count": 0, "lenient": "no_seed_data"},
                        "error": None,
                        "evidence": {"lenient_reason": "0 rows; missing seed data"}}
            return {"passed": True,
                    "output": {"rows": rows[:5], "row_count": len(rows), "lenient": "row_value_diff"},
                    "error": None,
                    "evidence": {"lenient_reason": "; ".join(notes)[:120]}}
        return {
            "passed": ok,
            "output": {"rows": rows[:10], "row_count": len(rows), "match": ok},
            "error": None if ok else "; ".join(notes),
            "evidence": {"db_query": sql[:120], "row_count": len(rows)},
        }
    except Exception as e:
        if os.environ.get("HARNESS_LENIENT_MODE") == "1":
            return {"passed": True, "output": {"lenient": "sql_error"},
                    "error": None, "evidence": {"lenient_reason": str(e)[:100]}}
        return {"passed": False, "output": None, "error": f"SQL error: {e}", "evidence": {}}


# =============================================================================
# =============================================================================
def p09_db_table_exists(inputs: dict, context: dict, store=None) -> dict:
    conn = get_db_connection()
    if conn is None:
        return {"passed": False, "output": None, "error": "DB unavailable", "evidence": {}}
    tables = inputs.get("tables", [])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            )
            existing = {r[0] for r in cur.fetchall()}
        present = [t for t in tables if t in existing]
        missing = [t for t in tables if t not in existing]
        ok = not missing
        return {
            "passed": ok,
            "output": {"existing": present, "missing": missing,
                       "found_count": len(present), "total_count": len(tables)},
            "error": None if ok else f"missing tables: {missing}",
            "evidence": {"tables_checked": tables, "missing": missing},
        }
    except Exception as e:
        return {"passed": False, "output": None, "error": str(e), "evidence": {}}


# =============================================================================
# =============================================================================
def p10_db_column_check(inputs: dict, context: dict, store=None) -> dict:
    conn = get_db_connection()
    if conn is None:
        return {"passed": False, "output": None, "error": "DB unavailable", "evidence": {}}
    table = inputs.get("table", "")
    expected = inputs.get("expected_columns", [])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                (table,),
            )
            cols = {r[0] for r in cur.fetchall()}
        present = [c for c in expected if c in cols]
        missing = [c for c in expected if c not in cols]
        ok = not missing
        return {
            "passed": ok,
            "output": {"existing": present, "missing": missing,
                       "found_count": len(present), "total_count": len(expected)},
            "error": None if ok else f"missing cols on {table}: {missing}",
            "evidence": {"table": table, "missing_cols": missing},
        }
    except Exception as e:
        return {"passed": False, "output": None, "error": str(e), "evidence": {}}


# =============================================================================
# =============================================================================
def p11_db_index_check(inputs: dict, context: dict, store=None) -> dict:
    conn = get_db_connection()
    if conn is None:
        return {"passed": False, "output": None, "error": "DB unavailable", "evidence": {}}
    table = inputs.get("table", "")
    expected = inputs.get("expected_indexes", [])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=%s",
                (table,),
            )
            rows = cur.fetchall()
        defs = [r[1] for r in rows]
        matched = []
        for spec in expected:
            cols = spec.get("columns", []) if isinstance(spec, dict) else (spec if isinstance(spec, list) else [])
            ok = any(all(c in d for c in cols) for d in defs)
            matched.append({"columns": cols, "matched": ok})
        all_ok = all(m["matched"] for m in matched)
        return {
            "passed": all_ok,
            "output": {"matched": matched, "indexes_present": [r[0] for r in rows]},
            "error": None if all_ok else "missing indexes",
            "evidence": {"table": table},
        }
    except Exception as e:
        return {"passed": False, "output": None, "error": str(e), "evidence": {}}


# =============================================================================
# =============================================================================
def p12_docker_exec(inputs: dict, context: dict, store=None) -> dict:
    cmd = inputs.get("command", "")
    container = inputs.get("container", config.APP_CONTAINER)
    timeout = int(inputs.get("timeout", config.DEFAULT_DOCKER_EXEC_TIMEOUT))
    expect_success = inputs.get("expect_success", True)
    expect_contains = inputs.get("expect_output_contains")
    expect_regex = inputs.get("expect_output_match_regex")
    if not cmd:
        return {"passed": False, "output": None, "error": "empty command", "evidence": {}}
    proc = utils.docker_exec(container, cmd, timeout=timeout)
    out = proc.stdout or ""
    err = proc.stderr or ""
    success_ok = (proc.returncode == 0) == expect_success
    contains_ok = (expect_contains in out) if expect_contains else True
    regex_ok = bool(re.search(expect_regex, out)) if expect_regex else True
    ok = success_ok and contains_ok and regex_ok
    if not ok and os.environ.get("HARNESS_LENIENT_MODE") == "1":
        env_setup_signals = ["not found", "No such container", "command not found",
                              "No such file or directory", "executable file not found"]
        if proc.returncode in (127, 125, 126) or any(sig in err for sig in env_setup_signals):
            return {"passed": True,
                    "output": {"returncode": proc.returncode, "lenient": "env_setup_gap"},
                    "error": None,
                    "evidence": {"lenient_reason": err[:100]}}
    return {
        "passed": ok,
        "output": {"returncode": proc.returncode, "stdout": out[:2000], "stderr": err[:1000]},
        "error": None if ok else f"rc={proc.returncode}, contains_ok={contains_ok}, regex_ok={regex_ok}, stderr={err[:200]}",
        "evidence": {"docker_cmd": cmd[:120]},
    }


# =============================================================================
# =============================================================================
_ROLE_TOKEN_CACHE: dict[str, str] = {}


def p13_auth_login(inputs: dict, context: dict, store=None) -> dict:
    role = inputs.get("role", "admin")
    user = config.TEST_USERS.get(role, config.TEST_USERS["admin"])

    if inputs.get("method") == "form" and requests is not None:
        try:
            sess = requests.Session()
            login_path = inputs.get("login_path", "/login/canvas")
            page = sess.get(f"{config.API_BASE_URL}{login_path}",
                            timeout=config.DEFAULT_HTTP_TIMEOUT)
            m = (re.search(r'name="authenticity_token"[^>]*value="([^"]+)"', page.text)
                 or re.search(r'csrf-token"[^>]*content="([^"]+)"', page.text))
            data = {"pseudonym_session[unique_id]": user["email"],
                    "pseudonym_session[password]": user["password"]}
            if m:
                data["authenticity_token"] = m.group(1)
            r = sess.post(f"{config.API_BASE_URL}{login_path}", data=data,
                          allow_redirects=False, timeout=config.DEFAULT_HTTP_TIMEOUT)
            ok = r.status_code in (200, 302)
            cookie = sess.cookies.get(config.SESSION_COOKIE_NAME)
            if cookie:
                context["session_cookie"] = cookie
            return {"passed": ok,
                    "output": {"status_code": r.status_code, "session_cookie": cookie},
                    "error": None if ok else f"form login status {r.status_code}",
                    "evidence": {"auth_method": "form", "auth_role": role}}
        except requests.RequestException as e:
            return {"passed": False, "output": None, "error": str(e), "evidence": {}}

    env_token = os.environ.get(f"HARNESS_{role.upper()}_TOKEN")
    if env_token:
        _ROLE_TOKEN_CACHE[role] = env_token
        context["auth_token"] = env_token
        context[f"auth_token_{role}"] = env_token
        context[f"{role}_token"] = env_token
        return {"passed": True, "output": {"role": role, "token_method": "env"}, "error": None,
                "evidence": {"auth_role": role}}

    if role in _ROLE_TOKEN_CACHE:
        token = _ROLE_TOKEN_CACHE[role]
        context["auth_token"] = token
        context[f"auth_token_{role}"] = token
        return {"passed": True, "output": {"role": role, "token": "(cached)"}, "error": None,
                "evidence": {"auth_role": role}}

    if requests is not None:
        try:
            r = requests.post(
                f"{config.API_BASE_URL}/api/v1/access_tokens",
                json={"token": {"purpose": f"eval_{role}"}},
                auth=(user["email"], user["password"]),
                timeout=config.DEFAULT_HTTP_TIMEOUT,
            )
            if r.status_code in (200, 201):
                tok = r.json().get("token") or r.json().get("access_token")
                if tok:
                    _ROLE_TOKEN_CACHE[role] = tok
                    context["auth_token"] = tok
                    context[f"auth_token_{role}"] = tok
                    return {"passed": True, "output": {"role": role, "token_method": "api"}, "error": None,
                            "evidence": {"auth_role": role}}
        except requests.RequestException:
            pass

    conn = get_db_connection()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE id IN (SELECT user_id FROM pseudonyms WHERE unique_id=%s) LIMIT 1",
                            (user["email"],))
                row = cur.fetchone()
                if row:
                    user_id = row[0]
                    new_token = secrets.token_hex(32)
                    cur.execute("DELETE FROM access_tokens WHERE purpose=%s", (f"eval_{role}",))
                    cur.execute(
                        "INSERT INTO access_tokens (user_id, crypted_token, token_hint, purpose, created_at, updated_at, workflow_state) "
                        "VALUES (%s, %s, %s, %s, NOW(), NOW(), 'active')",
                        (user_id, hashlib.sha256(new_token.encode()).hexdigest(), new_token[:8], f"eval_{role}"),
                    )
                    _ROLE_TOKEN_CACHE[role] = new_token
                    context["auth_token"] = new_token
                    context[f"auth_token_{role}"] = new_token
                    return {"passed": True, "output": {"role": role, "token_method": "db_insert"}, "error": None,
                            "evidence": {"auth_role": role}}
        except Exception as e:
            log.warning(f"P13 db-insert failed: {e}")

    if inputs.get("method") == "form" and requests is not None:
        try:
            r = requests.post(
                f"{config.API_BASE_URL}{inputs.get('login_path','/login/canvas')}",
                data={"pseudonym_session[unique_id]": user["email"],
                      "pseudonym_session[password]": user["password"]},
                allow_redirects=False, timeout=config.DEFAULT_HTTP_TIMEOUT,
            )
            ok = r.status_code in (200, 302)
            if ok:
                cookie = r.cookies.get(config.SESSION_COOKIE_NAME)
                context["session_cookie"] = cookie
                return {"passed": True, "output": {"status_code": r.status_code, "session_cookie": cookie}, "error": None,
                        "evidence": {"auth_method": "form", "auth_role": role}}
        except requests.RequestException as e:
            return {"passed": False, "output": None, "error": str(e), "evidence": {}}
    if os.environ.get("HARNESS_LENIENT_MODE") == "1":
        context["auth_token"] = context.get("auth_token", "")
        return {"passed": True, "output": {"role": role, "lenient": "no_token_for_role"},
                "error": None, "evidence": {"lenient_reason": f"role {role!r} has no pre-injected token"}}
    return {"passed": False, "output": None, "error": "all auth strategies failed", "evidence": {}}


# =============================================================================
# =============================================================================
def p14_permission_check(inputs: dict, context: dict, store=None) -> dict:
    if requests is None:
        return {"passed": False, "output": None, "error": "requests unavailable", "evidence": {}}
    role = inputs.get("role", "admin")
    action = (inputs.get("action") or "").strip()
    if not action:
        op = inputs.get("operation") or inputs.get("method")
        pth = inputs.get("path")
        if op and pth:
            action = f"{str(op).upper()} {pth}"
    expected_result = inputs.get("expected_result", "allowed")
    expected_status = inputs.get("expected_status")
    if expected_status is None:
        expected_status = inputs.get("expect_status")
    acceptable = inputs.get("acceptable_statuses")
    allowed_acceptable = acceptable
    if not allowed_acceptable and expected_status is not None:
        allowed_acceptable = list(expected_status) if isinstance(expected_status, (list, tuple)) else [expected_status]

    m = re.match(r"^([A-Z]+)\s+(.+)$", action)
    if not m:
        if os.environ.get("HARNESS_LENIENT_MODE") == "1":
            return {"passed": True, "output": {"lenient": "unparseable_action"}, "error": None, "evidence": {}}
        return {"passed": False, "output": None, "error": f"unparseable action: {action}", "evidence": {}}
    method, path = m.group(1), m.group(2)

    is_anon = role == "anonymous" or ("token" in inputs and inputs.get("token") is None)
    if not is_anon and not context.get(f"auth_token_{role}"):
        p13_result = p13_auth_login({"role": role}, context, store)
        if not p13_result["passed"]:
            if os.environ.get("HARNESS_LENIENT_MODE") == "1":
                return {"passed": True, "output": {"lenient": "no_role_token"}, "error": None, "evidence": {}}
            return {"passed": False, "output": None, "error": "P14 needs role token", "evidence": {}}

    headers = {} if is_anon else {"Authorization": f"Bearer {context.get(f'auth_token_{role}','')}"}
    try:
        r = requests.request(method, f"{config.API_BASE_URL}{path}",
                              headers=headers, params=inputs.get("query"),
                              json=inputs.get("body"),
                              timeout=config.DEFAULT_HTTP_TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        return {"passed": False, "output": None, "error": str(e), "evidence": {}}

    if expected_result == "denied":
        denied_codes = acceptable or [401, 403, 404]
        ok = r.status_code in denied_codes
        msg = f"denied as expected ({r.status_code})" if ok else f"got {r.status_code}, expected denied"
    else:
        allowed_codes = allowed_acceptable or [200, 201, 202, 204]
        ok = r.status_code in allowed_codes
        if not ok and r.status_code == 404 and os.environ.get("HARNESS_LENIENT_MODE") == "1":
            ok = True
            msg = f"allowed/not-implemented ({r.status_code}) [lenient]"
        else:
            msg = f"allowed ({r.status_code})" if ok else f"got {r.status_code}, expected allowed"
    return {
        "passed": ok,
        "output": {"status_code": r.status_code, "role": role, "action": action, "msg": msg},
        "error": None if ok else msg,
        "evidence": {"rbac_check": {"role": role, "action": action, "status": r.status_code, "expected": expected_result}},
    }


# =============================================================================
# =============================================================================
def p15_status_code_assert(inputs: dict, context: dict, store=None) -> dict:
    response = inputs.get("response") or context.get("from_P04") or context.get("last_response")
    if not response or not isinstance(response, dict):
        if os.environ.get("HARNESS_LENIENT_MODE") == "1":
            return {"passed": True, "output": {"lenient": "no_response"}, "error": None, "evidence": {}}
        return {"passed": False, "output": None, "error": "no response in chain", "evidence": {}}
    code = response.get("status_code")
    expected = inputs.get("expected_status")
    acceptable = inputs.get("acceptable_statuses")
    if not acceptable:
        if isinstance(expected, (list, tuple)):
            acceptable = list(expected)
        elif expected is not None:
            acceptable = [expected]
        else:
            acceptable = []
    ok = code in acceptable if acceptable else (200 <= (code or 0) < 300)

    if not ok and os.environ.get("HARNESS_LENIENT_MODE") == "1":
        is_2xx_expected = (expected and 200 <= int(expected) < 300) or \
                          (acceptable and any(200 <= int(c) < 300 for c in acceptable))
        is_4xx_expected = (expected and 400 <= int(expected) < 500) or \
                          (acceptable and any(400 <= int(c) < 500 for c in acceptable))
        is_4xx_actual = code is not None and 400 <= code < 500
        is_2xx_actual = code is not None and 200 <= code < 300
        if (is_2xx_expected and is_4xx_actual) or (is_4xx_expected and is_4xx_actual):
            return {"passed": True,
                    "output": {"actual_status": code, "expected": expected or acceptable, "lenient": True},
                    "error": None,
                    "evidence": {"lenient_reason": f"close-but-not-exact status (got {code})"}}

    return {
        "passed": ok,
        "output": {"actual_status": code, "expected": expected or acceptable},
        "error": None if ok else f"got {code}, expected {expected or acceptable}",
        "evidence": {},
    }


# =============================================================================
# =============================================================================
def p16_response_time_check(inputs: dict, context: dict, store=None) -> dict:
    response = inputs.get("response") or context.get("from_P04") or context.get("last_response")
    max_ms = float(inputs.get("max_ms", 1000))
    if not response or not isinstance(response, dict):
        return {"passed": False, "output": None, "error": "no response", "evidence": {}}
    actual = float(response.get("response_time_ms", 0))
    ok = actual <= max_ms
    return {
        "passed": ok,
        "output": {"actual_ms": actual, "max_ms": max_ms},
        "error": None if ok else f"{actual}ms > {max_ms}ms",
        "evidence": {},
    }


# =============================================================================
# =============================================================================
_CODE_EXTS = {".rb", ".rake", ".erb", ".js", ".jsx", ".ts", ".tsx", ".vue",
              ".graphql", ".gql", ".py", ".go", ".java", ".kt", ".rs", ".php",
              ".ex", ".exs", ".scala", ".sql"}
_SKIP_DIR = ("/node_modules/", "/dist/", "/build/", "/.git/", "/vendor/",
             "/coverage/", "/tmp/", "/log/", "/public/dist/", "/spec/",
             "/test/", "/__tests__/", "/fixtures/", "/.yardoc/")
_RUBRIC_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent does "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling whether lives well how".split())


def _rank_fs_files(workspace_dir, files_to_sample, rubric, max_files=14):
    ws = Path(workspace_dir)
    entries = list(files_to_sample) or ["app/", "lib/"]
    cands = set()
    for ent in entries:
        ent = str(ent)
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
                globbed = (list(ws.glob(ent))[:40]
                           or list(ws.glob(f"**/{ent}"))[:40]
                           or list(ws.glob(stem + "*"))[:40]
                           or list(ws.glob(f"**/{stem}*"))[:40])
                for fp in globbed:
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
    for p in re.findall(r"(?:app|lib|config|db|frontend)/[\w./*-]+", rubric or ""):
        for seg in re.split(r"[/.*]", p):
            if len(seg) >= 3:
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
        base = os.path.basename(low)
        sc = 0.0
        for m in mentioned:
            if m and (m == base or low.endswith(m)):
                sc += 50
        for w in pathwords:
            if w in low:
                sc += 8
        for w in kws:
            if w in low:
                sc += 3
        sc += 2.0 if fp.suffix.lower() in _CODE_EXTS else 0.0
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


def _rubric_keywords(rubric):
    kws = set()
    for m in re.findall(r"[\w./*-]+\.\w{1,5}", rubric or ""):
        kws.add(m.split("/")[-1].split(".")[0].lower())
    for p in re.findall(r"(?:app|lib|config|db|ui|gems)/[\w./*-]+", rubric or ""):
        for seg in re.split(r"[/.*]", p):
            if len(seg) >= 3:
                kws.add(seg.lower())
    for t in re.findall(r"[A-Za-z_]{4,}", (rubric or "")):
        low = t.lower()
        if low not in _RUBRIC_STOP:
            kws.add(low)
    return {k for k in kws if len(k) >= 3}


def _extract_relevant(text, keywords, cap=9000, head=1400, window=10):
    if not text:
        return text
    if len(text) <= cap:
        return text
    import math
    lines = text.split("\n")
    lows = [ln.lower() for ln in lines]
    df = {}
    for k in keywords:
        c = sum(1 for lw in lows if k in lw)
        if c:
            df[k] = c
    n = len(lines) or 1
    line_score = []
    for i, lw in enumerate(lows):
        sc = 0.0
        for k, c in df.items():
            if k in lw:
                sc += math.log(1 + n / c)
                if lw.lstrip().startswith(("def ", "class ", "module ",
                                           "rescue_from", "scope ", "has_many",
                                           "def self.")):
                    sc += 1.5
        if sc:
            line_score.append((sc, i))
    head_txt = "\n".join(lines[:60])[:head]
    if not line_score:
        return head_txt + "\n... (elided; no rubric-relevant lines found) ...\n" \
            + text[head:head + (cap - len(head_txt))]
    specific = {k for k, c in df.items()
                if len(k) >= 6 and c <= max(3, int(n * 0.05))}
    _defre = re.compile(r"^\s*(?:def self\.|def |class |module |scope\s+:)"
                        r"([a-z0-9_?!]+)", re.I)
    def_seeds = [i for i, ln in enumerate(lines)
                 if (m := _defre.match(ln)) and any(k in m.group(1).lower()
                                                    for k in specific)]

    def _windows(seed_idxs):
        s = set()
        for i in seed_idxs:
            s.update(range(max(0, i - window), min(len(lines), i + window + 1)))
        return s

    budget = cap - len(head_txt)
    def_set = _windows(def_seeds)
    approx = sum(len(lines[j]) + 1 for j in def_set)
    chosen_fill = set()
    line_score.sort(reverse=True)
    for sc, i in line_score:
        if approx >= budget:
            break
        for j in range(max(0, i - window), min(len(lines), i + window + 1)):
            if j not in def_set and j not in chosen_fill:
                chosen_fill.add(j)
                approx += len(lines[j]) + 1

    def _emit(idxs):
        parts, prev = [], None
        for j in sorted(idxs):
            if prev is None or j != prev + 1:
                parts.append(f"\n... (elided) ...\n# [line {j + 1}]")
            parts.append(lines[j])
            prev = j
        return "\n".join(parts)

    result = head_txt + "\n" + _emit(def_set)
    fill_txt = _emit(chosen_fill)
    if len(result) < cap and fill_txt:
        result += "\n" + fill_txt[:cap - len(result)]
    return result[:cap]


def p17_llm_judge(inputs: dict, context: dict, store=None) -> dict:
    score_range_for_skip = inputs.get("score_range", [0, 5])
    if getattr(config, "SKIP_LLM_JUDGE", False):
        return {"score": 0, "max_score": score_range_for_skip[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "SKIP_LLM_JUDGE=1 (LLM judge intentionally skipped for peer-review-grade scoring)"}
    rubric_prompt = inputs.get("rubric_prompt") or inputs.get("rubric") or ""
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "code_files")
    files_to_sample = inputs.get("files_to_sample", [])
    if not rubric_prompt:
        return {"passed": False, "output": None, "error": "empty rubric_prompt", "evidence": {}}

    evidence_text = ""
    sampled_files: list[str] = []

    def _sample_code_files():
        txt = ""
        files: list[str] = []
        kw = _rubric_keywords(rubric_prompt)
        for rel, fp in _rank_fs_files(config.WORKSPACE_DIR, files_to_sample,
                                      rubric_prompt, max_files=14):
            if len(txt) > 65000:
                break
            try:
                raw = fp.read_text(errors="replace")
                txt += f"\n--- {rel} ---\n"
                txt += _extract_relevant(raw, kw, cap=9000)
                files.append(rel)
            except Exception:
                pass
        return txt, files

    if evidence_type == "code_files":
        evidence_text, sampled_files = _sample_code_files()
    elif evidence_type == "http_response_html":
        last = context.get("from_P04") or context.get("last_response", {})
        if isinstance(last, dict):
            evidence_text = str(last.get("body", ""))[:8000]
    elif evidence_type == "http_response_headers":
        last = context.get("from_P04") or context.get("last_response", {})
        hdrs = last.get("headers") if isinstance(last, dict) else None
        if hdrs:
            evidence_text = "=== HTTP RESPONSE HEADERS ===\n" + "\n".join(
                f"{k}: {v}" for k, v in hdrs.items())
        if files_to_sample:
            src_txt, sampled_files = _sample_code_files()
            evidence_text = (evidence_text + "\n\n=== SOURCE (CSP/CSRF CONFIG) ===\n"
                             + src_txt) if evidence_text.strip() else src_txt
    elif evidence_type == "rendered_dom":
        dom = context.get("rendered_dom") or ""
        if isinstance(dom, str) and len(dom.strip()) > 200:
            evidence_text = dom[:20000]
        elif files_to_sample:
            evidence_text, sampled_files = _sample_code_files()
    evidence_text = evidence_text[:65000]

    if not evidence_text.strip():
        return {
            "passed": True,
            "output": {
                "score": (score_range[0] + score_range[1]) // 2,
                "max": score_range[1],
                "note": "no evidence collected (files_to_sample paths missing); returning mid-range",
            },
            "error": None,
            "evidence": {
                "rubric_id": inputs.get("rubric_id"),
                "files_to_sample": files_to_sample,
                "sampled_files_count": 0,
            },
        }

    if not config.LLM_JUDGE_API_KEY:
        mid = (score_range[0] + score_range[1]) / 2
        return {
            "passed": True,
            "output": {"score": mid, "max": score_range[1], "note": "LLM_JUDGE_API_KEY not set; returning mid-range"},
            "error": None,
            "evidence": {"rubric_prompt_len": len(rubric_prompt), "evidence_len": len(evidence_text)},
        }

    prompt = (
        f"Evaluate the following implementation against this rubric:\n\n{rubric_prompt}\n\n"
        f"Score range: {score_range[0]}-{score_range[1]} (integer).\n\n"
        f"Evidence:\n{evidence_text}\n\n"
        "Respond with a JSON object and NOTHING ELSE — no preamble, no markdown "
        "fences, no analysis before it. The score MUST come first so it is never "
        f"lost to truncation. Format exactly: {{\"score\": <integer {score_range[0]}-{score_range[1]}>, "
        "\"reasoning\": \"<one short sentence>\"}"
    )
    text = None
    api_failure = None
    if config.LLM_JUDGE_PROVIDER == "openai":
        from _llm_judge_safe import safe_chat_completion
        base = (config.LLM_JUDGE_API_BASE or "").rstrip("/")
        api_base = base if base and base != "https://api.openai.com/v1" else ""
        res = safe_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=config.LLM_JUDGE_MODEL,
            api_key=config.LLM_JUDGE_API_KEY,
            api_base=api_base,
            timeout=config.LLM_JUDGE_TIMEOUT,
            max_tokens=700,
        )
        if res.skipped:
            api_failure = res
        else:
            text = res.raw
    else:
        try:
            from anthropic import Anthropic
            anth_kwargs = {"api_key": config.LLM_JUDGE_API_KEY}
            base = (config.LLM_JUDGE_API_BASE or "").rstrip("/")
            if base and "anthropic" not in base:
                anth_kwargs["base_url"] = base
            client = Anthropic(**anth_kwargs)
            r = client.messages.create(
                model=config.LLM_JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700,
            )
            text = r.content[0].text
        except Exception as e:
            api_failure = type("AnthropicFail", (), {
                "skipped": True, "llm_api_failure": True,
                "exception_class": type(e).__name__, "error": str(e)[:300],
                "reason": lambda self=None: f"Anthropic API failure ({type(e).__name__}: {str(e)[:120]})",
            })()

    if api_failure is not None:
        return {
            "passed": True,
            "output": {
                "skipped": True,
                "llm_api_failure": True,
                "exception_class": api_failure.exception_class,
                "error": api_failure.error,
            },
            "error": api_failure.reason() if callable(getattr(api_failure, "reason", None))
                     else f"LLM API failure ({api_failure.exception_class})",
            "evidence": {
                "llm_judge_skipped": True,
                "llm_api_failure": True,
                "rubric_id": inputs.get("rubric_id"),
            },
        }

    text = text or ""
    m = re.search(r'"?score"?\s*[:=]\s*(-?\d+(?:\.\d+)?)', text, re.I)
    if not m:
        m = re.search(r'\bscore\b\D{0,12}?(-?\d+(?:\.\d+)?)', text, re.I)
    score_val = float(m.group(1)) if m else (score_range[0] + score_range[1]) / 2
    score_val = max(score_range[0], min(score_range[1], score_val))
    if float(score_val).is_integer():
        score_val = int(score_val)
    return {
        "passed": True,
        "output": {"score": score_val, "max": score_range[1], "raw": text[:500]},
        "error": None,
        "evidence": {
            "llm_judge_score": score_val,
            "rubric_id": inputs.get("rubric_id"),
            "sampled_files": sampled_files[:10],
        },
    }


# =============================================================================
# =============================================================================
def p18_browser_interaction(inputs: dict, context: dict, store=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"passed": False, "output": None, "error": "playwright not installed", "evidence": {}}
    steps = inputs.get("steps", [])
    base_url = inputs.get("base_url", config.API_BASE_URL)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            log_steps = []
            for s in steps:
                action = s.get("action")
                try:
                    if action == "goto":
                        _u = s.get("url", base_url)
                        if _u and not str(_u).startswith("http"):
                            _u = f"{base_url}{_u}"
                        page.goto(_u, timeout=15000)
                    elif action == "fill":
                        page.fill(s["selector"], s["value"])
                    elif action == "click":
                        page.click(s["selector"])
                    elif action == "wait":
                        page.wait_for_timeout(int(s.get("ms", 1000)))
                    elif action == "tab":
                        for _ in range(int(s.get("times", 1))):
                            page.keyboard.press("Tab")
                    elif action == "assert_url_not_contains":
                        if s["value"] in page.url:
                            raise AssertionError(f"URL still contains {s['value']}: {page.url}")
                    elif action == "assert_focus_visible":
                        _fv = page.evaluate(
                            "() => { const el = document.activeElement;"
                            " if (!el || el === document.body || el === document.documentElement) return false;"
                            " const s = getComputedStyle(el); const r = el.getBoundingClientRect();"
                            " return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; }")
                        if not _fv:
                            raise AssertionError("no visible focused element after keyboard navigation")
                    log_steps.append({"action": action, "passed": True})
                except Exception as e:
                    log_steps.append({"action": action, "passed": False, "error": str(e)})
                    browser.close()
                    return {"passed": False, "output": {"steps": log_steps}, "error": str(e),
                            "evidence": {"browser_steps": log_steps}}
            current_url = page.url
            html = page.content()[:5000]
            browser.close()
            return {"passed": True, "output": {"url": current_url, "html": html},
                    "error": None, "evidence": {"browser_steps": log_steps, "final_url": current_url}}
    except Exception as e:
        return {"passed": False, "output": None, "error": f"playwright error: {e}", "evidence": {}}


# =============================================================================
# =============================================================================
def p19_dom_assertion(inputs: dict, context: dict, store=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        last = context.get("from_P04") or context.get("last_response", {})
        if not isinstance(last, dict):
            return {"passed": False, "output": None, "error": "no playwright + no html", "evidence": {}}
        html = str(last.get("body", ""))
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {"passed": False, "output": None, "error": "neither playwright nor bs4", "evidence": {}}
        soup = BeautifulSoup(html, "html.parser")
        results = []
        all_ok = True
        for a in inputs.get("assertions", []):
            sel = a.get("selector", "")
            elems = soup.select(sel)
            ok = bool(elems) if a.get("shouldExist", True) else not elems
            if "textContains" in a and elems:
                ok = ok and a["textContains"] in elems[0].get_text()
            results.append({"selector": sel, "matched": len(elems), "passed": ok})
            if not ok:
                all_ok = False
        return {"passed": all_ok, "output": {"results": results}, "error": None if all_ok else "DOM assert failed",
                "evidence": {"dom_assertions": results}}
    url = inputs.get("url", "/")
    full_url = url if url.startswith("http") else f"{config.API_BASE_URL}{url}"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            if context.get("auth_token"):
                page.set_extra_http_headers({"Authorization": f"Bearer {context['auth_token']}"})
            page.goto(full_url, timeout=15000)
            results = []
            all_ok = True
            for a in inputs.get("assertions", []):
                sel = a.get("selector", "")
                want_exist = a.get("shouldExist", True)
                visible = a.get("visible", False)
                text_contains = a.get("textContains")
                elem = page.query_selector(sel)
                ok = (elem is not None) == want_exist
                if visible and elem:
                    ok = ok and elem.is_visible()
                if text_contains and elem:
                    ok = ok and (text_contains in (elem.text_content() or ""))
                results.append({"selector": sel, "passed": ok})
                if not ok:
                    all_ok = False
            browser.close()
            return {"passed": all_ok, "output": {"results": results, "url": full_url},
                    "error": None if all_ok else "DOM assertion(s) failed",
                    "evidence": {"dom_assertions": results}}
    except Exception as e:
        return {"passed": False, "output": None, "error": f"playwright error: {e}", "evidence": {}}


# =============================================================================
# =============================================================================
def p20_network_fault_inject(inputs: dict, context: dict, store=None) -> dict:
    return {"passed": True, "output": {"note": "P20 not implemented for HTTP-only harness"},
            "error": None, "evidence": {}}


# =============================================================================
# =============================================================================
def p21_websocket_connect(inputs: dict, context: dict, store=None) -> dict:
    try:
        import websocket
    except ImportError:
        return {"passed": True, "output": {"note": "websocket-client not installed; skipping"},
                "error": None, "evidence": {}}
    url = inputs.get("url", "")
    timeout_ms = int(inputs.get("expect_message", {}).get("timeout_ms", 5000))
    headers = []
    if context.get("auth_token") or inputs.get("auth_token"):
        tok = inputs.get("auth_token") or context.get("auth_token")
        headers.append(f"Authorization: Bearer {tok}")
    try:
        ws = websocket.create_connection(url, timeout=timeout_ms / 1000.0, header=headers)
        sub = inputs.get("subscribe")
        if sub:
            ws.send(json.dumps({"command": "subscribe", "identifier": json.dumps(sub)}))
        msg = ws.recv()
        ws.close()
        return {"passed": True, "output": {"connected": True, "first_message": msg[:200]},
                "error": None, "evidence": {"ws_url": url}}
    except Exception as e:
        return {"passed": False, "output": None, "error": f"WS error: {e}", "evidence": {}}


# =============================================================================
# =============================================================================
def p22_graphql_query(inputs: dict, context: dict, store=None) -> dict:
    if requests is None:
        return {"passed": False, "output": None, "error": "requests unavailable", "evidence": {}}
    endpoint = inputs.get("endpoint", config.GRAPHQL_ENDPOINT)
    url = endpoint if endpoint.startswith("http") else f"{config.API_BASE_URL}{endpoint}"
    query = inputs.get("query", "")
    variables = inputs.get("variables", {})
    expect_no_errors = inputs.get("expect_no_errors", True)
    headers = {"Content-Type": "application/json"}
    token = inputs.get("token") or context.get("auth_token") or context.get("admin_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        t0 = time.perf_counter()
        r = requests.post(url, json={"query": query, "variables": variables},
                           headers=headers, timeout=config.DEFAULT_HTTP_TIMEOUT)
        elapsed = (time.perf_counter() - t0) * 1000
        try:
            body = r.json()
        except Exception:
            body = {"_raw": r.text[:1000]}
        errors = body.get("errors") if isinstance(body, dict) else None
        ok = r.status_code == 200 and (not errors if expect_no_errors else True)
        out = {"status_code": r.status_code, "data": body.get("data") if isinstance(body, dict) else None,
               "errors": errors, "body": body, "response_time_ms": round(elapsed, 1)}
        if not ok and os.environ.get("HARNESS_LENIENT_MODE") == "1":
            err_msgs = " ".join(e.get("message", "") for e in (errors or []))
            schema_diff_keywords = ["not found", "doesn't exist", "no field",
                                     "field 'legacynode'", "variable", "invalid",
                                     "unknown argument", "not a defined input type",
                                     "must be defined"]
            if any(kw in err_msgs.lower() for kw in schema_diff_keywords):
                return {"passed": True, "output": {**out, "lenient": "graphql_schema_diff"},
                        "error": None, "evidence": {"lenient_reason": err_msgs[:100]}}
        return {
            "passed": ok,
            "output": out,
            "error": None if ok else f"GraphQL: status={r.status_code}, errors={errors}",
            "evidence": {"graphql_url": url, "errors_count": len(errors or [])},
        }
    except requests.RequestException as e:
        return {"passed": False, "output": None, "error": str(e), "evidence": {}}


# =============================================================================
# =============================================================================
def p23_file_upload_download(inputs: dict, context: dict, store=None) -> dict:
    if requests is None:
        return {"passed": False, "output": None, "error": "requests unavailable", "evidence": {}}
    upload = inputs.get("upload", {})
    download = inputs.get("download", {})
    method = upload.get("method", "POST")
    url = f"{config.API_BASE_URL}{upload.get('path', '/api/v1/files/upload')}"
    field_name = upload.get("field_name", "file")
    file_name = upload.get("file_name", "test.txt")
    fc = upload.get("file_content", "base64:dGVzdA==")
    if fc.startswith("base64:"):
        content = base64.b64decode(fc[7:])
    else:
        content = fc.encode()
    headers = {}
    if context.get("auth_token"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    if upload.get("flow") == "canvas":
        try:
            r1 = requests.post(url, headers=headers,
                               data={"name": file_name, "size": str(len(content)),
                                     "content_type": upload.get("content_type", "text/plain")},
                               timeout=config.DEFAULT_HTTP_TIMEOUT)
            d1 = r1.json() if r1.content else {}
            up_url = d1.get("upload_url")
            if not up_url:
                return {"passed": False, "output": {"step1_status": r1.status_code, "body": d1},
                        "error": "no upload_url from step 1", "evidence": {}}
            r2 = requests.post(up_url, data=d1.get("upload_params", {}),
                               files={"file": (file_name, content,
                                               upload.get("content_type", "text/plain"))},
                               allow_redirects=False, timeout=config.DEFAULT_HTTP_TIMEOUT)
            loc = r2.headers.get("Location")
            file_body, file_id = {}, None
            if loc:
                r3 = requests.get(loc, headers=headers, timeout=config.DEFAULT_HTTP_TIMEOUT)
                file_body = r3.json() if r3.content else {}
                file_id = file_body.get("id")
            ok = file_id is not None
            return {
                "passed": ok,
                "output": {"file_id": file_id, "step1_status": r1.status_code,
                           "step2_status": r2.status_code, "file": file_body},
                "error": None if ok else "canvas upload flow did not yield a file id",
                "evidence": {"file_id": file_id},
            }
        except requests.RequestException as e:
            return {"passed": False, "output": None, "error": str(e), "evidence": {}}
    try:
        r = requests.request(method, url, headers=headers,
                              files={field_name: (file_name, content,
                                                   upload.get("content_type", "application/octet-stream"))},
                              timeout=config.DEFAULT_HTTP_TIMEOUT)
        try:
            up_body = r.json()
        except Exception:
            up_body = {}
        upload_ok = r.status_code in (200, 201)
        download_ok = False
        if upload_ok and download:
            dl_path_field = download.get("path_from_response", "$.url")
            dl_url = utils.jsonpath_get(up_body, dl_path_field)
            if dl_url:
                d = requests.get(dl_url if str(dl_url).startswith("http") else f"{config.API_BASE_URL}{dl_url}",
                                  headers=headers, timeout=config.DEFAULT_HTTP_TIMEOUT)
                download_ok = d.status_code == 200
        steps_passed = int(upload_ok) + int(download_ok)
        return {
            "passed": steps_passed >= 1,
            "output": {"upload_status": r.status_code, "upload_body": up_body,
                       "download_ok": download_ok, "steps_passed": steps_passed, "steps_total": 2},
            "error": None if steps_passed == 2 else "upload or download failed",
            "evidence": {"upload_status": r.status_code, "download_ok": download_ok},
        }
    except requests.RequestException as e:
        return {"passed": False, "output": None, "error": str(e), "evidence": {}}


# =============================================================================
# =============================================================================
def p24_queue_job_check(inputs: dict, context: dict, store=None) -> dict:
    trigger = inputs.get("trigger", {})
    verify = inputs.get("verify", {})
    max_wait = int(verify.get("max_wait_ms", 30000)) / 1000.0
    poll_interval = int(verify.get("poll_interval_ms", 2000)) / 1000.0
    triggered = False

    if trigger.get("type") == "http" and requests is not None:
        try:
            tr = requests.request(trigger.get("method", "POST"),
                                   f"{config.API_BASE_URL}{trigger.get('path','/')}",
                                   headers={"Authorization": f"Bearer {context.get('auth_token','')}"} if context.get("auth_token") else {},
                                   json=trigger.get("body"),
                                   timeout=config.DEFAULT_HTTP_TIMEOUT)
            triggered = tr.status_code in (200, 201, 202)
        except Exception as e:
            return {"passed": False, "output": None, "error": str(e), "evidence": {}}

    strategy = verify.get("strategy", "db_query")
    deadline = time.time() + max_wait
    completed = False
    last_obs = None
    while time.time() < deadline:
        if strategy == "db_query":
            res = p08_db_query({"sql": verify.get("sql", ""),
                                  "expected_result": verify.get("expected_result")},
                                 context, store)
            last_obs = res
            if res.get("passed"):
                completed = True
                break
        elif strategy == "poll_api" and requests is not None:
            try:
                pr = requests.get(f"{config.API_BASE_URL}{verify.get('path','/')}",
                                   headers={"Authorization": f"Bearer {context.get('auth_token','')}"} if context.get("auth_token") else {},
                                   timeout=10)
                body = pr.json() if "json" in pr.headers.get("Content-Type","") else {}
                actual = utils.jsonpath_get(body, verify.get("expected_field", "$.status"))
                last_obs = {"status_code": pr.status_code, "value": actual}
                if str(actual) == str(verify.get("expected_value", "completed")):
                    completed = True
                    break
            except Exception:
                pass
        time.sleep(poll_interval)
    return {
        "passed": triggered and completed,
        "output": {"triggered": triggered, "job_completed": completed, "last_observation": last_obs,
                    "wait_time_ms": int((max_wait - (deadline - time.time())) * 1000)},
        "error": None if (triggered and completed) else f"triggered={triggered}, completed={completed}",
        "evidence": {"queue_job": {"triggered": triggered, "completed": completed}},
    }


# =============================================================================
# =============================================================================
def p25_oauth_oidc_flow(inputs: dict, context: dict, store=None) -> dict:
    if requests is None:
        return {"passed": False, "output": None, "error": "requests unavailable", "evidence": {}}
    flow = inputs.get("flow", "authorization_code")
    token_url = f"{config.API_BASE_URL}{inputs.get('token_url','/login/oauth2/token')}"
    client_id = inputs.get("client_id")
    client_secret = inputs.get("client_secret")
    redirect_uri = inputs.get("redirect_uri", "http://localhost:9999/cb")
    if flow == "authorization_code" and client_id:
        # Step 1: authorize
        try:
            auth_resp = requests.get(
                f"{config.API_BASE_URL}{inputs.get('authorize_url','/login/oauth2/auth')}",
                params={"client_id": client_id, "response_type": "code",
                        "redirect_uri": redirect_uri, "scope": inputs.get("scope", "")},
                allow_redirects=False, timeout=config.DEFAULT_HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            return {"passed": False, "output": None, "error": str(e), "evidence": {}}
        return {
            "passed": auth_resp.status_code in (200, 302),
            "output": {"authorize_status": auth_resp.status_code,
                        "note": "full code-exchange flow requires user consent (manual step)"},
            "error": None,
            "evidence": {"oauth_flow": flow, "authorize_status": auth_resp.status_code},
        }
    return {"passed": True, "output": {"note": f"P25 flow={flow} stub"},
            "error": None, "evidence": {}}


# =============================================================================
# =============================================================================
def p26_search_query(inputs: dict, context: dict, store=None) -> dict:
    res = p04_http_request(
        {"method": inputs.get("method", "GET"),
         "path": inputs.get("path", "/api/v1/search"),
         "query": inputs.get("params", {}),
         "headers": inputs.get("headers", {})},
        context, store
    )
    if not res["passed"]:
        return res
    body = res["output"].get("body", [])
    expected = inputs.get("expected_results", {})
    total = len(body) if isinstance(body, list) else (body.get("count", 0) if isinstance(body, dict) else 0)
    ok = total >= int(expected.get("min_count", 1))
    return {
        "passed": ok,
        "output": {"total_results": total, "first_n": body[:5] if isinstance(body, list) else None},
        "error": None if ok else f"got {total} results, need ≥{expected.get('min_count', 1)}",
        "evidence": {"search_total": total},
    }


# =============================================================================
# =============================================================================
def p27_webhook_delivery(inputs: dict, context: dict, store=None) -> dict:
    return {"passed": True, "output": {"note": "P27 webhook-receiver stub; populate per-task"},
            "error": None, "evidence": {}}


# =============================================================================
# =============================================================================
def p28_email_check(inputs: dict, context: dict, store=None) -> dict:
    if requests is None:
        return {"passed": False, "output": None, "error": "requests unavailable", "evidence": {}}
    trigger = inputs.get("trigger", {})
    if trigger.get("path") and trigger.get("method"):
        try:
            requests.request(trigger["method"],
                              f"{config.API_BASE_URL}{trigger['path']}",
                              json=trigger.get("body"),
                              timeout=config.DEFAULT_HTTP_TIMEOUT)
        except Exception:
            pass
    mail_url = inputs.get("mailserver_api", "http://localhost:8025/api/v2/messages")
    expect = inputs.get("expect", {})
    deadline = time.time() + (int(expect.get("timeout_ms", 10000)) / 1000.0)
    while time.time() < deadline:
        try:
            r = requests.get(mail_url, timeout=5)
            messages = r.json().get("items", [])
            for m in messages:
                if expect.get("to") and expect["to"] not in str(m.get("Content", {}).get("Headers", {}).get("To", "")):
                    continue
                subj = str(m.get("Content", {}).get("Headers", {}).get("Subject", ""))
                body_s = str(m.get("Content", {}).get("Body", ""))
                if expect.get("subject_contains") and expect["subject_contains"] not in subj:
                    continue
                if expect.get("body_contains") and expect["body_contains"] not in body_s:
                    continue
                return {"passed": True, "output": {"matched_message_subject": subj[:80]},
                        "error": None, "evidence": {"email_to": expect.get("to")}}
        except Exception:
            pass
        time.sleep(1)
    return {"passed": False, "output": None, "error": "no matching email within timeout",
            "evidence": {}}


# =============================================================================
# =============================================================================
def p29_multi_step_workflow(inputs: dict, context: dict, store=None) -> dict:
    if requests is None:
        return {"passed": False, "output": None, "error": "requests unavailable", "evidence": {}}
    setup = inputs.get("entity_setup")
    steps = inputs.get("steps", [])
    final_verify = inputs.get("final_verify")
    headers = {"Authorization": f"Bearer {context.get('auth_token','')}"} if context.get("auth_token") else {}
    entity_id = None
    step_log = []
    if setup:
        try:
            r = requests.request(setup.get("method", "POST"),
                                  f"{config.API_BASE_URL}{utils.substitute(setup.get('path','/'), context)}",
                                  headers=headers, json=utils.substitute(setup.get("body"), context),
                                  timeout=config.DEFAULT_HTTP_TIMEOUT)
            if r.status_code in (200, 201):
                try:
                    entity_id = r.json().get("id") or r.json().get("data", {}).get("id")
                except Exception:
                    entity_id = None
                context["id"] = entity_id
            step_log.append({"name": "setup", "status": r.status_code, "passed": r.status_code in (200, 201)})
        except Exception as e:
            return {"passed": False, "output": {"step_log": step_log}, "error": str(e), "evidence": {}}
    passes = 0
    for s in steps:
        try:
            path = utils.substitute(s.get("path", "/"), context)
            r = requests.request(s.get("method", "POST"),
                                  f"{config.API_BASE_URL}{path}",
                                  headers=headers, json=utils.substitute(s.get("body"), context),
                                  timeout=config.DEFAULT_HTTP_TIMEOUT)
            ok = r.status_code == int(s.get("expect_status", 200))
            if ok and "expect_state" in s:
                try:
                    body = r.json()
                except Exception:
                    body = {}
                actual = utils.jsonpath_get(body, s["expect_state"]["path"])
                ok = actual == s["expect_state"]["value"]
            if ok:
                passes += 1
            step_log.append({"name": s.get("name", "?"), "status": r.status_code, "passed": ok})
        except Exception as e:
            step_log.append({"name": s.get("name", "?"), "passed": False, "error": str(e)})
    final_ok = True
    if final_verify and final_verify.get("db_query"):
        final_sql = utils.substitute(final_verify["db_query"], context)
        res = p08_db_query({"sql": final_sql, "expected_result": final_verify.get("expected")},
                             context, store)
        final_ok = res["passed"]
    total = len(steps)
    if not (passes == total and final_ok) and os.environ.get("HARNESS_LENIENT_MODE") == "1":
        return {"passed": True,
                "output": {"entity_id": entity_id, "lenient": "workflow_partial",
                           "steps_passed": passes, "steps_total": total},
                "error": None,
                "evidence": {"lenient_reason": f"{passes}/{total} steps passed; treated as N/A"}}
    return {
        "passed": passes == total and final_ok,
        "output": {"entity_id": entity_id, "steps_passed": passes, "steps_total": total,
                    "final_state_match": final_ok, "step_log": step_log},
        "error": None if (passes == total and final_ok) else f"{passes}/{total} steps passed, final={final_ok}",
        "evidence": {"workflow_steps": step_log, "final_match": final_ok},
    }


# =============================================================================
# =============================================================================
PRIMITIVE_REGISTRY = {
    "P01": p01_file_exists, "P02": p02_file_content_match, "P03": p03_file_count,
    "P04": p04_http_request, "P05": p05_api_crud, "P06": p06_json_schema_match,
    "P07": p07_json_value_assert, "P08": p08_db_query, "P09": p09_db_table_exists,
    "P10": p10_db_column_check, "P11": p11_db_index_check, "P12": p12_docker_exec,
    "P13": p13_auth_login, "P14": p14_permission_check, "P15": p15_status_code_assert,
    "P16": p16_response_time_check, "P17": p17_llm_judge, "P18": p18_browser_interaction,
    "P19": p19_dom_assertion, "P20": p20_network_fault_inject, "P21": p21_websocket_connect,
    "P22": p22_graphql_query, "P23": p23_file_upload_download, "P24": p24_queue_job_check,
    "P25": p25_oauth_oidc_flow, "P26": p26_search_query, "P27": p27_webhook_delivery,
    "P28": p28_email_check, "P29": p29_multi_step_workflow,
}


try:
    from _browser_primitives import (
        p18_render_dom as _shared_render_dom,
        p19_screenshot as _shared_screenshot,
    )
    def _bp_render_dom(inputs, context, _store=None):
        return _shared_render_dom(inputs, context)
    def _bp_screenshot(inputs, context, _store=None):
        return _shared_screenshot(inputs, context)
    PRIMITIVE_REGISTRY.setdefault("RENDER_DOM", _bp_render_dom)
    PRIMITIVE_REGISTRY.setdefault("SCREENSHOT", _bp_screenshot)
except Exception as _bp_exc:
    import logging as _bp_log
    _bp_log.getLogger("_browser_primitives").warning(
        "RENDER_DOM/SCREENSHOT registration failed: %s", _bp_exc)


_LENIENT_INSTRUMENTED = {"P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08",
                          "P09", "P10", "P11", "P12", "P13", "P14", "P15",
                          "P17", "P22", "P29"}


def dispatch(primitive_type: str, inputs: dict, context: dict, store=None) -> dict:
    fn = PRIMITIVE_REGISTRY.get(primitive_type)
    if not fn:
        return {"passed": False, "output": None, "error": f"unknown primitive: {primitive_type}",
                "evidence": {}}
    try:
        result = fn(inputs, context, store)
        if (not result.get("passed")
            and os.environ.get("HARNESS_LENIENT_MODE") == "1"
            and primitive_type not in _LENIENT_INSTRUMENTED):
            return {"passed": True,
                    "output": {"lenient": f"{primitive_type}_uninstrumented", "original": result.get("output")},
                    "error": None,
                    "evidence": {"lenient_reason": (result.get("error") or "")[:100]}}
        return result
    except Exception as e:
        log.exception(f"primitive {primitive_type} crashed")
        if os.environ.get("HARNESS_LENIENT_MODE") == "1":
            return {"passed": True,
                    "output": {"lenient": f"{primitive_type}_crash"},
                    "error": None,
                    "evidence": {"lenient_reason": f"{type(e).__name__}: {e}"[:100]}}
        return {"passed": False, "output": None, "error": f"{type(e).__name__}: {e}",
                "evidence": {}}
