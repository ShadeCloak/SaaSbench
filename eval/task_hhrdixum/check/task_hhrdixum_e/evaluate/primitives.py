from __future__ import annotations

import base64
import io
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config as cfg
from .utils import (
    PrimitiveResult,
    ctx,
    docker_exec,
    http_request,
    json_get,
    logger,
    substitute,
)

try:
    import psycopg
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _db_conn():
    if not HAS_PSYCOPG:
        raise RuntimeError("psycopg not installed; pip install 'psycopg[binary]'")
    return psycopg.connect(
        host=cfg.DB_HOST,
        port=cfg.DB_PORT,
        dbname=cfg.DB_NAME,
        user=cfg.DB_USER,
        password=cfg.DB_PASSWORD,
        connect_timeout=cfg.DB_CONNECT_TIMEOUT,
    )


def _safe_path(rel: str) -> Path:
    p = Path(rel)
    if not p.is_absolute():
        p = cfg.WORKSPACE_DIR / rel
    return p


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P01_file_exists(inputs: Dict[str, Any]) -> PrimitiveResult:
    rel = inputs.get("path", "")
    expected_type = inputs.get("type", "any")
    p = _safe_path(rel)
    exists = p.exists()
    if exists and expected_type == "file":
        exists = p.is_file()
    elif exists and expected_type == "dir":
        exists = p.is_dir()
    return PrimitiveResult(
        primitive="P01",
        passed=exists,
        score_hint=1.0 if exists else 0.0,
        evidence={"path": str(p), "exists": exists},
        message=f"{'found' if exists else 'missing'}: {p}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P02_file_content_match(inputs: Dict[str, Any]) -> PrimitiveResult:
    rel = inputs.get("path", "")
    pat = inputs.get("pattern", "")
    mode = inputs.get("match_type", "contains")
    p = _safe_path(rel)
    if not p.exists():
        return PrimitiveResult("P02", False, 0.0, {"path": str(p)}, "file not found")
    if p.is_dir():
        return PrimitiveResult(
            "P02", True, 1.0,
            {"path": str(p), "is_dir": True},
            "P02 target is a directory, not a file — treating as dir-exists pass",
        )
    try:
        text = p.read_text(errors="replace")
    except Exception as e:
        return PrimitiveResult("P02", False, 0.0, {"path": str(p)}, f"read error: {e}")

    if mode == "contains":
        matched = pat in text
        cnt = text.count(pat)
    elif mode == "regex":
        matches = list(re.finditer(pat, text, re.MULTILINE))
        matched = len(matches) > 0
        cnt = len(matches)
    else:
        return PrimitiveResult("P02", False, 0.0, {}, f"unknown match_type {mode!r}")

    return PrimitiveResult(
        primitive="P02",
        passed=matched,
        score_hint=1.0 if matched else 0.0,
        evidence={"path": str(p), "pattern": pat, "match_type": mode, "match_count": cnt},
        message=f"{cnt} match(es)" if matched else "no match",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P03_file_count(inputs: Dict[str, Any]) -> PrimitiveResult:
    glob_pat = inputs.get("glob", "**/*")
    base = _safe_path(inputs.get("base_dir", "."))
    min_expected = int(inputs.get("min_expected", 1))
    if not base.exists():
        return PrimitiveResult("P03", False, 0.0, {"base_dir": str(base)}, "base dir missing")
    files = list(base.glob(glob_pat))
    cnt = len(files)
    passed = cnt >= min_expected
    ratio = min(cnt / max(min_expected, 1), 1.0)
    return PrimitiveResult(
        primitive="P03",
        passed=passed,
        score_hint=ratio,
        evidence={"base_dir": str(base), "glob": glob_pat, "count": cnt, "files_sample": [str(f) for f in files[:10]]},
        message=f"{cnt} files (>= {min_expected})" if passed else f"only {cnt} files, need {min_expected}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P04_http_request(inputs: Dict[str, Any]) -> PrimitiveResult:
    method = inputs.get("method", "GET")
    path = inputs.get("path", "/")
    headers = inputs.get("headers", {}) or {}
    body = inputs.get("body", None)
    timeout = inputs.get("timeout", cfg.HTTP_TIMEOUT)
    resp = http_request(method, path, headers=headers, body=body, timeout=timeout)
    ctx["__last_response__"] = resp
    err = resp.get("error")
    if err:
        return PrimitiveResult(
            primitive="P04",
            passed=False,
            score_hint=0.0,
            evidence={"response": resp},
            message=f"network error: {err}",
        )
    save_id_as = inputs.get("save_response_id_as")
    save_field = inputs.get("save_response_field_as")
    rbody = resp.get("body")
    if isinstance(rbody, list) and rbody and isinstance(rbody[0], dict):
        rbody = rbody[0]
    if save_id_as and isinstance(rbody, dict):
        pk = rbody.get("pk") or rbody.get("id") or rbody.get("ID") or rbody.get("key")
        if pk is not None:
            ctx[save_id_as] = pk
    if save_field and isinstance(rbody, dict):
        if isinstance(save_field, dict) and "field" in save_field and "var" in save_field:
            v = rbody.get(save_field["field"])
            if v is not None:
                ctx[save_field["var"]] = v
        elif isinstance(save_field, dict):
            for var_name, field_name in save_field.items():
                v = rbody.get(field_name)
                if v is not None:
                    ctx[var_name] = v
    return PrimitiveResult(
        primitive="P04",
        passed=True,
        score_hint=1.0,
        evidence={"response": resp},
        message=f"{method} {resp['url']} → {resp['status_code']} ({resp['response_time_ms']}ms)",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P05_api_crud(inputs: Dict[str, Any]) -> PrimitiveResult:
    resource = inputs.get("resource", "/").rstrip("/")
    create_body = inputs.get("create_body", {})
    update_body = inputs.get("update_body", {})
    expected_create = inputs.get("expected_create_status", 201)
    expected_read_fields = inputs.get("expected_read_fields", [])
    expected_update = inputs.get("expected_update_status", 200)
    expected_delete_raw = inputs.get("expected_delete_status", [200, 204])
    expected_deletes = expected_delete_raw if isinstance(expected_delete_raw, (list, tuple)) else [expected_delete_raw]

    steps_passed = 0
    steps_total = 4
    last_id: Optional[Any] = None
    evidence: Dict[str, Any] = {"resource": resource}
    msgs: List[str] = []

    setup = inputs.get("setup_company_first")
    if isinstance(setup, dict):
        ts = ctx.get("ts", "0")
        leaf = resource.rstrip("/").rsplit("/", 1)[-1] or "x"
        setup_body = {
            "name":     f"P05-Setup-{leaf}-{ts}-{secrets.token_hex(3)}",
            "currency": "USD",
            **setup,
        }
        setup_resp = http_request("POST", "/api/company/", body=setup_body)
        evidence["setup_company"] = setup_resp
        sb = setup_resp.get("body")
        if isinstance(sb, dict) and (sb.get("pk") or sb.get("id")):
            cid = sb.get("pk") or sb.get("id")
            ctx["cid"] = cid
            ctx["company_id"] = cid
            from .utils import substitute as _sub
            create_body = _sub(create_body)
        else:
            msgs.append(f"setup_company_first failed: {setup_resp.get('status_code')}")

    create = http_request("POST", resource + "/", body=create_body)
    evidence["create"] = create
    if create.get("status_code") == expected_create or (create.get("status_code") in (200, 201) and not isinstance(expected_create, int)):
        steps_passed += 1
        body = create.get("body", {})
        if isinstance(body, list) and body and isinstance(body[0], dict):
            body = body[0]
        last_id = body.get("pk") or body.get("id") if isinstance(body, dict) else None
    else:
        err_snippet = ""
        b = create.get("body")
        if isinstance(b, dict):
            err_snippet = json.dumps(b, ensure_ascii=False)[:160]
        elif isinstance(b, str):
            err_snippet = b[:160]
        msgs.append(f"CREATE expected {expected_create} got {create.get('status_code')} body={err_snippet}")

    if last_id is None and steps_passed > 0 and isinstance(create.get("body"), dict):
        last_id = create["body"].get("pk") or create["body"].get("id")

    if last_id is not None:
        read = http_request("GET", f"{resource}/{last_id}/")
        evidence["read"] = read
        if read.get("status_code") == 200:
            steps_passed += 1
            if expected_read_fields and isinstance(read.get("body"), dict):
                missing = [f for f in expected_read_fields if f not in read["body"]]
                if missing:
                    msgs.append(f"READ missing fields {missing}")

        else:
            msgs.append(f"READ got {read.get('status_code')}")
    else:
        msgs.append("READ skipped (no id)")

    if last_id is not None:
        upd = http_request("PATCH", f"{resource}/{last_id}/", body=update_body)
        evidence["update"] = upd
        if upd.get("status_code") == expected_update:
            steps_passed += 1
        else:
            msgs.append(f"UPDATE expected {expected_update} got {upd.get('status_code')}")
    else:
        msgs.append("UPDATE skipped (no id)")

    if last_id is not None:
        dele = http_request("DELETE", f"{resource}/{last_id}/")
        evidence["delete"] = dele
        if dele.get("status_code") in expected_deletes:
            steps_passed += 1
        else:
            msgs.append(f"DELETE expected one of {expected_deletes} got {dele.get('status_code')}")
    else:
        msgs.append("DELETE skipped (no id)")

    return PrimitiveResult(
        primitive="P05",
        passed=(steps_passed == steps_total),
        score_hint=steps_passed / steps_total,
        evidence=evidence | {"steps_passed": steps_passed, "steps_total": steps_total, "last_id": last_id},
        message=f"CRUD {steps_passed}/{steps_total} | {'; '.join(msgs)[:200]}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P06_json_schema_match(inputs: Dict[str, Any]) -> PrimitiveResult:
    resp = ctx.get("__last_response__", {})
    body = resp.get("body", {})
    required = inputs.get("required_fields", [])
    types = inputs.get("field_types", {})
    if not isinstance(body, dict):
        return PrimitiveResult("P06", False, 0.0, {"got_type": type(body).__name__}, "response not an object")
    missing = [f for f in required if f not in body]
    bad_type = []
    for f, expected in types.items():
        if f in body and not _typecheck(body[f], expected):
            bad_type.append((f, expected, type(body[f]).__name__))
    passed = not missing and not bad_type
    score = (len(required) - len(missing)) / max(len(required), 1)
    return PrimitiveResult(
        primitive="P06",
        passed=passed,
        score_hint=score,
        evidence={"required": required, "missing": missing, "bad_type": bad_type},
        message=f"{len(required)-len(missing)}/{len(required)} fields present" + (f", bad_type={bad_type}" if bad_type else ""),
    )


def _typecheck(v: Any, expected: str) -> bool:
    table = {
        "string": str,
        "str": str,
        "integer": int,
        "int": int,
        "boolean": bool,
        "bool": bool,
        "number": (int, float),
        "float": float,
        "array": list,
        "list": list,
        "object": dict,
        "dict": dict,
        "null": type(None),
    }
    if expected not in table:
        return True
    target = table[expected]
    if isinstance(target, tuple):
        return isinstance(v, target)
    return isinstance(v, target)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P07_json_value_assert(inputs: Dict[str, Any]) -> PrimitiveResult:
    resp = ctx.get("__last_response__", {})
    body = resp.get("body", {})
    assertions = inputs.get("assertions", [])
    results = []
    passed_count = 0
    for a in assertions:
        ok, detail = _eval_assertion(body, a)
        results.append({"assertion": a, "passed": ok, "detail": detail})
        if ok:
            passed_count += 1
    all_ok = passed_count == len(assertions)
    return PrimitiveResult(
        primitive="P07",
        passed=all_ok,
        score_hint=passed_count / max(len(assertions), 1),
        evidence={"assertions_passed": passed_count, "assertions_total": len(assertions), "results": results[:30]},
        message=f"{passed_count}/{len(assertions)} assertions",
    )


def _eval_assertion(body: Any, a: Dict[str, Any]) -> Tuple[bool, str]:
    paths: List[str] = []
    if "path" in a:
        paths = [a["path"]]
    elif "path_any_of" in a:
        paths = list(a["path_any_of"])
    else:
        return False, "no path/path_any_of in assertion"

    actuals: List[Tuple[str, Any]] = [(p, json_get(body, p)) for p in paths]

    if "exists" in a:
        want = bool(a["exists"])
        any_present = any(v is not None for _, v in actuals)
        any_missing = any(v is None for _, v in actuals)
        if want and not any_present:
            return False, f"none of {paths} present"
        if (not want) and not any_missing:
            return False, f"all of {paths} unexpectedly present"

    if "expected" in a:
        want = a["expected"]
        tol = a.get("tolerance", 0)
        ok_any = False
        for _, actual in actuals:
            if _approx_equal(actual, want, tol):
                ok_any = True; break
        if not ok_any:
            return False, f"actuals={[v for _,v in actuals]} expected={want!r} tol={tol}"

    if "expected_in" in a:
        want_set = list(a["expected_in"])
        ok_any = any(v in want_set for _, v in actuals)
        if not ok_any:
            return False, f"actuals={[v for _,v in actuals]} not in {want_set}"

    if "type" in a:
        want_t = a["type"]
        ok_any = any(_typecheck(v, want_t) for _, v in actuals if v is not None)
        if not ok_any:
            return False, f"actuals not of type {want_t}"

    if "regex" in a:
        pat = a["regex"]
        ok_any = False
        for _, v in actuals:
            if v is None:
                continue
            if re.search(pat, str(v)):
                ok_any = True; break
        if not ok_any:
            return False, f"none of actuals matches /{pat}/"

    if "regex_in_str" in a:
        pat = a["regex_in_str"]
        joined = " ".join(str(v) for _, v in actuals if v is not None)
        if not re.search(pat, joined, re.IGNORECASE):
            return False, f"regex /{pat}/ not found"

    if "deep_equal" in a:
        want = a["deep_equal"]
        ok_any = any(v == want for _, v in actuals)
        if not ok_any:
            return False, f"actuals={[v for _,v in actuals]} != {want!r}"

    if "min_length" in a:
        want = int(a["min_length"])
        ok_any = any(hasattr(v, "__len__") and len(v) >= want for _, v in actuals)
        if not ok_any:
            return False, f"none reaches min_length={want}"

    if "tolerance_str" in a and a["tolerance_str"]:
        want = a.get("expected", "")
        ok_any = False
        for _, v in actuals:
            if v is None:
                continue
            sv = str(v).rstrip("0").rstrip(".") if isinstance(v, (str, float, int)) else str(v)
            sw = str(want).rstrip("0").rstrip(".")
            if sv.startswith(sw[:6]) or sw.startswith(sv[:6]):
                ok_any = True; break
        if not ok_any:
            return False, f"actuals={[v for _,v in actuals]} not approximately {want!r}"

    return True, "ok"


def _approx_equal(a: Any, b: Any, tol: float) -> bool:
    if a is None and b is None:
        return True
    try:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) <= tol
        if isinstance(a, str) and isinstance(b, (int, float)):
            return abs(float(a) - b) <= tol
        if isinstance(a, (int, float)) and isinstance(b, str):
            return abs(a - float(b)) <= tol
    except (TypeError, ValueError):
        return False
    return a == b


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P08_db_query(inputs: Dict[str, Any]) -> PrimitiveResult:
    sql = inputs.get("sql", "")
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, context)
    except Exception:
        pass
    expected_result = inputs.get("expected_result")
    expected_partial = inputs.get("expected_partial_result")
    expect_rowcount_min = inputs.get("expect_rowcount_min")
    expect_rowcount_max = inputs.get("expect_rowcount_max")
    first_row_assertions = inputs.get("first_row_assertions", {})
    if not sql.strip():
        return PrimitiveResult("P08", False, 0.0, {}, "empty SQL")
    if "{{" in sql and "}}" in sql:
        return PrimitiveResult(
            "P08", False, 0.0,
            {"sql": sql[:300], "unresolved_placeholder": True},
            "P08 SQL contains unresolved {{placeholder}} — prereq did not populate ctx",
        )
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(sql)
            if cur.description:
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            else:
                conn.commit()
                rows = []
    except Exception as e:
        return PrimitiveResult("P08", False, 0.0, {"sql": sql[:300], "error": str(e)}, f"db error: {e}")

    issues: List[str] = []
    if expected_result is not None:
        if rows != expected_result:
            issues.append(f"rows!=expected_result (got {len(rows)} rows)")

    if expected_partial is not None and isinstance(expected_partial, list):
        for i, want in enumerate(expected_partial):
            if i >= len(rows):
                issues.append(f"row[{i}] missing")
                continue
            for k, v in want.items():
                if rows[i].get(k) != v:
                    issues.append(f"row[{i}].{k} = {rows[i].get(k)!r}, want {v!r}")

    if expect_rowcount_min is not None and len(rows) < int(expect_rowcount_min):
        issues.append(f"rowcount {len(rows)} < min {expect_rowcount_min}")
    if expect_rowcount_max is not None and len(rows) > int(expect_rowcount_max):
        issues.append(f"rowcount {len(rows)} > max {expect_rowcount_max}")

    if first_row_assertions:
        if not rows:
            issues.append("first_row_assertions but no rows")
        else:
            for k, v in first_row_assertions.items():
                if k.endswith("_gte"):
                    real = k[:-4]
                    if rows[0].get(real, 0) < v:
                        issues.append(f"first_row.{real}={rows[0].get(real)} < {v}")
                elif k.endswith("_lte"):
                    real = k[:-4]
                    if rows[0].get(real, 0) > v:
                        issues.append(f"first_row.{real}={rows[0].get(real)} > {v}")
                elif k.endswith("_not_null"):
                    real = k[:-9]
                    if rows[0].get(real) is None:
                        issues.append(f"first_row.{real} is null")
                else:
                    if rows[0].get(k) != v:
                        issues.append(f"first_row.{k} = {rows[0].get(k)!r}, want {v!r}")

    passed = not issues
    return PrimitiveResult(
        primitive="P08",
        passed=passed,
        score_hint=1.0 if passed else 0.0,
        evidence={"sql": sql[:500], "row_count": len(rows), "rows_sample": rows[:5], "issues": issues},
        message=f"{len(rows)} rows; {'OK' if passed else '; '.join(issues)[:200]}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P09_db_table_exists(inputs: Dict[str, Any]) -> PrimitiveResult:
    tables = inputs.get("tables", [])
    if not tables:
        return PrimitiveResult("P09", False, 0.0, {}, "no tables specified")
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name = ANY(%s)",
                (list(tables),),
            )
            existing = sorted({r[0] for r in cur.fetchall()})
    except Exception as e:
        return PrimitiveResult("P09", False, 0.0, {"error": str(e)}, f"db error: {e}")
    missing = sorted(set(tables) - set(existing))
    passed = not missing
    return PrimitiveResult(
        primitive="P09",
        passed=passed,
        score_hint=len(existing) / len(tables),
        evidence={"existing": existing, "missing": missing},
        message=f"{len(existing)}/{len(tables)} tables" + (f"; missing={missing}" if missing else ""),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P10_db_column_check(inputs: Dict[str, Any]) -> PrimitiveResult:
    table = inputs.get("table", "")
    expected = inputs.get("expected_columns", [])
    if not table or not expected:
        return PrimitiveResult("P10", False, 0.0, {}, "missing table/columns")
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name = %s",
                (table,),
            )
            existing = {r[0] for r in cur.fetchall()}
    except Exception as e:
        return PrimitiveResult("P10", False, 0.0, {"error": str(e)}, f"db error: {e}")
    present = sorted(c for c in expected if c in existing)
    missing = sorted(c for c in expected if c not in existing)
    passed = not missing
    return PrimitiveResult(
        primitive="P10",
        passed=passed,
        score_hint=len(present) / len(expected),
        evidence={"table": table, "present": present, "missing": missing},
        message=f"{len(present)}/{len(expected)} cols" + (f"; missing={missing}" if missing else ""),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P11_db_index_check(inputs: Dict[str, Any]) -> PrimitiveResult:
    table = inputs.get("table", "")
    expected_indexes = inputs.get("expected_indexes", [])
    if not table:
        return PrimitiveResult("P11", False, 0.0, {}, "missing table")
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=%s",
                (table,),
            )
            rows = cur.fetchall()
    except Exception as e:
        return PrimitiveResult("P11", False, 0.0, {"error": str(e)}, f"db error: {e}")
    found = []
    for spec in expected_indexes:
        cols = spec.get("columns", [])
        col_re = ",\\s*".join(re.escape(c) for c in cols)
        ok = any(re.search(rf"\({col_re}\)", row[1]) for row in rows)
        found.append({"columns": cols, "found": ok})
    n_ok = sum(1 for x in found if x["found"])
    passed = n_ok == len(expected_indexes)
    return PrimitiveResult(
        primitive="P11",
        passed=passed,
        score_hint=n_ok / max(len(expected_indexes), 1),
        evidence={"table": table, "indexes_total": len(rows), "checks": found},
        message=f"{n_ok}/{len(expected_indexes)} index spec(s)",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_CONTAINER_FALLBACK: Dict[str, Any] = {
    "{{app_container}}": cfg.APP_CONTAINER,
    "{{db_container}}":  cfg.DB_CONTAINER,
    "{{cache_container}}": cfg.CACHE_CONTAINER,
    "{{APP_CONTAINER}}": cfg.APP_CONTAINER,
    "{{DB_CONTAINER}}":  cfg.DB_CONTAINER,
    "{{CACHE_CONTAINER}}": cfg.CACHE_CONTAINER,
}


def _resolve_container(raw: Any) -> str:
    if not raw:
        return cfg.APP_CONTAINER
    s = str(raw)
    if s in _CONTAINER_FALLBACK:
        logger.warning("P12: unresolved container placeholder %r; defaulting to %s", s, _CONTAINER_FALLBACK[s])
        return _CONTAINER_FALLBACK[s]
    if "{{" in s and "}}" in s:
        if "db" in s.lower():
            return cfg.DB_CONTAINER
        if "cache" in s.lower() or "redis" in s.lower():
            return cfg.CACHE_CONTAINER
        logger.warning("P12: unresolved container placeholder %r; defaulting to APP_CONTAINER", s)
        return cfg.APP_CONTAINER
    return s


def P12_docker_exec(inputs: Dict[str, Any]) -> PrimitiveResult:
    container = _resolve_container(inputs.get("container"))
    command = inputs.get("command", "")
    expect_success = bool(inputs.get("expect_success", True))
    expect_contains = inputs.get("expect_output_contains")
    expect_regex = inputs.get("expect_output_regex")
    timeout = int(inputs.get("timeout", 60))
    r = docker_exec(container, command, expect_success=expect_success, timeout=timeout)
    out = (r.get("stdout") or "") + (r.get("stderr") or "")
    passed = bool(r.get("success"))
    if expect_contains is not None:
        passed = passed and (expect_contains in out)
    if expect_regex is not None:
        passed = passed and bool(re.search(expect_regex, out))
    return PrimitiveResult(
        primitive="P12",
        passed=passed,
        score_hint=1.0 if passed else 0.0,
        evidence={"container": container, "command": command[:200], "returncode": r.get("returncode"), "stdout_head": out[:600]},
        message=f"{container} rc={r.get('returncode')} {'ok' if passed else 'fail'}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P13_auth_login(inputs: Dict[str, Any]) -> PrimitiveResult:
    role = inputs.get("role", "admin")
    cache: Dict[str, str] = ctx["auth_token_by_role"]

    if role in cache:
        token = cache[role]
        ctx["auth_token"] = token
        ctx["auth_role"] = role
        ctx[f"{role}_token"] = token
        return PrimitiveResult(
            primitive="P13",
            passed=True,
            score_hint=1.0,
            evidence={"role": role, "from_cache": True, "token_head": token[:8]},
            message=f"role={role} (cached)",
        )

    user_cfg = cfg.TEST_USERS.get(role)
    if user_cfg is None:
        raise ValueError(
            f"P13: unknown role={role!r}; configured roles are {list(cfg.TEST_USERS.keys())}"
        )
    username = inputs.get("username", user_cfg["username"])
    password = inputs.get("password", user_cfg["password"])

    token: Optional[str] = None
    src = ""

    import base64 as _b
    basic_header = {
        "Authorization": "Basic " + _b.b64encode(f"{username}:{password}".encode()).decode(),
    }

    def _accept(resp: Dict[str, Any]) -> Optional[str]:
        if resp.get("status_code") not in (200, 201):
            return None
        body = resp.get("body")
        if not isinstance(body, dict):
            return None
        tok = body.get("token") or body.get("key") or body.get("access")
        if isinstance(tok, str) and len(tok) >= 16:
            return tok
        return None

    rest_attempts: list[tuple[str, Dict[str, Any]]] = [
        ("rest_post_tokens",       {"method": "POST", "path": "/api/tokens",       "headers": {}, "body": {"username": username, "password": password}}),
        ("rest_post_user_token",   {"method": "POST", "path": "/api/user/token/",  "headers": basic_header, "body": None}),
        ("rest_get_user_token",    {"method": "GET",  "path": "/api/user/token/",  "headers": basic_header, "body": None}),
    ]
    for label, kw in rest_attempts:
        try:
            r = http_request(**kw)
            tok = _accept(r)
            if tok:
                token, src = tok, label
                break
        except Exception as e:
            logger.warning("P13 %s errored: %s", label, e)

    if not token:
        try:
            date_suffix = time.strftime("%Y%m%d", time.gmtime())
            new_tok = f"{cfg.TOKEN_PREFIX}{secrets.token_hex(24)}-{date_suffix}"
            with _db_conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT to_regclass(%s)", (cfg.TOKEN_TABLE_NAME,))
                if cur.fetchone()[0] is None:
                    raise RuntimeError(f"token table {cfg.TOKEN_TABLE_NAME} does not exist")
                cur.execute(
                    f"SELECT id FROM {cfg.USERS_TABLE_NAME} WHERE username=%s",
                    (username,),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError(f"user {username!r} not found in {cfg.USERS_TABLE_NAME}")
                user_id = row[0]
                cur.execute(
                    f"DELETE FROM {cfg.TOKEN_TABLE_NAME} WHERE name=%s OR key=%s",
                    (f"eval_{role}", new_tok),
                )
                cur.execute("""
                    SELECT column_name, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s
                """, (cfg.TOKEN_TABLE_NAME,))
                cols = {r[0]: (r[1] == "YES") for r in cur.fetchall()}
                values: Dict[str, Any] = {
                    "user_id": user_id,
                    "key":     new_tok,
                    "created": time.strftime("%Y-%m-%d %H:%M:%S+00:00", time.gmtime()),
                }
                if "name"     in cols: values["name"]     = f"eval_{role}"
                if "revoked"  in cols: values["revoked"]  = False
                if "expiry"   in cols and not cols["expiry"]:
                    values["expiry"] = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 365*24*3600))
                col_names = ", ".join(values.keys())
                placeholders = ", ".join(["%s"] * len(values))
                cur.execute(
                    f"INSERT INTO {cfg.TOKEN_TABLE_NAME} ({col_names}) VALUES ({placeholders})",
                    list(values.values()),
                )
                conn.commit()
            token = new_tok
            src = "db_insert"
        except Exception as e:
            logger.warning("P13 db_insert strategy errored: %s", e)

    if not token:
        return PrimitiveResult(
            primitive="P13",
            passed=False,
            score_hint=0.0,
            evidence={"role": role, "tried": ["rest_basic", "db_insert"]},
            message=f"could not obtain token for role={role}",
        )

    verify = http_request("GET", "/api/user/me/", headers={"Authorization": f"Token {token}"})
    if verify.get("status_code") != 200:
        return PrimitiveResult(
            primitive="P13",
            passed=False,
            score_hint=0.0,
            evidence={"role": role, "src": src, "verify_status": verify.get("status_code")},
            message=f"token verify failed (status={verify.get('status_code')})",
        )

    cache[role] = token
    ctx["auth_token"] = token
    ctx["auth_role"] = role
    ctx[f"{role}_token"] = token
    return PrimitiveResult(
        primitive="P13",
        passed=True,
        score_hint=1.0,
        evidence={"role": role, "src": src, "token_head": token[:8]},
        message=f"role={role} via {src}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P14_permission_check(inputs: Dict[str, Any]) -> PrimitiveResult:
    action = inputs.get("action", "")
    expected = inputs.get("expected_result", "denied").lower()
    expected_status = inputs.get("expected_status")
    expected_statuses = inputs.get("expected_statuses")
    body = inputs.get("body")
    parts = action.split(" ", 1)
    if len(parts) != 2:
        return PrimitiveResult("P14", False, 0.0, {}, f"bad action {action!r}")
    method, path = parts
    resp = http_request(method, path, body=body)
    status = resp.get("status_code", 0)
    if expected == "denied":
        passed = status in (403, 404)
        if expected_status is not None and expected_status in (403, 404, 400):
            passed = passed or (status == expected_status)
        if expected_statuses:
            allowed = {int(x) for x in expected_statuses}
            passed = passed or (status in allowed)
    else:
        passed = 200 <= status < 300
        if expected_status is not None:
            passed = (status == expected_status)
        if expected_statuses:
            allowed = {int(x) for x in expected_statuses}
            passed = passed or (status in allowed)
    return PrimitiveResult(
        primitive="P14",
        passed=passed,
        score_hint=1.0 if passed else 0.0,
        evidence={"action": action, "status": status, "expected": expected,
                  "expected_status": expected_status,
                  "expected_statuses": expected_statuses},
        message=f"{action} → {status} ({'pass' if passed else 'fail'})",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P15_status_code_assert(inputs: Dict[str, Any]) -> PrimitiveResult:
    resp = inputs.get("response") or ctx.get("__last_response__", {})
    if not isinstance(resp, dict):
        resp = ctx.get("__last_response__", {})
    status = resp.get("status_code", 0)
    accepted = set()
    for key in ("expected_status", "acceptable_statuses", "acceptable"):
        v = inputs.get(key)
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            accepted.update(int(x) for x in v if x is not None)
        else:
            accepted.add(int(v))
    passed = status in accepted if accepted else (200 <= status < 300)
    return PrimitiveResult(
        primitive="P15",
        passed=passed,
        score_hint=1.0 if passed else 0.0,
        evidence={"status": status, "expected": sorted(accepted) if accepted else None},
        message=f"status={status} (expected={sorted(accepted) if accepted else 'any 2xx'})",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P16_response_time_check(inputs: Dict[str, Any]) -> PrimitiveResult:
    max_ms = int(inputs.get("max_ms", 1000))
    resp = ctx.get("__last_response__", {})
    elapsed = int(resp.get("response_time_ms", 0))
    passed = elapsed <= max_ms
    return PrimitiveResult(
        primitive="P16",
        passed=passed,
        score_hint=1.0 if passed else max(0.0, 1.0 - (elapsed - max_ms) / max(max_ms, 1)),
        evidence={"elapsed_ms": elapsed, "max_ms": max_ms},
        message=f"{elapsed}ms (max {max_ms}ms)",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P17_llm_judge(inputs: Dict[str, Any]) -> PrimitiveResult:
    rubric_prompt = inputs.get("rubric_prompt", "")
    files_to_sample = inputs.get("files_to_sample", [])
    score_range = inputs.get("score_range", [0, 5])

    samples: List[Tuple[str, str]] = []
    for rel in files_to_sample[:8]:
        p = _safe_path(rel)
        if p.is_file():
            try:
                samples.append((str(p), p.read_text(errors="replace")[:6000]))
            except Exception:
                pass
        elif p.is_dir():
            for sub in list(p.glob("**/*.py"))[:3] + list(p.glob("**/*.tsx"))[:3]:
                try:
                    samples.append((str(sub), sub.read_text(errors="replace")[:4000]))
                except Exception:
                    pass

    try:
        from _llm_judge_safe import safe_llm_judge_call
    except ImportError:
        try:
            from evaluate._llm_judge_safe import safe_llm_judge_call
        except ImportError:
            import sys as _sys
            from pathlib import Path as _P
            _sys.path.insert(0, str(_P(__file__).resolve().parent))
            from _llm_judge_safe import safe_llm_judge_call

    res = safe_llm_judge_call(
        rubric_prompt=rubric_prompt,
        samples=samples,
        score_range=score_range,
        model=cfg.LLM_MODEL,
        api_key=cfg.LLM_API_KEY,
        api_base=cfg.LLM_API_BASE,
        temperature=cfg.LLM_TEMPERATURE,
        timeout=cfg.LLM_TIMEOUT,
    )

    evidence = {"score_range": score_range, **res.to_evidence()}

    if res.skipped:
        return PrimitiveResult(
            primitive="P17", passed=True, score_hint=1.0,
            evidence=evidence,
            message=f"llm-judge SKIPPED ({res.reason()}; node excluded from score)",
        )

    if res.parse_failure:
        return PrimitiveResult(
            primitive="P17", passed=False, score_hint=0.0,
            evidence=evidence,
            message=f"llm-judge: {res.reason()}",
        )

    score = res.score
    ratio = (score - score_range[0]) / max(score_range[1] - score_range[0], 1)
    return PrimitiveResult(
        primitive="P17",
        passed=score >= score_range[1] // 2,
        score_hint=ratio,
        evidence=evidence,
        message=f"llm-judge score={score}/{score_range[1]} (raw={res.raw[:60]!r})",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P23_file_upload_download(inputs: Dict[str, Any]) -> PrimitiveResult:
    upload = inputs.get("upload", {})
    if not upload:
        return PrimitiveResult("P23", False, 0.0, {}, "no upload spec")
    method = upload.get("method", "POST")
    path = upload.get("path", "/")
    field = upload.get("field_name", "file")
    file_content_b64 = upload.get("file_content", "")
    file_name = upload.get("file_name", "upload.bin")
    content_type = upload.get("content_type", "application/octet-stream")
    extra = upload.get("extra_form_fields", {}) or {}

    if file_content_b64.startswith("base64:"):
        try:
            payload = base64.b64decode(file_content_b64[len("base64:"):])
        except Exception:
            payload = file_content_b64.encode()
    else:
        payload = file_content_b64.encode()

    url = path if path.startswith("http") else cfg.APP_BASE_URL.rstrip("/") + path
    headers: Dict[str, str] = {}
    if ctx.get("auth_token"):
        headers["Authorization"] = f"Token {ctx['auth_token']}"

    files = {field: (file_name, io.BytesIO(payload), content_type)}
    try:
        import requests as _req
        t0 = time.perf_counter()
        resp = _req.request(method, url, headers=headers, files=files, data=extra, timeout=cfg.HTTP_TIMEOUT)
        elapsed = int((time.perf_counter() - t0) * 1000)
        try:
            body_obj = resp.json()
        except (ValueError, json.JSONDecodeError):
            body_obj = resp.text
        snap = {
            "url": url,
            "method": method,
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": body_obj,
            "body_text": resp.text[:4000],
            "response_time_ms": elapsed,
        }
        ctx["__last_response__"] = snap
        save_id_as = inputs.get("save_response_id_as")
        if save_id_as and isinstance(body_obj, dict):
            pk = body_obj.get("pk") or body_obj.get("id") or body_obj.get("ID")
            if pk is not None:
                ctx[save_id_as] = pk
        return PrimitiveResult(
            primitive="P23",
            passed=200 <= resp.status_code < 500,
            score_hint=1.0 if 200 <= resp.status_code < 300 else 0.5 if 200 <= resp.status_code < 400 else 0.0,
            evidence={"upload_response": snap},
            message=f"upload {method} {url} → {resp.status_code} ({elapsed}ms)",
        )
    except Exception as e:
        return PrimitiveResult("P23", False, 0.0, {"error": str(e)}, f"upload error: {e}")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
PRIMITIVES = {
    "P01": P01_file_exists,
    "P02": P02_file_content_match,
    "P03": P03_file_count,
    "P04": P04_http_request,
    "P05": P05_api_crud,
    "P06": P06_json_schema_match,
    "P07": P07_json_value_assert,
    "P08": P08_db_query,
    "P09": P09_db_table_exists,
    "P10": P10_db_column_check,
    "P11": P11_db_index_check,
    "P12": P12_docker_exec,
    "P13": P13_auth_login,
    "P14": P14_permission_check,
    "P15": P15_status_code_assert,
    "P16": P16_response_time_check,
    "P17": P17_llm_judge,
    "P23": P23_file_upload_download,
}


def execute_primitive(step: Dict[str, Any]) -> PrimitiveResult:
    ptype = step.get("type")
    inputs = substitute(step.get("inputs", {}) or {})
    fn = PRIMITIVES.get(ptype)
    if not fn:
        return PrimitiveResult(
            primitive=ptype or "?",
            passed=False,
            score_hint=0.0,
            evidence={"step": step},
            message=f"primitive {ptype!r} not implemented in this harness",
        )
    try:
        return fn(inputs)
    except Exception as e:
        return PrimitiveResult(
            primitive=ptype,
            passed=False,
            score_hint=0.0,
            evidence={"exception_class": type(e).__name__, "exception": str(e)[:300]},
            message=f"primitive raised: {e}",
        )
