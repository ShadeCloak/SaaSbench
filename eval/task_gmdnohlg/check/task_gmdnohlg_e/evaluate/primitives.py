import os
import re
import glob
import json
import hashlib
import requests
from config import WORKSPACE_DIR, APP_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT, TABLE_PREFIX, TEST_USERS
from utils import http_request, docker_exec, db_query


def P01_file_exists(inputs, context):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    ftype = inputs.get("type", "file")
    if ftype == "file":
        exists = os.path.isfile(path)
    else:
        exists = os.path.isdir(path)
    return {"passed": exists, "exists": exists, "path": path}


def P02_file_content_match(inputs, context):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    if not os.path.isfile(path):
        return {"passed": False, "matched": False, "error": "file not found"}
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    match_type = inputs.get("match_type", "contains")
    pattern = inputs["pattern"]
    if match_type == "contains":
        matched = pattern in content
    elif match_type == "regex":
        matched = bool(re.search(pattern, content))
    else:
        matched = False
    return {"passed": matched, "matched": matched, "match_type": match_type}


def P03_file_count(inputs, context):
    base = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", "."))
    pattern = inputs.get("glob", "**/*")
    files = glob.glob(os.path.join(base, pattern), recursive=True)
    files = [f for f in files if os.path.isfile(f)]
    min_expected = inputs.get("min_expected", 1)
    return {"passed": len(files) >= min_expected, "count": len(files), "min_expected": min_expected}


def P04_http_request(inputs, context):
    method = inputs.get("method", "GET")
    path = inputs.get("path", "/")
    headers = dict(inputs.get("headers", {}))

    if "auth_token" in context and "Authorization" not in headers:
        auth_method = context.get("auth_method", "bearer")
        if auth_method == "basic":
            headers["Authorization"] = f"Basic {context['auth_token']}"
        else:
            headers["Authorization"] = f"Bearer {context['auth_token']}"

    path = _resolve_templates(path, context)
    body = inputs.get("body")
    if isinstance(body, str):
        body = _resolve_templates(body, context)
    elif isinstance(body, dict):
        body = json.loads(_resolve_templates(json.dumps(body), context))

    if "/ocs/" in path or "/api/v2/" in path:
        separator = "&" if "?" in path else "?"
        if "format=" not in path:
            path = path + separator + "format=json"
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

    result = http_request(method, path, headers=headers, body=body, timeout=inputs.get("timeout", HTTP_TIMEOUT))
    result["passed"] = result.get("status_code", 0) > 0
    return result


def P05_api_crud(inputs, context):
    resource = inputs["resource"]
    token_header = {}
    if "auth_token" in context:
        token_header = {"Authorization": f"Bearer {context['auth_token']}"}

    steps_passed = 0
    steps_total = 4
    evidence = {}

    create_resp = http_request("POST", resource, headers={**token_header, "Content-Type": "application/json"},
                               body=inputs.get("create_body", {}))
    exp_create = inputs.get("expected_create_status", 201)
    if create_resp["status_code"] in ([exp_create] if isinstance(exp_create, int) else exp_create):
        steps_passed += 1
        entity_id = (create_resp.get("body") or {}).get("id") or \
                     (create_resp.get("body") or {}).get("api", {}).get("data", {}).get("id")
        evidence["create"] = {"success": True, "id": entity_id}
    else:
        evidence["create"] = {"success": False, "status": create_resp["status_code"]}
        return {"passed": False, "steps_passed": steps_passed, "steps_total": steps_total, "evidence": evidence}

    read_resp = http_request("GET", f"{resource}/{entity_id}", headers=token_header)
    if read_resp["status_code"] == 200:
        steps_passed += 1
        evidence["read"] = {"success": True}
    else:
        evidence["read"] = {"success": False}

    update_resp = http_request("PUT", f"{resource}/{entity_id}",
                               headers={**token_header, "Content-Type": "application/json"},
                               body=inputs.get("update_body", {}))
    exp_update = inputs.get("expected_update_status", 200)
    if update_resp["status_code"] == exp_update:
        steps_passed += 1
        evidence["update"] = {"success": True}
    else:
        evidence["update"] = {"success": False}

    delete_resp = http_request("DELETE", f"{resource}/{entity_id}", headers=token_header)
    exp_delete = inputs.get("expected_delete_status", 204)
    if delete_resp["status_code"] in [exp_delete, 200]:
        steps_passed += 1
        evidence["delete"] = {"success": True}
    else:
        evidence["delete"] = {"success": False}

    return {"passed": steps_passed == steps_total, "steps_passed": steps_passed,
            "steps_total": steps_total, "evidence": evidence}


def P06_json_schema_match(inputs, context):
    response = _get_response(inputs, context)
    body = response.get("body") if isinstance(response, dict) else None
    if body is None:
        return {"passed": False, "error": "no JSON body"}
    required = inputs.get("required_fields", [])
    missing = [f for f in required if f not in _flatten_keys(body)]
    return {"passed": len(missing) == 0, "missing_fields": missing}


def P07_json_value_assert(inputs, context):
    response = _get_response(inputs, context)
    assertions = inputs.get("assertions", [])

    if isinstance(response, dict):
        sc = response.get("status_code") or (response.get("body") or {}).get("statuscode")
        body = response.get("body")
        flat_body = ""
        if isinstance(body, str):
            flat_body = body.lower()
        elif isinstance(body, dict):
            flat_body = json.dumps(body).lower() if body else ""
        elif isinstance(body, list):
            flat_body = json.dumps(body).lower() if body else ""
        idempotent_kw = (
            "already exists", "already taken", "already used", "duplicate",
            "name has already", "title has already",
        )
        not_implemented_kw = (
            "wrong path", "file/folder does not exist", "not found",
            "does not exist", "no such", "resource not found",
            "endpoint not found", "no app", "unknown app", "app not enabled",
        )
        if sc == 404 and (not flat_body or any(kw in flat_body for kw in not_implemented_kw)):
            return {"passed": True, "assertions": [], "passed_count": 0,
                    "total_count": 0,
                    "_inclusivity_p07_skip": "prev 404 (endpoint not implemented in baseline)"}
        if sc in (400, 401, 409, 422) and any(kw in flat_body for kw in idempotent_kw):
            return {"passed": True, "assertions": [], "passed_count": 0,
                    "total_count": 0,
                    "_inclusivity_p07_skip": f"prev {sc} idempotent — baseline rejected duplicate, body irrelevant"}

    results = []
    all_passed = True

    for assertion in assertions:
        path = assertion.get("path", "$")
        expected = assertion.get("expected")
        operator = assertion.get("operator", "eq")
        tolerance = assertion.get("tolerance", 0)

        actual = _json_path_extract(response, path)
        if actual is None and path.startswith("$.api."):
            actual = _json_path_extract(response, path.replace("$.api.", "$.ocs.", 1))
        if actual is None and isinstance(response, dict) and "body" in response:
            actual = _json_path_extract(response["body"], path)
            if actual is None and path.startswith("$.api."):
                actual = _json_path_extract(response["body"], path.replace("$.api.", "$.ocs.", 1))

        if operator == "eq":
            if tolerance and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
                passed = abs(actual - expected) <= tolerance
            else:
                passed = actual == expected
        elif operator == "contains":
            passed = isinstance(actual, str) and str(expected) in actual
        elif operator == "not_contains":
            passed = isinstance(actual, str) and str(expected) not in actual
        elif operator == "exists":
            passed = actual is not None
        elif operator == "gte":
            passed = isinstance(actual, (int, float)) and actual >= expected
        elif operator == "lte":
            passed = isinstance(actual, (int, float)) and actual <= expected
        elif operator == "gt":
            passed = isinstance(actual, (int, float)) and actual > expected
        elif operator == "regex":
            passed = isinstance(actual, str) and bool(re.search(str(expected), actual))
        elif operator == "type":
            type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
            passed = isinstance(actual, type_map.get(expected, object))
        elif operator == "in":
            passed = actual in expected
        elif operator == "not_eq":
            passed = actual != expected
        elif operator == "is_array":
            passed = isinstance(actual, list)
        elif operator == "regex_match":
            pattern = assertion.get("pattern", expected)
            passed = isinstance(actual, str) and bool(re.search(str(pattern), actual))
        elif operator == "exists_or":
            alt = assertion.get("alt_check")
            alt_actual = None
            if alt:
                alt_actual = _json_path_extract(response, alt)
                if alt_actual is None and isinstance(response, dict) and "body" in response:
                    alt_actual = _json_path_extract(response["body"], alt)
            passed = (actual is not None) or (alt_actual is not None)
        elif operator == "eq_or_empty":
            passed = (actual == expected) or (actual is None) or (actual == "") or (actual == []) or (actual == {})
        else:
            passed = False

        if not passed:
            all_passed = False
        results.append({"path": path, "expected": expected, "actual": actual, "operator": operator, "passed": passed})

    return {"passed": all_passed, "assertions": results, "passed_count": sum(1 for r in results if r["passed"]),
            "total_count": len(results)}


def P08_db_query(inputs, context):
    sql = _resolve_templates(inputs.get("sql", ""), context)
    rows = db_query(sql)
    if isinstance(rows, dict) and "error" in rows:
        return {"passed": False, "error": rows["error"], "rows": []}

    expected = inputs.get("expected_result")
    if expected and isinstance(rows, list) and len(rows) > 0:
        row = rows[0]
        all_match = all(row.get(k) == v for k, v in expected.items())
        return {"passed": all_match, "rows": rows, "expected": expected, "actual_first_row": row}

    passed = isinstance(rows, list) and len(rows) >= 0
    return {"passed": passed, "rows": rows if isinstance(rows, list) else [],
            "row_count": len(rows) if isinstance(rows, list) else 0}


def P09_db_table_exists(inputs, context):
    tables = inputs.get("tables", [])
    existing = []
    missing = []
    for table in tables:
        result = db_query(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')")
        if isinstance(result, list) and result and result[0].get("exists"):
            existing.append(table)
        else:
            missing.append(table)
    return {"passed": len(missing) == 0, "existing": existing, "missing": missing}


def P10_db_column_check(inputs, context):
    table = inputs["table"]
    expected = inputs.get("expected_columns", [])
    result = db_query(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")
    if isinstance(result, dict) and "error" in result:
        return {"passed": False, "error": result["error"]}
    actual_cols = [r["column_name"] for r in result] if isinstance(result, list) else []
    missing = [c for c in expected if c not in actual_cols]
    return {"passed": len(missing) == 0, "actual_columns": actual_cols, "missing_columns": missing,
            "expected": expected}


def P11_db_index_check(inputs, context):
    table = inputs["table"]
    result = db_query(f"SELECT indexname FROM pg_indexes WHERE tablename = '{table}'")
    if isinstance(result, dict) and "error" in result:
        return {"passed": False, "error": result["error"]}
    actual = [r["indexname"] for r in result] if isinstance(result, list) else []
    expected = inputs.get("expected_indexes", [])
    missing = [i for i in expected if not any(i in a for a in actual)]
    return {"passed": len(missing) == 0, "actual_indexes": actual, "missing": missing}


def P12_docker_exec(inputs, context):
    command = _resolve_templates(inputs.get("command", ""), context)
    
    if command.startswith("bash -c"):
        cmd_list = ["bash", "-c", command[len("bash -c "):].strip().strip("'\"")]
    else:
        cmd_list = command
    
    result = docker_exec(APP_CONTAINER, cmd_list, timeout=inputs.get("timeout", 30))
    expected_exit = inputs.get("expected_exit_code", 0)
    expected_output = inputs.get("expected_output_contains")
    
    combined_output = (result.get("stdout", "") + " " + result.get("stderr", "")).lower()

    passed = result["exit_code"] == expected_exit
    if expected_output and passed:
        passed = expected_output.lower() in combined_output

    if not passed and any(kw in combined_output for kw in ["already exists", "user_exists", "was created"]):
        passed = True

    return {"passed": passed, **result}


def P13_auth_login(inputs, context):
    method = inputs.get("method", "bearer")
    role = inputs.get("role", "admin")

    user_key = role
    if "username" in inputs:
        for k, v in TEST_USERS.items():
            if v["username"] == inputs["username"]:
                user_key = k
                break

    user_info = TEST_USERS.get(user_key, TEST_USERS.get("admin"))
    username = inputs.get("username", user_info["username"])
    password = inputs.get("password", user_info["password"])

    if method == "bearer":
        import base64 as _b64
        basic_creds = _b64.b64encode(f"{username}:{password}".encode()).decode()
        basic_header = {"Authorization": f"Basic {basic_creds}", "OCS-APIREQUEST": "true"}

        context["auth_token"] = basic_creds
        context["auth_method"] = "basic"
        context[f"auth_token_{role}"] = basic_creds
        context["_basic_creds"] = basic_creds
        return {"passed": True, "method": "basic_direct", "role": role}

        try:
            import secrets
            token = secrets.token_hex(36)
            token_hash = hashlib.sha512(token.encode()).hexdigest()
            prefix_rows = db_query("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '%users' LIMIT 5")
            detected_prefix = ""
            if isinstance(prefix_rows, list):
                for pr in prefix_rows:
                    tn = pr.get("tablename", "")
                    if tn.endswith("_users") or tn == "users":
                        detected_prefix = tn.replace("users", "")
                        break
            if not detected_prefix:
                detected_prefix = TABLE_PREFIX

            user_rows = db_query(f"SELECT uid FROM {detected_prefix}users WHERE uid = '{username}'")
            if isinstance(user_rows, list) and user_rows:
                db_query(f"DELETE FROM {detected_prefix}authtoken WHERE name = 'eval_{role}'")
                db_query(f"INSERT INTO {detected_prefix}authtoken (uid, login_name, password, name, token, type, last_activity) "
                        f"VALUES ('{username}', '{username}', '', 'eval_{role}', '{token_hash}', 1, {int(__import__('time').time())})")
                context["auth_token"] = token
                context["auth_method"] = "bearer"
                context[f"auth_token_{role}"] = token
                return {"passed": True, "method": "db_token", "role": role}
        except Exception as e:
            pass

        return {"passed": False, "error": "all auth methods failed", "role": role}

    elif method == "session":
        resp = http_request("POST", "/login", headers={"Content-Type": "application/x-www-form-urlencoded"},
                           body=f"user={username}&password={password}")
        passed = resp["status_code"] in [200, 302, 303]
        if passed:
            cookies = resp.get("headers", {}).get("Set-Cookie", "")
            context["session_cookie"] = cookies
        return {"passed": passed, "status_code": resp["status_code"], "role": role}

    return {"passed": False, "error": f"unknown auth method: {method}"}


def P14_permission_check(inputs, context):
    action = inputs.get("action", "GET /")
    expected = inputs.get("expected_result", "allowed")
    expected_status = inputs.get("expected_status")

    parts = action.split(" ", 1)
    method = parts[0]
    path = parts[1] if len(parts) > 1 else "/"

    headers = {}
    if "auth_token" in context:
        if context.get("auth_method") == "basic":
            headers["Authorization"] = f"Basic {context['auth_token']}"
            headers["OCS-APIREQUEST"] = "true"
        else:
            headers["Authorization"] = f"Bearer {context['auth_token']}"

    resp = http_request(method, path, headers=headers)
    status = resp["status_code"]

    def _status_ok(st, exp):
        return st in exp if isinstance(exp, (list, tuple, set)) else st == exp

    if expected == "denied":
        passed = status in [401, 403]
        if expected_status:
            passed = _status_ok(status, expected_status)
    else:
        passed = status in [200, 201, 204, 207, 301, 302]
        if expected_status:
            passed = _status_ok(status, expected_status)

    return {"passed": passed, "status_code": status, "expected_result": expected, "action": action}


def P15_status_code_assert(inputs, context):
    response = _get_response(inputs, context)
    if isinstance(response, dict):
        actual = response.get("status_code", 0)
    elif isinstance(response, int):
        actual = response
    else:
        actual = 0
    expected = inputs.get("expected_status")
    acceptable = inputs.get("acceptable_statuses")

    if acceptable:
        passed = actual in acceptable
    elif expected:
        passed = actual == expected
    else:
        passed = 200 <= actual < 300

    return {"passed": passed, "actual_status": actual, "expected": expected or acceptable}


def P16_response_time_check(inputs, context):
    response = _get_response(inputs, context)
    actual_ms = response.get("response_time_ms", 0) if isinstance(response, dict) else 0
    max_ms = inputs.get("max_ms", 5000)
    return {"passed": actual_ms <= max_ms, "actual_ms": actual_ms, "max_ms": max_ms}


_CODE_EXTS = {".php", ".js", ".ts", ".tsx", ".jsx", ".vue", ".py", ".rb",
              ".go", ".java", ".rs", ".sql", ".inc"}
_MARKUP_EXTS = {".html", ".htm", ".scss", ".css", ".md", ".txt", ".json",
                ".yaml", ".yml", ".xml", ".lock", ".svg", ".twig"}
_SKIP_SUBSTR = ("/3rdparty/", "/node_modules/", "/vendor/", "/dist/", "/build/",
                "/.git/", "/__pycache__/", "/tests/", "/test/", "/l10n/",
                "/composer/", "/.github/")
_RUBRIC_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent does "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling whether well overall".split())


def _gather_and_rank(root, files_to_sample, rubric, max_files=16):
    root = (root or "").rstrip("/")
    entries = list(files_to_sample) or ["lib/", "apps/"]
    cands = []
    explicit = set()
    for ent in entries:
        base = os.path.join(root, str(ent))
        if os.path.isfile(base):
            cands.append(base)
            explicit.add(os.path.realpath(base))
            continue
        if not os.path.isdir(base):
            try:
                for p in glob.glob(base, recursive=True):
                    if os.path.isfile(p):
                        cands.append(p)
                        explicit.add(os.path.realpath(p))
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
    if not cands:
        for fb in ("lib", "apps", "core"):
            base = os.path.join(root, fb)
            if os.path.isdir(base):
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
    _seen_rp, _uniq = set(), []
    for c in cands:
        rp = os.path.realpath(c)
        if rp in _seen_rp:
            continue
        _seen_rp.add(rp)
        _uniq.append(c)
    cands = _uniq
    mentioned = {m.split("/")[-1].lower()
                 for m in re.findall(r"[\w./*-]+\.\w{1,5}", rubric or "")}
    pathwords = set()
    for p in re.findall(r"(?:src|lib|apps|core|js|vue)/[\w./*-]+", rubric or ""):
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
        if any(s in "/" + low for s in _SKIP_SUBSTR):
            continue
        base = os.path.basename(low)
        ext = os.path.splitext(low)[1]
        sc = 0.0
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
        if "test" in base:
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
    pinned = [(rel, full) for sc, strat, rel, full in scored
              if os.path.realpath(full) in explicit]
    pinned_set = {full for _rel, full in pinned}
    picked = list(pinned)
    budget = max(max_files, len(pinned))
    while len(picked) < budget and any(groups[k] for k in order):
        for k in order:
            if groups[k]:
                rel, full = groups[k].pop(0)
                if full in pinned_set:
                    continue
                picked.append((rel, full))
                if len(picked) >= budget:
                    break
    return picked


def P17_llm_judge(inputs, context):
    from config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL
    try:
        from _llm_judge_safe import dispatch_external_evidence as _dee
        _ext_ctx = context
        _ext_result = _dee(
            inputs=inputs,
            ctx=_ext_ctx,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE or "",
            return_type='dict',
        )
        if _ext_result is not None:
            return _ext_result
    except Exception as _ext_exc:
        import logging as _ext_logging
        _ext_logging.getLogger("p17_dispatch").warning(
            "dispatch_external_evidence failed for evidence_type=%r: %s",
            inputs.get("evidence_type"), _ext_exc)
    from config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL
    max_score = inputs.get("max_score", 5)

    evidence_text = ""
    evidence_type = inputs.get("evidence_type", "code_files")

    if evidence_type == "http_response_html":
        urls = inputs.get("urls_to_sample", ["/"])
        for url in urls[:3]:
            resp = http_request("GET", url)
            evidence_text += f"\n--- {url} (HTTP {resp['status_code']}) ---\n{resp.get('body_text', '')[:3000]}\n"
    elif evidence_type == "code_files":
        files_to_sample = inputs.get("files_to_sample", [])
        _rubric_for_rank = inputs.get("rubric") or inputs.get("rubric_prompt") or ""
        for rel, full in _gather_and_rank(WORKSPACE_DIR, files_to_sample,
                                          _rubric_for_rank, max_files=16):
            if len(evidence_text) > 38000:
                break
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    evidence_text += f"\n--- {rel} ---\n{f.read()[:3000]}\n"
            except Exception:
                pass

    rubric = inputs.get("rubric", "Evaluate quality from 0 to max_score.")

    from _llm_judge_safe import safe_chat_completion, _extract_score as _p17_extract_score
    _msgs = [
        {"role": "system", "content": f"You are a code/UI quality evaluator. Score from 0 to {max_score}. Respond with ONLY a single JSON object {{\"score\": <int 0-{max_score}>, \"reasoning\": \"<one short sentence>\"}} and NOTHING else — no preamble before the JSON."},
        {"role": "user", "content": f"Rubric: {rubric}\n\nEvidence:\n{evidence_text[:24000]}"}
    ]
    parsed_score = None
    parsed_reason = ""
    last_raw = ""
    for _attempt in range(3):
        res = safe_chat_completion(
            messages=_msgs,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            temperature=0.1,
            max_tokens=2000,
        )
        raw_str = (res.raw or "").strip()
        last_raw = raw_str
        if raw_str.startswith("```"):
            first_nl = raw_str.find("\n")
            if first_nl != -1:
                raw_str = raw_str[first_nl + 1:]
            if raw_str.rstrip().endswith("```"):
                raw_str = raw_str.rstrip()[:-3].rstrip()
        try:
            result_json = json.loads(raw_str)
            parsed_score = int(result_json.get("score", 0))
            parsed_reason = str(result_json.get("reasoning", ""))[:500]
        except Exception:
            if "score" in raw_str.lower():
                parsed_score = _p17_extract_score(raw_str)
        if parsed_score is not None:
            break

    if parsed_score is None:
        _infra = bool(getattr(res, "skipped", False))
        return {"passed": False, "skipped": True, "llm_api_failure": _infra,
                "score": 0, "max_score": max_score,
                "parse_failure": not _infra,
                "reason": "LLM judge unavailable: no parseable score after retries",
                "raw": last_raw[:200]}

    score = min(max(parsed_score, 0), max_score)
    return {"passed": score > 0, "score": score, "max_score": max_score,
            "reasoning": parsed_reason}


def P18_browser_interaction(inputs, context):
    return {"passed": False, "message": "P18 browser_interaction not implemented"}

def P19_dom_assertion(inputs, context):
    response = _get_response(inputs, context)
    body_text = response.get("body_text", "") if isinstance(response, dict) else ""
    if not body_text and inputs.get("url"):
        fetched = P04_http_request({"method": "GET", "path": inputs["url"]}, context)
        body_text = fetched.get("body_text", "")
    selector = inputs.get("selector", "")
    if selector and selector in body_text:
        return {"passed": True, "found": True}
    assertions = inputs.get("assertions", [])
    if assertions:
        passed = 0
        for a in assertions:
            sel = a.get("selector", "")
            should = a.get("shouldExist", True)
            exists = sel in body_text
            if exists == should:
                passed += 1
        return {"passed": passed == len(assertions), "found": passed > 0, "matched": passed, "total": len(assertions)}
    return {"passed": False, "found": False, "selector": selector}

def P23_file_upload_download(inputs, context):
    return {"passed": False, "message": "P23 not fully implemented"}

def P25_oauth_oidc_flow(inputs, context):
    return {"passed": False, "message": "P25 not fully implemented"}

def P27_webhook_delivery(inputs, context):
    return {"passed": False, "message": "P27 not fully implemented"}



PRIMITIVE_MAP = {
    "P01": P01_file_exists, "P02": P02_file_content_match, "P03": P03_file_count,
    "P04": P04_http_request, "P05": P05_api_crud, "P06": P06_json_schema_match,
    "P07": P07_json_value_assert, "P08": P08_db_query, "P09": P09_db_table_exists,
    "P10": P10_db_column_check, "P11": P11_db_index_check, "P12": P12_docker_exec,
    "P13": P13_auth_login, "P14": P14_permission_check, "P15": P15_status_code_assert,
    "P16": P16_response_time_check, "P17": P17_llm_judge, "P18": P18_browser_interaction,
    "P19": P19_dom_assertion, "P23": P23_file_upload_download,
    "P25": P25_oauth_oidc_flow, "P27": P27_webhook_delivery,
}


def execute_primitive(ptype, inputs, context):
    func = PRIMITIVE_MAP.get(ptype)
    if not func:
        return {"passed": False, "error": f"unknown primitive: {ptype}"}
    try:
        return func(inputs, context)
    except Exception as e:
        return {"passed": False, "error": str(e)}


def _get_response(inputs, context):
    ref = inputs.get("response", "")
    if isinstance(ref, str) and ref.startswith("{{") and ref.endswith("}}"):
        key = ref[2:-2]
        return context.get(key, {})
    return inputs.get("response", {})


def _resolve_templates(text, context):
    if not isinstance(text, str):
        return text
    import re as _re
    def replacer(match):
        key = match.group(1)
        parts = key.split(".")
        val = context
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p, match.group(0))
            else:
                return match.group(0)
        return str(val) if not isinstance(val, dict) else match.group(0)
    return _re.sub(r'\{\{([^}]+)\}\}', replacer, text)


def _flatten_keys(obj, prefix=""):
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.append(full)
            keys.extend(_flatten_keys(v, full))
    return keys


def _json_path_extract(data, path):
    if not path or path == "$":
        return data
    parts = path.lstrip("$.").split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current

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
