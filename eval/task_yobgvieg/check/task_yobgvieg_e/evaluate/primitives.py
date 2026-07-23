import os
import re
import glob
import json
import time
import subprocess
import psycopg2
import psycopg2.extras
from utils import (
    PrimitiveResult, context, resolve_dict, get_url, get_headers, get_session,
    http_get, http_post, http_patch, http_delete, docker_exec as _docker_exec
)
from config import (
    WORKSPACE_DIR, APP_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    APP_CONTAINER, TEST_USERS, LLM_API_KEY, LLM_API_BASE, LLM_MODEL, HTTP_TIMEOUT
)


class LLMJudgeUnavailable(BaseException):
    pass

LOGIN_ENDPOINT = os.environ.get("LOGIN_ENDPOINT", "/auth/sign-in/")
CSRF_ENDPOINT = os.environ.get("CSRF_ENDPOINT", "/auth/get-csrf-token/")
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "session-id")
SESSION_COOKIE_FALLBACKS = (SESSION_COOKIE_NAME, "session-id", "sessionid", "session_id", "session", "_session", "app_session")


def _get_db_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def P01_file_exists(inputs):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    ftype = inputs.get("type", "file")
    if ftype == "file":
        exists = os.path.isfile(path)
    else:
        exists = os.path.isdir(path)
    return PrimitiveResult(passed=exists, data={"exists": exists}, message=f"{'Found' if exists else 'Not found'}: {inputs['path']}")


def P02_file_content_match(inputs):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    if not os.path.isfile(path):
        return PrimitiveResult(passed=False, message=f"File not found: {inputs['path']}")
    with open(path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    pattern = inputs["pattern"]
    match_type = inputs.get("match_type", "contains")
    if match_type == "contains":
        matched = pattern in content
        count = content.count(pattern)
    else:
        matches = re.findall(pattern, content)
        matched = len(matches) > 0
        count = len(matches)
    return PrimitiveResult(passed=matched, data={"matched": matched, "match_count": count}, message=f"{'Matched' if matched else 'No match'}: {pattern}")


def P03_file_count(inputs):
    base = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", ""))
    pattern = inputs["glob"]
    files = glob.glob(os.path.join(base, pattern), recursive=True)
    min_expected = inputs.get("min_expected", 1)
    passed = len(files) >= min_expected
    return PrimitiveResult(passed=passed, data={"count": len(files)}, message=f"Found {len(files)} files (min: {min_expected})")


def P04_http_request(inputs):
    method = inputs.get("method", "GET").upper()
    path = resolve_dict(inputs["path"])
    body = resolve_dict(inputs.get("body"))
    timeout = inputs.get("timeout", HTTP_TIMEOUT)
    headers = inputs.get("headers")
    if headers is not None:
        headers = resolve_dict(headers)
    else:
        headers = get_headers(path)

    url = get_url(path)
    s = get_session()
    if method in ("POST", "PUT", "PATCH", "DELETE") and "X-CSRFToken" not in headers:
        csrf = s.cookies.get("csrftoken", "")
        if csrf:
            headers["X-CSRFToken"] = csrf
    try:
        if method == "GET":
            resp = s.get(url, headers=headers, timeout=timeout)
        elif method == "POST":
            resp = s.post(url, json=body, headers=headers, timeout=timeout)
        elif method == "PUT":
            resp = s.put(url, json=body, headers=headers, timeout=timeout)
        elif method == "PATCH":
            resp = s.patch(url, json=body, headers=headers, timeout=timeout)
        elif method == "DELETE":
            resp = s.delete(url, headers=headers, timeout=timeout)
        else:
            return PrimitiveResult(passed=False, message=f"Unknown method: {method}")
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"HTTP error: {e}")

    try:
        data = resp.json()
    except Exception:
        data = resp.text

    context["last_response"] = resp
    context["last_response_data"] = data
    context["last_status_code"] = resp.status_code

    return PrimitiveResult(passed=True, data=data, response=resp, message=f"{method} {path} → {resp.status_code}")


def P05_api_crud(inputs):
    resource = resolve_dict(inputs["resource"])
    create_body = resolve_dict(inputs.get("create_body", {}))
    url = get_url(resource)
    s = get_session()
    h = get_headers()
    results = []
    try:
        r = s.post(url, json=create_body, headers=h, timeout=HTTP_TIMEOUT)
        results.append(("CREATE", r.status_code in (200, 201)))
        eid = r.json().get("id") if r.status_code in (200, 201) else None
        if eid:
            r2 = s.get(f"{url}{eid}/", headers=h, timeout=HTTP_TIMEOUT)
            results.append(("READ", r2.status_code == 200))
            r3 = s.patch(f"{url}{eid}/", json={"name": "Updated"}, headers=h, timeout=HTTP_TIMEOUT)
            results.append(("UPDATE", r3.status_code in (200, 204)))
            r4 = s.delete(f"{url}{eid}/", headers=h, timeout=HTTP_TIMEOUT)
            results.append(("DELETE", r4.status_code in (200, 204)))
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))
    passed_count = sum(1 for _, p in results if p)
    return PrimitiveResult(passed=passed_count == len(results), data={"results": results, "pass_ratio": passed_count / max(len(results), 1)})


def P07_json_value_assert(inputs):
    data = context.get("last_response_data")
    resp = context.get("last_response")
    assertions = inputs.get("assertions", [])
    results = []
    or_groups = []
    cur_or = []
    flat = []
    for a in assertions:
        if "or_path" in a:
            cur_or.append(a)
        else:
            if cur_or:
                or_groups.append(cur_or); cur_or = []
            flat.append(a)
    if cur_or:
        or_groups.append(cur_or)

    def _eval_one(a, p_path):
        operator = a.get("operator", "eq")
        expected = a.get("expected")
        try:
            actual = _json_path(data, p_path, resp)
        except Exception:
            return {"path": p_path, "passed": False, "actual": None, "expected": expected, "message": "Path not found"}
        if operator == "exists":
            passed = actual is not None
        elif operator == "not_null":
            passed = actual is not None
        elif operator == "eq":
            passed = actual == expected
        elif operator == "gt":
            passed = actual is not None and actual > expected
        elif operator == "gte":
            passed = actual is not None and actual >= expected
        elif operator == "lt":
            passed = actual is not None and actual < expected
        elif operator == "lte":
            passed = actual is not None and actual <= expected
        elif operator == "contains":
            passed = isinstance(actual, str) and expected in actual
        elif operator == "starts_with":
            passed = isinstance(actual, str) and actual.startswith(expected)
        elif operator == "length_gte":
            passed = hasattr(actual, "__len__") and len(actual) >= expected
        elif operator == "is_json":
            passed = isinstance(data, (dict, list))
        elif operator == "is_boolean":
            passed = isinstance(actual, bool)
        elif operator == "contains_html":
            text = resp.text if resp else str(data)
            passed = expected in text
        else:
            passed = actual == expected
        tolerance = a.get("tolerance")
        if tolerance and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            passed = abs(actual - expected) <= tolerance
        return {"path": p_path, "passed": passed, "actual": actual, "expected": expected}

    for grp in or_groups:
        sub = [_eval_one(a, a["or_path"]) for a in grp]
        any_pass = any(r["passed"] for r in sub)
        for s in sub:
            s["passed"] = any_pass
            results.append(s)

    for a in flat:
        path = a["path"]
        operator = a.get("operator", "eq")
        expected = a.get("expected")
        try:
            actual = _json_path(data, path, resp)
        except Exception:
            results.append({"path": path, "passed": False, "message": "Path not found"})
            continue
        if operator == "exists":
            passed = actual is not None
        elif operator == "not_null":
            passed = actual is not None
        elif operator == "eq" or operator not in ("gt", "gte", "lt", "lte", "contains", "starts_with", "length_gte", "is_json", "is_boolean", "contains_html"):
            passed = actual == expected
        elif operator == "gt":
            passed = actual is not None and actual > expected
        elif operator == "gte":
            passed = actual is not None and actual >= expected
        elif operator == "lt":
            passed = actual is not None and actual < expected
        elif operator == "lte":
            passed = actual is not None and actual <= expected
        elif operator == "contains":
            passed = isinstance(actual, str) and expected in actual
        elif operator == "starts_with":
            passed = isinstance(actual, str) and actual.startswith(expected)
        elif operator == "length_gte":
            passed = hasattr(actual, "__len__") and len(actual) >= expected
        elif operator == "is_json":
            passed = isinstance(data, (dict, list))
        elif operator == "is_boolean":
            passed = isinstance(actual, bool)
        elif operator == "contains_html":
            text = resp.text if resp else str(data)
            passed = expected in text
        else:
            passed = actual == expected
        tolerance = a.get("tolerance")
        if tolerance and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            passed = abs(actual - expected) <= tolerance
        results.append({"path": path, "passed": passed, "actual": actual, "expected": expected})

        capture_key = a.get("capture_as")
        if capture_key and actual is not None:
            context[capture_key] = actual

    all_passed = all(r["passed"] for r in results)
    failed = [r for r in results if not r["passed"]]
    msg = f"{sum(1 for r in results if r['passed'])}/{len(results)} assertions passed"
    if failed:
        msg += f" | Failed: {failed[0]['path']}"
    return PrimitiveResult(passed=all_passed, data={"assertions": results, "pass_ratio": sum(1 for r in results if r["passed"]) / max(len(results), 1)}, message=msg)


def _json_path(data, path, resp=None):
    if path == "$":
        return data
    if path.startswith("$."):
        keys = path[2:].split(".")
        current = data
        for k in keys:
            if isinstance(current, dict):
                current = current.get(k)
            elif isinstance(current, list) and k.isdigit():
                current = current[int(k)]
            else:
                return None
        return current
    if path in ("$",):
        return data
    return data.get(path) if isinstance(data, dict) else None


def P08_db_query(inputs):
    sql = resolve_dict(inputs["sql"])
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")

    row = dict(rows[0]) if rows else {}
    expected = inputs.get("expected_result")
    assertions = inputs.get("assertions", [])

    if expected:
        passed = all(row.get(k) == v for k, v in expected.items())
        return PrimitiveResult(passed=passed, data=row, message=f"DB result: {row}")

    if assertions:
        results = []
        for a in assertions:
            path = a["path"]
            operator = a.get("operator", "eq")
            exp = a.get("expected")
            actual = row.get(path) if isinstance(row, dict) else None
            if path == "$" and operator == "length_gte":
                actual = len(rows)
                passed = actual >= exp
            elif path == "$" and operator == "exists":
                actual = len(rows)
                passed = actual > 0
            elif operator == "eq":
                passed = actual == exp
            elif operator == "gte":
                passed = actual is not None and actual >= exp
            elif operator == "not_null":
                passed = actual is not None
            elif operator == "starts_with":
                passed = isinstance(actual, str) and actual.startswith(exp)
            elif operator == "exists":
                passed = actual is not None
            else:
                passed = actual == exp
            results.append({"path": path, "passed": passed, "actual": actual})
        all_passed = all(r["passed"] for r in results)
        return PrimitiveResult(passed=all_passed, data={"rows": [dict(r) for r in rows[:5]], "assertions": results}, message=f"DB assertions: {sum(1 for r in results if r['passed'])}/{len(results)}")

    return PrimitiveResult(passed=len(rows) > 0, data={"rows": [dict(r) for r in rows[:5]], "count": len(rows)})


def P09_db_table_exists(inputs):
    tables = inputs["tables"]
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        results = []
        for t in tables:
            cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)", (t,))
            exists = cur.fetchone()["exists"]
            results.append({"table": t, "exists": exists})
        cur.close()
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")
    all_passed = all(r["exists"] for r in results)
    return PrimitiveResult(passed=all_passed, data={"tables": results}, message=f"Tables: {sum(1 for r in results if r['exists'])}/{len(results)}")


def P10_db_column_check(inputs):
    table = inputs["table"]
    expected = inputs["expected_columns"]
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (table,))
        actual_cols = {r["column_name"] for r in cur.fetchall()}
        cur.close()
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")
    found = [c for c in expected if c in actual_cols]
    missing = [c for c in expected if c not in actual_cols]
    passed = len(missing) == 0
    return PrimitiveResult(passed=passed, data={"found": found, "missing": missing, "pass_ratio": len(found) / max(len(expected), 1)}, message=f"Columns: {len(found)}/{len(expected)} found" + (f" | Missing: {missing}" if missing else ""))


def P12_docker_exec(inputs):
    command = resolve_dict(inputs["command"])
    command = command.replace("python manage.py", "python3 manage.py")
    command = command.replace("python -m ", "python3 -m ")

    import shutil
    if shutil.which("docker"):
        rc, stdout, stderr = _docker_exec(APP_CONTAINER, command)
    else:
        try:
            import subprocess
            env = dict(os.environ)
            env.setdefault("DATABASE_URL", f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
            env.setdefault("REDIS_URL", "redis://redis:6379/0")
            env.setdefault("SECRET_KEY", "sk-smoke-test")
            env.setdefault("DJANGO_SETTINGS_MODULE", os.environ.get("DJANGO_SETTINGS_MODULE", "app.settings.local"))
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60, cwd=WORKSPACE_DIR, env=env)
            rc, stdout, stderr = result.returncode, result.stdout, result.stderr
        except Exception as e:
            rc, stdout, stderr = -1, "", str(e)
    passed = rc == 0 or "already exists" in stderr.lower() or "already exists" in stdout.lower()
    return PrimitiveResult(passed=passed, data={"returncode": rc, "stdout": stdout[:500], "stderr": stderr[:500]}, message=f"Exit {rc}: {stdout[:200]}")


def _has_session_cookie(session):
    cookie_names = [c.name for c in session.cookies]
    return any(n in SESSION_COOKIE_FALLBACKS for n in cookie_names)


def P13_auth_login(inputs):
    role = inputs.get("role", "admin")
    method = inputs.get("method", "session")
    user_info = TEST_USERS.get(role, TEST_USERS["admin"])

    s = get_session()
    try:
        csrf_resp = s.get(get_url(CSRF_ENDPOINT), timeout=HTTP_TIMEOUT)
        csrf_token = ""
        if csrf_resp.status_code == 200:
            try:
                csrf_token = csrf_resp.json().get("csrf_token", "")
            except Exception:
                pass
        if not csrf_token:
            csrf_token = s.cookies.get("csrftoken", "")

        login_data = {"email": user_info["email"], "password": user_info["password"], "medium": "email"}

        logged_in = False

        form_headers = {"X-CSRFToken": csrf_token, "Referer": get_url("/")} if csrf_token else {"Referer": get_url("/")}
        resp = s.post(get_url(LOGIN_ENDPOINT), data=login_data, headers=form_headers, timeout=HTTP_TIMEOUT, allow_redirects=False)
        if resp.status_code == 302:
            loc = resp.headers.get("Location", "")
            if "error" not in loc:
                logged_in = True
            elif _has_session_cookie(s):
                logged_in = True
        elif resp.status_code in (200, 204):
            logged_in = True

        if not logged_in:
            json_headers = {"Content-Type": "application/json", "X-CSRFToken": csrf_token}
            resp = s.post(get_url(LOGIN_ENDPOINT), json=login_data, headers=json_headers, timeout=HTTP_TIMEOUT, allow_redirects=False)
            if resp.status_code in (200, 204) and _has_session_cookie(s):
                logged_in = True
            elif resp.status_code == 302 and _has_session_cookie(s):
                logged_in = True
            elif resp.status_code in (200, 204):
                logged_in = True

        if not logged_in and _has_session_cookie(s):
            logged_in = True

        if logged_in:
            context["auth_cookies"] = s.cookies
            context["current_role"] = role
            context["auth_method"] = "session"
            try:
                data = resp.json()
                if isinstance(data, dict) and data.get("access_token"):
                    context["auth_token"] = data["access_token"]
            except Exception:
                pass
            return PrimitiveResult(passed=True, data={"role": role, "cookies": list(s.cookies.keys())}, message=f"Logged in as {role}")
    except Exception as e:
        pass

    return PrimitiveResult(passed=False, message=f"Failed to login as {role}")


def P14_permission_check(inputs):
    action = inputs.get("action", "")
    expected_result = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status", 403)
    body = resolve_dict(inputs.get("body"))

    parts = action.split(" ", 1)
    method = parts[0] if len(parts) > 0 else "GET"
    path = parts[1] if len(parts) > 1 else action
    path = resolve_dict(path)

    s = get_session()
    h = get_headers()
    url = get_url(path)
    try:
        if method == "GET":
            resp = s.get(url, headers=h, timeout=HTTP_TIMEOUT)
        elif method == "POST":
            resp = s.post(url, json=body, headers=h, timeout=HTTP_TIMEOUT)
        elif method == "DELETE":
            resp = s.delete(url, headers=h, timeout=HTTP_TIMEOUT)
        elif method == "PATCH":
            resp = s.patch(url, json=body, headers=h, timeout=HTTP_TIMEOUT)
        else:
            resp = s.get(url, headers=h, timeout=HTTP_TIMEOUT)
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))

    context["last_response"] = resp
    context["last_status_code"] = resp.status_code

    if expected_result == "denied":
        passed = resp.status_code in (expected_status, 403, 404, 401)
    else:
        passed = resp.status_code == expected_status

    return PrimitiveResult(passed=passed, data={"status": resp.status_code, "expected": expected_status}, message=f"Permission check: {resp.status_code} (expected {expected_status})")


def P15_status_code_assert(inputs):
    status = context.get("last_status_code")
    resp = context.get("last_response")
    if resp is not None:
        status = resp.status_code

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
        passed = status in accepted
        return PrimitiveResult(passed=passed, data={"status": status, "expected": sorted(accepted)}, message=f"Status {status} {'in' if passed else 'not in'} {sorted(accepted)}")
    return PrimitiveResult(passed=False, message="No status expectation provided")


_CODE_EXTS = {".py", ".pyx", ".js", ".ts", ".tsx", ".jsx", ".vue", ".html",
              ".go", ".rb", ".java", ".kt", ".rs", ".php", ".sql"}
_MARKUP_EXTS = {".scss", ".css", ".md", ".txt", ".json", ".yaml", ".yml",
                ".toml", ".lock", ".svg", ".cfg", ".ini"}
_SKIP_SUBSTR = ("/node_modules/", "/dist/", "/build/", "/.git/", "/vendor/",
                "/__pycache__/", "/migrations/", "/static/", "/.venv/",
                "/venv/", "/tests/", "/test/", "/locale/")
_RUBRIC_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent does "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling whether well overall".split())


def _gather_and_rank(root, files_to_sample, rubric, max_files=16):
    root = (root or "").rstrip("/")
    entries = list(files_to_sample) or ["apps/", "."]
    cands = []
    explicit = set()
    for ent in entries:
        if not isinstance(ent, str) or not ent or "{{" in ent:
            continue
        base = os.path.join(root, ent.lstrip("/"))
        if os.path.isfile(base):
            cands.append(base)
            explicit.add(base)
            continue
        if not os.path.isdir(base):
            try:
                for p in glob.glob(base, recursive=True):
                    if os.path.isfile(p):
                        cands.append(p)
                        explicit.add(p)
            except Exception:
                pass
            continue
        n = 0
        for dp, dirs, fns in os.walk(base):
            low = "/" + dp.lower() + "/"
            if any(s in low for s in _SKIP_SUBSTR):
                dirs[:] = []
                continue
            for fn in fns:
                if os.path.splitext(fn)[1].lower() in _CODE_EXTS:
                    cands.append(os.path.join(dp, fn))
                    n += 1
            if n > 4000:
                break
    mentioned = {m.split("/")[-1].lower()
                 for m in re.findall(r"[\w./*-]+\.\w{1,5}", rubric or "")}
    pathwords = set()
    for p in re.findall(r"(?:apps|src|lib|core)/[\w./*-]+", rubric or ""):
        for seg in re.split(r"[/.*]", p):
            if len(seg) >= 4:
                pathwords.add(seg.lower())
    kws = {}
    for t in re.findall(r"[A-Za-z_]{3,}", (rubric or "").lower()):
        if t not in _RUBRIC_STOP:
            kws[t] = kws.get(t, 0) + 1
    scored = []
    for full in cands:
        rel = full[len(root):].lstrip("/") if full.startswith(root) else full
        low = rel.lower()
        is_explicit = full in explicit
        if not is_explicit and any(s in "/" + low for s in _SKIP_SUBSTR):
            continue
        base = os.path.basename(low)
        ext = os.path.splitext(low)[1]
        sc = 0.0
        if is_explicit:
            sc += 100
        for m in mentioned:
            if m and (m == base or low.endswith(m)):
                sc += 50
        for w in pathwords:
            if w in low:
                sc += 6
        for w in kws:
            if w in low:
                sc += 3
        sc += 2.0 if ext in _CODE_EXTS else (0.0 if ext in _MARKUP_EXTS else 0.5)
        if "test" in base and not is_explicit:
            sc -= 4.0
        parts = rel.split("/")
        strat = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
        scored.append((sc, strat, rel, full))
    scored.sort(key=lambda x: (-x[0], x[2]))
    groups, order = {}, []
    for sc, strat, rel, full in scored:
        if strat not in groups:
            groups[strat] = []
            order.append(strat)
        groups[strat].append((rel, full))
    picked = []
    while len(picked) < max_files and any(groups[k] for k in order):
        for k in order:
            if groups[k]:
                picked.append(groups[k].pop(0))
                if len(picked) >= max_files:
                    break
    return picked


def P17_llm_judge(inputs):
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
            passed=False,
            data={"skipped": True, "llm_api_failure": False, "score": 0,
                  "reason": "LLM judge skipped: SKIP_LLM_JUDGE is set"},
            message="LLM judge SKIPPED (SKIP_LLM_JUDGE set)")
    rubric = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "code_files")

    if not LLM_API_KEY:
        return PrimitiveResult(
            passed=False,
            data={"skipped": True, "llm_api_failure": True, "score": 0,
                  "reason": "LLM judge skipped: LLM_API_KEY is unset"},
            message="LLM judge SKIPPED (LLM_API_KEY unset)")

    if evidence_type in ("rendered_dom", "screenshot"):
        from _llm_judge_safe import dispatch_external_evidence as _dee
        _RETRIES_EXT = 6
        _last_ext = ""
        for _att in range(_RETRIES_EXT):
            _ext_result = _dee(
                inputs=inputs,
                ctx=context,
                model=LLM_MODEL,
                api_key=LLM_API_KEY,
                api_base=LLM_API_BASE or "",
                return_type='primitive',
                primitive_result_cls=PrimitiveResult,
            )
            if _ext_result is None:
                break
            _sk = getattr(_ext_result, "data", None) or {}
            if isinstance(_sk, dict) and _sk.get("skipped"):
                _last_ext = str(_sk.get("reason") or "skipped")
                time.sleep(min(2.0 * (_att + 1), 8.0))
                continue
            return _ext_result
        else:
            return PrimitiveResult(
                passed=False,
                data={"skipped": True, "llm_api_failure": True, "score": 0,
                      "reason": f"LLM judge (external evidence) unavailable after "
                                f"{_RETRIES_EXT} attempts (last: {_last_ext})"},
                message="LLM judge SKIPPED (external evidence, no verdict)")

    evidence_text = ""
    if evidence_type == "code_files":
        files_to_sample = resolve_dict(inputs.get("files_to_sample", []))
        for rel, fpath in _gather_and_rank(WORKSPACE_DIR, files_to_sample,
                                           rubric, max_files=16):
            if len(evidence_text) > 38000:
                break
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    evidence_text += f"\n--- {rel} ---\n{f.read()[:3000]}\n"
            except Exception:
                pass
    elif evidence_type == "http_response_html":
        resp = context.get("last_response")
        if resp:
            evidence_text = resp.text[:5000]

    from _llm_judge_safe import safe_chat_completion

    _RETRIES = 6
    _last_err = ""
    for _attempt in range(_RETRIES):
        res = safe_chat_completion(
            messages=[
                {"role": "system", "content": f"You are a code quality evaluator. Score from {score_range[0]} to {score_range[1]}. Return JSON: {{\"score\": <number>, \"reason\": \"<explanation>\"}}"},
                {"role": "user", "content": f"Rubric:\n{rubric}\n\nEvidence:\n{evidence_text[:24000]}"},
            ],
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE or "",
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        if res.skipped:
            _last_err = f"api failure: {res.exception_class or ''} {res.error or ''}".strip()
            time.sleep(min(2.0 * (_attempt + 1), 8.0))
            continue

        raw = res.raw or ""
        parsed = None
        parse_err = None
        try:
            parsed = json.loads(raw)
        except Exception as e1:
            parse_err = e1
            m = re.search(r'\{[^{}]*?"score"\s*:\s*-?\d+(?:\.\d+)?[^{}]*?\}', raw, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    parse_err = None
                except Exception as e2:
                    parse_err = e2

        if parsed is not None and isinstance(parsed, dict):
            try:
                raw_score = float(parsed.get("score", 0))
                score = min(max(raw_score, score_range[0]), score_range[1])
                return PrimitiveResult(
                    passed=score > 0,
                    data={"score": score, "reason": parsed.get("reason", "")},
                    message=f"LLM score: {score}/{score_range[1]}",
                )
            except Exception as e3:
                parse_err = e3

        int_match = re.search(r"\b(-?\d+)\b", raw)
        if int_match:
            try:
                raw_score = float(int_match.group(1))
                score = min(max(raw_score, score_range[0]), score_range[1])
                return PrimitiveResult(
                    passed=score > 0,
                    data={
                        "score": score,
                        "reason": f"parse fallback: integer extracted (no JSON in reply)",
                        "parse_fallback": True,
                        "raw": raw[:200],
                    },
                    message=f"LLM score: {score}/{score_range[1]} (parse fallback)",
                )
            except Exception as e4:
                parse_err = e4

        _last_err = f"parse failure: {parse_err}; raw={raw[:120]!r}"
        time.sleep(min(1.5 * (_attempt + 1), 6.0))

    return PrimitiveResult(
        passed=False,
        data={"skipped": True, "llm_api_failure": True, "score": 0,
              "reason": f"LLM judge unavailable after {_RETRIES} attempts (last: {_last_err})"},
        message="LLM judge SKIPPED (no verdict)")


PRIMITIVE_MAP = {
    "P01": P01_file_exists,
    "P02": P02_file_content_match,
    "P03": P03_file_count,
    "P04": P04_http_request,
    "P05": P05_api_crud,
    "P07": P07_json_value_assert,
    "P08": P08_db_query,
    "P09": P09_db_table_exists,
    "P10": P10_db_column_check,
    "P12": P12_docker_exec,
    "P13": P13_auth_login,
    "P14": P14_permission_check,
    "P15": P15_status_code_assert,
    "P17": P17_llm_judge,
}


def execute_primitive(ptype, inputs):
    fn = PRIMITIVE_MAP.get(ptype)
    if fn is None:
        return PrimitiveResult(passed=False, message=f"Unknown primitive: {ptype}")
    inputs = resolve_dict(inputs)
    return fn(inputs)

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
