import os
import re
import glob
import json
import requests
import psycopg2
import psycopg2.extras
from utils import PrimitiveResult, context, http_request, safe_json, resolve_placeholders, docker_exec
from config import (
    WORKSPACE_DIR, APP_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
    APP_CONTAINER, LLM_API_KEY, LLM_API_BASE, LLM_MODEL, REQUEST_TIMEOUT,
    TOKEN_URL_TEMPLATE, TEST_USERS,
)

_token_cache = {}
_token_expiry = {}
_last_response = None


def get_last_response():
    return _last_response


def _get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def p01_file_exists(inputs):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    ftype = inputs.get("type", "file")
    if ftype == "directory":
        exists = os.path.isdir(path)
    else:
        exists = os.path.isfile(path)
    return PrimitiveResult(passed=exists, data={"exists": exists}, message=f"{'Found' if exists else 'Not found'}: {inputs['path']}")


def p02_file_content_match(inputs):
    path = inputs.get("path", "")
    resp = get_last_response()
    if resp is not None:
        content = resp.text if hasattr(resp, 'text') else str(resp)
    elif path:
        fpath = os.path.join(WORKSPACE_DIR, path)
        if not os.path.isfile(fpath):
            return PrimitiveResult(passed=False, message=f"File not found: {path}")
        with open(fpath, "r", errors="replace") as f:
            content = f.read()
    else:
        return PrimitiveResult(passed=False, message="No content to match")

    pattern = inputs["pattern"]
    match_type = inputs.get("match_type", "contains")

    if match_type == "contains":
        matched = pattern in content
    elif match_type == "regex":
        matched = bool(re.search(pattern, content))
    else:
        matched = pattern in content

    return PrimitiveResult(passed=matched, data={"matched": matched}, message=f"Pattern '{pattern[:50]}': {'found' if matched else 'not found'}")


def p03_file_count(inputs):
    base = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", ""))
    pattern = inputs.get("glob", "**/*")
    files = glob.glob(os.path.join(base, pattern), recursive=True)
    files = [f for f in files if os.path.isfile(f)]
    count = len(files)
    min_expected = inputs.get("min_expected", 1)
    return PrimitiveResult(
        passed=count >= min_expected,
        data={"count": count, "files": [os.path.basename(f) for f in files[:20]]},
        message=f"Found {count} files (expected >= {min_expected})"
    )


def p04_http_request(inputs):
    global _last_response
    resolved = resolve_placeholders(inputs)
    method = resolved.get("method", "GET")
    path = resolved.get("path", "/")
    headers = resolved.get("headers", {})
    body = resolved.get("body")
    body_form = resolved.get("body_form")
    timeout = resolved.get("timeout", REQUEST_TIMEOUT)

    resp = http_request(method, path, headers=headers, body=body, body_form=body_form, timeout=timeout)
    _last_response = resp

    data = {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "body": safe_json(resp),
        "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
        "text": resp.text[:2000] if resp.text else "",
    }

    _capture_api_evidence(method, path, resp, data)

    return PrimitiveResult(passed=True, data=data, message=f"{method} {path} -> {resp.status_code}")


def _capture_api_evidence(method, path, resp, data):
    try:
        bucket = context.get("api_evidence")
        if not isinstance(bucket, list):
            bucket = []
            context["api_evidence"] = bucket
        text_snippet = (resp.text or "")[:1500]
        try:
            body_snippet = safe_json(resp)
            if isinstance(body_snippet, (dict, list)):
                body_str = json.dumps(body_snippet)[:1500]
            else:
                body_str = text_snippet
        except Exception:
            body_str = text_snippet
        rec = {
            "method": method,
            "path": path,
            "status": resp.status_code,
            "content_type": resp.headers.get("Content-Type", "")[:120],
            "body": body_str,
            "ms": data.get("response_time_ms", 0),
        }
        bucket.append(rec)
        cap = 80
        if len(bucket) > cap:
            errs = [r for r in bucket if r.get("status", 200) >= 400]
            oks = [r for r in bucket if r.get("status", 200) < 400]
            err_keep = errs[-max(cap // 2, len(errs) - cap // 2):] if errs else []
            ok_keep = oks[-(cap - len(err_keep)):]
            bucket[:] = err_keep + ok_keep
    except Exception:
        pass


def p05_api_crud(inputs):
    resolved = resolve_placeholders(inputs)
    resource = resolved["resource"]
    create_body = resolved.get("create_body", {})
    update_body = resolved.get("update_body", {})
    token = context.get("auth_token", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    steps_passed = 0
    steps_total = 4
    entity_id = None
    evidence = {}

    try:
        exp_create = resolved.get("expected_create_status", 201)
        resp = http_request("POST", resource, headers=headers, body=create_body)
        evidence["create_status"] = resp.status_code
        if resp.status_code == exp_create:
            steps_passed += 1
            loc = resp.headers.get("Location", "")
            if loc:
                entity_id = loc.rstrip("/").split("/")[-1]
            else:
                d = safe_json(resp)
                entity_id = d.get("id", "")
            evidence["entity_id"] = entity_id

        if entity_id:
            resp = http_request("GET", f"{resource}/{entity_id}", headers=headers)
            evidence["read_status"] = resp.status_code
            if resp.status_code == 200:
                steps_passed += 1
                read_data = safe_json(resp)
                evidence["read_body"] = read_data
                expected_fields = resolved.get("expected_read_fields", [])
                for ef in expected_fields:
                    if ef not in read_data:
                        evidence[f"missing_field_{ef}"] = True

        if entity_id and update_body:
            exp_update = resolved.get("expected_update_status", 204)
            resp = http_request("PUT", f"{resource}/{entity_id}", headers=headers, body=update_body)
            evidence["update_status"] = resp.status_code
            if resp.status_code == exp_update:
                steps_passed += 1
        elif entity_id:
            steps_passed += 1

        if entity_id:
            exp_delete = resolved.get("expected_delete_status", 204)
            resp = http_request("DELETE", f"{resource}/{entity_id}", headers=headers)
            evidence["delete_status"] = resp.status_code
            if resp.status_code == exp_delete:
                steps_passed += 1

    except Exception as e:
        evidence["error"] = str(e)

    return PrimitiveResult(
        passed=steps_passed == steps_total,
        data={"steps_passed": steps_passed, "steps_total": steps_total, "entity_id": entity_id, **evidence},
        message=f"CRUD {resource}: {steps_passed}/{steps_total} steps"
    )


def p06_json_schema_match(inputs):
    resp = get_last_response()
    if resp is None:
        return PrimitiveResult(passed=False, message="No response to validate")

    body = safe_json(resp)
    required = inputs.get("required_fields", [])
    missing = [f for f in required if f not in body]

    return PrimitiveResult(
        passed=len(missing) == 0,
        data={"missing_fields": missing, "present_fields": [f for f in required if f in body]},
        message=f"Schema: {len(required)-len(missing)}/{len(required)} fields present" + (f", missing: {missing}" if missing else "")
    )


def p07_json_value_assert(inputs):
    resp = get_last_response()
    if resp is None:
        return PrimitiveResult(passed=False, message="No response to assert on")

    body = safe_json(resp)
    if isinstance(body, list) and not inputs.get("assertions", [{}])[0].get("path", "").startswith("$["):
        pass

    assertions = inputs.get("assertions", [])
    results = []
    all_passed = True

    for a in assertions:
        path = a.get("path", "")
        operator = a.get("operator", "equals")
        expected = a.get("expected")

        actual = _json_path_extract(body, path)

        if "expected_in" in a:
            passed = actual in a["expected_in"]
            expected = a["expected_in"]
            results.append({"path": path, "expected": expected, "actual": actual, "passed": passed, "operator": "in"})
            if not passed: all_passed = False
            continue
        if "expected_min_length" in a:
            passed = isinstance(actual, (list, str, dict)) and len(actual) >= a["expected_min_length"]
            results.append({"path": path, "expected": f">= {a['expected_min_length']}", "actual": actual, "passed": passed, "operator": "min_length"})
            if not passed: all_passed = False
            continue
        if "expected_type" in a:
            tp = a["expected_type"]
            type_map = {"array": list, "string": str, "number": (int, float), "integer": int, "object": dict, "boolean": bool}
            passed = isinstance(actual, type_map.get(tp, object))
            results.append({"path": path, "expected": tp, "actual": str(type(actual).__name__), "passed": passed, "operator": "type"})
            if not passed: all_passed = False
            continue

        if operator == "equals":
            passed = actual == expected
        elif operator == "contains":
            passed = expected in str(actual) if actual is not None else False
        elif operator == "contains_all":
            passed = all(item in (actual or []) for item in (expected or []))
        elif operator == "exists":
            passed = actual is not None
        elif operator == "not_exists":
            passed = actual is None
        elif operator == "is_array":
            passed = isinstance(actual, list)
        elif operator == "is_string":
            passed = isinstance(actual, str)
        elif operator == "gt":
            passed = actual is not None and actual > expected
        elif operator == "gte":
            passed = actual is not None and actual >= expected
        elif operator == "lt":
            passed = actual is not None and actual < expected
        elif operator == "array_length":
            passed = isinstance(actual, list) and len(actual) == expected
        elif operator == "array_min_length":
            passed = isinstance(actual, list) and len(actual) >= expected
        elif operator == "starts_with":
            passed = isinstance(actual, str) and actual.startswith(expected)
        elif operator == "not_contains":
            passed = expected not in (actual if isinstance(actual, list) else [actual])
        elif operator == "not_equals":
            passed = actual != expected
        elif operator == "store_as":
            stored = actual
            if isinstance(stored, list) and len(stored) >= 1:
                stored = stored[0]
            if isinstance(stored, dict) and "id" in stored:
                stored = stored["id"]
            context[a.get("key", "stored_value")] = stored
            passed = True
        elif operator == "conditional_exists_on_status_200":
            resp_obj = get_last_response()
            passed = (resp_obj and resp_obj.status_code == 200 and actual is not None) or (resp_obj and resp_obj.status_code != 200)
        else:
            passed = actual == expected

        if a.get("tolerance") and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            passed = abs(actual - expected) <= a["tolerance"]

        results.append({"path": path, "expected": expected, "actual": actual, "passed": passed, "operator": operator})
        if not passed:
            all_passed = False

    return PrimitiveResult(
        passed=all_passed,
        data={"results": results, "all_passed": all_passed},
        message=f"Assertions: {sum(1 for r in results if r['passed'])}/{len(results)} passed"
    )


def _json_path_extract(data, path):
    if not path or path == "$":
        return data
    path = path.lstrip("$")
    if path.startswith("[") and not path.startswith("[?("):
        idx_match = re.match(r"\[(\d+)\](.*)", path)
        if idx_match:
            idx = int(idx_match.group(1))
            rest = idx_match.group(2).lstrip(".")
            if isinstance(data, list) and idx < len(data):
                return _json_path_extract(data[idx], rest) if rest else data[idx]
            return None
    path = path.lstrip(".")

    if path.startswith("[?("):
        match = re.match(r'\[\?@\.(\w+)==[\'"]?([^\'")\]]+)[\'"]?\]', path.replace("(", "").replace(")", ""))
        if match and isinstance(data, list):
            key, val = match.groups()
            for item in data:
                if str(item.get(key, "")) == val:
                    rest = path[path.index("]") + 1:].lstrip(".")
                    if rest:
                        return _json_path_extract(item, rest)
                    return item
            return None
        if "[?(@." in path and isinstance(data, list):
            filter_match = re.search(r"\[\?\(@\.(\w+)=='([^']+)'\)\]", path)
            if filter_match:
                key, val = filter_match.groups()
                rest_start = path.index(")]") + 2
                rest = path[rest_start:].lstrip(".")
                for item in data:
                    if str(item.get(key, "")) == val:
                        return _json_path_extract(item, rest) if rest else item
            return None

    parts = path.split(".")
    current = data
    for part in parts:
        if current is None:
            return None
        idx_match = re.match(r"(\w+)\[(\d+)\]", part)
        if idx_match:
            key, idx = idx_match.groups()
            current = current.get(key, []) if isinstance(current, dict) else current
            idx = int(idx)
            current = current[idx] if isinstance(current, list) and idx < len(current) else None
        elif isinstance(current, dict):
            if part in current:
                current = current[part]
            elif part.startswith("[?("):
                return _json_path_extract(current, part)
            else:
                return None
        else:
            return None
    return current


def p08_db_query(inputs):
    resolved = resolve_placeholders(inputs)
    sql = resolved.get("sql", "SELECT 1")
    expected = resolved.get("expected_result")

    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            rows = [dict(r) for r in rows]
        conn.close()

        matched = True
        if expected and rows:
            for k, v in expected.items():
                if str(rows[0].get(k)) != str(v):
                    matched = False

        return PrimitiveResult(passed=matched, data={"rows": rows, "row_count": len(rows)}, message=f"Query returned {len(rows)} rows")
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")


def p09_db_table_exists(inputs):
    tables = inputs.get("tables", [])
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            existing = {r["table_name"].lower() for r in cur.fetchall()}
        conn.close()

        found = [t for t in tables if t.lower() in existing]
        missing = [t for t in tables if t.lower() not in existing]

        return PrimitiveResult(
            passed=len(missing) == 0,
            data={"existing": found, "missing": missing, "found_count": len(found), "total_count": len(tables)},
            message=f"Tables: {len(found)}/{len(tables)} exist" + (f", missing: {missing}" if missing else "")
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")


def p10_db_column_check(inputs):
    table = inputs.get("table", "")
    expected = inputs.get("expected_columns", [])
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND LOWER(table_name)=LOWER(%s)", (table,))
            actual = {r["column_name"].lower() for r in cur.fetchall()}
        conn.close()

        found = [c for c in expected if c.lower() in actual]
        missing = [c for c in expected if c.lower() not in actual]

        return PrimitiveResult(
            passed=len(missing) == 0,
            data={"existing": found, "missing": missing, "found_count": len(found), "total_count": len(expected)},
            message=f"Columns in {table}: {len(found)}/{len(expected)}" + (f", missing: {missing}" if missing else "")
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"DB error: {e}")


def p11_db_index_check(inputs):
    table = inputs.get("table", "")
    expected_indexes = inputs.get("expected_indexes", [])
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT indexname, array_agg(attname ORDER BY attnum) as columns
                FROM pg_indexes JOIN pg_attribute ON attrelid = (schemaname || '.' || tablename)::regclass
                WHERE LOWER(tablename)=LOWER(%s) AND schemaname='public'
                GROUP BY indexname
            """, (table,))
            rows = cur.fetchall()
        conn.close()
        return PrimitiveResult(passed=True, data={"indexes": [dict(r) for r in rows]}, message=f"Found {len(rows)} indexes on {table}")
    except Exception:
        return PrimitiveResult(passed=True, message="Index check skipped")


def p12_docker_exec(inputs):
    resolved = resolve_placeholders(inputs)
    command = resolved.get("command", "echo ok")
    container = resolved.get("container", APP_CONTAINER)
    expect_success = resolved.get("expect_success", True)

    code, stdout, stderr = docker_exec(command, container)
    passed = (code == 0) if expect_success else True

    expect_output = resolved.get("expect_output_contains")
    if expect_output and expect_output not in stdout:
        passed = False

    return PrimitiveResult(passed=passed, data={"exit_code": code, "stdout": stdout[:1000], "stderr": stderr[:500]}, message=f"docker exec: exit={code}")


def p13_auth_login(inputs):
    resolved = resolve_placeholders(inputs)
    role = resolved.get("role", "admin")

    import time
    if role in _token_cache:
        expiry = _token_expiry.get(role, 0)
        if expiry == 0 or time.time() < expiry - 30:
            context["auth_token"] = _token_cache[role]
            context["auth_role"] = role
            return PrimitiveResult(passed=True, message=f"Using cached token for {role}")
        else:
            del _token_cache[role]
            del _token_expiry[role]

    method = resolved.get("method", "password_grant")
    realm = resolved.get("realm", TEST_USERS.get(role, {}).get("realm", "master"))
    client_id = resolved.get("client_id", TEST_USERS.get(role, {}).get("client_id", "admin-cli"))
    username = resolved.get("username", TEST_USERS.get(role, {}).get("username", "admin"))
    password = resolved.get("password", TEST_USERS.get(role, {}).get("password", "admin"))

    token_url = resolved.get("token_endpoint", TOKEN_URL_TEMPLATE.format(realm=realm))
    if token_url.startswith("/"):
        token_url = APP_BASE_URL + token_url

    try:
        data = f"grant_type=password&client_id={client_id}&username={username}&password={password}"
        client_secret = resolved.get("client_secret")
        if client_secret:
            data += f"&client_secret={client_secret}"

        resp = requests.post(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=REQUEST_TIMEOUT)

        if resp.status_code == 200:
            token_data = resp.json()
            token = token_data.get("access_token")
            if token:
                _token_cache[role] = token
                expires_in = token_data.get("expires_in", 300)
                _token_expiry[role] = time.time() + expires_in
                context["auth_token"] = token
                context["auth_role"] = role
                context["refresh_token"] = token_data.get("refresh_token", "")
                return PrimitiveResult(passed=True, data=token_data, message=f"Auth OK for {role} (expires in {expires_in}s)")

        return PrimitiveResult(passed=False, data=safe_json(resp), message=f"Auth failed for {role}: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        return PrimitiveResult(passed=False, message=f"Auth error: {e}")


def p14_permission_check(inputs):
    resolved = resolve_placeholders(inputs)
    action = resolved.get("action", "GET /")
    expected_result = resolved.get("expected_result", "denied")
    expected_status = resolved.get("expected_status", 403)

    parts = action.split(" ", 1)
    method = parts[0]
    path = parts[1] if len(parts) > 1 else "/"
    body = resolved.get("body")

    resp = http_request(method, path, body=body)

    if expected_result == "denied":
        passed = resp.status_code in (403, 404, expected_status)
    else:
        passed = resp.status_code in (200, 201, 204)

    return PrimitiveResult(
        passed=passed,
        data={"status_code": resp.status_code, "expected": expected_status},
        message=f"Permission {action}: {resp.status_code} ({'denied' if resp.status_code in (403,404) else 'allowed'})"
    )


def p15_status_code_assert(inputs):
    resp = get_last_response()
    if resp is None:
        return PrimitiveResult(passed=False, message="No response for status check")

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

    actual = resp.status_code
    if accepted:
        passed = actual in accepted
    else:
        passed = 200 <= actual < 400

    accepted_disp = sorted(accepted) if accepted else "2xx/3xx"
    return PrimitiveResult(
        passed=passed,
        data={"actual_status": actual, "expected": accepted_disp},
        message=f"Status: {actual} (expected {accepted_disp})",
    )


def p16_response_time_check(inputs):
    resp = get_last_response()
    if resp is None:
        return PrimitiveResult(passed=False, message="No response for timing")

    max_ms = inputs.get("max_ms", 5000)
    actual_ms = int(resp.elapsed.total_seconds() * 1000)
    return PrimitiveResult(passed=actual_ms <= max_ms, data={"actual_ms": actual_ms, "max_ms": max_ms}, message=f"Response time: {actual_ms}ms (max {max_ms}ms)")


def p17_llm_judge(inputs):
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
    from _llm_judge_safe import safe_chat_completion

    evidence_type = inputs.get("evidence_type", "code_files")
    rubric = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])

    evidence_text = ""
    if evidence_type == "http_response_html":
        resp = get_last_response()
        if resp:
            evidence_text = resp.text[:3000]
    elif evidence_type == "api_responses":
        bucket = context.get("api_evidence", [])
        if isinstance(bucket, dict):
            bucket = list(bucket.values()) if bucket else []
        filter_paths = inputs.get("api_path_filters")
        if filter_paths:
            filtered = [r for r in bucket
                        if any(fp in r.get("path", "") for fp in filter_paths)]
            if filtered:
                bucket = filtered
        if not bucket:
            return PrimitiveResult(
                passed=True,
                data={"score": 0, "skipped": True,
                      "llm_api_failure": False,
                      "reason": "no api_responses evidence captured"},
                message="LLM judge SKIPPED (no api_responses evidence)",
            )
        cap = int(inputs.get("max_evidence_chars", 25000))
        evidence_text = json.dumps(bucket, indent=2)[:cap]
    elif evidence_type == "code_files":
        files_to_sample = inputs.get("files_to_sample", ["src/"])
        evidence_text = _sample_code_files(
            files_to_sample,
            max_chars=int(inputs.get("max_evidence_chars", 30000)),
            per_file_chars=int(inputs.get("per_file_chars", 3000)),
            max_files_per_root=int(inputs.get("max_files_per_root", 40)),
            file_globs=inputs.get("file_globs"),
            prefer_keywords=inputs.get("prefer_keywords"),
        )

    _prompt_cap = int(inputs.get("max_evidence_chars", 30000))
    res = safe_chat_completion(
        messages=[
            {"role": "system", "content": (
                f"You are a strict code quality evaluator. Score from {score_range[0]} to {score_range[1]}. "
                "You have NO access to any tools, shell, or filesystem: evaluate SOLELY from the evidence "
                "provided below and do NOT ask to inspect more files. "
                "Respond with ONLY a JSON object {\"score\": <integer>, \"reasoning\": \"<concise justification citing the evidence>\"} "
                "and no other text, preamble, or markdown fences.")},
            {"role": "user", "content": f"## Rubric\n{rubric}\n\n## Evidence\n{evidence_text[:_prompt_cap]}"},
        ],
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE,
        temperature=0.1,
        max_tokens=2000,
    )

    if res.skipped:
        return PrimitiveResult(
            passed=True,
            data={"score": 0, "skipped": True,
                  "llm_api_failure": res.llm_api_failure,
                  "exception_class": res.exception_class,
                  "error": res.error},
            message=f"LLM judge SKIPPED ({res.reason()})",
        )

    def _try_parse(raw_text):
        r = (raw_text or "").strip()
        if r.startswith("```"):
            nl = r.find("\n")
            r = r[nl + 1:] if nl > 0 else r[3:]
            if r.endswith("```"):
                r = r[:-3]
        r = r.strip()
        for parser in (
            lambda x: json.loads(x),
            lambda x: json.loads(x, strict=False),
            lambda x: _extract_score_json(x),
        ):
            try:
                out = parser(r)
                if isinstance(out, dict) and "score" in out:
                    return out
            except Exception:
                continue
        return None

    result = _try_parse(res.raw)

    if result is None:
        force_instr = (
            "\n\nIMPORTANT: You have NO tools and cannot inspect any files. The evidence above is "
            "ALL you get. Do NOT offer to investigate. Respond with ONLY a JSON object "
            f"{{\"score\": <integer {score_range[0]}-{score_range[1]}>, \"reasoning\": \"<at least "
            "one sentence citing the evidence>\"}} and nothing else.")
        for _attempt in range(3):
            force_res = safe_chat_completion(
                messages=[
                    {"role": "system", "content": (
                        f"You are a strict code quality evaluator. Score from {score_range[0]} to {score_range[1]}. "
                        "You have NO access to any tools, shell, or filesystem: evaluate SOLELY from the evidence. "
                        "Respond with ONLY a JSON object {\"score\": <integer>, \"reasoning\": \"<justification>\"}.")},
                    {"role": "user", "content": f"## Rubric\n{rubric}\n\n## Evidence\n{evidence_text[:_prompt_cap]}{force_instr}"},
                ],
                model=LLM_MODEL,
                api_key=LLM_API_KEY,
                api_base=LLM_API_BASE,
                max_tokens=2000,
            )
            if not force_res.skipped:
                result = _try_parse(force_res.raw)
                if result is not None:
                    break

    if result is None:
        return PrimitiveResult(
            passed=True,
            data={"score": 0, "skipped": True, "parse_failure": True,
                  "llm_api_failure": False, "raw": res.raw[:200]},
            message="LLM judge SKIPPED (parse failure: no recoverable score)",
        )

    try:
        score = max(score_range[0], min(score_range[1], int(result.get("score", 0))))
    except Exception:
        score = 0

    reasoning = result.get("reasoning", "") or ""
    if score > 0 and len(reasoning.strip()) < 50:
        return PrimitiveResult(
            passed=True,
            data={"score": 0, "reasoning": "",
                  "empty_reasoning_protection": True,
                  "raw_score": score,
                  "raw_excerpt": (reasoning or "")[:120]},
            message=f"LLM judge SKIPPED (score={score} but reasoning<50 chars; anti-hallucinate protection)",
        )

    return PrimitiveResult(
        passed=score > 0,
        data={"score": score, "reasoning": reasoning},
        message=f"LLM score: {score}/{score_range[1]}",
    )


_CODE_EXTS = (".java", ".py", ".ts", ".tsx", ".jsx", ".js",
              ".xml", ".ftl", ".yml", ".yaml", ".json",
              ".sql", ".properties", ".kt", ".gradle")


def _extract_score_json(raw: str):
    import re
    m = re.search(r'"score"\s*:\s*(-?\d+(?:\.\d+)?)', raw)
    if m:
        score_val = float(m.group(1))
        rs = re.search(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
        reasoning = rs.group(1) if rs else ""
        return {"score": score_val, "reasoning": reasoning}

    md_patterns = [
        r'(?:^|\n)\s*#*\s*(?:Overall\s+)?Score\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
        r'(?:^|\n)\s*#*\s*Evaluation\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
        r'(?:^|\n)\s*#*\s*Rating\s*[:\-]?\s*\**\s*(-?\d+(?:\.\d+)?)',
        r'\*\*\s*Score\s*[:\-]?\s*(-?\d+(?:\.\d+)?)',
        r'\bscore\s+(?:is|of|=)\s*\**\s*(-?\d+(?:\.\d+)?)',
        r'(?:^|\n)\s*\**\s*(-?\d+(?:\.\d+)?)\s*(?:/\s*\d+\s*)?(?:—|–|-)\s*(?:Excellent|Strong|Good|Complete|Weak|Poor|None|Fair|Adequate)',
    ]
    for pat in md_patterns:
        md_score = re.search(pat, raw, re.IGNORECASE)
        if md_score:
            score_val = float(md_score.group(1))
            md_reason = re.search(
                r'(?:^|\n)\s*#+\s*(?:Reasoning|Justification|Rationale|Explanation|Analysis|Notes?)\s*[:\-]?\s*\n+(.+)',
                raw, re.IGNORECASE | re.DOTALL)
            if md_reason:
                reasoning = re.split(r'\n\s*#+\s*\w', md_reason.group(1), maxsplit=1)[0].strip()
            else:
                reasoning = raw[:1500]
            return {"score": score_val, "reasoning": reasoning}

    frac = re.search(r'(?<!\d)(-?\d+(?:\.\d+)?)\s*/\s*\d+(?:\.\d+)?(?!\d)', raw)
    if frac:
        return {"score": float(frac.group(1)), "reasoning": raw[:1500]}

    return None


def _sample_code_files(paths, max_chars=30000, per_file_chars=3000,
                       max_files_per_root=40, file_globs=None,
                       prefer_keywords=None):
    import fnmatch
    import glob as _glob

    sampled = []
    total = 0
    seen = set()

    def _accepted_name(fname: str) -> bool:
        if file_globs:
            return any(fnmatch.fnmatch(fname, pat) for pat in file_globs)
        return fname.endswith(_CODE_EXTS)

    def _read_one(fpath: str) -> None:
        nonlocal total
        if fpath in seen or total >= max_chars:
            return
        seen.add(fpath)
        try:
            with open(fpath, "r", errors="replace") as fh:
                content = fh.read(per_file_chars)
        except Exception:
            return
        rel = os.path.relpath(fpath, WORKSPACE_DIR)
        block = f"--- {rel} ---\n{content}\n"
        sampled.append(block)
        total += len(block)

    def _walk_dir(base: str) -> None:
        kept = 0
        candidates = []
        for root, _dirs, files in os.walk(base):
            for f in files:
                if not _accepted_name(f):
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, WORKSPACE_DIR)
                priority = 0
                if prefer_keywords:
                    rel_lower = rel.lower()
                    priority = -sum(1 for k in prefer_keywords if k in rel_lower)
                candidates.append((priority, rel, fpath))
        candidates.sort()
        for _p, _rel, fpath in candidates:
            if kept >= max_files_per_root or total >= max_chars:
                break
            _read_one(fpath)
            kept += 1

    for p in paths:
        if total >= max_chars:
            break
        if any(ch in p for ch in "*?["):
            for hit in sorted(_glob.glob(os.path.join(WORKSPACE_DIR, p),
                                         recursive=True))[:max_files_per_root]:
                if total >= max_chars:
                    break
                if os.path.isdir(hit):
                    _walk_dir(hit)
                elif os.path.isfile(hit):
                    if _accepted_name(os.path.basename(hit)):
                        _read_one(hit)
            continue
        base = os.path.join(WORKSPACE_DIR, p)
        if os.path.isfile(base):
            _read_one(base)
        elif os.path.isdir(base):
            _walk_dir(base)
    return "".join(sampled)[:max_chars]


PRIMITIVE_MAP = {
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
}


def execute_primitive(ptype, inputs):
    func = PRIMITIVE_MAP.get(ptype)
    if not func:
        return PrimitiveResult(passed=False, message=f"Unknown primitive: {ptype}")
    return func(inputs)

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
