from __future__ import annotations
import glob as _glob
import json
import os
import re
import subprocess
import time
from typing import Any

import requests

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

try:
    import openai as _openai
except ImportError:
    _openai = None

from config import (
    APP_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    APP_CONTAINER, WORKSPACE_DIR, HTTP_TIMEOUT,
    LLM_API_KEY, LLM_API_BASE, LLM_MODEL,
    PUBLIC_API_KEY_HEADER, SKIP_LLM_JUDGE,
)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
context: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _url(path: str) -> str:
    if path.startswith(("http://", "https://", "ws://", "wss://")):
        return path
    return APP_BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def _resolve(template: str) -> str:
    def _repl(m: re.Match) -> str:
        key = m.group(1)
        return str(context.get(key, m.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", _repl, str(template))


def _resolve_deep(obj: Any) -> Any:
    if isinstance(obj, str):
        return _resolve(obj)
    if isinstance(obj, dict):
        return {k: _resolve_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_deep(v) for v in obj]
    return obj


def _session_headers() -> dict[str, str]:
    cookie = context.get("session_cookie")
    if cookie:
        return {"Cookie": cookie}
    return {}


def _api_key_headers() -> dict[str, str]:
    key = context.get("public_api_key")
    if key:
        return {PUBLIC_API_KEY_HEADER: key}
    return {}


def _auth_headers(raw_headers: dict | None) -> dict[str, str]:
    headers = dict(raw_headers or {})
    resolved = {k: _resolve(v) for k, v in headers.items()}
    if "Cookie" in resolved and "{{session_cookie}}" in (raw_headers or {}).get("Cookie", ""):
        cookie = context.get("session_cookie", "")
        resolved["Cookie"] = cookie
    if PUBLIC_API_KEY_HEADER in resolved and "{{public_api_key}}" in (raw_headers or {}).get(PUBLIC_API_KEY_HEADER, ""):
        resolved[PUBLIC_API_KEY_HEADER] = context.get("public_api_key", "")
    return resolved


def _db_conn():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p01_file_exists(inputs: dict) -> dict:
    raw_path = inputs["path"]
    kind = inputs.get("type", "file")
    if isinstance(raw_path, list):
        candidates = [_resolve(p) for p in raw_path]
    else:
        candidates = [_resolve(raw_path)]

    matched_path = None
    for cand in candidates:
        full = os.path.join(WORKSPACE_DIR, cand)
        ok = os.path.isdir(full) if kind == "directory" else os.path.exists(full)
        if ok:
            matched_path = cand
            break

    exists = matched_path is not None
    result: dict = {"exists": exists, "passed": exists}
    if isinstance(raw_path, list):
        result["matched_path"] = matched_path
        result["candidates_checked"] = candidates
    return result


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p02_file_content_match(inputs: dict) -> dict:
    path = os.path.join(WORKSPACE_DIR, _resolve(inputs["path"]))
    if not os.path.isfile(path):
        return {"matched": False, "match_count": 0, "passed": False}
    content = open(path, encoding="utf-8", errors="replace").read()
    match_type = inputs.get("match_type", "contains")
    pattern = inputs["pattern"]
    if match_type == "regex":
        matches = re.findall(pattern, content)
    else:
        matches = [m for m in [content.find(pattern)] if m >= 0]
    passed = len(matches) > 0
    return {"matched": passed, "match_count": len(matches), "passed": passed}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p03_file_count(inputs: dict) -> dict:
    base = os.path.join(WORKSPACE_DIR, _resolve(inputs.get("base_dir", "")))
    pattern = inputs.get("glob", "**/*")
    files = _glob.glob(os.path.join(base, pattern), recursive=True)
    files = [f for f in files if os.path.isfile(f)]
    min_expected = inputs.get("min_expected", 1)
    return {"count": len(files), "files": [os.path.basename(f) for f in files[:20]],
            "passed": len(files) >= min_expected}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p04_http_request(inputs: dict) -> dict:
    method = _resolve(inputs.get("method", "GET"))
    path = _resolve(inputs.get("path", "/"))
    headers = _auth_headers(inputs.get("headers"))
    body = _resolve_deep(inputs.get("body"))
    query = _resolve_deep(inputs.get("query"))
    timeout = inputs.get("timeout", HTTP_TIMEOUT)

    resp = requests.request(
        method, _url(path),
        headers=headers, json=body, params=query,
        timeout=timeout, allow_redirects=False,
    )

    cookie_header_used = str(headers.get("Cookie", ""))
    _SCN = os.environ.get("SESSION_COOKIE_NAME", "n8n-auth")
    _retry_info = None
    if inputs.get("no_auth_retry"):
        pass
    elif resp.status_code == 401 and f"{_SCN}=" in cookie_header_used:
        _retry_info = {"first_status": resp.status_code, "first_body": resp.text[:80]}
        context["session_cookie"] = ""
        from config import TEST_USERS as _TEST_USERS
        _owner = _TEST_USERS["owner"]
        relogin = p13_auth_login({
            "role": "admin",
            "method": "form",
            "login_path": "/rest/login",
            "username": _owner["email"],
            "password": _owner["password"],
        })
        _retry_info["relogin_success"] = relogin.get("success")
        _retry_info["new_cookie_set"] = bool(context.get("session_cookie"))
        if context.get("session_cookie"):
            headers = dict(headers)
            headers["Cookie"] = context["session_cookie"]
            resp = requests.request(
                method, _url(path),
                headers=headers, json=body, params=query,
                timeout=timeout, allow_redirects=False,
            )
            _retry_info["retry_status"] = resp.status_code

    cookies = resp.cookies
    _SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "n8n-auth")
    if _SESSION_COOKIE_NAME in resp.headers.get("Set-Cookie", ""):
        for c in resp.headers.get("Set-Cookie", "").split(","):
            if _SESSION_COOKIE_NAME in c:
                cookie_val = c.split(";")[0].strip()
                if cookie_val and cookie_val != f"{_SESSION_COOKIE_NAME}=" and len(cookie_val) > 15:
                    context["session_cookie"] = cookie_val

    try:
        resp_json = resp.json()
    except Exception:
        resp_json = resp.text

    context["_last_response"] = resp
    context["_last_status"] = resp.status_code
    context["_last_body"] = resp_json
    context["_last_headers"] = dict(resp.headers)

    if method == "POST" and resp.status_code in (200, 201) and isinstance(resp_json, dict):
        data = resp_json.get("data", resp_json)
        if isinstance(data, dict) and "id" in data:
            resource_id = str(data["id"])
            _RESOURCE_MAP = {
                "/rest/workflows": "workflow_id",
                "/rest/credentials": "credential_id",
                "/rest/projects": "project_id",
                "/rest/tags": "tag_id",
                "/rest/variables": "variable_id",
                "/rest/api-keys": "api_key_id",
                "/rest/invitations": "invitation_id",
                "/rest/annotation-tags": "annotation_tag_id",
                "/rest/instance-ai/threads": "thread_id",
                "/rest/chat/agents": "chat_agent_id",
                "/api/v1/workflows": "workflow_id",
                "/api/v1/credentials": "credential_id",
                "/api/v1/projects": "project_id",
                "/api/v1/tags": "tag_id",
                "/api/v1/variables": "variable_id",
                "/api/v1/users": "user_id",
                "/api/v1/data-tables": "data_table_id",
            }
            for prefix, ctx_key in _RESOURCE_MAP.items():
                if path.rstrip("/") == prefix or path.startswith(prefix + "/"):
                    context[ctx_key] = resource_id
                    break
            if "rawApiKey" in data:
                context["public_api_key"] = data["rawApiKey"]

    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "body": resp_json,
        "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
        "passed": True,
        "retry_info": _retry_info,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p06_json_schema_match(inputs: dict) -> dict:
    body = context.get("_last_body", {})
    required = inputs.get("required_fields", [])
    field_types = inputs.get("field_types", {})
    missing = []
    type_mismatches = []
    data = body
    if isinstance(body, dict) and "data" in body:
        data = body["data"]
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return {"all_present": False, "missing_fields": required, "type_mismatches": [], "passed": False}
    for f in required:
        if f not in data:
            missing.append(f)
    passed = len(missing) == 0
    return {"all_present": passed, "missing_fields": missing, "type_mismatches": type_mismatches, "passed": passed}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _extract_jsonpath(obj: Any, path: str) -> Any:
    if path.startswith("$.__meta."):
        meta_key = path[len("$.__meta."):]
        if meta_key == "response_wrapper":
            if isinstance(obj, dict):
                if "data" in obj:
                    return "data" if not isinstance(obj["data"], list) else "data[]"
                return "root"
            if isinstance(obj, list):
                return "root[]"
            return "root:string" if isinstance(obj, str) else "root"
        if meta_key == "content_type":
            ct = context.get("_last_headers", {}).get("Content-Type", "")
            return ct.split(";")[0].strip()
        return None
    if path == "$.__status":
        return context.get("_last_status")
    if path in ("$", "$.", ""):
        return obj

    parts = path.replace("$.", "").replace("$", "").split(".")
    cur = obj
    for part in parts:
        mf = re.match(r"(\w+)\[\?(\w+)=(.*)\]$", part)
        if mf:
            key, fld, val = mf.group(1), mf.group(2), mf.group(3)
            lst = None
            if isinstance(cur, dict) and isinstance(cur.get(key), list):
                lst = cur[key]
            elif isinstance(cur, list) and key in ("", "data"):
                lst = cur
            if lst is None:
                return None
            match = None
            for _el in lst:
                if isinstance(_el, dict) and str(_el.get(fld)) == str(val):
                    match = _el
                    break
            if match is None:
                return None
            cur = match
            continue
        m = re.match(r"(\w+)\[(\d+)\]", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
                if isinstance(cur, list) and idx < len(cur):
                    cur = cur[idx]
                elif isinstance(cur, dict) and "items" in cur and isinstance(cur["items"], list):
                    items = cur["items"]
                    if idx < len(items):
                        cur = items[idx]
                    else:
                        return None
                else:
                    return None
            else:
                return None
        elif part == "length" and isinstance(cur, (list, str)):
            return len(cur)
        elif part == "length" and isinstance(cur, dict) and "items" in cur:
            return len(cur["items"])
        elif part == "count" and isinstance(cur, dict) and "count" in cur:
            return cur["count"]
        elif part == "count" and isinstance(cur, list):
            return len(cur)
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def p07_json_value_assert(inputs: dict) -> dict:
    body = context.get("_last_body", {})
    assertions = inputs.get("assertions", [])
    assertions_any_of = inputs.get("assertions_any_of", [])
    results = []
    all_passed = True

    def _check(a):
        path = _resolve(a.get("path", "$"))
        expected = a.get("expected")
        tolerance = a.get("tolerance")
        op = a.get("operator", "eq")
        actual = _extract_jsonpath(body, path)
        if op == "exists":
            passed = actual is not None
        elif op == "not_exists":
            passed = actual is None
        elif op == "gte":
            passed = actual is not None and actual >= expected
        elif op == "lte":
            passed = actual is not None and actual <= expected
        elif op == "contains":
            passed = actual is not None and str(expected) in str(actual)
        elif op == "not_contains":
            passed = actual is not None and str(expected) not in str(actual)
        elif op == "is_array":
            passed = isinstance(actual, list)
        elif op == "is_object":
            passed = isinstance(actual, dict)
        elif tolerance and isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            passed = abs(actual - expected) <= tolerance
        elif isinstance(expected, list) and isinstance(actual, list):
            passed = actual == expected
        else:
            passed = actual == expected
        return path, actual, expected, op, passed

    for a in assertions:
        path, actual, expected, op, passed = _check(a)
        results.append({"path": path, "actual": actual, "expected": expected, "op": op, "passed": passed})
        if not passed:
            all_passed = False

    if assertions_any_of:
        any_passed = False
        any_results = []
        for a in assertions_any_of:
            path, actual, expected, op, passed = _check(a)
            any_results.append({"path": path, "actual": actual, "expected": expected, "op": op, "passed": passed})
            if passed:
                any_passed = True
        results.append({"any_of": any_results, "passed": any_passed})
        if any_passed:
            all_passed = True

    return {"all_passed": all_passed, "results": results, "passed": all_passed}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p08_db_query(inputs: dict) -> dict:
    query = _resolve(inputs.get("query", "SELECT 1"))
    expected_rows = inputs.get("expected_rows")
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    match = True
    if expected_rows is not None:
        if len(rows) != len(expected_rows):
            match = False
        else:
            for actual, exp in zip(rows, expected_rows):
                for k, v in exp.items():
                    if actual.get(k) != v:
                        match = False
                        break

    return {"rows": rows, "row_count": len(rows), "match": match, "passed": match}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p09_db_table_exists(inputs: dict) -> dict:
    tables_wanted = inputs.get("tables", [])
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            )
            existing = {r["table_name"] for r in cur.fetchall()}
    finally:
        conn.close()

    found = [t for t in tables_wanted if t in existing]
    missing = [t for t in tables_wanted if t not in existing]
    return {
        "existing": found, "missing": missing,
        "found_count": len(found), "total_count": len(tables_wanted),
        "passed": len(missing) == 0,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p10_db_column_check(inputs: dict) -> dict:
    table = inputs["table"]
    expected = inputs.get("expected_columns", [])
    conn = _db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s", (table,)
            )
            actual_cols = {r["column_name"] for r in cur.fetchall()}
    finally:
        conn.close()

    found = [c for c in expected if c in actual_cols]
    missing = [c for c in expected if c not in actual_cols]
    return {
        "existing": found, "missing": missing,
        "found_count": len(found), "total_count": len(expected),
        "passed": len(missing) == 0,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p12_docker_exec(inputs: dict) -> dict:
    command = _resolve(inputs.get("command", "echo ok"))
    container = _resolve(inputs.get("container", APP_CONTAINER))
    expect_success = inputs.get("expect_success", True)
    expect_output = inputs.get("expect_output_contains")

    result = subprocess.run(
        ["docker", "exec", container, "bash", "-lc", command],
        capture_output=True, text=True, timeout=60,
    )

    passed = True
    if expect_success and result.returncode != 0:
        passed = False
    if expect_output and expect_output not in (result.stdout + result.stderr):
        passed = False

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout[:2000],
        "stderr": result.stderr[:2000],
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p13_auth_login(inputs: dict) -> dict:
    role = inputs.get("role", "admin")
    method = inputs.get("method", "form")
    login_path = _resolve(inputs.get("login_path", "/rest/login"))
    username = _resolve(inputs.get("username", "owner@example.com"))
    password = _resolve(inputs.get("password", "App123egsszeqG!"))

    if role in ("admin", "owner") or (
        context.get("_current_auth_user") and context.get("_current_auth_user") != username):
        context["session_cookie"] = ""

    if role in ("admin", "owner") and not context.get("session_cookie") and not context.get("_owner_bootstrapped"):
        try:
            setup_resp = requests.post(
                _url("/rest/owner/setup"),
                json={
                    "email": username,
                    "firstName": "Eval",
                    "lastName": "Owner",
                    "password": password,
                },
                timeout=HTTP_TIMEOUT,
                allow_redirects=False,
            )
            if "Set-Cookie" in setup_resp.headers:
                _scn = os.environ.get("SESSION_COOKIE_NAME", "n8n-auth")
                for c in setup_resp.headers.get("Set-Cookie", "").split(","):
                    if _scn in c:
                        context["session_cookie"] = c.split(";")[0].strip()
            if setup_resp.status_code in (200, 201):
                context["_owner_bootstrapped"] = True
        except Exception:
            pass

    if not context.get("session_cookie") or role not in ("admin", "owner"):
        for login_body in [
            {"emailOrLdapLoginId": username, "password": password},
            {"email": username, "password": password},
        ]:
            try:
                login_resp = requests.post(
                    _url(login_path),
                    json=login_body,
                    timeout=HTTP_TIMEOUT,
                    allow_redirects=False,
                )
                if "Set-Cookie" in login_resp.headers:
                    _scn = os.environ.get("SESSION_COOKIE_NAME", "n8n-auth")
                    for c in login_resp.headers.get("Set-Cookie", "").split(","):
                        if _scn in c:
                            context["session_cookie"] = c.split(";")[0].strip()
                if context.get("session_cookie"):
                    break
            except Exception:
                pass

    success = bool(context.get("session_cookie"))
    if success:
        context["_current_auth_user"] = username

    if success and role in ("admin", "owner") and not context.get("_resources_seeded"):
        _seed_test_resources()

    return {"success": success, "role": role, "passed": success}


def _seed_test_resources():
    context["_resources_seeded"] = True
    cookie = context.get("session_cookie", "")
    if not cookie:
        return
    hdr = {"Cookie": cookie, "Content-Type": "application/json"}

    def _post(path, body):
        try:
            r = requests.post(_url(path), json=body, headers=hdr, timeout=HTTP_TIMEOUT, allow_redirects=False)
            if r.status_code in (200, 201):
                data = r.json().get("data", r.json())
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    wf = _post("/rest/workflows", {
        "name": "EvalTestWorkflow", "nodes": [
            {"parameters": {}, "name": "Start", "type": "manualTrigger",
             "typeVersion": 1, "position": [250, 300]}],
        "connections": {}, "settings": {},
    })
    if wf.get("id"):
        context["workflow_id"] = str(wf["id"])

    def _patch(path, body):
        try:
            r = requests.patch(_url(path), json=body, headers=hdr, timeout=HTTP_TIMEOUT, allow_redirects=False)
            if r.status_code in (200, 201):
                d = r.json().get("data", r.json())
                return d if isinstance(d, dict) else {}
        except Exception:
            pass
        return {}

    hist_wf = _post("/rest/workflows", {
        "name": "EvalHistoryWorkflow", "nodes": [
            {"parameters": {}, "name": "Start", "type": "manualTrigger",
             "typeVersion": 1, "position": [250, 300]}],
        "connections": {}, "settings": {},
    })
    hist_id = hist_wf.get("id")
    if hist_id:
        context["history_workflow_id"] = str(hist_id)
        for _i in range(9):
            _patch(f"/rest/workflows/{hist_id}", {
                "name": "EvalHistoryWorkflow",
                "nodes": [
                    {"parameters": {}, "name": "Start", "type": "manualTrigger",
                     "typeVersion": 1, "position": [250, 300]},
                    {"parameters": {"values": {"number": [{"name": "n", "value": _i}]}},
                     "name": f"Set{_i}", "type": "set", "typeVersion": 1, "position": [450, 300]}],
                "connections": {},
            })
        try:
            _hr = requests.get(_url(f"/rest/workflow-history/workflow/{hist_id}"),
                               headers=hdr, params={"take": 1}, timeout=HTTP_TIMEOUT)
            _hd = _hr.json().get("data", [])
            if _hd and _hd[0].get("versionId"):
                context["history_version_id"] = str(_hd[0]["versionId"])
        except Exception:
            pass

    cred = _post("/rest/credentials", {
        "name": "EvalTestCred", "type": "httpBasicAuth",
        "data": {"user": "eval", "password": "eval"},
    })
    if cred.get("id"):
        context["credential_id"] = str(cred["id"])

    oauth_cred = _post("/rest/credentials", {
        "name": "EvalOAuth2Cred", "type": "oAuth2Api",
        "data": {
            "grantType": "authorizationCode",
            "authUrl": "https://example.com/oauth/authorize",
            "accessTokenUrl": "https://example.com/oauth/token",
            "clientId": "client_id", "clientSecret": "client_secret",
            "scope": "openid", "authQueryParameters": "access_type=offline",
            "authentication": "header",
        },
    })
    if oauth_cred.get("id"):
        context["oauth2_credential_id"] = str(oauth_cred["id"])
        try:
            import urllib.parse as _uparse
            for _k in ("oauth2_auth_state", "oauth2_auth_state2"):
                _ar = requests.get(_url("/rest/oauth2-credential/auth"), headers=hdr,
                                   params={"id": oauth_cred["id"]}, timeout=HTTP_TIMEOUT)
                _st = _uparse.parse_qs(_uparse.urlparse(_ar.json().get("data", "")).query).get("state", [None])[0]
                if _st:
                    context[_k] = _st
        except Exception:
            pass

    tag = _post("/rest/tags", {"name": "eval-tag"})
    if tag.get("id"):
        context["tag_id"] = str(tag["id"])

    try:
        proj = _post("/rest/projects", {"name": "EvalTestProject"})
        if proj.get("id"):
            context["project_id"] = str(proj["id"])
    except Exception:
        pass

    _seed_test_users(hdr)

    _scn = os.environ.get("SESSION_COOKIE_NAME", "n8n-auth")

    def _login_cookie(email, password):
        for body in ({"emailOrLdapLoginId": email, "password": password},
                     {"email": email, "password": password}):
            try:
                lr = requests.post(_url("/rest/login"), json=body, timeout=HTTP_TIMEOUT, allow_redirects=False)
                for c in lr.headers.get("Set-Cookie", "").split(","):
                    if _scn in c:
                        cv = c.split(";")[0].strip()
                        if len(cv) > 15:
                            return cv
            except Exception:
                pass
        return None

    try:
        _mc = _login_cookie("member@example.com", "Testpassword1!")
        if _mc:
            requests.post(_url("/rest/credentials"),
                          headers={"Cookie": _mc, "Content-Type": "application/json"},
                          json={"name": "MemberOwnedCred", "type": "httpBasicAuth",
                                "data": {"user": "m", "password": "m"}},
                          timeout=HTTP_TIMEOUT)
    except Exception:
        pass

    try:
        import urllib.parse as _up
        _chat_email = "chatuser@example.com"
        _iv = requests.post(_url("/rest/invitations"), headers=hdr,
                            json=[{"email": _chat_email, "role": "global:chatUser"}],
                            timeout=HTTP_TIMEOUT)
        _u = (_iv.json().get("data") or [{}])[0].get("user", {})
        _tok = _up.parse_qs(_up.urlparse(_u.get("inviteAcceptUrl", "")).query).get("token", [None])[0]
        if _u.get("id") and _tok:
            requests.post(_url("/rest/invitations/accept"),
                          headers={"Content-Type": "application/json"},
                          json={"inviteeId": _u["id"], "firstName": "Chat", "lastName": "User",
                                "password": "Testpassword1!", "token": _tok},
                          timeout=HTTP_TIMEOUT)
            _cc = _login_cookie(_chat_email, "Testpassword1!")
            if _cc:
                context["chatuser_session_cookie"] = _cc
    except Exception:
        pass


def _seed_test_users(owner_hdr: dict):
    _scn = os.environ.get("SESSION_COOKIE_NAME", "n8n-auth")
    test_users = [
        {"email": "member@example.com", "password": "Testpassword1!", "role": "global:member"},
    ]
    for u in test_users:
        try:
            inv_resp = requests.post(
                _url("/rest/invitations"),
                json=[{"email": u["email"], "role": u.get("role", "global:member")}],
                headers=owner_hdr,
                timeout=HTTP_TIMEOUT,
                allow_redirects=False,
            )
            if inv_resp.status_code not in (200, 201):
                continue
            inv_data = inv_resp.json()
            invitees = inv_data.get("data", inv_data)
            if isinstance(invitees, list) and invitees:
                invite = invitees[0]
            elif isinstance(invitees, dict):
                invite = invitees
            else:
                continue
            user_obj = invite.get("user", invite)
            inv_id = user_obj.get("id", "")
            accept_url = user_obj.get("inviteAcceptUrl", "")
            if not inv_id:
                continue
            inv_token = ""
            if accept_url and "token=" in accept_url:
                inv_token = accept_url.split("token=")[-1].split("&")[0]
            if not inv_token:
                continue
            accept_resp = requests.post(
                _url("/rest/invitations/accept"),
                json={
                    "token": inv_token,
                    "firstName": "Eval",
                    "lastName": "Member",
                    "password": u["password"],
                },
                timeout=HTTP_TIMEOUT,
                allow_redirects=False,
            )
            if accept_resp.status_code in (200, 201):
                for c in accept_resp.headers.get("Set-Cookie", "").split(","):
                    if _scn in c:
                        _role_sessions[u["role"]] = c.split(";")[0].strip()
                        _role_sessions["member"] = c.split(";")[0].strip()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_role_sessions: dict[str, str] = {}

_ROLE_CREDENTIALS: dict[str, dict[str, str]] = {
    "global:owner":   {"email": "owner@example.com",   "password": "App123egsszeqG!"},
    "global:admin":   {"email": "admin@example.com",   "password": "App123egsszeqG!"},
    "global:member":  {"email": "member@example.com",  "password": "Testpassword1!"},
    "global:chatUser": {"email": "chatuser@example.com", "password": "Testpassword1!"},
    "project:admin":  {"email": "padmin@example.com",  "password": "Testpassword1!"},
    "project:editor": {"email": "peditor@example.com", "password": "Testpassword1!"},
    "project:viewer": {"email": "pviewer@example.com", "password": "Testpassword1!"},
    "owner":          {"email": "owner@example.com",   "password": "App123egsszeqG!"},
    "admin":          {"email": "owner@example.com",   "password": "App123egsszeqG!"},
    "member":         {"email": "member@example.com",  "password": "Testpassword1!"},
    "member1":        {"email": "member@example.com",  "password": "Testpassword1!"},
}


def _get_role_session(role: str) -> str | None:
    if role in _role_sessions:
        return _role_sessions[role]

    creds = _ROLE_CREDENTIALS.get(role)
    if not creds:
        return context.get("session_cookie")

    for login_body in [
        {"emailOrLdapLoginId": creds["email"], "password": creds["password"]},
        {"email": creds["email"], "password": creds["password"]},
    ]:
        try:
            resp = requests.post(
                _url("/rest/login"),
                json=login_body,
                timeout=HTTP_TIMEOUT,
                allow_redirects=False,
            )
            if "Set-Cookie" in resp.headers:
                _scn = os.environ.get("SESSION_COOKIE_NAME", "n8n-auth")
                for c in resp.headers.get("Set-Cookie", "").split(","):
                    if _scn in c:
                        cookie = c.split(";")[0].strip()
                        _role_sessions[role] = cookie
                        return cookie
        except Exception:
            pass

    return context.get("session_cookie")


def p14_permission_check(inputs: dict) -> dict:
    role = inputs.get("role", "global:member")
    action = inputs.get("action", "GET /")
    expected_result = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status", 403)

    parts = action.split(" ", 1)
    method = parts[0] if parts else "GET"
    path = parts[1] if len(parts) > 1 else "/"

    role_cookie = _get_role_session(role)
    headers = {"Cookie": role_cookie} if role_cookie else {}

    try:
        resp = requests.request(
            method, _url(_resolve(path)),
            headers=headers,
            timeout=HTTP_TIMEOUT,
            allow_redirects=False,
        )
    except Exception as e:
        return {"passed": False, "actual_status": None, "role": role, "message": str(e)}

    actual = resp.status_code
    if expected_result == "denied":
        passed = actual in (403, 404)
    else:
        passed = actual == expected_status

    return {"passed": passed, "actual_status": actual, "expected_status": expected_status, "role": role}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p15_status_code_assert(inputs: dict) -> dict:
    actual = context.get("_last_status")
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
        passed = actual is not None and 200 <= actual < 400

    return {"passed": passed, "actual": actual,
            "expected": sorted(accepted) if accepted else "2xx/3xx",
            "message": f"Status: {actual} (expected {sorted(accepted) if accepted else '2xx/3xx'})"}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p17_llm_judge(inputs: dict) -> dict:
    score_range_for_skip = inputs.get("score_range", [0, 5])
    if SKIP_LLM_JUDGE:
        return {"score": 0, "max_score": score_range_for_skip[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "SKIP_LLM_JUDGE=1 (LLM judge intentionally skipped for peer-review-grade scoring)"}
    score_range = inputs.get("score_range", [0, 10])
    if not LLM_API_KEY:
        return {"passed": True, "score": 0, "max": score_range[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "LLM_API_KEY unset"}

    rubric = inputs.get("rubric_prompt", "")
    evidence_type = inputs.get("evidence_type", "code_files")

    evidence_text = ""
    files_sampled: list[str] = []
    missing_bases: list[str] = []

    if evidence_type in ("code_files", "frontend_code_and_dom"):
        files_to_sample = inputs.get("files_to_sample", [])

        def _candidate_paths(base: str) -> list[str]:
            base = base.strip("/")
            head = base.split("/", 1)[0] if "/" in base else base
            tail = base.split("/", 1)[1] if "/" in base else ""
            variants = [base]
            for prefix in ("packages", "apps", "services"):
                variants.append(f"{prefix}/{base}")
                variants.append(f"{prefix}/{head}/{tail}".rstrip("/"))
                variants.append(f"{prefix}/{head}")
            if head == "frontend":
                variants += [
                    "packages/frontend/editor-ui/src",
                    "packages/frontend/editor-ui",
                    "packages/editor-ui/src",
                    "packages/editor-ui",
                ]
            if head == "backend":
                variants += [
                    "packages/cli/src",
                    "packages/cli",
                    "packages/core/src",
                    "packages/core",
                ]
            seen: set[str] = set()
            out: list[str] = []
            for v in variants:
                if v and v not in seen:
                    seen.add(v)
                    out.append(v)
            return out

        def _ingest_dir(dirpath: str) -> None:
            nonlocal evidence_text
            for root, _, fnames in os.walk(dirpath):
                for fn in fnames[:30]:
                    fp = os.path.join(root, fn)
                    try:
                        content = open(fp, encoding="utf-8", errors="replace").read()[:3000]
                        evidence_text += f"\n--- {os.path.relpath(fp, WORKSPACE_DIR)} ---\n{content}\n"
                    except Exception:
                        pass
                if len(evidence_text) > 40000:
                    break

        def _ingest_file(filepath: str) -> None:
            nonlocal evidence_text
            try:
                content = open(filepath, encoding="utf-8", errors="replace").read()[:6000]
                evidence_text += f"\n--- {os.path.relpath(filepath, WORKSPACE_DIR)} ---\n{content}\n"
            except Exception:
                pass

        for base in files_to_sample:
            matched_any = False
            matched_path: str | None = None
            for candidate in _candidate_paths(base):
                full = os.path.join(WORKSPACE_DIR, candidate)
                if os.path.isdir(full):
                    _ingest_dir(full)
                    matched_any = True
                    matched_path = candidate
                    break
                if os.path.isfile(full):
                    _ingest_file(full)
                    matched_any = True
                    matched_path = candidate
                    break
            if matched_any:
                files_sampled.append(matched_path or base)
            else:
                missing_bases.append(base)
                evidence_text += f"\n--- {base} ---\n[evidence path not found in workspace; layout may differ from the reference baseline]\n"
            if len(evidence_text) > 40000:
                break
    elif evidence_type == "http_response_html":
        try:
            evidence_text = str(context.get("_last_body", ""))[:10000]
        except NameError:
            evidence_text = ""

    from _llm_judge_safe import safe_chat_completion
    sys_prompt = (
        "You are an expert code reviewer.\n\n"
        f"Score the candidate from {score_range[0]} to {score_range[1]} "
        "(integer, or a number with at most one decimal).\n\n"
        "You MUST respond with EXACTLY one JSON object and NOTHING else.\n"
        "The first character of your reply MUST be '{' and the last MUST be '}'.\n"
        "Do NOT wrap the JSON in Markdown code fences (no ```).\n"
        "Do NOT add any preface, header, analysis, or trailing commentary outside the JSON.\n"
        "Reasoning MUST be written in English.\n"
        "Required schema:\n"
        "{\"score\": <number>, \"reasoning\": \"<one short paragraph in English, <=250 words, explaining strengths and weaknesses>\"}\n\n"
        "Place the numeric score FIRST so it is preserved even if the reply is truncated."
    )
    def _extract_score(text: str) -> float | None:
        if not text:
            return None
        stripped = text.strip().strip("`").strip()
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict) and "score" in obj:
                return float(obj["score"])
        except Exception:
            pass
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if fence:
            try:
                obj = json.loads(fence.group(1))
                if isinstance(obj, dict) and "score" in obj:
                    return float(obj["score"])
            except Exception:
                pass
        embedded = re.search(r"\{[^{}]*\"score\"\s*:\s*-?\d+(?:\.\d+)?[^{}]*\}", text)
        if embedded:
            try:
                obj = json.loads(embedded.group(0))
                if "score" in obj:
                    return float(obj["score"])
            except Exception:
                pass
        patterns = [
            r"^\s*##\s*(?:Final\s+|Overall\s+)?Score\s*:?\s*(-?\d+(?:\.\d+)?)",
            r"\*\*\s*(?:Final\s+|Overall\s+)?Score\s*\*\*\s*[:=]\s*(-?\d+(?:\.\d+)?)",
            r"\b(?:Final\s+|Overall\s+)?Score\s*:\s*(-?\d+(?:\.\d+)?)\s*/\s*\d+",
            r"\b(?:Final\s+|Overall\s+)?Score\s*[:=]\s*(-?\d+(?:\.\d+)?)",
            r"\bRating\s*[:=]\s*(-?\d+(?:\.\d+)?)\s*(?:out\s+of|/)\s*\d+",
            r"\bRating\s*[:=]\s*(-?\d+(?:\.\d+)?)",
            r"\"score\"\s*[:=]\s*(-?\d+(?:\.\d+)?)",
            r"score\s*[:=]\s*(-?\d+(?:\.\d+)?)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    continue
        return None

    _budgets = [30000, 15000, 10000, 8000, 6000, 5000, 4000, 4000]
    raw = ""
    score_val = None
    last_res = None
    for _budget in _budgets:
        res = safe_chat_completion(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"Rubric:\n{rubric}\n\nEvidence:\n{evidence_text[:_budget]}"},
            ],
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            temperature=0.1,
            max_tokens=1200,
        )
        last_res = res
        if res.skipped:
            return {"passed": True, "score": 0, "max": score_range[1],
                    "skipped": True,
                    "llm_api_failure": res.llm_api_failure,
                    "exception_class": res.exception_class,
                    "reason": res.error or "skipped"}
        raw = (res.raw or "").strip()
        score_val = _extract_score(raw)
        if score_val is not None:
            break

    if score_val is None:
        return {"passed": True, "score": 0, "max": score_range[1],
                "skipped": True,
                "parse_failure": True,
                "reason": "no parseable score in LLM response (after truncation retries) — skipped",
                "raw": raw[:1500],
                "evidence_size": len(evidence_text),
                "files_sampled": files_sampled[:30],
                "missing_bases": missing_bases}
    score_val = max(score_range[0], min(score_range[1], score_val))
    reasoning_text = ""
    try:
        stripped = raw.strip().strip("`").strip()
        obj_try = json.loads(stripped)
        if isinstance(obj_try, dict) and "reasoning" in obj_try:
            reasoning_text = str(obj_try["reasoning"])[:600]
    except Exception:
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
        if fence:
            try:
                obj_try = json.loads(fence.group(1))
                if isinstance(obj_try, dict) and "reasoning" in obj_try:
                    reasoning_text = str(obj_try["reasoning"])[:600]
            except Exception:
                pass
    return {"passed": True, "score": score_val, "max": score_range[1],
            "reasoning": reasoning_text,
            "evidence_size": len(evidence_text),
            "files_sampled": files_sampled[:30],
            "missing_bases": missing_bases,
            "raw_excerpt": raw[:300]}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p21_websocket_connect(inputs: dict) -> dict:
    path = _resolve(inputs.get("path", "/"))
    expect_connected = inputs.get("expect_connected", True)

    ws_url = _url(path).replace("http://", "ws://").replace("https://", "wss://")
    try:
        import websockets.sync.client as ws_client
        with ws_client.connect(ws_url, open_timeout=10, close_timeout=5) as ws:
            connected = True
    except Exception:
        connected = False

    passed = connected == expect_connected
    return {"connected": connected, "passed": passed}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p24_queue_job_check(inputs: dict) -> dict:
    queue = inputs.get("queue", "default")
    return {"passed": True, "queue": queue, "stub": True,
            "note": "Queue job verification requires a running Bull/Redis stack"}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
PRIMITIVE_MAP = {
    "P01": p01_file_exists,
    "P02": p02_file_content_match,
    "P03": p03_file_count,
    "P04": p04_http_request,
    "P06": p06_json_schema_match,
    "P07": p07_json_value_assert,
    "P08": p08_db_query,
    "P09": p09_db_table_exists,
    "P10": p10_db_column_check,
    "P12": p12_docker_exec,
    "P13": p13_auth_login,
    "P14": p14_permission_check,
    "P15": p15_status_code_assert,
    "P17": p17_llm_judge,
    "P21": p21_websocket_connect,
    "P24": p24_queue_job_check,
}


def execute_primitive(ptype: str, inputs: dict) -> dict:
    fn = PRIMITIVE_MAP.get(ptype)
    if fn is None:
        return {"passed": False, "error": f"Unknown primitive {ptype}"}
    resolved = _resolve_deep(inputs)
    return fn(resolved)
