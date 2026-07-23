import base64
import glob as glob_mod
import io
import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

import config
from config import (
    APP_BASE_URL,
    API_BASE_URL,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    APP_CONTAINER,
    DB_CONTAINER,
    HTTP_TIMEOUT,
    LLM_API_KEY,
    LLM_API_BASE,
    LLM_MODEL,
    WORKSPACE_DIR,
    TEST_USERS,
)
from utils import context, get_db_connection

logger = logging.getLogger(__name__)

_token_cache: dict[str, dict] = {}
_session_cookies: dict[str, dict] = {}


def _basic_auth_header(username: str, token: str) -> dict:
    cred = base64.b64encode(f"{username}:{token}".encode()).decode()
    return {"Authorization": f"Basic {cred}"}


def _get_auth_headers(role: str = "admin") -> dict:
    if role in _token_cache:
        info = _token_cache[role]
        return _basic_auth_header(info["username"], info["token"])
    return {}


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
        matched = pattern in content
    elif match_type == "regex":
        matched = bool(re.search(pattern, content))
    else:
        matched = False

    return {"passed": matched, "matched": matched}


def p03_file_count(inputs: dict, ctx: dict) -> dict:
    pattern = inputs.get("glob", "**/*")
    base_dir = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", ""))
    min_expected = inputs.get("min_expected", 1)
    files = glob_mod.glob(os.path.join(base_dir, pattern), recursive=True)
    files = [f for f in files if os.path.isfile(f)]
    count = len(files)
    passed = count >= min_expected
    return {"passed": passed, "count": count, "min_expected": min_expected}


def p04_http_request(inputs: dict, ctx: dict) -> dict:
    method = inputs.get("method", "GET").upper()
    path = inputs.get("path", "/")
    headers = dict(inputs.get("headers", {}))
    body = inputs.get("body")
    timeout = inputs.get("timeout", HTTP_TIMEOUT)

    cookies = None
    if path.startswith("/api/") or path.startswith("/webhooks/"):
        role = ctx.get("_current_role", "admin")
        cached = _token_cache.get(role, {})
        if cached.get("session"):
            cookies = _session_cookies.get(role, ctx.get("_admin_session_cookies"))
        else:
            auth_h = _get_auth_headers(role)
            for k, v in auth_h.items():
                headers.setdefault(k, v)

    url = APP_BASE_URL + path

    kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout, "allow_redirects": False}
    if cookies:
        kwargs["cookies"] = cookies

    if isinstance(body, str) and "=" in body and headers.get("Content-Type") == "application/x-www-form-urlencoded":
        kwargs["data"] = body
    elif isinstance(body, dict):
        if headers.get("Content-Type", "").startswith("multipart/form-data"):
            headers.pop("Content-Type", None)
            kwargs["headers"] = headers
            file_data = body.get("file")
            if file_data and isinstance(file_data, str) and not file_data.startswith("/"):
                import struct, zlib
                def _make_png():
                    width, height = 1, 1
                    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
                    raw = b'\x00' + b'\xff\x00\x00'
                    idat = zlib.compress(raw)
                    def _chunk(ctype, data):
                        c = ctype + data
                        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
                    return b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr) + _chunk(b'IDAT', idat) + _chunk(b'IEND', b'')
                img = io.BytesIO(_make_png())
                kwargs["files"] = {"file": ("test_image.png", img, "image/png")}
            params = body.get("params")
            if params:
                kwargs["data"] = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}
        else:
            kwargs["json"] = body
    elif isinstance(body, str):
        kwargs["data"] = body

    import time as _time
    last_err = None
    for attempt in range(3):
        if attempt > 0:
            _time.sleep(2)
            if "files" in kwargs and hasattr(kwargs["files"].get("file", (None,None,None))[1], "seek"):
                kwargs["files"]["file"][1].seek(0)
        try:
            resp = requests.request(method, url, **kwargs)
            resp_body = None
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                try:
                    resp_body = resp.json()
                except Exception:
                    resp_body = resp.text
            else:
                resp_body = resp.text

            return {
                "passed": True,
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp_body,
                "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
                "cookies": dict(resp.cookies),
                "_response": resp,
            }
        except (requests.exceptions.ConnectionError, ConnectionResetError) as e:
            last_err = e
            logger.warning("P04 retry %d: %s %s -> %s", attempt + 1, method, url, e)
            continue
        except Exception as e:
            logger.error("P04 failed: %s %s -> %s", method, url, e)
            return {"passed": False, "status_code": 0, "headers": {}, "body": None, "error": str(e)}

    logger.error("P04 failed after retries: %s %s -> %s", method, url, last_err)
    return {"passed": False, "status_code": 0, "headers": {}, "body": None, "error": str(last_err)}


def p05_api_crud(inputs: dict, ctx: dict) -> dict:
    resource = inputs.get("resource", "")
    create_body = inputs.get("create_body", {})
    update_body = inputs.get("update_body", {})
    expected_create_status = inputs.get("expected_create_status", 200)
    expected_read_fields = inputs.get("expected_read_fields", [])
    expected_update_status = inputs.get("expected_update_status", 200)
    expected_delete_status = inputs.get("expected_delete_status", 200)

    steps_passed = 0
    steps_total = 4
    entity_id = None
    evidence = {}

    create_r = p04_http_request({"method": "POST", "path": resource, "body": create_body}, ctx)
    if create_r.get("status_code") == expected_create_status:
        steps_passed += 1
        body = create_r.get("body", {})
        if isinstance(body, dict):
            data = body.get("data", body)
            entity_id = data.get("id")
            evidence["create"] = {"id": entity_id}
    else:
        evidence["create_error"] = {"status": create_r.get("status_code"), "body": str(create_r.get("body", ""))[:500]}

    if entity_id is not None:
        read_r = p04_http_request({"method": "GET", "path": f"{resource}/{entity_id}"}, ctx)
        if read_r.get("status_code") == 200:
            body = read_r.get("body", {})
            data = body.get("data", body) if isinstance(body, dict) else {}
            if isinstance(data, dict):
                found = [f for f in expected_read_fields if f in data]
                if len(found) >= len(expected_read_fields) * 0.7:
                    steps_passed += 1
        evidence["read_status"] = read_r.get("status_code")

        update_r = p04_http_request({"method": "PUT", "path": f"{resource}/{entity_id}", "body": update_body}, ctx)
        if update_r.get("status_code") == expected_update_status:
            steps_passed += 1
        evidence["update_status"] = update_r.get("status_code")

        delete_r = p04_http_request({"method": "DELETE", "path": f"{resource}/{entity_id}"}, ctx)
        if delete_r.get("status_code") == expected_delete_status:
            steps_passed += 1
        evidence["delete_status"] = delete_r.get("status_code")
    else:
        evidence["skipped"] = "create failed, no entity_id"

    return {
        "passed": steps_passed == steps_total,
        "steps_passed": steps_passed,
        "steps_total": steps_total,
        "entity_id": entity_id,
        "evidence": evidence,
    }


def p06_json_schema_match(inputs: dict, ctx: dict) -> dict:
    response = inputs.get("response")
    if response is None:
        response = ctx.get("_last_response_body", {})
    required_fields = inputs.get("required_fields", [])

    if isinstance(response, dict):
        data = response
    else:
        return {"passed": False, "all_present": False, "missing_fields": required_fields}

    def _resolve(obj, parts):
        for p in parts:
            if isinstance(obj, dict) and p in obj:
                obj = obj[p]
            else:
                return False, None
        return True, obj

    candidates = [data]
    if isinstance(data, dict):
        if isinstance(data.get("data"), dict):
            candidates.append(data["data"])

    def _try_field(root, field_path):
        if isinstance(root, dict) and field_path in root:
            return True
        parts = field_path.split(".")
        ok, _ = _resolve(root, parts)
        if ok:
            return True
        if parts and parts[0] == "data":
            ok, _ = _resolve(root, parts[1:])
            if ok:
                return True
        return False

    best_missing = None
    for root in candidates:
        miss = [fp for fp in required_fields if not _try_field(root, fp)]
        if best_missing is None or len(miss) < len(best_missing):
            best_missing = miss
        if not miss:
            break

    missing = best_missing or []
    all_present = len(missing) == 0
    return {
        "passed": all_present,
        "all_present": all_present,
        "missing_fields": missing,
        "found_count": len(required_fields) - len(missing),
        "total_count": len(required_fields),
    }


def p07_json_value_assert(inputs: dict, ctx: dict) -> dict:
    assertions = inputs.get("assertions", [])
    response_body = ctx.get("_last_response_body")

    results = []
    for a in assertions:
        path = a.get("path", "")
        expected = a.get("expected")
        tolerance = a.get("tolerance", 0)

        actual = _resolve_json_path(response_body, path, ctx)

        if expected == "not_empty":
            passed = actual is not None and actual != "" and actual != [] and actual != {}
        elif expected == "array":
            passed = isinstance(actual, list)
        elif isinstance(expected, str) and expected.startswith(">="):
            try:
                threshold = int(expected[2:])
                passed = isinstance(actual, (int, float)) and actual >= threshold
            except (ValueError, TypeError):
                passed = False
        elif isinstance(expected, str) and expected.startswith("contains:"):
            needle = expected[len("contains:"):]
            passed = isinstance(actual, str) and needle in actual
        elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            passed = abs(actual - expected) <= tolerance
        elif isinstance(expected, list):
            passed = actual == expected
        elif isinstance(expected, bool):
            passed = actual is expected
        else:
            passed = str(actual) == str(expected) if actual is not None else False

        results.append({"path": path, "expected": expected, "actual": actual, "passed": passed})

    all_passed = all(r["passed"] for r in results)
    return {"passed": all_passed, "all_passed": all_passed, "results": results}


def _resolve_json_path(data: Any, path: str, ctx: dict) -> Any:
    if path.startswith("$._headers."):
        key = path[len("$._headers."):]
        headers = ctx.get("_last_response_headers", {})
        for h_key, h_val in headers.items():
            if h_key.lower() == key.lower():
                return h_val
        return None
    if path == "$._body_first_line":
        raw = ctx.get("_last_response_raw", "")
        if isinstance(raw, str) and raw:
            return raw.split("\n")[0]
        return None

    if not path.startswith("$."):
        path = "$." + path

    parts = path[2:].split(".")
    obj = data
    for part in parts:
        if obj is None:
            return None
        bracket = re.match(r"(.+)\[(\d+)\]$", part)
        if bracket:
            key, idx = bracket.group(1), int(bracket.group(2))
            obj = obj.get(key) if isinstance(obj, dict) else None
            obj = obj[idx] if isinstance(obj, list) and 0 <= idx < len(obj) else None
        elif part.startswith("[?(@."):
            pass
        else:
            if isinstance(obj, dict):
                obj = obj.get(part)
            elif isinstance(obj, list) and part == "length":
                return len(obj)
            else:
                return None
    return obj


def p08_db_query(inputs: dict, ctx: dict) -> dict:
    sql = inputs.get("sql", "")
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, ctx)
    except Exception:
        pass
    params = inputs.get("params")
    expected_result = inputs.get("expected_result")

    if params is None:
        for key, val in ctx.items():
            if isinstance(val, (int, str)):
                sql = sql.replace("{{" + key + "}}", str(val))

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            sql_upper = sql.strip().upper()
            if sql_upper.startswith(("INSERT", "UPDATE", "DELETE", "REFRESH", "CREATE", "ALTER", "DROP", "TRUNCATE")):
                conn.commit()
                if "RETURNING" in sql.upper():
                    rows = [dict(r) for r in cur.fetchall()]
                else:
                    rows = [{"affected": cur.rowcount}]
            else:
                rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        logger.error("P08 db_query failed: %s -- %s", sql[:200], e)
        return {"passed": False, "rows": [], "row_count": 0, "match": False, "error": str(e)}

    if expected_result is None or expected_result == {}:
        return {"passed": True, "rows": rows, "row_count": len(rows), "match": True}

    if len(rows) == 0:
        return {"passed": False, "rows": rows, "row_count": 0, "match": False}

    row = rows[0]
    match = True
    for k, v in expected_result.items():
        actual = row.get(k)
        if isinstance(v, dict):
            for op, threshold in v.items():
                if op == "$gte":
                    match = match and (isinstance(actual, (int, float)) and actual >= threshold)
                elif op == "$gt":
                    match = match and (isinstance(actual, (int, float)) and actual > threshold)
                elif op == "$lte":
                    match = match and (isinstance(actual, (int, float)) and actual <= threshold)
                elif op == "$lt":
                    match = match and (isinstance(actual, (int, float)) and actual < threshold)
                elif op == "$ne":
                    match = match and (actual != threshold)
                elif op == "$in":
                    match = match and (actual in threshold)
        elif isinstance(v, (int, float)) and isinstance(actual, (int, float)):
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
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            existing_tables = {r["tablename"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return {"passed": False, "existing": [], "missing": tables, "found_count": 0, "total_count": len(tables), "error": str(e)}

    found = [t for t in tables if t in existing_tables]
    missing = [t for t in tables if t not in existing_tables]

    return {
        "passed": len(missing) == 0,
        "existing": found,
        "missing": missing,
        "found_count": len(found),
        "total_count": len(tables),
    }


def p10_db_column_check(inputs: dict, ctx: dict) -> dict:
    table = inputs.get("table", "")
    expected_columns = inputs.get("expected_columns", [])
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            )
            actual_cols = {r["column_name"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return {"passed": False, "existing": [], "missing": expected_columns, "found_count": 0, "total_count": len(expected_columns), "error": str(e)}

    found = [c for c in expected_columns if c in actual_cols]
    missing = [c for c in expected_columns if c not in actual_cols]

    return {
        "passed": len(missing) == 0,
        "existing": found,
        "missing": missing,
        "found_count": len(found),
        "total_count": len(expected_columns),
    }


def p11_db_index_check(inputs: dict, ctx: dict) -> dict:
    table = inputs.get("table", "")
    expected_indexes = inputs.get("expected_indexes", [])
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT indexname, string_agg(a.attname, ',' ORDER BY array_position(i.indkey, a.attnum)) AS columns
                   FROM pg_indexes pi
                   JOIN pg_class c ON c.relname = pi.indexname
                   JOIN pg_index i ON i.indexrelid = c.oid
                   JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                   WHERE pi.tablename = %s AND pi.schemaname = 'public'
                   GROUP BY indexname""",
                (table,),
            )
            rows = cur.fetchall()
        conn.close()
        existing_idx_cols = [set(r["columns"].split(",")) for r in rows]
    except Exception as e:
        return {"passed": False, "error": str(e)}

    found = 0
    for ei in expected_indexes:
        exp_cols = set(ei.get("columns", []))
        if any(exp_cols <= s for s in existing_idx_cols):
            found += 1

    return {"passed": found == len(expected_indexes), "found": found, "total": len(expected_indexes)}


def p12_docker_exec(inputs: dict, ctx: dict) -> dict:
    command = inputs.get("command", "")
    container = inputs.get("container", APP_CONTAINER)
    expect_success = inputs.get("expect_success", True)

    try:
        result = subprocess.run(
            ["docker", "exec", container, "sh", "-c", command],
            capture_output=True, text=True, timeout=30,
        )
        passed = (result.returncode == 0) == expect_success
        return {"passed": passed, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"passed": False, "error": str(e)}


def p13_auth_login(inputs: dict, ctx: dict) -> dict:
    role = inputs.get("role", "admin")
    method = inputs.get("method", "basic_auth")

    if role in _token_cache:
        info = _token_cache[role]
        if not (method == "basic_auth" and info.get("session")):
            ctx["_current_role"] = role
            ctx["auth_token"] = info["token"]
            ctx["auth_username"] = info["username"]
            return {"passed": True, "role": role, "method": "cached"}

    if method == "basic_auth" and role == "admin":
        api_cfg = TEST_USERS.get("api_admin", {})
        api_username = api_cfg.get("username", "evalapiuser")
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM users WHERE username = %s AND type = 'api'", (api_username,))
                row = cur.fetchone()
            conn.close()
            if row:
                token = row["password"]
                _token_cache["admin"] = {"username": api_username, "token": token}
                ctx["_current_role"] = "admin"
                ctx["auth_token"] = token
                ctx["auth_username"] = api_username
                return {"passed": True, "role": "admin", "method": "basic_auth_from_db"}
        except Exception as e:
            logger.warning("Basic auth DB lookup failed: %s", e)

    if method == "form" or role == "admin":
        return _auth_admin(inputs, ctx, role)
    else:
        return _auth_api_role(inputs, ctx, role)


def _auth_admin(inputs: dict, ctx: dict, role: str) -> dict:
    admin_cfg = TEST_USERS["admin"]
    username = admin_cfg["username"]
    password = admin_cfg["password"]

    login_path = inputs.get("login_path", "/admin/login")
    url = APP_BASE_URL + login_path

    try:
        resp = requests.post(
            url,
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=HTTP_TIMEOUT,
            allow_redirects=False,
        )
        if resp.status_code in (200, 302, 303):
            cookies = dict(resp.cookies)
            _session_cookies["admin"] = cookies
            ctx["_admin_session_cookies"] = cookies

            api_cfg = TEST_USERS.get("api_admin", {})
            api_username = api_cfg.get("username", "evalapiuser")

            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    cur.execute("SELECT password FROM users WHERE username = %s AND type = 'api'", (api_username,))
                    row = cur.fetchone()
                conn.close()

                if row:
                    token = row["password"]
                    _token_cache["admin"] = {"username": api_username, "token": token}
                    ctx["_current_role"] = "admin"
                    ctx["auth_token"] = token
                    ctx["auth_username"] = api_username
                    return {"passed": True, "role": "admin", "method": "basic_auth_from_db"}
            except Exception as e:
                logger.warning("Failed to get API token from DB: %s", e)

            _token_cache["admin"] = {"username": username, "token": password, "session": True}
            ctx["_current_role"] = "admin"
            ctx["_admin_cookies"] = cookies
            ctx["_session_cookies"] = cookies
            return {"passed": True, "role": "admin", "method": "session"}

        return {"passed": False, "error": f"Login failed with status {resp.status_code}"}
    except Exception as e:
        return {"passed": False, "error": str(e)}


def _auth_api_role(inputs: dict, ctx: dict, role: str) -> dict:
    role_cfg = TEST_USERS.get(role, {})
    username = role_cfg.get("username", role)

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT password FROM users WHERE username = %s AND type = 'api'", (username,))
            row = cur.fetchone()
        conn.close()

        if row:
            token = row["password"]
            _token_cache[role] = {"username": username, "token": token}
            ctx["_current_role"] = role
            ctx["auth_token"] = token
            ctx["auth_username"] = username
            return {"passed": True, "role": role, "method": "basic_auth_from_db"}
    except Exception as e:
        logger.error("P13 DB lookup for role=%s failed: %s", role, e)

    return {"passed": False, "error": f"Could not authenticate role={role}"}


def p14_permission_check(inputs: dict, ctx: dict) -> dict:
    action = inputs.get("action", "")
    expected_result = inputs.get("expected_result", "denied")
    acceptable = inputs.get("acceptable_statuses", inputs.get("expected_status"))
    body = inputs.get("body")

    parts = action.split(" ", 1)
    method = parts[0] if len(parts) > 0 else "GET"
    path = parts[1] if len(parts) > 1 else "/"

    req_inputs: dict[str, Any] = {"method": method, "path": path}
    if body:
        req_inputs["body"] = body

    result = p04_http_request(req_inputs, ctx)
    status = result.get("status_code", 0)

    if expected_result == "denied":
        if isinstance(acceptable, list):
            passed = status in acceptable
        elif isinstance(acceptable, int):
            passed = status == acceptable
        else:
            passed = status in (403, 404)
    else:
        passed = 200 <= status < 300

    return {"passed": passed, "status_code": status, "expected": expected_result}


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

    try:
        actual_i = int(actual)
    except (TypeError, ValueError):
        actual_i = 0

    if accepted:
        passed = actual_i in accepted
    else:
        passed = 200 <= actual_i < 300

    return {"passed": passed, "expected": expected or acceptable, "actual": actual_i,
            "status_code": actual_i, "body": ctx.get("_last_response_body", "")[:500] if isinstance(ctx.get("_last_response_body"), str) else None}


def p16_response_time_check(inputs: dict, ctx: dict) -> dict:
    max_ms = inputs.get("max_ms", 500)
    actual_ms = ctx.get("_last_response_time_ms", 0)
    passed = actual_ms <= max_ms
    return {"passed": passed, "max_ms": max_ms, "actual_ms": actual_ms}


def p17_llm_judge(inputs: dict, ctx: dict) -> dict:
    score_range_for_skip = inputs.get("score_range", [0, 5])
    if getattr(config, "SKIP_LLM_JUDGE", False):
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
    score_range = inputs.get("score_range", [0, 10])
    evidence_type = inputs.get("evidence_type", "code_files")

    if not LLM_API_KEY:
        return {"passed": True, "score": 0, "skipped": True, "llm_api_failure": False,
                "reason": "LLM_API_KEY unset"}

    evidence_text = ""
    if evidence_type == "code_files":
        evidence_text = _collect_code_evidence(
            inputs.get("files_to_sample", []),
            rubric_prompt=rubric_prompt,
        )
    elif evidence_type == "http_response_html":
        evidence_text = str(ctx.get("_last_response_body", ""))[:5000]

    _prompt_cap = int(inputs.get("max_evidence_chars", 30000))
    from _llm_judge_safe import safe_chat_completion
    res = safe_chat_completion(
        messages=[
            {"role": "system", "content": (
                f"You are a strict code quality evaluator. Score from {score_range[0]} to {score_range[1]}. "
                "You have NO access to any tools, shell, or filesystem: evaluate SOLELY from the evidence "
                "provided below and do NOT ask to inspect more files. "
                "Respond with ONLY a JSON object with 'score' (number) and 'reasoning' (string) and no other text.")},
            {"role": "user", "content": f"## Rubric\n{rubric_prompt}\n\n## Evidence\n{evidence_text[:_prompt_cap]}"},
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

    parsed = _pkvwdnhj_parse_judge(res.raw)
    if parsed is not None:
        score = max(score_range[0], min(score_range[1], parsed.get("score", 0)))
        return {"passed": True, "score": score, "reasoning": parsed.get("reasoning", "")}

    import re as _re2
    _force_instr = (
        f"\n\nIMPORTANT: Respond with ONLY a single integer between {score_range[0]} and "
        f"{score_range[1]}. Output just the number — no prose, no explanation, no JSON, and do "
        "NOT offer to investigate or inspect files. The evidence above is all you get.")
    _last_force = None
    for _attempt in range(3):
        force_res = safe_chat_completion(
            messages=[
                {"role": "system", "content": (
                    f"You are a strict code quality evaluator scoring from {score_range[0]} to {score_range[1]}. "
                    "You have NO access to any tools, shell, or filesystem. Evaluate SOLELY from the evidence. "
                    "Respond with ONLY a single integer score and nothing else.")},
                {"role": "user", "content": f"## Rubric\n{rubric_prompt}\n\n## Evidence\n{evidence_text[:_prompt_cap]}{_force_instr}"},
            ],
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            max_tokens=2000,
        )
        _last_force = force_res
        if not force_res.skipped:
            _fnums = _re2.findall(r'-?\d+(?:\.\d+)?', (force_res.raw or "").strip())
            if _fnums:
                score = max(score_range[0], min(score_range[1], float(_fnums[-1])))
                return {"passed": True, "score": score, "reasoning": (force_res.raw or "")[:500],
                        "fallback_parse": "forced_retry"}
    return {"passed": True, "score": 0, "skipped": True, "parse_failure": True,
            "llm_api_failure": bool(getattr(_last_force, "llm_api_failure", False)),
            "error": "could not extract score from LLM output",
            "raw": (res.raw or "")[:200]}


def _pkvwdnhj_parse_judge(raw):
    if not raw:
        return None
    import re as _re
    s = str(raw).strip()
    fence = _re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", s, _re.DOTALL | _re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    try:
        d = json.loads(s)
        if isinstance(d, dict) and "score" in d:
            return {"score": float(d.get("score", 0)),
                    "reasoning": str(d.get("reasoning") or d.get("explanation") or "")}
    except Exception:
        pass
    m = _re.search(r"\{[\s\S]*?\}", s)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and "score" in d:
                return {"score": float(d.get("score", 0)),
                        "reasoning": str(d.get("reasoning") or d.get("explanation") or "")}
        except Exception:
            pass
    m = _re.search(r'(?:^|\W)["\']?score["\']?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)', s, _re.IGNORECASE)
    if m:
        try:
            return {"score": float(m.group(1)), "reasoning": s[:500]}
        except Exception:
            pass
    for pat in (
        r'(?:^|\n)\s*#*\s*(?:Overall\s+)?Score\s*[:\-]?\s*\**\s*([0-9]+(?:\.[0-9]+)?)',
        r'(?:^|\n)\s*#*\s*Evaluation\s*[:\-]?\s*\**\s*([0-9]+(?:\.[0-9]+)?)',
        r'(?:^|\n)\s*#*\s*Rating\s*[:\-]?\s*\**\s*([0-9]+(?:\.[0-9]+)?)',
        r'\*\*\s*Score\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)',
        r'\bscore\s+(?:is|of|=)\s*\**\s*([0-9]+(?:\.[0-9]+)?)',
        r'(?:^|\n)\s*\**\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*[0-9]+\s*)?(?:—|–|-)\s*(?:Excellent|Strong|Good|Complete|Weak|Poor|None|Fair|Adequate)',
    ):
        mm = _re.search(pat, s, _re.IGNORECASE)
        if mm:
            try:
                return {"score": float(mm.group(1)), "reasoning": s[:500]}
            except Exception:
                pass
    for _ln in reversed(s.splitlines()):
        _c = _ln.strip().strip("`").strip().rstrip(".").strip()
        if _re.fullmatch(r'-?\d+(?:\.\d+)?', _c):
            return {"score": float(_c), "reasoning": s[:500]}
    _nums = _re.findall(r'-?\d+(?:\.\d+)?', s)
    if _nums:
        try:
            return {"score": float(_nums[-1]), "reasoning": s[:500]}
        except Exception:
            pass
    return None


_EVIDENCE_SKIP_DIRS = frozenset({
    "node_modules", "vendor", "__pycache__", "dist", "build", "target",
    "coverage", "cypress", "docs", "doc", "i18n", "locales", "static",
    "public", "assets", "fontello", "tmp", "logs", "log", ".pytest_cache",
    ".mypy_cache", ".tox", ".venv", "venv", "env", ".cache",
})

_EVIDENCE_CODE_EXTENSIONS = (
    ".go", ".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".sql",
    ".rb", ".java", ".kt", ".rs", ".cs", ".php", ".scala", ".swift",
    ".sh", ".toml", ".yaml", ".yml",
)

_EVIDENCE_PRIORITY_DIR_PREFIXES = (
    "cmd/", "internal/", "models/", "queries/",
    "handlers/", "handler/", "routes/", "route/", "controllers/", "controller/",
    "src/", "app/", "lib/", "pkg/", "api/", "services/", "service/",
    "core/", "domain/", "modules/", "module/",
)


def _is_priority_path(rel_path: str) -> bool:
    norm = rel_path.replace(os.sep, "/")
    return any(norm.startswith(pref) or ("/" + pref) in norm
               for pref in _EVIDENCE_PRIORITY_DIR_PREFIXES)


_EVIDENCE_RUBRIC_VOCAB = (
    "bounce", "subscriber", "subscribers", "subscription",
    "campaign", "campaigns", "list", "lists", "role", "roles", "permission",
    "settings", "setting", "template", "templates", "tx", "auth",
    "user", "users", "admin", "media", "import", "export", "archive",
    "webhook", "webhooks", "smtp", "event", "events", "notif", "notification",
    "rbac", "mail", "mailing", "messenger", "captcha", "bounce_handling",
    "rate_limit", "throttle", "queue", "worker", "manager", "scheduler",
    "blocklist", "blacklist", "opt_in", "opt-in", "double_opt_in",
    "render", "rendering", "html", "transactional",
)


def _extract_rubric_keywords(rubric_prompt: str) -> list:
    if not rubric_prompt:
        return []
    text = rubric_prompt.lower()
    seen: set[str] = set()
    out: list[str] = []
    for kw in _EVIDENCE_RUBRIC_VOCAB:
        if kw in seen:
            continue
        if kw in text:
            seen.add(kw)
            out.append(kw)
    return out


_EVIDENCE_WORD_BOUNDARY_RE_CACHE: dict = {}


def _file_matches_keywords(rel_path: str, keywords: list) -> bool:
    if not keywords:
        return False
    lp = rel_path.lower().replace(os.sep, "/")
    import re as _re
    for kw in keywords:
        pat = _EVIDENCE_WORD_BOUNDARY_RE_CACHE.get(kw)
        if pat is None:
            esc = _re.escape(kw)
            pat = _re.compile(r"(?:^|[^a-z0-9])" + esc + r"(?:[^a-z0-9]|$)")
            _EVIDENCE_WORD_BOUNDARY_RE_CACHE[kw] = pat
        if pat.search(lp):
            return True
    return False


def _collect_code_evidence(paths: list, rubric_prompt: str = "") -> str:
    lines: list[str] = []
    total_chars = 0
    budget = 28000
    per_file_rubric = 6000
    per_file_priority = 3500
    per_file_code = 2500
    per_file_other = 1200

    def _emit(label: str, content: str) -> bool:
        nonlocal total_chars
        block = f"--- {label} ---\n{content}"
        if total_chars + len(block) > budget:
            return False
        lines.append(block)
        total_chars += len(block) + 1
        return True

    keywords = _extract_rubric_keywords(rubric_prompt)

    seen: set[str] = set()
    rubric_files: list[str] = []
    priority_files: list[str] = []
    code_files: list[str] = []
    other_files: list[str] = []

    def _classify(fp: str) -> None:
        if fp in seen:
            return
        seen.add(fp)
        rel = os.path.relpath(fp, WORKSPACE_DIR)
        is_code = fp.endswith(_EVIDENCE_CODE_EXTENSIONS)
        if is_code and _file_matches_keywords(rel, keywords):
            rubric_files.append(fp)
        elif is_code and _is_priority_path(rel):
            priority_files.append(fp)
        elif is_code:
            code_files.append(fp)
        else:
            other_files.append(fp)

    for p in paths:
        full = os.path.join(WORKSPACE_DIR, p)
        if os.path.isfile(full):
            _classify(full)
            continue
        if not os.path.isdir(full):
            continue
        for root, dirs, files in os.walk(full):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _EVIDENCE_SKIP_DIRS]
            dirs.sort()
            for fn in sorted(files):
                if fn.startswith("."):
                    continue
                _classify(os.path.join(root, fn))

    def _read_chunk(fp: str, n: int) -> str:
        try:
            with open(fp, errors="replace") as fh:
                return fh.read(n)
        except Exception:
            return "[binary or unreadable]"

    for fp in rubric_files:
        rel = os.path.relpath(fp, WORKSPACE_DIR)
        if not _emit(rel, _read_chunk(fp, per_file_rubric)):
            break

    if total_chars < budget:
        for fp in priority_files:
            rel = os.path.relpath(fp, WORKSPACE_DIR)
            if not _emit(rel, _read_chunk(fp, per_file_priority)):
                break

    if total_chars < budget:
        for fp in code_files:
            rel = os.path.relpath(fp, WORKSPACE_DIR)
            if not _emit(rel, _read_chunk(fp, per_file_code)):
                break

    if total_chars < budget:
        for fp in other_files:
            rel = os.path.relpath(fp, WORKSPACE_DIR)
            if not _emit(rel, _read_chunk(fp, per_file_other)):
                break

    return "\n".join(lines)[:budget]


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
