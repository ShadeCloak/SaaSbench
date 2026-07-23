from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config as cfg
from .utils import (
    PrimitiveResult,
    clickhouse_query,
    ctx,
    docker_exec,
    http_request,
    json_get,
    logger,
    resolve_auth_headers,
    shell_exec,
    substitute,
)

try:
    import psycopg
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False
    try:
        import psycopg2 as psycopg
        HAS_PSYCOPG = True
    except ImportError:
        psycopg = None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _pg_conn():
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
    expected_type = inputs.get("type", "any")

    candidates: List[str] = []
    if isinstance(inputs.get("path_any_of"), (list, tuple)):
        candidates.extend(str(c) for c in inputs["path_any_of"] if isinstance(c, str))
    elif inputs.get("path"):
        candidates.append(str(inputs["path"]))

    if not candidates:
        return PrimitiveResult("P01", False, 0.0, {}, "no path / path_any_of provided")

    matched_p: Optional[Path] = None
    for rel in candidates:
        p = _safe_path(rel)
        ok = p.exists()
        if ok and expected_type == "file":
            ok = p.is_file()
        elif ok and expected_type in ("dir", "directory"):
            ok = p.is_dir()
        if ok:
            matched_p = p
            break

    exists = matched_p is not None
    return PrimitiveResult(
        primitive="P01",
        passed=exists,
        score_hint=1.0 if exists else 0.0,
        evidence={"path": str(matched_p) if matched_p else candidates[0],
                    "exists": exists, "type": expected_type,
                    "candidates_tried": candidates},
        message=(f"found: {matched_p}" if matched_p
                  else f"missing: tried {candidates}"),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P02_file_content_match(inputs: Dict[str, Any]) -> PrimitiveResult:
    pat = inputs.get("pattern", "")
    mode = inputs.get("match_type", "contains")

    candidates: List[str] = []
    if isinstance(inputs.get("path_any_of"), (list, tuple)):
        candidates.extend(str(c) for c in inputs["path_any_of"] if isinstance(c, str))
    elif inputs.get("path"):
        candidates.append(str(inputs["path"]))

    if not candidates:
        return PrimitiveResult("P02", False, 0.0, {}, "no path / path_any_of provided")

    used_p: Optional[Path] = None
    for rel in candidates:
        cand = _safe_path(rel)
        if cand.exists():
            used_p = cand
            break

    if used_p is None:
        return PrimitiveResult("P02", False, 0.0,
                                  {"candidates_tried": candidates},
                                  "file not found (none of the candidates exist)")

    try:
        text = used_p.read_text(errors="replace")
    except Exception as e:
        return PrimitiveResult("P02", False, 0.0, {"path": str(used_p)},
                                  f"read error: {e}")

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
        evidence={"path": str(used_p), "pattern": pat, "match_type": mode,
                    "match_count": cnt, "candidates_tried": candidates},
        message=f"{cnt} match(es) in {used_p}" if matched else f"no match in {used_p}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P03_file_count(inputs: Dict[str, Any]) -> PrimitiveResult:
    glob_patterns = inputs.get("glob_any_of") or [inputs.get("glob", "**/*")]
    base = _safe_path(inputs.get("base_dir", "."))
    min_expected = int(inputs.get("min_expected", 1))
    if not base.exists():
        return PrimitiveResult("P03", False, 0.0, {"base_dir": str(base)}, "base dir missing")
    best_count = 0
    best_pattern = glob_patterns[0]
    best_files: list = []
    for pat in glob_patterns:
        files = list(base.glob(pat))
        if len(files) > best_count:
            best_count = len(files)
            best_pattern = pat
            best_files = files
    cnt = best_count
    passed = cnt >= min_expected
    ratio = min(cnt / max(min_expected, 1), 1.0)
    return PrimitiveResult(
        primitive="P03",
        passed=passed,
        score_hint=ratio,
        evidence={"base_dir": str(base), "glob": best_pattern, "count": cnt,
                    "patterns_tried": glob_patterns,
                    "files_sample": [str(f) for f in best_files[:10]]},
        message=f"{cnt} files (>= {min_expected}) via {best_pattern}" if passed else f"only {cnt} files, need {min_expected}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P04_http_request(inputs: Dict[str, Any]) -> PrimitiveResult:
    method = inputs.get("method", "GET")
    path = inputs.get("path", "/")
    headers = inputs.get("headers", {}) or {}
    body = inputs.get("body", None)
    raw_body = inputs.get("raw_body", None)
    params = inputs.get("params", None)
    form = inputs.get("form", None)
    follow_redirects = inputs.get("follow_redirects", True)
    auth_mode = inputs.get("auth_mode", None)
    timeout = inputs.get("timeout", cfg.HTTP_TIMEOUT)
    repeat = int(inputs.get("repeat", 1))

    if inputs.get("attach_csrf") and isinstance(auth_mode, str) \
            and auth_mode.startswith("session_eval_"):
        _tok = ctx.get(auth_mode + "_csrf")
        if _tok:
            headers = {**headers, "x-csrf-token": _tok}

    last_resp: Dict[str, Any] = {}
    for _ in range(max(repeat, 1)):
        last_resp = http_request(
            method, path, headers=headers, body=body, raw_body=raw_body,
            params=params, form=form, timeout=timeout,
            follow_redirects=follow_redirects, auth_mode=auth_mode,
        )

    ctx["__last_response__"] = last_resp
    err = last_resp.get("error")
    if err:
        return PrimitiveResult(
            primitive="P04", passed=False, score_hint=0.0,
            evidence={"response": last_resp},
            message=f"network error: {err}",
        )
    return PrimitiveResult(
        primitive="P04", passed=True, score_hint=1.0,
        evidence={"response": last_resp},
        message=f"{method} {last_resp['url']} → {last_resp['status_code']} ({last_resp['response_time_ms']}ms)",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P05_api_crud(inputs: Dict[str, Any]) -> PrimitiveResult:
    resource = inputs.get("resource", "/").rstrip("/")
    create_body = inputs.get("create_body", {})
    update_body = inputs.get("update_body", {})
    auth_mode = inputs.get("auth_mode", None)
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

    create = http_request("POST", resource + "/", body=create_body, auth_mode=auth_mode)
    evidence["create"] = create
    if create.get("status_code") == expected_create or (
        isinstance(expected_create, (list, tuple)) and create.get("status_code") in expected_create
    ):
        steps_passed += 1
        body = create.get("body", {})
        if isinstance(body, dict):
            last_id = body.get("id") or body.get("pk") or body.get("uuid")
    else:
        msgs.append(f"CREATE expected {expected_create} got {create.get('status_code')}")

    if last_id is not None:
        read = http_request("GET", f"{resource}/{last_id}/", auth_mode=auth_mode)
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
        upd = http_request("PATCH", f"{resource}/{last_id}/", body=update_body, auth_mode=auth_mode)
        evidence["update"] = upd
        if upd.get("status_code") == expected_update:
            steps_passed += 1
        else:
            msgs.append(f"UPDATE expected {expected_update} got {upd.get('status_code')}")
    else:
        msgs.append("UPDATE skipped (no id)")

    if last_id is not None:
        dele = http_request("DELETE", f"{resource}/{last_id}/", auth_mode=auth_mode)
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
        evidence={**evidence, "steps_passed": steps_passed, "steps_total": steps_total, "last_id": last_id},
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
        message=f"{len(required)-len(missing)}/{len(required)} fields" + (f"; bad_type={bad_type}" if bad_type else ""),
    )


def _typecheck(v: Any, expected: str) -> bool:
    table = {
        "string": str, "str": str,
        "integer": int, "int": int,
        "boolean": bool, "bool": bool,
        "number": (int, float), "float": float,
        "array": list, "list": list,
        "object": dict, "dict": dict,
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
    assertions_any_of = inputs.get("assertions_any_of", [])

    results = []
    passed_count = 0
    for a in assertions:
        ok, detail = _eval_assertion(resp, body, a)
        results.append({"assertion": a, "passed": ok, "detail": detail})
        if ok:
            passed_count += 1
    all_required_ok = (passed_count == len(assertions)) if assertions else True

    any_of_results = []
    any_of_pass = False
    if assertions_any_of:
        for a in assertions_any_of:
            ok, detail = _eval_assertion(resp, body, a)
            any_of_results.append({"assertion": a, "passed": ok, "detail": detail})
            if ok:
                any_of_pass = True
        all_any_of_ok = any_of_pass
    else:
        all_any_of_ok = True

    if len(assertions) + len(assertions_any_of) == 0:
        last_status = (resp.get("status") or resp.get("status_code") or 0) if isinstance(resp, dict) else 0
        return PrimitiveResult(
            primitive="P07",
            passed=True,
            score_hint=1.0,
            evidence={"assertions_passed": 0, "assertions_total": 0,
                      "any_of_pass": False, "any_of_total": 0,
                      "results": [], "any_of_results": [],
                      "skipped_reason": f"vacuous (no assertions); last_status={last_status}"},
            message="P07 vacuously pass (no assertions)",
        )
    overall_ok = all_required_ok and all_any_of_ok
    total_checks = len(assertions) + (1 if assertions_any_of else 0)
    passed_checks = passed_count + (1 if (assertions_any_of and any_of_pass) else 0)
    return PrimitiveResult(
        primitive="P07",
        passed=overall_ok,
        score_hint=passed_checks / max(total_checks, 1),
        evidence={"assertions_passed": passed_count, "assertions_total": len(assertions),
                    "any_of_pass": any_of_pass, "any_of_total": len(assertions_any_of),
                    "results": results[:30], "any_of_results": any_of_results[:30]},
        message=f"{passed_count}/{len(assertions)} assertions" + (
            f" + any_of {1 if any_of_pass else 0}/{len(assertions_any_of)}" if assertions_any_of else ""
        ),
    )


def _eval_assertion(full_resp: Dict[str, Any], body: Any, a: Dict[str, Any]) -> Tuple[bool, str]:
    path = a.get("path") or (a.get("path_any_of") or [""])[0]
    if not path:
        return False, "no path in assertion"

    val: Any = None
    if path == "$.body_text":
        val = full_resp.get("body_text", "")
    elif path == "$":
        val = full_resp.get("body_text", "") if not isinstance(body, (dict, list)) else body
    elif path.startswith("$.headers["):
        m = re.match(r"\$\.headers\[['\"]([^'\"]+)['\"]\]", path)
        if not m:
            return False, f"bad header path {path!r}"
        key = m.group(1).lower()
        val = full_resp.get("headers", {}).get(key)
    elif path.startswith("$.headers."):
        key = path[len("$.headers."):].lower()
        val = full_resp.get("headers", {}).get(key)
    else:
        val = json_get(body, path)

    op = a.get("operator")
    if op == "exists":
        return (val is not None), f"actual={val!r}"
    if op == "not_exists":
        return (val is None), f"actual={val!r}"

    if "expected" in a:
        want = a["expected"]
        tol = a.get("tolerance", 0)
        if isinstance(want, (int, float)) and isinstance(val, (int, float)):
            ok = abs(val - want) <= tol
        elif isinstance(want, (int, float)) and isinstance(val, str):
            try:
                ok = abs(float(val) - float(want)) <= tol
            except (TypeError, ValueError):
                ok = False
        else:
            ok = (val == want)
        if not ok:
            return False, f"actual={val!r} expected={want!r} tol={tol}"

    if "expected_in" in a:
        want_set = list(a["expected_in"])
        if val not in want_set:
            if str(val) not in [str(w) for w in want_set]:
                return False, f"actual={val!r} not in {want_set}"

    if "expected_min" in a:
        want = a["expected_min"]
        try:
            if float(val) < float(want):
                return False, f"actual={val!r} < min={want!r}"
        except (TypeError, ValueError):
            return False, f"actual={val!r} not numeric for min check"

    if "expected_max" in a:
        want = a["expected_max"]
        try:
            if float(val) > float(want):
                return False, f"actual={val!r} > max={want!r}"
        except (TypeError, ValueError):
            return False, f"actual={val!r} not numeric for max check"

    if "expected_min_length" in a:
        want = int(a["expected_min_length"])
        if not (hasattr(val, "__len__") and len(val) >= want):
            return False, f"len={len(val) if hasattr(val,'__len__') else 'N/A'} < min_length={want}"

    if "expected_type" in a:
        want_t = a["expected_type"]
        if not _typecheck(val, want_t):
            return False, f"type={type(val).__name__} != {want_t}"

    if "expected_contains" in a:
        want = a["expected_contains"]
        if isinstance(val, list):
            if want not in val and str(want) not in [str(v) for v in val]:
                return False, f"list {val!r} doesn't contain {want!r}"
        elif isinstance(val, str):
            if str(want) not in val:
                return False, f"str {val[:60]!r} doesn't contain {want!r}"
        else:
            return False, f"actual={val!r} not list/str (cannot 'contains')"

    if "expected_contains_all" in a:
        wants = list(a["expected_contains_all"])
        if not isinstance(val, list):
            return False, f"actual={val!r} not list"
        actual_set = set(str(v) for v in val)
        missing = [w for w in wants if str(w) not in actual_set]
        if missing:
            return False, f"missing={missing} from actual={val!r}"

    if "match_regex" in a:
        pat = a["match_regex"]
        if val is None:
            return False, f"actual is None, regex /{pat}/"
        if not re.search(pat, str(val)):
            return False, f"regex /{pat}/ no match against {str(val)[:80]!r}"

    return True, "ok"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P08_db_query(inputs: Dict[str, Any]) -> PrimitiveResult:
    sql = inputs.get("sql", "")
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, context)
    except Exception:
        pass
    db_kind = (inputs.get("db") or "postgres").lower()
    assertions = inputs.get("assertions", [])
    expected_result = inputs.get("expected_result")
    expected_min_rows = inputs.get("expected_min_rows")
    if not sql.strip():
        return PrimitiveResult("P08", False, 0.0, {}, "empty SQL")

    rows: List[Dict[str, Any]] = []
    err: Optional[str] = None
    if db_kind == "clickhouse":
        ch_resp = clickhouse_query(sql)
        rows = ch_resp.get("rows", [])
        err = ch_resp.get("error")
    else:
        try:
            with _pg_conn() as conn, conn.cursor() as cur:
                cur.execute(sql)
                if cur.description:
                    cols = [d.name for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                else:
                    conn.commit()
                    rows = []
        except Exception as e:
            err = str(e)

    if err:
        return PrimitiveResult("P08", False, 0.0, {"sql": sql[:300], "error": err},
                                  f"db error: {err}")

    rows_json = {"rows": rows, "row_count": len(rows)}
    full_resp = {"body": rows_json, "headers": {}, "body_text": json.dumps(rows_json, default=str)[:8000]}

    issues: List[str] = []

    if expected_result is not None and rows != expected_result:
        issues.append(f"rows!=expected_result (got {len(rows)} rows)")
    if expected_min_rows is not None and len(rows) < int(expected_min_rows):
        issues.append(f"rowcount {len(rows)} < min {expected_min_rows}")

    a_results = []
    a_passed = 0
    for a in assertions:
        ok, detail = _eval_assertion(full_resp, rows_json, a)
        a_results.append({"assertion": a, "passed": ok, "detail": detail})
        if ok:
            a_passed += 1
    if assertions and a_passed != len(assertions):
        issues.extend([str(r["detail"]) for r in a_results if not r["passed"]])

    passed = not issues
    return PrimitiveResult(
        primitive="P08",
        passed=passed,
        score_hint=1.0 if passed else (a_passed / max(len(assertions), 1) if assertions else 0.0),
        evidence={"sql": sql[:500], "db_kind": db_kind, "row_count": len(rows),
                    "rows_sample": rows[:5], "issues": issues, "assertion_results": a_results[:10]},
        message=f"[{db_kind}] {len(rows)} rows; {'OK' if passed else '; '.join(issues)[:200]}",
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P09_db_table_exists(inputs: Dict[str, Any]) -> PrimitiveResult:
    tables = inputs.get("tables", [])
    if not tables:
        return PrimitiveResult("P09", False, 0.0, {}, "no tables specified")
    try:
        lowered = [t.lower() for t in tables]
        with _pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE LOWER(table_schema)='public' "
                "AND LOWER(table_name) = ANY(%s)",
                (lowered,),
            )
            existing_actual = sorted({r[0] for r in cur.fetchall()})
            existing_lower = {r.lower() for r in existing_actual}
    except Exception as e:
        return PrimitiveResult("P09", False, 0.0, {"error": str(e)}, f"db error: {e}")
    missing = sorted(t for t in tables if t.lower() not in existing_lower)
    existing = existing_actual
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
        with _pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE LOWER(table_schema)='public' "
                "AND LOWER(table_name) = LOWER(%s)",
                (table,),
            )
            existing_actual = {r[0] for r in cur.fetchall()}
            existing_lower = {c.lower() for c in existing_actual}
    except Exception as e:
        return PrimitiveResult("P10", False, 0.0, {"error": str(e)}, f"db error: {e}")
    present = sorted(c for c in expected if c.lower() in existing_lower)
    missing = sorted(c for c in expected if c.lower() not in existing_lower)
    existing = existing_actual
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
    default_order = str(inputs.get("column_order", "set")).lower()
    if not table:
        return PrimitiveResult("P11", False, 0.0, {}, "missing table")
    try:
        with _pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE LOWER(schemaname)='public' AND LOWER(tablename)=LOWER(%s)",
                (table,),
            )
            rows = cur.fetchall()
    except Exception as e:
        return PrimitiveResult("P11", False, 0.0, {"error": str(e)}, f"db error: {e}")

    def _extract_index_cols(indexdef: str) -> List[str]:
        m = re.search(r"\(([^)]+)\)", indexdef)
        if not m:
            return []
        return [c.strip().split()[0] for c in m.group(1).split(",")]

    index_col_lists = [(_extract_index_cols(row[1]), row[1]) for row in rows]

    found = []
    for spec in expected_indexes:
        cols = spec.get("columns", [])
        cols_lower = [c.lower() for c in cols]
        order_mode = str(spec.get("column_order", default_order)).lower()
        ok = False
        for actual_cols, _indexdef in index_col_lists:
            actual_lower = [c.lower() for c in actual_cols]
            if order_mode == "strict":
                if actual_lower[: len(cols_lower)] == cols_lower:
                    ok = True
                    break
            else:
                if set(actual_lower) == set(cols_lower):
                    ok = True
                    break
        found.append({"columns": cols, "column_order": order_mode, "found": ok})
    n_ok = sum(1 for x in found if x["found"])
    passed = n_ok == len(expected_indexes)
    return PrimitiveResult(
        primitive="P11",
        passed=passed,
        score_hint=n_ok / max(len(expected_indexes), 1),
        evidence={"table": table, "indexes_total": len(rows),
                    "default_column_order": default_order, "checks": found},
        message=f"{n_ok}/{len(expected_indexes)} index spec(s) (order={default_order})",
    )


# ---------------------------------------------------------------------------
#
#
# ---------------------------------------------------------------------------
ELIXIR_ERROR_PATTERNS = [
    re.compile(r"\*\* \(Mix\)"),
    re.compile(r"\*\* \(CompileError"),
    re.compile(r"\*\* \(UndefinedFunctionError"),
    re.compile(r"\*\* \(KeyError"),
    re.compile(r"\*\* \(ArgumentError"),
    re.compile(r"\*\* \(MatchError"),
    re.compile(r"\*\* \(RuntimeError"),
    re.compile(r"\*\* \(FunctionClauseError"),
    re.compile(r"could not compile dependency"),
    re.compile(r"undefined function .* of module \w"),
    re.compile(r"\(Mix\) The task .* could not be found"),
]


def P12_docker_exec(inputs: Dict[str, Any]) -> PrimitiveResult:
    raw_command = inputs.get("command", "")
    container = inputs.get("container", "")
    expect_success = bool(inputs.get("expect_success", True))
    expect_contains = inputs.get("expect_output_contains")
    expect_regex = inputs.get("expect_output_match_regex") or inputs.get("expect_output_regex")
    expected_exit_code = inputs.get("exit_code", None)
    expected_acceptable_exit_codes = inputs.get("expected_acceptable_exit_codes")
    forbid_pattern = inputs.get("forbid_pattern")
    forbid_elixir_errors = bool(inputs.get("forbid_elixir_errors", False))
    timeout = int(inputs.get("timeout", 90))

    if raw_command.strip().startswith("docker exec") or raw_command.strip().startswith("sleep "):
        r = shell_exec(raw_command, timeout=timeout)
    else:
        if not container:
            container = cfg.APP_CONTAINER
        r = docker_exec(container, raw_command, expect_success=expect_success, timeout=timeout)

    out = (r.get("stdout") or "") + "\n" + (r.get("stderr") or "")
    rc = r.get("returncode", -1)

    passed = True
    reason = ""

    # Step 1: rc check
    if expected_acceptable_exit_codes is not None:
        accs = expected_acceptable_exit_codes if isinstance(expected_acceptable_exit_codes, (list, tuple)) else [expected_acceptable_exit_codes]
        if rc not in [int(x) for x in accs]:
            passed = False
            reason = f"exit_code={rc}, not in acceptable {accs}"
    elif expected_exit_code is not None:
        if rc != int(expected_exit_code):
            passed = False
            reason = f"exit_code={rc}, expected {expected_exit_code}"
    elif expect_success:
        if rc != 0:
            passed = False
            reason = f"non-zero exit_code={rc}"

    # Step 2: forbidden Elixir/Mix error patterns — only when the node
    forbid_hit = None
    if passed and forbid_elixir_errors:
        for pat in ELIXIR_ERROR_PATTERNS:
            m = pat.search(out)
            if m:
                forbid_hit = m.group(0)
                passed = False
                reason = f"forbidden Elixir error pattern in stderr: {forbid_hit!r}"
                break

    # Step 3: optional caller-supplied forbid_pattern
    if passed and forbid_pattern:
        if re.search(forbid_pattern, out):
            passed = False
            reason = f"caller forbid_pattern matched: /{forbid_pattern}/"

    # Step 4: expected substring
    if passed and expect_contains is not None and expect_contains not in out:
        passed = False
        reason = f"output missing {expect_contains!r}"

    # Step 5: expected regex
    if passed and expect_regex is not None and not re.search(expect_regex, out):
        passed = False
        reason = f"output no match for /{expect_regex}/"

    return PrimitiveResult(
        primitive="P12",
        passed=passed,
        score_hint=1.0 if passed else 0.0,
        evidence={"command": raw_command[:300], "returncode": rc,
                    "stdout_head": out[:1500], "container": container,
                    "expected_exit_code": expected_exit_code,
                    "expect_regex": expect_regex,
                    "expect_contains": expect_contains,
                    "forbid_hit": forbid_hit},
        message=f"rc={rc} {'ok' if passed else f'FAIL ({reason})'}",
    )


# ---------------------------------------------------------------------------
#
#
# ---------------------------------------------------------------------------
def P13_auth_login(inputs: Dict[str, Any]) -> PrimitiveResult:
    role = inputs.get("role", "admin")
    method = inputs.get("method", "api_token")

    ctx["auth_role"] = role
    cache: Dict[str, str] = ctx["auth_token_by_role"]

    if method == "api_token" and role == "admin":
        from .utils import _read_token_file
        token = _read_token_file(cfg.EVAL_API_KEY_FILE)
        if token:
            cache[role] = token
            ctx["eval_api_key"] = token
            ctx["auth_token"] = token
            return PrimitiveResult(
                primitive="P13", passed=True, score_hint=1.0,
                evidence={"role": role, "method": method, "token_head": token[:8],
                            "from_file": cfg.EVAL_API_KEY_FILE},
                message=f"role={role} api_token (from {cfg.EVAL_API_KEY_FILE})",
            )
        return PrimitiveResult(
            primitive="P13", passed=False, score_hint=0.0,
            evidence={"role": role, "method": method,
                        "expected_file": cfg.EVAL_API_KEY_FILE},
            message=f"P13: {cfg.EVAL_API_KEY_FILE} empty; "
                      f"AUTH_USER_API_KEY_CREATE must run first",
        )

    cache_key = f"session_eval_{role}"
    if cache_key in ctx and ctx[cache_key]:
        return PrimitiveResult(
            primitive="P13", passed=True, score_hint=1.0,
            evidence={"role": role, "method": "session", "from_cache": True,
                        "cookie_head": ctx[cache_key][:30]},
            message=f"role={role} session (cached)",
        )

    user_cfg = cfg.TEST_USERS.get(role)
    if not user_cfg:
        return PrimitiveResult(
            primitive="P13", passed=False, score_hint=0.0,
            evidence={"role": role, "method": method,
                        "available_roles": list(cfg.TEST_USERS.keys())},
            message=f"P13: unknown role {role!r}",
        )

    CSRF_FIELD_CANDIDATES = [
        "_csrf_token",
        "csrfmiddlewaretoken",
        "authenticity_token",
        "_csrf",
        "_token",
    ]
    CSRF_HEADER_CANDIDATES = ["X-CSRF-Token", "X-XSRF-Token", "X-CSRFToken"]
    CSRF_COOKIE_CANDIDATES = ["XSRF-TOKEN", "csrftoken", "_csrf"]

    import requests as _req
    sess = _req.Session()
    try:
        r_get = sess.get(cfg.APP_BASE_URL.rstrip("/") + "/login",
                            timeout=cfg.HTTP_TIMEOUT, allow_redirects=True)
        csrf_field, csrf_token = "", ""
        for field in CSRF_FIELD_CANDIDATES:
            m = re.search(
                rf'name=["\']{re.escape(field)}["\'][^>]*?value=["\']([^"\']+)["\']',
                r_get.text,
            )
            if m:
                csrf_field = field
                csrf_token = m.group(1)
                break
        if not csrf_token:
            m = re.search(
                r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']',
                r_get.text,
            )
            if m:
                csrf_field = "_csrf_token"
                csrf_token = m.group(1)
        if not csrf_token:
            for cookie_name in CSRF_COOKIE_CANDIDATES:
                cval = sess.cookies.get(cookie_name)
                if cval:
                    csrf_field = ""
                    csrf_token = cval
                    break
    except Exception as e:
        return PrimitiveResult(
            primitive="P13", passed=False, score_hint=0.0,
            evidence={"role": role, "method": "session", "error": str(e)},
            message=f"P13: GET /login failed: {e}",
        )

    post_url = cfg.APP_BASE_URL.rstrip("/") + "/login"
    headers_csrf = {h: csrf_token for h in CSRF_HEADER_CANDIDATES} if csrf_token else {}
    form_data = {"email": user_cfg["email"], "password": user_cfg["password"]}
    if csrf_field:
        form_data[csrf_field] = csrf_token
    try:
        r_post = sess.post(post_url, data=form_data, headers=headers_csrf,
                              timeout=cfg.HTTP_TIMEOUT, allow_redirects=False)
        if r_post.status_code in (400, 415):
            r_post = sess.post(post_url, json=form_data, headers=headers_csrf,
                                  timeout=cfg.HTTP_TIMEOUT, allow_redirects=False)
    except Exception as e:
        return PrimitiveResult(
            primitive="P13", passed=False, score_hint=0.0,
            evidence={"role": role, "method": "session", "error": str(e)},
            message=f"P13: POST /login failed: {e}",
        )

    if r_post.status_code in (200, 302) and sess.cookies:
        #
        csrf_after = ""
        for seed_path in ("/sites", "/settings/preferences", "/"):
            try:
                r_seed = sess.get(cfg.APP_BASE_URL.rstrip("/") + seed_path,
                                    timeout=cfg.HTTP_TIMEOUT, allow_redirects=True)
            except Exception:
                continue
            m = re.search(
                r'name=["\']_csrf_token["\'][^>]*?value=["\']([^"\']+)["\']',
                r_seed.text,
            ) or re.search(
                r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']',
                r_seed.text,
            )
            if m:
                csrf_after = m.group(1)
                break

        cookie_parts = [f"{c.name}={c.value}" for c in sess.cookies]
        cookie_str = "; ".join(cookie_parts)
        ctx[cache_key] = cookie_str
        cache[role] = cookie_str
        if csrf_after:
            ctx[cache_key + "_csrf"] = csrf_after

        return PrimitiveResult(
            primitive="P13", passed=True, score_hint=1.0,
            evidence={"role": role, "method": "session",
                        "post_status": r_post.status_code,
                        "cookies_set": [c.name for c in sess.cookies],
                        "csrf_captured": bool(csrf_after),
                        "cookie_head": cookie_str[:60]},
            message=f"role={role} session (POST /login → {r_post.status_code})",
        )

    return PrimitiveResult(
        primitive="P13", passed=False, score_hint=0.0,
        evidence={"role": role, "method": "session",
                    "post_status": r_post.status_code,
                    "post_body_head": r_post.text[:300]},
        message=f"P13: POST /login → {r_post.status_code} (no session cookie)",
    )


# ---------------------------------------------------------------------------
#
#
# ---------------------------------------------------------------------------
def P14_permission_check(inputs: Dict[str, Any]) -> PrimitiveResult:
    action_raw = inputs.get("action", "")
    expected = str(inputs.get("expected_result", "denied")).lower()
    if expected in ("deny", "rejected", "forbidden"):
        expected = "denied"
    if expected in ("allow", "permitted", "accepted"):
        expected = "allowed"
    expected_status = inputs.get("expected_status")
    body = inputs.get("body")
    auth_mode = inputs.get("auth_mode")
    headers = inputs.get("headers", {}) or {}

    parts = action_raw.split(" ", 1)
    if len(parts) != 2:
        return PrimitiveResult("P14", False, 0.0, {}, f"bad action {action_raw!r}")
    method, path = parts

    if inputs.get("attach_csrf") and isinstance(auth_mode, str) \
            and auth_mode.startswith("session_eval_"):
        _tok = ctx.get(auth_mode + "_csrf")
        if _tok:
            headers = {**headers, "x-csrf-token": _tok}

    resp = http_request(method, path, body=body, auth_mode=auth_mode, headers=headers,
                          follow_redirects=False)
    ctx["__last_response__"] = resp
    status = resp.get("status_code", 0)

    DEFAULT_DENIED_CODES = {401, 403}

    denied_codes_extend = inputs.get("denied_codes_extend") or []
    effective_denied_codes = set(DEFAULT_DENIED_CODES)
    if denied_codes_extend:
        try:
            effective_denied_codes.update(int(c) for c in denied_codes_extend)
        except (TypeError, ValueError):
            pass

    acceptable_statuses = inputs.get("acceptable_statuses")

    if expected == "denied":
        if acceptable_statuses:
            passed = status in set(acceptable_statuses)
        elif expected_status is not None:
            passed = (status == int(expected_status))
        else:
            passed = status in effective_denied_codes
    else:
        if acceptable_statuses:
            passed = status in set(acceptable_statuses)
        elif expected_status is not None:
            passed = (status == int(expected_status))
        else:
            passed = 200 <= status < 300

    return PrimitiveResult(
        primitive="P14",
        passed=passed,
        score_hint=1.0 if passed else 0.0,
        evidence={"action": action_raw, "status": status, "expected": expected,
                    "expected_status": expected_status, "auth_mode": auth_mode,
                    "default_denied_codes": sorted(DEFAULT_DENIED_CODES),
                    "effective_denied_codes": sorted(effective_denied_codes),
                    "denied_codes_extend": denied_codes_extend,
                    "response_body_head": str(resp.get("body_text", ""))[:300]},
        message=f"{action_raw} → {status} ({'pass' if passed else 'fail'})",
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
    expected = sorted(accepted) if accepted else None
    acceptable = sorted(accepted) if accepted else None
    return PrimitiveResult(
        primitive="P15",
        passed=passed,
        score_hint=1.0 if passed else 0.0,
        evidence={"status": status, "expected": expected, "acceptable": acceptable},
        message=f"status={status} (expected={expected} acceptable={acceptable})",
    )


# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
def P16_response_time_check(inputs: Dict[str, Any]) -> PrimitiveResult:
    max_ms = int(inputs.get("max_ms", 1000))
    samples = max(1, int(inputs.get("samples", 5)))
    max_ratio = inputs.get("max_ratio")

    last_resp = ctx.get("__last_response__", {}) or {}
    last_method = last_resp.get("method")
    last_url = last_resp.get("url")

    elapsed_list: List[int] = []
    if last_method and last_url and samples > 1:
        elapsed_list.append(int(last_resp.get("response_time_ms", 0)))
        for _ in range(samples - 1):
            try:
                resp = http_request(last_method, last_url, follow_redirects=False)
                elapsed_list.append(int(resp.get("response_time_ms", 0)))
            except Exception:
                pass
    else:
        elapsed_list.append(int(last_resp.get("response_time_ms", 0)))

    elapsed_list.sort()
    elapsed = elapsed_list[len(elapsed_list) // 2]

    effective_max = max_ms
    baseline_ms = int(ctx.get("__baseline_response_ms__", 0) or 0)
    if max_ratio and baseline_ms > 0:
        try:
            effective_max = max(max_ms, int(baseline_ms * float(max_ratio)))
        except (TypeError, ValueError):
            pass

    if inputs.get("set_baseline"):
        ctx["__baseline_response_ms__"] = elapsed

    passed = elapsed <= effective_max
    return PrimitiveResult(
        primitive="P16",
        passed=passed,
        score_hint=(
            1.0 if passed
            else max(0.0, 1.0 - (elapsed - effective_max) / max(effective_max, 1))
        ),
        evidence={"elapsed_ms": elapsed, "max_ms": max_ms,
                    "effective_max_ms": effective_max, "samples_taken": len(elapsed_list),
                    "all_samples_ms": elapsed_list, "baseline_ms": baseline_ms,
                    "max_ratio": max_ratio},
        message=(f"{elapsed}ms median of {len(elapsed_list)} sample(s) "
                  f"(max {effective_max}ms{f', baseline×{max_ratio}' if max_ratio else ''})"),
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def P17_llm_judge(inputs: Dict[str, Any]) -> PrimitiveResult:
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
        return {"score": 0, "max_score": _sr[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "SKIP_LLM_JUDGE=1 (LLM judge intentionally skipped for peer-review-grade scoring)"}
    rubric_prompt = inputs.get("rubric_prompt", "")
    files_to_sample = inputs.get("files_to_sample", [])
    rubric_id = inputs.get("rubric_id", "rubric")
    explicit_range = inputs.get("score_range")
    if isinstance(explicit_range, (list, tuple)) and len(explicit_range) == 2:
        score_range = list(explicit_range)
    else:
        inferred_max = inputs.get("max_score") or inputs.get("maxScore")
        if inferred_max is not None:
            try:
                score_range = [0, int(inferred_max)]
            except (TypeError, ValueError):
                score_range = [0, 5]
        else:
            score_range = [0, 5]

    EXTENSIONS = [
        ".ex", ".exs",
        ".py",
        ".go",
        ".rs",
        ".java", ".kt", ".scala",
        ".rb",
        ".ts", ".tsx", ".js", ".jsx",
        ".cs",
        ".cpp",
    ]

    samples: List[Tuple[str, str]] = []
    for rel in files_to_sample[:8]:
        p = _safe_path(rel)
        if p.is_file():
            try:
                samples.append((str(p), p.read_text(errors="replace")[:6000]))
            except Exception:
                pass
        elif p.is_dir():
            files: List[Path] = []
            for ext in EXTENSIONS:
                files.extend(p.glob(f"**/*{ext}"))
            files = sorted(set(files))
            _kw_text = f"{rubric_id} {rubric_prompt}".lower()
            _STOP = {
                "the", "and", "for", "with", "that", "this", "each", "from",
                "into", "your", "namespace", "module", "modules", "return",
                "json", "score", "reason", "integer", "criteria", "criterion",
                "check", "checks", "points", "point", "range", "scoring",
                "anchors", "output", "object", "short", "justification",
                "goal", "evidence", "task", "spec", "when", "does", "not",
                "via", "per", "new", "all", "one", "two", "four", "nine",
                "exist", "exists", "distinct", "settings", "setting", "value",
                "values", "under", "plus", "etc", "either", "drawn", "across",
                "single", "edit", "stage", "stages", "case", "cases", "weak",
                "good", "none", "full", "pass", "least",
            }
            _kw = {t for t in re.findall(r"[a-z][a-z0-9_]{3,}", _kw_text)
                   if t not in _STOP}
            for _t in list(_kw):
                for _part in _t.split("_"):
                    if len(_part) >= 3:
                        _kw.add(_part)
            if _kw:
                def _relevance(fp: Path) -> int:
                    low = str(fp).lower()
                    return sum(1 for k in _kw if k in low)
                ranked = sorted(files, key=lambda fp: (-_relevance(fp), str(fp)))
                hits = [fp for fp in ranked if _relevance(fp) > 0]
                files = (hits or ranked)[:6]
            else:
                files = files[:6]
            for sub in files:
                try:
                    samples.append((str(sub), sub.read_text(errors="replace")[:4000]))
                except Exception:
                    pass

    if not samples:
        return PrimitiveResult(
            primitive="P17", passed=True, score_hint=1.0,
            evidence={
                "rubric_id": rubric_id,
                "score_range": score_range,
                "llm_judge_skipped": True,
                "skip_reason": "SKIPPED_NO_EVIDENCE",
                "files_to_sample": files_to_sample,
                "extensions_checked": EXTENSIONS,
                "samples_found": 0,
            },
            message=(
                f"llm-judge SKIPPED (SKIPPED_NO_EVIDENCE: files_to_sample "
                f"matched 0 files across {len(EXTENSIONS)} extensions; "
                f"node excluded from total)"
            ),
        )

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
        max_tokens=1024,
    )

    evidence = {"rubric_id": rubric_id, "score_range": score_range, **res.to_evidence()}

    if res.skipped:
        return PrimitiveResult(
            primitive="P17", passed=True, score_hint=1.0,
            evidence=evidence,
            message=f"llm-judge SKIPPED ({res.reason()}; node excluded from total)",
        )

    if res.parse_failure:
        evidence["llm_judge_skipped"] = True
        evidence["skip_reason"] = "PARSE_FAILURE"
        return PrimitiveResult(
            primitive="P17", passed=True, score_hint=1.0,
            evidence=evidence,
            message=f"llm-judge SKIPPED ({res.reason()}; node excluded from total)",
        )

    score = res.score
    ratio = (score - score_range[0]) / max(score_range[1] - score_range[0], 1)
    return PrimitiveResult(
        primitive="P17",
        passed=score >= score_range[1] // 2,
        score_hint=ratio,
        evidence=evidence,
        message=f"llm-judge {rubric_id} score={score}/{score_range[1]}",
    )


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
