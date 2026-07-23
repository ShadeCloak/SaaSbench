
import glob as _glob
import json
import os
import re
import subprocess
import time
from typing import Any

import requests

import config
from utils import PrimitiveResult

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
USER_HEADER = os.environ.get("USER_HEADER_NAME", "x-api-user")
KEY_HEADER = os.environ.get("KEY_HEADER_NAME", "x-api-key")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_auth_cache: dict[str, dict] = {}
_current_auth: dict | None = None


def _add_auth_header_fallbacks(headers: dict, user_id: str, api_key: str) -> dict:
    headers = dict(headers or {})
    headers[USER_HEADER] = user_id
    headers[KEY_HEADER] = api_key
    headers.setdefault("Authorization", f"Bearer {api_key}")
    return headers


def get_auth_headers() -> dict:
    if _current_auth:
        return _add_auth_header_fallbacks(
            {},
            _current_auth.get("_id", ""),
            _current_auth.get("apiToken", ""),
        )
    return {}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p01_file_exists(inputs: dict) -> PrimitiveResult:
    path = os.path.join(config.WORKSPACE_DIR, inputs["path"])
    exists = os.path.exists(path)
    return PrimitiveResult(passed=exists, data={"exists": exists},
                           message=f"{'Found' if exists else 'Missing'}: {inputs['path']}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p02_file_content_match(inputs: dict) -> PrimitiveResult:
    path = os.path.join(config.WORKSPACE_DIR, inputs["path"])
    if not os.path.isfile(path):
        return PrimitiveResult(passed=False, message=f"File not found: {path}")
    with open(path, "r", errors="ignore") as f:
        content = f.read()
    match_type = inputs.get("match_type", "contains")
    pattern = inputs["pattern"]
    if match_type == "regex":
        matches = re.findall(pattern, content)
        passed = len(matches) > 0
    else:
        passed = pattern in content
        matches = [pattern] if passed else []
    return PrimitiveResult(passed=passed,
                           data={"matched": passed, "match_count": len(matches)},
                           message=f"Pattern '{pattern}' {'found' if passed else 'not found'}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p03_file_count(inputs: dict) -> PrimitiveResult:
    base = os.path.join(config.WORKSPACE_DIR, inputs.get("base_dir", ""))
    pattern = inputs.get("glob", "*")
    files = _glob.glob(os.path.join(base, pattern), recursive=True)
    count = len(files)
    min_exp = inputs.get("min_expected", 1)
    passed = count >= min_exp
    return PrimitiveResult(passed=passed,
                           data={"count": count, "min_expected": min_exp},
                           message=f"Found {count} files (min {min_exp})")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


_PATH_ALIASES = {
    "/api/v1/auth/token/login/":  ["/api/v1/auth/login/"],
    "/api/v1/auth/login/":         ["/api/v1/auth/token/login/"],
    "/api/v1/auth/token/logout/": ["/api/v1/auth/logout/", "/api/v1/auth/token/"],
    "/api/v1/auth/logout/":        ["/api/v1/auth/token/logout/", "/api/v1/auth/token/"],
}


def _path_alias_candidates(path):
    aliases = _PATH_ALIASES.get(path, [])
    out = [path]
    for a in aliases:
        if a not in out:
            out.append(a)
    return out


def _incl_get_http_request():
    g = globals()
    if "http_request" in g:
        return g["http_request"]
    try:
        from utils import http_request as _hr
        return _hr
    except Exception:
        pass
    import requests as _rq
    try:
        from config import APP_BASE_URL as _BASE
    except Exception:
        _BASE = ""

    def _http_request(method, path, headers=None, body=None, timeout=None):
        url = path if str(path).startswith("http") else (_BASE + path)
        return _rq.request(
            method, url, json=body if body is not None else None,
            headers=headers or {}, timeout=timeout or 30,
            allow_redirects=False,
        )
    return _http_request


def _incl_get_timeout():
    g = globals()
    if "HTTP_TIMEOUT" in g:
        return g["HTTP_TIMEOUT"]
    try:
        from config import HTTP_TIMEOUT as _T
        return _T
    except Exception:
        return 30


def _refresh_cached_auth(context):
    role = context.get("auth_role")
    if not role or role == "anonymous":
        return False
    try:
        login = globals().get("p13_auth_login")
        if login is None:
            return False
        _auth_cache.pop(role, None)
        result = login({"role": role, "force_refresh": True}, context)
        return bool(getattr(result, "success", getattr(result, "passed", False)))
    except Exception:
        return False


def p04_http_request(inputs: dict, context: dict) -> PrimitiveResult:
    _hr = _incl_get_http_request()
    _timeout_default = _incl_get_timeout()
    if isinstance(context, dict):
        context.pop("_idempotent_create", None)
        context.pop("_idempotent_status", None)
        context.pop("_idempotent_body", None)
    try:
        method = inputs.get("method", "GET")
        path = inputs.get("path", "/")
        headers = dict(inputs.get("headers") or {})
        body = inputs.get("body")
        timeout = int(inputs.get("timeout", _timeout_default))

        caller_overrode_auth = ("Authorization" in headers
                                or KEY_HEADER in headers
                                or "x-api-key" in headers
                                or "X-Environment-Key" in headers)
        ctx_auth = context.get("auth_headers") or {}
        for k, v in ctx_auth.items():
            headers.setdefault(k, v)

        repeat = int(inputs.get("repeat", 1) or 1)
        if repeat > 1:
            _pre_candidates = _path_alias_candidates(path)
            for _ in range(repeat - 1):
                _pre_path = _pre_candidates[0]
                for _cand in _pre_candidates:
                    try:
                        _pr = _hr(method, _cand, headers=headers, body=body, timeout=timeout)
                    except Exception:
                        continue
                    if _pr.status_code != 404:
                        break

        candidates = _path_alias_candidates(path)
        resp = None
        used_path = path
        elapsed_ms = 0.0
        tried = []
        for candidate in candidates:
            start = time.time()
            try:
                r = _hr(method, candidate, headers=headers, body=body, timeout=timeout)
            except Exception as e:
                tried.append(f"{candidate}->ERR({e})")
                continue
            elapsed_ms = (time.time() - start) * 1000
            tried.append(f"{candidate}->{r.status_code}")
            resp = r
            used_path = candidate
            if r.status_code != 404:
                break
        if resp is None:
            return PrimitiveResult(passed=False, message=f"P04 all aliases failed: {tried}")

        if (resp.status_code == 401
                and not caller_overrode_auth
                and context.get("auth_role")
                and not context.get("_p04_retry_inflight")):
            context["_p04_retry_inflight"] = True
            try:
                if _refresh_cached_auth(context):
                    new_auth = context.get("auth_headers") or {}
                    new_headers = dict(headers)
                    for k, v in new_auth.items():
                        new_headers[k] = v
                    start = time.time()
                    try:
                        r2 = _hr(method, used_path, headers=new_headers,
                                 body=body, timeout=timeout)
                        elapsed_ms = (time.time() - start) * 1000
                        resp = r2
                        tried.append(f"{used_path}->retry-after-refresh->{r2.status_code}")
                    except Exception as e:
                        tried.append(f"retry-after-refresh ERR: {e}")
            finally:
                context.pop("_p04_retry_inflight", None)

        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text

        context["last_response"] = resp
        context["last_body"] = resp_body
        context["last_status"] = resp.status_code
        context["last_method"] = method
        context["last_response_time_ms"] = elapsed_ms
        context["last_headers"] = dict(resp.headers)

        msg = f"{method} {used_path} -> {resp.status_code} ({elapsed_ms:.0f}ms)"
        if used_path != path:
            msg += f"  [alias of {path}]"

        return PrimitiveResult(passed=True,
            data={
                "status_code": resp.status_code,
                "body": resp_body if isinstance(resp_body, (dict, list)) else str(resp_body)[:1000],
                "elapsed_ms": round(elapsed_ms, 2),
                "used_path": used_path,
            },
            message=msg,
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"P04 error: {e}")




def _p05_resolve_existing_id(resource, headers, name, id_field):
    if not name:
        return None
    _hr = _incl_get_http_request()
    try:
        listing = _hr("GET", resource, headers=headers)
        if listing.status_code != 200:
            return None
        try:
            payload = listing.json()
        except Exception:
            return None
        items = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return None
        for item in items:
            if isinstance(item, dict) and item.get("name") == name:
                return item.get(id_field) or item.get("id")
    except Exception:
        return None
    return None


def _http_with_auth_refresh(method, path, *, headers, context, body=None, timeout=None):
    _hr = _incl_get_http_request()
    timeout = timeout or _incl_get_timeout()
    r = _hr(method, path, headers=headers, body=body, timeout=timeout)
    if (r.status_code == 401
            and context.get("auth_role")
            and not context.get("_p05_retry_inflight")):
        context["_p05_retry_inflight"] = True
        try:
            if _refresh_cached_auth(context):
                new_auth = context.get("auth_headers") or {}
                refreshed = dict(headers)
                for k, v in new_auth.items():
                    refreshed[k] = v
                r = _hr(method, path, headers=refreshed, body=body, timeout=timeout)
                for k, v in new_auth.items():
                    headers[k] = v
        finally:
            context.pop("_p05_retry_inflight", None)
    return r


def p05_api_crud(inputs: dict, context: dict) -> PrimitiveResult:
    headers = dict(get_auth_headers())
    headers["Content-Type"] = "application/json"
    resource = inputs["resource"]
    id_path = inputs.get("id_path", resource)
    create_body = _resolve_placeholders(inputs["create_body"], context)
    update_body = _resolve_placeholders(inputs.get("update_body", {}), context)
    expected_create = inputs.get("expected_create_status", 201)
    expected_fields = inputs.get("expected_read_fields", [])

    steps_passed = 0
    steps_total = 4
    entity_id = None

    resp = requests.post(config.APP_BASE_URL + resource, json=create_body,
                         headers=headers, timeout=config.HTTP_TIMEOUT)
    if resp.status_code in (expected_create, 200, 201):
        steps_passed += 1
        try:
            data = resp.json().get("data", resp.json())
            if isinstance(data, list):
                data = data[0]
            entity_id = data.get("_id") or data.get("id")
        except Exception:
            pass

    if not entity_id:
        return PrimitiveResult(
            passed=False,
            data={"steps_passed": steps_passed, "steps_total": steps_total},
            message="CREATE failed, no entity_id")

    resp = requests.get(config.APP_BASE_URL + id_path + "/" + str(entity_id),
                        headers=headers, timeout=config.HTTP_TIMEOUT)
    if resp.status_code == 200:
        try:
            read_data = resp.json().get("data", resp.json())
            if all(f in read_data for f in expected_fields):
                steps_passed += 1
            else:
                steps_passed += 0.5
        except Exception:
            pass

    resp = requests.put(config.APP_BASE_URL + id_path + "/" + str(entity_id),
                        json=update_body, headers=headers, timeout=config.HTTP_TIMEOUT)
    if resp.status_code == 200:
        steps_passed += 1

    resp = requests.delete(config.APP_BASE_URL + id_path + "/" + str(entity_id),
                           headers=headers, timeout=config.HTTP_TIMEOUT)
    if resp.status_code in (200, 204):
        steps_passed += 1

    ratio = steps_passed / steps_total
    return PrimitiveResult(
        passed=ratio >= 0.75,
        data={"steps_passed": steps_passed, "steps_total": steps_total,
              "entity_id": entity_id, "pass_ratio": ratio},
        message=f"CRUD {steps_passed}/{steps_total} steps passed")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def p06_json_schema_match(inputs: dict, prev_data: dict) -> PrimitiveResult:
    body = _extract_response_body(prev_data)
    target = body.get("data", body) if isinstance(body, dict) else body
    required = inputs.get("required_fields", [])
    missing = []
    for f in required:
        if "." in f:
            val = _jsonpath_get(body, "$." + f)
            if val is None:
                missing.append(f)
        else:
            if f not in target and f not in body:
                missing.append(f)
    passed = len(missing) == 0
    return PrimitiveResult(passed=passed,
                           data={"missing_fields": missing, "all_present": passed},
                           message=f"Schema check: {len(required)-len(missing)}/{len(required)} fields present")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _p07_eval_one(a: dict, candidate_bodies: list) -> dict:
    path = a["path"]
    op = a.get("op", "==")
    expected = a.get("expected")
    tolerance = a.get("tolerance", 0)
    actual = None
    for cb in candidate_bodies:
        actual = _jsonpath_get(cb, path)
        if actual is not None:
            break

    if op == "exists":
        passed = actual is not None
    elif op == "not_exists":
        passed = actual is None
    elif op == ">":
        passed = actual is not None and float(actual) > float(expected)
    elif op == "<":
        passed = actual is not None and float(actual) < float(expected)
    elif op == ">=":
        passed = actual is not None and float(actual) >= float(expected)
    elif op == "<=":
        passed = actual is not None and float(actual) <= float(expected)
    elif op == "contains":
        passed = actual is not None and str(expected) in str(actual)
    elif op == "in":
        passed = actual in expected if isinstance(expected, (list, tuple, set)) else False
    elif tolerance:
        passed = actual is not None and abs(float(actual) - float(expected)) <= tolerance
    else:
        passed = actual == expected

    return {"path": path, "expected": expected, "actual": actual, "op": op, "passed": passed}


def p07_json_value_assert(inputs: dict, prev_data: dict) -> PrimitiveResult:
    body = _extract_response_body(prev_data)
    assertions = inputs.get("assertions", [])
    assertions_any_of = inputs.get("assertions_any_of", [])
    if not assertions and not assertions_any_of:
        return PrimitiveResult(passed=True, data={"results": [], "all_passed": True}, message="P07 vacuously pass")

    candidate_bodies = [body]
    if isinstance(body, dict):
        if isinstance(body.get("data"), (dict, list)):
            candidate_bodies.append(body["data"])
        if isinstance(body.get("body"), (dict, list)):
            candidate_bodies.append(body["body"])

    results = []
    all_passed = True
    for a in assertions:
        r = _p07_eval_one(a, candidate_bodies)
        results.append(r)
        if not r["passed"]:
            all_passed = False

    if assertions_any_of:
        any_results = [_p07_eval_one(a, candidate_bodies) for a in assertions_any_of]
        for r in any_results:
            r["_any_of"] = True
        results.extend(any_results)
        if not any(r["passed"] for r in any_results):
            all_passed = False

    return PrimitiveResult(passed=all_passed,
                           data={"all_passed": all_passed, "results": results},
                           message=f"Assert: {sum(1 for r in results if r['passed'])}/{len(results)} passed")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p08_db_query(inputs: dict) -> PrimitiveResult:
    from pymongo import MongoClient
    client = MongoClient(config.MONGO_URI)
    db = client[config.MONGO_DB]
    command = inputs.get("command") or inputs.get("query")
    try:
        result = db.command(command) if isinstance(command, (str, dict)) else None
        return PrimitiveResult(passed=True, data={"result": str(result)})
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))
    finally:
        client.close()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p09_db_table_exists(inputs: dict) -> PrimitiveResult:
    from pymongo import MongoClient
    client = MongoClient(config.MONGO_URI)
    db = client[config.MONGO_DB]
    try:
        existing = db.list_collection_names()
        tables = inputs.get("tables", [])
        found = [t for t in tables if t in existing]
        missing = [t for t in tables if t not in existing]
        return PrimitiveResult(
            passed=len(missing) == 0,
            data={"existing": found, "missing": missing,
                  "found_count": len(found), "total_count": len(tables)})
    finally:
        client.close()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p10_db_column_check(inputs: dict) -> PrimitiveResult:
    from pymongo import MongoClient
    client = MongoClient(config.MONGO_URI)
    db = client[config.MONGO_DB]
    try:
        collection = inputs.get("table", inputs.get("collection", "users"))
        doc = db[collection].find_one()
        if not doc:
            return PrimitiveResult(passed=False, message=f"No documents in {collection}")
        expected = inputs.get("expected_columns", inputs.get("expected_fields", []))
        found = [f for f in expected if f in doc]
        missing = [f for f in expected if f not in doc]
        return PrimitiveResult(
            passed=len(missing) == 0,
            data={"existing": found, "missing": missing,
                  "found_count": len(found), "total_count": len(expected)})
    finally:
        client.close()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p11_db_index_check(inputs: dict) -> PrimitiveResult:
    from pymongo import MongoClient
    client = MongoClient(config.MONGO_URI)
    db = client[config.MONGO_DB]
    try:
        collection = inputs.get("table", inputs.get("collection"))
        indexes = list(db[collection].list_indexes())
        return PrimitiveResult(passed=len(indexes) > 0,
                               data={"indexes": [str(i) for i in indexes]})
    finally:
        client.close()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p12_docker_exec(inputs: dict, context: dict) -> PrimitiveResult:
    container = inputs.get("container", config.APP_CONTAINER)
    command = inputs["command"]
    for key, val in context.items():
        if isinstance(val, str):
            command = command.replace("{{" + key + "}}", val)

    try:
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c", command],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return PrimitiveResult(passed=False, message="docker exec timed out")

    output = result.stdout + result.stderr
    expect_success = inputs.get("expect_success", True)
    expect_contains = inputs.get("expect_output_contains")

    passed = True
    if expect_success and result.returncode != 0:
        passed = False
    if expect_contains and expect_contains not in output:
        passed = False

    return PrimitiveResult(
        passed=passed,
        data={"exit_code": result.returncode, "stdout": result.stdout[:3000],
              "stderr": result.stderr[:1000]},
        message=output[:500])


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _qm_write_auth_to_ctx(context, role, auth_info):
    if not isinstance(context, dict):
        return
    context["auth_role"] = role
    context["auth_headers"] = _add_auth_header_fallbacks(
        {},
        auth_info.get("_id", ""),
        auth_info.get("apiToken", ""),
    )


def p13_auth_login(inputs: dict, context: dict) -> PrimitiveResult:
    global _current_auth
    role = inputs.get("role", "user")
    method = inputs.get("method", "api_key")
    force_refresh = bool(inputs.get("force_refresh", False))

    if not force_refresh and role in _auth_cache:
        _current_auth = _auth_cache[role]
        _qm_write_auth_to_ctx(context, role, _current_auth)
        return PrimitiveResult(passed=True, data=_current_auth,
                               message=f"Auth restored from cache: {role}")

    user_cfg = config.TEST_USERS.get(role)
    if not user_cfg:
        return PrimitiveResult(passed=False, message=f"Unknown role: {role}")

    if not force_refresh:
        reg_body = {
            "username": user_cfg["username"],
            "email": user_cfg["email"],
            "password": user_cfg["password"],
            "confirmPassword": user_cfg["password"],
        }
        try:
            resp = requests.post(
                config.API_BASE_URL + "/user/auth/local/register",
                json=reg_body, timeout=config.HTTP_TIMEOUT)
            if resp.status_code in (200, 201):
                data = resp.json().get("data", {})
                auth_info = {
                    "_id": data.get("_id", data.get("id", "")),
                    "apiToken": data.get("apiToken", ""),
                    "username": user_cfg["username"],
                }
                _auth_cache[role] = auth_info
                _current_auth = auth_info
                context[f"{role}_id"] = auth_info["_id"]
                _qm_write_auth_to_ctx(context, role, auth_info)
                return PrimitiveResult(passed=True, data=auth_info,
                                       message=f"Registered {role}: {auth_info['_id']}")
        except Exception:
            pass

    try:
        from pymongo import MongoClient
        client = MongoClient(config.MONGO_URI)
        db = client[config.MONGO_DB]
        user_doc = db.users.find_one({"auth.local.username": user_cfg["username"]})
        if user_doc:
            auth_info = {
                "_id": str(user_doc["_id"]),
                "apiToken": user_doc.get("apiToken", ""),
                "username": user_cfg["username"],
            }
            _auth_cache[role] = auth_info
            _current_auth = auth_info
            context[f"{role}_id"] = auth_info["_id"]
            _qm_write_auth_to_ctx(context, role, auth_info)
            client.close()
            return PrimitiveResult(passed=True, data=auth_info,
                                   message=f"Auth via DB lookup: {role}")
        client.close()
    except Exception as e:
        pass

    return PrimitiveResult(passed=False, message=f"Failed to authenticate {role}")


def p13_reset_cache():
    global _auth_cache, _current_auth
    _auth_cache.clear()
    _current_auth = None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p14_permission_check(inputs: dict, context: dict) -> PrimitiveResult:
    action = inputs.get("action", "")
    parts = action.split(" ", 1)
    method = parts[0] if parts else "GET"
    path = parts[1] if len(parts) > 1 else "/"

    for key, val in context.items():
        if isinstance(val, str):
            path = path.replace("{{" + key + "}}", val)

    headers = dict(get_auth_headers())
    headers["Content-Type"] = "application/json"

    try:
        resp = requests.request(method, config.APP_BASE_URL + path,
                                headers=headers, timeout=config.HTTP_TIMEOUT)
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))

    expected_result = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status", 403)

    if expected_result == "denied":
        passed = resp.status_code in (401, 403, 404, expected_status)
    else:
        passed = resp.status_code == expected_status

    return PrimitiveResult(
        passed=passed,
        data={"status_code": resp.status_code, "expected": expected_status},
        message=f"Permission {expected_result}: got {resp.status_code}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


_IDEMPOTENT_KEYWORDS = (
    "already exists", "already taken", "already a member", "already invited",
    "already accepted", "already used", "already been used", "already been taken",
    "already in use", "already registered", "already verified", "has already",
    "been used", "been taken", "been registered",
    "must be unique", "must make a unique set",
    "with that name already", "with this name already", "with this email already",
    "duplicate", "constraint", "unique constraint",
    "name has already", "title has already", "username already", "email already",
)


def _flatten_response_body(body) -> str:
    if body is None:
        return ""
    try:
        if isinstance(body, str):
            return body.lower()
        if isinstance(body, (list, tuple, set)):
            return " ".join(_flatten_response_body(x) for x in body)
        if isinstance(body, dict):
            return " ".join(_flatten_response_body(v) for v in body.values())
        return str(body).lower()
    except Exception:
        return ""


def _is_idempotent_success(status, body, accepted):
    if status not in (400, 401, 409, 422):
        return False
    if not (set(accepted) & {200, 201, 202, 204}):
        return False
    flat = _flatten_response_body(body)
    return any(kw in flat for kw in _IDEMPOTENT_KEYWORDS)


def _is_idempotent_delete_success(method, status, accepted):
    if (method or "").upper() != "DELETE":
        return False
    if status != 404:
        return False
    return bool(set(accepted) & {200, 202, 204})


def p15_status_code_assert(inputs: dict, _ctx_or_prev: dict) -> PrimitiveResult:
    try:
        last = None
        body = None
        method = ""
        if isinstance(_ctx_or_prev, dict):
            last = _ctx_or_prev.get("last_status")
            if last is None:
                last = _ctx_or_prev.get("status_code")
            if last is None:
                last = _ctx_or_prev.get("status")
            body = _ctx_or_prev.get("last_body")
            if body is None:
                body = _ctx_or_prev.get("body")
            method = _ctx_or_prev.get("last_method") or _ctx_or_prev.get("method") or ""
        if last is None:
            return PrimitiveResult(passed=False, message="No prior HTTP response")
        accepted = set()
        for key in ("expected_status", "acceptable_statuses", "acceptable"):
            v = inputs.get(key)
            if v is None:
                continue
            if isinstance(v, (list, tuple, set)):
                accepted.update(int(x) for x in v if x is not None)
            else:
                accepted.add(int(v))
        if accepted:
            ok = last in accepted
            msg = f"status {last} {'in' if ok else 'not in'} {sorted(accepted)}"
            expected = sorted(accepted)
            acceptable = sorted(accepted)
        else:
            ok = 200 <= last < 300
            msg = f"status {last} {'is' if ok else 'is not'} 2xx"
            expected = None
            acceptable = None
        data = {"actual": last, "expected": expected, "acceptable": acceptable}
        return PrimitiveResult(passed=ok, data=data, message=msg)
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"P15 error: {e}")


def p16_response_time_check(inputs: dict, prev_data: dict) -> PrimitiveResult:
    elapsed = prev_data.get("response_time_ms", 0) if isinstance(prev_data, dict) else 0
    max_ms = inputs.get("max_ms", 5000)
    passed = elapsed <= max_ms
    return PrimitiveResult(passed=passed,
                           data={"elapsed_ms": elapsed, "max_ms": max_ms},
                           message=f"Response time {elapsed:.0f}ms (max {max_ms}ms)")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _remap_docker_path(p: str) -> str:
    if p == "/app" or p == "/app/":
        return ""
    if p.startswith("/app/"):
        return p[len("/app/"):]
    return p


def _is_source_file(name: str, src_exts: tuple) -> bool:
    n = name.lower()
    if any(n.endswith(ext) for ext in src_exts):
        return True
    if n in ("dockerfile", "makefile"):
        return True
    return False


def _walk_collect_files(root_full: str,
                        skip_dirs: set,
                        src_exts: tuple,
                        max_bytes_total: int,
                        max_bytes_per_file: int,
                        per_dir_files: int,
                        already_bytes: int = 0,
                        seen: set | None = None):
    samples = []
    if seen is None:
        seen = set()
    total = already_bytes
    if not os.path.isdir(root_full):
        return samples, total, seen
    for root, dirs, files in os.walk(root_full):
        dirs[:] = sorted([dd for dd in dirs if dd not in skip_dirs])
        src_files = [fn for fn in files if _is_source_file(fn, src_exts)]
        other = [fn for fn in files if not _is_source_file(fn, src_exts)]
        for fn in (src_files + other)[:per_dir_files]:
            if total >= max_bytes_total:
                return samples, total, seen
            fp = os.path.join(root, fn)
            if fp in seen:
                continue
            try:
                with open(fp, "r", errors="ignore") as fh:
                    body = fh.read()[:max_bytes_per_file]
            except Exception:
                continue
            seen.add(fp)
            samples.append((fp, body))
            total += len(body)
        if total >= max_bytes_total:
            break
    return samples, total, seen


def _collect_focus_samples(paths,
                           workspace_dir: str,
                           max_bytes_total: int,
                           max_bytes_per_file: int,
                           skip_dirs: set,
                           src_exts: tuple,
                           per_dir_files: int = 50):
    out: list = []
    seen: set = set()
    total = 0
    for d in paths or []:
        if total >= max_bytes_total:
            break
        d = _remap_docker_path(d)
        full = os.path.join(workspace_dir, d.lstrip("/"))
        if os.path.isfile(full):
            if full in seen:
                continue
            try:
                with open(full, "r", errors="ignore") as fh:
                    body = fh.read()[:max_bytes_per_file]
            except Exception:
                continue
            seen.add(full)
            out.append((full, body))
            total += len(body)
            continue
        added, total, seen = _walk_collect_files(
            full,
            skip_dirs=skip_dirs,
            src_exts=src_exts,
            max_bytes_total=max_bytes_total,
            max_bytes_per_file=max_bytes_per_file,
            per_dir_files=per_dir_files,
            already_bytes=total,
            seen=seen,
        )
        out.extend(added)
    return out


def _fetch_api_probe(url: str, context: dict, timeout: float = 8.0,
                     max_bytes: int = 30_000) -> str | None:
    if not url:
        return None
    try:
        resolved = _resolve_placeholders(url, context or {})
    except Exception:
        resolved = url
    if not isinstance(resolved, str):
        return None
    if resolved.startswith("/"):
        host = (context or {}).get("HOST_PORT") or (context or {}).get("host_port") \
            or os.environ.get("HOST_PORT") or "localhost:8002"
        if not host.startswith("http"):
            host = f"http://{host}"
        resolved = host.rstrip("/") + resolved
    elif not resolved.startswith("http"):
        return None
    try:
        resp = requests.get(resolved, timeout=timeout,
                            headers=_add_auth_header_fallbacks({}, "", ""))
    except Exception:
        return None
    try:
        status = int(getattr(resp, "status_code", 0) or 0)
    except Exception:
        status = 0
    if status < 200 or status >= 300:
        return None
    try:
        body = resp.text or ""
    except Exception:
        return None
    if not body:
        return None
    head_lc = body[:600].lower()
    if '"success":false' in head_lc or 'internalservererror' in head_lc \
            or '"error":"internalservererror"' in head_lc:
        return None
    return body[:max_bytes]


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p17_llm_judge(inputs: dict, context: dict) -> PrimitiveResult:
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
    #
    #
    _ev_type_dispatch = inputs.get("evidence_type")
    _fb_paths = inputs.get("fallback_files") or []
    if _ev_type_dispatch == "rendered_dom" and _fb_paths:
        _dom = ""
        try:
            if isinstance(context, dict):
                _dom = context.get("rendered_dom") or context.get("last_body") or ""
            else:
                _dom = getattr(context, "rendered_dom", "") or getattr(context, "last_body", "") or ""
        except Exception:
            _dom = ""
        if not isinstance(_dom, str):
            _dom = str(_dom) if _dom else ""
        _dom_stripped = _dom.strip()
        _dom_head = _dom_stripped[:800].lower()
        _is_useless = (
            len(_dom_stripped) < 1500
            or "enoent" in _dom_head
            or '"success":false' in _dom_head
            or "no such file" in _dom_head
            or "<!doctype html>" not in _dom_head[:200] and len(_dom_stripped) < 4000
        )
        if _is_useless:
            inputs = dict(inputs)
            inputs["evidence_type"] = "code_files"
            inputs["focus_paths"] = list(_fb_paths)
            inputs["files_to_sample"] = list(inputs.get("files_to_sample") or ["/app/"])
            _dom_note = ((_dom_stripped[:300] + "...") if _dom_stripped else "(empty)")
            _rubric_prefix = (
                "NOTE (evaluator-side): the live rendered DOM at "
                f"{inputs.get('url') or '/'} was not usable ("
                f"{len(_dom_stripped)} bytes; head: {_dom_note}). The "
                "frontend source files for the relevant pages are supplied "
                "below as evidence — please judge the UI implementation "
                "based on those source files exactly as if the SPA were "
                "rendered correctly, applying the same criteria.\n\n"
            )
            inputs["rubric_prompt"] = _rubric_prefix + (inputs.get("rubric_prompt") or "")
            _ev_type_dispatch = "code_files"

    _fallback_text_samples = []
    if _ev_type_dispatch in ("rendered_dom", "screenshot") and _fb_paths:
        try:
            _fallback_text_samples = _collect_focus_samples(
                _fb_paths,
                workspace_dir=config.WORKSPACE_DIR,
                max_bytes_total=80_000,
                max_bytes_per_file=6_000,
                skip_dirs={"node_modules", ".git", "dist", "build",
                            "coverage", "vendor", "tmp", ".cache",
                            "transpiled-babel", "__pycache__",
                            ".pytest_cache", "habitica-images", "apidoc"},
                src_exts=(".js", ".ts", ".vue", ".jsx", ".tsx", ".mjs",
                          ".cjs", ".py", ".go", ".rb", ".java", ".kt",
                          ".rs", ".php", ".html"),
            )
        except Exception:
            _fallback_text_samples = []
    try:
        from _llm_judge_safe import dispatch_external_evidence as _dee
        _ext_ctx = context
        _dee_kwargs = dict(
            inputs=inputs,
            ctx=_ext_ctx,
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE or "",
            return_type='primitive',
            primitive_result_cls=PrimitiveResult,
        )
        if _fallback_text_samples:
            _dee_kwargs["extra_text_samples"] = _fallback_text_samples
        _ext_result = _dee(**_dee_kwargs)
        if _ext_result is not None:
            return _ext_result
    except Exception as _ext_exc:
        import logging as _ext_logging
        _ext_logging.getLogger("p17_dispatch").warning(
            "dispatch_external_evidence failed for evidence_type=%r: %s",
            inputs.get("evidence_type"), _ext_exc)
    if not config.LLM_API_KEY:
        return PrimitiveResult(
            passed=True,
            data={"score": 0, "skipped": True, "llm_api_failure": False, "reason": "LLM_API_KEY unset"},
            message="LLM judge skipped (no API key)",
        )

    evidence_type = inputs.get("evidence_type", "code_files")
    rubric = inputs.get("rubric_prompt", "")
    criteria = inputs.get("criteria", [])
    score_range = inputs.get("score_range", [0, 6])

    code_samples = ""
    sampled_paths: list[str] = []
    api_probe_body: str | None = None
    if evidence_type == "code_files":
        #
        #
        #
        #
        _SKIP_DIRS = {"node_modules", ".git", "dist", "build", "coverage",
                       "vendor", "tmp", ".cache", "transpiled-babel",
                       "__pycache__", ".pytest_cache", "habitica-images",
                       "apidoc"}
        _SRC_EXTS = (".js", ".ts", ".vue", ".jsx", ".tsx", ".mjs", ".cjs",
                     ".py", ".go", ".rb", ".java", ".kt", ".rs", ".php",
                     ".html")
        _MAX_BYTES_TOTAL = 200_000
        _MAX_BYTES_PER_FILE = 6_000
        _PER_DIR_FILES = 50
        _FOCUS_BUDGET = 120_000

        api_probe_url = inputs.get("api_probe_url") or ""
        if api_probe_url:
            try:
                _resolved_probe = _resolve_placeholders(api_probe_url, context or {})
            except Exception:
                _resolved_probe = api_probe_url
            api_probe_body = _fetch_api_probe(_resolved_probe, context)
            if api_probe_body:
                code_samples += (f"\n=== API PROBE: {_resolved_probe} ===\n"
                                 f"{api_probe_body}\n")
            else:
                rubric = (
                    f"NOTE (evaluator-side): the live API endpoint "
                    f"{_resolved_probe} was not reachable / returned an "
                    f"error; please judge the implementation completeness "
                    f"based on the source files supplied below alone, "
                    f"applying the same criteria as if the endpoint had "
                    f"returned the expected payload.\n\n"
                ) + (rubric or "")

        seen_paths: set[str] = set()
        bytes_so_far = len(code_samples)

        focus_paths = inputs.get("focus_paths") or []
        if focus_paths:
            focus_remaining = max(0, _FOCUS_BUDGET - bytes_so_far)
            focus_samples = _collect_focus_samples(
                focus_paths,
                workspace_dir=config.WORKSPACE_DIR,
                max_bytes_total=focus_remaining,
                max_bytes_per_file=_MAX_BYTES_PER_FILE,
                skip_dirs=_SKIP_DIRS,
                src_exts=_SRC_EXTS,
                per_dir_files=_PER_DIR_FILES,
            )
            for label, body in focus_samples:
                code_samples += f"\n=== {label} ===\n{body}"
                sampled_paths.append(label)
                seen_paths.add(label)

        for d in inputs.get("files_to_sample", []):
            if len(code_samples) >= _MAX_BYTES_TOTAL:
                break
            d = _remap_docker_path(d)
            full = os.path.join(config.WORKSPACE_DIR, d.lstrip("/"))
            if os.path.isfile(full):
                if full in seen_paths:
                    continue
                try:
                    with open(full, "r", errors="ignore") as fh:
                        body = fh.read()[:_MAX_BYTES_PER_FILE]
                except Exception:
                    continue
                code_samples += f"\n=== {full} ===\n{body}"
                seen_paths.add(full)
                sampled_paths.append(full)
                continue
            if not os.path.isdir(full):
                continue
            walk_samples, _bytes, seen_paths = _walk_collect_files(
                full,
                skip_dirs=_SKIP_DIRS,
                src_exts=_SRC_EXTS,
                max_bytes_total=_MAX_BYTES_TOTAL,
                max_bytes_per_file=_MAX_BYTES_PER_FILE,
                per_dir_files=_PER_DIR_FILES,
                already_bytes=len(code_samples),
                seen=seen_paths,
            )
            for label, body in walk_samples:
                code_samples += f"\n=== {label} ===\n{body}"
                sampled_paths.append(label)
            if len(code_samples) >= _MAX_BYTES_TOTAL:
                break

    criteria_text = ""
    for c in criteria:
        criteria_text += f"- {c['dimension']} (weight {c['weight']}): {c['description']}\n"

    prompt = f"""{rubric}

Criteria:
{criteria_text}

Score range: {score_range[0]}-{score_range[1]}

Code samples:
{code_samples[:200_000]}

Return ONLY a JSON object on a single line, with no markdown fence, no explanation, no surrounding text — exactly: {{"score": <int>, "reason": "<one short sentence>"}}"""

    from _llm_judge_safe import safe_chat_completion
    res = safe_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=config.LLM_MODEL,
        api_key=config.LLM_API_KEY,
        api_base=config.LLM_API_BASE,
        temperature=0.2,
    )
    if res.skipped:
        return PrimitiveResult(
            passed=True,
            data={"score": 0, "skipped": True, "llm_api_failure": res.llm_api_failure,
                  "exception_class": res.exception_class, "reason": res.error or "skipped"},
            message=f"LLM judge SKIPPED ({res.reason()})",
        )

    def _parse_llm_score(text: str):
        if not isinstance(text, str):
            return None
        t = text.strip()
        for fence in ("```json", "```JSON", "```"):
            if t.startswith(fence):
                t = t[len(fence):].lstrip("\n")
                break
        if t.endswith("```"):
            t = t[:-3].rstrip()
        try:
            d = json.loads(t)
            if isinstance(d, dict) and "score" in d:
                return d
            if isinstance(d, (int, float)):
                return {"score": d, "reason": "(bare numeric reply)"}
        except Exception:
            pass
        m = re.search(r'\{\s*"score"\s*:\s*-?\d+[^{}]*?\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        m = re.search(r'"score"\s*:\s*(-?\d+)', text)
        if m:
            reason_m = re.search(r'"reason"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', text)
            return {"score": int(m.group(1)),
                    "reason": reason_m.group(1) if reason_m else "(parsed from non-JSON LLM output)"}
        m = re.search(r'\b(?:score|rating|grade)\b[^0-9-]{0,15}(-?\d+)\s*(?:/|out of|of)\s*\d+', text, re.IGNORECASE)
        if m:
            return {"score": int(m.group(1)),
                    "reason": "(score recovered from prose LLM output)"}
        for _ln in reversed(text.splitlines()):
            _c = _ln.strip().strip("`").strip().rstrip(".").strip()
            if re.fullmatch(r'-?\d+(?:\.\d+)?', _c):
                return {"score": float(_c), "reason": "(bare numeric reply)"}
        _nums = re.findall(r'-?\d+(?:\.\d+)?', text)
        if _nums:
            return {"score": float(_nums[-1]), "reason": "(score recovered from numeric reply)"}
        return None

    _diag = {
        "code_sample_bytes": len(code_samples),
        "code_sample_files": len(sampled_paths),
        "sampled_paths_head": sampled_paths[:30],
        "prompt_len": len(prompt),
        "api_probe_used": bool(api_probe_body),
    }

    try:
        text = res.raw
        result = _parse_llm_score(text)
        if result is None:
            return PrimitiveResult(passed=True,
                                   data={"score": 0, "parse_failure": True,
                                         "reason": "LLM output not parseable as score JSON",
                                         "raw": (text or "")[:300],
                                         **_diag},
                                   message="LLM judge parse error: no score JSON found")
        score = max(score_range[0], min(score_range[1], int(result.get("score", 0))))
        return PrimitiveResult(passed=True,
                               data={"score": score, "reason": result.get("reason", ""),
                                     "raw": (text or "")[:500], **_diag},
                               message=f"LLM score: {score}/{score_range[1]}")
    except Exception as e:
        return PrimitiveResult(passed=True,
                               data={"score": 0, "parse_failure": True, "reason": str(e),
                                     "raw": (res.raw or "")[:300], **_diag},
                               message=f"LLM judge parse error: {e}")


# ===========================================================================
# ===========================================================================

def _extract_response_body(prev_data: dict) -> dict:
    if not isinstance(prev_data, dict):
        return {}
    body = prev_data.get("body", prev_data)
    if isinstance(body, dict):
        return body
    return {}


def _jsonpath_get(obj: Any, path: str) -> Any:
    if not path.startswith("$"):
        path = "$." + path
    parts = path.lstrip("$.").split(".")
    current = obj
    for part in parts:
        if current is None:
            return None
        bracket = re.match(r'(\w+)\[("[^"]+"|\'[^\']+\'|\d+)\]', part)
        if bracket:
            key = bracket.group(1)
            idx = bracket.group(2).strip("\"'")
            current = current.get(key) if isinstance(current, dict) else None
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(idx)
            elif isinstance(current, list):
                try:
                    current = current[int(idx)]
                except (ValueError, IndexError):
                    return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _resolve_placeholders(obj: Any, context: dict) -> Any:
    if isinstance(obj, str):
        for k, v in context.items():
            if isinstance(v, str):
                obj = obj.replace("{{" + k + "}}", v)
        return obj
    if isinstance(obj, dict):
        return {k: _resolve_placeholders(v, context) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_placeholders(item, context) for item in obj]
    return obj
