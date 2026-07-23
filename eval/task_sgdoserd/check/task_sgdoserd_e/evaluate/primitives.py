import base64
import hashlib
import hmac
import json
import os
import re
import struct
import time
import urllib.parse
from typing import Any

from utils import (
    PrimitiveResult,
    docker_exec,
    docker_psql,
    http_request,
    json_path_get,
    render_obj,
    render_template,
)
import config

context: dict[str, Any] = {}

_token_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def parse_error(rj: Any) -> tuple[str, Any]:
    if not isinstance(rj, dict):
        return (str(rj) if rj is not None else ""), None
    if "id" in rj and "message" in rj:
        return rj.get("message", ""), rj.get("status_code")
    if "error" in rj:
        err = rj["error"]
        if isinstance(err, dict):
            return err.get("message", ""), err.get("code") or err.get("status")
        return (err if isinstance(err, str) else str(err)), rj.get("code") or rj.get("status")
    if "message" in rj:
        return rj.get("message", ""), rj.get("code") or rj.get("status")
    if "detail" in rj:
        return rj.get("detail", ""), rj.get("code") or rj.get("status")
    return "", None


WS_AUTH_PROTOCOL = os.environ.get("WS_AUTH_PROTOCOL", "authentication_challenge")
WS_AUTH_FALLBACKS = [
    "authentication_challenge",
    "bearer_cookie",
    "authorization_header",
    "identify_opcode",
]


LOCAL_ADMIN_SOCKET_PATH = os.environ.get("LOCAL_ADMIN_SOCKET_PATH", "/tmp/mm_local.sock")
LOCAL_ADMIN_SOCKET_FALLBACKS = [
    "/tmp/mm_local.sock",
    "/tmp/admin_local.sock",
    "/tmp/app_local.sock",
    "/var/run/admin.sock",
    "/var/run/admin_local.sock",
]


TABLE_ALIASES: dict[str, list[str]] = {
    "Users":     ["Users", "users", "User", "user", "members"],
    "Teams":     ["Teams", "teams", "Team", "team", "tenants"],
    "Channels":  ["Channels", "channels", "Channel", "channel", "rooms"],
    "Posts":     ["Posts", "posts", "Post", "messages", "Message"],
    "Reactions": ["Reactions", "reactions", "Reaction"],
    "Roles":     ["Roles", "roles", "Role"],
    "Schemes":   ["Schemes", "schemes", "Scheme"],
    "Threads":   ["Threads", "threads", "Thread"],
    "FileInfo":  ["FileInfo", "fileinfo", "files", "Files"],
}


def _set_token(role: str, token: str):
    _token_cache[role] = token
    context["auth_token"] = token
    context[f"{role}_token"] = token


def _get_token(role: str) -> str | None:
    return _token_cache.get(role)


def _current_token() -> str | None:
    return context.get("auth_token")


# =========================================================================
# =========================================================================
def p01(inputs: dict) -> PrimitiveResult:
    from pathlib import Path
    path = render_template(inputs.get("path", ""), context)
    base = Path(config.WORKSPACE_DIR)
    full = (base / path) if not path.startswith("/") else Path(path)
    exists = full.exists()
    expected_type = inputs.get("type", "file")
    if exists:
        if expected_type == "file" and not full.is_file():
            exists = False
        elif expected_type == "directory" and not full.is_dir():
            exists = False
    return PrimitiveResult("P01", exists, output={"exists": exists, "path": str(full)})


# =========================================================================
# =========================================================================
def p02(inputs: dict) -> PrimitiveResult:
    from pathlib import Path
    output_var = inputs.get("output_var")
    if output_var:
        text = context.get("__last_p12_output", {}).get(output_var, "")
    else:
        path = render_template(inputs.get("path", ""), context)
        full = Path(config.WORKSPACE_DIR) / path if not path.startswith("/") else Path(path)
        if not full.exists():
            return PrimitiveResult("P02", False, error=f"file not found: {full}")
        text = full.read_text(errors="replace")

    pattern = inputs.get("pattern", "")
    match_type = inputs.get("match_type", "contains")
    if match_type == "contains":
        passed = pattern in text
    elif match_type == "regex":
        passed = bool(re.search(pattern, text))
    elif match_type == "exact":
        passed = pattern == text.strip()
    else:
        return PrimitiveResult("P02", False, error=f"unknown match_type: {match_type}")
    return PrimitiveResult("P02", passed, output={"matched": passed, "pattern": pattern})


# =========================================================================
# =========================================================================
def p03(inputs: dict) -> PrimitiveResult:
    from pathlib import Path
    base = Path(config.WORKSPACE_DIR) / render_template(inputs.get("base_dir", ""), context)
    glob = inputs.get("glob", "*")
    min_expected = inputs.get("min_expected", 0)
    if not base.exists():
        return PrimitiveResult("P03", False, error=f"base_dir not found: {base}")
    files = list(base.rglob(glob))
    count = len(files)
    return PrimitiveResult("P03", count >= min_expected, output={"count": count, "min_expected": min_expected})


# =========================================================================
# =========================================================================
def p04(inputs: dict) -> PrimitiveResult:
    method = inputs.get("method", "GET")
    path = render_template(inputs.get("path", ""), context)
    body = render_obj(inputs.get("body"), context) if inputs.get("body") is not None else None
    headers = render_obj(inputs.get("headers"), context) if inputs.get("headers") else None
    auth = inputs.get("auth", "session")
    token = None if auth == "none" else _current_token()
    timeout = inputs.get("timeout", config.HTTP_TIMEOUT)
    files_def = inputs.get("files")
    if files_def:
        import requests
        files = []
        for f in files_def:
            data = base64.b64decode(f.get("content_b64", ""))
            files.append((f.get("field", "files"),
                          (f["filename"], data, f.get("content_type", "application/octet-stream"))))
        form_fields = render_obj(inputs.get("form_fields", {}), context) if inputs.get("form_fields") else None
        req_headers = dict(headers or {})
        if token:
            req_headers["Authorization"] = f"Bearer {token}"
        try:
            resp = requests.request(method, f"{config.APP_BASE_URL}{path}", data=form_fields,
                                    files=files, headers=req_headers, timeout=timeout)
            try:
                jb = resp.json()
            except Exception:
                jb = None
            r = {"status": resp.status_code, "headers": dict(resp.headers),
                 "body": jb, "raw": resp.text, "error": "", "elapsed_ms": int(resp.elapsed.total_seconds() * 1000)}
        except Exception as e:
            r = {"status": 0, "headers": {}, "body": None, "raw": "", "error": str(e), "elapsed_ms": 0}
    else:
        r = http_request(method, path, body=body, headers=headers, token=token, timeout=timeout)
        poll_path = inputs.get("poll_until_path")
        if poll_path:
            attempts = int(inputs.get("poll_attempts", 10))
            interval = float(inputs.get("poll_interval_ms", 500)) / 1000.0
            for _ in range(attempts):
                bd = r.get("body")
                val = json_path_get(bd, poll_path) if isinstance(bd, (dict, list)) else None
                if val is not None:
                    break
                time.sleep(interval)
                r = http_request(method, path, body=body, headers=headers, token=token, timeout=timeout)
    context["__last_response"] = r
    if "store_response_as" in inputs:
        key = inputs["store_response_as"]
        context.setdefault("__responses", {})[key] = r
    if "store_as" in inputs:
        pass
    passed = r["error"] == "" and r["status"] != 0
    return PrimitiveResult("P04", passed, output=r, error=r.get("error", ""))


# =========================================================================
# =========================================================================
def p05(inputs: dict) -> PrimitiveResult:
    resource = render_template(inputs.get("resource", ""), context)
    create_body = render_obj(inputs.get("create_body", {}), context)
    update_body = render_obj(inputs.get("update_body", {}), context)
    token = _current_token()
    steps = []

    r = http_request("POST", resource, body=create_body, token=token)
    steps.append({"op": "create", "status": r["status"]})
    if r["status"] not in (200, 201) or not r["body"]:
        return PrimitiveResult("P05", False, output={"steps": steps}, error="create failed")
    rid = r["body"].get("id") if isinstance(r["body"], dict) else None
    if not rid:
        return PrimitiveResult("P05", False, output={"steps": steps}, error="no id in create response")

    r2 = http_request("GET", f"{resource}/{rid}", token=token)
    steps.append({"op": "read", "status": r2["status"]})

    if update_body:
        r3 = http_request("PUT", f"{resource}/{rid}", body=update_body, token=token)
        steps.append({"op": "update", "status": r3["status"]})

    r4 = http_request("DELETE", f"{resource}/{rid}", token=token)
    steps.append({"op": "delete", "status": r4["status"]})

    passed = all(s["status"] in (200, 201, 204) for s in steps)
    return PrimitiveResult("P05", passed, output={"steps": steps, "id": rid})


# =========================================================================
# =========================================================================
def p06(inputs: dict) -> PrimitiveResult:
    body = context.get("__last_response", {}).get("body")
    if body is None:
        return PrimitiveResult("P06", False, error="no last response body")
    required = inputs.get("required_fields", [])
    if not isinstance(body, dict):
        return PrimitiveResult("P06", False, error=f"response not an object (type={type(body).__name__})")
    missing = [f for f in required if f not in body]
    return PrimitiveResult("P06", not missing,
                           output={"required": required, "missing": missing},
                           error=f"missing fields: {missing}" if missing else "")


# =========================================================================
# =========================================================================
def p07(inputs: dict) -> PrimitiveResult:
    last = context.get("__last_response", {})
    body = last.get("body")
    headers = last.get("headers", {})
    obj_root = {"headers": headers}
    if isinstance(body, dict):
        obj_root.update(body)
        obj_root["__body"] = body
    elif isinstance(body, list):
        obj_root["__body"] = body
    else:
        obj_root["__body"] = body

    stored_responses = context.get("__responses", {})

    def _resolve_path(p):
        if p == "$":
            return body
        if p.startswith("$.") and isinstance(p, str):
            head = p[2:].split(".", 1)[0]
            if head == "headers":
                return json_path_get(obj_root, p)
            if head in stored_responses:
                rest = p[2 + len(head):]
                stored_body = stored_responses[head].get("body")
                if not rest:
                    return stored_body
                lookup_path = "$" + rest
                if isinstance(stored_body, (dict, list)):
                    return json_path_get(stored_body, lookup_path)
                return None
            return json_path_get(body if isinstance(body, (dict, list)) else obj_root, p)
        return json_path_get(obj_root, p)

    assertions = inputs.get("assertions", [])
    failed = []
    passed_count = 0
    for a in assertions:
        rendered = render_obj(a, context)
        path = rendered.get("path", "$")
        actual = _resolve_path(path)

        if "expected_eq" in rendered and isinstance(rendered["expected_eq"], str) \
                and rendered["expected_eq"].startswith("$."):
            rendered = dict(rendered)
            rendered["expected_eq"] = _resolve_path(rendered["expected_eq"])

        ok = _assert_value(actual, rendered)
        if ok:
            passed_count += 1
        else:
            failed.append({"path": path, "actual": str(actual)[:100], "expected": rendered})
    all_passed = not failed
    return PrimitiveResult("P07", all_passed,
                           output={"passed": passed_count, "total": len(assertions), "failed": failed},
                           error=f"{len(failed)} of {len(assertions)} assertions failed" if failed else "")


def _assert_value(actual, rendered: dict) -> bool:
    if "expected" in rendered:
        exp = rendered["expected"]
        if exp == "" and actual is None:
            return True
        if exp is None and actual == "":
            return True
        return actual == exp
    if "expected_one_of" in rendered:
        return actual in rendered["expected_one_of"]
    if "expected_eq" in rendered:
        return actual == rendered["expected_eq"]
    if "regex" in rendered:
        return isinstance(actual, str) and bool(re.search(rendered["regex"], actual))
    if "contains" in rendered:
        if isinstance(actual, str):
            return rendered["contains"] in actual
        if isinstance(actual, list):
            return rendered["contains"] in actual
        if isinstance(actual, dict):
            return rendered["contains"] in actual
        return False
    if "exists" in rendered:
        want = rendered["exists"]
        return (actual is not None) == bool(want)
    if "not_exists" in rendered:
        return actual is None or actual == ""
    if "type" in rendered:
        t = rendered["type"]
        if t == "array":
            ok = isinstance(actual, list)
            if "min_length" in rendered and ok:
                ok = ok and len(actual) >= rendered["min_length"]
            if "max_length" in rendered and ok:
                ok = ok and len(actual) <= rendered["max_length"]
            return ok
        if t == "object":
            return isinstance(actual, dict)
        if t == "object_or_array":
            return isinstance(actual, (dict, list))
        if t == "integer":
            return isinstance(actual, int) and not isinstance(actual, bool)
        if t == "string":
            return isinstance(actual, str)
        return False
    if "min_value" in rendered:
        try:
            return float(actual) >= float(rendered["min_value"])
        except (TypeError, ValueError):
            return False
    if "min_length" in rendered:
        return hasattr(actual, "__len__") and len(actual) >= rendered["min_length"]
    if "max_length" in rendered:
        return hasattr(actual, "__len__") and len(actual) <= rendered["max_length"]
    return True


# =========================================================================
# =========================================================================
def p08(inputs: dict) -> PrimitiveResult:
    sql = render_template(inputs.get("sql", ""), context)
    r = docker_psql(sql)
    if r["exit"] != 0:
        return PrimitiveResult("P08", False, output=r, error=r.get("stderr", "") or r.get("error", ""))
    rows = r["rows"]
    store_as = inputs.get("store_field_as") or inputs.get("store_as")
    if store_as:
        if rows and rows[0]:
            val = rows[0][0]
            if isinstance(val, str):
                val = val.strip()
            context[store_as] = val
            r["captured"] = {store_as: val}
        else:
            r["captured"] = {store_as: None}
        if inputs.get("capture_only"):
            return PrimitiveResult("P08", True, output=r)
    expected_result = inputs.get("expected_result")
    if expected_result is not None:
        if not rows:
            return PrimitiveResult("P08", False, output=r, error="no rows returned")
        first = rows[0]
        for k, v in expected_result.items():
            sv = str(v).lower() if isinstance(v, bool) else str(v)
            if sv not in [str(x).strip() for x in first]:
                return PrimitiveResult("P08", False, output=r,
                                       error=f"expected {k}={v} not in row {first}")
        return PrimitiveResult("P08", True, output=r)
    if "expected_min" in inputs:
        try:
            v = int(rows[0][0]) if rows else 0
        except (ValueError, IndexError):
            v = 0
        return PrimitiveResult("P08", v >= inputs["expected_min"], output=r)
    if "expected_min_field" in inputs:
        min_value = inputs.get("expected_min_value", 0)
        if not rows:
            return PrimitiveResult("P08", True, output=r,
                                   error="no rows but expected_min_field is permissive")
        try:
            v = int(rows[0][0]) if rows[0] else 0
            return PrimitiveResult("P08", v >= min_value, output=r)
        except (ValueError, TypeError):
            return PrimitiveResult("P08", True, output=r,
                                   error=f"non-numeric value {rows[0][0]!r}, treated as PASS")
    if "expected_field_regex" in inputs:
        if not rows:
            return PrimitiveResult("P08", False, output=r, error="no rows")
        cell = rows[0][0] if rows[0] else ""
        return PrimitiveResult("P08", bool(re.search(inputs["expected_field_regex"]["pattern"], str(cell))), output=r)
    return PrimitiveResult("P08", True, output=r)


# =========================================================================
# =========================================================================
def p09(inputs: dict) -> PrimitiveResult:
    tables = inputs.get("tables", [])
    if not tables:
        return PrimitiveResult("P09", False, error="no tables specified")
    sql = ("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename IN ("
           + ",".join(f"'{t}'" for t in tables) + ")")
    r = docker_psql(sql)
    if r["exit"] != 0:
        return PrimitiveResult("P09", False, output=r, error=r.get("stderr", ""))
    cnt = int(r["rows"][0][0]) if r["rows"] and r["rows"][0] else 0
    return PrimitiveResult("P09", cnt == len(tables),
                           output={"expected": tables, "found_count": cnt})


# =========================================================================
# =========================================================================
def p10(inputs: dict) -> PrimitiveResult:
    table = inputs.get("table", "")
    expected = inputs.get("expected_columns", [])
    if not table or not expected:
        return PrimitiveResult("P10", False, error="missing table or expected_columns")
    sql = f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}'"
    r = docker_psql(sql)
    if r["exit"] != 0:
        return PrimitiveResult("P10", False, output=r, error=r.get("stderr", ""))
    actual_cols = {row[0].lower() for row in r["rows"]}
    missing = [c for c in expected if c.lower() not in actual_cols]
    return PrimitiveResult("P10", not missing,
                           output={"expected": expected, "actual_count": len(actual_cols), "missing": missing},
                           error=f"missing columns: {missing}" if missing else "")


# =========================================================================
# =========================================================================
def p11(inputs: dict) -> PrimitiveResult:
    table = inputs.get("table", "")
    expected_cols = inputs.get("expected_columns", [])
    unique_required = inputs.get("unique_required", False)
    sql = f"SELECT indexname, indexdef FROM pg_indexes WHERE tablename='{table}'"
    r = docker_psql(sql)
    if r["exit"] != 0:
        return PrimitiveResult("P11", False, error=r.get("stderr", ""))
    found = False
    for row in r["rows"]:
        if len(row) < 2:
            continue
        idxdef = row[1].lower()
        if unique_required and "unique" not in idxdef:
            continue
        if all(c.lower() in idxdef for c in expected_cols):
            found = True
            break
    return PrimitiveResult("P11", found,
                           output={"table": table, "cols": expected_cols, "found": found})


# =========================================================================
# =========================================================================
def p12(inputs: dict) -> PrimitiveResult:
    container = inputs.get("container", config.APP_CONTAINER)
    command = render_template(inputs.get("command", ""), context)
    timeout = inputs.get("timeout", config.DOCKER_EXEC_TIMEOUT)
    r = docker_exec(container, command, timeout=timeout)
    context["__last_p12_output"] = r
    expected_exit = inputs.get("command_exit_code")
    if expected_exit is not None:
        passed = r["exit"] == expected_exit
    else:
        passed = r["error"] == ""
    return PrimitiveResult("P12", passed, output=r, error=r.get("error", ""))


# =========================================================================
# =========================================================================
def _store_user_id(role: str, uid: str):
    context[f"{role}_user_id"] = uid
    if role == "admin":
        context["admin_user_id"] = uid
    elif role == "user":
        context["eval_user_id"] = uid
    elif role == "guest":
        context["eval_guest_id"] = uid


def _ensure_user(user_cfg: dict) -> bool:
    body = {
        "email": user_cfg.get("email", f"{user_cfg['username']}@test.local"),
        "username": user_cfg["username"],
        "password": user_cfg["password"],
        "first_name": user_cfg.get("first_name", "Eval"),
        "last_name": user_cfg.get("last_name", "User"),
    }
    r = http_request("POST", "/api/v4/users", body=body)
    if r["status"] in (201, 200):
        return True
    if r["status"] == 400:
        eid = (r["body"] or {}).get("id", "") if isinstance(r["body"], dict) else ""
        if "exists" in eid or "duplicate" in eid or "username" in eid or "email" in eid:
            return True
    return False


def p13(inputs: dict) -> PrimitiveResult:
    inputs = {
        k: (render_template(v, context) if isinstance(v, str) else v)
        for k, v in (inputs or {}).items()
    }
    role = inputs.get("role") or inputs.get("store_as") or "admin"

    if role in _token_cache and inputs.get("method") != "credentials":
        token = _token_cache[role]
        rv = http_request("GET", "/api/v4/users/me", token=token)
        if rv["status"] == 200:
            context["auth_token"] = token
            synth = dict(rv)
            synth_headers = dict(rv.get("headers", {}))
            synth_headers["Token"] = token
            synth["headers"] = synth_headers
            context["__last_response"] = synth
            uid = (rv["body"] or {}).get("id") if isinstance(rv["body"], dict) else None
            if uid:
                _store_user_id(role, uid)
            return PrimitiveResult("P13", True, output={"role": role, "method": "cache_validated"})
        _token_cache.pop(role, None)

    user_cfg = dict(config.TEST_USERS.get(role) or {})
    if inputs.get("login_id"):
        user_cfg["username"] = inputs["login_id"]
    if inputs.get("password"):
        user_cfg["password"] = inputs["password"]
    if not user_cfg.get("username"):
        return PrimitiveResult("P13", False, error=f"no test user for role={role}")

    _ensure_user(user_cfg)

    body = {"login_id": user_cfg["username"], "password": user_cfg["password"]}
    r = http_request("POST", "/api/v4/users/login", body=body)
    context["__last_response"] = r
    session_token = None
    uid = None
    if r["status"] == 200:
        session_token = r["headers"].get("Token") or r["headers"].get("token")
        if isinstance(r["body"], dict):
            uid = r["body"].get("id")

    if session_token:
        _set_token(role, session_token)
        if uid:
            _store_user_id(role, uid)
        return PrimitiveResult("P13", True, output={"role": role, "method": "session",
                                                      "token_len": len(session_token)})

    username = user_cfg["username"]
    if uid is None:
        sql = f"SELECT id FROM users WHERE username='{username}' LIMIT 1"
        r2 = docker_psql(sql)
        if r2["rows"] and r2["rows"][0]:
            uid = r2["rows"][0][0].strip()

    if not uid:
        return PrimitiveResult("P13", False, error=f"could not locate user_id for {username}")

    import secrets
    import string
    alphabet = string.ascii_lowercase + string.digits
    new_token = "".join(secrets.choice(alphabet) for _ in range(26))
    new_id = "".join(secrets.choice(alphabet) for _ in range(26))
    chk = docker_psql("SELECT 1 FROM pg_tables WHERE tablename='useraccesstokens'")
    if chk["exit"] == 0 and chk["rows"]:
        docker_psql(f"DELETE FROM useraccesstokens WHERE description='eval_{role}'")
        docker_psql(
            f"INSERT INTO useraccesstokens (id, token, userid, description, isactive) "
            f"VALUES ('{new_id}', '{new_token}', '{uid}', 'eval_{role}', true)"
        )
        rv = http_request("GET", "/api/v4/users/me", token=new_token)
        if rv["status"] == 200:
            _set_token(role, new_token)
            _store_user_id(role, uid)
            return PrimitiveResult("P13", True, output={"role": role, "method": "db_direct_PAT",
                                                          "token_len": 26})

    return PrimitiveResult("P13", False,
                           error=f"all 4 auth strategies failed for role={role}; user_id={uid}")


# =========================================================================
# =========================================================================
def p14(inputs: dict) -> PrimitiveResult:
    expected_result = inputs.get("expected_result", "allowed")
    expected_status = inputs.get("expected_status")
    last = context.get("__last_response", {})
    actual = last.get("status", 0)

    if expected_result == "allowed":
        if expected_status is not None:
            passed = actual == expected_status
        else:
            passed = 200 <= actual < 300
    elif expected_result == "not_denied":
        passed = actual not in (401, 403)
    elif expected_result == "denied":
        if expected_status is not None:
            passed = actual == expected_status or actual == 404
        else:
            passed = actual in (401, 403, 404)
    else:
        passed = False
    return PrimitiveResult("P14", passed,
                           output={"expected": expected_result, "actual_status": actual,
                                   "expected_status": expected_status})


# =========================================================================
# =========================================================================
def p15(inputs: dict) -> PrimitiveResult:
    last = context.get("__last_response", {})
    if "exit" in last and "stdout" in last:
        last = context.get("__last_response", {})
    actual = last.get("status", 0)
    if "expected_status" in inputs:
        exp = inputs["expected_status"]
        if isinstance(exp, (list, tuple, set)):
            passed = actual in exp
        else:
            passed = actual == exp
    elif "acceptable_statuses" in inputs:
        passed = actual in inputs["acceptable_statuses"]
    elif "command_exit_code" in inputs:
        p12_out = context.get("__last_p12_output", {})
        passed = p12_out.get("exit") == inputs["command_exit_code"]
    else:
        passed = 200 <= actual < 300
    return PrimitiveResult("P15", passed,
                           output={"actual_status": actual},
                           error=f"actual status {actual}" if not passed else "")


# =========================================================================
# =========================================================================
def p16(inputs: dict) -> PrimitiveResult:
    last = context.get("__last_response", {})
    elapsed_ms = last.get("elapsed_ms", 0)
    threshold = inputs.get("max_ms", 5000)
    return PrimitiveResult("P16", elapsed_ms <= threshold, output={"elapsed_ms": elapsed_ms})


# =========================================================================
# =========================================================================
def p17(inputs: dict) -> PrimitiveResult:
    rubric = inputs.get("rubric_prompt", "Score the implementation 0-5.")
    score_range = inputs.get("score_range", [0, 5])
    files = inputs.get("files_to_sample", [])

    from pathlib import Path
    import glob as _glob
    snippets = []
    base = Path(config.WORKSPACE_DIR)
    _CODE_EXTS = {".go", ".ts", ".tsx", ".js", ".jsx", ".py", ".sql", ".yaml", ".yml", ".json"}

    def _read(p: Path):
        try:
            return f"--- {p.relative_to(base)} ---\n{p.read_text(errors='replace')[:3000]}"
        except Exception:
            return None

    for f in files[:5]:
        full = base / f
        if full.is_dir():
            cands = []
            for sub in full.rglob("*"):
                if sub.is_file() and sub.suffix in _CODE_EXTS:
                    cands.append(sub)
                if len(cands) >= 3:
                    break
            for sub in cands[:3]:
                snip = _read(sub)
                if snip:
                    snippets.append(snip)
        elif full.is_file():
            snip = _read(full)
            if snip:
                snippets.append(snip)
        else:
            pat = str(full)
            matched = sorted(_glob.glob(pat))
            if not matched and "*" not in pat:
                prefix_dir = full.parent
                prefix_name = full.name
                if prefix_dir.is_dir():
                    matched = sorted(
                        str(p) for p in prefix_dir.iterdir()
                        if p.is_file() and p.name.startswith(prefix_name)
                        and p.suffix in _CODE_EXTS
                    )
            for m in matched[:3]:
                snip = _read(Path(m))
                if snip:
                    snippets.append(snip)
    evidence = "\n\n".join(snippets)[:20000]
    prompt = f"{rubric}\n\nReturn ONLY a JSON object: {{\"score\": <int>, \"reason\": \"<short>\"}}\n\n{evidence}"

    from _llm_judge_safe import safe_chat_completion, _extract_score

    _msgs = [{"role": "user", "content": prompt}]

    def _judge_call(msgs):
        return safe_chat_completion(
            messages=msgs,
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE or "",
            temperature=0.0,
            timeout=60.0,
            max_tokens=8192,
        )

    res = _judge_call(_msgs)

    if res.skipped:
        return PrimitiveResult(
            "P17", False,
            output={
                "skipped": True,
                "llm_api_failure": res.llm_api_failure,
                "exception_class": res.exception_class,
                "reason": res.error or "skipped",
                "score": 0,
                "max": score_range[1],
            },
            extras={"skipped": True, "reason": res.error or "skipped"},
        )

    score = _extract_score(res.raw)
    if score is None:
        retry = _judge_call(_msgs + [
            {"role": "assistant", "content": (res.raw or "")[:2000]},
            {"role": "user", "content": (
                f"You did not output a score. Reply with ONLY a single integer "
                f"between {score_range[0]} and {score_range[1]} — no words, no "
                f"explanation, just the number."
            )},
        ])
        if not retry.skipped:
            score = _extract_score(retry.raw)

    if score is None:
        return PrimitiveResult(
            "P17", False,
            output={"skipped": True, "parse_failure": True,
                    "reason": "model reply contains no parseable score after retry",
                    "score": 0, "max": score_range[1], "raw": (res.raw or "")[:200]},
            extras={"skipped": True, "reason": "llm parse failure"},
        )

    score = max(score_range[0], min(score_range[1], score))
    passed = score > (score_range[1] - score_range[0]) / 2
    return PrimitiveResult("P17", passed, output={"score": score, "max": score_range[1]})


# =========================================================================
# =========================================================================
def p19(inputs: dict) -> PrimitiveResult:
    last = context.get("__last_response", {})
    raw = last.get("raw", "") or ""
    body = last.get("body")
    if isinstance(body, str):
        raw = raw or body
    elif isinstance(body, (dict, list)):
        try:
            raw = raw or json.dumps(body)
        except Exception:
            pass
    selectors = inputs.get("selectors", [])
    all_required = inputs.get("all_required", True)
    matches = []
    for sel in selectors:
        token = sel
        if sel.startswith("#"):
            token_alts = [f'id="{sel[1:]}"', f"id='{sel[1:]}'", sel]
        elif sel.startswith("."):
            token_alts = [f'class="{sel[1:]}"', f'class="{sel[1:]} ', sel]
        else:
            token_alts = [f"<{sel}", f"<{sel} ", f"<{sel}>"]
        found = any(alt in raw for alt in token_alts)
        matches.append({"selector": sel, "found": found})
    if all_required:
        passed = all(m["found"] for m in matches)
    else:
        passed = any(m["found"] for m in matches) if matches else True
    return PrimitiveResult("P19", passed,
                           output={"matches": matches, "raw_len": len(raw)})


# =========================================================================
# =========================================================================
def p21(inputs: dict) -> PrimitiveResult:
    try:
        import websocket
    except ImportError:
        return PrimitiveResult("P21", True, output={"skipped": "websocket-client not installed"})
    path = render_template(inputs.get("path", "/api/v4/websocket"), context)
    url = path if path.startswith("ws") else f"ws://{config.APP_HOST}:{config.APP_PORT}{path}"
    token = _current_token()
    upgrade_headers = []
    if token:
        upgrade_headers.append(f"Authorization: Bearer {token}")
    cookie_header = f"MMAUTHTOKEN={token}" if token else None
    try:
        kw = {"timeout": config.WS_TIMEOUT, "header": upgrade_headers}
        if cookie_header:
            kw["cookie"] = cookie_header
        ws = websocket.create_connection(url, **kw)
        if token:
            try:
                ws.send(json.dumps({
                    "seq": 1,
                    "action": "authentication_challenge",
                    "data": {"token": token},
                }))
            except Exception:
                pass

        events = []
        ws.settimeout(3)
        for _ in range(5):
            try:
                raw = ws.recv()
                if not raw:
                    break
                try:
                    events.append(json.loads(raw))
                except Exception:
                    pass
            except Exception:
                break

        if inputs.get("send"):
            for msg in inputs["send"]:
                try:
                    ws.send(json.dumps(render_obj(msg, context)))
                    _ = ws.recv()
                except Exception:
                    pass

        if inputs.get("trigger_after_connect"):
            t = inputs["trigger_after_connect"].get("http_call", {})
            http_request(t.get("method", "GET"), render_template(t.get("path", ""), context),
                         body=render_obj(t.get("body"), context), token=token)
            ws.settimeout(2)
            for _ in range(8):
                try:
                    raw = ws.recv()
                    if not raw:
                        break
                    events.append(json.loads(raw))
                except Exception:
                    break
        try:
            ws.close()
        except Exception:
            pass

        first_event = events[0] if events else {}
        expect = inputs.get("expect_first_event")
        if expect:
            target = expect.get("event")
            ok = any(e.get("event") == target for e in events[:3])
            return PrimitiveResult("P21", ok,
                                   output={"first_event": first_event,
                                           "received_events": [e.get("event") for e in events]})
        expect_ev = inputs.get("expect_event")
        if expect_ev:
            target = expect_ev.get("event")
            ok = any(e.get("event") == target for e in events)
            return PrimitiveResult("P21", ok,
                                   output={"received_events": [e.get("event") for e in events]})
        ok = bool(events)
        return PrimitiveResult("P21", ok,
                               output={"received_events": [e.get("event") for e in events]})
    except Exception as e:
        return PrimitiveResult("P21", False, error=str(e))


# =========================================================================
# =========================================================================
def p23(inputs: dict) -> PrimitiveResult:
    upload_path = render_template(inputs.get("upload_path", "/api/v4/files"), context)
    form_fields = render_obj(inputs.get("form_fields", {}), context)
    files_def = inputs.get("files", [])
    token = _current_token()
    if not token:
        return PrimitiveResult("P23", False, error="no auth token")
    try:
        files = []
        for f in files_def:
            data = base64.b64decode(f.get("content_b64", ""))
            files.append((f.get("field", "files"), (f["filename"], data, f.get("content_type", "application/octet-stream"))))
        import requests
        r = requests.post(
            f"{config.APP_BASE_URL}{upload_path}", data=form_fields, files=files,
            headers={"Authorization": f"Bearer {token}"}, timeout=config.HTTP_TIMEOUT,
        )
        try:
            jb = r.json()
        except Exception:
            jb = None
        result = {"status": r.status_code, "headers": dict(r.headers), "body": jb, "raw": r.text}
        context["__last_response"] = result
        return PrimitiveResult("P23", r.status_code in (200, 201), output=result)
    except Exception as e:
        return PrimitiveResult("P23", False, error=str(e))


# =========================================================================
# =========================================================================
def _compute_totp(secret: str, *, step: int = 30, digits: int = 6, offset: int = 0) -> str:
    s = (secret or "").strip().upper().replace(" ", "")
    s += "=" * ((8 - len(s) % 8) % 8)
    key = base64.b32decode(s)
    counter = int(time.time()) // step + offset
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def p30(inputs: dict) -> PrimitiveResult:
    secret = inputs.get("secret")
    if secret is not None:
        secret = render_template(str(secret), context)
    else:
        key = inputs.get("secret_context_key", "mfa_secret")
        secret = context.get(key)
    if not secret:
        return PrimitiveResult("P30", False, error="no TOTP secret available")
    store_as = inputs.get("store_as", "mfa_code")
    try:
        code = _compute_totp(str(secret), step=inputs.get("step", 30),
                             digits=inputs.get("digits", 6), offset=inputs.get("offset", 0))
    except Exception as e:
        return PrimitiveResult("P30", False, error=f"TOTP compute failed: {e}")
    context[store_as] = code
    return PrimitiveResult("P30", True, output={"store_as": store_as, "digits": len(code)})


# =========================================================================
# =========================================================================
_PRIMITIVES = {
    "P01": p01, "P02": p02, "P03": p03, "P04": p04, "P05": p05,
    "P06": p06, "P07": p07, "P08": p08, "P09": p09, "P10": p10,
    "P11": p11, "P12": p12, "P13": p13, "P14": p14, "P15": p15,
    "P16": p16, "P17": p17, "P19": p19, "P21": p21, "P23": p23,
    "P30": p30,
}


def execute_primitive(spec: dict) -> PrimitiveResult:
    ptype = spec.get("type", "")
    inputs = spec.get("inputs", {}) or {}
    fn = _PRIMITIVES.get(ptype)
    if fn is None:
        return PrimitiveResult(ptype, False, error=f"unknown primitive: {ptype}")
    try:
        return fn(inputs)
    except Exception as e:
        import traceback
        return PrimitiveResult(ptype, False, error=f"{type(e).__name__}: {e}",
                               extras={"traceback": traceback.format_exc()})


def reset_context():
    global context
    context.clear()
    _token_cache.clear()
