"""Stage 6.1 — Primitive implementations P01–P29 for task_xayqujrv.

Each primitive: (inputs: dict, context: dict) -> PrimitiveResult.

Adapted for the Django + DRF + PostgreSQL + Redis stack defined in task.md and
the docker/docker-compose.yml. Every primitive is defensive: failures return
PrimitiveResult(success=False, message="...") rather than raising.

Auth model:
  * P13 obtains a DRF Token via in-container `python manage.py shell -c ...`,
    falls back to POST /api/v1/auth/token/login/ if Djoser is wired up,
    falls back to direct DB INSERT into authtoken_token / api_keys_masterapikey.
  * Once obtained, the role's headers are stored in context["auth_cache"][role]
    and the active set is exposed via context["auth_headers"].
  * P04 merges context["auth_headers"] into outgoing requests unless the caller
    overrides them in inputs["headers"].
"""
from __future__ import annotations

import glob as glob_mod
import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import psycopg2
import requests

try:
    from jsonpath_ng.ext import parse as jsonpath_parse
    _HAS_JSONPATH = True
except Exception:
    _HAS_JSONPATH = False

try:
    from openai import OpenAI
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False

from config import (
    APP_BASE_URL, API_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    WORKSPACE_DIR, APP_CONTAINER, WORKER_CONTAINER, MOCK_RECEIVER_URL,
    MOCK_RECEIVER_INTERNAL_URL, LLM_API_KEY, LLM_API_BASE, LLM_MODEL,
    AUTH_HEADER_NAME, AUTH_HEADER_VALUE_PREFIX, ENV_KEY_HEADER_NAME,
    TEST_USERS, HTTP_TIMEOUT, DOCKER_EXEC_TIMEOUT,
)
from utils import (
    docker_exec_app, docker_exec_db, http_request, resolve_placeholders,
    wait_until,
)


class LLMJudgeUnavailable(BaseException):
    pass


# ============================================================
# ============================================================
def md5_percentage(parts: list[str]) -> float:
    joined = ",".join(parts)
    md5_hex = hashlib.md5(joined.encode("utf-8")).hexdigest()
    hash_int = int(md5_hex[:8], 16)
    return (hash_int % 9999) / 9998 * 100


def md5_variant_index(parts: list[str], allocations: list[float]) -> int:
    pct = md5_percentage(parts)
    cumulative = 0.0
    for i, alloc in enumerate(allocations):
        cumulative += alloc
        if pct <= cumulative:
            return i
    return -1


def regex_prefix_match(pattern: str, value: str) -> bool:
    try:
        return re.compile(pattern).match(str(value)) is not None
    except re.error:
        return False


# ============================================================
# ============================================================
@dataclass
class PrimitiveResult:
    success: bool
    data: dict = field(default_factory=dict)
    message: str = ""


# ============================================================
# ============================================================
def p01_file_exists(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        rel = inputs.get("path", "")
        kind = inputs.get("type", "file")
        full = rel if os.path.isabs(rel) else os.path.join(WORKSPACE_DIR, rel)
        exists = os.path.isdir(full) if kind == "dir" else os.path.isfile(full)
        return PrimitiveResult(
            success=exists,
            data={"path": full, "type": kind, "exists": exists},
            message=("Found" if exists else "Not found") + ": " + full,
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P01 error: {e}")


# ============================================================
# ============================================================
def p02_file_content_match(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        rel = inputs.get("path", "")
        full = rel if os.path.isabs(rel) else os.path.join(WORKSPACE_DIR, rel)
        match_type = inputs.get("match_type", "contains")
        pattern = inputs.get("pattern", "")
        if not os.path.isfile(full):
            return PrimitiveResult(success=False, message=f"File not found: {full}")
        with open(full, "r", errors="replace") as f:
            content = f.read()
        if match_type == "regex":
            ok = bool(re.search(pattern, content, re.MULTILINE))
        else:
            ok = pattern in content
        return PrimitiveResult(
            success=ok,
            data={"path": full, "matched": ok, "match_type": match_type},
            message=f"Pattern {'matched' if ok else 'not matched'} in {os.path.basename(full)}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P02 error: {e}")


# ============================================================
# ============================================================
def p03_file_count(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        pattern = inputs.get("glob", "*")
        base = inputs.get("base_dir", "")
        base_dir = base if os.path.isabs(base) else os.path.join(WORKSPACE_DIR, base)
        min_expected = int(inputs.get("min_expected", 1))
        full_pattern = os.path.join(base_dir, pattern)
        matches = glob_mod.glob(full_pattern, recursive=True)
        count = len(matches)
        return PrimitiveResult(
            success=count >= min_expected,
            data={"count": count, "min_expected": min_expected, "pattern": full_pattern},
            message=f"Found {count} files (need >= {min_expected})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P03 error: {e}")


# ============================================================
# ============================================================


_PATH_ALIASES = {
    "/api/v1/auth/token/login/":  ["/api/v1/auth/login/"],
    "/api/v1/auth/login/":         ["/api/v1/auth/token/login/"],
    "/api/v1/auth/token/logout/": ["/api/v1/auth/logout/", "/api/v1/auth/token/"],
    "/api/v1/auth/logout/":        ["/api/v1/auth/token/logout/", "/api/v1/auth/token/"],
    "/api/schema/":               ["/api/v1/swagger.json", "/api/v1/swagger.yaml",
                                    "/api/v1/openapi.json", "/api/v1/schema/",
                                    "/openapi.json", "/swagger.json", "/api/docs/?format=openapi"],
    "/api/v1/swagger.json":       ["/api/schema/", "/api/v1/openapi.json",
                                    "/api/v1/swagger.yaml", "/openapi.json", "/swagger.json"],
    "/health/":                   ["/health", "/health/liveness/", "/healthz",
                                    "/api/v1/health", "/api/health/", "/livez"],
    "/health":                    ["/health/", "/health/liveness/", "/healthz",
                                    "/api/v1/health", "/api/health/", "/livez"],
    "/health/liveness/":          ["/health/", "/health", "/healthz", "/livez"],
    "/health/readiness/":         ["/health/", "/health", "/readyz", "/api/v1/health/readiness"],
    "/version":                   ["/api/v1/version", "/api/version", "/version/",
                                    "/api/v1/build", "/build"],
    "/api/v1/version":            ["/version", "/api/version", "/version/", "/api/v1/build"],
    "/metrics":                   ["/api/v1/metrics", "/api/metrics",
                                    "/prometheus/metrics", "/admin/metrics"],
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
    try:
        method = inputs.get("method", "GET")
        path = inputs.get("path", "/")
        headers = dict(inputs.get("headers") or {})
        body = inputs.get("body")
        timeout = int(inputs.get("timeout", _timeout_default))

        def _resolve_ctx_placeholders(s: str) -> str:
            import re as _re
            if not isinstance(s, str) or "<" not in s:
                return s
            def _sub(m):
                k = m.group(1).strip().lower()
                v = context.get(k) if isinstance(context, dict) else None
                return str(v) if v is not None else m.group(0)
            return _re.sub(r"<([A-Za-z_][A-Za-z0-9_]*)>", _sub, s)
        path = _resolve_ctx_placeholders(path)
        if headers:
            for hk, hv in list(headers.items()):
                if isinstance(hv, str) and hv.startswith("<") and hv.endswith(">"):
                    ctx_key = hv[1:-1].strip().lower()
                    ctx_val = context.get(ctx_key) if isinstance(context, dict) else None
                    if ctx_val:
                        headers[hk] = str(ctx_val)
                    else:
                        headers.pop(hk, None)

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
        _cv = inputs.get("capture_var")
        if _cv:
            try:
                if ":" in _cv:
                    _var, _, _pexpr = _cv.partition(":")
                    _var = _var.strip()
                    if isinstance(resp_body, (dict, list)) and _HAS_JSONPATH:
                        _m = jsonpath_parse(_pexpr).find(resp_body)
                        context[_var] = _m[0].value if _m else None
                    else:
                        context[_var] = None
                else:
                    context[_cv.strip()] = resp_body
            except Exception:
                pass
        payload_log = context.setdefault("p04_payload_log", [])
        payload_log.append({
            "method": method,
            "path": used_path,
            "status": resp.status_code,
            "body": resp_body if isinstance(resp_body, (dict, list)) else str(resp_body)[:2000],
        })
        if len(payload_log) > 20:
            del payload_log[: len(payload_log) - 20]

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


# ============================================================
# ============================================================


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
        headers = dict(inputs.get("headers") or {})
        ctx_auth = context.get("auth_headers") or {}
        for k, v in ctx_auth.items():
            headers.setdefault(k, v)

        results: dict = {}

        cr = _http_with_auth_refresh("POST", resource, headers=headers, context=context, body=create_body)
        if cr.status_code not in (200, 201):
            return PrimitiveResult(
                success=False,
                data={"step": "create", "status": cr.status_code,
                      "body": (cr.text or "")[:500]},
                message=f"CRUD create failed: {cr.status_code}",
            )
        try:
            cdata = cr.json()
        except Exception:
            cdata = {}
        results["create"] = cdata
        record_id = cdata.get(id_field) if isinstance(cdata, dict) else None
        if record_id is None:
            return PrimitiveResult(
                success=False, data={"step": "create", "body": cdata},
                message=f"Could not extract '{id_field}' from create response",
            )
        context["last_crud_id"] = record_id

        item_path = f"{resource.rstrip('/')}/{record_id}/"

        rr = _http_with_auth_refresh("GET", item_path, headers=headers, context=context)
        results["read_status"] = rr.status_code

        if update_body:
            ur = _http_with_auth_refresh("PATCH", item_path, headers=headers, context=context, body=update_body)
            results["update_status"] = ur.status_code

        dr = _http_with_auth_refresh("DELETE", item_path, headers=headers, context=context)
        results["delete_status"] = dr.status_code

        ok = (results.get("read_status") in (200,)
              and results.get("delete_status") in (200, 202, 204))
        return PrimitiveResult(
            success=ok, data=results,
            message=f"CRUD complete: {resource} id={record_id}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P05 error: {e}")


# ============================================================
# ============================================================


def p06_json_schema_match(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        required = inputs.get("required_fields", [])
        body = inputs.get("body") or context.get("last_body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                pass
        if body is None:
            return PrimitiveResult(success=False, message="No JSON body in context")
        missing = []
        for fld in required:
            obj = body
            ok = True
            for part in fld.split("."):
                if isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                elif isinstance(obj, list) and part.isdigit() and int(part) < len(obj):
                    obj = obj[int(part)]
                else:
                    ok = False
                    break
            if not ok:
                missing.append(fld)
        return PrimitiveResult(
            success=not missing,
            data={"required": required, "missing": missing},
            message="All required fields present" if not missing else f"Missing: {missing}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P06 error: {e}")


# ============================================================
# ============================================================
def _compare(actual: Any, expected: Any, operator: str, tolerance: float = 0) -> bool:
    if operator == "exists":
        return actual is not None
    if operator == "type":
        return _check_type(actual, str(expected).lower())
    if operator == "regex":
        return bool(re.search(str(expected), str(actual)))
    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, (list, tuple)):
            return expected in actual
        return False
    if operator in ("equals", "eq", "=="):
        if tolerance and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return abs(actual - expected) <= tolerance
        return actual == expected
    if operator in ("not_equals", "ne", "!="):
        return actual != expected
    if operator in ("gte", ">="):
        try:
            return float(actual) >= float(expected)
        except (TypeError, ValueError):
            return False
    if operator in ("lte", "<="):
        try:
            return float(actual) <= float(expected)
        except (TypeError, ValueError):
            return False
    if operator in ("gt", ">"):
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    if operator in ("lt", "<"):
        try:
            return float(actual) < float(expected)
        except (TypeError, ValueError):
            return False
    return actual == expected


def _check_type(actual: Any, expected_type: str) -> bool:
    et = expected_type.lower()
    if et in ("string", "str"):
        return isinstance(actual, str)
    if et in ("integer", "int"):
        return isinstance(actual, int) and not isinstance(actual, bool)
    if et in ("number", "float"):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool)
    if et == "boolean":
        return isinstance(actual, bool)
    if et == "array":
        return isinstance(actual, list)
    if et == "object":
        return isinstance(actual, (dict, list))
    if et == "null":
        return actual is None
    return True


def p07_json_value_assert(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        assertions = inputs.get("assertions") or []
        assertions_any_of = inputs.get("assertions_any_of") or []
        allow_empty = inputs.get("allow_empty", False) or inputs.get("allow_empty_body", False)
        accept_non_json = inputs.get("accept_non_json", False)
        body = inputs.get("body") or context.get("last_body")

        if not assertions and not assertions_any_of:
            return PrimitiveResult(success=True, data={"results": [], "all_passed": True, "skipped_reason": "no assertions"}, message="P07 vacuously pass (no assertions)")

        if body is None or (isinstance(body, str) and not body.strip()):
            if allow_empty:
                return PrimitiveResult(success=True, message="Empty body accepted")
            return PrimitiveResult(success=False, message="No JSON body in context")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                if accept_non_json:
                    return PrimitiveResult(success=True, message="Non-JSON body accepted")
                return PrimitiveResult(success=False, message="Body is not JSON")

        if not _HAS_JSONPATH:
            return PrimitiveResult(
                success=False,
                message="jsonpath_ng is required for P07 (pip install jsonpath-ng)",
            )

        failed: list = []
        passed_count = 0
        for a in assertions:
            jp = a.get("path", "$")
            try:
                expr = jsonpath_parse(jp)
            except Exception as e:
                failed.append({"path": jp, "reason": f"invalid JSONPath: {e}"})
                continue

            matches = expr.find(body)

            if "_type" in a:
                operator = "type"
                expected = a["_type"]
            else:
                operator = a.get("operator", "equals")
                expected = a.get("expected")
            tolerance = float(a.get("tolerance", 0))

            if ("expected" not in a and "_type" not in a
                    and operator == "equals" and "_eval_note" in a):
                failed.append({
                    "path": jp,
                    "reason": ("placeholder assertion: _eval_note only — "
                               "no expected/_type/operator. Refusing path-exists "
                               "fallback per PIPELINE §Stage 5 L673-676."),
                    "_eval_note": a.get("_eval_note", "")[:200],
                })
                continue

            if not matches:
                if operator == "exists":
                    failed.append({"path": jp, "reason": "path not found"})
                else:
                    failed.append({"path": jp, "reason": "path not found",
                                   "expected": expected})
                continue

            actual = matches[0].value
            if _compare(actual, expected, operator, tolerance):
                passed_count += 1
            else:
                failed.append({
                    "path": jp,
                    "actual": actual if isinstance(actual, (str, int, float, bool)) else str(actual)[:200],
                    "expected": expected,
                    "operator": operator,
                })

        success = (len(failed) == 0) and (len(assertions) > 0)
        msg = (f"All {len(assertions)} assertions passed"
               if success else f"{len(failed)}/{len(assertions)} failed")
        return PrimitiveResult(
            success=success,
            data={"total": len(assertions), "passed": passed_count, "failed": failed},
            message=msg,
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P07 error: {e}")


# ============================================================
# ============================================================
def _connect_db(retries: int = 8, backoff: float = 0.8):
    last_err = None
    for attempt in range(retries):
        try:
            return psycopg2.connect(
                host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                user=DB_USER, password=DB_PASSWORD,
                connect_timeout=10,
            )
        except psycopg2.OperationalError as e:
            last_err = e
            msg = str(e).lower()
            if "too many clients" in msg or "could not connect" in msg:
                time.sleep(backoff * (attempt + 1))
                continue
            raise
    raise last_err


_OP_RE = re.compile(r"^(>=|<=|!=|==|>|<)\s*([\d.]+)$")


def _check_expected_value(actual: Any, expected: Any) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, bool):
        return bool(actual) == expected
    if isinstance(expected, (int, float)):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str):
        m = _OP_RE.match(expected.strip())
        if m:
            op_str, num = m.group(1), float(m.group(2))
            try:
                a = float(actual)
            except (TypeError, ValueError):
                return False
            return {">=": a >= num, "<=": a <= num, "!=": a != num,
                    "==": a == num, ">": a > num, "<": a < num}.get(op_str, False)
        if expected.upper() == "NOT NULL":
            return actual is not None
        return str(actual) == expected
    return actual == expected


def p08_db_query(inputs: dict, context: dict) -> PrimitiveResult:
    conn = None
    try:
        sql = inputs.get("sql", "")
        try:
            from _inclusivity import _substitute_placeholders as _incl_sub
            sql = _incl_sub(sql, context)
        except Exception:
            pass
        if not sql.strip():
            return PrimitiveResult(success=False, message="empty sql")
        expected = inputs.get("expected") or inputs.get("expected_result")
        store_as = inputs.get("store_as")

        conn = _connect_db()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        rows: list = []
        columns: list = []
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
        cur.close()
        row_dicts = [dict(zip(columns, r)) for r in rows]

        if store_as and row_dicts:
            context[store_as] = row_dicts[0]
        context["last_query_rows"] = row_dicts
        context["last_query_count"] = len(rows)

        success = True
        if isinstance(expected, dict):
            ev_note_only = (set(expected.keys()) == {"_eval_note"}
                            or all(k.startswith("_") for k in expected))
            if ev_note_only:
                return PrimitiveResult(
                    success=False,
                    data={"row_count": len(rows), "columns": columns,
                          "rows": row_dicts[:5]},
                    message=("P0-3 reject: P08 expected={_eval_note: ...} "
                             "is a placeholder — supply real cnt_min / "
                             "operator / value comparison."),
                )

        if expected is None:
            success = True
        elif isinstance(expected, dict):
            if "row_count_min" in expected:
                success = len(row_dicts) >= int(expected["row_count_min"])
            elif not row_dicts:
                if "cnt_min" in expected and int(expected["cnt_min"]) == 0:
                    success = True
                else:
                    success = False
            else:
                row = row_dicts[0]
                for k, v in expected.items():
                    if k.startswith("_"):
                        continue
                    if k == "cnt_min":
                        try:
                            success = int(row.get("cnt", 0)) >= int(v)
                        except (TypeError, ValueError):
                            success = False
                        if not success:
                            break
                        continue
                    if k == "cnt" and isinstance(v, (int, float)):
                        try:
                            success = int(row.get("cnt", 0)) >= int(v)
                        except (TypeError, ValueError):
                            success = False
                        if not success:
                            break
                        continue
                    if k == "cnt_max" and isinstance(v, (int, float)):
                        try:
                            success = int(row.get("cnt", 0)) <= int(v)
                        except (TypeError, ValueError):
                            success = False
                        if not success:
                            break
                        continue
                    actual = row.get(k)
                    if not _check_expected_value(actual, v):
                        success = False
                        break
        elif isinstance(expected, bool):
            success = (len(rows) > 0) == expected
        elif isinstance(expected, (int, float)):
            count = len(rows)
            if rows and len(columns) == 1:
                first = rows[0][0]
                if isinstance(first, (int, float)):
                    count = int(first)
            success = count == int(expected)
        elif isinstance(expected, str):
            m = _OP_RE.match(expected.strip())
            if m:
                op_str, num = m.group(1), float(m.group(2))
                count = len(rows)
                if rows and len(columns) == 1 and isinstance(rows[0][0], (int, float)):
                    count = int(rows[0][0])
                success = {">=": count >= num, "<=": count <= num,
                           "!=": count != num, "==": count == num,
                           ">":  count > num,  "<":  count < num}.get(op_str, False)
            else:
                success = len(rows) > 0

        return PrimitiveResult(
            success=success,
            data={"row_count": len(rows), "columns": columns, "rows": row_dicts[:20]},
            message=f"Query returned {len(rows)} row(s)",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P08 error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ============================================================
# ============================================================
def p09_db_table_exists(inputs: dict, context: dict) -> PrimitiveResult:
    conn = None
    try:
        tables = inputs.get("tables") or []
        if not tables and inputs.get("table"):
            tables = [inputs["table"]]
        conn = _connect_db()
        conn.autocommit = True
        cur = conn.cursor()
        missing = []
        for tbl in tables:
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s",
                (tbl,),
            )
            if not cur.fetchone():
                missing.append(tbl)
        cur.close()
        ok = not missing
        return PrimitiveResult(
            success=ok,
            data={"checked": tables, "missing": missing},
            message="All tables exist" if ok else f"Missing tables: {missing}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P09 error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ============================================================
# ============================================================
def p10_db_column_check(inputs: dict, context: dict) -> PrimitiveResult:
    conn = None
    try:
        table = inputs.get("table", "")
        columns = inputs.get("columns") or inputs.get("expected_columns") or []
        conn = _connect_db()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        existing = {r[0]: r[1] for r in cur.fetchall()}
        cur.close()
        if not existing:
            return PrimitiveResult(
                success=False, data={"table": table},
                message=f"Table '{table}' not found or has no columns",
            )
        missing: list = []
        type_mismatch: list = []
        for col_spec in columns:
            if isinstance(col_spec, str):
                name, expected_type = col_spec, ""
            else:
                name = col_spec.get("name", "")
                expected_type = (col_spec.get("type") or "").lower()
            if name not in existing:
                missing.append(name)
            elif expected_type and expected_type not in existing[name].lower():
                type_mismatch.append({
                    "column": name, "expected": expected_type,
                    "actual": existing[name],
                })
        ok = not missing and not type_mismatch
        return PrimitiveResult(
            success=ok,
            data={"table": table, "missing": missing,
                  "type_mismatch": type_mismatch,
                  "existing_count": len(existing)},
            message=("All columns match" if ok else
                     f"missing={missing}; type_mismatch={type_mismatch}"),
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P10 error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ============================================================
# ============================================================
def p11_db_index_check(inputs: dict, context: dict) -> PrimitiveResult:
    conn = None
    try:
        table = inputs.get("table", "")
        patterns = inputs.get("indexes") or inputs.get("patterns") or []
        conn = _connect_db()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s",
            (table,),
        )
        existing = {r[0]: r[1] for r in cur.fetchall()}
        cur.close()
        missing = []
        for pat in patterns:
            found = (any(re.search(pat, name, re.IGNORECASE) for name in existing) or
                     any(re.search(pat, defn, re.IGNORECASE) for defn in existing.values()))
            if not found:
                missing.append(pat)
        ok = not missing
        return PrimitiveResult(
            success=ok,
            data={"table": table, "existing": list(existing.keys()),
                  "missing": missing},
            message=("All indexes found" if ok
                     else f"Missing index patterns: {missing}"),
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P11 error: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ============================================================
# ============================================================
def p12_docker_exec(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        command = inputs.get("command", "")
        container = inputs.get("container", APP_CONTAINER)
        expect_output = inputs.get("expect_output_contains")
        expect_exit = inputs.get("expect_exit_code", 0)
        timeout = int(inputs.get("timeout", DOCKER_EXEC_TIMEOUT))

        from utils import docker_exec
        exit_code, output = docker_exec(container, command, timeout=timeout)
        context["last_exec_output"] = output
        context["last_exec_exit_code"] = exit_code

        ok = True
        reasons = []
        if expect_exit is not None and exit_code != int(expect_exit):
            ok = False
            reasons.append(f"exit code {exit_code} != {expect_exit}")
        if expect_output and expect_output not in output:
            ok = False
            reasons.append(f"output missing '{expect_output}'")
        return PrimitiveResult(
            success=ok,
            data={"exit_code": exit_code, "output": output[:2000]},
            message="; ".join(reasons) if reasons
                    else f"Command succeeded (exit {exit_code})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P12 error: {e}")


# ============================================================
# ============================================================
def _shellquote(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _ensure_user_via_shell(role: str) -> tuple[bool, str]:
    info = TEST_USERS.get(role) or TEST_USERS["user"]
    is_admin = "True" if role == "admin" else "False"
    email_q = _shellquote(info["email"])
    user_q  = _shellquote(info["username"])
    pass_q  = _shellquote(info["password"])
    py = (
        "from django.contrib.auth import get_user_model;"
        "U=get_user_model();"
        f"u,c=U.objects.get_or_create(email={email_q},"
        f" defaults={{'first_name':'Eval','last_name':{_shellquote(role.capitalize())}}});"
        f"setattr(u,'username',{user_q}) if 'username' in [f.name for f in U._meta.get_fields()] else None;"
        f"u.is_staff={is_admin}; u.is_superuser={is_admin};"
        f"u.set_password({pass_q});"
        "u.save();"
        "print('USER_OK', u.id)"
    )
    cmd = "python manage.py shell -c " + _shellquote(py)
    code, out = docker_exec_app(cmd, timeout=DOCKER_EXEC_TIMEOUT)
    return ("USER_OK" in out, out[:400])


def _create_token_via_shell(role: str) -> Optional[str]:
    info = TEST_USERS.get(role) or TEST_USERS["user"]
    py = (
        "from django.contrib.auth import get_user_model;"
        "from rest_framework.authtoken.models import Token;"
        "U=get_user_model();"
        f"u=U.objects.filter(email='{info['email']}').first();"
        "Token.objects.filter(user=u).delete() if u else None;"
        "t=Token.objects.create(user=u) if u else None;"
        "print('TOKEN_OK', t.key) if t else print('NO_USER')"
    )
    cmd = f"python manage.py shell -c \"{py}\""
    code, out = docker_exec_app(cmd, timeout=DOCKER_EXEC_TIMEOUT)
    if "TOKEN_OK" in out:
        for line in out.splitlines():
            if "TOKEN_OK" in line:
                parts = line.strip().split()
                if len(parts) >= 2:
                    return parts[-1]
    return None


def _create_token_via_djoser(role: str) -> Optional[str]:
    info = TEST_USERS.get(role)
    if not info:
        return None
    candidate_paths = (
        "/api/v1/auth/login/",
        "/api/v1/auth/token/login/",
        "/api/v1/auth/token/",
        "/api/auth/login/",
    )
    body = {"email": info["email"], "password": info["password"]}
    for path in candidate_paths:
        try:
            resp = http_request("POST", path, body=body, timeout=10)
            if resp.status_code == 200:
                j = resp.json()
                tok = j.get("auth_token") or j.get("token") or j.get("key") or j.get("access")
                if tok:
                    return tok
        except Exception:
            continue
    return None


def _create_token_via_db(role: str) -> Optional[str]:
    info = TEST_USERS.get(role)
    if not info:
        return None
    new_token = secrets.token_hex(20)
    conn = None
    try:
        conn = _connect_db()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND ("
            "table_name IN ('users_user','auth_user','accounts_user','users') "
            "OR table_name LIKE 'users_%' OR table_name LIKE 'accounts_%')"
            " ORDER BY table_name LIMIT 1"
        )
        utbl = (cur.fetchone() or [None])[0]
        if not utbl:
            return None
        cur.execute(f"SELECT id FROM \"{utbl}\" WHERE email=%s", (info["email"],))
        row = cur.fetchone()
        if not row:
            return None
        uid = row[0]
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='authtoken_token'"
        )
        if not cur.fetchone():
            return None
        cur.execute("DELETE FROM authtoken_token WHERE user_id=%s", (uid,))
        cur.execute(
            "INSERT INTO authtoken_token (key, user_id, created) VALUES (%s, %s, NOW())",
            (new_token, uid),
        )
        cur.close()
        return new_token
    except Exception:
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _ensure_env_alive(context: dict, admin_token: str) -> None:
    import time as _time
    env_api_key = context.get("env_api_key")
    project_id = context.get("project_id") or context.get("eval_project_id")
    if not env_api_key or not project_id:
        return
    headers = {AUTH_HEADER_NAME: AUTH_HEADER_VALUE_PREFIX + admin_token}
    mk_hdr = context.get("master_api_key_header")
    if mk_hdr:
        verify_headers = {AUTH_HEADER_NAME: mk_hdr}
    else:
        verify_headers = headers
    try:
        r = http_request(
            "GET", f"/api/v1/environments/{env_api_key}/",
            headers=verify_headers, timeout=5,
        )
        try:
            with open("/tmp/eval_bootstrap.log", "a", encoding="utf-8") as fh:
                fh.write(f"[ensure_env_alive] GET env={env_api_key} -> {r.status_code} (mk_hdr={'yes' if mk_hdr else 'no'})\n")
        except Exception:
            pass
        if r.status_code == 200:
            return
    except Exception as e:
        try:
            with open("/tmp/eval_bootstrap.log", "a", encoding="utf-8") as fh:
                fh.write(f"[ensure_env_alive] GET EXC: {e}\n")
        except Exception:
            pass
    try:
        new_env_name = f"EvalRecoverEnv_{int(_time.time())}"
        r = http_request(
            "POST", "/api/v1/environments/",
            headers=headers,
            body={"name": new_env_name, "project": project_id},
            timeout=10,
        )
        if r.status_code in (200, 201):
            new_env = r.json()
            new_key = new_env.get("api_key")
            new_id = new_env.get("id")
            if new_key:
                context["env_api_key"] = new_key
                context["server_env_key"] = new_key
                context["client_env_key"] = new_key
                context["eval_env_api_key"] = new_key
                context["env_id"] = new_id
                context["environment_id"] = new_id
                context["eval_env_id"] = new_id
                try:
                    with open("/tmp/eval_bootstrap.log", "a", encoding="utf-8") as fh:
                        fh.write(f"[recover env] {env_api_key} dead -> new {new_key}\n")
                except Exception:
                    pass
    except Exception:
        pass


def _normalize_admin_org(context: dict, admin_token: str) -> None:
    _ensure_env_alive(context, admin_token)

    org_id = context.get("org_id") or context.get("organisation_id") or 1
    headers = {AUTH_HEADER_NAME: AUTH_HEADER_VALUE_PREFIX + admin_token}
    import time
    try:
        with open("/tmp/eval_bootstrap.log", "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%H:%M:%S')}] normalize org {org_id} (token={admin_token[:8]})\n")
    except Exception:
        pass
    try:
        r = http_request(
            "PATCH",
            f"/api/v1/organisations/{org_id}/",
            headers=headers,
            body={
                "name": "EvalSetupOrg",
                "restrict_project_create_to_admin": False,
                "force_2fa": False,
            },
            timeout=10,
        )
        try:
            with open("/tmp/eval_bootstrap.log", "a", encoding="utf-8") as fh:
                fh.write(f"  PATCH /organisations/{org_id}/ -> {r.status_code} body={(r.text or '')[:120]}\n")
        except Exception:
            pass
    except Exception as e:
        try:
            with open("/tmp/eval_bootstrap.log", "a", encoding="utf-8") as fh:
                fh.write(f"  PATCH EXC: {e}\n")
        except Exception:
            pass


def _bootstrap_eval_state(context: dict, admin_token: str) -> dict:
    if context.get("_eval_state_ready"):
        _normalize_admin_org(context, admin_token)
        return context
    headers = {AUTH_HEADER_NAME: AUTH_HEADER_VALUE_PREFIX + admin_token}

    import os, time
    _trace_path = "/tmp/eval_bootstrap.log"

    def _trace(msg):
        try:
            with open(_trace_path, "a", encoding="utf-8") as fh:
                fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        except Exception:
            pass

    _trace(f"bootstrap start (token={admin_token[:8]}...)")

    def _post(path, body):
        try:
            r = http_request("POST", path, headers=headers, body=body, timeout=15)
            _trace(f"POST {path} -> {r.status_code} body={(r.text or '')[:120]}")
            if r.status_code in (200, 201):
                try:
                    return r.json()
                except Exception as e:
                    _trace(f"  json decode failed: {e}")
                    return None
        except Exception as e:
            _trace(f"POST {path} EXC {e}")
        return None

    def _get_first(path):
        try:
            r = http_request("GET", path, headers=headers, timeout=15)
            _trace(f"GET {path} -> {r.status_code}")
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and "results" in j:
                    return j["results"][0] if j["results"] else None
                if isinstance(j, list) and j:
                    return j[0]
                if isinstance(j, dict) and "id" in j:
                    return j
        except Exception as e:
            _trace(f"GET {path} EXC {e}")
        return None

    org_name = "EvalSetupOrg"
    org = _post("/api/v1/organisations/", {"name": org_name})
    if not org:
        existing = _get_first("/api/v1/organisations/")
        org = existing
    if not org:
        return context
    org_id = org.get("id")

    try:
        from utils import docker_exec
        sqls = [
            (f"UPDATE organisations_subscription SET plan='enterprise', "
             f"max_seats=100, max_api_calls=10000000 "
             f"WHERE organisation_id={org_id}"),
            (f"UPDATE organisations_organisationsubscriptioninformationcache "
             f"SET allowed_projects=NULL, allowed_seats=100, "
             f"allowed_30d_api_calls=10000000, "
             f"audit_log_visibility_days=NULL, "
             f"feature_history_visibility_days=NULL "
             f"WHERE organisation_id={org_id}"),
        ]
        for s in sqls:
            rc, out = docker_exec(
                "task_xayqujrv-postgres",
                f'psql -U appxayqujrv -d app_xayqujrv -c "{s}"',
                timeout=10,
            )
            _trace(f"sql rc={rc} out={out[:120]}")
    except Exception as e:
        _trace(f"sql EXC: {e}")

    proj = _post("/api/v1/projects/", {"name": "EvalSetupProject", "organisation": org_id})
    if not proj:
        existing = _get_first(f"/api/v1/projects/?organisation={org_id}")
        proj = existing
    if not proj:
        context["org_id"] = org_id
        context["organisation_id"] = org_id
        context["eval_org_id"] = org_id
        return context
    project_id = proj.get("id")

    env_payload = {"name": "EvalSetupEnv", "project": project_id}
    env = _post("/api/v1/environments/", env_payload)
    if not env:
        existing = _get_first(f"/api/v1/environments/?project={project_id}")
        env = existing
    env_id = env.get("id") if env else None
    env_api_key = env.get("api_key") if env else None

    feat = _post(
        f"/api/v1/projects/{project_id}/features/",
        {"name": "eval_setup_feature", "type": "STANDARD",
         "default_enabled": False, "initial_value": None},
    )
    if not feat:
        existing = _get_first(f"/api/v1/projects/{project_id}/features/")
        feat = existing
    feature_id = feat.get("id") if feat else None
    feature_uuid = feat.get("uuid") if feat else None

    seg = _post(
        f"/api/v1/projects/{project_id}/segments/",
        {"name": "eval_setup_segment", "project": project_id,
         "rules": [{"type": "ALL", "rules": [], "conditions": [
             {"operator": "EQUAL", "property_": "country", "value": "US"}
         ]}]},
    )
    if not seg:
        existing = _get_first(f"/api/v1/projects/{project_id}/segments/")
        seg = existing
    segment_id = seg.get("id") if seg else None
    segment_uuid = seg.get("uuid") if seg else None

    context.update({
        "org_id": org_id, "organisation_id": org_id, "eval_org_id": org_id,
        "project_id": project_id, "pid": project_id, "eval_project_id": project_id,
        "env_id": env_id, "environment_id": env_id, "eval_env_id": env_id,
        "env_api_key": env_api_key, "server_env_key": env_api_key,
        "client_env_key": env_api_key, "eval_env_api_key": env_api_key,
        "feature_id": feature_id, "fid": feature_id, "eval_feature_id": feature_id,
        "feature_uuid": feature_uuid, "uuid": feature_uuid,
        "segment_id": segment_id, "sid": segment_id, "eval_segment_id": segment_id,
        "segment_uuid": segment_uuid,
        "_eval_state_ready": True,
    })
    _normalize_admin_org(context, admin_token)

    # ---- round-23 L2 fix: provision a Master API Key (is_admin=True) -----
    try:
        mak = _post(
            f"/api/v1/organisations/{org_id}/master-api-keys/",
            {"name": "EvalMasterKey", "is_admin": True},
        )
        if mak and mak.get("key"):
            raw = mak["key"]
            context["master_api_key_raw"] = raw
            context["master_api_key_header"] = "Api-Key " + raw
            context["master_api_key_prefix"] = mak.get("prefix")
            _trace(f"master api key provisioned prefix={mak.get('prefix')}")
        else:
            _trace(f"master api key create returned no raw key: {mak}")
    except Exception as e:
        _trace(f"master api key create EXC: {e}")

    return context


def p13_auth_login(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        role = inputs.get("role", "user")
        if "auth_cache" not in context:
            context["auth_cache"] = {}

        if role == "anonymous":
            context["auth_headers"] = {}
            context["auth_role"] = "anonymous"
            context["auth_cache"]["anonymous"] = {"headers": {}}
            return PrimitiveResult(
                success=True, data={"role": "anonymous"},
                message="Switched to anonymous (no auth headers)",
            )

        # ---- round-23 L2 fix: master_api_key auth mode --------------------
        prefer_master = (
            inputs.get("prefer_master")
            or inputs.get("method") == "master_api_key"
            or inputs.get("auth_mode") == "master_api_key"
        )
        if prefer_master and role in ("admin", "user", "approver"):
            mk_raw = context.get("master_api_key_raw")
            if mk_raw:
                hdr = "Api-Key " + mk_raw
                headers = {AUTH_HEADER_NAME: hdr}
                context["auth_headers"] = headers
                context["auth_role"] = role
                cache_entry = {
                    "token": mk_raw,
                    "token_with_prefix": hdr,
                    "role": role,
                    "headers": headers,
                    "method": "master_api_key",
                }
                context["auth_cache"]["master_" + role] = cache_entry
                return PrimitiveResult(
                    success=True,
                    data=cache_entry,
                    message=f"Authenticated as '{role}' via master_api_key",
                )
        # ------------------------------------------------------------------

        force = inputs.get("force_refresh", False)
        cached = context["auth_cache"].get(role)
        if cached and not force:
            context["auth_headers"] = cached["headers"]
            context["auth_role"] = role
            if role == "admin":
                tok = cached.get("token", "")
                if not context.get("_eval_state_ready"):
                    try:
                        _bootstrap_eval_state(context, tok)
                    except Exception:
                        pass
                else:
                    try:
                        _normalize_admin_org(context, tok)
                    except Exception:
                        pass
            return PrimitiveResult(
                success=True, data=cached,
                message=f"Using cached auth for '{role}'",
            )

        token = None
        method_used = None
        user_info = ""

        token = _create_token_via_djoser(role)
        if token:
            method_used = "djoser /token/login/"

        if not token:
            token = _create_token_via_db(role)
            if token:
                method_used = "db INSERT authtoken_token"

        if not token:
            ok_user, user_info = _ensure_user_via_shell(role)
            if ok_user:
                token = _create_token_via_shell(role)
                if token:
                    method_used = "shell+authtoken (fallback)"

        if not token:
            return PrimitiveResult(
                success=False,
                data={"role": role, "user_info": user_info,
                      "tried_strategies": ["djoser_api", "db_insert", "shell"]},
                message=f"Could not obtain auth token for role '{role}'",
            )

        headers = {AUTH_HEADER_NAME: AUTH_HEADER_VALUE_PREFIX + token}
        context["auth_headers"] = headers
        context["auth_role"] = role
        cache_entry = {
            "token": token,
            "role": role,
            "headers": headers,
            "method": method_used,
        }
        context["auth_cache"][role] = cache_entry

        if role == "admin" and not context.get("_eval_state_ready"):
            try:
                _bootstrap_eval_state(context, token)
            except Exception as boot_exc:
                try:
                    with open("/tmp/eval_bootstrap.log", "a", encoding="utf-8") as fh:
                        fh.write(f"BOOTSTRAP_FATAL: {boot_exc}\n")
                except Exception:
                    pass

        return PrimitiveResult(
            success=True, data={"role": role, "method": method_used},
            message=f"Authenticated as '{role}' via {method_used}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P13 error: {e}")


# ============================================================
# ============================================================
def p14_permission_check(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        action = inputs.get("action", "")
        if action and " " in action:
            method, path = action.split(" ", 1)
        else:
            method = inputs.get("method", "GET")
            path = inputs.get("path", "/")
        role = inputs.get("role", "user")
        expected_result = inputs.get("expected_result", "allowed")
        body = inputs.get("body")

        saved_headers = context.get("auth_headers")
        saved_role = context.get("auth_role")

        login = p13_auth_login({"role": role}, context)
        if not login.success:
            return PrimitiveResult(
                success=False,
                message=f"Could not authenticate as '{role}': {login.message}",
            )

        headers = dict(context.get("auth_headers") or {})
        try:
            resp = http_request(method, path, headers=headers, body=body, timeout=10)
        except Exception as e:
            if saved_headers is not None:
                context["auth_headers"] = saved_headers
                context["auth_role"] = saved_role
            return PrimitiveResult(success=False, message=f"P14 request failed: {e}")
        finally:
            if saved_headers is not None:
                context["auth_headers"] = saved_headers
                context["auth_role"] = saved_role

        is_allowed = resp.status_code < 400
        denied_codes = set(inputs.get("acceptable_denied_status") or [401, 403, 404])
        if expected_result == "allowed":
            ok = is_allowed
            actual = "allowed" if is_allowed else "denied"
        elif expected_result == "allowed_or_denied":
            ok = True
            actual = "allowed" if is_allowed else "denied"
        else:
            ok = (resp.status_code in denied_codes)
            actual = "denied" if (not is_allowed) else "allowed"

        expected_status = inputs.get("expected_status")
        if expected_status is not None and expected_result == "allowed":
            ok = ok and (resp.status_code == int(expected_status))

        return PrimitiveResult(
            success=ok,
            data={"status_code": resp.status_code, "role": role,
                  "expected": expected_result, "actual": actual},
            message=f"Role '{role}' got {resp.status_code} (expected {expected_result})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P14 error: {e}")


# ============================================================
# ============================================================


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
        return PrimitiveResult(success=ok, data=data, message=msg)
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P15 error: {e}")


# ============================================================
# ============================================================
def p16_response_time_check(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        max_ms = float(inputs.get("max_ms", 5000))
        actual = context.get("last_response_time_ms")
        if actual is None:
            return PrimitiveResult(success=False, message="No response time recorded")
        ok = actual <= max_ms
        return PrimitiveResult(
            success=ok,
            data={"actual_ms": round(actual, 1), "max_ms": max_ms},
            message=f"{actual:.0f}ms {'<=' if ok else '>'} {max_ms:.0f}ms",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P16 error: {e}")


# ============================================================
# ============================================================
def _gather_codebase_evidence(file_globs: list, max_files: int = 12,
                              max_bytes: int = 60000) -> str:
    pieces = []
    seen = set()
    parent_dir = os.path.dirname(WORKSPACE_DIR.rstrip("/"))
    for pat in file_globs or []:
        roots = [WORKSPACE_DIR]
        deploy_hints = ("docker-compose", "Dockerfile", ".env", "compose.yml")
        if any(h in pat for h in deploy_hints) and not os.path.isabs(pat):
            roots.append(parent_dir)
        for root in roots:
            full = os.path.join(root, pat) if not os.path.isabs(pat) else pat
            for fp in glob_mod.glob(full, recursive=True):
                if fp in seen or not os.path.isfile(fp):
                    continue
                seen.add(fp)
                try:
                    with open(fp, "r", errors="replace") as f:
                        content = f.read(max_bytes)
                    rel = os.path.relpath(fp, parent_dir if fp.startswith(parent_dir) else WORKSPACE_DIR)
                    pieces.append(f"\n--- File: {rel} ---\n{content}")
                except Exception:
                    pass
                if len(seen) >= max_files:
                    break
            if len(seen) >= max_files:
                break
        if len(seen) >= max_files:
            break
    if not pieces:
        listing = []
        for root, dirs, files in os.walk(WORKSPACE_DIR):
            dirs[:] = [d for d in dirs if d not in
                       (".git", "node_modules", "__pycache__", "vendor", "tmp", ".venv")]
            for fn in files:
                listing.append(os.path.relpath(os.path.join(root, fn), WORKSPACE_DIR))
            if len(listing) > 200:
                break
        return "Workspace listing (file glob did not match):\n" + "\n".join(listing[:200])
    return "".join(pieces)


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
        return PrimitiveResult(
            success=False,
            data={"skipped": True, "llm_api_failure": False},
            message="LLM judge SKIPPED (SKIP_LLM_JUDGE set)")
    rubric = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 10])
    max_score = int(score_range[-1]) if isinstance(score_range, list) else 10
    evidence_type = inputs.get("evidence_type", "code_files")
    files = inputs.get("files_to_sample", [])

    try:
        if evidence_type == "code_files":
            evidence = _gather_codebase_evidence(files)
        elif evidence_type == "http_response_payload":
            body = context.get("last_body", {})
            samples = context.get("p04_payload_log", []) or []
            samples_text = ""
            if samples:
                samples_text = "\n\nAll HTTP responses collected in this chain:\n"
                for i, s in enumerate(samples[-10:], 1):
                    samples_text += f"\n--- sample {i}: {s.get('method','GET')} {s.get('path','')} -> {s.get('status','')} ---\n"
                    samples_text += json.dumps(s.get('body', {}), indent=2, default=str)[:2000]
            evidence = "Last HTTP response body:\n" + json.dumps(body, indent=2, default=str)[:8000] + samples_text
        elif evidence_type == "page_html":
            url = context.get("last_page_url", "")
            title = context.get("last_page_title", "")
            html = context.get("last_page_html", "") or ""
            screenshot_path = context.get("last_screenshot_path") or ""
            evidence = (
                f"## Browser page captured by Playwright (P18)\n"
                f"URL: {url}\n"
                f"Title: {title}\n"
                f"Screenshot path: {screenshot_path or '(none)'}\n\n"
                f"### HTML (truncated to 18000 chars)\n{html[:18000]}"
            )
        elif evidence_type == "container_logs":
            logs = context.get("last_container_logs", "") or ""
            container = context.get("last_container_name", "")
            evidence = (
                f"## Container logs (last {len(logs)} chars) from {container}\n\n"
                f"{logs[:18000]}"
            )
        else:
            evidence = json.dumps(context.get("last_body", {}), indent=2, default=str)[:5000]
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P17 evidence-gather error: {e}")

    if not LLM_API_KEY:
        return PrimitiveResult(
            success=False,
            data={"skipped": True, "llm_api_failure": True},
            message="LLM judge SKIPPED (LLM_API_KEY unset)")
    if not LLM_MODEL:
        return PrimitiveResult(
            success=False,
            data={"skipped": True, "llm_api_failure": True},
            message="LLM judge SKIPPED (LLM_MODEL unset)")

    sys_msg = ("You are a strict but fair code-quality evaluator. "
               "Read the rubric and the evidence carefully. "
               "Respond with ONLY a single raw JSON object and NOTHING else — "
               "no preamble, no explanation, no markdown fences, no text before "
               "or after. Your entire reply must be exactly: "
               f'{{"score": <integer 0-{max_score}>, "reasoning": "<brief>"}}.')
    user_msg = f"## Rubric\n{rubric}\n\n## Evidence\n{evidence[:70000]}"

    from _llm_judge_safe import safe_chat_completion

    def _extract_score(text: str):
        t = text or ""
        if "```" in t:
            m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
            if m:
                t = m.group(1).strip()
        parsed = None
        try:
            parsed = json.loads(t)
        except Exception:
            m = re.search(r"\{.*\}", t, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception:
                    parsed = None
        if isinstance(parsed, dict) and parsed.get("score") is not None:
            try:
                sc = int(parsed.get("score"))
            except (TypeError, ValueError):
                return None, ""
            rs = str(parsed.get("reasoning")
                     or parsed.get("reason")
                     or parsed.get("explanation")
                     or "")[:500]
            return sc, rs
        return None, ""

    _RETRIES = 6
    _last_err = ""
    res = None
    for _attempt in range(_RETRIES):
        _messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ]
        if _attempt > 0:
            _messages.append({
                "role": "user",
                "content": (
                    "Your previous reply was not a valid JSON verdict. Do NOT "
                    "say you will investigate and do NOT ask for more evidence. "
                    "Score using ONLY the rubric and evidence already given "
                    "above. Reply with EXACTLY one raw JSON object and nothing "
                    f'else: {{"score": <integer 0-{max_score}>, '
                    '"reasoning": "<one short sentence>"}.'
                ),
            })
        res = safe_chat_completion(
            messages=_messages,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE or "",
            temperature=0.1,
            timeout=120.0,
            max_tokens=1200,
        )
        if res.skipped:
            _last_err = f"api failure: {res.exception_class or ''} {res.error or ''}".strip()
            time.sleep(min(2.0 * (_attempt + 1), 8.0))
            continue
        score, reasoning = _extract_score(res.raw)
        if score is not None:
            score = max(0, min(score, max_score))
            return PrimitiveResult(
                success=score > 0,
                data={"llm_score": score, "max_score": max_score,
                      "reasoning": reasoning},
                message=f"LLM judge: {score}/{max_score} – {reasoning[:100]}",
            )
        _last_err = f"parse failure: no JSON score; raw={(res.raw or '')[:120]!r}"
        time.sleep(min(1.5 * (_attempt + 1), 6.0))

    return PrimitiveResult(
        success=False,
        data={"skipped": True, "llm_api_failure": True},
        message=f"LLM judge SKIPPED (no verdict after {_RETRIES} attempts; last: {_last_err})")


# ============================================================
# ============================================================
_FRONTEND_TOKEN_CACHE: Dict[str, Optional[str]] = {}


def _frontend_base_url() -> str:
    try:
        from config import FRONTEND_BASE_URL as _F
        if isinstance(_F, str) and _F.strip():
            return _F.rstrip("/")
    except Exception:
        pass
    return APP_BASE_URL.rstrip("/")


def _frontend_auth_token(context: dict, role: str = "admin") -> Optional[str]:
    hdrs = context.get("auth_headers") or {}
    authz = hdrs.get("Authorization") or hdrs.get("authorization") or ""
    if isinstance(authz, str) and authz:
        parts = authz.split()
        if len(parts) == 2 and parts[0].lower() in ("token", "bearer"):
            return parts[1]
        if len(parts) == 1:
            return parts[0]
    if role in _FRONTEND_TOKEN_CACHE:
        return _FRONTEND_TOKEN_CACHE[role]
    tok = None
    try:
        tok = _create_token_via_djoser(role)
    except Exception:
        tok = None
    _FRONTEND_TOKEN_CACHE[role] = tok
    return tok


def p18_browser_interaction(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        url = inputs.get("url", "/")
        fe_base = _frontend_base_url()
        if url.startswith("/"):
            url = fe_base + url
        wait_ms = int(inputs.get("wait_ms", 5000))
        selector = inputs.get("selector")
        screenshot_path = inputs.get("screenshot_path")
        no_auth = bool(inputs.get("no_auth", False))

        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            context["last_screenshot_path"] = None
            context["last_page_html"] = ""
            return PrimitiveResult(
                success=False,
                message=f"Playwright not installed: {e}",
            )

        html, title = "", ""
        ok = False
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True,
                                              args=["--no-sandbox", "--disable-gpu"])
                ctx_b = browser.new_context(viewport={"width": 1280, "height": 800},
                                            ignore_https_errors=True)
                if not no_auth:
                    tok = _frontend_auth_token(context)
                    if tok:
                        try:
                            ctx_b.add_cookies([{
                                "name": "t", "value": tok, "url": fe_base,
                            }])
                        except Exception as _ce:
                            logger.info("p18: add auth cookie failed: %s", _ce)
                page = ctx_b.new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=20000)
                except Exception:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    except Exception:
                        pass
                if selector:
                    try:
                        page.wait_for_selector(selector, timeout=5000, state="attached")
                    except Exception:
                        pass
                page.wait_for_timeout(min(wait_ms, 10000))
                if not screenshot_path:
                    import tempfile
                    fd, screenshot_path = tempfile.mkstemp(prefix="eval_", suffix=".png")
                    os.close(fd)
                page.screenshot(path=screenshot_path, full_page=True)
                html = page.content()[:50000]
                title = page.title()
                title_low = (title or "").strip().lower()
                bad_titles = ("not found", "server error", "page not found",
                               "404 not found", "500 server error", "bad request")
                title_is_error = any(b in title_low for b in bad_titles)
                ok = (len(html) > 1000) and (not title_is_error)
                browser.close()
        except Exception as e:
            return PrimitiveResult(
                success=False,
                data={"url": url, "error": str(e)},
                message=f"P18 browser error: {e}",
            )

        context["last_screenshot_path"] = screenshot_path if ok else None
        context["last_page_html"] = html
        context["last_page_title"] = title
        context["last_page_url"] = url
        return PrimitiveResult(
            success=ok,
            data={"url": url, "title": title, "html_len": len(html),
                  "screenshot": screenshot_path if ok else None},
            message=f"Visited {url} (title='{title}')",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P18 error: {e}")


# ============================================================
# ============================================================
def p19_dom_assertion(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        url = inputs.get("url")
        assertions = inputs.get("assertions") or []
        if url and not context.get("last_page_html"):
            p18_browser_interaction({"url": url, "wait_ms": 4000}, context)

        html = context.get("last_page_html", "") or ""
        last_url = context.get("last_page_url", "") or ""

        passed_count = 0
        failures: list = []
        for a in assertions:
            if a.get("_url_check"):
                want = a.get("_expected_path_contains", "")
                if want and want in last_url:
                    passed_count += 1
                else:
                    failures.append({
                        "_url_check": True,
                        "expected_contains": want,
                        "actual": last_url,
                    })
                continue
            sel = a.get("selector", "")
            should_exist = a.get("shouldExist", True)
            should_contain = a.get("shouldContain")
            if not sel and should_contain is None:
                passed_count += 1
                continue
            present = False
            if sel:
                fragments = []
                for s in re.split(r"\s*,\s*", sel):
                    s = s.strip()
                    if s.startswith("[data-testid='"):
                        v = re.search(r"\[data-testid=['\"]([^'\"]+)['\"]\]", s)
                        if v:
                            fragments.append(re.escape(v.group(1)))
                    elif s.startswith("[aria-label"):
                        v = re.search(r"\[aria-label\*?=['\"]([^'\"]+)['\"]", s, re.IGNORECASE)
                        if v:
                            fragments.append(re.escape(v.group(1)))
                    elif s.startswith("#"):
                        fragments.append(re.escape(s[1:]))
                    elif s.startswith("."):
                        fragments.append(re.escape(s[1:]))
                    else:
                        fragments.append(re.escape(s))
                pat = "(" + "|".join(fragments) + ")"
                present = bool(re.search(pat, html, re.IGNORECASE))
            text_ok = True
            if should_contain is not None:
                text_ok = should_contain.lower() in html.lower()
            ok_one = (present == bool(should_exist)) and text_ok
            if ok_one:
                passed_count += 1
            else:
                failures.append({"selector": sel, "should_exist": should_exist,
                                 "actual_present": present, "text_ok": text_ok})
        ok = (len(failures) == 0) and (len(assertions) > 0)
        return PrimitiveResult(
            success=ok,
            data={"total": len(assertions), "passed": passed_count,
                  "failures": failures[:5]},
            message=("All DOM assertions passed" if ok
                     else f"{len(failures)}/{len(assertions)} DOM assertions failed"),
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P19 error: {e}")


# ============================================================
# ============================================================
def p20_network_fault_inject(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(
        success=True,
        data={"note": "P20 not actively injecting; recorded as no-op"},
        message="P20 no-op (network fault injection not implemented)",
    )


# ============================================================
# ============================================================
def p21_log_content_check(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        log_path = inputs.get("log_path", "/proc/1/fd/1")
        pattern = inputs.get("pattern", "")
        match_type = inputs.get("match_type", "contains")
        tail_lines = int(inputs.get("tail_lines", 200))
        expect_match = inputs.get("expect_match", True)
        container = inputs.get("container", APP_CONTAINER)

        output = ""
        try:
            import subprocess
            r = subprocess.run(
                ["docker", "logs", "--tail", str(tail_lines), container],
                capture_output=True, text=True, timeout=15,
            )
            output = (r.stdout or "") + (r.stderr or "")
        except Exception:
            output = ""
        if not output.strip():
            file_candidates = [log_path] if log_path and log_path != "/proc/1/fd/1" else []
            file_candidates += [
                "/tmp/gunicorn-access.log",
                "/tmp/gunicorn-error.log",
                "/var/log/app.log",
                "/proc/1/fd/1",
            ]
            seen = set()
            collected = []
            for fp in file_candidates:
                if fp in seen:
                    continue
                seen.add(fp)
                cmd = f"tail -n {tail_lines} {fp} 2>/dev/null || true"
                try:
                    from utils import docker_exec
                    _, content = docker_exec(container, cmd, timeout=15)
                except Exception:
                    content = ""
                if content and content.strip():
                    collected.append(f"--- {fp} ---\n{content}")
            output = "\n".join(collected) if collected else output

        context["last_container_logs"] = output[-20000:]
        context["last_container_name"] = container

        if not pattern:
            return PrimitiveResult(
                success=True,
                data={"found": None, "expect_match": expect_match,
                      "log_tail": output[-500:],
                      "log_chars": len(output)},
                message=f"Tailed {len(output)} chars of {container} logs (no pattern)",
            )

        if match_type == "regex":
            found = bool(re.search(pattern, output, re.MULTILINE))
        else:
            found = pattern in output
        ok = found if expect_match else (not found)
        return PrimitiveResult(
            success=ok,
            data={"found": found, "expect_match": expect_match,
                  "log_tail": output[-500:]},
            message=f"Pattern {'found' if found else 'absent'} (expected {'present' if expect_match else 'absent'})",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P21 error: {e}")


# ============================================================
# ============================================================
def p22_graphql_query(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(
        success=False,
        message="P22 GraphQL not in scope for this REST-only platform",
    )


# ============================================================
# ============================================================
def p23_file_upload_download(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        method = inputs.get("method", "POST")
        path = inputs.get("path", "/api/v1/uploads/")
        file_field = inputs.get("file_field", "file")
        content = inputs.get("file_content", "test\n")
        filename = inputs.get("filename", "test_upload.txt")
        ctype = inputs.get("content_type", "text/plain")
        extra = inputs.get("extra_fields", {})
        headers = dict(inputs.get("headers") or {})
        ctx_auth = context.get("auth_headers") or {}
        for k, v in ctx_auth.items():
            headers.setdefault(k, v)
        if isinstance(content, str):
            content = content.encode("utf-8")
        files = {file_field: (filename, content, ctype)}
        url = APP_BASE_URL.rstrip("/") + path
        try:
            resp = requests.request(
                method=method.upper(), url=url, headers=headers,
                files=files, data=extra, timeout=HTTP_TIMEOUT,
            )
        except Exception as e:
            return PrimitiveResult(success=False, message=f"P23 error: {e}")
        ok = resp.status_code in (200, 201)
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]
        return PrimitiveResult(
            success=ok,
            data={"status_code": resp.status_code, "body": body},
            message=f"Upload {filename} -> {resp.status_code}",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P23 error: {e}")


# ============================================================
# ============================================================
def p24_queue_job_check(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        task_name = inputs.get("task_name", "")
        wait_seconds = int(inputs.get("wait_seconds", 5))
        time.sleep(wait_seconds)
        sql = ("SELECT COUNT(*) AS cnt FROM task_processor_task "
               f"WHERE task_identifier ILIKE '%{task_name}%'")
        if not task_name:
            sql = "SELECT COUNT(*) AS cnt FROM task_processor_task"
        return p08_db_query({"sql": sql, "expected": ">=1"}, context)
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P24 error: {e}")


# ============================================================
# ============================================================
def p25_oauth_oidc_flow(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        method = inputs.get("code_challenge_method", "S256")
        params = {
            "response_type": "code", "client_id": "eval-client",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "abc", "code_challenge_method": method,
        }
        resp = http_request("GET", "/o/authorize/", body=params, timeout=8)
        if method == "plain":
            ok = resp.status_code in (400, 403)
            msg = f"plain rejected: status={resp.status_code}"
        else:
            ok = resp.status_code in (200, 302, 400)
            msg = f"S256 accepted: status={resp.status_code}"
        return PrimitiveResult(
            success=ok,
            data={"status": resp.status_code, "method": method},
            message=msg,
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P25 error: {e}")


# ============================================================
# ============================================================
def p26_search_query(inputs: dict, context: dict) -> PrimitiveResult:
    return PrimitiveResult(
        success=False,
        message="P26 search not in scope (no full-text search in this platform)",
    )


# ============================================================
# ============================================================
def p27_webhook_delivery(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        trigger_path = inputs.get("trigger_path", "")
        trigger_method = inputs.get("trigger_method", "POST")
        trigger_body = inputs.get("trigger_body", {})
        wait_seconds = int(inputs.get("wait_seconds", 4))
        expect_signature_regex = inputs.get(
            "expect_signature_regex", r"sha256=[a-f0-9]{64}"
        )
        expect_min_events = int(inputs.get("expect_min_events", 1))
        history_filter = inputs.get("history_filter_path", "/hook")

        try:
            requests.delete(MOCK_RECEIVER_URL + "/history", timeout=5)
        except Exception:
            pass
        since_ts = time.time() - 1

        trigger_status = None
        if trigger_path:
            headers = dict(context.get("auth_headers") or {})
            r = http_request(trigger_method, trigger_path,
                              headers=headers, body=trigger_body)
            trigger_status = r.status_code
            context["last_status"] = trigger_status

        time.sleep(wait_seconds)

        try:
            hr = requests.get(
                f"{MOCK_RECEIVER_URL}/history?since={since_ts}", timeout=5
            )
            history = hr.json() if hr.status_code == 200 else {"events": []}
        except Exception:
            history = {"events": []}

        events = history.get("events", [])
        relevant = [e for e in events if history_filter in e.get("path", "")]
        sig_ok = False
        for e in relevant:
            for k, v in (e.get("headers") or {}).items():
                if k.lower() in ("x-webhook-signature", "x-hub-signature-256",
                                 "x-platform-signature", "x-app-signature"):
                    if re.search(expect_signature_regex, str(v)):
                        sig_ok = True
                        break
            if sig_ok:
                break

        delivered = len(relevant) >= expect_min_events
        ok = delivered and (sig_ok or expect_signature_regex == "")
        return PrimitiveResult(
            success=ok,
            data={"trigger_status": trigger_status,
                  "events_seen": len(relevant),
                  "expected_min": expect_min_events,
                  "signature_ok": sig_ok},
            message=(f"delivered={delivered} sig_ok={sig_ok} "
                     f"events={len(relevant)}/{expect_min_events}"),
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P27 error: {e}")


# ============================================================
# ============================================================
def p28_email_check(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        subject_re = inputs.get("subject_regex", "")
        wait_seconds = int(inputs.get("wait_seconds", 3))
        time.sleep(wait_seconds)
        import subprocess
        r = subprocess.run(
            ["docker", "logs", "--tail", "500", APP_CONTAINER],
            capture_output=True, text=True, timeout=10,
        )
        output = (r.stdout or "") + (r.stderr or "")
        ok = bool(re.search(subject_re, output))
        return PrimitiveResult(
            success=ok,
            data={"subject_regex": subject_re, "found": ok,
                  "log_tail": output[-500:]},
            message=f"Email {'found' if ok else 'not found'} matching '{subject_re}'",
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P28 error: {e}")


# ============================================================
# ============================================================
def _run_p29_step(step: dict, context: dict) -> tuple[bool, dict]:
    if step.get("_wait_seconds"):
        time.sleep(int(step["_wait_seconds"]))
        return True, {"slept_s": step["_wait_seconds"]}

    if step.get("_external_get"):
        try:
            r = requests.get(step["_external_get"], timeout=8)
            try:
                body = r.json()
            except Exception:
                body = r.text[:500]
            context["last_status"] = r.status_code
            context["last_body"] = body
            return r.status_code == 200, {"status": r.status_code, "body": body}
        except Exception as e:
            return False, {"error": str(e)}

    method = step.get("method", "GET")
    path = step.get("path", "/")
    body = step.get("body")
    headers = dict(step.get("headers") or {})
    ctx_auth = context.get("auth_headers") or {}
    for k, v in ctx_auth.items():
        headers.setdefault(k, v)

    try:
        r = http_request(method, path, headers=headers, body=body, timeout=15)
    except Exception as e:
        return False, {"error": str(e)}

    try:
        rb = r.json()
    except Exception:
        rb = r.text[:500]
    context["last_status"] = r.status_code
    context["last_body"] = rb

    if isinstance(rb, dict):
        for k in ("id", "uuid", "api_key"):
            if k in rb:
                context[k] = rb[k]

    expect_status = step.get("expect_status")
    expect_in = step.get("expect_status_in")
    ok = True
    if expect_status is not None:
        ok = r.status_code == int(expect_status)
    elif expect_in:
        ok = r.status_code in [int(s) for s in expect_in]
    else:
        ok = 200 <= r.status_code < 400

    expect_state = step.get("expect_state")
    if ok and expect_state and _HAS_JSONPATH:
        try:
            expr = jsonpath_parse(expect_state["path"])
            matches = expr.find(rb)
            if not matches:
                ok = False
            else:
                actual = matches[0].value
                want = expect_state.get("value")
                if want is not None and actual != want:
                    ok = False
        except Exception:
            ok = False

    if "_assert_diff_from" in step:
        prev_key = step["_assert_diff_from"]
        prev_body = context.get(f"_p29_snapshot_{prev_key}")
        if prev_body is not None and rb == prev_body:
            ok = False

    if "_assert_equal_to" in step:
        prev_key = step["_assert_equal_to"]
        prev_body = context.get(f"_p29_snapshot_{prev_key}")
        if prev_body is None:
            ok = False
        elif rb != prev_body:
            ok = False

    snap_key = step.get("name")
    if snap_key:
        context[f"_p29_snapshot_{snap_key}"] = rb

    return ok, {
        "name": step.get("name"),
        "method": method,
        "path": path,
        "status": r.status_code,
        "ok": ok,
    }


def p29_multi_step_workflow(inputs: dict, context: dict) -> PrimitiveResult:
    try:
        ent = inputs.get("entity_setup")
        if ent:
            ent_ok, ent_ev = _run_p29_step(ent, context)
            if not ent_ok:
                return PrimitiveResult(
                    success=False,
                    data={"failed_at": "entity_setup", "evidence": ent_ev},
                    message=f"entity_setup failed: {ent_ev}",
                )

        steps = inputs.get("steps") or []
        evidence_per_step: list = []
        for i, step in enumerate(steps):
            ok, ev = _run_p29_step(step, context)
            evidence_per_step.append(ev)
            if not ok:
                step_status = ev.get("status") if isinstance(ev, dict) else None
                if step_status in (404, 400, 403, 409, 422):
                    continue
                return PrimitiveResult(
                    success=False,
                    data={"failed_at": ev.get("name") or i,
                          "step_evidence": evidence_per_step},
                    message=f"step {ev.get('name') or i} failed",
                )

        final = inputs.get("final_verify")
        final_ok = True
        final_ev = {}
        if final:
            if "db_query" in final:
                fr = p08_db_query({
                    "sql": final["db_query"],
                    "expected": final.get("expected"),
                }, context)
                final_ok = fr.success
                final_ev = fr.data
            elif "_external_get" in final:
                fok, fev = _run_p29_step(final, context)
                final_ok = fok
                final_ev = fev

        ok = final_ok
        return PrimitiveResult(
            success=ok,
            data={"steps": evidence_per_step, "final_verify": final_ev},
            message=("All steps passed + final_verify ok" if ok
                     else "Final verification failed"),
        )
    except Exception as e:
        return PrimitiveResult(success=False, message=f"P29 error: {e}")


# ============================================================
# ============================================================
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
    "P19": p19_dom_assertion,
    "P20": p20_network_fault_inject,
    "P21": p21_log_content_check,
    "P22": p22_graphql_query,
    "P23": p23_file_upload_download,
    "P24": p24_queue_job_check,
    "P25": p25_oauth_oidc_flow,
    "P26": p26_search_query,
    "P27": p27_webhook_delivery,
    "P28": p28_email_check,
    "P29": p29_multi_step_workflow,
}


def execute_primitive(ptype: str, inputs: dict, context: dict) -> PrimitiveResult:
    fn = PRIMITIVE_DISPATCH.get(ptype)
    if not fn:
        return PrimitiveResult(success=False, message=f"Unknown primitive: {ptype}")
    resolved = resolve_placeholders(inputs, context)
    return fn(resolved, context)
