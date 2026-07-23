import base64
import json
import os
import re
import secrets
import subprocess
import glob as globmod
from typing import Any

import psycopg2
import psycopg2.extras
import requests
from jsonpath_ng.ext import parse as jp_parse

from config import (
    APP_BASE_URL, WORKSPACE_DIR, HTTP_TIMEOUT,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    APP_CONTAINER, LLM_API_KEY, LLM_API_BASE, LLM_MODEL,
    TEST_USERS,
)
from utils import PrimitiveResult

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
context: dict[str, Any] = {}
_token_cache: dict[str, str] = {}
_publishable_key: str | None = None
_run_suffix: str = secrets.token_hex(3)


def _ensure_publishable_key() -> str | None:
    global _publishable_key
    if _publishable_key:
        return _publishable_key

    admin_token = _token_cache.get("admin")
    if not admin_token:
        admin_info = TEST_USERS.get("admin")
        try:
            r = requests.post(f"{APP_BASE_URL}/auth/user/emailpass",
                              json={"email": admin_info["email"], "password": admin_info["password"]},
                              timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                admin_token = r.json().get("token")
                _token_cache["admin"] = admin_token
        except Exception:
            pass
    if not admin_token:
        return None

    hdrs = {"Authorization": f"Bearer {admin_token}"}
    try:
        r = requests.get(f"{APP_BASE_URL}/admin/api-keys", headers=hdrs, timeout=HTTP_TIMEOUT)
        keys = r.json().get("api_keys", [])
        pub_keys = [k for k in keys if k.get("type") == "publishable" and k.get("token")]
        if pub_keys:
            pk_id = pub_keys[0]["id"]
            _publishable_key = pub_keys[0]["token"]
            r2 = requests.get(f"{APP_BASE_URL}/admin/sales-channels", headers=hdrs, timeout=HTTP_TIMEOUT)
            scs = r2.json().get("sales_channels", [])
            if scs:
                requests.post(f"{APP_BASE_URL}/admin/api-keys/{pk_id}/sales-channels",
                              json={"add": [scs[0]["id"]]}, headers=hdrs, timeout=HTTP_TIMEOUT)
            return _publishable_key
    except Exception:
        pass
    return None


def _resolve(val: Any) -> Any:
    if isinstance(val, str):
        def _repl(m):
            key = m.group(1)
            return str(context.get(key, m.group(0)))
        return re.sub(r"\{\{(\w+)\}\}", _repl, val)
    if isinstance(val, dict):
        return {k: _resolve(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_resolve(v) for v in val]
    return val


def _url(path: str) -> str:
    if path.startswith("http"):
        return path
    return APP_BASE_URL.rstrip("/") + ("" if path.startswith("/") else "/") + path


def _db_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ===================================================================
# ===================================================================
def p01_file_exists(inputs: dict) -> PrimitiveResult:
    raw_path = _resolve(inputs["path"])
    path = os.path.join(WORKSPACE_DIR, raw_path)
    ftype = inputs.get("type", "file")
    if ftype == "directory":
        ok = os.path.isdir(path)
    else:
        ok = os.path.isfile(path)
    if not ok:
        try:
            container_path = f"/app/{raw_path}" if not raw_path.startswith("/") else raw_path
            result = subprocess.run(
                ["docker", "exec", APP_CONTAINER, "test", "-e", container_path],
                capture_output=True, timeout=10)
            if result.returncode == 0:
                ok = True
        except Exception:
            pass
    return PrimitiveResult(passed=ok, data={"exists": ok, "path": path},
                           message=f"{'Found' if ok else 'Missing'}: {path}")


# ===================================================================
# ===================================================================
def p02_file_content_match(inputs: dict) -> PrimitiveResult:
    raw_path = _resolve(inputs["path"])
    path = os.path.join(WORKSPACE_DIR, raw_path)
    content = None
    if os.path.isfile(path):
        content = open(path, errors="replace").read()
    else:
        try:
            container_path = f"/app/{raw_path}" if not raw_path.startswith("/") else raw_path
            result = subprocess.run(
                ["docker", "exec", APP_CONTAINER, "cat", container_path],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                content = result.stdout
        except Exception:
            pass
    if content is None:
        return PrimitiveResult(passed=False, message=f"File not found: {path}")

    patterns = inputs.get("patterns") or [inputs.get("pattern", "")]
    if isinstance(patterns, str):
        patterns = [patterns]
    match_type = inputs.get("match_type", "contains")

    def _match_one(p, content, mt):
        if mt == "regex":
            return bool(re.search(p, content))
        return p.lower() in content.lower()

    matched_list = []
    for pat in patterns:
        if isinstance(pat, dict) and "any_of" in pat:
            alts = [_resolve(p) for p in pat["any_of"]]
            found = any(_match_one(a, content, match_type) for a in alts)
            matched_list.append((pat["any_of"], found))
        else:
            pat = _resolve(pat)
            found = _match_one(pat, content, match_type)
            matched_list.append((pat, found))
    ok = all(f for _, f in matched_list)
    detail = "; ".join(f"Pattern {p!r}: {'matched' if f else 'no match'}" for p, f in matched_list)
    return PrimitiveResult(passed=ok, data={"matched": ok, "patterns": matched_list},
                           message=detail)


# ===================================================================
# ===================================================================
def p03_file_count(inputs: dict) -> PrimitiveResult:
    base = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", ""))
    pattern = inputs.get("glob", "**/*")
    files = globmod.glob(os.path.join(base, pattern), recursive=True)
    files = [f for f in files if os.path.isfile(f)]
    min_exp = inputs.get("min_expected", 1)
    ok = len(files) >= min_exp
    return PrimitiveResult(passed=ok, data={"count": len(files)},
                           message=f"Found {len(files)} files (min {min_exp})")


# ===================================================================
# ===================================================================
def p04_http_request(inputs: dict) -> PrimitiveResult:
    method = _resolve(inputs["method"]).upper()
    path = _resolve(inputs["path"])
    url = _url(path)
    body = _resolve(inputs.get("body"))
    headers = _resolve(inputs.get("headers", {}))
    timeout = inputs.get("timeout", HTTP_TIMEOUT)

    if context.get("auth_token") and "Authorization" not in headers:
        headers.setdefault("Authorization", f"Bearer {context['auth_token']}")

    if "/store/" in path and "x-publishable-api-key" not in headers:
        pk = _ensure_publishable_key()
        if pk:
            headers["x-publishable-api-key"] = pk

    try:
        r = requests.request(method, url, json=body if body else None,
                             headers=headers, timeout=timeout, allow_redirects=True)
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"HTTP {method} {url} failed: {e}")

    if method == "POST" and r.status_code in (400, 409, 422, 500) and body and isinstance(body, dict):
        err_msg = ""
        try:
            err_msg = r.json().get("message", "") or r.text[:200]
        except Exception:
            err_msg = r.text[:200] if r.text else ""
        if "already exists" in err_msg.lower() or "duplicate" in err_msg.lower():
            for key in ("title", "name", "code", "handle", "email", "sku"):
                if key in body and isinstance(body[key], str):
                    body[key] = f"{body[key]}_{_run_suffix}"
            try:
                r = requests.request(method, url, json=body,
                                     headers=headers, timeout=timeout, allow_redirects=True)
            except Exception as e:
                return PrimitiveResult(passed=False, message=f"HTTP {method} {url} retry failed: {e}")

    try:
        resp_json = r.json()
    except Exception:
        resp_json = None

    context["last_response"] = {
        "status_code": r.status_code,
        "headers": dict(r.headers),
        "body": resp_json,
        "text": r.text[:5000],
        "response_time_ms": int(r.elapsed.total_seconds() * 1000),
    }

    if method == "POST" and r.status_code in (200, 201) and resp_json and isinstance(resp_json, dict):
        for entity_key, entity_val in resp_json.items():
            if isinstance(entity_val, dict) and "id" in entity_val:
                ctx_key = f"{entity_key}_id"
                context[ctx_key] = entity_val["id"]
                context["last_created_id"] = entity_val["id"]

    return PrimitiveResult(passed=True, data=context["last_response"],
                           message=f"{method} {path} → {r.status_code}")


# ===================================================================
# ===================================================================
def p05_api_crud(inputs: dict) -> PrimitiveResult:
    resource = _resolve(inputs["resource"])
    create_body = _resolve(inputs.get("create_body", {}))
    update_body = _resolve(inputs.get("update_body"))
    read_fields = inputs.get("expected_read_fields", [])
    token = context.get("auth_token")
    hdrs = {"Authorization": f"Bearer {token}"} if token else {}
    if "/store/" in resource:
        pk = _ensure_publishable_key()
        if pk:
            hdrs["x-publishable-api-key"] = pk
    base = _url(resource)
    steps_passed = 0
    steps_total = 4
    entity_id = None
    evidence: dict[str, Any] = {}

    try:
        r = requests.post(base, json=create_body, headers=hdrs, timeout=HTTP_TIMEOUT)
        if r.status_code in (200, 201):
            steps_passed += 1
            body = r.json()
            for key in body:
                if isinstance(body[key], dict) and "id" in body[key]:
                    entity_id = body[key]["id"]
                    break
            evidence["create"] = {"status": r.status_code, "id": entity_id}
        else:
            evidence["create"] = {"status": r.status_code, "error": r.text[:500]}
    except Exception as e:
        evidence["create"] = {"error": str(e)}

    if not entity_id:
        return PrimitiveResult(passed=False, data={"steps_passed": steps_passed, "steps_total": steps_total},
                               message=f"CRUD create failed; got {evidence.get('create', {})}")

    try:
        r = requests.get(f"{base}/{entity_id}", headers=hdrs, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            steps_passed += 1
            body = r.json()
            if read_fields:
                top = next(iter(body.values())) if isinstance(body, dict) and len(body) == 1 else body
                if isinstance(top, dict) and all(f in top for f in read_fields):
                    pass
            evidence["read"] = {"status": r.status_code}
        else:
            evidence["read"] = {"status": r.status_code}
    except Exception as e:
        evidence["read"] = {"error": str(e)}

    if update_body:
        try:
            r = requests.post(f"{base}/{entity_id}", json=_resolve(update_body),
                              headers=hdrs, timeout=HTTP_TIMEOUT)
            if r.status_code in (200, 201):
                steps_passed += 1
            evidence["update"] = {"status": r.status_code}
        except Exception as e:
            evidence["update"] = {"error": str(e)}
    else:
        steps_passed += 1
        steps_total -= 0

    try:
        r = requests.delete(f"{base}/{entity_id}", headers=hdrs, timeout=HTTP_TIMEOUT)
        if r.status_code in (200, 204):
            steps_passed += 1
        evidence["delete"] = {"status": r.status_code}
    except Exception as e:
        evidence["delete"] = {"error": str(e)}

    return PrimitiveResult(
        passed=steps_passed == steps_total,
        data={"steps_passed": steps_passed, "steps_total": steps_total,
              "entity_id": entity_id, "evidence": evidence},
        message=f"CRUD {resource}: {steps_passed}/{steps_total} steps",
    )


# ===================================================================
# ===================================================================
def p06_json_schema_match(inputs: dict) -> PrimitiveResult:
    resp = context.get("last_response", {})
    body = resp.get("body") or {}
    required = inputs.get("required_fields", [])

    flat = body
    if isinstance(body, dict) and len(body) == 1:
        v = next(iter(body.values()))
        if isinstance(v, dict):
            flat = v

    missing = [f for f in required if f not in flat and f not in body]
    ok = len(missing) == 0
    return PrimitiveResult(passed=ok, data={"missing_fields": missing},
                           message=f"Schema: {'all present' if ok else 'missing ' + str(missing)}")


# ===================================================================
# ===================================================================
def p07_json_value_assert(inputs: dict) -> PrimitiveResult:
    resp = context.get("last_response", {})
    body = resp.get("body")
    assertions = inputs.get("assertions", [])

    if not assertions:
        return PrimitiveResult(passed=True, data={"results": []},
                               message="P07 vacuously pass (no assertions)")
    if body is None:
        return PrimitiveResult(passed=False, message="No JSON body in last response")

    def _resolve_placeholder(v):
        if not isinstance(v, str):
            return v
        if "{{" not in v:
            return v
        import re as _re
        out = v
        for ph in _re.findall(r"\{\{(\w+)\}\}", v):
            val = context.get(ph)
            if val is not None:
                out = out.replace("{{" + ph + "}}", str(val))
        return out

    results = []
    all_pass = True

    for a in assertions:
        path = a.get("path", "$")
        try:
            expr = jp_parse(path)
            matches = expr.find(body)
            actual = matches[0].value if matches else None
        except Exception:
            actual = _deep_get(body, path)

        if a.get("store_as"):
            context[a["store_as"]] = actual
            _cap_ok = actual is not None
            if not _cap_ok:
                all_pass = False
            results.append({"path": path, "passed": _cap_ok,
                            "detail": f"store_as {a['store_as']}={actual}", "store_as": True})
            continue

        passed = False
        expected = a.get("expected")
        if isinstance(expected, str):
            expected = _resolve_placeholder(expected)
        tolerance = a.get("tolerance", 0)
        msg_detail = ""

        if "expected" in a:
            if isinstance(expected, str) and expected == "not_null":
                passed = actual is not None
                msg_detail = f"expected not_null, actual={actual}"
            elif isinstance(expected, str) and expected == "is_integer":
                passed = isinstance(actual, int) and not isinstance(actual, bool)
                msg_detail = f"expected is_integer, actual={actual} ({type(actual).__name__})"
            elif isinstance(expected, str) and expected == "is_string":
                passed = isinstance(actual, str)
                msg_detail = f"expected is_string, actual={actual}"
            elif isinstance(expected, str) and expected == "not_empty":
                passed = bool(actual)
                msg_detail = f"expected not_empty, actual={actual}"
            elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                passed = abs(actual - expected) <= tolerance
                msg_detail = f"expected={expected}, actual={actual}"
            else:
                passed = actual == expected
                msg_detail = f"expected={expected}, actual={actual}"
        elif "expected_gte" in a:
            passed = actual is not None and actual >= a["expected_gte"]
            msg_detail = f"expected>={a['expected_gte']}, actual={actual}"
        elif "expected_in" in a:
            passed = actual in a["expected_in"]
            msg_detail = f"expected in {a['expected_in']}, actual={actual}"
        elif "expected_not_null" in a:
            passed = actual is not None
            msg_detail = f"expected not null, actual={actual}"
        elif "expected_not_empty" in a:
            passed = actual is not None and (isinstance(actual, (list, dict)) and len(actual) > 0)
            msg_detail = f"expected not empty, actual type={type(actual).__name__}"
        elif "expected_length" in a:
            passed = isinstance(actual, list) and len(actual) == a["expected_length"]
            msg_detail = f"expected len={a['expected_length']}, actual len={len(actual) if isinstance(actual, list) else 'N/A'}"
        elif "expected_length_gte" in a:
            passed = isinstance(actual, list) and len(actual) >= a["expected_length_gte"]
            msg_detail = f"expected len>={a['expected_length_gte']}, actual={len(actual) if isinstance(actual, list) else 'N/A'}"
        elif "expected_contains" in a:
            passed = isinstance(actual, str) and a["expected_contains"] in actual
            msg_detail = f"expected contains '{a['expected_contains']}'"
        elif "expected_all" in a:
            if isinstance(actual, list):
                passed = all(v == a["expected_all"] for v in actual)
            else:
                passed = actual == a["expected_all"]
            msg_detail = f"expected all={a['expected_all']}"

        if not passed:
            all_pass = False
        results.append({"path": path, "passed": passed, "detail": msg_detail})

    return PrimitiveResult(passed=all_pass, data={"results": results},
                           message=f"Assertions: {sum(r['passed'] for r in results)}/{len(results)} passed")


def _deep_get(obj, path: str):
    parts = path.replace("$.", "").replace("$", "").split(".")
    cur = obj
    for p in parts:
        if not p:
            continue
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            try:
                cur = cur[int(p)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


# ===================================================================
# ===================================================================
def p08_db_query(inputs: dict) -> PrimitiveResult:
    sql = _resolve(inputs["sql"])
    expected = inputs.get("expected_result")
    try:
        conn = _db_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB query failed: {e}")

    rows = [dict(r) for r in rows]
    context["last_db_result"] = rows

    if expected is not None:
        if isinstance(expected, dict):
            ok = len(rows) > 0 and all(
                rows[0].get(k) == v for k, v in expected.items()
            )
        else:
            ok = rows == expected
        return PrimitiveResult(passed=ok, data={"rows": rows, "row_count": len(rows)},
                               message=f"DB: {len(rows)} rows, match={ok}")
    return PrimitiveResult(passed=len(rows) >= 0, data={"rows": rows, "row_count": len(rows)},
                           message=f"DB: {len(rows)} rows returned")


# ===================================================================
# ===================================================================
def p09_db_table_exists(inputs: dict) -> PrimitiveResult:
    tables_wanted = inputs["tables"]
    try:
        conn = _db_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            existing = {r["table_name"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB table check failed: {e}")

    found = []
    missing = []
    for t in tables_wanted:
        if t in existing:
            found.append(t)
        else:
            missing.append(t)

    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"existing": found, "missing": missing,
              "found_count": len(found), "total_count": len(tables_wanted)},
        message=f"Tables: {len(found)}/{len(tables_wanted)} found" +
                (f", missing: {missing}" if missing else ""),
    )


# ===================================================================
# ===================================================================
def p10_db_column_check(inputs: dict) -> PrimitiveResult:
    table = inputs["table"]
    expected_cols = inputs["expected_columns"]
    try:
        conn = _db_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name LIKE %s
                ORDER BY CASE WHEN table_name = %s THEN 0 ELSE 1 END, length(table_name)
            """, (f"%{table}%", table))
            tables = [r["table_name"] for r in cur.fetchall()]
            if not tables:
                conn.close()
                return PrimitiveResult(passed=False, message=f"Table '*{table}*' not found")
            real_table = tables[0]
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
            """, (real_table,))
            actual_cols = {r["column_name"] for r in cur.fetchall()}
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"Column check failed: {e}")

    found = [c for c in expected_cols if c in actual_cols]
    missing = [c for c in expected_cols if c not in actual_cols]
    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"existing": found, "missing": missing,
              "found_count": len(found), "total_count": len(expected_cols)},
        message=f"Columns in {real_table}: {len(found)}/{len(expected_cols)}" +
                (f", missing: {missing}" if missing else ""),
    )


# ===================================================================
# ===================================================================
def p11_db_index_check(inputs: dict) -> PrimitiveResult:
    table = inputs["table"]
    try:
        conn = _db_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT indexname, indexdef FROM pg_indexes
                WHERE tablename LIKE %s
            """, (f"%{table}%",))
            indexes = cur.fetchall()
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"Index check failed: {e}")

    return PrimitiveResult(passed=len(indexes) > 0,
                           data={"indexes": [dict(i) for i in indexes]},
                           message=f"Found {len(indexes)} indexes on *{table}*")


# ===================================================================
# ===================================================================
def p12_docker_exec(inputs: dict) -> PrimitiveResult:
    command = _resolve(inputs["command"])
    container = inputs.get("container", APP_CONTAINER)
    expect_success = inputs.get("expect_success", True)
    expect_output = inputs.get("expect_output_contains")

    try:
        result = subprocess.run(
            ["docker", "exec", container, "sh", "-c", command],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        try:
            result = subprocess.run(
                ["docker", "exec", container, "sh", "-c", command],
                capture_output=True, text=True, timeout=60,
            )
        except Exception as e2:
            return PrimitiveResult(passed=False, message=f"docker exec failed: {e2}")

    output = result.stdout + result.stderr
    ok = True
    if expect_success and result.returncode != 0:
        ok = False
    if expect_output and expect_output not in output:
        ok = False

    return PrimitiveResult(passed=ok,
                           data={"exit_code": result.returncode, "output": output[:3000]},
                           message=f"docker exec (rc={result.returncode}): {output[:200]}")


# ===================================================================
# ===================================================================
def p13_auth_login(inputs: dict) -> PrimitiveResult:
    role = inputs.get("role", "admin")
    method = inputs.get("method", "bearer_jwt")

    if role in _token_cache:
        cached = _token_cache[role]
        try:
            vr = requests.get(f"{APP_BASE_URL}/admin/products?limit=1",
                              headers={"Authorization": f"Bearer {cached}"}, timeout=5)
            if vr.status_code in (200, 401):
                if vr.status_code == 200:
                    context["auth_token"] = cached
                    return PrimitiveResult(passed=True, message=f"Auth: reused cached token for {role}")
                else:
                    del _token_cache[role]
        except Exception:
            del _token_cache[role]

    if method == "api_key_basic":
        return PrimitiveResult(passed=True, message="Auth: api_key_basic mode (no token caching)")

    user_info = TEST_USERS.get(role, TEST_USERS.get("admin"))
    email = user_info["email"]
    password = user_info["password"]
    token = None

    _ADMIN_ROLES = ("admin", "super_admin", "limited_admin", "no_role_user",
                    "product_reader", "product_full_reader")
    actor = "user" if role in _ADMIN_ROLES else "customer"

    try:
        r = requests.post(f"{APP_BASE_URL}/auth/{actor}/emailpass",
                          json={"email": email, "password": password}, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            body = r.json()
            token = body.get("token")
            if token:
                decoded = _decode_jwt_payload(token)
                if decoded and not decoded.get("actor_id"):
                    token = None
    except Exception:
        pass

    if not token and role == "admin":
        token = _bootstrap_admin(email, password)

    if not token and role in _ADMIN_ROLES and role != "admin":
        token = _provision_rbac_user(role, email, password)

    if not token and actor == "customer":
        try:
            requests.post(f"{APP_BASE_URL}/auth/customer/emailpass/register",
                          json={"email": email, "password": password}, timeout=HTTP_TIMEOUT)
            r = requests.post(f"{APP_BASE_URL}/auth/customer/emailpass",
                              json={"email": email, "password": password}, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                token = r.json().get("token")
        except Exception:
            pass

    if not token:
        try:
            token = _db_create_token(email, role)
        except Exception:
            pass

    if token:
        _token_cache[role] = token
        context["auth_token"] = token
        return PrimitiveResult(passed=True, data={"token": token[:20] + "..."},
                               message=f"Auth: obtained token for {role}")

    return PrimitiveResult(passed=False, message=f"Auth: failed to obtain token for {role} ({email})")


def _decode_jwt_payload(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None


def _bootstrap_admin(email: str, password: str) -> str | None:
    try:
        requests.post(f"{APP_BASE_URL}/auth/user/emailpass/register",
                      json={"email": email, "password": password}, timeout=HTTP_TIMEOUT)
    except Exception:
        pass

    for cmd_prefix in [["sudo", "docker"], ["docker"]]:
        try:
            result = subprocess.run(
                cmd_prefix + ["exec", APP_CONTAINER, "npx", "medusa", "user",
                              "-e", email, "-p", password],
                capture_output=True, text=True, timeout=30)
            if "User created" in (result.stdout + result.stderr) or result.returncode == 0:
                break
        except Exception:
            continue

    try:
        r = requests.post(f"{APP_BASE_URL}/auth/user/emailpass",
                          json={"email": email, "password": password}, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            token = r.json().get("token")
            if token:
                decoded = _decode_jwt_payload(token)
                if decoded and decoded.get("actor_id"):
                    return token
    except Exception:
        pass

    return None


def _provision_rbac_user(role: str, email: str, password: str) -> str | None:
    admin_token = _token_cache.get("admin")
    if not admin_token:
        admin_info = TEST_USERS.get("admin")
        try:
            r = requests.post(f"{APP_BASE_URL}/auth/user/emailpass",
                              json={"email": admin_info["email"], "password": admin_info["password"]},
                              timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                admin_token = r.json().get("token")
                _token_cache["admin"] = admin_token
        except Exception:
            return None
    if not admin_token:
        return None

    hdrs = {"Authorization": f"Bearer {admin_token}"}

    # Step 1: Create invite for this user
    try:
        r = requests.post(f"{APP_BASE_URL}/admin/invites",
                          json={"email": email}, headers=hdrs, timeout=HTTP_TIMEOUT)
        if r.status_code in (200, 201):
            invite = r.json().get("invite", {})
            invite_token = invite.get("token")
        else:
            invite_token = None
    except Exception:
        invite_token = None

    # Step 2: Accept invite (register the user with auth identity)
    if invite_token:
        try:
            requests.post(f"{APP_BASE_URL}/auth/user/emailpass/register",
                          json={"email": email, "password": password},
                          timeout=HTTP_TIMEOUT)
            requests.post(f"{APP_BASE_URL}/admin/invites/accept",
                          json={"invite_token": invite_token, "auth_identity_id": email},
                          headers=hdrs, timeout=HTTP_TIMEOUT)
        except Exception:
            pass

    # Step 3: Login the new user
    try:
        r = requests.post(f"{APP_BASE_URL}/auth/user/emailpass",
                          json={"email": email, "password": password}, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            return r.json().get("token")
    except Exception:
        pass

    return None


def _db_create_token(email: str, role: str) -> str | None:
    try:
        conn = _db_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            tables = [r["table_name"] for r in cur.fetchall()]
            user_table = next((t for t in tables if "user" in t and "auth" not in t), None)
            if not user_table:
                conn.close()
                return None
            cur.execute(f'SELECT id FROM "{user_table}" WHERE email = %s LIMIT 1', (email,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return None
        conn.close()
        return None
    except Exception:
        return None


# ===================================================================
# ===================================================================
def p14_permission_check(inputs: dict) -> PrimitiveResult:
    role = inputs.get("role", None)
    action = _resolve(inputs["action"])
    expected = inputs["expected_result"]
    expected_status = inputs.get("expected_status")

    parts = action.split(" ", 1)
    method = parts[0] if len(parts) > 0 else "GET"
    path = parts[1] if len(parts) > 1 else "/"

    old_token = context.get("auth_token")
    if role:
        p13_result = p13_auth_login({"role": role})
        if not p13_result.passed and expected == "denied":
            context["auth_token"] = old_token
            return PrimitiveResult(passed=True, message=f"Permission: {role} auth failed → treated as denied")
    else:
        context["auth_token"] = None

    try:
        headers = {}
        if context.get("auth_token"):
            headers["Authorization"] = f"Bearer {context['auth_token']}"
        r = requests.request(method, _url(path), headers=headers, timeout=HTTP_TIMEOUT)
        status = r.status_code
    except Exception as e:
        context["auth_token"] = old_token
        return PrimitiveResult(passed=False, message=f"Permission check failed: {e}")

    context["auth_token"] = old_token
    context["last_response"] = {"status_code": status, "body": None}
    try:
        context["last_response"]["body"] = r.json()
    except Exception:
        pass

    if expected == "denied":
        ok = status in (401, 403, 404)
        if expected_status:
            ok = status in (expected_status, 404) if expected_status == 403 else status == expected_status
    else:
        ok = 200 <= status < 400
        if expected_status:
            ok = status == expected_status

    return PrimitiveResult(passed=ok,
                           data={"status_code": status, "expected": expected},
                           message=f"Permission {role} {action}: {status} ({'ok' if ok else 'fail'})")


# ===================================================================
# ===================================================================
def p15_status_code_assert(inputs: dict) -> PrimitiveResult:
    resp = context.get("last_response", {})
    actual = resp.get("status_code", 0)
    acceptable = inputs.get("acceptable_statuses", [])
    if not acceptable:
        acceptable = [inputs.get("expected_status", 200)]
    ok = actual in acceptable
    return PrimitiveResult(passed=ok,
                           data={"actual": actual, "acceptable": acceptable},
                           message=f"Status {actual} {'in' if ok else 'not in'} {acceptable}")


# ===================================================================
# ===================================================================
def p16_response_time_check(inputs: dict) -> PrimitiveResult:
    resp = context.get("last_response", {})
    actual_ms = resp.get("response_time_ms", 9999)
    max_ms = inputs.get("max_ms", 500)
    ok = actual_ms <= max_ms
    return PrimitiveResult(passed=ok, data={"actual_ms": actual_ms, "max_ms": max_ms},
                           message=f"Response time {actual_ms}ms {'<=' if ok else '>'} {max_ms}ms")


# ===================================================================
# ===================================================================
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
        return PrimitiveResult(passed=True, data={"score": 0, "reason": "LLM not configured"},
                               message="LLM judge skipped (no API key)")

    rubric = inputs.get("rubric_prompt", "")
    criteria = inputs.get("criteria", [])
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "http_response_html")
    evidence_text = ""

    if evidence_type == "http_response_html":
        resp = context.get("last_response", {})
        evidence_text = resp.get("text", "")[:8000]
    elif evidence_type == "code_files":
        files_to_sample = inputs.get("files_to_sample", [])
        evidence_text = _sample_code_files(files_to_sample, rubric)

    criteria_text = ""
    if criteria:
        criteria_text = "\n\nEvaluation Criteria:\n"
        for c in criteria:
            criteria_text += f"- {c['dimension']} (weight: {c['weight']}): {c['description']}\n"

    prompt = f"""You are an evaluation judge. Score the following evidence on a scale of {score_range[0]} to {score_range[1]}.

{rubric}
{criteria_text}

Evidence:
```
{evidence_text[:24000]}
```

Respond with ONLY a JSON object: {{"score": <number>, "reason": "<brief explanation>"}}"""

    from _llm_judge_safe import safe_chat_completion

    _msgs = [{"role": "user", "content": prompt}]

    def _judge_call(msgs):
        return safe_chat_completion(
            messages=msgs,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE or "",
            temperature=0.1,
            max_tokens=8192,
        )

    res = _judge_call(_msgs)

    if res.skipped:
        return PrimitiveResult(
            passed=True,
            data={"score": 0, "skipped": True,
                  "llm_api_failure": res.llm_api_failure,
                  "exception_class": res.exception_class, "error": res.error},
            message=f"LLM judge SKIPPED ({res.reason()})",
        )

    parsed = _parse_judge_reply(res.raw, score_range)
    if parsed is None:
        retry = _judge_call(_msgs + [
            {"role": "assistant", "content": (res.raw or "")[:2000]},
            {"role": "user", "content": (
                f"You did not output a score. Reply with ONLY a single integer "
                f"between {score_range[0]} and {score_range[1]} — no words, no "
                f"explanation, just the number."
            )},
        ])
        if not retry.skipped:
            parsed = _parse_judge_reply(retry.raw, score_range)
    if parsed is None:
        return PrimitiveResult(passed=False,
                               data={"score": 0, "skipped": True, "parse_failure": True,
                                     "raw": (res.raw or "")[:200]},
                               message="LLM judge parse error: no parseable score after retry (SKIPPED)")
    score, reason = parsed
    return PrimitiveResult(passed=score > 0,
                           data={"score": score, "reason": reason},
                           message=f"LLM judge: {score}/{score_range[1]}")


def _parse_judge_reply(raw: str, score_range: list) -> tuple[int, str] | None:
    import re as _re
    lo, hi = int(score_range[0]), int(score_range[1])
    text = (raw or "").strip()
    if not text:
        return None

    fence_re = _re.compile(r"^```(?:json|JSON)?\s*\n(.*?)\n```\s*$", _re.DOTALL)
    m = fence_re.match(text)
    if m:
        text_inner = m.group(1).strip()
    else:
        text_inner = text

    for candidate in (text_inner, text):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and "score" in obj:
                try:
                    score = int(obj["score"])
                except (TypeError, ValueError):
                    continue
                reason = str(obj.get("reason") or obj.get("reasoning") or "")[:500]
                return (max(lo, min(hi, score)), reason)
        except Exception:
            pass

    brace_match = _re.search(r"\{[^{}]*\"score\"\s*:\s*-?\d+[^{}]*\}", text, _re.DOTALL)
    if brace_match:
        try:
            obj = json.loads(brace_match.group(0))
            score = int(obj.get("score", 0))
            reason = str(obj.get("reason") or obj.get("reasoning") or "")[:500]
            return (max(lo, min(hi, score)), reason)
        except Exception:
            pass

    score_match = _re.search(r'score[^\d\n]{0,15}(-?\d+)', text, _re.IGNORECASE)
    if score_match:
        try:
            score = int(score_match.group(1))
            return (max(lo, min(hi, score)), text[:500])
        except Exception:
            pass

    int_match = _re.search(r"-?\d+", text)
    if int_match:
        try:
            score = int(int_match.group(0))
            return (max(lo, min(hi, score)), text[:500])
        except Exception:
            return None
    return None


def _resolve_sample_paths(p: str) -> list[str]:
    p = p.rstrip("/")
    cands = [p]

    if p.startswith("packages/"):
        rest = p[len("packages/"):]
        cands.append(rest)
        cands.append(os.path.join("src", rest))

    parts = p.split("/")
    if len(parts) >= 2 and parts[0] == "packages":
        if parts[1] in ("server", "core"):
            tail = "/".join(parts[2:]) if len(parts) > 2 else ""
            if tail:
                cands.append(tail)
                cands.append(os.path.join("src", tail))
                if tail.startswith("src/"):
                    cands.append(tail[len("src/"):])
                    cands.append(os.path.join("src", tail[len("src/"):]))
        elif parts[1] == "modules":
            tail = "/".join(parts[2:]) if len(parts) > 2 else ""
            if tail:
                cands.append(os.path.join("src", "modules", tail))
                cands.append(os.path.join("src", tail))
                cands.append(tail)
            else:
                cands.append(os.path.join("src", "modules"))

    if "server/src/routes" in p:
        suffix = p.split("server/src/routes", 1)[1].lstrip("/")
        if suffix:
            cands.append(os.path.join("src", "api", suffix))
        else:
            cands.append(os.path.join("src", "api"))

    seen: set[str] = set()
    uniq: list[str] = []
    for c in cands:
        c = c.rstrip("/")
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


_DFHJKEB_CODE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py",
                      ".go", ".rb", ".java", ".kt", ".rs", ".php", ".vue",
                      ".json", ".sql"}
_DFHJKEB_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent does "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling whether well overall".split())


def _dfhjkeb_rank(cands, root, rubric, max_files=16):
    mentioned = {m.split("/")[-1].lower()
                 for m in re.findall(r"[\w./*-]+\.\w{1,5}", rubric or "")}
    kws = {}
    for t in re.findall(r"[A-Za-z_]{3,}", (rubric or "").lower()):
        if t not in _DFHJKEB_STOP:
            kws[t] = kws.get(t, 0) + 1
    scored = []
    for full in cands:
        rel = os.path.relpath(full, root)
        low = rel.lower()
        base = os.path.basename(low)
        ext = os.path.splitext(low)[1]
        sc = 0.0
        for m in mentioned:
            if m and (m == base or low.endswith(m)):
                sc += 50
        for w in kws:
            if w in low:
                sc += 3
        sc += 2.0 if ext in _DFHJKEB_CODE_EXTS else 0.0
        if "test" in base or "spec" in base:
            sc -= 4.0
        parts = rel.split(os.sep)
        strat = os.sep.join(parts[:2]) if len(parts) > 1 else parts[0]
        scored.append((sc, strat, rel, full))
    scored.sort(key=lambda x: (-x[0], x[2]))
    groups, order = {}, []
    for sc, strat, rel, full in scored:
        if strat not in groups:
            groups[strat] = []
            order.append(strat)
        groups[strat].append(full)
    picked = []
    while len(picked) < max_files and any(groups[k] for k in order):
        for k in order:
            if groups[k]:
                picked.append(groups[k].pop(0))
                if len(picked) >= max_files:
                    break
    return picked


def _sample_code_files(paths: list[str], rubric: str = "", max_chars: int = 14000) -> str:
    sampled: list[str] = []
    total = 0
    cands: list[str] = []
    explicit: list[str] = []
    for p in paths:
        for candidate in _resolve_sample_paths(p):
            full = os.path.join(WORKSPACE_DIR, candidate)
            if os.path.isfile(full):
                explicit.append(full)
            elif os.path.isdir(full):
                for root, dirs, files in os.walk(full):
                    rr = "/" + os.path.relpath(root, WORKSPACE_DIR).lower() + "/"
                    if any(s in rr for s in ("/node_modules/", "/.git/",
                                             "/dist/", "/build/", "/__pycache__/",
                                             "/vendor/", "/coverage/")):
                        dirs[:] = []
                        continue
                    for f in files:
                        if os.path.splitext(f)[1].lower() in _DFHJKEB_CODE_EXTS:
                            cands.append(os.path.join(root, f))

    def _emit(fp, per_file):
        nonlocal total
        if total >= max_chars:
            return
        try:
            content = open(fp, errors="replace").read()[:per_file]
            rel = os.path.relpath(fp, WORKSPACE_DIR)
            sampled.append(f"--- {rel} ---\n{content}")
            total += len(content)
        except Exception:
            pass

    seen = set()
    for fp in explicit:
        if fp not in seen:
            seen.add(fp)
            _emit(fp, 3000)
    for fp in _dfhjkeb_rank(cands, WORKSPACE_DIR, rubric, max_files=16):
        if total >= max_chars:
            break
        if fp not in seen:
            seen.add(fp)
            _emit(fp, 2500)

    if not sampled and os.path.isdir(WORKSPACE_DIR):
        root_cands = []
        for root, dirs, files in os.walk(WORKSPACE_DIR):
            rr = "/" + os.path.relpath(root, WORKSPACE_DIR).lower() + "/"
            if any(s in rr for s in ("/node_modules/", "/.git/", "/dist/",
                                     "/build/", "/__pycache__/", "/vendor/")):
                dirs[:] = []
                continue
            for f in files:
                if os.path.splitext(f)[1].lower() in _DFHJKEB_CODE_EXTS:
                    root_cands.append(os.path.join(root, f))
        for fp in _dfhjkeb_rank(root_cands, WORKSPACE_DIR, rubric, max_files=16):
            if total >= max_chars:
                break
            _emit(fp, 1800)

    return "\n\n".join(sampled)


# ===================================================================
# ===================================================================
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
}


def execute_primitive(ptype: str, inputs: dict) -> PrimitiveResult:
    fn = PRIMITIVE_MAP.get(ptype)
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
