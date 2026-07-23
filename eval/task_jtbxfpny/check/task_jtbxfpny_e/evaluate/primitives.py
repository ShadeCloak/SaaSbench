import glob as glob_mod
import io
import json
import logging
import os
import re
import subprocess
import time
import zipfile
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

from config import (
    APP_BASE_URL, API_BASE_URL, DB_HOST, DB_NAME, DB_PASSWORD,
    DB_PORT, DB_USER, APP_CONTAINER, DB_CONTAINER, HTTP_TIMEOUT,
    LLM_API_KEY, LLM_API_BASE, LLM_MODEL, WORKSPACE_DIR, TEST_USERS,
)
from utils import context, get_db_connection, resolve_placeholders, resolve_deep

logger = logging.getLogger(__name__)

_token_cache: dict[str, str] = {}
_session_cache: dict[str, requests.Session] = {}
_csrf_cache: dict[str, str] = {}
_csrf_endpoint_cache: Optional[str] = None
_login_endpoint_cache: Optional[str] = None

CSRF_ENDPOINT_CANDIDATES = [
    "/api/v1/security/csrf_token/",
    "/api/csrf/",
    "/csrf-token",
    "/auth/csrf",
    "/api/auth/csrf",
]
LOGIN_ENDPOINT_CANDIDATES = [
    "/api/v1/security/login",
    "/api/auth/login",
    "/api/login",
    "/login",
]
OPENAPI_ENDPOINT_CANDIDATES = [
    "/api/v1/_openapi",
    "/openapi.json",
    "/swagger.json",
    "/api/openapi.json",
    "/docs/openapi.json",
]


def _get_session(role: str = "__default__") -> requests.Session:
    if role not in _session_cache:
        _session_cache[role] = requests.Session()
    return _session_cache[role]


def _extract_csrf_token(resp_json: Any) -> str:
    if isinstance(resp_json, dict):
        for key in ("result", "csrf_token", "csrfToken", "token", "csrf"):
            v = resp_json.get(key)
            if isinstance(v, str) and v:
                return v
    if isinstance(resp_json, str) and resp_json:
        return resp_json
    return ""


def _get_csrf_token(role: str = "admin") -> str:
    global _csrf_endpoint_cache
    if role in _csrf_cache:
        return _csrf_cache[role]
    session = _get_session(role)
    token = _token_cache.get(role, "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    endpoints = [_csrf_endpoint_cache] if _csrf_endpoint_cache else CSRF_ENDPOINT_CANDIDATES
    for ep in endpoints:
        if not ep:
            continue
        try:
            resp = session.get(APP_BASE_URL + ep, headers=headers, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text
                csrf = _extract_csrf_token(body)
                if csrf:
                    _csrf_cache[role] = csrf
                    _csrf_endpoint_cache = ep
                    return csrf
        except Exception as e:
            logger.debug("CSRF token attempt %s failed for %s: %s", ep, role, e)
    return ""


def _get_auth_headers(role: str = "admin") -> dict:
    token = _token_cache.get(role)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _extract_access_token(body: Any) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    for key in ("access_token", "accessToken", "token", "jwt", "id_token"):
        v = body.get(key)
        if isinstance(v, str) and v:
            return v
    result = body.get("result") or body.get("data")
    if isinstance(result, dict):
        return _extract_access_token(result)
    return None


def _login_for_token(username: str, password: str, role: str = "admin") -> Optional[str]:
    global _login_endpoint_cache
    session = _get_session(role)

    payload_variants = [
        {"username": username, "password": password, "provider": "db", "refresh": True},
        {"username": username, "password": password},
        {"email": username, "password": password},
        {"login": username, "password": password},
    ]

    endpoints = [_login_endpoint_cache] if _login_endpoint_cache else LOGIN_ENDPOINT_CANDIDATES
    for ep in endpoints:
        if not ep:
            continue
        for payload in payload_variants:
            try:
                resp = session.post(APP_BASE_URL + ep, json=payload, timeout=HTTP_TIMEOUT)
                if resp.status_code != 200:
                    continue
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                token = _extract_access_token(body)
                if token or resp.cookies:
                    _login_endpoint_cache = ep
                    if token:
                        _csrf_cache.pop(role, None)
                        _get_csrf_token(role)
                    return token or "session"
            except Exception as e:
                logger.debug("Login attempt %s failed for %s: %s", ep, username, e)
    logger.error("All login endpoints failed for %s", username)
    return None


def _ensure_user_exists(role: str) -> None:
    cfg = TEST_USERS.get(role)
    if not cfg:
        return
    candidates = cfg.get("cli_create_candidates") or []
    if not candidates and cfg.get("cli_create"):
        candidates = [cfg["cli_create"]]
    for cmd in candidates:
        try:
            result = subprocess.run(
                ["docker", "exec", APP_CONTAINER, "sh", "-c", cmd],
                capture_output=True, text=True, timeout=30,
            )
            out = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0 or "already exists" in out.lower() or "duplicate" in out.lower():
                return
        except Exception:
            continue


def _ensure_auth(role: str) -> str:
    if role in _token_cache:
        return _token_cache[role]

    cfg = TEST_USERS.get(role, TEST_USERS["admin"])
    _ensure_user_exists(role)
    token = _login_for_token(cfg["username"], cfg["password"], role=role)
    if token:
        _token_cache[role] = token
        return token
    return ""



def p01_file_exists(inputs: dict, ctx: dict) -> dict:
    path = inputs.get("path", "")
    full = os.path.join(WORKSPACE_DIR, path)
    exists = os.path.exists(full)
    return {"passed": exists, "exists": exists, "path": full}



def p02_file_content_match(inputs: dict, ctx: dict) -> dict:
    path = inputs.get("path", "")
    full = os.path.join(WORKSPACE_DIR, path)
    match_type = inputs.get("match_type", "contains")
    pattern = inputs.get("pattern", "")

    if not os.path.isfile(full):
        return {"passed": False, "matched": False, "error": "file not found"}
    try:
        with open(full) as f:
            content = f.read()
    except Exception as e:
        return {"passed": False, "matched": False, "error": str(e)}

    if match_type == "contains":
        matched = pattern.lower() in content.lower()
    elif match_type == "regex":
        matched = bool(re.search(pattern, content))
    else:
        matched = False
    return {"passed": matched, "matched": matched}



def p03_file_count(inputs: dict, ctx: dict) -> dict:
    pattern = inputs.get("glob", "**/*")
    base_dir = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", ""))
    min_expected = inputs.get("min_expected", 1)
    files = [f for f in glob_mod.glob(os.path.join(base_dir, pattern), recursive=True) if os.path.isfile(f)]
    return {"passed": len(files) >= min_expected, "count": len(files), "min_expected": min_expected}



def p04_http_request(inputs: dict, ctx: dict) -> dict:
    resolved_inputs = resolve_deep(inputs, ctx)

    method = resolved_inputs.get("method", "GET").upper()
    path = str(resolved_inputs.get("path", "/"))
    headers = dict(resolved_inputs.get("headers", {}))
    body = resolved_inputs.get("body")
    timeout = resolved_inputs.get("timeout", HTTP_TIMEOUT)
    skip_auth = resolved_inputs.get("skip_auth", False)
    save_as = resolved_inputs.get("save_as")

    role = ctx.get("_current_role", "admin")
    if not skip_auth and path.startswith("/api/"):
        auth_h = _get_auth_headers(role)
        for k, v in auth_h.items():
            headers.setdefault(k, v)
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            csrf = _get_csrf_token(role)
            if csrf:
                headers.setdefault("X-CSRFToken", csrf)

    session = _get_session(role if not skip_auth else "__default__")
    url = APP_BASE_URL + path
    kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout, "allow_redirects": False}

    content_type = resolved_inputs.get("content_type", "")
    if content_type.startswith("multipart"):
        file_data = resolved_inputs.get("file_data")
        file_field = resolved_inputs.get("file_field", "formData")
        if file_data and isinstance(file_data, bytes):
            kwargs["files"] = {file_field: ("import.zip", io.BytesIO(file_data), "application/zip")}
        elif ctx.get("_last_export_data"):
            kwargs["files"] = {file_field: ("import.zip", io.BytesIO(ctx["_last_export_data"]), "application/zip")}
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                envelope = (
                    "version: 1.0.0\n"
                    "type: Dashboard\n"
                    "kind: Dashboard\n"
                    "resource: dashboard\n"
                    "timestamp: '2025-01-01T00:00:00'\n"
                )
                zf.writestr("metadata.yaml", envelope)
                zf.writestr("metadata.json", json.dumps({
                    "version": "1.0.0", "type": "Dashboard",
                    "kind": "Dashboard", "resource": "dashboard",
                }))
            buf.seek(0)
            kwargs["files"] = {file_field: ("import.zip", buf, "application/zip")}
        if body and isinstance(body, dict):
            kwargs["data"] = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in body.items()}
    elif isinstance(body, dict):
        kwargs["json"] = body
    elif isinstance(body, list):
        kwargs["json"] = body
    elif isinstance(body, str):
        kwargs["data"] = body

    try:
        resp = session.request(method, url, **kwargs)
        resp_body = None
        ct = resp.headers.get("Content-Type", "")
        if "json" in ct:
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = resp.text
        elif "zip" in ct or "octet-stream" in ct:
            ctx["_last_export_data"] = resp.content
            resp_body = f"[binary {len(resp.content)} bytes]"
        else:
            resp_body = resp.text

        ctx["_last_status_code"] = resp.status_code
        ctx["_last_response_body"] = resp_body
        ctx["_last_response_headers"] = dict(resp.headers)
        ctx["_last_response_time_ms"] = int(resp.elapsed.total_seconds() * 1000)
        ctx.setdefault("_response_log", []).append({
            "method": inputs.get("method", "GET").upper(),
            "path": inputs.get("path", ""),
            "status": resp.status_code,
            "content_type": resp.headers.get("Content-Type", ""),
            "body": resp_body,
        })

        result_id = None
        if isinstance(resp_body, dict):
            result_id = resp_body.get("id")
            if result_id is None and isinstance(resp_body.get("result"), dict):
                result_id = resp_body["result"].get("id")
        if result_id is not None:
            ctx["_last_created_id"] = result_id

        result = {
            "passed": True,
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp_body,
            "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
            "created_id": result_id,
        }

        if save_as:
            ctx[save_as] = result

        return result
    except Exception as e:
        logger.error("P04 %s %s -> %s", method, url, e)
        ctx["_last_status_code"] = 0
        return {"passed": False, "status_code": 0, "headers": {}, "body": None, "error": str(e)}



_NAME_FIELDS = [
    "name",
    "title",
    "label",
    "display_name",
    "slice_name",
    "chart_name",
    "dashboard_title",
    "database_name",
    "table_name",
    "dataset_name",
    "resource_name",
]


def _cleanup_existing_entity(resource: str, create_body: dict, ctx: dict) -> None:
    name_val = None
    name_field = None
    for f in _NAME_FIELDS:
        if f in create_body:
            name_val = create_body[f]
            name_field = f
            break
    if not name_val:
        return
    list_r = p04_http_request({"method": "GET", "path": resource}, ctx)
    body = list_r.get("body", {})
    results = body.get("result", []) if isinstance(body, dict) else []
    if not isinstance(results, list):
        return
    for item in results:
        if isinstance(item, dict) and item.get(name_field) == name_val:
            eid = item.get("id")
            if eid is not None:
                p04_http_request({"method": "DELETE", "path": f"{resource}{eid}"}, ctx)
                break


def p05_api_crud(inputs: dict, ctx: dict) -> dict:
    resolved = resolve_deep(inputs, ctx)

    resource = str(resolved.get("resource", ""))
    create_body = resolved.get("create_body", {})
    update_body = resolved.get("update_body", {})
    expected_create_status = resolved.get("expected_create_status", 201)
    expected_read_fields = resolved.get("expected_read_fields", [])
    expected_update_status = resolved.get("expected_update_status", 200)
    expected_delete_status = resolved.get("expected_delete_status", 200)
    keep_alive = resolved.get("keep_alive", False)

    steps_passed = 0
    steps_total = 4
    entity_id = None
    evidence = {}

    create_r = p04_http_request({"method": "POST", "path": resource, "body": create_body}, ctx)
    create_response_body = create_r.get("body")
    if create_r.get("status_code") in (409, 422) and "already exists" in str(create_r.get("body", "")).lower():
        _cleanup_existing_entity(resource, create_body, ctx)
        create_r = p04_http_request({"method": "POST", "path": resource, "body": create_body}, ctx)
        create_response_body = create_r.get("body")
    if create_r.get("status_code") == expected_create_status:
        steps_passed += 1
        body = create_r.get("body", {})
        if isinstance(body, dict):
            entity_id = body.get("id") or (body.get("result", {}).get("id") if isinstance(body.get("result"), dict) else None)
            evidence["create"] = {"id": entity_id, "status": create_r.get("status_code")}
    else:
        evidence["create_error"] = {"status": create_r.get("status_code"), "body": str(create_r.get("body", ""))[:500]}

    if entity_id is not None:
        ctx["_last_created_id"] = entity_id

        read_r = p04_http_request({"method": "GET", "path": f"{resource}{entity_id}"}, ctx)
        if read_r.get("status_code") == 200:
            body = read_r.get("body", {})
            data = body.get("result", body) if isinstance(body, dict) else {}
            if isinstance(data, dict):
                found = [f for f in expected_read_fields if f in data]
                if len(found) >= len(expected_read_fields) * 0.7:
                    steps_passed += 1
        evidence["read_status"] = read_r.get("status_code")

        update_r = p04_http_request({"method": "PUT", "path": f"{resource}{entity_id}", "body": update_body}, ctx)
        if update_r.get("status_code") == expected_update_status:
            steps_passed += 1
        evidence["update_status"] = update_r.get("status_code")

        delete_r = p04_http_request({"method": "DELETE", "path": f"{resource}{entity_id}"}, ctx)
        if delete_r.get("status_code") == expected_delete_status:
            steps_passed += 1
        evidence["delete_status"] = delete_r.get("status_code")

        if keep_alive:
            recreate_r = p04_http_request({"method": "POST", "path": resource, "body": create_body}, ctx)
            re_body = recreate_r.get("body", {})
            if isinstance(re_body, dict):
                new_id = re_body.get("id") or (re_body.get("result", {}).get("id") if isinstance(re_body.get("result"), dict) else None)
                if new_id is not None:
                    entity_id = new_id
                    ctx["_last_created_id"] = new_id
                    evidence["keep_alive_id"] = new_id
            create_response_body = recreate_r.get("body")
    else:
        evidence["skipped"] = "create failed"

    ctx["_last_response_body"] = create_response_body
    ctx["_p05_create_response"] = create_response_body

    return {
        "passed": steps_passed == steps_total,
        "steps_passed": steps_passed,
        "steps_total": steps_total,
        "entity_id": entity_id,
        "pass_ratio": steps_passed / steps_total if steps_total > 0 else 0,
        "evidence": evidence,
    }



def p06_json_schema_match(inputs: dict, ctx: dict) -> dict:
    response = inputs.get("response") or ctx.get("_last_response_body", {})
    required_fields = inputs.get("required_fields", [])

    if not isinstance(response, dict):
        return {"passed": False, "all_present": False, "missing_fields": required_fields}

    missing = []
    for fp in required_fields:
        parts = fp.split(".")
        obj = response
        found = True
        for part in parts:
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                found = False
                break
        if not found:
            missing.append(fp)

    return {
        "passed": len(missing) == 0,
        "all_present": len(missing) == 0,
        "missing_fields": missing,
        "found_count": len(required_fields) - len(missing),
        "total_count": len(required_fields),
    }



def _resolve_json_path(data: Any, path: str, ctx: dict) -> Any:
    if path.startswith("$._headers."):
        key = path[len("$._headers."):]
        headers = ctx.get("_last_response_headers", {})
        for h_key, h_val in headers.items():
            if h_key.lower() == key.lower():
                return h_val
        return None

    if path == "$":
        return data

    if not path.startswith("$."):
        path = "$." + path

    remainder = path[2:]
    if not remainder:
        return data

    parts = remainder.split(".")
    obj = data
    for part in parts:
        if obj is None:
            return None
        wildcard = re.match(r"(.+)\[\*\]$", part)
        bracket = re.match(r"(.+)\[(\d+)\]$", part)
        if wildcard:
            key = wildcard.group(1)
            obj = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(obj, list):
                return [item for item in obj]
            return None
        elif bracket:
            key, idx = bracket.group(1), int(bracket.group(2))
            obj = obj.get(key) if isinstance(obj, dict) else None
            obj = obj[idx] if isinstance(obj, list) and 0 <= idx < len(obj) else None
        elif part == "length" and isinstance(obj, list):
            return len(obj)
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def p07_json_value_assert(inputs: dict, ctx: dict) -> dict:
    assertions = inputs.get("assertions", [])
    source = inputs.get("source")
    if source and source in ctx:
        response_body = ctx[source]
    else:
        response_body = ctx.get("_last_response_body")

    results = []
    for a in assertions:
        path = a.get("path", "")
        expected = a.get("expected")
        match_type = a.get("match_type", "equals")
        tolerance = a.get("tolerance", 0)

        actual = _resolve_json_path(response_body, path, ctx)

        if match_type == "not_empty":
            passed = actual is not None and actual != "" and actual != [] and actual != {}
        elif match_type == "exists":
            passed = actual is not None
        elif match_type == "contains" and isinstance(expected, str):
            passed = isinstance(actual, str) and expected in actual
        elif match_type == "greater_than":
            try:
                passed = float(actual) > float(expected)
            except (TypeError, ValueError):
                passed = False
        elif match_type == "less_than_or_equal":
            try:
                passed = float(actual) <= float(expected)
            except (TypeError, ValueError):
                passed = False
        elif match_type == "in":
            passed = actual in expected if isinstance(expected, list) else actual == expected
        elif match_type == "all_equal":
            passed = isinstance(actual, list) and all(v == expected for v in actual)
        elif isinstance(expected, bool):
            passed = actual is expected
        elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            passed = abs(actual - expected) <= tolerance
        elif expected is None and match_type == "equals":
            passed = actual is not None
        else:
            passed = str(actual) == str(expected) if actual is not None else expected is None

        results.append({"path": path, "expected": expected, "actual": actual, "passed": passed})

    all_passed = all(r["passed"] for r in results) if results else False
    msg = ""
    if not all_passed:
        for r in results:
            if not r["passed"]:
                msg = f"P07: path={r.get('path')} expected={r.get('expected')!r} actual={r.get('actual')!r}"[:160]
                break
    return {"passed": all_passed, "all_passed": all_passed, "results": results,
            "pass_count": sum(1 for r in results if r["passed"]), "total_count": len(results),
            "message": msg}



def p08_db_query(inputs: dict, ctx: dict) -> dict:
    sql = inputs.get("sql", "")
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, ctx)
    except Exception:
        pass

    sql = resolve_placeholders(sql, ctx)

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(sql)
            if sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                conn.commit()
                rows = [{"affected": cur.rowcount}]
            else:
                rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        logger.error("P08 failed: %s -- %s", sql[:200], e)
        return {"passed": False, "rows": [], "row_count": 0, "match": False, "error": str(e)}

    expected_result = inputs.get("expected_result")
    if expected_result is None or expected_result == {}:
        return {"passed": True, "rows": rows, "row_count": len(rows), "match": True}

    if not rows:
        return {"passed": False, "rows": rows, "row_count": 0, "match": False}

    row = rows[0]
    match = True
    for k, v in expected_result.items():
        actual = row.get(k)
        if isinstance(v, bool):
            match = match and (actual is v or actual == v)
        elif isinstance(v, int) and isinstance(actual, int):
            match = match and (actual == v)
        elif actual is not None:
            match = match and (str(actual).strip() == str(v).strip())
        else:
            match = False

    return {"passed": match, "rows": rows, "row_count": len(rows), "match": match}



def p09_db_table_exists(inputs: dict, ctx: dict) -> dict:
    tables = inputs.get("tables", [])
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            existing = {r["tablename"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return {"passed": False, "existing": [], "missing": tables, "error": str(e)}

    found = [t for t in tables if t in existing]
    missing = [t for t in tables if t not in existing]
    return {
        "passed": len(missing) == 0,
        "existing": found, "missing": missing,
        "found_count": len(found), "total_count": len(tables),
    }



def p10_db_column_check(inputs: dict, ctx: dict) -> dict:
    table = inputs.get("table", "")
    expected_columns = inputs.get("expected_columns", [])
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                (table,),
            )
            actual_cols = {r["column_name"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return {"passed": False, "existing": [], "missing": expected_columns, "error": str(e)}

    found = [c for c in expected_columns if c in actual_cols]
    missing = [c for c in expected_columns if c not in actual_cols]
    return {
        "passed": len(missing) == 0,
        "existing": found, "missing": missing,
        "found_count": len(found), "total_count": len(expected_columns),
    }



def p11_db_index_check(inputs: dict, ctx: dict) -> dict:
    table = inputs.get("table", "")
    expected_indexes = inputs.get("expected_indexes", [])
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT indexname, string_agg(a.attname, ',' ORDER BY array_position(i.indkey, a.attnum)) AS columns
                FROM pg_indexes pi
                JOIN pg_class c ON c.relname = pi.indexname
                JOIN pg_index i ON i.indexrelid = c.oid
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE pi.tablename = %s AND pi.schemaname = 'public'
                GROUP BY indexname
            """, (table,))
            rows = cur.fetchall()
        conn.close()
        existing_idx = [set(r["columns"].split(",")) for r in rows]
    except Exception as e:
        return {"passed": False, "error": str(e)}

    found = sum(1 for ei in expected_indexes if any(set(ei.get("columns", [])) <= s for s in existing_idx))
    return {"passed": found == len(expected_indexes), "found": found, "total": len(expected_indexes)}



def p12_docker_exec(inputs: dict, ctx: dict) -> dict:
    command = inputs.get("command", "")
    container = inputs.get("container", APP_CONTAINER)
    expect_exit_code = inputs.get("expect_exit_code", 0)

    env_prefix = os.environ.get("TARGET_APP_ENV_PREFIX", "")
    if env_prefix and not env_prefix.rstrip().endswith("&&"):
        env_prefix = env_prefix.rstrip() + " && "
    full_command = env_prefix + command

    exec_env_args = []
    for _k in ("TARGET_APP_CLI", "TARGET_APP_ENV_PREFIX"):
        _v = os.environ.get(_k)
        if _v:
            exec_env_args += ["-e", f"{_k}={_v}"]

    try:
        result = subprocess.run(
            ["docker", "exec", *exec_env_args, container, "bash", "-c", full_command],
            capture_output=True, text=True, timeout=120,
        )
        exit_ok = (result.returncode == expect_exit_code)
        if not exit_ok and "already exists" in (result.stdout + result.stderr).lower():
            exit_ok = True
        return {"passed": exit_ok, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"passed": False, "exit_code": -1, "error": str(e)}



def p13_auth_login(inputs: dict, ctx: dict) -> dict:
    role = inputs.get("role", "admin")
    credentials = inputs.get("credentials")

    if role in _token_cache:
        ctx["_current_role"] = role
        ctx["auth_token"] = _token_cache[role]
        _csrf_cache.pop(role, None)
        _get_csrf_token(role)
        return {"passed": True, "role": role, "method": "cached"}

    if credentials:
        username = credentials.get("username", "")
        password = credentials.get("password", "")
    else:
        cfg = TEST_USERS.get(role, TEST_USERS["admin"])
        username = cfg["username"]
        password = cfg["password"]

    _ensure_user_exists(role)
    token = _login_for_token(username, password, role=role)

    if token:
        _token_cache[role] = token
        ctx["_current_role"] = role
        ctx["auth_token"] = token
        return {"passed": True, "role": role, "method": "jwt_bearer"}

    return {"passed": False, "role": role, "error": f"Login failed for {username}"}



def p14_permission_check(inputs: dict, ctx: dict) -> dict:
    resolved = resolve_deep(inputs, ctx)
    method = resolved.get("method", "GET")
    path = str(resolved.get("path", "/"))
    expected_status = resolved.get("expected_status", 403)
    body = resolved.get("body")

    req = {"method": method, "path": path}
    if body:
        req["body"] = body
    result = p04_http_request(req, ctx)
    status = result.get("status_code", 0)

    expected_result = resolved.get("expected_result", "denied")
    acceptable = resolved.get("acceptable_statuses", [expected_status])
    if isinstance(acceptable, int):
        acceptable = [acceptable]

    if expected_result == "denied":
        deny_codes = {400, 401, 403, 404, 405, 422}
        passed = status in acceptable or status in deny_codes
    else:
        passed = status in acceptable

    return {"passed": passed, "status_code": status, "expected": expected_status}



def p15_status_code_assert(inputs: dict, ctx: dict) -> dict:
    expected = inputs.get("expected_status")
    acceptable = inputs.get("acceptable_statuses") or inputs.get("acceptable")
    actual = ctx.get("_last_status_code", 0)

    accepted = set()
    for v in (expected, acceptable):
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            for x in v:
                try: accepted.add(int(x))
                except (TypeError, ValueError): pass
        else:
            try: accepted.add(int(v))
            except (TypeError, ValueError): pass

    try: actual_i = int(actual)
    except (TypeError, ValueError): actual_i = 0

    if accepted:
        passed = actual_i in accepted
    else:
        passed = 200 <= actual_i < 300

    msg = "" if passed else f"P15: status {actual_i} not in {sorted(accepted) if accepted else '2xx'}"
    return {"passed": passed, "expected": expected or acceptable, "actual": actual_i, "message": msg}



def p16_response_time_check(inputs: dict, ctx: dict) -> dict:
    max_ms = inputs.get("max_ms", 500)
    actual_ms = ctx.get("_last_response_time_ms", 0)
    return {"passed": actual_ms <= max_ms, "max_ms": max_ms, "actual_ms": actual_ms}



def p17_llm_judge(inputs: dict, ctx: dict) -> dict:
    score_range_for_skip = inputs.get("score_range", [0, 5])
    if os.environ.get("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes"):
        return {"score": 0, "max_score": score_range_for_skip[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "SKIP_LLM_JUDGE=1 (LLM judge intentionally skipped for peer-review-grade scoring)"}
    try:
        from _llm_judge_safe import dispatch_external_evidence as _dee
        _ext_ctx = ctx
        _ext_result = _dee(
            inputs=inputs,
            ctx=_ext_ctx,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE or "",
            return_type='dict',
        )
        if _ext_result is not None:
            return _ext_result
    except Exception as _ext_exc:
        import logging as _ext_logging
        _ext_logging.getLogger("p17_dispatch").warning(
            "dispatch_external_evidence failed for evidence_type=%r: %s",
            inputs.get("evidence_type"), _ext_exc)
    rubric_prompt = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "code_files")

    if not LLM_API_KEY:
        return {"passed": True, "score": 0, "skipped": True, "llm_api_failure": False,
                "reason": "LLM_API_KEY unset"}

    evidence_text = ""
    if evidence_type == "code_files":
        ext_list = inputs.get("extensions")
        evidence_text = _collect_code_evidence(
            inputs.get("files_to_sample", []),
            max_files=int(inputs.get("max_files", 60)),
            per_file_chars=int(inputs.get("per_file_chars", 4000)),
            total_chars=int(inputs.get("total_chars", 70000)),
            extensions=tuple(f".{e.lstrip('.')}" for e in ext_list) if ext_list else None,
            rubric=rubric_prompt,
        )
    elif evidence_type == "http_response_html":
        evidence_text = str(ctx.get("_last_response_body", ""))[:20000]
    elif evidence_type == "http_response_body":
        full_log = ctx.get("_response_log", []) or []
        start = int(ctx.get("_node_resp_start", 0) or 0)
        log = full_log[start:] if start <= len(full_log) else full_log
        per_resp_cap = int(inputs.get("evidence_prompt_budget", 60000))
        errs, seen_k = [], set()
        for e in log:
            st = e.get("status", 0)
            if isinstance(st, int) and st >= 400:
                k = (st, e.get("path", ""))
                if k not in seen_k:
                    seen_k.add(k)
                    errs.append(e)
        chosen = errs if errs else log[-8:]
        if chosen:
            parts = []
            for i, e in enumerate(chosen[:12], 1):
                parts.append(
                    f"--- response {i}: {e.get('method','GET')} {e.get('path','')} "
                    f"-> {e.get('status','')} ({e.get('content_type','')}) ---\n"
                    + json.dumps(e.get("body", ""), indent=2, default=str)[:per_resp_cap])
            evidence_text = "\n\n".join(parts)
        else:
            evidence_text = str(ctx.get("_last_response_body", ""))[:per_resp_cap]

    if evidence_type in ("http_response_html", "http_response_body") and not evidence_text.strip():
        return {"passed": True, "score": 0, "skipped": True, "llm_api_failure": False,
                "reason": f"no {evidence_type} evidence captured"}

    evidence_budget = int(inputs.get("evidence_prompt_budget", 60000))
    from _llm_judge_safe import safe_chat_completion
    res = safe_chat_completion(
        messages=[
            {"role": "system", "content": (
                f"You are a strict code quality evaluator. Score from {score_range[0]} to {score_range[1]}. "
                "You have NO access to any tools, shell, or filesystem: evaluate SOLELY from the evidence "
                "provided below and do NOT ask to inspect more files. "
                "Respond with ONLY a JSON object with 'score' (number) and 'reasoning' (string) and no other text.")},
            {"role": "user", "content": f"## Rubric\n{rubric_prompt}\n\n## Evidence\n{evidence_text[:evidence_budget]}"},
        ],
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE,
        temperature=0.1,
        max_tokens=2000,
    )
    if res.skipped:
        return {"passed": True, "score": 0, "skipped": True,
                "llm_api_failure": res.llm_api_failure,
                "exception_class": res.exception_class,
                "reason": res.error or "skipped"}

    def _fence_strip(s: str) -> str:
        if s.startswith("```"):
            s = re.sub(r"^```(?:json|JSON)?\s*", "", s, count=1)
            s = re.sub(r"\s*```\s*$", "", s, count=1)
        return s.strip()

    def _extract(raw: str):
        raw = (raw or "").strip()
        if not raw:
            return None
        candidates = [_fence_strip(raw)]
        brace_match = re.search(r"\{[^{}]*\"score\"[^{}]*\}", raw, flags=re.DOTALL)
        if brace_match:
            candidates.append(brace_match.group(0))
        for cand in candidates:
            try:
                parsed = json.loads(cand)
            except Exception:
                continue
            score_val = parsed.get("score") if isinstance(parsed, dict) else None
            if isinstance(score_val, (int, float)):
                score = max(score_range[0], min(score_range[1], float(score_val)))
                return {"passed": True, "score": score,
                        "reasoning": (parsed.get("reasoning") if isinstance(parsed, dict) else "") or ""}
        m = re.search(r'"?score"?\s*[:=]\s*(-?\d+(?:\.\d+)?)', raw, flags=re.IGNORECASE)
        if m:
            score = max(score_range[0], min(score_range[1], float(m.group(1))))
            return {"passed": True, "score": score, "fallback_parse": "regex", "raw": raw[:200]}
        for pat in (
            r'(?:^|\n)\s*#*\s*(?:Overall\s+)?Score\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*#*\s*Evaluation\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*#*\s*Rating\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'\*\*\s*Score\s*[:\-]?\s*(-?\d+(?:\.\d+)?)',
            r'\bscore\s+(?:is|of|=)\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*\**\s*(-?\d+(?:\.\d+)?)\s*(?:/\s*\d+\s*)?(?:—|–|-)\s*(?:Excellent|Strong|Good|Complete|Weak|Poor|None|Fair|Adequate)',
        ):
            mm = re.search(pat, raw, flags=re.IGNORECASE)
            if mm:
                score = max(score_range[0], min(score_range[1], float(mm.group(1))))
                return {"passed": True, "score": score, "fallback_parse": "markdown", "raw": raw[:200]}
        for _ln in reversed(raw.splitlines()):
            _c = _ln.strip().strip("`").strip().rstrip(".").strip()
            if re.fullmatch(r'-?\d+(?:\.\d+)?', _c):
                score = max(score_range[0], min(score_range[1], float(_c)))
                return {"passed": True, "score": score, "fallback_parse": "bare_number", "raw": raw[:200]}
        _nums = re.findall(r'-?\d+(?:\.\d+)?', raw)
        if _nums:
            score = max(score_range[0], min(score_range[1], float(_nums[-1])))
            return {"passed": True, "score": score, "fallback_parse": "trailing_number", "raw": raw[:200]}
        return None

    parsed_result = _extract(res.raw)
    if parsed_result is not None:
        return parsed_result

    force_instr = (
        f"\n\nIMPORTANT: Respond with ONLY a single integer between {score_range[0]} and "
        f"{score_range[1]}. Output just the number — no prose, no explanation, no JSON, and do "
        "NOT offer to investigate or inspect files. The evidence above is all you get.")
    last_force = None
    for _attempt in range(3):
        force_res = safe_chat_completion(
            messages=[
                {"role": "system", "content": (
                    f"You are a strict code quality evaluator scoring from {score_range[0]} to {score_range[1]}. "
                    "You have NO access to any tools, shell, or filesystem. Evaluate SOLELY from the evidence. "
                    "Respond with ONLY a single integer score and nothing else.")},
                {"role": "user", "content": f"## Rubric\n{rubric_prompt}\n\n## Evidence\n{evidence_text[:evidence_budget]}{force_instr}"},
            ],
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            max_tokens=2000,
        )
        last_force = force_res
        if not force_res.skipped:
            forced = _extract(force_res.raw)
            if forced is not None:
                forced["fallback_parse"] = "forced_retry"
                return forced

    return {"passed": True, "score": 0, "skipped": True, "parse_failure": True,
            "llm_api_failure": bool(getattr(last_force, "llm_api_failure", False)),
            "error": "no parseable score in reply", "raw": (res.raw or "")[:200]}


_DEFAULT_EVIDENCE_EXTENSIONS = (
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".java", ".kt", ".rb", ".rs", ".cs", ".php", ".swift",
    ".vue", ".svelte", ".css", ".scss", ".less", ".sass",
    ".html", ".htm", ".yaml", ".yml", ".json", ".toml", ".sql",
    ".md", ".sh", ".dockerfile",
)


_CODE_EVIDENCE_EXTS = (
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".java", ".kt", ".rb", ".rs", ".cs", ".php", ".swift",
    ".vue", ".svelte", ".scala",
)
_STYLE_EVIDENCE_EXTS = (".css", ".scss", ".less", ".sass", ".html", ".htm")

_RUBRIC_STOPWORDS = {
    "score", "based", "does", "this", "that", "with", "from", "have", "they",
    "their", "which", "where", "when", "what", "evidence", "implementation",
    "rubric", "criteria", "criterion", "points", "point", "quality", "design",
    "system", "code", "should", "must", "uses", "used", "using", "provide",
    "provides", "following", "appropriate", "proper", "across", "between",
    "consistent", "consistently", "structured", "structure", "evaluate",
}


def _ext_priority(fn: str) -> int:
    low = fn.lower()
    if low.endswith(_CODE_EVIDENCE_EXTS):
        return 0
    if low.endswith(_STYLE_EVIDENCE_EXTS):
        return 1
    return 2


def _collect_code_evidence(paths: list, *, max_files: int = 60,
                            per_file_chars: int = 4000,
                            total_chars: int = 70000,
                            extensions: Optional[tuple] = None,
                            rubric: str = "") -> str:
    exts = tuple(extensions) if extensions else _DEFAULT_EVIDENCE_EXTENSIONS
    skip_dirs = {"node_modules", ".git", "vendor", "__pycache__", "dist",
                 "build", ".next", ".venv", "venv", ".pytest_cache", ".mypy_cache",
                 "target", "coverage", ".turbo", ".cache",
                 "docs", "storybook", ".storybook", "stories", "examples",
                 "cypress", "e2e", ".github", ".devcontainer", "scripts",
                 "tests", "test", "__tests__", "spec", "fixtures"}
    _rub_kw = set(w.lower() for w in re.findall(r"[A-Za-z]{4,}", str(rubric) or "")
                  if w.lower() not in _RUBRIC_STOPWORDS)

    if (
        paths
        and os.path.isdir(WORKSPACE_DIR)
        and not any(
            os.path.exists(os.path.join(WORKSPACE_DIR, p))
            or glob_mod.glob(os.path.join(WORKSPACE_DIR, p), recursive=True)
            for p in paths
        )
    ):
        paths = ["."]

    cands = []
    for p in paths:
        full = os.path.join(WORKSPACE_DIR, p)
        if os.path.isdir(full):
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for fn in files:
                    if exts and not fn.lower().endswith(exts):
                        continue
                    fp = os.path.join(root, fn)
                    cands.append((fp, os.path.relpath(fp, WORKSPACE_DIR)))
        elif os.path.isfile(full):
            cands.append((full, os.path.relpath(full, WORKSPACE_DIR)))
        else:
            for fp in glob_mod.glob(full, recursive=True):
                if not os.path.isfile(fp):
                    continue
                if exts and not fp.lower().endswith(exts):
                    continue
                cands.append((fp, os.path.relpath(fp, WORKSPACE_DIR)))

    def _file_rank(fp: str, rel: str):
        rl = rel.lower()
        bn = rl.rsplit("/", 1)[-1]
        noise = 1 if (bn == "__init__.py" or bn.startswith(".") or bn == "index.ts"
                      or bn == "index.js") else 0
        relevance = sum(1 for w in _rub_kw if w in rl)
        return (_ext_priority(fp), -relevance, noise, rl)

    from collections import defaultdict as _dd
    groups = _dd(list)
    root_files = []
    for fp, rel in cands:
        rel2 = rel.replace(os.sep, "/")
        rank = _file_rank(fp, rel2)
        if "/" not in rel2:
            root_files.append((rank, fp, rel))
        else:
            groups[rel2.split("/", 1)[0]].append((rank, fp, rel))
    for g in groups.values():
        g.sort()
    root_files.sort()

    def _codecnt(items):
        return sum(1 for (rk, _, _) in items if rk[0] == 0)
    ranked_dirs = sorted(groups.keys(), key=lambda t: (-_codecnt(groups[t]), t))
    primary = [t for t in ranked_dirs if _codecnt(groups[t]) > 0][:4]
    rest = [t for t in ranked_dirs if t not in primary]

    ordered = []

    def _drain(dirlist):
        while len(ordered) < max_files and any(groups[t] for t in dirlist):
            for t in dirlist:
                if groups[t]:
                    _, fp, rel = groups[t].pop(0)
                    ordered.append((fp, rel))
                    if len(ordered) >= max_files:
                        return
    _drain(primary)
    _drain(rest)
    for _, fp, rel in root_files:
        if len(ordered) >= max_files:
            break
        ordered.append((fp, rel))

    lines = []
    for fp, rel in ordered:
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                content = fh.read(per_file_chars)
        except Exception:
            content = "[binary or unreadable]"
        lines.append(f"--- {rel} ---")
        lines.append(content)
        if sum(len(s) for s in lines) >= total_chars:
            break
    return "\n".join(lines)[:total_chars]


PRIMITIVES = {
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
}

try:
    from _browser_primitives import (
        p18_render_dom as _shared_render_dom,
        p19_screenshot as _shared_screenshot,
    )
    for _bp_map_name in ("PRIMITIVE_MAP", "PRIMITIVES", "PRIMITIVE_DISPATCH"):
        _bp_map = globals().get(_bp_map_name)
        if isinstance(_bp_map, dict):
            _bp_map.setdefault("RENDER_DOM", _shared_render_dom)
            _bp_map.setdefault("SCREENSHOT", _shared_screenshot)
            break
except Exception as _bp_exc:
    import logging as _bp_log
    _bp_log.getLogger("_browser_primitives").warning(
        "RENDER_DOM/SCREENSHOT registration failed: %s", _bp_exc)
