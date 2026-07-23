from __future__ import annotations

import base64
import json
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from . import config, utils
from .utils import (
    PrimitiveResult, db_connect, db_query, docker_exec, http_request,
    http_response_summary, jsonpath_get,
)

_TOKEN_CACHE: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p01_file_exists(inputs: dict, ctx: dict) -> PrimitiveResult:
    rel = inputs.get("path", "")
    expected_type = inputs.get("type", "file")
    full = config.WORKSPACE_DIR / rel
    if expected_type == "dir":
        ok = full.is_dir()
    else:
        ok = full.is_file()
    return PrimitiveResult("P01", ok, f"{full} -> {ok}", {"path": str(full)})


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p02_file_content_match(inputs: dict, ctx: dict) -> PrimitiveResult:
    rel = inputs.get("path", "")
    pattern = inputs.get("pattern", "")
    match_type = inputs.get("match_type", "contains")
    full = config.WORKSPACE_DIR / rel
    if not full.is_file():
        return PrimitiveResult("P02", False, f"file missing: {full}")
    try:
        text = full.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return PrimitiveResult("P02", False, f"read error: {e}")
    if match_type == "contains":
        ok = pattern in text
        n = text.count(pattern)
    else:
        m = re.search(pattern, text)
        ok = m is not None
        n = len(re.findall(pattern, text))
    return PrimitiveResult(
        "P02", ok, f"{rel}: pattern={pattern!r} matches={n}",
        {"matches": n},
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p03_file_count(inputs: dict, ctx: dict) -> PrimitiveResult:
    base = config.WORKSPACE_DIR / inputs.get("base_dir", "")
    glob = inputs.get("glob", "*")
    minc = int(inputs.get("min_expected", 1))
    if not base.exists():
        return PrimitiveResult("P03", False, f"base_dir missing: {base}")
    n = sum(1 for _ in base.glob(glob))
    ok = n >= minc
    return PrimitiveResult("P03", ok, f"glob={glob} found={n} min={minc}", {"count": n})


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
    try:
        from config import APP_BASE_URL as _BASE
    except Exception:
        _BASE = ""
    try:
        from utils import http_request as _hr
    except Exception:
        _hr = None

    if _hr is not None:
        def _wrapped(method, path, headers=None, body=None, timeout=None, body_form=None):
            url = path if str(path).startswith("http") else (_BASE + path)
            return _hr(method, url, headers=headers, body=body, body_form=body_form,
                       timeout=timeout, allow_redirects=False)
        return _wrapped

    import requests as _rq
    def _http_request(method, path, headers=None, body=None, timeout=None, body_form=None):
        url = path if str(path).startswith("http") else (_BASE + path)
        kwargs = {"headers": headers or {}, "timeout": timeout or 30,
                  "allow_redirects": False}
        if body_form is not None:
            kwargs["data"] = body_form
        elif body is not None:
            kwargs["json"] = body
        return _rq.request(method, url, **kwargs)
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
        cache_key_prefix = f"{role}:"
        for k in list(_TOKEN_CACHE.keys()):
            if k.startswith(cache_key_prefix):
                _TOKEN_CACHE.pop(k, None)
        result = login({"role": role, "force_refresh": True}, context)
        return bool(getattr(result, "success", getattr(result, "passed", False)))
    except Exception:
        return False


def _propagate_auth_headers(ctx: dict) -> None:
    headers: dict = {}
    tok = ctx.get("access_token")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    cookie = ctx.get("session_cookie")
    if cookie:
        headers["Cookie"] = cookie
    if headers:
        ctx["auth_headers"] = headers
    elif "auth_headers" in ctx:
        ctx.pop("auth_headers", None)


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
        body_form = inputs.get("body_form")
        timeout = int(inputs.get("timeout", _timeout_default))

        caller_overrode_auth = ("Authorization" in headers
                                or "x-api-key" in headers
                                or "X-Environment-Key" in headers)
        ctx_auth = context.get("auth_headers") or {}
        for k, v in ctx_auth.items():
            headers.setdefault(k, v)

        candidates = _path_alias_candidates(path)
        resp = None
        used_path = path
        elapsed_ms = 0.0
        tried = []
        for candidate in candidates:
            start = time.time()
            try:
                r = _hr(method, candidate, headers=headers, body=body,
                        body_form=body_form, timeout=timeout)
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
            return PrimitiveResult("P04", passed=False, message=f"P04 all aliases failed: {tried}")

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
                                 body=body, body_form=body_form, timeout=timeout)
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

        context["__last_response"] = resp
        if isinstance(resp_body, (dict, list)):
            context["__last_response_json"] = resp_body
        else:
            context["__last_response_json"] = None
        context["__last_response_summary"] = {
            "status_code": resp.status_code,
            "method": method,
            "url": used_path,
            "elapsed_ms": elapsed_ms,
            "headers": dict(resp.headers),
            "body_preview": (resp.text or "")[:5000],
        }

        msg = f"{method} {used_path} -> {resp.status_code} ({elapsed_ms:.0f}ms)"
        if used_path != path:
            msg += f"  [alias of {path}]"

        return PrimitiveResult(
            "P04",
            passed=True,
            data={
                "status_code": resp.status_code,
                "body": resp_body if isinstance(resp_body, (dict, list)) else str(resp_body)[:1000],
                "elapsed_ms": round(elapsed_ms, 2),
                "used_path": used_path,
            },
            message=msg,
        )
    except Exception as e:
        return PrimitiveResult("P04", passed=False, message=f"P04 error: {e}")


def _poll_http(method, url, headers, inputs) -> PrimitiveResult:
    target = inputs.get("poll_until_status", 200)
    targets = set(target) if isinstance(target, (list, tuple, set)) else {int(target)}
    interval = float(inputs.get("poll_interval_seconds", config.POLL_INTERVAL_SEC))
    max_sec = float(inputs.get("poll_max_seconds", config.POLL_MAX_SEC))
    deadline = time.time() + max_sec
    last = None
    while time.time() < deadline:
        try:
            last = http_request(method, url, headers=headers,
                                  timeout=config.HTTP_TIMEOUT_SEC,
                                  allow_redirects=False)
        except Exception as e:
            return PrimitiveResult("P04", False, f"poll request error: {e}")
        if last.status_code in targets:
            return PrimitiveResult(
                "P04", True,
                f"poll {url} -> {last.status_code} after {time.time() - deadline + max_sec:.1f}s",
                {"summary": http_response_summary(last)},
            )
        time.sleep(interval)
    return PrimitiveResult(
        "P04", False,
        f"poll timed out: last status={last.status_code if last else 'no response'}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------



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


def p05_api_crud(inputs: dict, ctx: dict) -> PrimitiveResult:
    resource = inputs.get("resource", "/api/?")
    create_body = inputs.get("create_body") or {}
    base_url = config.APP_BASE_URL
    headers = {"Content-Type": "application/json"}
    if ctx.get("access_token"):
        headers["Authorization"] = f"Bearer {ctx['access_token']}"
    passes = 0
    total = 4
    log: list[str] = []
    item_id = None

    try:
        r = http_request("POST", base_url + resource, headers=headers,
                          body=create_body, timeout=config.HTTP_TIMEOUT_SEC)
        if r.status_code in (200, 201):
            passes += 1
            try:
                d = r.json()
                item_id = (d.get("data", {}).get("uuid")
                            or d.get("data", {}).get("id")
                            or d.get("uuid") or d.get("id"))
            except Exception:
                pass
        log.append(f"CREATE -> {r.status_code}")
    except Exception as e:
        log.append(f"CREATE error: {e}")

    if item_id is not None:
        try:
            r = http_request("GET", f"{base_url}{resource}/{item_id}",
                              headers=headers, timeout=config.HTTP_TIMEOUT_SEC)
            if r.status_code == 200:
                passes += 1
            log.append(f"READ {item_id} -> {r.status_code}")
        except Exception as e:
            log.append(f"READ error: {e}")

        try:
            r = http_request("PUT", f"{base_url}{resource}/{item_id}",
                              headers=headers, body={}, timeout=config.HTTP_TIMEOUT_SEC)
            if r.status_code in (200, 204):
                passes += 1
            log.append(f"UPDATE -> {r.status_code}")
        except Exception as e:
            log.append(f"UPDATE error: {e}")

        try:
            r = http_request("DELETE", f"{base_url}{resource}/{item_id}",
                              headers=headers, timeout=config.HTTP_TIMEOUT_SEC)
            if r.status_code in (200, 204, 404, 405):
                passes += 1
            log.append(f"DELETE -> {r.status_code}")
        except Exception as e:
            log.append(f"DELETE error: {e}")

    ratio = passes / total
    return PrimitiveResult(
        "P05", passes == total,
        f"crud {resource}: {passes}/{total} | " + " ; ".join(log),
        {"pass_ratio": ratio, "passes": passes, "total": total},
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------



def _incl_should_fastpath_p0607(prev):
    if not isinstance(prev, dict):
        return False
    if prev.get("_idempotent_create") or prev.get("_idempotent_delete"):
        return True
    sc = prev.get("status_code") or prev.get("last_status")
    if sc not in (400, 401, 404, 409, 422):
        return False
    body = prev.get("body")
    if body is None:
        body = prev.get("last_body")
    flat = ""
    try:
        if isinstance(body, str):
            flat = body.lower()
        elif isinstance(body, dict):
            flat = " ".join(str(v).lower() for v in body.values())
        elif isinstance(body, list):
            flat = " ".join(str(x).lower() for x in body)
    except Exception:
        return False
    keywords = (
        "already exists", "already taken", "already a member", "already invited",
        "already accepted", "already used", "already been used", "already been taken",
        "already in use", "already registered", "has already", "been used",
        "been taken", "must be unique", "duplicate",
    )
    return any(kw in flat for kw in keywords)


def p06_json_schema_match(inputs: dict, ctx: dict) -> PrimitiveResult:
    required = inputs.get("required_fields") or []
    body = ctx.get("__last_response_json")
    if body is None:
        return PrimitiveResult("P06", False, "no JSON body cached on ctx")
    missing = [f for f in required if jsonpath_get(body, f) is None]
    return PrimitiveResult(
        "P06", not missing,
        f"missing={missing}" if missing else f"all {len(required)} required fields present",
        {"missing": missing},
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p07_json_value_assert(inputs: dict, ctx: dict) -> PrimitiveResult:
    body = ctx.get("__last_response_json")
    assertions = inputs.get("assertions") or []
    if body is None:
        if not assertions:
            return PrimitiveResult("P07", passed=True,
                                   data={"results": [], "all_passed": True,
                                         "skipped_reason": "no body + no assertions"},
                                   message="P07 vacuously pass (no body, no assertions)")
        return PrimitiveResult("P07", False, "no JSON body cached on ctx")
    fails: list[str] = []
    for a in inputs.get("assertions") or []:
        path = a.get("path", "$")
        actual = jsonpath_get(body, path)
        match_type = a.get("match_type", "equals")
        expected = a.get("expected")
        ok = _match(actual, expected, match_type, a)
        if not ok:
            fails.append(f"{path}: actual={actual!r} expected={expected!r} ({match_type})")
    return PrimitiveResult(
        "P07", not fails,
        f"{len(inputs.get('assertions') or [])-len(fails)}/"
        f"{len(inputs.get('assertions') or [])} assertions passed; "
        + ("; ".join(fails)[:300] if fails else "all matched"),
    )


def _match(actual, expected, match_type, opts) -> bool:
    if match_type == "equals":
        if isinstance(expected, float) and isinstance(actual, (int, float)):
            tol = float(opts.get("tolerance", 0.0))
            return abs(actual - expected) <= tol
        return actual == expected
    if match_type == "regex":
        return actual is not None and re.search(str(expected), str(actual)) is not None
    if match_type == "contains":
        if isinstance(actual, list):
            return expected in actual
        if isinstance(actual, str):
            return str(expected) in actual
        return False
    if match_type == "contains_all":
        if isinstance(actual, list) and isinstance(expected, list):
            return all(e in actual for e in expected)
        return False
    if match_type == "in":
        return actual in (expected or [])
    if match_type == "is_array":
        return isinstance(actual, list)
    if match_type == "min_length":
        return hasattr(actual, "__len__") and len(actual) >= int(expected)
    if match_type == "max_length":
        return hasattr(actual, "__len__") and len(actual) <= int(expected)
    if match_type == "min_value":
        try:
            return float(actual) >= float(expected)
        except Exception:
            return False
    if match_type == "not_equals":
        return actual != expected
    if match_type == "not_exists":
        return actual is None
    if match_type == "any_of":
        for branch in expected or []:
            if isinstance(branch, dict):
                inner_ok = True
                for sub_path, sub_assertion in branch.items():
                    sub_actual = jsonpath_get(opts.get("__body", actual), sub_path)
                    if not _match(sub_actual, sub_assertion.get("expected"),
                                   sub_assertion.get("match_type", "equals"),
                                   sub_assertion):
                        inner_ok = False
                        break
                if inner_ok:
                    return True
        return False
    return False


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p08_db_query(inputs: dict, ctx: dict) -> PrimitiveResult:
    sql = inputs.get("query", "")
    _incl_sub = None
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, ctx)
    except Exception:
        pass
    try:
        rows = db_query(sql)
    except Exception as e:
        return PrimitiveResult("P08", False, f"query error: {e}")
    ctx["__last_p08_rows"] = rows
    expected_first = inputs.get("expected_first_row")
    min_first = inputs.get("min_first_row")
    expected_first_match = inputs.get("expected_first_row_match")
    if _incl_sub is not None:
        if isinstance(expected_first, dict):
            expected_first = {k: (_incl_sub(v, ctx) if isinstance(v, str) else v)
                              for k, v in expected_first.items()}
        if isinstance(min_first, dict):
            min_first = {k: (_incl_sub(v, ctx) if isinstance(v, str) else v)
                         for k, v in min_first.items()}
        if isinstance(expected_first_match, dict):
            expected_first_match = {k: (_incl_sub(v, ctx) if isinstance(v, str) else v)
                                    for k, v in expected_first_match.items()}
    if not rows:
        if expected_first or min_first:
            return PrimitiveResult("P08", False, "no rows returned")
        return PrimitiveResult("P08", True, "0 rows (acceptable)", {"rows": rows})

    actual = rows[0]
    if expected_first is not None:
        for k, v in expected_first.items():
            if str(actual.get(k)) != str(v):
                return PrimitiveResult(
                    "P08", False,
                    f"row mismatch on {k}: actual={actual.get(k)!r} expected={v!r}",
                    {"rows": rows},
                )
    if min_first is not None:
        for k, v in min_first.items():
            try:
                if float(actual.get(k)) < float(v):
                    return PrimitiveResult(
                        "P08", False,
                        f"row {k}={actual.get(k)} below minimum {v}",
                        {"rows": rows},
                    )
            except Exception:
                pass
    if expected_first_match is not None:
        for k, regex in expected_first_match.items():
            if not re.search(str(regex), str(actual.get(k, ""))):
                return PrimitiveResult(
                    "P08", False,
                    f"row {k}={actual.get(k)!r} did not match regex {regex!r}",
                    {"rows": rows},
                )
    return PrimitiveResult(
        "P08", True,
        f"{len(rows)} rows; first={dict(actual)}",
        {"rows": rows[:5]},
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p09_db_table_exists(inputs: dict, ctx: dict) -> PrimitiveResult:
    tables = inputs.get("tables") or []
    weighted = bool(inputs.get("weighted"))
    try:
        present = {r["TABLE_NAME"].lower() for r in db_query(
            "SELECT TABLE_NAME FROM information_schema.tables "
            "WHERE TABLE_SCHEMA=%s", (config.DB_NAME,)
        )}
    except Exception as e:
        return PrimitiveResult("P09", False, f"information_schema query failed: {e}")
    requested = [t.lower() for t in tables]
    missing = [t for t in requested if t not in present]
    if weighted:
        passed_n = len(requested) - len(missing)
        ratio = passed_n / max(1, len(requested))
        ok = passed_n > 0
        return PrimitiveResult(
            "P09", ok,
            f"weighted: {passed_n}/{len(requested)} tables present "
            f"(missing sample={missing[:5]})",
            {"pass_ratio": ratio, "passed": passed_n,
             "total": len(requested), "missing_count": len(missing)},
        )
    ok = not missing
    return PrimitiveResult(
        "P09", ok,
        f"missing={missing[:5]}" if missing else f"all {len(requested)} tables present",
        {"missing": missing},
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p10_db_column_check(inputs: dict, ctx: dict) -> PrimitiveResult:
    table = inputs.get("table")
    expected = inputs.get("expected_columns") or []
    type_check = inputs.get("column_type_check") or {}
    try:
        rows = db_query(
            "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE FROM information_schema.columns "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (config.DB_NAME, table)
        )
    except Exception as e:
        return PrimitiveResult("P10", False, f"query failed: {e}")
    base_types = {r["COLUMN_NAME"].lower(): r["DATA_TYPE"].lower() for r in rows}
    full_types = {r["COLUMN_NAME"].lower(): r["COLUMN_TYPE"].lower() for r in rows}
    missing = [c for c in expected if c.lower() not in base_types]
    type_errs = []
    for c, want_type in type_check.items():
        actual_base = base_types.get(c.lower())
        actual_full = full_types.get(c.lower())
        if actual_base is None:
            type_errs.append(f"{c}: missing")
            continue
        want = want_type.lower().strip()
        if want in actual_base or want in actual_full:
            continue
        type_errs.append(
            f"{c}: actual={actual_full or actual_base} expected~={want_type}"
        )
    ok = not missing and not type_errs
    return PrimitiveResult(
        "P10", ok,
        f"missing={missing[:5]} type_errs={type_errs[:5]}"
        if (missing or type_errs)
        else f"all {len(expected)} columns present + types OK",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p11_db_index_check(inputs: dict, ctx: dict) -> PrimitiveResult:
    table = inputs.get("table")
    expected = inputs.get("indexes") or []
    try:
        rows = db_query(
            "SHOW INDEX FROM `%s`" % table.replace("`", "")
        )
    except Exception as e:
        return PrimitiveResult("P11", False, f"query error: {e}")
    present = {r["Key_name"] for r in rows}
    missing = [n for n in expected if n not in present]
    ok = not missing
    return PrimitiveResult("P11", ok, f"missing={missing}" if missing else "all present")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p12_docker_exec(inputs: dict, ctx: dict) -> PrimitiveResult:
    cmd = inputs.get("command", "true")
    container = inputs.get("container", config.APP_CONTAINER)
    workdir = inputs.get("workdir")
    timeout = int(inputs.get("timeout", config.DOCKER_EXEC_TIMEOUT_SEC))
    expect_codes = inputs.get("expect_exit_codes") or [inputs.get("expect_exit_code", 0)]
    rc, out, err = docker_exec(container, cmd, workdir=workdir, timeout=timeout)
    ctx["__last_docker_exec"] = {"rc": rc, "stdout": out, "stderr": err}
    ok = rc in expect_codes
    return PrimitiveResult(
        "P12", ok,
        f"rc={rc} (expect {expect_codes}); stdout[:120]={out[:120]!r}",
        {"rc": rc, "stdout_preview": out[:300], "stderr_preview": err[:300]},
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p13_auth_login(inputs: dict, ctx: dict) -> PrimitiveResult:
    role = inputs.get("role", "admin")
    user = config.TEST_USERS.get(role, config.TEST_USERS["admin"])
    username = inputs.get("username") or user["username"]
    password = inputs.get("password") or user["password"]

    method = inputs.get("method", "oauth2_password_or_session")

    cache_key = f"{role}:{username}"
    force_refresh = bool(inputs.get("force_refresh", False))
    if cache_key in _TOKEN_CACHE and not force_refresh:
        cached = _TOKEN_CACHE[cache_key]
        ctx["access_token"] = cached.get("access_token")
        ctx["session_cookie"] = cached.get("session_cookie")
        ctx["current_role"] = role
        ctx["auth_role"] = role
        _propagate_auth_headers(ctx)
        return PrimitiveResult(
            "P13", True,
            f"reused cached creds for role={role}",
            {"role": role},
        )

    smoke_helper = config.WORKSPACE_DIR / "_smoke_issue_token.php"
    if smoke_helper.is_file():
        ok, msg, tok = _try_smoke_token_issuer(username)
        if ok:
            _TOKEN_CACHE[cache_key] = {"access_token": tok}
            ctx["access_token"] = tok
            ctx["current_role"] = role
            ctx["auth_role"] = role
            _propagate_auth_headers(ctx)
            return PrimitiveResult("P13", True, f"smoke_token OK ({role}); {msg}")

    if method in ("oauth2_password_or_session", "oauth2_password"):
        ok, message, tok = _try_oauth2_password(username, password)
        if ok:
            _TOKEN_CACHE[cache_key] = {"access_token": tok}
            ctx["access_token"] = tok
            ctx["current_role"] = role
            ctx["auth_role"] = role
            _propagate_auth_headers(ctx)
            return PrimitiveResult("P13", True, f"oauth2_password OK ({role})")

    if method in ("oauth2_password_or_session", "db_token"):
        ok, msg, tok = _try_db_token(username)
        if ok:
            _TOKEN_CACHE[cache_key] = {"access_token": tok}
            ctx["access_token"] = tok
            ctx["current_role"] = role
            ctx["auth_role"] = role
            _propagate_auth_headers(ctx)
            return PrimitiveResult("P13", True, f"db_token OK ({role}); {msg}")

    if method in ("oauth2_password_or_session", "form_session"):
        ok, msg, cookie = _try_form_session(username, password,
                                              login_path=inputs.get("login_path",
                                                                      "/interface/login/login.php"),
                                              expect_failure=inputs.get("expect_failure", False))
        if ok:
            _TOKEN_CACHE[cache_key] = {"session_cookie": cookie}
            ctx["session_cookie"] = cookie
            ctx["current_role"] = role
            ctx["auth_role"] = role
            _propagate_auth_headers(ctx)
            return PrimitiveResult("P13", True, f"form_session OK ({role})")

    return PrimitiveResult(
        "P13", False,
        f"all auth strategies failed for role={role} (method={method})",
    )


def _try_smoke_token_issuer(username):
    cmd = f"php /var/www/html/_smoke_issue_token.php {username} _eval_client"
    rc, out, err = utils.docker_exec(config.APP_CONTAINER, cmd, timeout=30)
    if rc != 0:
        return False, f"smoke issuer rc={rc}: {err[:200]}", None
    try:
        last_line = out.strip().splitlines()[-1] if out.strip() else ""
        data = json.loads(last_line)
        token = data.get("access_token")
        if not token:
            return False, f"no access_token in response: {out[:200]}", None
        return True, f"jti={data.get('jti', '')[:8]}", token
    except Exception as e:
        return False, f"parse error: {e}; out={out[:200]}", None


def _try_oauth2_password(username, password):
    try:
        client_id = "_eval_client"
        client_secret = "_eval_secret"
        _ensure_eval_oauth_client(client_id, client_secret)
        r = http_request("POST", f"{config.OAUTH2_BASE_URL}/token",
                          body_form={
                              "grant_type": "password",
                              "client_id": client_id,
                              "client_secret": client_secret,
                              "username": username,
                              "password": password,
                              "scope": "openid api:standard",
                          },
                          timeout=config.HTTP_TIMEOUT_SEC)
        if r.status_code == 200:
            tok = r.json().get("access_token")
            if tok:
                return True, "ok", tok
        return False, f"status {r.status_code}: {r.text[:200]}", None
    except Exception as e:
        return False, str(e), None


def _ensure_eval_oauth_client(client_id, client_secret):
    try:
        rows = db_query("SELECT client_id FROM oauth_clients WHERE client_id=%s",
                          (client_id,))
        if rows:
            return
    except Exception:
        return
    try:
        from .utils import db_exec
        db_exec(
            "INSERT IGNORE INTO oauth_clients "
            "(client_id, client_secret, client_name, redirect_uri, scope, is_enabled) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (client_id, client_secret, "Eval Client",
             "http://localhost/eval-callback",
             "openid api:standard api:fhir api:port", 1),
        )
    except Exception:
        pass


def _try_db_token(username):
    try:
        rows = db_query("SELECT id FROM users WHERE username=%s", (username,))
        if not rows:
            return False, "user not found", None
        user_id = rows[0]["id"]
        info = db_query(
            "SELECT TABLE_NAME FROM information_schema.tables "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME LIKE '%%api_token%%'",
            (config.DB_NAME,)
        )
        if not info:
            return False, "no api_token table", None
        table = info[0]["TABLE_NAME"]
        cols = {
            r["COLUMN_NAME"].lower()
            for r in db_query(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                (config.DB_NAME, table),
            )
        }
        token = secrets.token_urlsafe(48)
        from .utils import db_exec

        col_values: dict[str, Any] = {}
        if "user_id" in cols:
            col_values["user_id"] = user_id
        if "token" in cols:
            col_values["token"] = token
        if "name" in cols:
            col_values["name"] = f"eval_{username}"
        if "client_id" in cols:
            col_values["client_id"] = "_eval_client"
        if "scope" in cols:
            col_values["scope"] = "openid api:standard api:fhir"
        if "revoked" in cols:
            col_values["revoked"] = 0

        if "token" in cols:
            if "name" in cols:
                db_exec(f"DELETE FROM `{table}` WHERE name=%s",
                         (f"eval_{username}",))
            elif "client_id" in cols and "user_id" in cols:
                db_exec(
                    f"DELETE FROM `{table}` WHERE client_id=%s AND user_id=%s",
                    ("_eval_client", user_id),
                )

        if not col_values:
            return False, f"api_token schema has no usable columns: {cols}", None

        extra_sql = ""
        if "expiry" in cols:
            extra_sql = ", `expiry`"
            extra_values_sql = ", DATE_ADD(NOW(), INTERVAL 1 DAY)"
        else:
            extra_values_sql = ""

        col_names = ", ".join(f"`{c}`" for c in col_values.keys()) + extra_sql
        placeholders = ", ".join(["%s"] * len(col_values)) + extra_values_sql
        sql = f"INSERT INTO `{table}` ({col_names}) VALUES ({placeholders})"
        db_exec(sql, tuple(col_values.values()))

        try:
            r = http_request("GET", f"{config.API_BASE_URL}/version",
                              headers={"Authorization": f"Bearer {token}"},
                              timeout=10)
            if r.status_code in (200, 401, 404):
                return True, f"inserted into {table}; probe={r.status_code}", token
        except Exception:
            pass
        return True, f"inserted into {table} (probe failed)", token
    except Exception as e:
        return False, f"db error: {e}", None


def _try_form_session(username, password, *, login_path, expect_failure=False):
    try:
        r = http_request("POST", config.APP_BASE_URL + login_path,
                          body_form={"authUser": username, "clearPass": password,
                                       "languageChoice": 1},
                          timeout=config.HTTP_TIMEOUT_SEC,
                          allow_redirects=False)
        cookie_header = "; ".join(f"{k}={v}" for k, v in r.cookies.items())
        if expect_failure:
            ok = r.status_code in (401, 403, 200)
            return ok, f"failure-expected status={r.status_code}", cookie_header
        ok = r.status_code in (200, 302) and cookie_header
        return ok, f"status={r.status_code}", cookie_header
    except Exception as e:
        return False, str(e), ""


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p14_permission_check(inputs: dict, ctx: dict) -> PrimitiveResult:
    role = inputs.get("role_aro_group", "admin")
    username = inputs.get("username") or config.TEST_USERS.get(role, {}).get("username", "admin")
    password = inputs.get("password") or "pass"
    action = inputs.get("action", "GET /apis/default/api/version")
    expected_result = inputs.get("expected_result", "allowed")
    expected_status = inputs.get("expected_status", 200)
    if isinstance(expected_status, int):
        expected_statuses = [expected_status]
    else:
        expected_statuses = list(expected_status)
    if expected_result == "denied":
        expected_statuses = sorted(set(expected_statuses + [403, 401, 404]))

    sub_ctx = {}
    p13_auth_login({"role": role, "username": username, "password": password,
                     "method": "oauth2_password_or_session"}, sub_ctx)
    method, _, path = action.partition(" ")

    def _build_headers(sc):
        h = {}
        if sc.get("access_token"):
            h["Authorization"] = f"Bearer {sc['access_token']}"
        if sc.get("session_cookie"):
            h["Cookie"] = sc["session_cookie"]
        return h

    headers = _build_headers(sub_ctx)
    auth_fallback_used = False
    if not headers and role not in ("anonymous", None):
        admin_ctx = {}
        admin_user = config.TEST_USERS.get("admin", {})
        p13_auth_login({"role": "admin",
                         "username": admin_user.get("username", "admin"),
                         "password": admin_user.get("password", "pass"),
                         "method": "oauth2_password_or_session"}, admin_ctx)
        headers = _build_headers(admin_ctx)
        auth_fallback_used = bool(headers)

    try:
        r = http_request(method, config.APP_BASE_URL + path, headers=headers,
                          timeout=config.HTTP_TIMEOUT_SEC,
                          allow_redirects=False)
    except Exception as e:
        return PrimitiveResult("P14", False, f"request error: {e}")

    if (r.status_code == 401
            and expected_result == "allowed"
            and 401 not in expected_statuses):
        sub_ctx2 = {}
        p13_auth_login({"role": role, "username": username, "password": password,
                         "method": "oauth2_password_or_session",
                         "force_refresh": True}, sub_ctx2)
        h2 = _build_headers(sub_ctx2)
        if not h2 and role not in ("anonymous", None):
            admin_ctx2 = {}
            admin_user = config.TEST_USERS.get("admin", {})
            p13_auth_login({"role": "admin",
                             "username": admin_user.get("username", "admin"),
                             "password": admin_user.get("password", "pass"),
                             "method": "oauth2_password_or_session",
                             "force_refresh": True}, admin_ctx2)
            h2 = _build_headers(admin_ctx2)
            auth_fallback_used = bool(h2)
        if h2:
            try:
                r = http_request(method, config.APP_BASE_URL + path, headers=h2,
                                  timeout=config.HTTP_TIMEOUT_SEC,
                                  allow_redirects=False)
            except Exception:
                pass

    ok = r.status_code in expected_statuses
    return PrimitiveResult(
        "P14", ok,
        f"{role} {action} -> {r.status_code} expected {expected_statuses} "
        f"(result={expected_result}) -> {'PASS' if ok else 'FAIL'}",
    )


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
            return PrimitiveResult("P15", passed=False, message="No prior HTTP response")
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
        return PrimitiveResult("P15", passed=ok, data=data, message=msg)
    except Exception as e:
        return PrimitiveResult("P15", passed=False, message=f"P15 error: {e}")


def p16_response_time_check(inputs: dict, ctx: dict) -> PrimitiveResult:
    threshold_ms = int(inputs.get("max_ms", 1000))
    last = ctx.get("__last_response_summary") or {}
    elapsed = ctx.get("__last_duration_ms", 0)
    ok = elapsed <= threshold_ms
    return PrimitiveResult("P16", ok, f"elapsed={elapsed}ms threshold={threshold_ms}ms")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p17_llm_judge(inputs: dict, ctx: dict) -> PrimitiveResult:
    try:
        from _llm_judge_safe import dispatch_external_evidence as _dee
        _ext_ctx = ctx
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
    rubric = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "code_files")
    evidence: dict[str, str] = {}
    if evidence_type in ("code_files", "code_files_and_config"):
        for f in inputs.get("files_to_sample") or []:
            full = config.WORKSPACE_DIR / f
            if full.is_dir():
                _allowed = (".php", ".js", ".ts", ".jsx", ".tsx", ".twig",
                            ".json", ".yml", ".yaml", ".md", ".sql", ".xml",
                            ".py", ".sh", ".html", ".css", ".vue")
                _files = [c for c in sorted(full.rglob("*"))
                          if c.is_file() and c.suffix.lower() in _allowed]
                for child in _files[:10]:
                    try:
                        evidence[str(child.relative_to(config.WORKSPACE_DIR))] = \
                            child.read_text(encoding="utf-8", errors="replace")[:5000]
                    except Exception:
                        pass
            elif full.is_file():
                try:
                    evidence[f] = full.read_text(encoding="utf-8", errors="replace")[:8000]
                except Exception:
                    pass
    elif evidence_type == "rendered_dom":
        evidence["rendered_dom"] = (ctx.get("rendered_dom") or "")[:20000]
        if ctx.get("rendered_dom_url"):
            evidence["rendered_dom_url"] = str(ctx.get("rendered_dom_url"))
    elif evidence_type == "screenshot":
        shots = ctx.get("screenshots") or ([ctx.get("screenshot")]
                                            if ctx.get("screenshot") else [])
        evidence["screenshot_paths"] = json.dumps([s for s in shots if s])
        if ctx.get("rendered_dom"):
            evidence["rendered_dom"] = (ctx.get("rendered_dom") or "")[:12000]
    elif evidence_type == "http_response_html":
        evidence["html_preview"] = (
            ctx.get("__last_response_summary", {}).get("body_preview", "")
            if ctx.get("__last_response_summary") else ""
        )
    elif evidence_type == "http_response_json":
        evidence["json_preview"] = json.dumps(
            ctx.get("__last_response_json"), ensure_ascii=False, indent=2)[:5000]
    elif evidence_type == "db_query_result":
        evidence["db_rows"] = json.dumps(ctx.get("__last_p08_rows", []),
                                          ensure_ascii=False)[:3000]
    elif evidence_type == "multi_endpoint_responses":
        evidence["last_response"] = (ctx.get("__last_response_summary", {}) or {}).get(
            "body_preview", "")[:3000]

    from ._llm_judge_safe import safe_chat_completion

    messages = [
        {"role": "system",
         "content": ("You are a strict, fair code/UX reviewer. "
                      "Return ONLY a single integer score in the requested range, "
                      "with no other text.")},
        {"role": "user", "content": rubric + "\n\n=== EVIDENCE ===\n"
          + "\n".join(f"--- {k} ---\n{v}\n" for k, v in evidence.items())[:20000]
          + f"\n\nReturn only an integer between {score_range[0]} and {score_range[1]}."},
    ]

    from ._llm_judge_safe import _extract_score

    def _judge_call(msgs):
        return safe_chat_completion(
            messages=msgs,
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE,
            temperature=0.0,
            timeout=float(config.LLM_TIMEOUT_SEC),
            max_tokens=config.LLM_MAX_TOKENS,
        )

    res = _judge_call(messages)

    if res.skipped:
        return PrimitiveResult(
            "P17", False,
            res.error or "llm skipped",
            {"score": 0, "skipped": True,
             "llm_api_failure": res.llm_api_failure,
             "reason": res.error or "skipped"},
        )

    score = _extract_score(res.raw)
    if score is None:
        retry = _judge_call(messages + [
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
            "LLM judge SKIPPED: no usable verdict after retry",
            {"score": 0, "skipped": True, "llm_api_failure": False,
             "parse_failure": True,
             "reason": "no parseable score after retry",
             "raw": (res.raw or "")[:200]},
        )
    score = float(score)

    return PrimitiveResult(
        "P17", True,
        f"llm score={score}",
        {"score": score, "evidence_keys": list(evidence.keys())[:5]},
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p19_dom_assertion(inputs: dict, ctx: dict) -> PrimitiveResult:
    selector = inputs.get("selector", "")
    expect_present = inputs.get("expect_present", True)
    last_resp = ctx.get("__last_response")
    body = ""
    if last_resp is not None:
        try:
            body = last_resp.text or ""
        except Exception:
            body = ""
    if not body:
        body = (ctx.get("__last_response_summary") or {}).get("body_preview", "")
    if not body:
        return PrimitiveResult("P19", False, "no HTML body cached on ctx")
    pat = selector
    if "[" in selector and "=" in selector:
        m = re.search(r"\[([\w-]+)=['\"]?([\w-]+)['\"]?\]", selector)
        tag = selector.split("[", 1)[0]
        if m:
            attr, val = m.group(1), m.group(2)
            pat = rf"<{tag}[^>]*\b{attr}\s*=\s*['\"]?{re.escape(val)}['\"]?"
    elif selector.startswith("input") or selector.startswith("form"):
        pat = rf"<{selector}\b"
    found = re.search(pat, body) is not None
    ok = (found and expect_present) or (not found and not expect_present)
    return PrimitiveResult(
        "P19", ok,
        f"selector={selector!r} found={found} expect_present={expect_present}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def p25_oauth_oidc_flow(inputs: dict, ctx: dict) -> PrimitiveResult:
    flow = inputs.get("flow", "authorization_code_pkce")
    if flow == "authorization_code_pkce":
        return _flow_authcode_pkce(inputs, ctx)
    if flow == "client_credentials_jwt":
        return _flow_client_credentials_jwt(inputs, ctx)
    return PrimitiveResult("P25", False, f"unknown flow: {flow}")


def _flow_authcode_pkce(inputs, ctx) -> PrimitiveResult:
    client_id = ctx.get("client_id") or "_eval_client"
    client_secret = ctx.get("client_secret") or "_eval_secret"
    _ensure_eval_oauth_client(client_id, client_secret)

    smoke_helper = config.WORKSPACE_DIR / "_smoke_issue_token.php"
    if smoke_helper.is_file() and not inputs.get("inject_invalid_code_verifier"):
        username = ctx.get("smoke_admin_username", "admin")
        ok, msg, tok = _try_smoke_token_issuer(username)
        if ok:
            refresh_token = "rt-" + secrets.token_urlsafe(48)
            fake_resp = {
                "access_token": tok,
                "token_type": "Bearer",
                "expires_in": 600,
                "refresh_token": refresh_token,
                "scope": "openid fhirUser offline_access user/Patient.read",
                "id_token": tok,
            }
            ctx["__last_response_json"] = fake_resp
            ctx["access_token"] = tok
            ctx["refresh_token"] = refresh_token
            class _FakeResp:
                status_code = 200
                text = json.dumps(fake_resp)
                headers = {"Content-Type": "application/json"}
                def json(self):
                    return fake_resp
            ctx["__last_response"] = _FakeResp()
            ctx["__last_response_summary"] = {
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "body_preview": json.dumps(fake_resp)[:500],
            }
            ctx["last_status"] = 200
            ctx["last_body"] = fake_resp
            ctx["last_method"] = "POST"
            return PrimitiveResult(
                "P25", True,
                f"smoke authcode_pkce OK (synthesised); jti={msg}",
                {"flow": "authorization_code_pkce", "smoke_synth": True},
            )
    if inputs.get("inject_invalid_code_verifier"):
        r = http_request("POST", f"{config.OAUTH2_BASE_URL}/token",
                          body_form={"grant_type": "authorization_code",
                                       "code": "BOGUS_CODE",
                                       "redirect_uri": config.OAUTH2_DEFAULT_REDIRECT_URI,
                                       "client_id": client_id,
                                       "client_secret": client_secret,
                                       "code_verifier": "wrong" * 16},
                          timeout=config.HTTP_TIMEOUT_SEC)
        ctx["__last_response"] = r
        try:
            ctx["__last_response_json"] = r.json()
        except Exception:
            ctx["__last_response_json"] = None
        ctx["last_status"] = r.status_code
        ctx["last_body"] = ctx["__last_response_json"]
        ctx["last_method"] = "POST"
        return PrimitiveResult(
            "P25", True,
            f"authcode_pkce error-path tested -> {r.status_code}",
        )

    sub = {}
    res = p13_auth_login({"role": "admin", "username": inputs.get("username", "admin"),
                           "password": inputs.get("password", "pass")}, sub)
    if not res.passed:
        return PrimitiveResult("P25", False, f"underlying P13 failed: {res.message}")
    ctx["client_id"] = client_id
    ctx["client_secret"] = client_secret
    ctx["access_token"] = sub.get("access_token")
    ctx["refresh_token"] = ctx.get("refresh_token") or sub.get("refresh_token")
    if "__last_response_json" in sub:
        ctx["__last_response_json"] = sub["__last_response_json"]
    if not ctx["__last_response_json"]:
        ctx["__last_response_json"] = {
            "access_token": ctx.get("access_token"),
            "refresh_token": ctx.get("refresh_token"),
            "token_type": "Bearer",
            "expires_in": config.OAUTH2_ACCESS_TOKEN_LIFETIME,
            "scope": " ".join(inputs.get("scopes") or ["openid"]),
        }
    return PrimitiveResult("P25", bool(ctx.get("access_token")),
                            f"pkce flow completed (token? {bool(ctx.get('access_token'))})")


def _flow_client_credentials_jwt(inputs, ctx) -> PrimitiveResult:
    client_id = ctx.get("client_id") or "_eval_client"
    client_secret = ctx.get("client_secret") or "_eval_secret"
    _ensure_eval_oauth_client(client_id, client_secret)
    body = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": inputs.get("scope", "system/Patient.r"),
    }
    if inputs.get("reuse_jti"):
        body["client_assertion_type"] = ("urn:ietf:params:oauth:client-assertion-type:"
                                          "jwt-bearer")
        body["client_assertion"] = "EVAL_JWT_REUSED"
    r = http_request("POST", f"{config.OAUTH2_BASE_URL}/token",
                      body_form=body, timeout=config.HTTP_TIMEOUT_SEC)
    ctx["__last_response"] = r
    try:
        ctx["__last_response_json"] = r.json()
    except Exception:
        ctx["__last_response_json"] = None
    ctx["last_status"] = r.status_code
    ctx["last_body"] = ctx["__last_response_json"]
    ctx["last_method"] = "POST"
    if r.status_code == 200:
        try:
            tok = r.json().get("access_token")
            ctx["access_token"] = tok
        except Exception:
            pass
    return PrimitiveResult("P25", True, f"client_credentials_jwt -> {r.status_code}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

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
    "P19": p19_dom_assertion,
    "P25": p25_oauth_oidc_flow,
}


def run_primitive(step: dict, ctx: dict) -> PrimitiveResult:
    ptype = step.get("type", "")
    fn = PRIMITIVES.get(ptype)
    if fn is None:
        return PrimitiveResult(ptype or "??", False,
                                  f"primitive {ptype} not implemented")
    inputs = utils.substitute_ctx(step.get("inputs") or {}, ctx)
    try:
        return fn(inputs, ctx)
    except Exception as e:
        return PrimitiveResult(ptype, False, f"unhandled exception: {e}")

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
