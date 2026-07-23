import io
import json
import re
import os
from pathlib import Path

import requests
import config
import utils

_context = {"auth_token": None, "auth_cookie": None}
_token_cache = {}


def _resolve(value, context):
    if not isinstance(value, str) or "{{" not in value:
        return value
    merged = dict(_context)
    merged.update(context)
    if value.startswith("{{") and value.endswith("}}") and value.count("{{") == 1:
        key = value[2:-2].strip()
        return merged.get(key)
    def _repl(m):
        key = m.group(1).strip()
        val = merged.get(key)
        return str(val) if val is not None else m.group(0)
    return re.sub(r'\{\{(\w+)\}\}', _repl, value)


def _resolve_inputs(inputs, context):
    if not inputs:
        return inputs
    out = {}
    for k, v in inputs.items():
        if isinstance(v, str):
            out[k] = _resolve(v, context)
        elif isinstance(v, dict):
            out[k] = _resolve_inputs(v, context)
        elif isinstance(v, list):
            out[k] = [_resolve(x, context) if isinstance(x, str) else x for x in v]
        else:
            out[k] = v
    return out


def P01_file_exists(inputs, context, last_response=None):
    path = _resolve_inputs(inputs, context).get("path")
    path = path or inputs.get("path")
    base = getattr(config, "WORKSPACE_DIR", ".")
    full = Path(base) / path if path else Path(base)
    exists = full.exists()
    return {"passed": exists, "message": f"exists={exists}", "data": {"exists": exists}}


def P02_file_content_match(inputs, context, last_response=None):
    inp = _resolve_inputs(inputs, context)
    path = inp.get("path")
    base = getattr(config, "WORKSPACE_DIR", ".")
    full = Path(base) / path
    if not full.exists():
        return {"passed": False, "message": "file not found"}
    text = full.read_text(encoding="utf-8", errors="ignore")
    pattern = inp.get("pattern", "")
    match_type = inp.get("match_type", "contains")
    if match_type == "regex":
        matched = bool(re.search(pattern, text))
    else:
        matched = pattern in text
    return {"passed": matched, "message": f"matched={matched}", "data": {"matched": matched}}


def P04_http_request(inputs, context, last_response=None):
    import time as _time
    inp = _resolve_inputs(inputs, context)
    method = (inp.get("method") or "GET").upper()
    path = inp.get("path", "")
    if path.startswith("/"):
        url = config.APP_BASE_URL.rstrip("/") + path
    else:
        url = path
    headers = dict(inp.get("headers") or {})
    if _context.get("auth_token"):
        headers.setdefault("Authorization", "Bearer " + _context["auth_token"])
    cookies = dict(inp.get("cookies") or {})
    if inp.get("send_token_cookie") and _context.get("auth_token"):
        _cookie_names = [os.environ.get("AUTH_COOKIE_NAME", "payload-token")]
        for _cn in _cookie_names:
            cookies.setdefault(_cn, _context["auth_token"])
    body = inp.get("body")
    timeout = inp.get("timeout") or config.HTTP_TIMEOUT
    use_multipart = isinstance(body, dict) and (body.get("_payload") == "multipart" or "file" in body)
    try:
        if method == "GET":
            r = utils.http_get(url, headers=headers, timeout=timeout, cookies=cookies)
        elif method == "POST" and isinstance(body, str):
            _h = dict(headers)
            _h.setdefault("Content-Type", "application/json")
            r = requests.post(url, data=body.encode("utf-8"), headers=_h, cookies=cookies, timeout=timeout)
        elif method == "POST" and use_multipart:
            data = {k: (v if isinstance(v, (str, type(None))) else str(v)) for k, v in body.items() if k not in ("_payload", "file") and v is not None}
            file_val = body.get("file")
            if file_val is not None:
                fname = file_val if isinstance(file_val, str) else "upload.bin"
                minimal_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
                files = {"file": (fname, io.BytesIO(minimal_png), "image/png")}
            else:
                files = None
            r = requests.post(url, files=files, data=data, headers=headers, cookies=cookies, timeout=timeout)
        elif method == "POST":
            r = utils.http_post(url, json_body=body, headers=headers, timeout=timeout, cookies=cookies)
        elif method == "PATCH":
            r = utils.http_patch(url, json_body=body, headers=headers, timeout=timeout, cookies=cookies)
        elif method == "DELETE":
            r = utils.http_delete(url, headers=headers, timeout=timeout, cookies=cookies)
        else:
            r = requests.request(method, url, json=body, headers=headers, cookies=cookies, timeout=timeout)
    except Exception as e:
        return {"passed": False, "message": str(e), "data": {"status_code": None, "body": None}}
    try:
        resp_body = r.json()
    except Exception:
        resp_body = r.text
    if r.status_code in (401, 403):
        _token_cache.clear()
    if "logout" in path.lower() and r.status_code in (200, 201):
        _token_cache.clear()
        _context["auth_token"] = None
    data = {"status_code": r.status_code, "headers": dict(r.headers), "body": resp_body, "response_body": r.text}
    capture_key = inp.get("capture_id_as")
    if capture_key and r.status_code in (200, 201) and isinstance(resp_body, dict):
        doc_id = resp_body.get("id")
        if doc_id is None and isinstance(resp_body.get("doc"), dict):
            doc_id = resp_body["doc"].get("id")
        if doc_id is None and isinstance(resp_body.get("data"), dict):
            doc_id = resp_body["data"].get("id")
        if doc_id is not None:
            context[capture_key] = doc_id
            _context[capture_key] = doc_id
    return {"passed": True, "message": f"status={r.status_code}", "data": data, "last_response": data}


def P05_api_crud(inputs, context, last_response=None):
    inp = _resolve_inputs(inputs, context)
    resource = inp.get("resource", "")
    base = config.APP_BASE_URL.rstrip("/")
    url_base = base + resource if resource.startswith("/") else base + "/" + resource
    token = _context.get("auth_token")
    headers = {"Authorization": "Bearer " + token} if token else {}
    create_body = inp.get("create_body") or {}
    steps = []
    r = utils.http_post(url_base, json_body=create_body, headers=headers, timeout=config.HTTP_TIMEOUT)
    steps.append(("create", r.status_code))
    if r.status_code not in (200, 201):
        return {"passed": False, "message": f"create failed {r.status_code}", "data": {"steps": steps}}
    try:
        doc = r.json()
        doc_id = doc.get("doc", doc).get("id") or doc.get("id")
        if doc_id is not None:
            context["post_id"] = doc_id
            context["access_post_id"] = doc_id
            context["deny_post_id"] = doc_id
    except Exception:
        pass
    read_url = f"{url_base}/{doc_id}" if doc_id is not None else url_base
    r2 = utils.http_get(read_url, headers=headers, timeout=config.HTTP_TIMEOUT)
    steps.append(("read", r2.status_code))
    passed = all(s[1] in (200, 201) for s in steps)
    return {"passed": passed, "message": str(steps), "data": {"steps": steps}, "last_response": {"body": r.json() if r.ok else None}}


def P06_json_schema_match(inputs, context, last_response=None):
    resp = (last_response or {}).get("body") if isinstance(last_response, dict) else last_response
    if resp is None:
        return {"passed": False, "message": "no response"}
    required = inputs.get("required_fields") or []
    if not required:
        return {"passed": True, "message": "no required fields"}
    missing = [f for f in required if not (isinstance(resp, dict) and f in resp)]
    return {"passed": len(missing) == 0, "message": f"missing={missing}", "data": {"missing_fields": missing}}


def _get_path(obj, path):
    if path == "response_body":
        if isinstance(obj, dict):
            return obj.get("response_body") or obj.get("body") or (json.dumps(obj) if not isinstance(obj.get("body"), str) else obj.get("body"))
        return obj if isinstance(obj, str) else json.dumps(obj)
    if not path or path == "$":
        return obj
    path = path.lstrip("$").lstrip(".")
    tokens = _tokenize_path(path)
    return _walk(obj, tokens)


def _tokenize_path(path):
    tokens = []
    for part in path.split("."):
        if not part:
            continue
        if part == "length":
            tokens.append("length")
            continue
        m_all = re.findall(r'([^\[\]]+|\[\d+\]|\[\*\])', part)
        if m_all:
            tokens.extend(m_all)
        else:
            tokens.append(part)
    return tokens


def _walk(obj, tokens):
    for i, tok in enumerate(tokens):
        if obj is None:
            return None
        if tok == "length":
            return len(obj) if isinstance(obj, (list, str, dict)) else None
        if tok == "[*]" or tok == "*":
            if isinstance(obj, list):
                rest = tokens[i + 1:]
                if rest:
                    return [_walk(x, rest) for x in obj]
                return obj
            return obj
        m = re.match(r'^\[(\d+)\]$', tok)
        if m:
            idx = int(m.group(1))
            obj = obj[idx] if isinstance(obj, list) and idx < len(obj) else None
        elif tok.isdigit():
            idx = int(tok)
            obj = obj[idx] if isinstance(obj, list) and idx < len(obj) else None
        else:
            obj = obj.get(tok) if isinstance(obj, dict) else None
    return obj


def P07_json_value_assert(inputs, context, last_response=None):
    resp = last_response
    if isinstance(resp, dict):
        body = resp.get("body") or resp.get("response_body")
        if body is None:
            body = resp
    else:
        body = resp
    if body is None:
        return {"passed": False, "message": "no response body"}
    if isinstance(body, str) and body.startswith("{"):
        try:
            body = json.loads(body)
        except Exception:
            pass
    assertions = inputs.get("assertions") or []
    results = []
    for a in assertions:
        path = a.get("path", "")
        expected = _resolve(a.get("expected"), context)
        actual = _get_path(body, path) if path != "response_body" else (body if isinstance(body, str) else json.dumps(body))
        if path == "status_code" and isinstance(resp, dict):
            actual = resp.get("status_code")
        expect_absent = a.get("expected_absent")
        expect_contains = a.get("expected_contains")
        expect_type = a.get("expected_type")
        expect_gte = a.get("expected_gte")
        expect_lte = a.get("expected_lte")
        expect_not_equals = a.get("expected_not_equals")
        expect_min_length = a.get("expected_min_length")
        expect_all_false_or_absent = a.get("expected_all_false_or_absent")
        tolerance = a.get("tolerance")
        expect_not_contains = a.get("expected_not_contains")
        expect_sorted_by = a.get("expected_sorted_by")
        expect_regex = a.get("expected_regex")
        expect_equals = a.get("expected_equals")
        expect_all_gt = a.get("expected_all_gt")
        expect_all_lte = a.get("expected_all_lte")
        expect_absent_or_null = a.get("expected_absent_or_null")
        if expect_absent:
            passed = actual is None or (isinstance(body, dict) and path.split(".")[-1] not in body)
        elif expect_contains is not None:
            if isinstance(expect_contains, list):
                if isinstance(actual, list):
                    passed = all(item in actual for item in expect_contains)
                else:
                    passed = all(str(item) in str(actual) for item in expect_contains)
            else:
                passed = expect_contains in str(actual) if actual is not None else False
        elif expect_type:
            type_ok = (expect_type == "string" and isinstance(actual, str)) or \
                      (expect_type == "number" and isinstance(actual, (int, float))) or \
                      (expect_type == "array" and isinstance(actual, list)) or \
                      (expect_type == "object" and isinstance(actual, dict))
            passed = type_ok
        elif expect_gte is not None:
            passed = actual is not None and (actual >= expect_gte if isinstance(actual, (int, float)) else len(actual) >= expect_gte)
        elif expect_lte is not None:
            passed = actual is not None and (actual <= expect_lte if isinstance(actual, (int, float)) else len(actual) <= expect_lte)
        elif expect_not_equals is not None:
            passed = actual != _resolve(expect_not_equals, context)
        elif expect_min_length is not None:
            passed = actual is not None and len(str(actual)) >= expect_min_length
        elif expect_all_false_or_absent:
            if isinstance(actual, list):
                passed = all(x is False or x is None for x in actual)
            elif isinstance(actual, bool):
                passed = actual is False
            else:
                passed = actual is None or actual is False
        elif tolerance is not None and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            passed = abs(actual - expected) <= tolerance
        elif expect_not_contains is not None:
            if isinstance(actual, list):
                passed = all(item != expect_not_contains and str(item) != str(expect_not_contains) for item in actual)
            elif actual is None:
                passed = True
            else:
                passed = str(expect_not_contains) not in str(actual)
        elif expect_sorted_by is not None:
            order = (a.get("order") or "asc").lower()
            if isinstance(actual, list):
                vals = [(x.get(expect_sorted_by) if isinstance(x, dict) else x) for x in actual]
                vals = [v for v in vals if v is not None]
                if len(vals) <= 1:
                    passed = True
                else:
                    try:
                        if order == "desc":
                            passed = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
                        else:
                            passed = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
                    except TypeError:
                        passed = False
            else:
                passed = False
        elif expect_regex is not None:
            passed = actual is not None and re.search(str(expect_regex), str(actual)) is not None
        elif expect_equals is not None:
            target = expect_equals
            if isinstance(expect_equals, str) and expect_equals.startswith("$"):
                target = _get_path(body, expect_equals)
            else:
                target = _resolve(expect_equals, context)
            passed = actual == target
        elif expect_all_gt is not None:
            passed = isinstance(actual, list) and len(actual) > 0 and all(isinstance(x, (int, float)) and x > expect_all_gt for x in actual)
        elif expect_all_lte is not None:
            passed = isinstance(actual, list) and len(actual) > 0 and all(isinstance(x, (int, float)) and x <= expect_all_lte for x in actual)
        elif expect_absent_or_null is not None:
            passed = actual is None
        else:
            passed = actual == expected
        results.append({"path": path, "actual": actual, "passed": passed})
    all_passed = all(r["passed"] for r in results)
    return {"passed": all_passed, "message": str(results), "data": {"results": results}}


def P08_db_query(inputs, context, last_response=None):
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        return {"passed": False, "message": "psycopg2 not installed"}
    inp = _resolve_inputs(inputs, context)
    sql = inp.get("sql", "")
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, context)
    except Exception:
        pass
    expected = inp.get("expected_result")
    try:
        conn = psycopg2.connect(host=config.DB_HOST, port=config.DB_PORT, dbname=config.DB_NAME,
                                user=config.DB_USER, password=config.DB_PASSWORD)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return {"passed": False, "message": str(e), "data": {"rows": []}}
    rows = [dict(r) for r in rows]
    match = True
    if expected is not None and rows:
        for k, v in expected.items():
            if rows[0].get(k) != v:
                match = False
                break
    return {"passed": match, "message": f"rows={len(rows)}", "data": {"rows": rows, "row_count": len(rows), "match": match}}


def P09_db_table_exists(inputs, context, last_response=None):
    try:
        import psycopg2
    except ImportError:
        return {"passed": False, "message": "psycopg2 not installed"}
    tables = inputs.get("tables") or []
    try:
        conn = psycopg2.connect(host=config.DB_HOST, port=config.DB_PORT, dbname=config.DB_NAME,
                                user=config.DB_USER, password=config.DB_PASSWORD)
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        existing_tables = {r[0] for r in cur.fetchall()}
        cur.close()
        conn.close()
    except Exception as e:
        return {"passed": False, "message": str(e)}
    existing = [t for t in tables if t in existing_tables]
    missing = [t for t in tables if t not in existing_tables]
    found = len(existing)
    total = len(tables)
    passed = found >= max(1, total - 2)
    return {"passed": passed, "message": f"found={found}/{total}", "data": {"existing": existing, "missing": missing, "found_count": found, "total_count": total}}


def P10_db_column_check(inputs, context, last_response=None):
    try:
        import psycopg2
    except ImportError:
        return {"passed": False, "message": "psycopg2 not installed"}
    inp = _resolve_inputs(inputs, context)
    table = inp.get("table", "")
    expected_columns = inp.get("expected_columns") or []
    try:
        conn = psycopg2.connect(host=config.DB_HOST, port=config.DB_PORT, dbname=config.DB_NAME,
                                user=config.DB_USER, password=config.DB_PASSWORD)
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s", (table,))
        existing = {r[0] for r in cur.fetchall()}
        cur.close()
        conn.close()
    except Exception as e:
        return {"passed": False, "message": str(e)}
    found = [c for c in expected_columns if c in existing]
    missing = [c for c in expected_columns if c not in existing]
    passed = len(found) >= max(1, len(expected_columns) - 2)
    return {"passed": passed, "message": f"found={len(found)}/{len(expected_columns)}", "data": {"existing": found, "missing": missing}}


def P12_docker_exec(inputs, context, last_response=None):
    inp = _resolve_inputs(inputs, context)
    cmd = inp.get("command", "")
    container = inp.get("container") or config.APP_CONTAINER
    expect_success = inp.get("expect_success", True)
    try:
        code, out, err = utils.docker_exec(cmd, container=container, expect_success=expect_success)
        return {"passed": code == 0, "message": f"exit={code}", "data": {"returncode": code, "stdout": out, "stderr": err}}
    except Exception as e:
        return {"passed": False, "message": str(e)}


def P13_auth_login(inputs, context, last_response=None):
    import time as _time
    inp = _resolve_inputs(inputs, context)
    role = inp.get("role", "admin")
    if role in _token_cache:
        test_token = _token_cache[role]
        try:
            tr = utils.http_get(config.APP_BASE_URL.rstrip("/") + "/api/users/me",
                                headers={"Authorization": "Bearer " + test_token}, timeout=5)
            if tr.status_code in (200, 201):
                try:
                    me_data = tr.json()
                    if me_data.get("user") is not None:
                        _context["auth_token"] = test_token
                        _uid = me_data["user"].get("id")
                        if _uid is not None:
                            context[f"{role}_id"] = _uid
                            _context[f"{role}_id"] = _uid
                        return {"passed": True, "message": f"cached role={role}"}
                except Exception:
                    pass
        except Exception:
            pass
        del _token_cache[role]
    users = getattr(config, "TEST_USERS", {})
    creds = users.get(role) or users.get("admin", {})
    email = creds.get("email", "admin@test.com")
    password = creds.get("password", "Test1234!")
    login_path = inp.get("login_path") or "/api/users/login"
    url = config.APP_BASE_URL.rstrip("/") + login_path
    r = None
    for attempt in range(3):
        try:
            r = utils.http_post(url, json_body={"email": email, "password": password}, timeout=config.HTTP_TIMEOUT)
            break
        except Exception as e:
            if attempt < 2:
                _time.sleep(1 * (attempt + 1))
                continue
            return {"passed": False, "message": str(e)}
    if r.status_code not in (200, 201):
        return {"passed": False, "message": f"login {r.status_code}"}
    try:
        data = r.json()
        token = data.get("token") or data.get("refreshedToken")
        if not token:
            token = data.get("user", {}).get("token")
        if token:
            _token_cache[role] = token
            _context["auth_token"] = token
            if isinstance(data.get("user"), dict) and data["user"].get("id") is not None:
                context["admin_id"] = data["user"]["id"]
                context[f"{role}_id"] = data["user"]["id"]
                _context[f"{role}_id"] = data["user"]["id"]
            return {"passed": True, "message": f"logged in as {role}"}
    except Exception:
        pass
    return {"passed": False, "message": "no token in response"}


def P14_permission_check(inputs, context, last_response=None):
    inp = _resolve_inputs(inputs, context)
    action = inp.get("action", "")
    expected = inp.get("expected_result", "denied")
    token = _context.get("auth_token")
    method, path = action.split(None, 1) if " " in action else ("GET", action)
    url = config.APP_BASE_URL.rstrip("/") + path if path.startswith("/") else config.API_BASE_URL + "/" + path
    headers = {"Authorization": "Bearer " + token} if token else {}
    try:
        if method == "GET":
            r = utils.http_get(url, headers=headers)
        elif method == "POST":
            r = utils.http_post(url, headers=headers)
        elif method == "PATCH":
            r = utils.http_patch(url, headers=headers)
        elif method == "DELETE":
            r = utils.http_delete(url, headers=headers)
        else:
            r = requests.request(method, url, headers=headers, timeout=config.HTTP_TIMEOUT)
    except Exception as e:
        return {"passed": False, "message": str(e)}
    if expected == "denied":
        passed = r.status_code in (403, 404)
    else:
        passed = r.status_code in (200, 201)
    return {"passed": passed, "message": f"status={r.status_code}", "data": {"status_code": r.status_code}}


def P15_status_code_assert(inputs, context, last_response=None):
    status = (last_response or {}).get("status_code") if isinstance(last_response, dict) else None
    if status is None:
        return {"passed": False, "message": "no status_code"}
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
    else:
        passed = 200 <= status < 300
    return {"passed": passed, "message": f"status={status} expected={sorted(accepted) if accepted else 'any 2xx'}"}


def P17_llm_judge(inputs, context, last_response=None):
    rubric = (inputs or {}).get("rubric_prompt") or ""
    files_to_sample = (inputs or {}).get("files_to_sample") or []
    score_range = (inputs or {}).get("score_range") or [0, 5]
    workspace = getattr(config, "WORKSPACE_DIR", ".")

    api_key = getattr(config, "LLM_API_KEY", None) or ""

    evidence_parts = [rubric]
    _SRC_EXTS = (".ts", ".tsx", ".js", ".jsx", ".json")
    _EVID_BUDGET = 24000
    _evid_used = 0
    _rubric_tokens = {w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", (rubric or "").lower())}
    def _rank(relpath: str) -> int:
        low = relpath.lower()
        score = sum(1 for t in _rubric_tokens if t in low)
        for key in ("payload.config", "collections", "globals", "hooks", "fields", "access", "endpoints"):
            if key in low:
                score += 3
        return score
    for item in files_to_sample[:5]:
        if _evid_used >= _EVID_BUDGET:
            break
        p = Path(workspace) / item if isinstance(item, str) else Path(workspace)
        if p.is_dir():
            try:
                cand = []
                for f in p.rglob("*"):
                    parts = set(f.parts)
                    if parts & {"node_modules", ".next", ".git", "dist", "build"}:
                        continue
                    if f.is_file() and f.suffix in _SRC_EXTS:
                        try:
                            rel = str(f.relative_to(Path(workspace)))
                        except Exception:
                            rel = f.name
                        cand.append((f, rel))
                    if len(cand) >= 200:
                        break
                cand.sort(key=lambda fr: (-_rank(fr[1]), fr[1]))
                for f, rel in cand[:14]:
                    if _evid_used >= _EVID_BUDGET:
                        break
                    chunk = f"\n--- {rel} ---\n{f.read_text(encoding='utf-8', errors='ignore')[:2000]}"
                    evidence_parts.append(chunk)
                    _evid_used += len(chunk)
            except Exception:
                pass
        elif p.is_file():
            try:
                chunk = f"\n--- {p.name} ---\n{p.read_text(encoding='utf-8', errors='ignore')[:3000]}"
                evidence_parts.append(chunk)
                _evid_used += len(chunk)
            except Exception:
                pass
    prompt = "Evaluate the following according to the rubric. Reply with only a number (integer) for the score in range " + str(score_range) + ".\n\n" + "\n".join(evidence_parts)

    from _llm_judge_safe import safe_chat_completion
    res = safe_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=getattr(config, "LLM_MODEL", "gpt-4o-mini"),
        api_key=api_key,
        api_base=getattr(config, "LLM_API_BASE", "") or "",
        temperature=0.0,
        max_tokens=64,
    )
    try:
        text = res.raw or ""
        m = re.search(r"\d+", text)
        if m is None:
            for _retry in range(2):
                res = safe_chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    model=getattr(config, "LLM_MODEL", "gpt-4o-mini"),
                    api_key=api_key,
                    api_base=getattr(config, "LLM_API_BASE", "") or "",
                    temperature=0.0,
                    max_tokens=16,
                )
                if res.skipped:
                    break
                text = res.raw or ""
                m = re.search(r"\d+", text)
                if m is not None:
                    break
        if m is None:
            return {
                "passed": False,
                "message": "LLM judge SKIPPED (no verdict after retries)",
                "data": {
                    "score": 0,
                    "score_range": score_range,
                    "skipped": True,
                    "parse_failure": True,
                    "llm_api_failure": bool(getattr(res, "llm_api_failure", False)),
                    "exception_class": "",
                    "reason": "LLM judge unavailable: no verdict after retries",
                    "raw": (res.raw or "")[:200],
                },
            }
        score = int(m.group())
        score = max(score_range[0], min(score_range[1], score))
        passed = score >= (score_range[0] + score_range[1]) / 2
        return {"passed": passed, "message": f"llm score={score}", "data": {"score": score, "score_range": score_range}}
    except Exception as e:
        return {
            "passed": False,
            "message": f"LLM judge SKIPPED ({e})",
            "data": {
                "score": 0,
                "score_range": score_range,
                "skipped": True,
                "parse_failure": True,
                "llm_api_failure": False,
                "exception_class": type(e).__name__,
                "reason": f"parse failure: {e}",
                "raw": res.raw[:200],
            },
        }


PRIMITIVES = {
    "P01": P01_file_exists,
    "P02": P02_file_content_match,
    "P04": P04_http_request,
    "P05": P05_api_crud,
    "P06": P06_json_schema_match,
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
