from __future__ import annotations

import hashlib
import http.server
import json
import os
import re
import socket
import socketserver
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import requests

import config
from utils import (
    PrimitiveResult, db_query, db_query_dict, docker_exec, http_request,
    jsonpath_get, log,
)


class LLMJudgeUnavailable(BaseException):
    pass

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_PLACEHOLDER_RE = re.compile(r"\{\{([^}]+)\}\}")


def _substitute(value: Any, ctx: dict) -> Any:
    if isinstance(value, str):
        def repl(m):
            key = m.group(1).strip()
            if key in ctx:
                return str(ctx[key])
            return m.group(0)
        return _PLACEHOLDER_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, ctx) for v in value]
    return value


# ===========================================================================
# ===========================================================================
def P01(inputs: dict, ctx: dict) -> PrimitiveResult:
    path = _substitute(inputs["path"], ctx)
    p = Path(path) if Path(path).is_absolute() else (config.WORKSPACE_DIR / path)
    exists = p.exists()
    typ = inputs.get("type", "file")
    if exists:
        passed = (typ == "file" and p.is_file()) or (typ == "dir" and p.is_dir()) or (typ not in ("file", "dir"))
    else:
        passed = False
    return PrimitiveResult("P01", passed,
                            message=f"path={p}, exists={exists}",
                            data={"path": str(p), "exists": exists})


def P02(inputs: dict, ctx: dict) -> PrimitiveResult:
    path = _substitute(inputs["path"], ctx)
    pattern = _substitute(inputs["pattern"], ctx)
    match_type = inputs.get("match_type", "contains")
    p = Path(path) if Path(path).is_absolute() else (config.WORKSPACE_DIR / path)
    if not p.exists():
        return PrimitiveResult("P02", False, message=f"file not found: {p}")
    text = p.read_text(errors="ignore")
    if match_type == "contains":
        passed = pattern in text
    elif match_type == "regex":
        passed = bool(re.search(pattern, text))
    else:
        passed = pattern in text
    return PrimitiveResult("P02", passed, message=f"match_type={match_type}, pattern={pattern[:60]}",
                            data={"matched": passed})


def P03(inputs: dict, ctx: dict) -> PrimitiveResult:
    glob = _substitute(inputs["glob"], ctx)
    base = inputs.get("base_dir", str(config.WORKSPACE_DIR))
    base = _substitute(base, ctx)
    base_p = Path(base) if Path(base).is_absolute() else (config.WORKSPACE_DIR / base)
    files = list(base_p.glob(glob))
    n = len(files)
    min_expected = inputs.get("min_expected", 1)
    return PrimitiveResult("P03", n >= min_expected,
                            message=f"count={n}, min_expected={min_expected}",
                            data={"count": n, "files": [str(f.relative_to(base_p)) for f in files[:10]]})


# ===========================================================================
# ===========================================================================
def P04(inputs: dict, ctx: dict) -> PrimitiveResult:
    method = inputs.get("method", "GET").upper()
    path = _substitute(inputs.get("path", "/"), ctx)
    headers = _substitute(inputs.get("headers", {}), ctx) or {}
    body = _substitute(inputs.get("body"), ctx)
    timeout = inputs.get("timeout", config.DEFAULT_HTTP_TIMEOUT)

    if "auth_token" in ctx and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {ctx['auth_token']}"

    resp = http_request(method, path, headers=headers, body=body, timeout=timeout,
                        base_url=config.APP_BASE_URL)
    ctx["last_response"] = resp
    ctx["last_response_status"] = resp.get("status_code", -1)
    ctx["last_response_body"] = resp.get("body")
    ctx["last_response_headers"] = resp.get("headers", {})

    cv = inputs.get("capture_var")
    if cv:
        if ":" in cv:
            var, _, path_expr = cv.partition(":")
            var = var.replace("_path", "")
            ctx[var] = jsonpath_get(resp.get("body"), path_expr)
        else:
            ctx[cv] = resp.get("body")

    return PrimitiveResult("P04", True,
                            message=f"{method} {path} → {resp.get('status_code')}",
                            data=resp,
                            response_time_ms=resp.get("response_time_ms", 0))


# ===========================================================================
# ===========================================================================
def P05(inputs: dict, ctx: dict) -> PrimitiveResult:
    resource = _substitute(inputs["resource"], ctx)
    create_body = _substitute(inputs.get("create_body", {}), ctx)
    update_body = _substitute(inputs.get("update_body", {}), ctx)
    headers = {}
    if "auth_token" in ctx:
        headers["Authorization"] = f"Bearer {ctx['auth_token']}"

    steps = []
    create = http_request("POST", f"{resource}.create", headers=headers, body=create_body)
    steps.append(("create", create.get("status_code")))
    new_id = jsonpath_get(create.get("body"), "$.data.id")

    if new_id:
        info = http_request("POST", f"{resource}.info", headers=headers, body={"id": new_id})
        steps.append(("info", info.get("status_code")))
        upd = http_request("POST", f"{resource}.update", headers=headers, body={**update_body, "id": new_id})
        steps.append(("update", upd.get("status_code")))
        dele = http_request("POST", f"{resource}.delete", headers=headers, body={"id": new_id})
        steps.append(("delete", dele.get("status_code")))
    n_pass = sum(1 for _, sc in steps if 200 <= (sc or -1) < 300)
    return PrimitiveResult("P05", n_pass == len(steps),
                            message=f"crud steps={steps}",
                            data={"steps": steps, "pass_ratio": n_pass / max(len(steps), 1), "id": new_id})


# ===========================================================================
# ===========================================================================
def P06(inputs: dict, ctx: dict) -> PrimitiveResult:
    body = ctx.get("last_response_body") or inputs.get("body")
    required = inputs.get("required_fields") or inputs.get("required_keys") or []
    min_count = inputs.get("required_keys_min_count")

    if min_count is not None and isinstance(body, dict):
        passed = len(body.keys()) >= int(min_count)
        return PrimitiveResult("P06", passed,
                                message=f"keys_count={len(body.keys())} min_required={min_count}",
                                data={"keys_count": len(body.keys())})

    missing = []
    for f in required:
        if jsonpath_get(body, f if f.startswith("$") else f"$.{f}") is None:
            missing.append(f)
    return PrimitiveResult("P06", not missing,
                            message=f"missing={missing}" if missing else "all_required_present",
                            data={"missing": missing})


# ===========================================================================
# ===========================================================================
def _match_assertion(actual: Any, a: dict) -> tuple[bool, str]:
    if "expected" in a:
        exp = a["expected"]
        match = a.get("match", "equal")
        if match == "equal":
            return actual == exp, f"actual={actual!r} expected={exp!r}"
        if match == "contains":
            return (str(exp) in str(actual)) if actual is not None else False, f"contains {exp!r}"
        if match == "regex":
            return bool(actual is not None and re.search(str(exp), str(actual))), f"regex {exp!r}"
        if match == "endswith":
            return str(actual or "").endswith(str(exp)), f"endswith {exp!r}"
        if match == "startswith":
            return str(actual or "").startswith(str(exp)), f"startswith {exp!r}"
        if match == "in":
            return actual in exp, f"in {exp!r}"
    if "expected_in" in a:
        return actual in a["expected_in"], f"actual={actual!r} expected_in={a['expected_in']}"
    if a.get("exists") is True:
        if a.get("not_null"):
            return actual is not None, f"actual={actual!r} not_null"
        return actual is not None or actual == 0 or actual == "" or actual is False, f"exists actual={actual!r}"
    if a.get("type"):
        types = {"array": list, "object": dict, "string": str, "number": (int, float), "boolean": bool}
        t = types.get(a["type"], object)
        if not isinstance(actual, t):
            return False, f"actual is {type(actual).__name__}, expected {a['type']}"
        if a.get("min_length") is not None:
            return len(actual) >= int(a["min_length"]), f"len={len(actual)} min={a['min_length']}"
        if a.get("max_length") is not None:
            return len(actual) <= int(a["max_length"]), f"len={len(actual)} max={a['max_length']}"
        return True, f"type ok"
    if a.get("min_length") is not None:
        return len(actual or []) >= int(a["min_length"]), f"len={len(actual or [])} min={a['min_length']}"
    if a.get("max_length") is not None:
        return len(actual or []) <= int(a["max_length"]), f"len={len(actual or [])} max={a['max_length']}"
    if a.get("tolerance"):
        try:
            return abs(float(actual) - float(a.get("expected_value", 0))) <= float(a["tolerance"]), "tolerance"
        except Exception:
            return False, "tolerance type error"
    return False, f"unrecognised assertion {a!r}"


def P07(inputs: dict, ctx: dict) -> PrimitiveResult:
    assertions = inputs.get("assertions", [])
    body = ctx.get("last_response_body")
    headers = ctx.get("last_response_headers", {})
    results = []
    n_or = 0
    or_passed = False
    for a in assertions:
        path = a.get("path") or a.get("or_path")
        is_or = "or_path" in a or "or_header" in a
        if is_or:
            n_or += 1
        if "or_header" in a:
            actual = headers.get(a["or_header"])
        else:
            actual = jsonpath_get(body, path)
        if "compare_query_fields" in a:
            keys = a["compare_query_fields"]
            vals = [ctx.get(k) for k in keys]
            ok = all(v == vals[0] for v in vals)
            results.append((ok, f"compare {keys} → {vals}"))
            continue
        ok, why = _match_assertion(actual, a)
        if is_or:
            if ok:
                or_passed = True
            results.append((ok, f"OR {path}: {why}"))
        else:
            results.append((ok, f"{path}: {why}"))

    final_results = []
    for r, msg in results:
        if msg.startswith("OR ") and or_passed:
            final_results.append((True, msg))
        else:
            final_results.append((r, msg))
    n_pass = sum(1 for r, _ in final_results if r)
    n_total = len(final_results) or 1
    return PrimitiveResult("P07", n_pass == n_total,
                            message=" | ".join(m for _, m in final_results)[:300],
                            data={"pass_ratio": n_pass / n_total,
                                  "passed": n_pass, "total": n_total})


# ===========================================================================
# ===========================================================================
def P08(inputs: dict, ctx: dict) -> PrimitiveResult:
    sql = _substitute(inputs["sql"], ctx)
    expected_rows = inputs.get("expected_rows")
    expected_match = inputs.get("expected_row_match")
    capture_var = inputs.get("capture_var")

    res = db_query(sql)
    if not res["ok"]:
        return PrimitiveResult("P08", False, message=f"sql_error: {res.get('error', '?')[:200]}",
                                data=res)
    rows = res["rows"]

    if capture_var and rows:
        ctx[capture_var] = rows[0][0] if rows[0] else None

    if expected_rows is not None:
        if len(rows) != len(expected_rows):
            return PrimitiveResult("P08", False,
                                    message=f"row_count_mismatch: got {len(rows)}, expected {len(expected_rows)}",
                                    data={"rows": rows, "expected": expected_rows})
        for actual_row, exp in zip(rows, expected_rows):
            for col_idx, (k, v) in enumerate(exp.items()):
                if col_idx >= len(actual_row):
                    return PrimitiveResult("P08", False,
                                            message=f"col_missing for {k}",
                                            data={"row": actual_row, "expected": exp})
                a = actual_row[col_idx]
                if isinstance(v, bool):
                    a = (a == "t" or a == "true" or a == "True")
                elif isinstance(v, int):
                    try:
                        a = int(a)
                    except Exception:
                        pass
                elif v is None:
                    if a == "" or a is None:
                        a = None
                if a != v:
                    return PrimitiveResult("P08", False,
                                            message=f"col {k}: got {a!r}, expected {v!r}",
                                            data={"row": actual_row, "expected": exp})
        return PrimitiveResult("P08", True, message=f"matched {len(rows)} rows", data={"rows": rows})

    if expected_match is not None:
        if not rows:
            return PrimitiveResult("P08", False, message="no rows", data={})
        first = rows[0]
        for k, v in expected_match.items():
            if k.endswith("_min"):
                actual_col = k[:-4]
                idx = 0
                try:
                    actual_v = int(first[idx])
                except Exception:
                    actual_v = first[idx]
                if not (isinstance(actual_v, int) and actual_v >= int(v)):
                    return PrimitiveResult("P08", False,
                                            message=f"min check failed: {actual_col} actual={actual_v} min={v}",
                                            data={"row": first})
            elif v == "NOT NULL":
                if not first[0]:
                    return PrimitiveResult("P08", False, message=f"{k} is NULL", data={"row": first})
        return PrimitiveResult("P08", True, message=f"row_match ok: {first}", data={"row": first})

    return PrimitiveResult("P08", True, message=f"sql ran, {len(rows)} rows", data={"rows": rows})


# ===========================================================================
# ===========================================================================
def P09(inputs: dict, ctx: dict) -> PrimitiveResult:
    tables = inputs.get("tables", [])
    missing = []
    for t in tables:
        sql = f"SELECT to_regclass('public.\"{t}\"');"
        res = db_query(sql)
        if not res["ok"] or not res["rows"] or not res["rows"][0][0] or res["rows"][0][0] == "":
            missing.append(t)
    return PrimitiveResult("P09", not missing,
                            message=f"missing_tables={missing}" if missing else "all_present",
                            data={"missing": missing, "checked": tables})


# ===========================================================================
# ===========================================================================
def P10(inputs: dict, ctx: dict) -> PrimitiveResult:
    table = inputs["table"]
    expected = inputs.get("expected_columns", [])
    sql = f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' ORDER BY ordinal_position;"
    res = db_query(sql)
    if not res["ok"]:
        return PrimitiveResult("P10", False, message=f"sql_error", data=res)
    actual = [r[0] for r in res["rows"]]
    missing = [c for c in expected if c not in actual]
    return PrimitiveResult("P10", not missing,
                            message=f"missing_columns={missing}" if missing else f"all {len(expected)} columns present",
                            data={"missing": missing, "actual_count": len(actual),
                                  "expected_count": len(expected),
                                  "pass_ratio": (len(expected) - len(missing)) / max(len(expected), 1)})


# ===========================================================================
# ===========================================================================
def P11(inputs: dict, ctx: dict) -> PrimitiveResult:
    table = inputs["table"]
    cols = inputs.get("columns", [])
    sql = (f"SELECT i.indexname FROM pg_indexes i WHERE i.tablename='{table}' AND "
           + " AND ".join(f"i.indexdef ILIKE '%{c}%'" for c in cols) + ";")
    res = db_query(sql)
    passed = res["ok"] and bool(res["rows"])
    return PrimitiveResult("P11", passed,
                            message=f"table={table}, cols={cols}, found={[r[0] for r in res.get('rows', [])]}",
                            data={"indexes_found": [r[0] for r in res.get("rows", [])]})


# ===========================================================================
# ===========================================================================
def P12(inputs: dict, ctx: dict) -> PrimitiveResult:
    cmd = _substitute(inputs["command"], ctx)
    container = inputs.get("container", config.APP_CONTAINER)
    timeout = inputs.get("timeout", 60)

    runs_on_host = (
        cmd.lstrip().startswith("docker")
        or cmd.lstrip().startswith("cat /tmp/saasbench_")
        or cmd.lstrip().startswith("test -s /tmp/saasbench_")
        or cmd.lstrip().startswith("test ")
        or cmd.lstrip().startswith("rm /tmp/saasbench_")
        or cmd.lstrip().startswith("rm -f /tmp/saasbench_")
        or cmd.lstrip().startswith("TOKEN=$(cat /tmp/saasbench_")
        or cmd.lstrip().startswith("L=$(wc")
        or cmd.lstrip().startswith("curl")
    )
    if runs_on_host or inputs.get("on_host"):
        try:
            out = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout)
            res = {"exit_code": out.returncode, "stdout": out.stdout, "stderr": out.stderr}
        except Exception as e:
            res = {"exit_code": -1, "stdout": "", "stderr": str(e)}
    else:
        res = docker_exec(container, cmd, timeout=timeout)

    expected_exit = inputs.get("expected_exit_code", 0)
    expected_substr = _substitute(inputs.get("expected_stdout_contains"), ctx)
    capture_var = inputs.get("capture_stdout_var")
    if capture_var:
        lines = [l for l in res["stdout"].split("\n") if l.strip()]
        ctx[capture_var] = lines[-1] if lines else ""

    passed = res["exit_code"] == expected_exit
    if expected_substr and expected_substr not in res["stdout"]:
        passed = False
    return PrimitiveResult("P12", passed,
                            message=f"exit={res['exit_code']} stdout={res['stdout'][:80]!r}",
                            data=res)


# ===========================================================================
# ===========================================================================
_TOKEN_CACHE: dict[str, str] = {}


def _bootstrap_token_via_db(role: str, *, user_email: str | None = None) -> str | None:
    import json as _json
    import requests as _req

    email = user_email or config.TEST_USERS.get(role, {}).get("email")
    if not email:
        return None
    safe_email = email.replace("'", "''")
    res = db_query(f"SELECT id FROM users WHERE email='{safe_email}' LIMIT 1;")
    if not res.get("ok") or not res.get("rows") or not res["rows"][0]:
        log.warning("P13(%s): user %s not in DB; trying admin-cookie fallback", role, email)
        if not _ADMIN_COOKIE_TOKEN[0]:
            _ADMIN_COOKIE_TOKEN[0] = _try_fetch_admin_cookie_token()
        return _ADMIN_COOKIE_TOKEN[0]
    user_id = res["rows"][0][0]

    import os, secrets as _secrets, string
    prefix = os.getenv("EVAL_API_TOKEN_PREFIX", "ol_api_")
    if len(prefix) != 7:
        prefix = "ol_api_"
    rnd = "".join(_secrets.choice(string.ascii_letters + string.digits) for _ in range(38))
    token = prefix + rnd
    h = hashlib.sha256(token.encode()).hexdigest()
    last4 = token[-4:]
    name = config.API_KEY_NAME_PREFIX + role
    db_query(f"DELETE FROM \"apiKeys\" WHERE name='{name}' AND \"userId\"='{user_id}';")
    safe_token = token.replace("'", "''")
    safe_hash = h.replace("'", "''")
    insert_sql = (f"INSERT INTO \"apiKeys\" "
                  f"(id, name, secret, last4, hash, \"userId\", \"createdAt\", \"updatedAt\") "
                  f"VALUES (gen_random_uuid(), '{name}', '{safe_token}', '{last4}', '{safe_hash}', "
                  f"'{user_id}', NOW(), NOW());")
    insert_res = db_query(insert_sql)
    if not insert_res.get("ok"):
        fallback_sql = (f"INSERT INTO \"apiKeys\" (id, name, hash, \"userId\", \"createdAt\", \"updatedAt\") "
                        f"VALUES (gen_random_uuid(), '{name}', '{safe_hash}', '{user_id}', NOW(), NOW());")
        if not db_query(fallback_sql).get("ok"):
            return None

    try:
        r = _req.post(config.APP_BASE_URL + "/api/auth.info",
                      headers={"Authorization": f"Bearer {token}"},
                      timeout=8)
        if r.status_code == 200:
            return token
        log.info("P13(%s) ApiKey route returned %s; falling back to admin-cookie share",
                 role, r.status_code)
    except Exception as e:
        log.warning("P13 verify request failed: %s", e)
        return None

    if not _ADMIN_COOKIE_TOKEN[0]:
        admin_token = _try_fetch_admin_cookie_token()
        if admin_token:
            _ADMIN_COOKIE_TOKEN[0] = admin_token
    return _ADMIN_COOKIE_TOKEN[0]


_ADMIN_COOKIE_TOKEN: list[str | None] = [None]


_ADMIN_COOKIE_FILE = Path("/tmp/saasbench_eval_admin_cookie.txt")


def _try_fetch_admin_cookie_token() -> str | None:
    import requests as _req
    if _ADMIN_COOKIE_FILE.exists():
        cached = _ADMIN_COOKIE_FILE.read_text().strip()
        if cached:
            try:
                r = _req.post(config.APP_BASE_URL + "/api/auth.info",
                              headers={"Authorization": f"Bearer {cached}"},
                              timeout=5)
                if r.status_code == 200:
                    return cached
            except Exception:
                pass

    import os
    if os.getenv("SAASBENCH_ALLOW_DB_RESET", "0") != "1":
        log.warning("admin cookie missing and DB reset disabled (default: disabled to prevent "
                    "TRUNCATE TABLE teams CASCADE wiping candidate data; set "
                    "SAASBENCH_ALLOW_DB_RESET=1 to opt in to destructive bootstrap)")
        return None
    try:
        from utils import db_query as _q
        _q("TRUNCATE TABLE teams CASCADE;")
        r = _req.post(config.APP_BASE_URL + "/api/installation.create",
                      json={
                          "teamName": "EvalTeam",
                          "userName": "Eval Admin",
                          "userEmail": "eval_admin@example.com",
                      },
                      allow_redirects=False, timeout=10)
        if r.status_code in (200, 302):
            cookie = r.cookies.get("accessToken")
            if cookie:
                _ADMIN_COOKIE_FILE.write_text(cookie)
                log.info("admin cookie acquired & cached (installation.create -> %s)", r.status_code)
                for r_name, mail in [("Eval Member","eval_member@example.com"),
                                     ("Eval Viewer","eval_viewer@example.com"),
                                     ("Eval Guest","eval_guest@example.com")]:
                    role_lc = r_name.split()[1].lower()
                    _q(f"INSERT INTO users (id, name, email, role, \"teamId\", "
                       f"\"createdAt\", \"updatedAt\", \"jwtSecret\", \"notificationSettings\") "
                       f"SELECT gen_random_uuid(), '{r_name}', '{mail}', '{role_lc}', "
                       f"t.id, NOW(), NOW(), decode(repeat('ab',64),'hex'), '{{}}'::jsonb "
                       f"FROM teams t WHERE name='EvalTeam' LIMIT 1 ON CONFLICT DO NOTHING;")
                _q("INSERT INTO teams (id,name,subdomain,\"createdAt\",\"updatedAt\") "
                   "VALUES (gen_random_uuid(),'OtherTeam','otherteam',NOW(),NOW()) ON CONFLICT DO NOTHING;")
                _q("INSERT INTO users (id, name, email, role, \"teamId\", "
                   "\"createdAt\", \"updatedAt\", \"jwtSecret\", \"notificationSettings\") "
                   "SELECT gen_random_uuid(),'Other Team Admin','eval_other_team@example.com', "
                   "'admin',t.id,NOW(),NOW(),decode(repeat('12',64),'hex'),'{}'::jsonb "
                   "FROM teams t WHERE name='OtherTeam' LIMIT 1 ON CONFLICT DO NOTHING;")
                return cookie
        log.info("installation.create did not yield cookie (status=%s)", r.status_code)
    except Exception as e:
        log.warning("installation.create for admin cookie failed: %s", e)
    return None


def P13(inputs: dict, ctx: dict) -> PrimitiveResult:
    role = inputs.get("role", "admin")
    method = inputs.get("method", "api_token")
    cache_key = role
    from pathlib import Path as _P
    fixture = _P(f"/tmp/saasbench_eval_{role}_token.txt")
    if fixture.exists():
        token = fixture.read_text().strip()
        if token:
            _TOKEN_CACHE[cache_key] = token
            ctx["auth_token"] = token
            ctx[f"{role}_token"] = token
            return PrimitiveResult("P13", True, message=f"role={role} (fixture token)",
                                    data={"role": role, "method": "fixture"})
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and not cached.startswith("PLACEHOLDER_"):
        ctx["auth_token"] = cached
        ctx[f"{role}_token"] = cached
        return PrimitiveResult("P13", True, message=f"role={role} (cached token)",
                                data={"role": role, "method": "cached"})

    if method in ("api_token", "auto"):
        token = _bootstrap_token_via_db(role)
        if token:
            _TOKEN_CACHE[cache_key] = token
            ctx["auth_token"] = token
            ctx[f"{role}_token"] = token
            return PrimitiveResult("P13", True, message=f"role={role} (DB-bootstrapped)",
                                    data={"role": role, "method": "db_direct"})

    placeholder = f"PLACEHOLDER_{role}_TOKEN"
    _TOKEN_CACHE[cache_key] = placeholder
    ctx["auth_token"] = placeholder
    ctx[f"{role}_token"] = placeholder
    return PrimitiveResult("P13", False, message=f"role={role} (could not obtain real token; using placeholder)",
                            data={"role": role, "method": "placeholder"})


# ===========================================================================
# ===========================================================================
def P14(inputs: dict, ctx: dict) -> PrimitiveResult:
    expected = inputs.get("expected_result", "denied")
    acceptable_statuses = inputs.get("acceptable_statuses",
                                      [403, 404] if expected == "denied" else [200])
    last_status = ctx.get("last_response_status", -1)
    passed = last_status in acceptable_statuses
    return PrimitiveResult("P14", passed,
                            message=f"last_status={last_status} expected={expected} acceptable={acceptable_statuses}",
                            data={"status_code": last_status, "expected_result": expected})


# ===========================================================================
# ===========================================================================
def P15(inputs: dict, ctx: dict) -> PrimitiveResult:
    accepted = set()
    expected = inputs.get("expected_status")
    if isinstance(expected, (list, tuple, set)):
        accepted.update(int(x) for x in expected if x is not None)
    elif expected is not None:
        accepted.add(int(expected))
    acc_alias = inputs.get("acceptable_statuses") or inputs.get("acceptable")
    if isinstance(acc_alias, (list, tuple, set)):
        accepted.update(int(x) for x in acc_alias if x is not None)
    elif acc_alias is not None:
        accepted.add(int(acc_alias))
    last = ctx.get("last_response_status", -1)
    passed = last in accepted if accepted else False
    show = sorted(accepted)
    return PrimitiveResult("P15", passed,
                            message=f"got {last}, expected {show}",
                            data={"status_code": last, "expected": show})


# ===========================================================================
# ===========================================================================
def P16(inputs: dict, ctx: dict) -> PrimitiveResult:
    threshold = inputs.get("threshold_ms", 1000)
    last = ctx.get("last_response", {}).get("response_time_ms", 0)
    return PrimitiveResult("P16", last <= threshold,
                            message=f"response_time={last}ms threshold={threshold}ms",
                            data={"response_time_ms": last, "threshold_ms": threshold},
                            response_time_ms=last)


# ===========================================================================
# ===========================================================================
def P17(inputs: dict, ctx: dict) -> PrimitiveResult:
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
            "P17", False,
            message="LLM judge SKIPPED (SKIP_LLM_JUDGE set)",
            data={"skipped": True, "llm_api_failure": False})
    from _llm_judge_safe import safe_chat_completion

    rubric = inputs.get("rubric_prompt", "")
    files = inputs.get("files_to_sample", [])
    score_range = inputs.get("score_range", [0, 5])

    if not config.LLM_API_KEY:
        return PrimitiveResult(
            "P17", False,
            message="LLM judge SKIPPED (LLM_API_KEY unset)",
            data={"skipped": True, "llm_api_failure": True})

    workspace_dir = str(config.WORKSPACE_DIR).rstrip("/")

    def _rewrite_path(raw: str) -> str:
        if raw == "/app":
            return workspace_dir
        if raw.startswith("/app/"):
            return workspace_dir + raw[len("/app"):]
        return raw

    snippets = []
    resolved_paths: list[tuple[str, str, bool]] = []
    for f in files:
        resolved = _rewrite_path(f)
        p = Path(resolved)
        exists = p.exists()
        resolved_paths.append((f, resolved, exists))
        if not exists:
            snippets.append(f"# {f} (NOT FOUND)\n")
            continue
        if p.is_dir():
            entries = sorted(x.name for x in p.iterdir())[:25]
            snippets.append(f"# {f} (directory listing, {len(entries)} entries)\n" + "\n".join(entries))
        else:
            try:
                text = p.read_text(errors="ignore")[:4000]
            except Exception as e:
                text = f"<read error: {e}>"
            snippets.append(f"# {f}\n{text}")

    evidence_blob = "\n\n---\n\n".join(snippets)

    messages = [
        {"role": "system", "content": "You are a strict code reviewer. Reply with JSON only."},
        {"role": "user", "content": (
            f"{rubric}\n\nEvidence:\n```\n{evidence_blob}\n```\n\n"
            f"Reply STRICT JSON: {{\"score\": <integer>, \"justification\": \"<one sentence>\"}}.\n"
            f"IMPORTANT: 'score' MUST be an integer in the inclusive range [{score_range[0]}, {score_range[1]}]. "
            f"The maximum possible score for THIS rubric is {score_range[1]}; do NOT exceed it. "
            f"A perfect implementation that meets every criterion should receive exactly {score_range[1]}."
        )},
    ]

    import os as _os_io
    _io_dir = _os_io.getenv("LLM_JUDGE_IO_DIR")
    _node_id = ctx.get("_node_id", "unknown") if isinstance(ctx, dict) else "unknown"
    _io_path = None
    if _io_dir:
        try:
            from pathlib import Path as _PathIO
            import json as _json_io
            import time as _time_io
            _io_root = _PathIO(_io_dir)
            _io_root.mkdir(parents=True, exist_ok=True)
            _stamp = _time_io.strftime("%Y%m%dT%H%M%S")
            _io_path = _io_root / f"{_node_id}_{_stamp}.json"
            _io_payload = {
                "node_id": _node_id,
                "model": config.LLM_MODEL,
                "api_base": config.LLM_API_BASE,
                "score_range": score_range,
                "rubric_prompt": rubric,
                "files_to_sample": list(files),
                "resolved_paths": [
                    {"original": o, "resolved": r, "exists": e}
                    for (o, r, e) in resolved_paths
                ],
                "evidence_blob_length": len(evidence_blob),
                "messages_request": messages,
            }
            _io_path.write_text(_json_io.dumps(_io_payload, indent=2, ensure_ascii=False))
        except Exception as _e_io:
            log.warning("LLM_JUDGE_IO_DIR write request failed: %s", _e_io)
            _io_path = None

    _RETRIES = 6
    _last_err = ""
    for _attempt in range(_RETRIES):
        res = safe_chat_completion(
            messages=messages,
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE,
            temperature=0.0,
            max_tokens=900,
        )

        if _io_path is not None:
            try:
                import json as _json_io
                _payload = _json_io.loads(_io_path.read_text())
                _payload.setdefault("attempts", []).append({
                    "attempt": _attempt,
                    "skipped": res.skipped,
                    "llm_api_failure": res.llm_api_failure,
                    "exception_class": res.exception_class,
                    "error": res.error,
                    "raw": res.raw,
                })
                _io_path.write_text(_json_io.dumps(_payload, indent=2, ensure_ascii=False))
            except Exception as _e_io2:
                log.warning("LLM_JUDGE_IO_DIR write response failed: %s", _e_io2)

        if res.skipped:
            _last_err = f"api failure: {res.exception_class or ''} {res.error or ''}".strip()
            time.sleep(min(2.0 * (_attempt + 1), 8.0))
            continue

        content = res.raw
        parse_diag = {}
        try:
            m = re.search(r"\{.*\}", content, re.S)
            if not m:
                raise ValueError("model reply contained no JSON verdict")
            parsed = json.loads(m.group(0))
            parse_diag["regex_matched"] = True
            score_unclamped = int(parsed.get("score", 0))
            score = max(score_range[0], min(score_range[1], score_unclamped))
            parse_diag["score_raw"] = score_unclamped
            parse_diag["score_clamped"] = score
            parse_diag["clamp_applied"] = (score_unclamped != score)
        except Exception as e:
            _last_err = f"parse failure: {e}; raw={(content or '')[:120]!r}"
            time.sleep(min(1.5 * (_attempt + 1), 6.0))
            continue

        if _io_path is not None:
            try:
                import json as _json_io
                _payload = _json_io.loads(_io_path.read_text())
                _payload["parse_diagnostics"] = {
                    **parse_diag,
                    "parsed_justification_preview": parsed.get("justification", "")[:200],
                }
                _io_path.write_text(_json_io.dumps(_payload, indent=2, ensure_ascii=False))
            except Exception as _e_io3:
                log.warning("LLM_JUDGE_IO_DIR parse_diagnostics write failed: %s", _e_io3)

        return PrimitiveResult(
            "P17", True,
            message=f"score={score}/{score_range[1]} — {parsed.get('justification', '')[:160]}",
            data={"score": score, "max": score_range[1],
                  "justification": parsed.get("justification", ""),
                  "raw": content[:500],
                  "io_log": str(_io_path) if _io_path else None,
                  "evidence_resolved_paths": [
                      {"original": o, "resolved": r, "exists": e}
                      for (o, r, e) in resolved_paths
                  ]})

    return PrimitiveResult(
        "P17", False,
        message=f"LLM judge SKIPPED (no verdict after {_RETRIES} attempts; last: {_last_err})",
        data={"skipped": True, "llm_api_failure": True})


# ===========================================================================
# ===========================================================================
def _outline_session_cookie(ctx: dict) -> str | None:
    cached = ctx.get("_outline_access_token")
    if cached:
        return cached
    try:
        import jwt as _jwt
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from utils import db_query
    except Exception as e:
        print(f"[P18] cannot mint session cookie (missing deps): {e}")
        return None
    try:
        sk = subprocess.run(
            ["docker", "exec", config.APP_CONTAINER, "printenv", "SECRET_KEY"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception as e:
        print(f"[P18] cannot read SECRET_KEY from {config.APP_CONTAINER}: {e}")
        return None
    if not sk:
        print("[P18] SECRET_KEY empty")
        return None
    res = db_query(
        'SELECT id, encode("jwtSecret", \'hex\') FROM users '
        'WHERE "jwtSecret" IS NOT NULL AND "suspendedById" IS NULL '
        "ORDER BY (role='admin') DESC, \"createdAt\" ASC LIMIT 1;"
    )
    if not res.get("ok") or not res.get("rows"):
        print(f"[P18] no user with jwtSecret: {res.get('error')}")
        return None
    user_id = res["rows"][0][0]
    blob_hex = res["rows"][0][1] if len(res["rows"][0]) > 1 else ""
    if not user_id or not blob_hex:
        print("[P18] empty user_id / jwtSecret blob")
        return None
    try:
        raw = bytes.fromhex(blob_hex)
        key = bytes.fromhex(sk)
        iv, ct = raw[:16], raw[16:]
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = dec.update(ct) + dec.finalize()
        plain = padded[: -padded[-1]].decode("utf-8")
        jwt_secret = json.loads(plain)
    except Exception as e:
        print(f"[P18] jwtSecret decrypt failed: {e}")
        return None
    try:
        token = _jwt.encode({"id": user_id, "type": "session"}, jwt_secret, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode()
    except Exception as e:
        print(f"[P18] jwt sign failed: {e}")
        return None
    ctx["_outline_access_token"] = token
    return token


# ===========================================================================
# ===========================================================================
def P18(inputs: dict, ctx: dict) -> PrimitiveResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return PrimitiveResult("P18", False, message="playwright not installed", data={"stub": True})
    url = _substitute(inputs.get("url", "/"), ctx)
    actions = inputs.get("actions", [])
    raw_cookie = _substitute(inputs.get("auth_cookie", ""), ctx)
    token = None
    if isinstance(raw_cookie, str) and raw_cookie and "{{" not in raw_cookie:
        token = raw_cookie
    if not token and "auth_cookie" in inputs:
        token = _outline_session_cookie(ctx)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                viewport={"width": 1280, "height": 900}, ignore_https_errors=True
            )
            if token:
                context.add_cookies(
                    [{"name": "accessToken", "value": token, "url": "http://localhost:8031"}]
                )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            for a in actions:
                if "wait_for_selector" in a:
                    page.wait_for_selector(a["wait_for_selector"], timeout=a.get("timeout_ms", 5000))
                elif "click" in a:
                    page.click(a["click"])
                elif "fill" in a:
                    page.fill(a["fill"]["selector"], a["fill"]["value"])
            html = page.content()
            browser.close()
        ctx["last_dom"] = html
        return PrimitiveResult(
            "P18", True,
            message=f"browser ok url={url} auth={'yes' if token else 'no'}",
            data={"html_preview": html[:200]},
        )
    except Exception as e:
        return PrimitiveResult("P18", False, message=f"browser error: {e}", data={})


# ===========================================================================
# ===========================================================================
def P19(inputs: dict, ctx: dict) -> PrimitiveResult:
    selector = inputs.get("selector", "")
    assertion = inputs.get("assertion", "visible")
    html = ctx.get("last_dom", "")
    if not html:
        return PrimitiveResult("P19", False, message="no DOM in ctx (P18 not run)", data={})
    sel_simple = selector.lstrip(".").lstrip("#").split("[")[0]
    found = sel_simple in html
    return PrimitiveResult("P19", found, message=f"selector={selector} found={found}", data={})


# ===========================================================================
# ===========================================================================
def P21(inputs: dict, ctx: dict) -> PrimitiveResult:
    try:
        from websocket import create_connection
    except ImportError:
        return PrimitiveResult("P21", False, message="websocket-client not installed", data={"stub": True})
    url = _substitute(inputs.get("url", ""), ctx)
    timeout = inputs.get("timeout_ms", 5000) / 1000.0
    try:
        ws = create_connection(url, timeout=timeout)
        msg = None
        try:
            msg = ws.recv()
        except Exception:
            pass
        ws.close()
        passed = bool(msg)
        return PrimitiveResult("P21", passed,
                                message=f"ws url={url} first_msg={str(msg)[:80] if msg else '(none)'}",
                                data={"first_message": str(msg)[:200] if msg else None,
                                      "received_first_message": bool(msg)})
    except Exception as e:
        return PrimitiveResult("P21", False, message=f"ws error: {e}", data={"url": url})


# ===========================================================================
# ===========================================================================
def P24(inputs: dict, ctx: dict) -> PrimitiveResult:
    trigger = inputs.get("trigger", {})
    verify = inputs.get("verify", {})
    if trigger.get("type") == "http":
        body = _substitute(trigger.get("body", {}), ctx)
        headers = {"Authorization": f"Bearer {ctx.get('auth_token', '')}"} if ctx.get("auth_token") else {}
        http_request(trigger.get("method", "POST"), trigger["path"], headers=headers, body=body)
    strategy = verify.get("strategy", "db_query")
    expected = verify.get("expected_result", {})
    max_wait_ms = verify.get("max_wait_ms", 10000)
    interval = 500
    deadline = time.time() + max_wait_ms / 1000.0
    last_rows = None
    while time.time() < deadline:
        if strategy == "db_query":
            sql = _substitute(verify["sql"], ctx)
            res = db_query(sql)
            last_rows = res.get("rows")
            if res["ok"] and last_rows:
                row = last_rows[0]
                ok = True
                for col_idx, (k, v) in enumerate(expected.items()):
                    if col_idx >= len(row):
                        ok = False
                        break
                    if k.endswith("_min"):
                        try:
                            if int(row[col_idx]) < int(v):
                                ok = False
                                break
                        except Exception:
                            ok = False
                            break
                    else:
                        if isinstance(v, bool):
                            row_v = row[col_idx] in ("t", "true", "True")
                        elif isinstance(v, int):
                            try:
                                row_v = int(row[col_idx])
                            except Exception:
                                row_v = row[col_idx]
                        else:
                            row_v = row[col_idx]
                        if row_v != v:
                            ok = False
                            break
                if ok:
                    return PrimitiveResult("P24", True, message=f"verified after {(deadline - time.time()) * 1000:.0f}ms",
                                            data={"row": row, "expected": expected})
        time.sleep(interval / 1000.0)
        interval = min(interval * 1.5, 2000)
    return PrimitiveResult("P24", False, message=f"timeout after {max_wait_ms}ms; last={last_rows}",
                            data={"last": last_rows, "expected": expected})


# ===========================================================================
# ===========================================================================
def P25(inputs: dict, ctx: dict) -> PrimitiveResult:
    import base64 as _b64
    import hashlib as _hl
    from urllib.parse import urlparse, parse_qs

    base = config.APP_BASE_URL
    to = config.DEFAULT_HTTP_TIMEOUT
    redirect_uri = _substitute(inputs.get("redirect_uri", "http://localhost/cb"), ctx)
    scope = _substitute(inputs.get("scope", "read"), ctx)
    authorize_path = inputs.get("authorize_url", "/oauth/authorize")
    token_path = inputs.get("token_url", "/oauth/token")
    verify = inputs.get("verify_userinfo", {}) or {}
    verify_url = verify.get("url", "/api/auth.info")
    expected_fields = verify.get("expected_fields", ["data"])

    session_jwt = _outline_session_cookie(ctx)
    if not session_jwt:
        return PrimitiveResult("P25", False, message="could not mint admin session cookie")

    sess = requests.Session()
    sess.cookies.set("accessToken", session_jwt)

    try:
        sess.get(base + "/", timeout=to, allow_redirects=True)
    except Exception as e:
        return PrimitiveResult("P25", False, message=f"csrf bootstrap GET failed: {e}")
    csrf = sess.cookies.get("csrfToken")
    if not csrf:
        return PrimitiveResult("P25", False, message="csrfToken cookie not issued by GET /")
    sess.cookies.clear()
    sess.cookies.set("accessToken", session_jwt)
    sess.cookies.set("csrfToken", csrf)

    try:
        r_client = sess.post(
            base + "/api/oauthClients.create",
            headers={"x-csrf-token": csrf, "Content-Type": "application/json"},
            data=json.dumps({"name": "Eval OAuth PKCE Client",
                             "redirectUris": [redirect_uri]}),
            timeout=to,
        )
    except Exception as e:
        return PrimitiveResult("P25", False, message=f"oauthClients.create failed: {e}")
    if r_client.status_code not in (200, 201):
        return PrimitiveResult("P25", False,
                               message=f"oauthClients.create -> {r_client.status_code}: {r_client.text[:200]}")
    try:
        cdata = (r_client.json() or {}).get("data", {}) or {}
    except Exception:
        cdata = {}
    client_id = cdata.get("clientId")
    client_secret = cdata.get("clientSecret")
    if not client_id:
        return PrimitiveResult("P25", False,
                               message=f"no clientId in create response: {r_client.text[:200]}")

    verifier = _b64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = _b64.urlsafe_b64encode(
        _hl.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = _b64.urlsafe_b64encode(os.urandom(12)).rstrip(b"=").decode()

    try:
        r_auth = sess.post(
            base + authorize_path,
            headers={"x-csrf-token": csrf},
            data={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            allow_redirects=False,
            timeout=to,
        )
    except Exception as e:
        return PrimitiveResult("P25", False, message=f"authorize request failed: {e}")

    code = None
    if r_auth.status_code in (301, 302, 303, 307, 308):
        loc = r_auth.headers.get("Location", "")
        code = (parse_qs(urlparse(loc).query).get("code") or [None])[0]
    elif r_auth.status_code == 200:
        try:
            code = (r_auth.json() or {}).get("code")
        except Exception:
            code = None
    if not code:
        return PrimitiveResult(
            "P25", False,
            message=(f"authorize yielded no code (status={r_auth.status_code}, "
                     f"loc={r_auth.headers.get('Location', '')[:120]}, "
                     f"body={r_auth.text[:120]})"))

    token_body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    if client_secret:
        token_body["client_secret"] = client_secret
    try:
        r_tok = requests.post(base + token_path, data=token_body, timeout=to)
    except Exception as e:
        return PrimitiveResult("P25", False, message=f"token request failed: {e}")
    if r_tok.status_code != 200:
        return PrimitiveResult("P25", False,
                               message=f"token endpoint -> {r_tok.status_code}: {r_tok.text[:200]}")
    try:
        tok_json = r_tok.json() or {}
    except Exception:
        tok_json = {}
    access_token = tok_json.get("access_token")
    if not access_token:
        return PrimitiveResult("P25", False, message=f"no access_token: {r_tok.text[:200]}")

    try:
        r_info = requests.post(base + verify_url,
                               headers={"Authorization": f"Bearer {access_token}"},
                               data=json.dumps({}),
                               timeout=to)
    except Exception as e:
        return PrimitiveResult("P25", False, message=f"userinfo request failed: {e}")
    if r_info.status_code != 200:
        return PrimitiveResult("P25", False,
                               message=f"userinfo -> {r_info.status_code}: {r_info.text[:200]}")
    try:
        info_json = r_info.json() or {}
    except Exception:
        info_json = {}
    missing = [f for f in expected_fields if f not in info_json]
    if missing:
        return PrimitiveResult("P25", False,
                               message=f"userinfo missing {missing}: {r_info.text[:200]}")

    return PrimitiveResult(
        "P25", True,
        message=(f"OAuth2 authorization_code+PKCE OK "
                 f"(client={client_id}, scope={tok_json.get('scope')})"),
        data={"client_id": client_id,
              "has_refresh_token": bool(tok_json.get("refresh_token")),
              "scope": tok_json.get("scope"),
              "token_type": tok_json.get("token_type")})


# ===========================================================================
# ===========================================================================
def P26(inputs: dict, ctx: dict) -> PrimitiveResult:
    path = inputs.get("path", "/api/documents.search")
    method = inputs.get("method", "POST")
    params = _substitute(inputs.get("params", {}), ctx)
    expected = inputs.get("expected_results", {})
    wait = inputs.get("wait_ms", 0)
    if wait:
        time.sleep(wait / 1000.0)
    headers = {"Authorization": f"Bearer {ctx.get('auth_token', '')}"} if ctx.get("auth_token") else {}
    body = params if method == "POST" else None
    resp = http_request(method, path, headers=headers, body=body)
    items = jsonpath_get(resp.get("body"), "$.data") or []
    n = len(items) if isinstance(items, list) else 0
    if expected.get("min_count", 0) > n:
        return PrimitiveResult("P26", False, message=f"only {n} results, expected ≥{expected['min_count']}",
                                data={"results": items[:5], "count": n})
    if expected.get("first_result_contains"):
        first = items[0] if items else {}
        title = (first.get("title") or first.get("name") or "") if isinstance(first, dict) else str(first)
        if expected["first_result_contains"] not in title:
            return PrimitiveResult("P26", False, message=f"first result {title!r} doesn't contain {expected['first_result_contains']!r}",
                                    data={"first": first})
    return PrimitiveResult("P26", True, message=f"search ok n={n}",
                            data={"count": n, "first": items[0] if items else None})


# ===========================================================================
# ===========================================================================
class _WebhookReceiver:
    def __init__(self, port: int):
        self.port = port
        self.received: list[dict] = []
        self._server = None
        self._thread = None

    def start(self):
        received = self.received

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8", errors="ignore") if length else ""
                received.append({"path": self.path, "headers": dict(self.headers), "body": body})
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_):
                pass

        self._server = socketserver.ThreadingTCPServer(("0.0.0.0", self.port), H)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()


def P27(inputs: dict, ctx: dict) -> PrimitiveResult:
    register = inputs.get("register", {})
    trigger = inputs.get("trigger", {})
    expect = inputs.get("expect_delivery", {})
    port = config.WEBHOOK_RECEIVER_PORT
    receiver = _WebhookReceiver(port)
    try:
        receiver.start()
    except OSError:
        return PrimitiveResult("P27", False, message=f"port {port} in use", data={})
    try:
        ctx_copy = dict(ctx)
        ctx_copy["webhook_port"] = port
        body = _substitute(register.get("body", {}), ctx_copy)
        headers = {"Authorization": f"Bearer {ctx.get('auth_token', '')}"}
        http_request("POST", register["path"], headers=headers, body=body)
        body2 = _substitute(trigger.get("body", {}), ctx)
        http_request(trigger.get("method", "POST"), trigger["path"], headers=headers, body=body2)
        deadline = time.time() + expect.get("timeout_ms", 10000) / 1000.0
        while time.time() < deadline:
            if receiver.received:
                got = receiver.received[0]
                ok_body = True
                if expect.get("body_contains"):
                    want = expect["body_contains"]
                    for k, v in want.items():
                        if v not in got["body"]:
                            ok_body = False
                            break
                ok_hdr = True
                if expect.get("headers_contain"):
                    for k, vpat in expect["headers_contain"].items():
                        if not re.search(vpat, got["headers"].get(k, "")):
                            ok_hdr = False
                            break
                return PrimitiveResult("P27", ok_body and ok_hdr,
                                        message=f"delivered (body_ok={ok_body} hdr_ok={ok_hdr})",
                                        data={"received": got})
            time.sleep(0.5)
        return PrimitiveResult("P27", False, message=f"no delivery in {expect.get('timeout_ms')}ms",
                                data={"received_count": len(receiver.received)})
    finally:
        receiver.stop()


# ===========================================================================
# ===========================================================================
PRIMITIVE_FUNCS = {
    "P01": P01, "P02": P02, "P03": P03, "P04": P04, "P05": P05, "P06": P06,
    "P07": P07, "P08": P08, "P09": P09, "P10": P10, "P11": P11, "P12": P12,
    "P13": P13, "P14": P14, "P15": P15, "P16": P16, "P17": P17, "P18": P18,
    "P19": P19, "P21": P21, "P24": P24, "P25": P25, "P26": P26, "P27": P27,
}


def run_primitive(t: str, inputs: dict, ctx: dict) -> PrimitiveResult:
    fn = PRIMITIVE_FUNCS.get(t)
    if fn is None:
        return PrimitiveResult(t, False, message=f"primitive {t} not implemented", data={"stub": True})
    try:
        return fn(inputs, ctx)
    except Exception as e:
        return PrimitiveResult(t, False, message=f"exception: {type(e).__name__}: {e}", data={})
