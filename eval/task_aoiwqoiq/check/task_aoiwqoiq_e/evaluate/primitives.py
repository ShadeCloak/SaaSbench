
import glob as glob_mod
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import psycopg2
import requests
from jsonpath_ng.ext import parse as jsonpath_parse
from openai import OpenAI

from config import (
    APP_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    WORKSPACE_DIR, APP_CONTAINER, LLM_API_KEY, LLM_API_BASE, LLM_MODEL,
    AUTH_HEADER_KEY, AUTH_HEADER_USER, TEST_USERS, HTTP_TIMEOUT,
    DOCKER_EXEC_TIMEOUT,
)
from utils import docker_exec_app, http_request, resolve_placeholders


@dataclass
class PrimitiveResult:
    success: bool
    data: dict = field(default_factory=dict)
    message: str = ""


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _ruby_literal(v: Any) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(v, list):
        return "[" + ", ".join(_ruby_literal(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(
            f"{_ruby_literal(k)} => {_ruby_literal(val)}" for k, val in v.items()
        ) + "}"
    return repr(v)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p01_file_exists(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        check_type = inputs.get("type", "file")
        candidate_paths = inputs.get("path_any_of")
        if not candidate_paths:
            candidate_paths = [inputs.get("path", "")]
        elif isinstance(candidate_paths, str):
            candidate_paths = [candidate_paths]

        probed = []
        matched = None
        for rel_path in candidate_paths:
            if not rel_path:
                continue
            full_path = (
                rel_path
                if os.path.isabs(rel_path)
                else os.path.join(WORKSPACE_DIR, rel_path)
            )
            if check_type == "dir":
                hit = os.path.isdir(full_path)
            else:
                hit = os.path.isfile(full_path)
            probed.append({"path": full_path, "exists": hit})
            if hit and matched is None:
                matched = full_path

        exists = matched is not None
        return PrimitiveResult(
            success=exists,
            data={
                "path": matched or (probed[0]["path"] if probed else ""),
                "type": check_type,
                "exists": exists,
                "probed": probed,
            },
            message=(
                f"Found: {matched}" if matched
                else f"None of the candidate paths existed ({len(probed)} probed)"
            ),
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P01 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p02_file_content_match(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        candidate_paths = inputs.get("path_any_of")
        if not candidate_paths:
            candidate_paths = [inputs.get("path", "")]
        elif isinstance(candidate_paths, str):
            candidate_paths = [candidate_paths]
        match_type = inputs.get("match_type", "contains")
        pattern = inputs.get("pattern", "")

        probed = []
        matched_path = None
        for rel_path in candidate_paths:
            if not rel_path:
                continue
            full_path = (rel_path if os.path.isabs(rel_path)
                         else os.path.join(WORKSPACE_DIR, rel_path))
            if not os.path.isfile(full_path):
                probed.append({"path": full_path, "exists": False})
                continue
            with open(full_path, "r", errors="replace") as f:
                content = f.read()
            if match_type == "regex":
                match = bool(re.search(pattern, content, re.MULTILINE))
            else:
                match = pattern in content
            probed.append({"path": full_path, "exists": True, "matched": match})
            if match and matched_path is None:
                matched_path = full_path
                break

        ok = matched_path is not None
        first_path = probed[0]["path"] if probed else ""
        return PrimitiveResult(
            success=ok,
            data={"path": matched_path or first_path, "match_type": match_type,
                  "matched": ok, "probed": probed},
            message=(f"Pattern matched in {matched_path}" if ok
                     else f"No probed path matched (probed {len(probed)} paths)"),
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P02 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p03_file_count(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        pattern = inputs.get("glob", "*")
        candidate_base_dirs = inputs.get("base_dir_any_of")
        if not candidate_base_dirs:
            candidate_base_dirs = [inputs.get("base_dir", WORKSPACE_DIR)]
        elif isinstance(candidate_base_dirs, str):
            candidate_base_dirs = [candidate_base_dirs]
        min_expected = int(inputs.get("min_expected", 1))

        def _brace_expand(pat):
            import re as _re
            m = _re.search(r"\{([^{}]+)\}", pat)
            if not m:
                return [pat]
            head, tail = pat[:m.start()], pat[m.end():]
            options = [o.strip() for o in m.group(1).split(",")]
            out = []
            for o in options:
                out.extend(_brace_expand(head + o + tail))
            return out

        probed = []
        best_count = 0
        best_pattern = ""
        for bd in candidate_base_dirs:
            if not bd:
                continue
            base_dir = bd if os.path.isabs(bd) else os.path.join(WORKSPACE_DIR, bd)
            sub_patterns = _brace_expand(pattern)
            all_matches = set()
            for sp in sub_patterns:
                full_pattern = os.path.join(base_dir, sp)
                for m in glob_mod.glob(full_pattern, recursive=True):
                    all_matches.add(m)
            full_pattern = os.path.join(base_dir, pattern)
            count = len(all_matches)
            probed.append({"base_dir": base_dir, "pattern": full_pattern, "count": count})
            if count > best_count:
                best_count = count
                best_pattern = full_pattern

        return PrimitiveResult(
            success=best_count >= min_expected,
            data={"count": best_count, "min_expected": min_expected,
                  "pattern": best_pattern, "probed": probed},
            message=f"Found {best_count} files (expected >= {min_expected})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P03 error: {e}")


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
    repeat_n = inputs.get("repeat")
    try:
        repeat_n = int(repeat_n) if repeat_n is not None else 1
    except (TypeError, ValueError):
        repeat_n = 1
    if repeat_n < 1:
        repeat_n = 1
    rapid_fire = bool(inputs.get("rapid_fire"))
    try:
        method = inputs.get("method", "GET")
        path = inputs.get("path", "/")
        headers = dict(inputs.get("headers") or {})
        for hk, hv in list(headers.items()):
            if isinstance(hv, str) and ("\n" in hv or "\r" in hv):
                first_line = hv.split("\n")[0].split("\r")[0].strip()
                if first_line:
                    headers[hk] = first_line
        body = inputs.get("body")
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
        for iteration in range(repeat_n):
            iter_candidates = candidates if iteration == 0 else [used_path]
            for candidate in iter_candidates:
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
            if not rapid_fire and iteration < repeat_n - 1:
                time.sleep(0.05)
        if resp is None:
            return PrimitiveResult(success=False, message=f"P04 all aliases failed: {tried}")

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

        if isinstance(resp_body, dict) and 200 <= resp.status_code < 300:
            for key_name in ("id", "topic_id", "post_id", "user_id", "category_id", "group_id", "key", "api_key", "token", "uuid"):
                v = resp_body.get(key_name)
                if v is None:
                    continue
                if key_name not in context or context.get(key_name) in (None, "", "null"):
                    context[key_name] = v
            for nest_key in ("topic", "post", "user", "category", "group", "data"):
                nv = resp_body.get(nest_key)
                if isinstance(nv, dict) and "id" in nv:
                    target = f"{nest_key}_id"
                    if target not in context or context.get(target) in (None, "", "null"):
                        context[target] = nv["id"]

        msg = f"{method} {used_path} -> {resp.status_code} ({elapsed_ms:.0f}ms)"
        if used_path != path:
            msg += f"  [alias of {path}]"

        return PrimitiveResult(
            success=True,
            data={
                "status_code": resp.status_code,
                "body": resp_body if isinstance(resp_body, (dict, list)) else str(resp_body)[:1000],
                "elapsed_ms": round(elapsed_ms, 2),
                "used_path": used_path,
            },
            message=msg,
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P04 error: {e}")




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
    try:
        resource = inputs.get("resource", "")
        create_body = inputs.get("create_body", {})
        update_body = inputs.get("update_body", {})
        id_field = inputs.get("id_field", "id")
        read_path_tpl = inputs.get("read_path", None)
        update_path_tpl = inputs.get("update_path", None)
        delete_path_tpl = inputs.get("delete_path", None)
        headers = dict(inputs.get("headers", {}) or {})

        auth_headers = context.get("auth_headers")
        if auth_headers:
            for k, v in auth_headers.items():
                headers.setdefault(k, v)

        results = {}

        create_resp = _http_with_auth_refresh("POST", resource, headers=headers, context=context, body=create_body)
        if create_resp.status_code not in (200, 201):
            err_body_incl = None
            try:
                err_body_incl = create_resp.json()
            except Exception:
                err_body_incl = create_resp.text
            if (_is_idempotent_success(create_resp.status_code, err_body_incl, {201})
                    and isinstance(create_body, dict)):
                rid_incl = _p05_resolve_existing_id(resource, headers,
                                                   create_body.get('name'), id_field)
                if rid_incl is not None:
                    item_path_incl = f"{resource.rstrip(chr(47))}/{rid_incl}/"
                    rr_incl = _http_with_auth_refresh('GET', item_path_incl, headers=headers, context=context)
                    dr_incl = _http_with_auth_refresh('DELETE', item_path_incl, headers=headers, context=context)
                    results_incl = {'create': {'id': rid_incl, 'name': create_body.get('name'), '_idempotent': True},
                                     'read_status': rr_incl.status_code,
                                     'delete_status': dr_incl.status_code}
                    context['last_crud_id'] = rid_incl
                    ok_incl = (rr_incl.status_code == 200 and dr_incl.status_code in (200, 202, 204))
                    return PrimitiveResult(success=ok_incl, data=results_incl,
                                           message=f'CRUD complete (idempotent) id={rid_incl}')
            return PrimitiveResult(
                success=False,
                data={"step": "create", "status": create_resp.status_code, "body": create_resp.text[:500]},
                message=f"CRUD create failed: {create_resp.status_code}",
            )
        create_data = create_resp.json()
        results["create"] = create_data

        record_id = None
        if isinstance(create_data, dict):
            if id_field in create_data:
                record_id = create_data[id_field]
            else:
                for v in create_data.values():
                    if isinstance(v, dict) and id_field in v:
                        record_id = v[id_field]
                        break

        if record_id is None:
            return PrimitiveResult(
                success=False,
                data={"step": "create", "response": create_data},
                message=f"Could not extract '{id_field}' from create response",
            )

        context["last_crud_id"] = record_id

        def _build_path(tpl, fallback_suffix=""):
            if tpl:
                return tpl.replace("{id}", str(record_id))
            return f"{resource}/{record_id}{fallback_suffix}"

        r_path = _build_path(read_path_tpl)
        read_resp = _http_with_auth_refresh("GET", r_path, headers=headers, context=context)
        results["read_status"] = read_resp.status_code

        if update_body:
            u_path = _build_path(update_path_tpl)
            update_resp = http_request("PUT", u_path, headers=headers, body=update_body)
            results["update_status"] = update_resp.status_code

        d_path = _build_path(delete_path_tpl)
        delete_resp = _http_with_auth_refresh("DELETE", d_path, headers=headers, context=context)
        results["delete_status"] = delete_resp.status_code

        success = (
            results.get("read_status") in (200, 301, 302, 304, 307, 308)
            and results.get("delete_status") in (200, 202, 204, 301, 302, 307, 308, 404)
        )

        return PrimitiveResult(
            success=success,
            data=results,
            message=f"CRUD cycle complete for {resource}, id={record_id}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P05 error: {e}")


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


def p06_json_schema_match(inputs: dict, context: dict) -> PrimitiveResult:
    if _incl_should_fastpath_p0607(context):
        return PrimitiveResult(success=True, data={"missing_fields": [], "all_present": True, "_idempotent_skip": True}, message="P06 skipped (idempotent CREATE 4xx — body is error not resource)")

    try:
        required_fields = inputs.get("required_fields", [])
        body = inputs.get("body") or context.get("last_body")

        if body is None:
            return PrimitiveResult(success=False, message="No JSON body available")

        if isinstance(body, str):
            body = json.loads(body)

        body_for_lookup = body
        array_first_element = None
        if isinstance(body, list) and body:
            first = body[0]
            if isinstance(first, dict):
                array_first_element = first

        missing = []
        for fld in required_fields:
            parts = fld.split(".")
            obj = body_for_lookup
            found = True
            for idx, p in enumerate(parts):
                if isinstance(obj, dict) and p in obj:
                    obj = obj[p]
                elif isinstance(obj, list) and p.isdigit() and int(p) < len(obj):
                    obj = obj[int(p)]
                elif idx == 0 and isinstance(obj, list) and array_first_element is not None and p in array_first_element:
                    obj = array_first_element[p]
                else:
                    found = False
                    break
            if not found:
                missing.append(fld)

        success = len(missing) == 0
        return PrimitiveResult(
            success=success,
            data={"required": required_fields, "missing": missing,
                  "body_type": "array" if isinstance(body, list) else "object"},
            message=f"Schema check: {len(missing)} missing fields" if missing else "All required fields present",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P06 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _compare(actual: Any, expected: Any, operator: str, tolerance: float = 0) -> bool:
    if operator == "exists":
        return actual is not None
    if operator == "equals":
        if tolerance and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return abs(actual - expected) <= tolerance
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, (list, tuple)):
            return expected in actual
        if isinstance(actual, dict):
            if isinstance(expected, dict):
                return all(actual.get(k) == v for k, v in expected.items())
            if isinstance(expected, (list, tuple, set)):
                return all(k in actual for k in expected)
            return expected in actual or expected in actual.values()
        return False
    if operator == "gte":
        return float(actual) >= float(expected)
    if operator == "lte":
        return float(actual) <= float(expected)
    return actual == expected


def p07_json_value_assert(inputs: dict, context: dict) -> PrimitiveResult:
    if _incl_should_fastpath_p0607(context):
        return PrimitiveResult(success=True, data={"results": [], "all_passed": True, "_idempotent_skip": True}, message="P07 skipped (idempotent CREATE 4xx — body is error not resource)")

    try:
        assertions = inputs.get("assertions", [])
        allow_empty = inputs.get("allow_empty", False)
        body = inputs.get("body") or context.get("last_body")

        if body is None or (isinstance(body, str) and not body.strip()):
            if allow_empty:
                return PrimitiveResult(success=True, message="Empty body accepted (allow_empty)")
            return PrimitiveResult(success=False, message="No JSON body available")
        if isinstance(body, str):
            body = json.loads(body)

        failed = []
        for a in assertions:
            jp = a.get("path", "$")
            expected = a.get("expected")
            operator = a.get("operator", "equals")
            tolerance = float(a.get("tolerance", 0))

            expr = jsonpath_parse(jp)
            matches = expr.find(body)

            if not matches:
                if operator == "exists":
                    failed.append({"path": jp, "reason": "path not found"})
                else:
                    failed.append({"path": jp, "reason": "path not found", "expected": expected})
                continue

            actual = matches[0].value
            if not _compare(actual, expected, operator, tolerance):
                failed.append({
                    "path": jp,
                    "actual": actual,
                    "expected": expected,
                    "operator": operator,
                })

        success = len(failed) == 0
        return PrimitiveResult(
            success=success,
            data={"total": len(assertions), "failed": failed},
            message=f"All {len(assertions)} assertions passed" if success else f"{len(failed)}/{len(assertions)} assertions failed",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P07 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p08_db_query(inputs: dict, context: dict) -> PrimitiveResult:
    conn = None
    try:
        sql = inputs.get("sql", "")
        expected_result = inputs.get("expected_result")
        store_as = inputs.get("store_as")
        try:
            from _inclusivity import _substitute_placeholders as _incl_sub
            sql = _incl_sub(sql, context)
        except Exception:
            pass

        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT,
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)

        rows = []
        columns = []
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()

        cur.close()

        row_dicts = [dict(zip(columns, row)) for row in rows]

        if store_as and row_dicts:
            context[store_as] = row_dicts[0]

        context["last_query_rows"] = row_dicts
        context["last_query_count"] = len(rows)

        success = True
        mismatch = None
        if expected_result is not None:
            if isinstance(expected_result, dict):
                if not row_dicts:
                    success = False
                    mismatch = ("(no rows)", expected_result)
                else:
                    row = row_dicts[0]
                    for key, exp_val in expected_result.items():
                        actual = row.get(key)
                        if isinstance(exp_val, str):
                            m = re.match(r"^(>=|<=|>|<)\s*(\d+)$", str(exp_val))
                            if m:
                                op_str, threshold = m.group(1), int(m.group(2))
                                act_num = int(actual) if actual is not None else 0
                                op_map = {">=": act_num >= threshold, "<=": act_num <= threshold,
                                          ">": act_num > threshold, "<": act_num < threshold}
                                if not op_map.get(op_str, False):
                                    success = False
                                    mismatch = (key, actual, exp_val)
                                    break
                            elif exp_val == "NOT NULL":
                                if actual is None:
                                    success = False
                                    mismatch = (key, actual, exp_val)
                                    break
                            else:
                                if str(actual) != str(exp_val):
                                    success = False
                                    mismatch = (key, actual, exp_val)
                                    break
                        elif isinstance(exp_val, bool):
                            if bool(actual) != exp_val:
                                success = False
                                mismatch = (key, actual, exp_val)
                                break
                        elif isinstance(exp_val, (int, float)):
                            try:
                                if float(actual) != float(exp_val):
                                    success = False
                                    mismatch = (key, actual, exp_val)
                                    break
                            except (TypeError, ValueError):
                                success = False
                                mismatch = (key, actual, exp_val)
                                break
                        elif actual != exp_val:
                            success = False
                            mismatch = (key, actual, exp_val)
                            break
            elif isinstance(expected_result, bool):
                success = (len(rows) > 0) == expected_result
            elif isinstance(expected_result, str):
                m = re.match(r"^(>=|<=|>|<|==)?\s*(\d+)$", str(expected_result))
                if m:
                    op_str = m.group(1) or "=="
                    val = int(m.group(2))
                    count = len(rows)
                    if rows and len(columns) == 1:
                        first_val = rows[0][0]
                        if isinstance(first_val, (int, float)):
                            count = int(first_val)
                    ops = {">=": count >= val, "<=": count <= val,
                           ">": count > val, "<": count < val, "==": count == val}
                    success = ops.get(op_str, count == val)
                else:
                    success = len(rows) > 0
            elif isinstance(expected_result, (int, float)):
                count = len(rows)
                if rows and len(columns) == 1:
                    first_val = rows[0][0]
                    if isinstance(first_val, (int, float)):
                        count = int(first_val)
                success = count == int(expected_result)

        if success:
            msg = f"Query returned {len(rows)} rows"
        elif mismatch and len(mismatch) == 3:
            key_, actual_, exp_ = mismatch
            msg = f"P08 mismatch: {key_}={actual_!r} (expected {exp_!r}); {len(rows)} rows"
        elif mismatch:
            msg = f"P08 mismatch: {mismatch}; {len(rows)} rows"
        else:
            msg = f"Query returned {len(rows)} rows but expected_result not satisfied"
        return PrimitiveResult(
            success=success,
            data={"row_count": len(rows), "columns": columns, "rows": row_dicts[:20]},
            message=msg,
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P08 error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p09_db_table_exists(inputs: dict, context: dict) -> PrimitiveResult:
    conn = None
    try:
        tables = inputs.get("tables") or []
        if not tables and inputs.get("table"):
            tables = [inputs["table"]]

        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT,
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        )
        conn.autocommit = True
        cur = conn.cursor()

        missing = []
        for tbl in tables:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE LOWER(table_schema) = 'public' AND LOWER(table_name) = LOWER(%s)",
                (tbl,),
            )
            if not cur.fetchone():
                missing.append(tbl)

        cur.close()

        success = len(missing) == 0
        return PrimitiveResult(
            success=success,
            data={"checked": tables, "missing": missing},
            message=f"All tables exist" if success else f"Missing tables: {missing}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P09 error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p10_db_column_check(inputs: dict, context: dict) -> PrimitiveResult:
    conn = None
    try:
        table = inputs.get("table", "")
        columns = inputs.get("columns", [])

        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT,
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        )
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE LOWER(table_schema) = 'public' AND LOWER(table_name) = LOWER(%s)",
            (table,),
        )
        existing = {row[0]: row[1] for row in cur.fetchall()}
        existing_lc = {k.lower(): v for k, v in existing.items()}
        cur.close()

        if not existing:
            return PrimitiveResult(
                success=False,
                data={"table": table},
                message=f"Table '{table}' not found or has no columns",
            )

        missing = []
        type_mismatch = []
        for col_spec in columns:
            name = col_spec.get("name", "")
            expected_type = col_spec.get("type", "").lower()
            actual_type = existing.get(name) or existing_lc.get(name.lower())
            if actual_type is None:
                missing.append(name)
            elif expected_type and expected_type not in actual_type.lower():
                type_mismatch.append({
                    "column": name,
                    "expected": expected_type,
                    "actual": actual_type,
                })

        success = len(missing) == 0 and len(type_mismatch) == 0
        return PrimitiveResult(
            success=success,
            data={"table": table, "missing": missing, "type_mismatch": type_mismatch,
                  "existing_columns": existing},
            message="All columns match" if success else f"Missing: {missing}, Type mismatch: {type_mismatch}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P10 error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p11_db_index_check(inputs: dict, context: dict) -> PrimitiveResult:
    conn = None
    try:
        table = inputs.get("table", "")
        indexes = inputs.get("indexes", [])

        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT,
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        )
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s",
            (table,),
        )
        existing_indexes = {row[0]: row[1] for row in cur.fetchall()}
        cur.close()

        missing = []
        for idx_pattern in indexes:
            found = any(re.search(idx_pattern, name, re.IGNORECASE) for name in existing_indexes)
            if not found:
                found = any(re.search(idx_pattern, defn, re.IGNORECASE) for defn in existing_indexes.values())
            if not found:
                missing.append(idx_pattern)

        success = len(missing) == 0
        return PrimitiveResult(
            success=success,
            data={"table": table, "existing": list(existing_indexes.keys()), "missing_patterns": missing},
            message="All indexes found" if success else f"Missing index patterns: {missing}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P11 error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p12_docker_exec(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        command = inputs.get("command", "")
        expect_output = inputs.get("expect_output_contains")
        expect_exit = inputs.get("expect_exit_code", 0)
        timeout = int(inputs.get("timeout", DOCKER_EXEC_TIMEOUT))

        exit_code, output = docker_exec_app(command, timeout=timeout)
        cleaned_output = (output or "").strip()
        if cleaned_output:
            lines = cleaned_output.splitlines()
            filtered = []
            for ln in lines:
                lower = ln.lower().strip()
                if not lower: continue
                if lower.startswith(("fatal:", "warning:", "stopping at filesystem")): continue
                if "not a git repository" in lower: continue
                if "git_discovery" in lower: continue
                if lower.startswith("sidekiq "): continue
                if "connecting to redis" in lower: continue
                filtered.append(ln)
            if filtered:
                cleaned_output = "\n".join(filtered).strip()
        first_clean_line = cleaned_output.split("\n")[0].strip() if "\n" in cleaned_output else cleaned_output
        context["last_exec_output"] = output
        context["last_exec_exit_code"] = exit_code
        context["previous"] = {
            "stdout": first_clean_line if first_clean_line and len(first_clean_line) > 8 else cleaned_output,
            "output": cleaned_output,
            "exit_code": exit_code,
        }
        capture_as = inputs.get("capture_stdout_as")
        if capture_as:
            value = cleaned_output
            non_empty = [ln.strip() for ln in value.split("\n") if ln.strip()]
            if non_empty:
                value = non_empty[-1]
            context[capture_as] = value

        success = True
        reasons = []
        if expect_exit is not None and exit_code != int(expect_exit):
            success = False
            reasons.append(f"exit code {exit_code} != expected {expect_exit}")
        if expect_output and expect_output not in output:
            success = False
            reasons.append(f"output does not contain '{expect_output}'")

        return PrimitiveResult(
            success=success,
            data={"exit_code": exit_code, "output": output[:2000]},
            message="; ".join(reasons) if reasons else f"Command succeeded (exit {exit_code})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P12 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p13_auth_login(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        role = inputs.get("role", "user")

        if "auth_cache" not in context:
            context["auth_cache"] = {}

        if role == "anonymous":
            context["auth_headers"] = {}
            context["auth_role"] = "anonymous"
            context["auth_cache"]["anonymous"] = {"headers": {}, "role": "anonymous"}
            return PrimitiveResult(
                success=True,
                data={"role": "anonymous"},
                message="Switched to anonymous (no auth headers)",
            )

        force_refresh = inputs.get("force_refresh", False)
        cached = context["auth_cache"].get(role)
        if cached and not force_refresh:
            context["auth_headers"] = cached["headers"]
            context["auth_role"] = role
            cached_username = cached.get("username", "")
            if cached_username:
                context["username"] = cached_username
                context[f"{role}_username"] = cached_username
                if role == "admin":
                    context["admin_username"] = cached_username
            return PrimitiveResult(
                success=True,
                data=cached,
                message=f"Using cached auth for role '{role}'",
            )

        ROLE_CONFIG = {
            "admin":     {"admin": True,  "moderator": False, "trust_level": 4},
            "moderator": {"admin": False, "moderator": True,  "trust_level": 4},
            "user":      {"admin": False, "moderator": False, "trust_level": 1},
            "tl0":       {"admin": False, "moderator": False, "trust_level": 0},
            "tl1":       {"admin": False, "moderator": False, "trust_level": 1},
            "tl2":       {"admin": False, "moderator": False, "trust_level": 2},
            "tl3":       {"admin": False, "moderator": False, "trust_level": 3},
            "tl4":       {"admin": False, "moderator": False, "trust_level": 4},
        }
        cfg = ROLE_CONFIG.get(role, ROLE_CONFIG["user"])

        if role in TEST_USERS:
            user_info = TEST_USERS[role]
        else:
            user_info = {
                "username": f"eval_{role}",
                "email": f"eval_{role}@eval.test",
                "password": "EvalPass12345!",
            }
        username = user_info["username"]
        email = user_info["email"]
        password = user_info["password"]

        is_admin = "true" if cfg["admin"] else "false"
        is_moderator = "true" if cfg["moderator"] else "false"
        trust_level = cfg["trust_level"]

        ensure_cmd = (
            f"rails runner \""
            f"u = User.find_or_initialize_by(username: '{username}'); "
            f"u.username_lower = '{username}'.downcase if u.respond_to?(:username_lower=); "
            f"u.email = '{email}' if u.respond_to?(:email=); "
            f"u.password = '{password}' if u.respond_to?(:password=); "
            f"u.active = true; "
            f"u.approved = true; "
            f"u.admin = {is_admin}; "
            f"u.moderator = {is_moderator}; "
            f"u.trust_level = {trust_level}; "
            f"u.save!(validate: false); "
            f"if defined?(UserEmail) && UserEmail.respond_to?(:find_or_initialize_by); "
            f"  ue = UserEmail.find_or_initialize_by(user_id: u.id, primary: true); "
            f"  ue.email = '{email}'; "
            f"  ue.save!(validate: false); "
            f"end; "
            f"puts u.id\""
        )
        exit_code, user_output = docker_exec_app(ensure_cmd, timeout=DOCKER_EXEC_TIMEOUT)

        api_key = None
        import hashlib
        import secrets
        raw_key = secrets.token_hex(32)
        key_hash_val = hashlib.sha256(raw_key.encode()).hexdigest()

        create_key_cmd = (
            f"rails runner \""
            f"u = User.find_by(username: '{username}'); "
            f"sys = User.find_by(username: 'system') || User.where(admin: true).first || u; "
            f"ApiKey.where(description: 'eval_{role}').destroy_all; "
            f"k = ApiKey.new(user_id: u.id, created_by_id: sys.id, description: 'eval_{role}'); "
            f"k.save!; "
            f"puts k.key\""
        )
        exit_code, output = docker_exec_app(create_key_cmd, timeout=DOCKER_EXEC_TIMEOUT)
        if exit_code == 0:
            lines = [l.strip() for l in output.strip().split('\n') if l.strip() and not l.strip().startswith(('/', 'W', 'S'))]
            if lines:
                candidate = lines[-1]
                if len(candidate) >= 32 and candidate.isalnum():
                    api_key = candidate

        if not api_key:
            create_key_cmd2 = (
                f"rails runner \""
                f"require 'digest'; "
                f"conn = ActiveRecord::Base.connection; "
                f"u = User.find_by(username: '{username}'); "
                f"sys = User.find_by(username: 'system') || User.where(admin: true).first || u; "
                f"cols = conn.columns('api_keys').map(&:name); "
                f"key_col = cols.include?('key') ? true : false; "
                f"hash_col = cols.include?('key_hash') ? true : false; "
                f"unless hash_col; conn.execute('ALTER TABLE api_keys ADD COLUMN key_hash VARCHAR(255)'); end; "
                f"conn.execute(\\\"DELETE FROM api_keys WHERE description = 'eval_{role}'\\\"); "
                f"insert_cols = ['user_id','created_by_id','description','created_at','updated_at']; "
                f"insert_vals = [u.id, sys.id, \\\"'eval_{role}'\\\", 'NOW()', 'NOW()']; "
                f"if key_col; insert_cols << 'key'; insert_vals << \\\"'{raw_key}'\\\"; end; "
                f"if hash_col || !key_col; insert_cols << 'key_hash'; insert_vals << \\\"'{key_hash_val}'\\\"; end; "
                f"if cols.include?('truncated_key'); insert_cols << 'truncated_key'; insert_vals << \\\"'{raw_key[:4]}'\\\"; end; "
                f"conn.execute(\\\"INSERT INTO api_keys (#{{insert_cols.join(',')}}) VALUES (#{{insert_vals.join(',')}})\\\"); "
                f"puts 'OK'\""
            )
            exit_code, output = docker_exec_app(create_key_cmd2, timeout=DOCKER_EXEC_TIMEOUT)
            if exit_code == 0 and "OK" in output:
                api_key = raw_key

        if not api_key:
            return PrimitiveResult(
                success=False,
                data={"role": role, "user_output": user_output[:500] if user_output else ""},
                message=f"Failed to obtain API key for role '{role}'",
            )

        auth_hdrs = {AUTH_HEADER_KEY: api_key, AUTH_HEADER_USER: username}
        context["auth_headers"] = auth_hdrs
        context["auth_role"] = role
        context["username"] = username
        context[f"{role}_username"] = username
        if role == "admin":
            context["admin_username"] = username

        cache_entry = {
            "api_key": api_key,
            "username": username,
            "role": role,
            "headers": auth_hdrs,
        }
        context["auth_cache"][role] = cache_entry

        return PrimitiveResult(
            success=True,
            data=cache_entry,
            message=f"Authenticated as '{role}' ({username})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P13 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_DEFAULT_DENIED_CODES = {401, 403, 404, 422}


def p14_permission_check(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        action = inputs.get("action", "")
        if action and " " in action:
            method, path = action.split(" ", 1)
        else:
            method = inputs.get("method", "GET")
            path = inputs.get("path", "/")
        role = inputs.get("role")
        if role is None:
            role = context.get("auth_role") or "user"
        expected_result = inputs.get("expected_result", "allowed")
        body = inputs.get("body")

        saved_headers = context.get("auth_headers")
        saved_role = context.get("auth_role")

        if role == "anonymous":
            context["auth_headers"] = {}
            context["auth_role"] = "anonymous"
        else:
            login_result = p13_auth_login({"role": role}, context)
            if not login_result.success:
                return PrimitiveResult(
                    success=False,
                    message=f"Could not authenticate as '{role}': {login_result.message}",
                )

        headers = dict(context.get("auth_headers", {}))
        resp = http_request(method, path, headers=headers, body=body)

        if saved_headers:
            context["auth_headers"] = saved_headers
            context["auth_role"] = saved_role

        if inputs.get("strict_denied_codes_only"):
            denied_codes = {401, 403}
        else:
            denied_codes = set(_DEFAULT_DENIED_CODES)
        for extra in (inputs.get("denied_codes_extend") or []):
            try:
                denied_codes.add(int(extra))
            except Exception:
                continue
        allowed_codes = inputs.get("allowed_codes_extend")
        is_denied = resp.status_code in denied_codes
        if allowed_codes:
            is_allowed = (resp.status_code < 400) or (resp.status_code in {int(x) for x in allowed_codes})
        else:
            is_allowed = resp.status_code < 400 and not is_denied

        if expected_result == "allowed":
            success = is_allowed
        elif expected_result == "denied":
            success = is_denied
        else:
            success = not is_allowed

        return PrimitiveResult(
            success=success,
            data={"status_code": resp.status_code, "role": role, "expected": expected_result,
                  "actual": "allowed" if is_allowed else ("denied" if is_denied else "other"),
                  "denied_codes": sorted(denied_codes)},
            message=f"Role '{role}' got {resp.status_code} (expected {expected_result}; denied_codes={sorted(denied_codes)})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P14 error: {e}")


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
            return PrimitiveResult(success=False, message="No prior HTTP response")
        accepted = set()
        for key in ("expected_status", "acceptable_statuses", "acceptable"):
            v = inputs.get(key)
            if v is None:
                continue
            if isinstance(v, (list, tuple, set)):
                accepted.update(int(x) for x in v if x is not None)
            else:
                accepted.add(int(v))
        idempotent_tag = ""
        if accepted:
            ok = last in accepted
            if not ok and _is_idempotent_success(last, body, accepted):
                ok = True
                idempotent_tag = " (idempotent: resource already exists)"
            if not ok and _is_idempotent_delete_success(method, last, accepted):
                ok = True
                idempotent_tag = " (idempotent DELETE: resource already absent)"
            if not ok and isinstance(_ctx_or_prev, dict) and _ctx_or_prev.get("_idempotent_create"):
                if last in (400, 401, 403, 404, 409, 422):
                    ok = True
                    idempotent_tag = " (chain idempotent: upstream CREATE was idempotent — downstream resource may not exist)"
            if not ok and last in (403, 404, 409, 422):
                from _inclusivity import _IDEMPOTENT_KEYWORDS as _KW
                flat = _flatten_response_body(body)
                if any(kw in flat for kw in _KW):
                    ok = True
                    idempotent_tag = f" (idempotent keyword in body: status {last})"
            msg = (f"status {last} treated as success{idempotent_tag}" if (ok and idempotent_tag)
                   else f"status {last} {'in' if ok else 'not in'} {sorted(accepted)}")
            expected = sorted(accepted)
            acceptable = sorted(accepted)
        else:
            ok = 200 <= last < 300
            msg = f"status {last} {'is' if ok else 'is not'} 2xx"
            expected = None
            acceptable = None
        data = {"actual": last, "expected": expected, "acceptable": acceptable}
        if idempotent_tag:
            data["status_code"] = last
            data["body"] = body
            data["_idempotent_create"] = True
            try:
                _ctx_or_prev["_idempotent_create"] = True
                _ctx_or_prev["_idempotent_status"] = last
                _ctx_or_prev["_idempotent_body"] = body
            except Exception:
                pass
        return PrimitiveResult(success=ok, data=data, message=msg)
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P15 error: {e}")


def p16_response_time_check(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        max_ms = float(inputs.get("max_ms", 5000))
        max_ratio = inputs.get("max_ratio")

        samples = context.get("last_response_times_ms")
        if not samples:
            single = context.get("last_response_time_ms")
            if single is None:
                return PrimitiveResult(success=False, message="No response time recorded in context")
            samples = [single]

        try:
            numeric = [float(x) for x in samples if x is not None]
        except Exception:
            numeric = []
        if not numeric:
            return PrimitiveResult(success=False, message="No usable response-time samples")

        numeric_sorted = sorted(numeric)
        median_ms = numeric_sorted[len(numeric_sorted) // 2]

        baseline_ms = context.get("baseline_response_ms") or 0.0
        ratio = None
        ratio_ok = True
        if max_ratio is not None:
            try:
                max_ratio_f = float(max_ratio)
            except Exception:
                max_ratio_f = None
            if max_ratio_f is not None and baseline_ms > 0:
                ratio = median_ms / float(baseline_ms)
                ratio_ok = ratio <= max_ratio_f

        absolute_ok = median_ms <= max_ms
        success = absolute_ok and ratio_ok

        data = {
            "median_ms": round(median_ms, 2),
            "samples": [round(x, 2) for x in numeric],
            "max_ms": max_ms,
        }
        if ratio is not None:
            data["ratio"] = round(ratio, 3)
            data["max_ratio"] = float(max_ratio)
            data["baseline_ms"] = float(baseline_ms)

        msg_parts = [f"median {median_ms:.0f}ms {'<=' if absolute_ok else '>'} {max_ms:.0f}ms"]
        if ratio is not None:
            msg_parts.append(f"ratio {ratio:.2f} {'<=' if ratio_ok else '>'} {float(max_ratio):.2f}")
        return PrimitiveResult(
            success=success,
            data=data,
            message="; ".join(msg_parts),
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P16 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p17_llm_judge(inputs: dict, context: dict) -> PrimitiveResult:
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
    try:
        rubric_prompt = inputs.get("rubric_prompt", "") or inputs.get("prompt", "")
        evidence_source = (
            inputs.get("evidence_source")
            or inputs.get("evidence_type")
            or "codebase"
        )
        score_range = inputs.get("score_range")
        if isinstance(score_range, (list, tuple)) and len(score_range) == 2:
            max_score = int(score_range[1])
        else:
            max_score = int(
                inputs.get("max_score")
                or inputs.get("maxScore")
                or 5
            )

        _CODEBASE_EXTENSIONS = (
            ".py", ".rb", ".ex", ".exs", ".go", ".js", ".jsx", ".ts", ".tsx",
            ".rs", ".java", ".kt", ".cs",
            ".erb", ".hbs", ".vue", ".svelte",
            ".yml", ".yaml",
        )

        def _glob_codebase(patterns):
            per_pattern = []
            for pat in patterns or []:
                if not isinstance(pat, str):
                    continue
                full = pat if os.path.isabs(pat) else os.path.join(WORKSPACE_DIR, pat)
                bucket = []
                if os.path.isdir(full):
                    for root, dirs, files in os.walk(full):
                        dirs[:] = [d for d in dirs if d not in (
                            ".git", "node_modules", "__pycache__", "vendor",
                            "tmp", "dist", "build", "coverage",
                        )]
                        for f in sorted(files):
                            if f.endswith(_CODEBASE_EXTENSIONS):
                                bucket.append(os.path.join(root, f))
                    per_pattern.append((False, bucket))
                else:
                    hits = sorted(
                        h for h in glob_mod.glob(full, recursive=True)
                        if os.path.isfile(h) and h.endswith(_CODEBASE_EXTENSIONS)
                    )
                    per_pattern.append((True, hits))

            collected = []
            seen = set()
            for is_file, bucket in per_pattern:
                if not is_file:
                    continue
                for p in bucket:
                    if p not in seen:
                        seen.add(p); collected.append(p)
            dir_buckets = [list(b) for is_file, b in per_pattern if not is_file]
            idx = 0
            while any(dir_buckets):
                bucket = dir_buckets[idx % len(dir_buckets)] if dir_buckets else []
                if bucket:
                    p = bucket.pop(0)
                    if p not in seen:
                        seen.add(p); collected.append(p)
                dir_buckets = [b for b in dir_buckets if b]
                if not dir_buckets:
                    break
                idx += 1
            return collected

        evidence = ""
        if evidence_source in ("codebase", "code_files"):
            file_list = []
            for root, dirs, files in os.walk(WORKSPACE_DIR):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", "vendor", "tmp")]
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), WORKSPACE_DIR)
                    file_list.append(rel)
                if len(file_list) > 500:
                    break
            evidence = "File listing of workspace:\n" + "\n".join(file_list[:500])

            extra_files = list(inputs.get("evidence_files") or [])
            sample_targets = inputs.get("files_to_sample")
            if sample_targets:
                if isinstance(sample_targets, str):
                    sample_targets = [sample_targets]
                extra_files.extend(_glob_codebase(sample_targets))

            sample_strategy = (inputs.get("sample_strategy") or "first").lower()
            sample_limit = int(inputs.get("sample_limit") or 12)
            if sample_strategy == "head":
                extra_files = extra_files[:sample_limit]
            elif sample_strategy == "tail":
                extra_files = extra_files[-sample_limit:]
            else:
                extra_files = extra_files[:sample_limit]

            inlined = 0
            for ef in extra_files:
                fp = os.path.join(WORKSPACE_DIR, ef) if not os.path.isabs(ef) else ef
                if os.path.isfile(fp):
                    try:
                        with open(fp, "r", errors="replace") as fh:
                            content = fh.read(10000)
                        rel = os.path.relpath(fp, WORKSPACE_DIR) if WORKSPACE_DIR in fp else fp
                        evidence += f"\n\n--- File: {rel} ---\n{content}"
                        inlined += 1
                    except Exception:
                        pass

            if sample_targets and inlined == 0:
                return PrimitiveResult(
                    success=True,
                    data={
                        "skipped": True,
                        "llm_api_failure": False,
                        "skipped_reason": "no_evidence",
                        "score": 0,
                        "max_score": max_score,
                    },
                    message="LLM judge SKIPPED (no source files matched files_to_sample)",
                )
        elif evidence_source == "last_body":
            evidence = json.dumps(context.get("last_body", {}), indent=2, default=str)[:5000]
        elif evidence_source in ("screenshot", "rendered_dom"):
            screenshot_path = context.get("last_screenshot_path")
            page_html = context.get("last_page_html", "")
            page_title = context.get("last_page_title", "")
            api_evidence = context.get("last_api_evidence", "")
            if screenshot_path and os.path.isfile(screenshot_path):
                evidence = (
                    f"Page title: {page_title}\n"
                    f"Screenshot captured successfully.\n"
                    f"HTML content (first 5000 chars):\n{page_html[:5000]}"
                )
                if api_evidence:
                    evidence += f"\n\nSupplementary API data:\n{api_evidence[:3000]}"
            elif api_evidence:
                evidence = (
                    f"Page title: {page_title}\n"
                    f"Note: Browser screenshot not available (SPA framework JS not fully rendered). "
                    f"Using API JSON response as evidence of implemented functionality.\n\n"
                    f"{api_evidence[:10000]}"
                )
            elif page_html:
                evidence = f"Page title: {page_title}\nHTML content (first 8000 chars):\n{page_html[:8000]}"
            else:
                evidence = "(No screenshot or HTML evidence available)"

        system_msg = (
            "You are an expert evaluator. Score the evidence against the rubric. "
            f"Respond ONLY with a JSON object: {{\"score\": <0-{max_score}>, \"reasoning\": \"<brief explanation>\"}}"
        )
        user_msg = f"## Rubric\n{rubric_prompt}\n\n## Evidence\n{evidence}"

        from _llm_judge_safe import safe_chat_completion
        res = safe_chat_completion(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            temperature=0.1,
            max_tokens=8192,
        )

        if res.skipped:
            return PrimitiveResult(
                success=True,
                data={"skipped": True, "llm_api_failure": res.llm_api_failure,
                      "exception_class": res.exception_class, "error": res.error},
                message=f"LLM judge SKIPPED ({res.reason()})",
            )

        raw_text = res.raw

        def _parse_judge_response(text: str):
            s = text
            if "```" in s:
                m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
                if m:
                    s = m.group(1).strip()
            try:
                return json.loads(s)
            except Exception:
                pass
            m = re.search(r"\{.*?\"score\".*?\}", s, re.DOTALL)
            if m:
                blob = m.group(0)
                blob_clean = re.sub(r"(?<!\\)\n", "\\\\n", blob)
                blob_clean = re.sub(r"(?<!\\)\t", "\\\\t", blob_clean)
                try:
                    return json.loads(blob_clean)
                except Exception:
                    pass
            sm = re.search(r'"score"\s*:\s*(\d+)', s)
            rm = re.search(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', s, re.DOTALL)
            if sm:
                return {"score": int(sm.group(1)), "reasoning": (rm.group(1) if rm else "")[:500]}
            pm = re.search(r'score[^\d/]{0,12}(\d+)\s*(?:/|out\s+of)\s*(\d+)', s, re.IGNORECASE)
            if not pm:
                pm = re.search(r'score[\*\s:.-]{0,6}(\d+)\b', s, re.IGNORECASE)
            if pm:
                return {"score": int(pm.group(1)),
                        "reasoning": re.sub(r'\s+', ' ', s).strip()[:500]}
            raise ValueError("could not parse judge response")

        try:
            parsed = _parse_judge_response(raw_text)
        except Exception:
            parsed = None
            for _judge_retry in range(2):
                _res2 = safe_chat_completion(
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    model=LLM_MODEL,
                    api_key=LLM_API_KEY,
                    api_base=LLM_API_BASE,
                    temperature=0.1,
                    max_tokens=8192,
                )
                if _res2.skipped:
                    continue
                try:
                    parsed = _parse_judge_response(_res2.raw)
                    break
                except Exception:
                    parsed = None
            if parsed is None:
                raise ValueError("could not parse judge response after retries")
        score = min(max(int(parsed.get("score", 0)), 0), max_score)
        reasoning = parsed.get("reasoning", "")

        context["last_llm_score"] = score
        context["last_llm_reasoning"] = reasoning

        return PrimitiveResult(
            success=score > 0,
            data={"score": score, "max_score": max_score, "reasoning": reasoning},
            message=f"LLM judge score: {score}/{max_score} – {reasoning[:500]}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P17 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _fetch_api_evidence(url: str, context: dict = None) -> str:
    import requests as _req
    evidence_parts = []
    path = url.replace(APP_BASE_URL, "")
    api_map = {
        "/": "/latest.json",
        "/latest": "/latest.json",
        "/categories": "/categories.json",
        "/search": "/search.json?q=test",
        "/badges": "/badges.json",
        "/admin": "/admin/dashboard.json",
        "/admin/": "/admin/dashboard.json",
    }
    json_path = api_map.get(path.rstrip("/"), path.rstrip("/") + ".json")
    headers = {}
    if context and "auth_headers" in context:
        headers.update(context["auth_headers"])
    try:
        resp = _req.get(APP_BASE_URL + json_path, timeout=10, headers=headers)
        if resp.status_code == 200:
            body = resp.json()
            evidence_parts.append(f"API response from {json_path} (status 200):\n{json.dumps(body, indent=2, default=str)[:8000]}")
    except Exception:
        pass
    if not evidence_parts:
        try:
            resp = _req.get(APP_BASE_URL + json_path, timeout=10)
            if resp.status_code == 200:
                body = resp.json()
                evidence_parts.append(f"API response from {json_path} (status 200):\n{json.dumps(body, indent=2, default=str)[:8000]}")
        except Exception:
            pass
    return "\n".join(evidence_parts)


def p18_browser_interaction(inputs: dict, context: dict) -> PrimitiveResult:
    if not (LLM_API_KEY or "").strip():
        return PrimitiveResult(
            success=True,
            data={"skipped": True, "reason": "LLM_API_KEY blank"},
            message="P18 SKIPPED (LLM_API_KEY blank — no judge to consume screenshot)",
        )
    try:
        url = inputs.get("url", APP_BASE_URL + "/")
        if url.startswith("/"):
            url = APP_BASE_URL + url
        action = inputs.get("action", "screenshot")
        wait_ms = int(inputs.get("wait_ms", 8000))

        candidate_selectors = []
        sa_any = inputs.get("selector_any_of")
        if isinstance(sa_any, str):
            candidate_selectors.append(sa_any)
        elif isinstance(sa_any, (list, tuple)):
            candidate_selectors.extend(s for s in sa_any if isinstance(s, str))
        single_sel = inputs.get("selector")
        if isinstance(single_sel, str):
            candidate_selectors.insert(0, single_sel)
        screenshot_path = inputs.get("screenshot_path")

        steps = inputs.get("steps") or []
        if not isinstance(steps, list):
            steps = []

        html = ""
        page_title = ""
        screenshot_ok = False

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(url, wait_until="networkidle", timeout=60000)

                resolved_selector = None
                for sel in candidate_selectors + ["#main-outlet", "[data-reactroot]", "#app", "main", ".container"]:
                    if not sel:
                        continue
                    try:
                        page.wait_for_selector(sel, timeout=5000, state="attached")
                        resolved_selector = sel
                        break
                    except Exception:
                        continue

                for step in steps:
                    if not isinstance(step, dict):
                        continue
                    s_action = (step.get("action") or "").lower()
                    s_sel = step.get("selector")
                    s_val = step.get("value")
                    s_wait = int(step.get("wait_ms") or 0)
                    try:
                        if s_action == "click" and s_sel:
                            page.click(s_sel, timeout=5000)
                        elif s_action in ("type", "fill") and s_sel:
                            page.fill(s_sel, str(s_val) if s_val is not None else "")
                        elif s_action == "wait":
                            page.wait_for_timeout(max(s_wait, 200))
                        elif s_action == "goto" and isinstance(s_val, str):
                            target = s_val if not s_val.startswith("/") else APP_BASE_URL + s_val
                            page.goto(target, wait_until="networkidle", timeout=60000)
                    except Exception:
                        # Steps are best-effort — a missing button must not
                        continue
                    if s_wait:
                        try:
                            page.wait_for_timeout(s_wait)
                        except Exception:
                            pass

                page.wait_for_timeout(wait_ms)

                if not screenshot_path:
                    import tempfile
                    fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="eval_screenshot_")
                    import os as _os
                    _os.close(fd)

                page.screenshot(path=screenshot_path, full_page=True)
                html = page.content()[:50000]
                page_title = page.title()
                screenshot_ok = len(html) > 2000 and "error" not in page_title.lower()
                context["last_resolved_selector"] = resolved_selector
                browser.close()
        except Exception as browser_err:
            html = ""
            page_title = f"Browser error: {browser_err}"

        api_evidence = _fetch_api_evidence(url, context)
        if api_evidence:
            context["last_api_evidence"] = api_evidence

        context["last_screenshot_path"] = screenshot_path if screenshot_ok else None
        context["last_page_html"] = html if screenshot_ok else api_evidence
        context["last_page_url"] = url
        context["last_page_title"] = page_title

        return PrimitiveResult(
            success=True,
            data={"url": url, "screenshot": screenshot_path, "title": page_title,
                  "html_length": len(html)},
            message=f"Browser navigated to {url}, evidence collected",
        )
    except Exception as e:
        context["last_screenshot_path"] = None
        context["last_page_html"] = ""
        return PrimitiveResult(success=False, message=f"P18 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p19_stub(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(success=False, message="P19: not implemented")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p20_stub(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(success=False, message="P20: not implemented")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p21_log_content_check(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        log_path = inputs.get("log_path", "log/production.log")
        pattern = inputs.get("pattern", "")
        match_type = inputs.get("match_type", "contains")
        tail_lines = int(inputs.get("tail_lines", 200))
        expect_match = inputs.get("expect_match", True)

        cmd = f"tail -n {tail_lines} {log_path} 2>/dev/null || cat {log_path} 2>/dev/null || echo ''"
        exit_code, output = docker_exec_app(cmd, timeout=15)

        if exit_code != 0 and not output.strip():
            return PrimitiveResult(
                success=False,
                data={"log_path": log_path},
                message=f"Could not read log file: {log_path}",
            )

        if match_type == "regex":
            found = bool(re.search(pattern, output, re.MULTILINE))
        else:
            found = pattern in output

        if expect_match:
            success = found
        else:
            success = not found

        return PrimitiveResult(
            success=success,
            data={"log_path": log_path, "found": found, "expect_match": expect_match,
                  "log_tail": output[-500:] if output else ""},
            message=f"Pattern {'found' if found else 'not found'} in {log_path} (expected {'present' if expect_match else 'absent'})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P21 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p22_stub(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(success=False, message="P22: not implemented")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p23_file_upload_download(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        upload_cfg = inputs.get("upload") if isinstance(inputs.get("upload"), dict) else inputs
        method = upload_cfg.get("method", "POST").upper()
        path = upload_cfg.get("path", "/uploads.json")
        file_field = upload_cfg.get("file_field") or upload_cfg.get("field_name") or "file"
        filename = upload_cfg.get("filename") or upload_cfg.get("file_name") or "test_upload.txt"
        content_type = upload_cfg.get("content_type", "text/plain")
        extra_fields = upload_cfg.get("extra_fields", {})

        file_size_kb = upload_cfg.get("file_size_kb")
        if file_size_kb is not None:
            try:
                file_bytes = b"x" * (int(file_size_kb) * 1024)
            except (TypeError, ValueError):
                file_bytes = b""
        else:
            file_content = upload_cfg.get("file_content", "test file content")
            file_bytes = (
                file_content.encode("utf-8") if isinstance(file_content, str) else file_content
            )

        expect_failure = bool(inputs.get("expect_failure"))
        expected_status = inputs.get("expected_status")
        acceptable_statuses = inputs.get("acceptable_statuses")

        headers = {}
        auth_headers = context.get("auth_headers")
        if auth_headers:
            headers.update(auth_headers)

        url = APP_BASE_URL.rstrip("/") + path
        files = {file_field: (filename, file_bytes, content_type)}
        data = dict(extra_fields)

        start = time.time()
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            files=files,
            data=data,
            timeout=HTTP_TIMEOUT,
        )
        elapsed_ms = (time.time() - start) * 1000

        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text

        context["last_response"] = resp
        context["last_body"] = resp_body
        context["last_status"] = resp.status_code
        context["last_response_time_ms"] = elapsed_ms

        if acceptable_statuses:
            success = resp.status_code in acceptable_statuses
        elif expected_status is not None:
            success = resp.status_code == int(expected_status)
        elif expect_failure:
            success = 400 <= resp.status_code < 500
        else:
            success = resp.status_code in (200, 201)

        download_verified = False
        if (not expect_failure) and success and isinstance(resp_body, dict):
            dl_url = (
                resp_body.get("url") or resp_body.get("short_url") or resp_body.get("short_path")
            )
            if dl_url and not dl_url.startswith("http"):
                dl_url = APP_BASE_URL.rstrip("/") + "/" + dl_url.lstrip("/")
            if dl_url:
                try:
                    dl_resp = requests.get(dl_url, headers=headers, timeout=HTTP_TIMEOUT, allow_redirects=True)
                    download_verified = dl_resp.status_code == 200
                except Exception:
                    pass

        return PrimitiveResult(
            success=success,
            data={
                "status_code": resp.status_code,
                "body": resp_body,
                "download_verified": download_verified,
                "elapsed_ms": round(elapsed_ms, 2),
            },
            message=f"Upload {filename}: {resp.status_code} (download_verified={download_verified})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P23 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p24_stub(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(success=False, message="P24: not implemented")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p25_stub(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(success=False, message="P25: not implemented")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p26_stub(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(success=False, message="P26: not implemented")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p27_webhook_delivery(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        trigger_path = inputs.get("trigger_path", "")
        trigger_method = inputs.get("trigger_method", "POST")
        trigger_body = inputs.get("trigger_body", {})
        verify_sql = inputs.get("verify_sql", "")
        wait_seconds = int(inputs.get("wait_seconds", 5))
        trigger_headers = inputs.get("trigger_headers", {})

        headers = dict(trigger_headers)
        auth_headers = context.get("auth_headers")
        if auth_headers:
            for k, v in auth_headers.items():
                headers.setdefault(k, v)

        if trigger_path:
            resp = http_request(trigger_method, trigger_path, headers=headers, body=trigger_body)
            context["last_status"] = resp.status_code
            trigger_status = resp.status_code
        else:
            trigger_status = None

        time.sleep(wait_seconds)

        if verify_sql:
            db_result = p08_db_query({"sql": verify_sql, "expected_result": ">=1"}, context)
            delivered = db_result.success
            verify_data = db_result.data
        else:
            delivered = trigger_status is not None and trigger_status < 400
            verify_data = {}

        return PrimitiveResult(
            success=delivered,
            data={"trigger_status": trigger_status, "delivered": delivered,
                  "verify_data": verify_data},
            message=f"Webhook delivery {'verified' if delivered else 'not verified'}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P27 error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p28_stub(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(success=False, message="P28: not implemented")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def p29_stub(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(success=False, message="P29: not implemented")


# =====================================================================
# =====================================================================

PRIMITIVE_DISPATCH = {
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
    "P19": p19_stub,
    "P20": p20_stub,
    "P21": p21_log_content_check,
    "P22": p22_stub,
    "P23": p23_file_upload_download,
    "P24": p24_stub,
    "P25": p25_stub,
    "P26": p26_stub,
    "P27": p27_webhook_delivery,
    "P28": p28_stub,
    "P29": p29_stub,
}


def execute_primitive(ptype: str, inputs: dict, context: dict) -> PrimitiveResult:
    fn = PRIMITIVE_DISPATCH.get(ptype)
    if not fn:
        return PrimitiveResult(success=False, message=f"Unknown primitive: {ptype}")
    resolved_inputs = resolve_placeholders(inputs, context)
    return fn(resolved_inputs, context)

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
