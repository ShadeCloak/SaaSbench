import os
import re
import glob
import json
import psycopg2
import psycopg2.extras
from utils import (
    PrimitiveResult, context, resolve_dict, get_url, get_headers, get_session,
    http_get, http_post, http_patch, http_delete, docker_exec as _docker_exec
)
from config import (
    WORKSPACE_DIR, APP_BASE_URL, GRAPHQL_URL, METADATA_URL, REST_URL,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    APP_CONTAINER, TEST_USERS, LLM_API_KEY, LLM_API_BASE, LLM_MODEL, HTTP_TIMEOUT
)


def _get_db_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def _json_path(data, path, resp=None):
    if path == "$":
        return data
    if path.startswith("$."):
        keys = path[2:].split(".")
        current = data
        for k in keys:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(k)
            elif isinstance(current, list) and k.isdigit():
                idx = int(k)
                current = current[idx] if idx < len(current) else None
            else:
                return None
        return current
    return data.get(path) if isinstance(data, dict) else None


def P01_file_exists(inputs):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    ftype = inputs.get("type", "file")
    exists = os.path.isfile(path) if ftype == "file" else os.path.isdir(path)
    return PrimitiveResult(passed=exists, data={"exists": exists}, message=f"{'Found' if exists else 'Not found'}: {inputs['path']}")


_P02_ALLOWED_EXTS = (
    '.ts', '.js', '.tsx', '.jsx', '.py',
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    '.json', '.yml', '.yaml', '.toml',
    '.vue', '.svelte', '.astro',
    '.go', '.rs', '.java', '.kt', '.swift', '.rb', '.php',
    '.md', '.mdx',
    '.sql', '.sh', '.dockerfile',
)

_P02_EXCLUDE_DIRS = (
    'node_modules', '.git', 'dist', 'build', '.cache', '.next',
    '.nuxt', 'out', '.output', 'target', '.gradle', 'venv',
    '.venv', '__pycache__', '.pytest_cache',
)


def _p02_resolve_paths(rel_path, return_all: bool = False):
    base = os.path.join(WORKSPACE_DIR, rel_path)
    results: list = []
    if os.path.exists(base):
        if not return_all:
            return base
        results.append(base)
    import glob as _g
    candidates = []
    for pat in (
        os.path.join(WORKSPACE_DIR, "packages", "*", rel_path),
        os.path.join(WORKSPACE_DIR, "apps", "*", rel_path),
        os.path.join(WORKSPACE_DIR, "src", rel_path),
        os.path.join(WORKSPACE_DIR, "server", rel_path),
        os.path.join(WORKSPACE_DIR, "backend", rel_path),
        os.path.join(WORKSPACE_DIR, "frontend", rel_path),
        os.path.join(WORKSPACE_DIR, "client", rel_path),
        os.path.join(WORKSPACE_DIR, "api", rel_path),
        os.path.join(WORKSPACE_DIR, "web", rel_path),
    ):
        candidates.extend(_g.glob(pat))
    for c in candidates:
        if os.path.exists(c) and c not in results:
            if not return_all:
                return c
            results.append(c)
    if return_all:
        return results
    return None


def P02_file_content_match(inputs):
    rel_path = inputs["path"]
    pattern = inputs["pattern"]
    match_type = inputs.get("match_type", "contains")

    candidates: list = []
    base_path = os.path.join(WORKSPACE_DIR, rel_path)
    if os.path.exists(base_path):
        candidates.append(base_path)
    if inputs.get("alt_paths"):
        for alt in inputs["alt_paths"]:
            ap = os.path.join(WORKSPACE_DIR, alt)
            if os.path.exists(ap) and ap not in candidates:
                candidates.append(ap)
    else:
        resolved_all = _p02_resolve_paths(rel_path, return_all=True) or []
        for r in resolved_all:
            if r not in candidates:
                candidates.append(r)

    if not candidates:
        return PrimitiveResult(passed=False, message=f"Path not found: {rel_path}")

    allowed_exts = inputs.get("allowed_exts", _P02_ALLOWED_EXTS)
    if isinstance(allowed_exts, list):
        allowed_exts = tuple(allowed_exts)

    last_message = f"Pattern not found in {rel_path}"
    for cand in candidates:
        if os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue
            if match_type == "contains":
                matched = pattern in content
            else:
                matched = bool(re.search(pattern, content))
            if matched:
                rel_label = os.path.relpath(cand, WORKSPACE_DIR)
                return PrimitiveResult(passed=True, data={"matched": True},
                                       message=f"{'Matched' if matched else 'No match'} in {rel_label}: {pattern[:50]}")
            last_message = f"No match: {pattern[:50]} in {os.path.relpath(cand, WORKSPACE_DIR)}"
            continue
        if os.path.isdir(cand):
            for root, dirs, files in os.walk(cand):
                dirs[:] = [d for d in dirs if d not in _P02_EXCLUDE_DIRS]
                for fn in files:
                    if not fn.lower().endswith(allowed_exts):
                        continue
                    try:
                        with open(os.path.join(root, fn), encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                    except Exception:
                        continue
                    if match_type == "contains":
                        matched = pattern in content
                    else:
                        matched = bool(re.search(pattern, content))
                    if matched:
                        rel_fn = os.path.relpath(os.path.join(root, fn), WORKSPACE_DIR)
                        return PrimitiveResult(passed=True, data={"matched": True},
                                               message=f"Found in {rel_fn}")

    return PrimitiveResult(passed=False, message=last_message)


def P03_file_count(inputs):
    base = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", ""))
    pattern = inputs["glob"]
    files = glob.glob(os.path.join(base, pattern), recursive=True)
    min_expected = inputs.get("min_expected", 1)
    return PrimitiveResult(passed=len(files) >= min_expected, data={"count": len(files)}, message=f"Found {len(files)} files (min: {min_expected})")


def P04_http_request(inputs):
    method = inputs.get("method", "GET").upper()
    path = resolve_dict(inputs["path"])
    body = resolve_dict(inputs.get("body"))
    timeout = inputs.get("timeout", HTTP_TIMEOUT)
    hdrs = inputs.get("headers")
    if hdrs is not None:
        hdrs = resolve_dict(hdrs)
    else:
        hdrs = get_headers()

    url = get_url(path)
    s = get_session()
    try:
        if method == "GET":
            resp = s.get(url, headers=hdrs, timeout=timeout)
        elif method == "POST":
            resp = s.post(url, json=body, headers=hdrs, timeout=timeout)
        elif method == "PATCH":
            resp = s.patch(url, json=body, headers=hdrs, timeout=timeout)
        elif method == "PUT":
            resp = s.put(url, json=body, headers=hdrs, timeout=timeout)
        elif method == "DELETE":
            resp = s.delete(url, headers=hdrs, timeout=timeout)
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
    if isinstance(data, dict) and data.get("access_token"):
        context["oauthToken"] = data["access_token"]
        context["oauthAccessToken"] = data["access_token"]
    return PrimitiveResult(passed=True, data=data, response=resp, message=f"{method} {path} -> {resp.status_code}")


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
        eid = None
        if r.status_code in (200, 201):
            try:
                eid = r.json().get("id")
            except Exception:
                pass
        if eid:
            r2 = s.get(f"{url}/{eid}", headers=h, timeout=HTTP_TIMEOUT)
            results.append(("READ", r2.status_code == 200))
            r3 = s.patch(f"{url}/{eid}", json={"name": "Updated"}, headers=h, timeout=HTTP_TIMEOUT)
            results.append(("UPDATE", r3.status_code in (200, 204)))
            r4 = s.delete(f"{url}/{eid}", headers=h, timeout=HTTP_TIMEOUT)
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
    for a in assertions:
        path = a["path"]
        expected = a.get("expected")
        expected_type = a.get("expected_type")
        expected_in = a.get("expected_in")
        contains = a.get("contains")
        try:
            actual = _json_path(data, path, resp)
        except Exception:
            results.append({"path": path, "passed": False, "message": "Path not found"})
            continue

        if expected == "undefined":
            passed = actual is None
        elif expected_type:
            type_map = {"string": str, "number": (int, float), "boolean": bool, "array": list, "object": dict}
            passed = isinstance(actual, type_map.get(expected_type, object))
        elif expected_in:
            passed = actual in expected_in
        elif contains:
            if isinstance(actual, str):
                passed = contains in actual
            elif isinstance(actual, (list, tuple)):
                passed = contains in actual
            elif isinstance(actual, dict):
                passed = contains in actual
            else:
                passed = False
        elif isinstance(expected, list) and isinstance(actual, list):
            passed = set(expected).issubset(set(actual)) if a.get("contains") else actual == expected
        else:
            tolerance = a.get("tolerance")
            if tolerance and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
                passed = abs(actual - expected) <= tolerance
            else:
                passed = actual == expected
        results.append({"path": path, "passed": passed, "actual": actual, "expected": expected or expected_type or expected_in or contains})

    all_passed = all(r["passed"] for r in results)
    failed = [r for r in results if not r["passed"]]
    msg = f"{sum(1 for r in results if r['passed'])}/{len(results)} assertions"
    if failed:
        msg += f" | FAIL: {failed[0]['path']}={failed[0].get('actual')}"
    return PrimitiveResult(passed=all_passed, data={"assertions": results, "pass_ratio": sum(1 for r in results if r["passed"]) / max(len(results), 1)}, message=msg)


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
    if expected:
        passed_items = []
        for k, v in expected.items():
            if k.endswith("_gte"):
                real_k = k[:-4]
                passed_items.append(row.get(real_k, 0) >= v)
            else:
                passed_items.append(row.get(k) == v)
        passed = all(passed_items)
        return PrimitiveResult(passed=passed, data=row, message=f"DB: {row}")
    return PrimitiveResult(passed=len(rows) > 0, data={"rows": [dict(r) for r in rows[:5]], "count": len(rows)})


def P09_db_table_exists(inputs):
    tables = inputs["tables"]
    allow_schema_fallback = bool(inputs.get("allow_schema_fallback", False))
    min_ratio = float(inputs.get("min_ratio", 0.0))
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        results = []
        for t in tables:
            if "." in t:
                schema, table = t.replace('"', '').split(".", 1)
            else:
                schema, table = "public", t.replace('"', '')
            cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s)", (schema, table))
            exists = cur.fetchone()["exists"]
            if not exists and allow_schema_fallback:
                if schema == "metadata":
                    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='core' AND table_name=%s)", (table,))
                    exists = cur.fetchone()["exists"]
                if not exists:
                    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=%s)", (table,))
                    exists = cur.fetchone()["exists"]
            results.append({"table": t, "exists": exists})
        cur.close()
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")
    found = sum(1 for r in results if r["exists"])
    ratio = found / max(len(results), 1)
    if min_ratio > 0:
        passed = ratio >= min_ratio
    else:
        passed = found > 0
    return PrimitiveResult(passed=passed, data={"tables": results, "pass_ratio": ratio, "min_ratio": min_ratio}, message=f"Tables: {found}/{len(results)} (ratio {ratio:.2f}, min {min_ratio:.2f})")


def P10_db_column_check(inputs):
    table = inputs["table"]
    expected = inputs["expected_columns"]
    allow_schema_fallback = bool(inputs.get("allow_schema_fallback", False))
    min_ratio = float(inputs.get("min_ratio", 0.5))
    if "." in table:
        schema, tbl = table.replace('"', '').split(".", 1)
    else:
        schema, tbl = "public", table.replace('"', '')
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s", (schema, tbl))
        actual_cols = {r["column_name"] for r in cur.fetchall()}
        if not actual_cols and allow_schema_fallback:
            if schema == "metadata":
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='core' AND table_name=%s", (tbl,))
                actual_cols = {r["column_name"] for r in cur.fetchall()}
            if not actual_cols:
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (tbl,))
                actual_cols = {r["column_name"] for r in cur.fetchall()}
        cur.close()
        conn.close()
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")
    clean_expected = [c.replace('"', '') for c in expected]
    found = [c for c in clean_expected if c in actual_cols]
    missing = [c for c in clean_expected if c not in actual_cols]
    ratio = len(found) / max(len(clean_expected), 1)
    passed = ratio >= min_ratio
    return PrimitiveResult(passed=passed, data={"found": found, "missing": missing, "pass_ratio": ratio, "min_ratio": min_ratio}, message=f"Columns: {len(found)}/{len(clean_expected)} (ratio {ratio:.2f}, min {min_ratio:.2f})" + (f" Missing: {missing[:3]}" if missing else ""))


def P12_docker_exec(inputs):
    command = resolve_dict(inputs["command"])
    accept_patterns = inputs.get("acceptable_stderr_patterns", []) or []
    accept_rc = inputs.get("acceptable_returncodes", [0]) or [0]
    rc, stdout, stderr = _docker_exec(APP_CONTAINER, command)
    passed = rc in accept_rc
    if not passed and accept_patterns:
        combined = (stderr + stdout).lower()
        for pat in accept_patterns:
            if str(pat).lower() in combined:
                passed = True
                break
    return PrimitiveResult(passed=passed, data={"returncode": rc, "stdout": stdout[:500], "accepted_patterns": accept_patterns}, message=f"Exit {rc}")


def _try_generate_jwt_directly(email=None, workspace_id=None):
    workspace_id = workspace_id or os.environ.get("EVAL_WORKSPACE_ID", "") or None
    try:
        import hashlib
        import time as _time
        try:
            import jwt as pyjwt
        except ImportError:
            try:
                import jose.jwt as pyjwt
            except ImportError:
                import base64 as _b64, hmac as _hmac
                class _FakeJwt:
                    @staticmethod
                    def encode(payload, secret, algorithm="HS256"):
                        import json as _json
                        def _b64url(data): return _b64.urlsafe_b64encode(data).rstrip(b"=").decode()
                        h = _b64url(_json.dumps({"alg":"HS256","typ":"JWT"}, separators=(',',':')).encode())
                        p = _b64url(_json.dumps(payload, separators=(',',':')).encode())
                        sig = _hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
                        return f"{h}.{p}.{_b64url(sig)}"
                pyjwt = _FakeJwt()

        app_secret = os.environ.get("APP_SECRET", "")
        if not app_secret:
            return None

        conn = _get_db_conn()
        cur = conn.cursor()

        base_sql = '''SELECT u.id as user_id, uw.id as uw_id, uw."workspaceId" as ws_id,
                             w."databaseSchema" as db_schema
                      FROM core."user" u
                      JOIN core."userWorkspace" uw ON uw."userId" = u.id
                      JOIN core.workspace w ON w.id = uw."workspaceId"
                      WHERE u."deletedAt" IS NULL AND w."activationStatus" = 'ACTIVE'{extra}
                      ORDER BY u."createdAt" ASC LIMIT 1'''
        row = None
        if email:
            if workspace_id:
                cur.execute(base_sql.format(extra=' AND u.email = %s AND uw."workspaceId" = %s'),
                            (email, workspace_id))
                row = cur.fetchone()
            if not row:
                cur.execute(base_sql.format(extra=' AND u.email = %s'), (email,))
                row = cur.fetchone()
        if not row:
            if workspace_id:
                cur.execute(base_sql.format(extra=' AND uw."workspaceId" = %s'), (workspace_id,))
                row = cur.fetchone()
            if not row:
                cur.execute(base_sql.format(extra=''))
                row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            return None

        user_id = str(row["user_id"])
        ws_id = str(row["ws_id"])
        uw_id = str(row["uw_id"])
        db_schema = row["db_schema"]

        wm_id = None
        if db_schema:
            try:
                cur.execute(f'SELECT id FROM "{db_schema}"."workspaceMember" WHERE "userId" = %s LIMIT 1', (user_id,))
                wm = cur.fetchone()
                if wm:
                    wm_id = str(wm["id"])
            except Exception:
                pass

        cur.close()
        conn.close()

        now = int(_time.time())
        secret = hashlib.sha256(f"{app_secret}{ws_id}ACCESS".encode()).hexdigest()
        payload = {
            "sub": user_id, "userId": user_id,
            "workspaceId": ws_id, "userWorkspaceId": uw_id,
            "type": "ACCESS", "iat": now, "exp": now + 86400,
        }
        if wm_id:
            payload["workspaceMemberId"] = wm_id

        token = pyjwt.encode(payload, secret, algorithm="HS256")
        return token

    except Exception:
        return None
    return None


def _extract_token_from_response(data):
    if not data or not data.get("data"):
        return None
    for k, v in data["data"].items():
        if not isinstance(v, dict):
            continue
        for token_key in ("accessToken", "accessOrWorkspaceAgnosticToken"):
            tok = v.get("tokens", {}).get(token_key, {}).get("token")
            if tok:
                return tok
        if v.get("loginToken", {}).get("token"):
            return ("loginToken", v["loginToken"]["token"])
    return None


def _token_has_workspace_claim(token: str) -> bool:
    if not token or token.count(".") < 2:
        return False
    try:
        import base64 as _b64
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(_b64.urlsafe_b64decode(payload_b64))
        return bool(
            payload.get("workspaceId")
            or payload.get("workspace_id")
            or payload.get("userWorkspaceId")
        )
    except Exception:
        return False


def _exchange_for_workspace_token(session, hdrs, endpoint_url, agnostic_token):
    if not agnostic_token:
        return agnostic_token
    auth_hdrs = {**hdrs, "Authorization": f"Bearer {agnostic_token}"}
    workspace_id = None
    try:
        for q in (
            "{ currentUser { workspaces { workspace { id } } } }",
            "{ currentUser { workspaces { id } } }",
            "{ currentUser { defaultWorkspace { id } } }",
        ):
            try:
                r = session.post(endpoint_url, json={"query": q}, headers=auth_hdrs, timeout=HTTP_TIMEOUT)
                if r.status_code != 200:
                    continue
                d = r.json()
                if d.get("errors"):
                    continue
                cu = (d.get("data") or {}).get("currentUser") or {}
                if cu.get("defaultWorkspace", {}).get("id"):
                    workspace_id = cu["defaultWorkspace"]["id"]
                    break
                wss = cu.get("workspaces") or []
                if wss:
                    first = wss[0]
                    workspace_id = first.get("workspace", {}).get("id") or first.get("id")
                    if workspace_id:
                        break
            except Exception:
                continue
    except Exception:
        pass
    if not workspace_id:
        return agnostic_token
    for transient_q in (
        "mutation { generateTransientToken { transientToken { token } } }",
        "mutation { generateLoginToken { loginToken { token } } }",
    ):
        try:
            r = session.post(endpoint_url, json={"query": transient_q}, headers=auth_hdrs, timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                continue
            d = r.json()
            tok = ((d.get("data") or {}).get("generateTransientToken") or {}).get("transientToken", {}).get("token") \
                or ((d.get("data") or {}).get("generateLoginToken") or {}).get("loginToken", {}).get("token")
            if not tok:
                continue
            xq = f'mutation {{ getAuthTokensFromLoginToken(loginToken: "{tok}", workspaceId: "{workspace_id}") {{ tokens {{ accessOrWorkspaceAgnosticToken {{ token }} accessToken {{ token }} }} }} }}'
            r2 = session.post(endpoint_url, json={"query": xq}, headers=hdrs, timeout=HTTP_TIMEOUT)
            if r2.status_code != 200:
                continue
            d2 = r2.json()
            t = ((d2.get("data") or {}).get("getAuthTokensFromLoginToken") or {}).get("tokens", {})
            bound = (t.get("accessToken") or {}).get("token") or (t.get("accessOrWorkspaceAgnosticToken") or {}).get("token")
            if bound:
                return bound
        except Exception:
            continue
    return agnostic_token


def P13_auth_login(inputs):
    role = inputs.get("role", "admin")
    forbid_jwt_fallback = bool(inputs.get("forbid_jwt_fallback", False))
    user_info = TEST_USERS.get(role, TEST_USERS["admin"])

    if role == "apikey" and context.get("api_key_token"):
        context["auth_token"] = context["api_key_token"]
        context["current_role"] = "apikey"
        return PrimitiveResult(passed=True, data={"role": "apikey"}, message="Using API Key")

    cached = context.get("token_cache", {}).get(role)
    if cached:
        context["auth_token"] = cached
        context["current_role"] = role
        context["last_response_data"] = {"role": role, "cached": True}
        return PrimitiveResult(passed=True, data={"role": role, "cached": True}, message=f"Cached token for {role}")

    s = get_session()
    hdrs = {"Content-Type": "application/json"}

    auth_attempts = [
        ("signIn", f'mutation {{ signIn(email: "{user_info["email"]}", password: "{user_info["password"]}") {{ tokens {{ accessOrWorkspaceAgnosticToken {{ token }} refreshToken {{ token }} }} }} }}'),
        ("signIn_legacy", f'mutation {{ signIn(email: "{user_info["email"]}", password: "{user_info["password"]}") {{ tokens {{ accessToken {{ token }} refreshToken {{ token }} }} }} }}'),
        ("getLoginTokenFromCredentials", f'mutation {{ getLoginTokenFromCredentials(email: "{user_info["email"]}", password: "{user_info["password"]}", origin: "http://localhost") {{ loginToken {{ token expiresAt }} }} }}'),
        ("signUp", f'mutation {{ signUp(email: "{user_info["email"]}", password: "{user_info["password"]}") {{ tokens {{ accessOrWorkspaceAgnosticToken {{ token }} }} }} }}'),
        ("signUp_legacy", f'mutation {{ signUp(email: "{user_info["email"]}", password: "{user_info["password"]}") {{ loginToken {{ token }} }} }}'),
        ("signUpInWorkspace", f'mutation {{ signUpInWorkspace(email: "{user_info["email"]}", password: "{user_info["password"]}") {{ loginToken {{ token }} }} }}'),
    ]

    endpoints = [get_url("/metadata"), get_url("/graphql")]

    for endpoint_url in endpoints:
        for attempt_name, query in auth_attempts:
            try:
                resp = s.post(endpoint_url, json={"query": query}, headers=hdrs, timeout=HTTP_TIMEOUT)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if data.get("errors"):
                    continue

                result = _extract_token_from_response(data)
                if result is None:
                    continue

                if isinstance(result, tuple) and result[0] == "loginToken":
                    login_token = result[1]
                    for verify_q in [
                        f'mutation {{ verify(loginToken: "{login_token}") {{ tokens {{ accessOrWorkspaceAgnosticToken {{ token }} }} }} }}',
                        f'mutation {{ verify(loginToken: "{login_token}") {{ tokens {{ accessToken {{ token }} refreshToken {{ token }} }} }} }}',
                    ]:
                        resp2 = s.post(endpoint_url, json={"query": verify_q}, headers=hdrs, timeout=HTTP_TIMEOUT)
                        if resp2.status_code == 200:
                            d2 = resp2.json()
                            tok2 = _extract_token_from_response(d2)
                            if tok2 and not isinstance(tok2, tuple):
                                tok2 = _exchange_for_workspace_token(s, hdrs, endpoint_url, tok2)
                                if not _token_has_workspace_claim(tok2):
                                    continue
                                context["auth_token"] = tok2
                                context["current_role"] = role
                                context.setdefault("token_cache", {})[role] = tok2
                                result_data = {"role": role, "method": f"{attempt_name}+verify"}
                                context["last_response_data"] = result_data
                                return PrimitiveResult(passed=True, data=result_data, message=f"Logged in as {role} via {attempt_name}+verify")
                else:
                    result = _exchange_for_workspace_token(s, hdrs, endpoint_url, result)
                    if not _token_has_workspace_claim(result):
                        continue
                    context["auth_token"] = result
                    context["current_role"] = role
                    context.setdefault("token_cache", {})[role] = result
                    result_data = {"role": role, "method": attempt_name}
                    context["last_response_data"] = result_data
                    return PrimitiveResult(passed=True, data=result_data, message=f"Logged in as {role} via {attempt_name}")
            except Exception:
                continue

    if forbid_jwt_fallback:
        return PrimitiveResult(
            passed=False,
            message=f"Failed to login as {role} via candidate API ({len(auth_attempts)} methods x {len(endpoints)} endpoints); JWT fallback forbidden by node config"
        )

    jwt_token = _try_generate_jwt_directly(email=user_info.get("email"))
    if jwt_token:
        context["auth_token"] = jwt_token
        context["current_role"] = role
        context.setdefault("token_cache", {})[role] = jwt_token
        result_data = {"role": role, "method": "fallback_jwt"}
        context["last_response_data"] = result_data
        return PrimitiveResult(passed=True, data=result_data, message=f"Logged in as {role} via DB-derived JWT fallback (candidate API failed)")

    return PrimitiveResult(passed=False, message=f"Failed to login as {role} (tried {len(auth_attempts)} methods x {len(endpoints)} endpoints + DB-derived JWT fallback)")


def P14_permission_check(inputs):
    action = inputs.get("action", "")
    expected_result = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status", 403)
    parts = action.split(" ", 1)
    method = parts[0] if len(parts) > 0 else "GET"
    path = resolve_dict(parts[1] if len(parts) > 1 else action)
    s = get_session()
    h = get_headers()
    url = get_url(path)
    try:
        resp = {"GET": s.get, "POST": s.post, "DELETE": s.delete, "PATCH": s.patch}.get(method, s.get)(url, headers=h, timeout=HTTP_TIMEOUT)
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))
    context["last_response"] = resp
    context["last_status_code"] = resp.status_code

    if expected_result == "denied":
        accepted = inputs.get("acceptable_denied_statuses")
        if accepted is None:
            accepted = [int(expected_status), 401, 403]
        accepted = {int(x) for x in accepted}
        passed = resp.status_code in accepted
        if not passed and resp.status_code in (404, 405, 501):
            return PrimitiveResult(
                passed=False,
                data={"status": resp.status_code, "evaluator_gap": True},
                message=f"Permission check returned {resp.status_code} (route may not exist; not a denial); set acceptable_denied_statuses to opt in"
            )
    else:
        passed = resp.status_code == int(expected_status)
    return PrimitiveResult(passed=passed, data={"status": resp.status_code}, message=f"Permission: {resp.status_code} (expected {expected_status})")


def P15_status_code_assert(inputs):
    resp = context.get("last_response")
    status = resp.status_code if resp else context.get("last_status_code")
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

    if status is None:
        return PrimitiveResult(passed=False, message="No status to assert against")

    if accepted:
        passed = status in accepted
    else:
        passed = 200 <= status < 300

    accepted_disp = sorted(accepted) if accepted else "2xx"
    return PrimitiveResult(
        passed=passed,
        data={"status": status, "expected": accepted_disp},
        message=f"Status {status} {'in' if passed else 'not in'} {accepted_disp}",
    )


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
        _sr = inputs.get("score_range", [0, 5]) if isinstance(inputs, dict) else [0, 5]
        return PrimitiveResult(
            passed=True,
            data={
                "score": 0,
                "max_score": _sr[1],
                "skipped": True,
                "llm_api_failure": False,
                "reason": "SKIP_LLM_JUDGE flag set; LLM judge node intentionally skipped",
            },
            message="LLM judge SKIPPED (SKIP_LLM_JUDGE flag set)",
        )
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
    rubric = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "code_files")
    if not LLM_API_KEY:
        return PrimitiveResult(
            passed=True,
            data={
                "score": 0,
                "skipped": True,
                "llm_api_failure": False,
                "exception_class": "",
                "reason": "LLM_API_KEY unset",
            },
            message="LLM judge SKIPPED (LLM_API_KEY unset)",
        )
    evidence_text = ""
    if evidence_type == "code_files":
        import glob as _glob
        import fnmatch as _fnmatch
        _ALLOWED_EXTS = (
            ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
            ".py", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs",
            ".html", ".css", ".scss", ".sass", ".vue", ".svelte",
            ".json", ".yaml", ".yml", ".graphql", ".gql", ".sql", ".md",
        )
        _SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage",
                      "__pycache__", ".turbo", ".cache", "out", ".nx"}
        _MAX_TOTAL = 12000
        _PER_FILE = 1800
        _MAX_FILES_PER_ENTRY = 12
        _scanned: set = set()

        def _emit_file(abs_path: str, label: str | None = None):
            nonlocal evidence_text
            if abs_path in _scanned:
                return
            if len(evidence_text) >= _MAX_TOTAL:
                return
            try:
                with open(abs_path, encoding="utf-8", errors="ignore") as fh:
                    body = fh.read()
            except Exception:
                return
            _scanned.add(abs_path)
            if label is None:
                label = os.path.relpath(abs_path, WORKSPACE_DIR)
            evidence_text += f"\n--- {label} ---\n{body[:_PER_FILE]}\n"

        def _walk_dir(dir_abs: str, max_files: int = _MAX_FILES_PER_ENTRY,
                      keyword: str | None = None):
            collected = 0
            for root, dirs, files in os.walk(dir_abs):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
                for fn in sorted(files):
                    if collected >= max_files or len(evidence_text) >= _MAX_TOTAL:
                        return
                    if not fn.endswith(_ALLOWED_EXTS):
                        continue
                    abs_path = os.path.join(root, fn)
                    if keyword:
                        rel = os.path.relpath(abs_path, dir_abs).lower()
                        if keyword.lower() not in rel and keyword.lower() not in fn.lower():
                            continue
                    _emit_file(abs_path)
                    collected += 1

        for fp in inputs.get("files_to_sample", []):
            if not isinstance(fp, str):
                continue
            if len(evidence_text) >= _MAX_TOTAL:
                break

            if fp.startswith("keyword:"):
                keyword = fp.split(":", 1)[1].strip()
                if not keyword:
                    continue
                root_dir = os.path.join(WORKSPACE_DIR, "src")
                if not os.path.isdir(root_dir):
                    _alt = os.path.join(WORKSPACE_DIR, "packages", "twenty-server", "src")
                    root_dir = _alt if os.path.isdir(_alt) else WORKSPACE_DIR
                _walk_dir(root_dir, keyword=keyword)
                continue

            if any(ch in fp for ch in "*?["):
                pattern = os.path.join(WORKSPACE_DIR, fp)
                matches = sorted(_glob.glob(pattern, recursive=True))[:_MAX_FILES_PER_ENTRY]
                if not matches and fp.startswith("src/"):
                    pattern = os.path.join(WORKSPACE_DIR, "packages", "twenty-server", fp)
                    matches = sorted(_glob.glob(pattern, recursive=True))[:_MAX_FILES_PER_ENTRY]
                for m in matches:
                    if os.path.isfile(m) and m.endswith(_ALLOWED_EXTS):
                        _emit_file(m)
                continue

            full = os.path.join(WORKSPACE_DIR, fp)
            if not os.path.exists(full) and fp.startswith("src/"):
                _alt_full = os.path.join(WORKSPACE_DIR, "packages", "twenty-server", fp)
                if os.path.exists(_alt_full):
                    full = _alt_full
            if os.path.isdir(full):
                _walk_dir(full)
            elif os.path.isfile(full):
                _emit_file(full, label=fp)
    elif evidence_type == "http_response_html":
        resp = context.get("last_response")
        if resp:
            evidence_text = resp.text[:5000]
    elif evidence_type == "rendered_dom":
        evidence_text = context.get("rendered_dom", "")[:8000]

    _prompt_cap = int(inputs.get("max_evidence_chars", 30000)) if isinstance(inputs, dict) else 30000
    from _llm_judge_safe import safe_chat_completion
    res = safe_chat_completion(
        messages=[
            {"role": "system", "content": (
                f"You are a strict code quality evaluator. Score from {score_range[0]} to {score_range[1]}. "
                "You have NO access to any tools, shell, or filesystem: evaluate SOLELY from the evidence "
                "provided below and do NOT ask to inspect more files. "
                "Return JSON: {\"score\": <number>, \"reason\": \"<explanation>\"} and no other text.")},
            {"role": "user", "content": f"Rubric:\n{rubric}\n\nEvidence:\n{evidence_text[:_prompt_cap]}"},
        ],
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE or "",
        temperature=0.1,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    if res.skipped:
        return PrimitiveResult(
            passed=True,
            data={
                "score": 0,
                "skipped": True,
                "llm_api_failure": res.llm_api_failure,
                "exception_class": res.exception_class,
                "reason": res.error or "skipped",
            },
            message=f"LLM judge SKIPPED ({res.reason()})",
        )

    raw = (res.raw or "").strip()
    raw_clean = raw
    fence_match = re.search(r"```(?:json|JSON)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fence_match:
        raw_clean = fence_match.group(1).strip()
    elif raw.startswith("```"):
        raw_clean = raw.lstrip("` \n").rstrip("` \n")
    if not raw_clean.startswith("{"):
        obj_match = re.search(r"\{.*\}", raw_clean, re.DOTALL)
        if obj_match:
            raw_clean = obj_match.group(0)
    try:
        result = json.loads(raw_clean)
        score = min(max(float(result.get("score", 0)), score_range[0]), score_range[1])
        return PrimitiveResult(passed=score > 0, data={"score": score, "reason": result.get("reason", "")}, message=f"LLM: {score}/{score_range[1]}")
    except Exception as e:
        for pat in (
            r'(?:^|\n)\s*#*\s*(?:Overall\s+)?Score\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*#*\s*Evaluation\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*#*\s*Rating\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'\*\*\s*Score\s*[:\-]?\s*(-?\d+(?:\.\d+)?)',
            r'\bscore\s+(?:is|of|=)\s*\**\s*(-?\d+(?:\.\d+)?)',
            r'(?:^|\n)\s*\**\s*(-?\d+(?:\.\d+)?)\s*(?:/\s*\d+\s*)?(?:—|–|-)\s*(?:Excellent|Strong|Good|Complete|Weak|Poor|None|Fair|Adequate)',
        ):
            mm = re.search(pat, raw, re.IGNORECASE)
            if mm:
                score = min(max(float(mm.group(1)), score_range[0]), score_range[1])
                return PrimitiveResult(passed=score > 0,
                                       data={"score": score, "reason": raw[:500], "fallback_parse": "markdown"},
                                       message=f"LLM: {score}/{score_range[1]}")
        _bare = None
        for _ln in reversed(raw.splitlines()):
            _c = _ln.strip().strip("`").strip().rstrip(".").strip()
            if re.fullmatch(r'-?\d+(?:\.\d+)?', _c):
                _bare = _c
                break
        if _bare is None:
            _nums = re.findall(r'-?\d+(?:\.\d+)?', raw)
            if _nums:
                _bare = _nums[-1]
        if _bare is not None:
            score = min(max(float(_bare), score_range[0]), score_range[1])
            return PrimitiveResult(passed=score > 0,
                                   data={"score": score, "reason": raw[:500], "fallback_parse": "bare_number"},
                                   message=f"LLM: {score}/{score_range[1]}")
        _force_instr = (
            f"\n\nIMPORTANT: Respond with ONLY a single integer between {score_range[0]} and "
            f"{score_range[1]}. Output just the number — no prose, no explanation, no JSON, and do "
            "NOT offer to investigate or inspect files. The evidence above is all you get.")
        _last_force = None
        for _attempt in range(3):
            force_res = safe_chat_completion(
                messages=[
                    {"role": "system", "content": (
                        f"You are a strict code quality evaluator scoring from {score_range[0]} to {score_range[1]}. "
                        "You have NO access to any tools, shell, or filesystem. Evaluate SOLELY from the evidence. "
                        "Respond with ONLY a single integer score and nothing else.")},
                    {"role": "user", "content": f"Rubric:\n{rubric}\n\nEvidence:\n{evidence_text[:_prompt_cap]}{_force_instr}"},
                ],
                model=LLM_MODEL,
                api_key=LLM_API_KEY,
                api_base=LLM_API_BASE or "",
                max_tokens=2000,
            )
            _last_force = force_res
            if not force_res.skipped:
                _fr = (force_res.raw or "").strip()
                _fnums = re.findall(r'-?\d+(?:\.\d+)?', _fr)
                if _fnums:
                    score = min(max(float(_fnums[-1]), score_range[0]), score_range[1])
                    return PrimitiveResult(passed=score > 0,
                                           data={"score": score, "reason": _fr[:500], "fallback_parse": "forced_retry"},
                                           message=f"LLM: {score}/{score_range[1]}")
        return PrimitiveResult(
            passed=True,
            data={
                "score": 0,
                "skipped": True,
                "parse_failure": True,
                "llm_api_failure": bool(getattr(_last_force, "llm_api_failure", False)),
                "exception_class": type(e).__name__,
                "reason": f"parse failure: {e}",
                "raw": res.raw[:200],
                "raw_clean": raw_clean[:200],
            },
            message=f"LLM judge SKIPPED (parse failure: {e})",
        )


def P22_graphql_query(inputs):
    endpoint = inputs.get("endpoint", "/graphql")
    query = resolve_dict(inputs.get("query", ""))
    variables = resolve_dict(inputs.get("variables"))
    expect_no_errors = inputs.get("expect_no_errors", False)
    url = get_url(endpoint)
    h = get_headers()
    body = {"query": query}
    if variables:
        body["variables"] = variables
    try:
        resp = get_session().post(url, json=body, headers=h, timeout=HTTP_TIMEOUT)
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"GraphQL error: {e}")
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}
    context["last_response"] = resp
    context["last_response_data"] = data
    context["last_status_code"] = resp.status_code

    store_as = inputs.get("store_as")
    if store_as:
        def _dig(obj, dotted):
            cur = obj
            for k in dotted.split("."):
                if isinstance(cur, dict):
                    cur = cur.get(k)
                elif isinstance(cur, list) and k.isdigit():
                    cur = cur[int(k)] if int(k) < len(cur) else None
                else:
                    return None
            return cur
        for ckey, spec in store_as.items():
            try:
                if isinstance(spec, str):
                    context[ckey] = _json_path(data, spec, resp)
                elif isinstance(spec, dict):
                    arr = _json_path(data, spec.get("from", "$"), resp) or []
                    find = spec.get("find", {})
                    extract = spec.get("extract")
                    for el in arr if isinstance(arr, list) else []:
                        if all(_dig(el, fk) == fv for fk, fv in find.items()):
                            context[ckey] = _dig(el, extract) if extract else el
                            break
            except Exception:
                pass

    if expect_no_errors and data.get("errors"):
        return PrimitiveResult(passed=False, data=data, response=resp, message=f"GraphQL errors: {data['errors'][0].get('message', '')[:100]}")
    return PrimitiveResult(passed=True, data=data, response=resp, message=f"GraphQL {endpoint} -> {resp.status_code}")


def P23_file_upload_download(inputs):
    upload = inputs.get("upload", {})
    upload = resolve_dict(upload)
    h = get_headers()
    h.pop("Content-Type", None)
    import base64
    content = upload.get("file_content", "")
    if content.startswith("base64:"):
        file_bytes = base64.b64decode(content[7:])
    else:
        file_bytes = content.encode()

    gql = upload.get("graphql")
    if gql:
        gql = resolve_dict(gql)
        endpoint = gql.get("endpoint", "/metadata")
        query = gql.get("query", "")
        variables = gql.get("variables", {}) or {}
        variables = dict(variables)
        variables[gql.get("file_var", "file")] = None
        operations = json.dumps({"query": query, "variables": variables})
        file_field = gql.get("file_var", "file")
        fmap = json.dumps({"0": [f"variables.{file_field}"]})
        mp = {
            "operations": (None, operations),
            "map": (None, fmap),
            "0": (upload.get("file_name", "test.txt"), file_bytes,
                  upload.get("content_type", "application/octet-stream")),
        }
        gh = dict(h)
        gh["x-apollo-operation-name"] = "uploadFile"
        gh["apollo-require-preflight"] = "true"
        try:
            resp = get_session().post(get_url(endpoint), files=mp, headers=gh, timeout=HTTP_TIMEOUT)
            context["last_response"] = resp
            context["last_status_code"] = resp.status_code
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            context["last_response_data"] = data
            ok = resp.status_code in (200, 201) and not data.get("errors")
            return PrimitiveResult(passed=ok, data=data, response=resp,
                                   message=f"GraphQL upload {endpoint} -> {resp.status_code}" +
                                           (f" errors: {data['errors'][0].get('message','')[:80]}" if data.get("errors") else ""))
        except Exception as e:
            return PrimitiveResult(passed=False, message=str(e))

    url = get_url(upload.get("path", "/file/upload"))
    try:
        resp = get_session().post(url, files={"file": (upload.get("file_name", "test.txt"), file_bytes, upload.get("content_type", "application/octet-stream"))}, headers=h, timeout=HTTP_TIMEOUT)
        context["last_response"] = resp
        context["last_status_code"] = resp.status_code
        try:
            data = resp.json()
            context["last_response_data"] = data
            if data.get("id"):
                context["fileId"] = data["id"]
        except Exception:
            context["last_response_data"] = resp.text
        return PrimitiveResult(passed=resp.status_code in (200, 201), data=context.get("last_response_data"), response=resp, message=f"Upload -> {resp.status_code}")
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


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
    "P22": P22_graphql_query,
    "P23": P23_file_upload_download,
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
