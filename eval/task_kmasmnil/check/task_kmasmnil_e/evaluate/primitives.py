import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from typing import Any

import psycopg2
import requests

from config import (
    WORKSPACE_DIR, APP_BASE_URL, API_BASE_URL,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    APP_CONTAINER, HTTP_TIMEOUT, LLM_API_KEY, LLM_API_BASE, LLM_MODEL,
    TEST_USERS, CRON_SECRET,
    EVAL_API_KEY, EVAL_ORG_ID, EVAL_PROJECT_ID, EVAL_ENV_PROD, EVAL_ENV_DEV, EVAL_ADMIN_EMAIL,
)
from utils import PrimitiveResult, context, resolve_placeholders


def _get_db_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD
    )


def p01_file_exists(inputs: dict) -> PrimitiveResult:
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    file_type = inputs.get("type", "file")
    if file_type == "directory":
        exists = os.path.isdir(path)
    else:
        exists = os.path.isfile(path)
    return PrimitiveResult(passed=exists, data={"exists": exists}, message=f"{'Found' if exists else 'Missing'}: {inputs['path']}")


def p02_file_content_match(inputs: dict) -> PrimitiveResult:
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    if not os.path.isfile(path):
        return PrimitiveResult(passed=False, message=f"File not found: {inputs['path']}")
    try:
        with open(path, "r", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))

    match_type = inputs.get("match_type", "contains")
    pattern = inputs["pattern"]

    if match_type == "contains":
        matched = pattern in content
        count = content.count(pattern)
    elif match_type == "regex":
        matches = re.findall(pattern, content)
        matched = len(matches) > 0
        count = len(matches)
    else:
        matched = False
        count = 0

    return PrimitiveResult(passed=matched, data={"matched": matched, "match_count": count})


def p03_file_count(inputs: dict) -> PrimitiveResult:
    base = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", ""))
    pattern = inputs["glob"]
    files = glob.glob(os.path.join(base, pattern), recursive=True)
    count = len(files)
    min_expected = inputs.get("min_expected", 1)
    return PrimitiveResult(
        passed=count >= min_expected,
        data={"count": count, "files": [os.path.basename(f) for f in files[:20]]},
    )


def p04_http_request(inputs: dict) -> PrimitiveResult:
    method = inputs.get("method", "GET").upper()
    path = resolve_placeholders(inputs["path"], context)
    headers = resolve_placeholders(inputs.get("headers", {}), context)
    body = resolve_placeholders(inputs.get("body"), context)
    timeout = inputs.get("timeout", HTTP_TIMEOUT)

    cookies = {}
    if "session_cookies" in context and "x-api-key" not in headers:
        cookies = context["session_cookies"]
    if "auth_token" in context and "x-api-key" not in headers and "Authorization" not in headers:
        token = context["auth_token"]
        if token.startswith("fbk_") or token.startswith("xmk_"):
            headers.setdefault("x-api-key", token)
        elif "session_cookies" not in context:
            headers.setdefault("Authorization", f"Bearer {token}")

    url = APP_BASE_URL + path
    try:
        start = time.time()
        kw = {"headers": headers, "timeout": timeout, "allow_redirects": False, "cookies": cookies}
        if method == "GET":
            resp = requests.get(url, **kw)
        elif method == "POST":
            resp = requests.post(url, json=body, **kw)
        elif method == "PUT":
            resp = requests.put(url, json=body, **kw)
        elif method == "PATCH":
            resp = requests.patch(url, json=body, **kw)
        elif method == "DELETE":
            resp = requests.delete(url, **kw)
        else:
            return PrimitiveResult(passed=False, message=f"Unknown method: {method}")
        elapsed = (time.time() - start) * 1000

        try:
            resp_body = resp.json()
        except Exception:
            resp_body = {"_raw_text": resp.text[:2000], "_is_html": "<html" in resp.text[:100].lower()}

        result_data = {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp_body,
            "response_time_ms": elapsed,
        }
        context["_last_response"] = result_data
        if "_response_history" not in context:
            context["_response_history"] = []
        context["_response_history"].append(result_data)
        if len(context["_response_history"]) >= 2:
            codes = [r["status_code"] for r in context["_response_history"][-2:]]
            context["_status_codes_match"] = codes[0] == codes[1]
        
        if isinstance(resp_body, dict) and resp.status_code in (200, 201):
            data_obj = resp_body.get("data", resp_body)
            if isinstance(data_obj, dict) and "id" in data_obj:
                entity_id = data_obj["id"]
                context["_last_created_id"] = entity_id
                
                custom_key = inputs.get("_store_id_as")
                if custom_key:
                    context[custom_key] = entity_id
                
                p = path.lower()
                if "survey" in p and "response" not in p:
                    if not custom_key:
                        context["survey_id"] = entity_id
                    context["new_survey_id"] = entity_id
                elif "response" in p:
                    context["response_id"] = entity_id
                elif "contact" in p and "attribute" not in p:
                    context["contact_id"] = entity_id
                elif "webhook" in p:
                    context["webhook_id"] = entity_id
                elif "team" in p and "project" not in p:
                    context["team_id"] = entity_id
                elif "action" in p:
                    context["action_class_id"] = entity_id

        return PrimitiveResult(passed=True, data=result_data)
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p05_api_crud(inputs: dict) -> PrimitiveResult:
    resource = resolve_placeholders(inputs["resource"], context)
    token = resolve_placeholders(inputs.get("token", context.get("auth_token", "")), context)
    headers = {"x-api-key": token} if token else {}
    create_body = resolve_placeholders(inputs.get("create_body", {}), context)
    update_body = resolve_placeholders(inputs.get("update_body", {}), context)

    steps_passed = 0
    steps_total = 4
    evidence = {}

    try:
        resp = requests.post(APP_BASE_URL + resource, json=create_body, headers=headers, timeout=HTTP_TIMEOUT)
        expected_create = inputs.get("expected_create_status", 200)
        if resp.status_code in ([expected_create] if isinstance(expected_create, int) else expected_create):
            steps_passed += 1
            try:
                body = resp.json()
                entity_id = body.get("data", {}).get("id") or body.get("id")
                evidence["create"] = {"success": True, "id": entity_id, "response": body}
            except Exception:
                entity_id = None
                evidence["create"] = {"success": True}
        else:
            evidence["create"] = {"success": False, "status": resp.status_code}

        if not entity_id:
            return PrimitiveResult(passed=False, data={"steps_passed": steps_passed, "steps_total": steps_total}, evidence=evidence)

        resp = requests.get(APP_BASE_URL + f"{resource}/{entity_id}", headers=headers, timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            steps_passed += 1
            evidence["read"] = {"success": True, "response": resp.json()}
        else:
            evidence["read"] = {"success": False, "status": resp.status_code}

        resp = requests.put(APP_BASE_URL + f"{resource}/{entity_id}", json=update_body, headers=headers, timeout=HTTP_TIMEOUT)
        expected_update = inputs.get("expected_update_status", 200)
        if resp.status_code == expected_update:
            steps_passed += 1
            evidence["update"] = {"success": True, "response": resp.json() if resp.text else {}}
        else:
            evidence["update"] = {"success": False, "status": resp.status_code}

        resp = requests.delete(APP_BASE_URL + f"{resource}/{entity_id}", headers=headers, timeout=HTTP_TIMEOUT)
        expected_delete = inputs.get("expected_delete_status", 200)
        if resp.status_code == expected_delete:
            steps_passed += 1
            evidence["delete"] = {"success": True}
        else:
            evidence["delete"] = {"success": False, "status": resp.status_code}

    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e), evidence=evidence)

    return PrimitiveResult(
        passed=steps_passed == steps_total,
        data={"steps_passed": steps_passed, "steps_total": steps_total},
        evidence=evidence,
    )


def p06_json_schema_match(inputs: dict) -> PrimitiveResult:
    response = context.get("_last_response", {})
    body = response.get("body", {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return PrimitiveResult(passed=False, message="Response is not valid JSON")

    required = inputs.get("required_fields", [])
    data_obj = body.get("data", body)
    missing = [f for f in required if f not in data_obj]
    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"missing_fields": missing, "all_present": len(missing) == 0},
    )


def p07_json_value_assert(inputs: dict) -> PrimitiveResult:
    response = context.get("_last_response", {})
    body = response.get("body", {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = {"_raw_text": body[:2000], "_is_html": "<html" in body[:100].lower()}

    assertions = inputs.get("assertions", [])
    results = []
    all_passed = True

    for assertion in assertions:
        path = assertion["path"]
        expected = assertion.get("expected")
        tolerance = assertion.get("tolerance", 0)
        operator = assertion.get("operator", "eq")

        actual = _resolve_json_path(body, path)

        if expected == "exists":
            passed = actual is not None
        elif expected == "is_array":
            passed = isinstance(actual, list)
        elif expected == "is_boolean":
            passed = isinstance(actual, bool)
        elif expected == "not_exists":
            passed = actual is None
        elif expected == "has_exactly_keys":
            keys = assertion.get("keys", [])
            passed = isinstance(actual, dict) and set(actual.keys()) == set(keys)
        elif isinstance(expected, str) and expected.startswith("contains:"):
            substr = expected[len("contains:"):]
            passed = isinstance(actual, str) and substr.lower() in actual.lower()
        elif isinstance(expected, str) and expected.startswith("matches_regex:"):
            pattern = expected[len("matches_regex:"):]
            passed = isinstance(actual, str) and bool(re.match(pattern, actual))
        elif isinstance(expected, str) and expected.startswith("has_exactly_keys:"):
            keys = expected[len("has_exactly_keys:"):].split(",")
            passed = isinstance(actual, dict) and set(actual.keys()) == set(keys)
        elif isinstance(expected, str) and expected.startswith("not_equals:"):
            val = expected[len("not_equals:"):]
            try:
                val = int(val)
            except ValueError:
                pass
            passed = actual != val
        elif isinstance(expected, list) and path.endswith("body_text_excludes"):
            if isinstance(actual, str):
                passed = not any(term.lower() in actual for term in expected)
            else:
                passed = True
        elif operator == "gte":
            passed = actual is not None and actual >= expected
        elif operator == "lte":
            passed = actual is not None and actual <= expected
        else:
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                passed = abs(actual - expected) <= tolerance
            else:
                passed = actual == expected

        if not passed:
            all_passed = False
        results.append({"path": path, "actual": actual, "expected": expected, "passed": passed})

    return PrimitiveResult(passed=all_passed, data={"all_passed": all_passed, "results": results})


def _resolve_json_path(obj: Any, path: str) -> Any:
    if path == "$.headers.x-content-type-options" or path.startswith("$.headers."):
        response = context.get("_last_response", {})
        headers = response.get("headers", {})
        header_name = path.split("$.headers.", 1)[1]
        return headers.get(header_name) or headers.get(header_name.lower()) or headers.get(header_name.title())
    if path == "$.body_text_excludes":
        response = context.get("_last_response", {})
        body = response.get("body", {})
        raw = body.get("_raw_text", "") if isinstance(body, dict) else str(body)
        return raw.lower()
    if path == "$.status_not_500":
        response = context.get("_last_response", {})
        return "verified" if response.get("status_code", 0) != 500 else "not_verified"
    if path == "$.status_codes_match":
        return context.get("_status_codes_match")

    if not path.startswith("$."):
        path = "$." + path
    parts = path[2:].split(".")
    current = obj
    for part in parts:
        if current is None:
            return None
        if "[" in part:
            key, idx_str = part.split("[", 1)
            idx_str = idx_str.rstrip("]")
            if key:
                current = current.get(key) if isinstance(current, dict) else None
            if current is None:
                return None
            try:
                idx = int(idx_str)
                current = current[idx] if isinstance(current, list) and idx < len(current) else None
            except (ValueError, IndexError):
                return None
        elif part == "length":
            return len(current) if isinstance(current, (list, dict, str)) else None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
    return current


def p08_db_query(inputs: dict) -> PrimitiveResult:
    sql = resolve_placeholders(inputs["sql"], context)
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, context)
    except Exception:
        pass
    expected = inputs.get("expected_result")
    try:
        conn = _get_db_conn()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        else:
            rows = []
            conn.commit()
        cur.close()
        conn.close()

        if expected is not None:
            if isinstance(expected, dict):
                if "row_count" in expected:
                    match = len(rows) == expected["row_count"]
                elif "cnt" in expected:
                    if rows:
                        actual_val = rows[0].get("cnt", rows[0].get(list(rows[0].keys())[0]))
                        match = actual_val == expected["cnt"]
                    else:
                        match = expected["cnt"] == 0
                else:
                    match = len(rows) > 0 and all(
                        rows[0].get(k) == v for k, v in expected.items()
                    )
            elif isinstance(expected, list):
                match = rows == expected
            else:
                match = len(rows) > 0
        else:
            match = True

        return PrimitiveResult(
            passed=match,
            data={"rows": rows, "row_count": len(rows), "match": match},
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")


def p09_db_table_exists(inputs: dict) -> PrimitiveResult:
    tables = inputs["tables"]
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
        """)
        existing_tables = {row[0] for row in cur.fetchall()}
        cur.close()
        conn.close()

        found = [t for t in tables if t in existing_tables]
        missing = [t for t in tables if t not in existing_tables]

        return PrimitiveResult(
            passed=len(missing) == 0,
            data={"existing": found, "missing": missing, "found_count": len(found), "total_count": len(tables)},
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")


def p10_db_column_check(inputs: dict) -> PrimitiveResult:
    table = inputs["table"]
    expected_columns = inputs["expected_columns"]
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
        """, (table,))
        actual_columns = {row[0] for row in cur.fetchall()}
        cur.close()
        conn.close()

        found = [c for c in expected_columns if c in actual_columns]
        missing = [c for c in expected_columns if c not in actual_columns]

        return PrimitiveResult(
            passed=len(missing) == 0,
            data={"existing": found, "missing": missing, "found_count": len(found), "total_count": len(expected_columns)},
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")


def p11_db_index_check(inputs: dict) -> PrimitiveResult:
    table = inputs["table"]
    expected_indexes = inputs.get("expected_indexes", [])
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = %s
        """, (table,))
        index_defs = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()

        found = 0
        for expected_cols in expected_indexes:
            for idx_def in index_defs:
                if all(col.lower() in idx_def.lower() for col in expected_cols):
                    found += 1
                    break

        return PrimitiveResult(
            passed=found == len(expected_indexes),
            data={"found": found, "total": len(expected_indexes), "index_defs": index_defs},
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")


def p12_docker_exec(inputs: dict) -> PrimitiveResult:
    command = resolve_placeholders(inputs["command"], context)
    container = inputs.get("container", APP_CONTAINER)
    try:
        result = subprocess.run(
            ["docker", "exec", container] + shlex.split(command),
            capture_output=True, text=True, timeout=30
        )
        return PrimitiveResult(
            passed=result.returncode == 0,
            data={"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p13_auth_login(inputs: dict) -> PrimitiveResult:
    role = inputs.get("role", "admin")
    method = inputs.get("method", "api_key")

    context.setdefault("org_id", EVAL_ORG_ID)
    context.setdefault("project_id", EVAL_PROJECT_ID)
    context.setdefault("env_id", EVAL_ENV_PROD)
    context.setdefault("prod_env_id", EVAL_ENV_PROD)
    context.setdefault("dev_env_id", EVAL_ENV_DEV)
    context.setdefault("admin_email", EVAL_ADMIN_EMAIL)
    context.setdefault("api_key", EVAL_API_KEY)
    context.setdefault("valid_api_key", EVAL_API_KEY)

    if method == "api_key":
        context["auth_token"] = EVAL_API_KEY
        context[f"api_key_{role}"] = EVAL_API_KEY
        context["_last_response"] = {"status_code": 200, "body": {"session_token": "api_key_mode"}, "headers": {}}
        return PrimitiveResult(passed=True, data={"method": "api_key_config", "role": role})

    if f"api_key_{role}" in context:
        context["auth_token"] = context[f"api_key_{role}"]
        return PrimitiveResult(passed=True, data={"method": "cached_api_key", "role": role})

    user = TEST_USERS.get(role, TEST_USERS["admin"])

    try:
        http_session = requests.Session()
        csrf_resp = http_session.get(f"{APP_BASE_URL}/api/auth/csrf", timeout=HTTP_TIMEOUT)
        if csrf_resp.status_code == 200:
            csrf_data = csrf_resp.json()
            csrf_token = csrf_data.get("csrfToken", "")

            login_resp = http_session.post(
                f"{APP_BASE_URL}/api/auth/callback/credentials",
                data={"email": user["email"], "password": user["password"], "csrfToken": csrf_token},
                timeout=HTTP_TIMEOUT,
                allow_redirects=False,
            )
            session_token = http_session.cookies.get("next-auth.session-token") or http_session.cookies.get("__Secure-next-auth.session-token")
            if session_token:
                context["auth_token"] = session_token
                context["session_cookies"] = dict(http_session.cookies)
                context[f"session_{role}"] = session_token
                context["_last_response"] = {"status_code": 200, "body": {"session_token": session_token}, "headers": {}}
                return PrimitiveResult(passed=True, data={"method": "nextauth_session", "role": role})
    except Exception:
        pass

    try:
        conn = _get_db_conn()
        cur = conn.cursor()

        user_id = None
        for user_query in (
            'SELECT id FROM "User" WHERE email = %s',
            'SELECT id FROM "users" WHERE email = %s',
            "SELECT id FROM users WHERE email = %s",
        ):
            try:
                cur.execute(user_query, (user["email"],))
                row = cur.fetchone()
                if row:
                    user_id = row[0]
                    break
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue

        if user_id is not None:
            context["admin_id"] = user_id

            membership = None
            for mem_query in (
                'SELECT "organizationId" FROM "Membership" WHERE "userId" = %s LIMIT 1',
                'SELECT organization_id FROM "memberships" WHERE user_id = %s LIMIT 1',
                "SELECT organization_id FROM memberships WHERE user_id = %s LIMIT 1",
            ):
                try:
                    cur.execute(mem_query, (user_id,))
                    membership = cur.fetchone()
                    if membership:
                        break
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    continue

            if membership:
                context["org_id"] = membership[0]

                ak_row = None
                for ak_query in (
                    'SELECT ak."hashedKey", ak.id FROM "ApiKey" ak '
                    'WHERE ak."organizationId" = %s LIMIT 1',
                    'SELECT ak.hashed_key, ak.id FROM "api_keys" ak '
                    'WHERE ak.organization_id = %s LIMIT 1',
                    "SELECT ak.hashed_key, ak.id FROM api_keys ak "
                    "WHERE ak.organization_id = %s LIMIT 1",
                ):
                    try:
                        cur.execute(ak_query, (membership[0],))
                        ak_row = cur.fetchone()
                        if ak_row:
                            break
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        continue

                if ak_row:
                    context[f"api_key_{role}"] = ak_row[0]
                    context["auth_token"] = ak_row[0]
                    cur.close()
                    conn.close()
                    return PrimitiveResult(passed=True, data={"method": "db_api_key_lookup", "role": role})

                envs = None
                for env_query in (
                    'SELECT e.id, e.type, p.id as project_id FROM "Environment" e '
                    'JOIN "Project" p ON e."projectId" = p.id '
                    'WHERE p."organizationId" = %s ORDER BY e.type',
                    'SELECT e.id, e.type, p.id as project_id FROM "environments" e '
                    'JOIN "projects" p ON e.project_id = p.id '
                    'WHERE p.organization_id = %s ORDER BY e.type',
                ):
                    try:
                        cur.execute(env_query, (membership[0],))
                        envs = cur.fetchall()
                        if envs:
                            break
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        continue

                if envs:
                    for env_row in envs:
                        env_id, env_type, project_id = env_row
                        if env_type == "production":
                            context["env_id"] = env_id
                            context["prod_env_id"] = env_id
                        elif env_type == "development":
                            context["dev_env_id"] = env_id
                        context["project_id"] = project_id

        cur.close()
        conn.close()
    except Exception:
        pass

    if "auth_token" in context or f"session_{role}" in context or f"api_key_{role}" in context:
        context["_last_response"] = {"status_code": 200, "body": {"session_token": context.get("auth_token", "db_fallback")}, "headers": {}}
        return PrimitiveResult(passed=True, data={"method": "db_fallback", "role": role})

    return PrimitiveResult(passed=False, data={"method": "none", "role": role}, message="Failed to obtain any valid credential")


def p14_permission_check(inputs: dict) -> PrimitiveResult:
    action = resolve_placeholders(inputs["action"], context)
    expected_result = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status", [403, 404])
    ctx = resolve_placeholders(inputs.get("context", {}), context)

    if isinstance(expected_status, int):
        expected_status = [expected_status]

    parts = action.split(" ", 1)
    method = parts[0].upper()
    path = parts[1] if len(parts) > 1 else "/"

    headers = {}
    if "api_key" in ctx:
        headers["x-api-key"] = ctx["api_key"]
    elif "role" in ctx:
        role = ctx["role"]
        if f"session_{role}" in context:
            headers["Authorization"] = f"Bearer {context[f'session_{role}']}"

    try:
        resp = requests.request(method, APP_BASE_URL + path, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=False)

        if expected_result == "denied":
            passed = resp.status_code in expected_status
        elif expected_result == "allowed":
            passed = resp.status_code in (expected_status if isinstance(expected_status, list) else [expected_status])
        else:
            passed = False

        return PrimitiveResult(
            passed=passed,
            data={"status_code": resp.status_code, "expected_result": expected_result, "expected_status": expected_status},
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p15_status_code_assert(inputs: dict) -> PrimitiveResult:
    response = context.get("_last_response", {})
    actual = response.get("status_code", 0)

    accepted = set()
    for key in ("expected_status", "acceptable_statuses", "acceptable", "expected"):
        v = inputs.get(key)
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            accepted.update(int(x) for x in v if x is not None)
        else:
            try:
                accepted.add(int(v))
            except (TypeError, ValueError):
                continue

    if accepted:
        passed = actual in accepted
    else:
        passed = 200 <= actual < 300

    return PrimitiveResult(
        passed=passed,
        data={"actual": actual,
              "expected": sorted(accepted) if accepted else "2xx"},
        message=f"Status: {actual} (expected {sorted(accepted) if accepted else '2xx'})",
    )


def p16_response_time_check(inputs: dict) -> PrimitiveResult:
    response = context.get("_last_response", {})
    actual_ms = response.get("response_time_ms", 0)
    max_ms = inputs.get("max_response_time_ms", 5000)
    passed = actual_ms <= max_ms
    return PrimitiveResult(passed=passed, data={"actual_ms": actual_ms, "max_ms": max_ms})


def p17_llm_judge(inputs: dict) -> PrimitiveResult:
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
    if not LLM_API_KEY:
        return PrimitiveResult(
            passed=True,
            data={"score": 0, "skipped": True, "llm_api_failure": False,
                  "reason": "LLM_API_KEY unset"},
            message="LLM judge skipped (no API key)",
        )

    rubric_prompt = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "")

    max_files = int(inputs.get("max_files", 12))
    max_lines_per_file = int(inputs.get("max_lines_per_file", 200))
    max_chars_per_file = int(inputs.get("max_chars_per_file", 5000))
    max_total_evidence_chars = int(inputs.get("max_total_evidence_chars", 120_000))
    sample_extensions = tuple(inputs.get(
        "sample_extensions",
        (".ts", ".tsx", ".js", ".jsx", ".py", ".rb", ".go", ".java", ".rs", ".prisma", ".sql", ".json", ".yaml", ".yml", ".md")
    ))

    def _read_truncated(fpath: str) -> str:
        try:
            with open(fpath, "r", errors="ignore") as f:
                content = f.read(max_chars_per_file + 1)
        except Exception:
            return ""
        if not content:
            return ""
        lines = content.splitlines()
        if len(lines) > max_lines_per_file:
            content = "\n".join(lines[:max_lines_per_file]) + f"\n... [{len(lines) - max_lines_per_file} more lines truncated] ...\n"
        return content[:max_chars_per_file]

    evidence_text = f"Evidence type: {evidence_type}\n"
    if "files_to_sample" in inputs:
        files_collected = 0
        for file_pattern in inputs["files_to_sample"]:
            if files_collected >= max_files or len(evidence_text) >= max_total_evidence_chars:
                break
            full_path = os.path.join(WORKSPACE_DIR, file_pattern)
            candidates = [full_path]
            if full_path.endswith("."):
                base = full_path.rstrip(".")
                candidates = [base + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".py", "")] + [base]
            elif not os.path.exists(full_path):
                candidates = [full_path + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".py")] + [full_path]
            resolved = next((c for c in candidates if os.path.exists(c)), full_path)

            if os.path.isfile(resolved):
                content = _read_truncated(resolved)
                if content:
                    evidence_text += f"\n--- {file_pattern} ---\n{content}\n"
                    files_collected += 1
            elif os.path.isdir(resolved):
                SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "coverage", ".turbo", "__pycache__", ".cache"}
                base_depth = resolved.rstrip(os.sep).count(os.sep)
                for root, dirs, files in os.walk(resolved):
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
                    cur_depth = root.rstrip(os.sep).count(os.sep) - base_depth
                    if cur_depth >= 4:
                        dirs[:] = []

                    rel_files = [f for f in files if f.endswith(sample_extensions)]
                    for fname in rel_files:
                        if files_collected >= max_files or len(evidence_text) >= max_total_evidence_chars:
                            break
                        fpath = os.path.join(root, fname)
                        content = _read_truncated(fpath)
                        if not content:
                            continue
                        rel = os.path.relpath(fpath, WORKSPACE_DIR)
                        evidence_text += f"\n--- {rel} ---\n{content}\n"
                        files_collected += 1
                    if files_collected >= max_files or len(evidence_text) >= max_total_evidence_chars:
                        break

    if len(evidence_text) > max_total_evidence_chars:
        evidence_text = evidence_text[:max_total_evidence_chars] + "\n... [evidence truncated to fit prompt budget] ...\n"

    from _llm_judge_safe import safe_chat_completion

    _judge_messages = [
        {"role": "system", "content": f"You are an expert code reviewer. Score the following evidence on a scale of {score_range[0]}-{score_range[1]}. Respond with JSON: {{\"score\": <number>, \"reason\": \"<explanation>\"}}"},
        {"role": "user", "content": f"{rubric_prompt}\n\n{evidence_text}"},
    ]

    def _judge_call(msgs):
        return safe_chat_completion(
            messages=msgs,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            temperature=0.1,
            max_tokens=8192,
        )

    res = _judge_call(_judge_messages)
    if res.skipped:
        return PrimitiveResult(
            passed=False,
            data={
                "score": 0,
                "skipped": True,
                "llm_api_failure": res.llm_api_failure,
                "exception_class": res.exception_class,
                "reason": res.error or "skipped",
            },
            message=f"LLM judge SKIPPED ({res.reason()})",
        )

    def _parse_score(raw: str):
        raw_text = (raw or "").strip()
        _score = None
        _reason = ""
        import re as _re

        stripped = raw_text.strip().strip("```json").strip("```").strip()
        candidates = [stripped]
        for m in _re.finditer(r"\{[\s\S]*?\}", raw_text):
            candidates.append(m.group(0))
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "score" in parsed:
                    _score = parsed.get("score")
                    _reason = parsed.get("reason", "")
                    break
            except Exception:
                continue

        if _score is None:
            m = _re.search(r'score[^\d\n]{0,15}(-?\d+(?:\.\d+)?)', raw_text, _re.IGNORECASE)
            if m:
                try:
                    _score = float(m.group(1))
                    _reason = raw_text[:500]
                except Exception:
                    _score = None
        if _score is None:
            m = _re.search(r'\*\*\s*(-?\d+(?:\.\d+)?)\s*\*\*\s*$', raw_text)
            if m:
                _score = float(m.group(1))
                _reason = raw_text[:500]
        if _score is None:
            for _line in reversed(raw_text.splitlines()):
                _cl = _line.strip().strip('`').strip().rstrip('.').strip()
                if _re.fullmatch(r'-?\d+(?:\.\d+)?', _cl):
                    _score = float(_cl)
                    _reason = raw_text[:500]
                    break
        if _score is None:
            _nums = _re.findall(r'-?\d+(?:\.\d+)?', raw_text)
            if _nums:
                try:
                    _score = float(_nums[-1])
                    _reason = raw_text[:500]
                except Exception:
                    _score = None
        return _score, _reason

    score, reason = _parse_score(res.raw)
    if score is None:
        retry = _judge_call(_judge_messages + [
            {"role": "assistant", "content": (res.raw or "")[:2000]},
            {"role": "user", "content": (
                f"You did not output a score. Reply with ONLY a single integer "
                f"between {score_range[0]} and {score_range[1]} — no words, no "
                f"explanation, just the number."
            )},
        ])
        if not retry.skipped:
            score, reason = _parse_score(retry.raw)

    if score is None:
        return PrimitiveResult(
            passed=False,
            data={
                "score": 0,
                "skipped": True,
                "parse_failure": True,
                "reason": "no parseable score after retry",
                "raw": (res.raw or "")[:500],
            },
            message="LLM judge parse error: no parseable score after retry (SKIPPED)",
        )

    try:
        score_num = float(score)
    except Exception:
        score_num = 0.0
    score_num = min(max(score_num, float(score_range[0])), float(score_range[1]))
    return PrimitiveResult(passed=True, data={"score": score_num, "reason": reason})


def p18_browser_interaction(inputs: dict) -> PrimitiveResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return PrimitiveResult(passed=False, message="Playwright not installed")

    actions = inputs.get("actions", [])
    if not actions:
        return PrimitiveResult(passed=False, message="No actions specified")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            pw_context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = pw_context.new_page()
            evidence = []
            all_ok = True

            for act in actions:
                action = act.get("action", "")

                if action == "login":
                    creds = act.get("credentials", {})
                    email = creds.get("email", "")
                    password = creds.get("password", "")
                    if not password or "{{" in password:
                        for u in TEST_USERS.values():
                            if u["email"] == email:
                                password = u["password"]
                                break
                    if not email or "{{" in email:
                        email = TEST_USERS["admin"]["email"]
                        password = TEST_USERS["admin"]["password"]
                    page.goto(APP_BASE_URL + "/auth/login", wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(2000)
                    try:
                        email_btn = page.query_selector('button:has-text("Login with Email")')
                        if email_btn:
                            email_btn.click()
                            page.wait_for_timeout(2000)
                        page.fill('#email', email)
                        page.fill('#password', password)
                        submit = page.query_selector('button:has-text("Login with Email"), button[type="submit"]')
                        if submit:
                            submit.click()
                        page.wait_for_timeout(5000)
                        evidence.append(f"Login as {email}: navigated to {page.url}")
                    except Exception as e:
                        evidence.append(f"Login failed: {e}")
                        all_ok = False

                elif action == "navigate":
                    url = act.get("url", "/")
                    if url.startswith("/"):
                        url = APP_BASE_URL + url
                    try:
                        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=6000)
                        except Exception:
                            pass
                        page.wait_for_timeout(10000)
                        status = resp.status if resp else 0
                        evidence.append(f"Navigate {url}: status={status}, title={page.title()}")
                        context["_last_browser_status"] = status
                    except Exception as e:
                        evidence.append(f"Navigate {url} failed: {e}")
                        all_ok = False

                elif action == "get_cookie":
                    name = act.get("name", "")
                    store_as = act.get("store_as", name)
                    cookies = pw_context.cookies()
                    val = next((c["value"] for c in cookies if c["name"] == name), None)
                    if val:
                        context[store_as] = val
                        evidence.append(f"Cookie '{name}' captured")
                    else:
                        evidence.append(f"Cookie '{name}' not found")
                        all_ok = False

                elif action == "set_cookie":
                    name = act.get("name", "")
                    value = act.get("value", "")
                    pw_context.add_cookies([{"name": name, "value": value, "domain": "localhost", "path": "/"}])
                    evidence.append(f"Cookie '{name}' set")

                elif action == "logout":
                    try:
                        page.goto(APP_BASE_URL + "/auth/login", wait_until="networkidle", timeout=15000)
                        pw_context.clear_cookies()
                        evidence.append("Logged out (cookies cleared)")
                    except Exception as e:
                        evidence.append(f"Logout: {e}")

                elif action == "assert_status":
                    expected = act.get("expected", 200)
                    actual = context.get("_last_browser_status", 0)
                    if actual == expected:
                        evidence.append(f"Status assert OK: {actual}")
                    else:
                        evidence.append(f"Status assert FAIL: expected {expected}, got {actual}")
                        all_ok = False

                elif action == "assert_url_contains":
                    expected_fragment = act.get("expected", "")
                    current_url = page.url
                    if expected_fragment in current_url:
                        evidence.append(f"URL contains '{expected_fragment}': {current_url}")
                    else:
                        evidence.append(f"URL does NOT contain '{expected_fragment}': {current_url}")
                        all_ok = False

            context["last_page_html"] = page.content()[:200000] if all_ok else ""
            context["last_page_url"] = page.url
            context["last_page_title"] = page.title()
            browser.close()

        return PrimitiveResult(
            passed=all_ok,
            data={"evidence": evidence, "url": context.get("last_page_url", "")},
            message="; ".join(evidence[-3:]),
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"P18 error: {e}")


def p19_dom_assertion(inputs: dict) -> PrimitiveResult:
    assertions = inputs.get("assertions", [])
    if not assertions:
        return PrimitiveResult(passed=False, message="No assertions specified")

    html = context.get("last_page_html", "")
    if not html:
        return PrimitiveResult(passed=False, message="No page HTML captured (P18 must run first)")

    all_ok = True
    evidence = []

    for assertion in assertions:
        selectors = assertion.get("selector", "")
        expected = assertion.get("expected", "exists")
        found = False
        for sel in selectors.split(","):
            sel = sel.strip()
            if not sel:
                continue
            sel_lower = sel.lower()
            tag_match = re.search(r'^(\w+)', sel_lower)
            if tag_match and f"<{tag_match.group(1)}" in html.lower():
                found = True
                break
            attr_match = re.search(r'\[([^=\]]+)(?:=[\'"]?([^\]"\']+))?', sel)
            if attr_match:
                attr_name = attr_match.group(1)
                attr_val = attr_match.group(2)
                if attr_val and attr_val in html:
                    found = True
                    break
                elif attr_name in html:
                    found = True
                    break
            class_match = re.search(r'\[class\*=[\'"]([^\]"\']+)', sel)
            if class_match and class_match.group(1) in html:
                found = True
                break
            if "data-testid" in sel:
                testid = re.search(r"data-testid=['\"]([^'\"]+)", sel)
                if testid and testid.group(1) in html:
                    found = True
                    break

        if found:
            evidence.append(f"'{selectors}': found")
        else:
            evidence.append(f"'{selectors}': NOT found")
            all_ok = False

    return PrimitiveResult(
        passed=all_ok,
        data={"assertions": evidence},
        message="; ".join(evidence),
    )


PRIMITIVE_MAP = {
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
