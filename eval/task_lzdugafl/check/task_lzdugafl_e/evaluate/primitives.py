import glob as glob_mod
import json
import os
import re
import time
from typing import Any

import requests

import config
import utils


class LLMJudgeUnavailable(BaseException):
    pass


def _resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(config.WORKSPACE_DIR, path)


# --------------- Table-prefix fairness helpers ---------------
TABLE_PREFIX = os.environ.get("TABLE_PREFIX", "kimai2_")
_TABLE_PREFIX_FALLBACKS = [TABLE_PREFIX, "kimai2_", "tt_", ""]
_known_prefixes = ("kimai2_", "tt_")

_known_tables_cache = None


def _list_db_tables():
    global _known_tables_cache
    if _known_tables_cache is None:
        try:
            rows = utils.db_query("SHOW TABLES")
            _known_tables_cache = [list(r.values())[0] for r in rows]
        except Exception:
            _known_tables_cache = []
    return _known_tables_cache


def _table_candidates(name: str):
    base = name
    for p in _known_prefixes:
        if name.startswith(p):
            base = name[len(p):]
            break
    cands = [name]
    for p in _TABLE_PREFIX_FALLBACKS:
        c = p + base
        if c not in cands:
            cands.append(c)
    return cands


def _resolve_existing_table(name: str) -> str:
    existing = set(_list_db_tables())
    for c in _table_candidates(name):
        if c in existing:
            return c
    return name


def _rewrite_sql_tables(sql: str) -> str:
    tok = re.compile(r"(?:kimai2_|tt_)[A-Za-z0-9_]+")

    def _repl(m):
        return _resolve_existing_table(m.group(0))

    try:
        return tok.sub(_repl, sql)
    except Exception:
        return sql


# --------------- File Primitives ---------------

def p01_file_exists(inputs: dict) -> dict:
    path = _resolve_path(inputs["path"])
    file_type = inputs.get("type", "file")
    if file_type == "directory":
        exists = os.path.isdir(path)
    else:
        exists = os.path.isfile(path)
    return {"passed": exists, "exists": exists, "path": path}


def p02_file_content_match(inputs: dict) -> dict:
    path = _resolve_path(inputs["path"])
    match_type = inputs.get("match_type", "contains")
    pattern = inputs["pattern"]

    if os.path.isdir(path):
        content = ""
        for root, _, files in os.walk(path):
            for f in files:
                if f.endswith(".php") or f.endswith(".py") or f.endswith(".json") or f.endswith(".yaml") or f.endswith(".yml"):
                    try:
                        with open(os.path.join(root, f), "r", errors="ignore") as fh:
                            content += fh.read() + "\n"
                    except Exception:
                        pass
    elif os.path.isfile(path):
        with open(path, "r", errors="ignore") as f:
            content = f.read()
    else:
        return {"passed": False, "matched": False, "error": f"Path not found: {path}"}

    if match_type == "contains":
        matched = pattern in content
        count = content.count(pattern)
    elif match_type == "regex":
        matches = re.findall(pattern, content, re.MULTILINE)
        matched = len(matches) > 0
        count = len(matches)
    else:
        return {"passed": False, "error": f"Unknown match_type: {match_type}"}

    return {"passed": matched, "matched": matched, "match_count": count}


def p03_file_count(inputs: dict) -> dict:
    base_dir = _resolve_path(inputs.get("base_dir", "."))
    pattern = inputs["glob"]
    min_expected = inputs.get("min_expected", 1)

    full_pattern = os.path.join(base_dir, pattern)
    files = glob_mod.glob(full_pattern, recursive=True)
    count = len(files)
    passed = count >= min_expected
    ratio = min(count / min_expected, 1.0) if min_expected > 0 else 1.0
    return {"passed": passed, "count": count, "min_expected": min_expected, "ratio": ratio, "files": [os.path.basename(f) for f in files[:20]]}


# --------------- HTTP Primitives ---------------

def p04_http_request(inputs: dict, context: dict = None) -> dict:
    method = inputs["method"].upper()
    path = inputs["path"]
    headers = dict(inputs.get("headers", {}))
    body = inputs.get("body")
    timeout = inputs.get("timeout", config.HTTP_TIMEOUT)

    if context and "auth_token" in context and "Authorization" not in headers and not inputs.get("skip_auth"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    if body is not None and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    if context and body:
        body = _resolve_placeholders(body, context)
    path = _resolve_placeholders_str(path, context) if context else path

    url = path if path.startswith("http") else config.APP_BASE_URL + path
    start = time.time()
    try:
        resp = requests.request(method, url, json=body if body else None, headers=headers, timeout=timeout, allow_redirects=False)
        elapsed = int((time.time() - start) * 1000)
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text[:2000]
        return {
            "passed": True,
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp_body,
            "response_time_ms": elapsed,
        }
    except Exception as e:
        return {"passed": False, "status_code": 0, "error": str(e), "body": None}


def p05_api_crud(inputs: dict, context: dict = None) -> dict:
    resource = inputs["resource"]
    create_body = _resolve_placeholders(inputs.get("create_body", {}), context)
    update_body = inputs.get("update_body", {})
    token = context.get("auth_token", "") if context else ""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    exp_create = inputs.get("expected_create_status", 200)
    exp_delete = inputs.get("expected_delete_status", 204)

    url = config.APP_BASE_URL + resource
    steps = {"create": False, "read": False, "update": False, "delete": False}
    entity_id = None

    try:
        r = requests.post(url, json=create_body, headers=headers, timeout=config.HTTP_TIMEOUT)
        if r.status_code in (200, 201, exp_create):
            steps["create"] = True
            try:
                entity_id = r.json().get("id")
            except Exception:
                pass

        if entity_id:
            r = requests.get(f"{url}/{entity_id}", headers=headers, timeout=config.HTTP_TIMEOUT)
            if r.status_code == 200:
                steps["read"] = True

            r = requests.patch(f"{url}/{entity_id}", json=update_body, headers=headers, timeout=config.HTTP_TIMEOUT)
            if r.status_code == 200:
                steps["update"] = True

            r = requests.delete(f"{url}/{entity_id}", headers=headers, timeout=config.HTTP_TIMEOUT)
            if r.status_code in (204, exp_delete):
                steps["delete"] = True
    except Exception:
        pass

    passed_count = sum(1 for v in steps.values() if v)
    return {"passed": passed_count == 4, "steps": steps, "steps_passed": passed_count, "steps_total": 4, "ratio": passed_count / 4, "entity_id": entity_id}


# --------------- JSON Primitives ---------------

def p06_json_schema_match(inputs: dict, prev_result: dict = None) -> dict:
    body = prev_result.get("body", {}) if prev_result else {}
    if body is None:
        body = {}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return {"passed": False, "error": "Body is not JSON"}

    required = inputs.get("required_fields", [])
    if isinstance(body, list):
        body = body[0] if body else {}
    if not isinstance(body, dict):
        return {"passed": False, "error": f"Body is not a dict: {type(body).__name__}"}

    present = [f for f in required if f in body]
    missing = [f for f in required if f not in body]
    ratio = len(present) / len(required) if required else 1.0
    return {"passed": len(missing) == 0, "present": present, "missing": missing, "ratio": ratio}


def p07_json_value_assert(inputs: dict, prev_result: dict = None) -> dict:
    body = prev_result.get("body", {}) if prev_result else {}
    if body is None:
        body = {}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return {"passed": False, "error": "Body is not JSON"}

    assertions = inputs.get("assertions", [])
    results = []
    for a in assertions:
        path_key = a["path"].lstrip("$.")

        if "expected_type" in a:
            actual = _get_nested(body, path_key)
            etype = a["expected_type"]
            type_map = {"integer": (int,), "number": (int, float), "string": (str,),
                        "boolean": (bool,), "array": (list,), "object": (dict,)}
            ok = isinstance(actual, type_map.get(etype, (object,))) and actual is not None
            results.append({"path": a["path"], "expected_type": etype, "actual": actual, "passed": ok})
            continue

        expected = a.get("expected")
        if expected is None and "expected" not in a:
            results.append({"path": a["path"], "expected": None, "actual": None, "passed": True})
            continue

        tolerance = a.get("tolerance", 0)
        actual = _get_nested(body, path_key)
        if tolerance and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            ok = abs(actual - expected) <= tolerance
        else:
            ok = actual == expected
        results.append({"path": a["path"], "expected": expected, "actual": actual, "passed": ok})

    all_passed = all(r["passed"] for r in results)
    return {"passed": all_passed, "results": results, "ratio": sum(1 for r in results if r["passed"]) / len(results) if results else 1.0}


# --------------- Database Primitives ---------------

def p08_db_query(inputs: dict) -> dict:
    sql = inputs["sql"]
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, context)
    except Exception:
        pass
    sql = _rewrite_sql_tables(sql)
    try:
        rows = utils.db_query(sql)
        expected = inputs.get("expected_result")
        match = True
        if expected and rows:
            for k, v in expected.items():
                if k.endswith("_gte"):
                    real_key = k[:-4]
                    actual_val = rows[0].get(real_key)
                    if actual_val is None or actual_val < v:
                        match = False
                elif k.endswith("_lte"):
                    real_key = k[:-4]
                    actual_val = rows[0].get(real_key)
                    if actual_val is None or actual_val > v:
                        match = False
                else:
                    if rows[0].get(k) != v:
                        match = False
        return {"passed": match, "rows": rows, "row_count": len(rows), "match": match}
    except Exception as e:
        return {"passed": False, "error": str(e)}


def p09_db_table_exists(inputs: dict) -> dict:
    tables = inputs["tables"]
    try:
        rows = utils.db_query("SHOW TABLES")
        existing_tables = set(list(r.values())[0] for r in rows)
        found = [t for t in tables if any(c in existing_tables for c in _table_candidates(t))]
        missing = [t for t in tables if not any(c in existing_tables for c in _table_candidates(t))]
        ratio = len(found) / len(tables) if tables else 1.0
        return {"passed": len(missing) == 0, "existing": found, "missing": missing, "found_count": len(found), "total_count": len(tables), "ratio": ratio}
    except Exception as e:
        return {"passed": False, "error": str(e), "ratio": 0}


def p10_db_column_check(inputs: dict) -> dict:
    table = _resolve_existing_table(inputs["table"])
    expected = inputs["expected_columns"]
    try:
        rows = utils.db_query(f"SHOW COLUMNS FROM `{table}`")
        actual_cols = [r["Field"] for r in rows]
        found = [c for c in expected if c in actual_cols]
        missing = [c for c in expected if c not in actual_cols]
        ratio = len(found) / len(expected) if expected else 1.0
        return {"passed": len(missing) == 0, "existing": found, "missing": missing, "found_count": len(found), "total_count": len(expected), "ratio": ratio}
    except Exception as e:
        return {"passed": False, "error": str(e), "ratio": 0}


def p11_db_index_check(inputs: dict) -> dict:
    table = _resolve_existing_table(inputs["table"])
    expected = inputs.get("expected_indexes", [])
    try:
        rows = utils.db_query(f"SHOW INDEX FROM `{table}`")
        index_cols = {}
        for r in rows:
            key = r.get("Key_name", "")
            col = r.get("Column_name", "")
            index_cols.setdefault(key, []).append(col)

        found = 0
        for exp in expected:
            exp_cols = exp["columns"]
            for idx_name, cols in index_cols.items():
                if exp_cols == cols[:len(exp_cols)]:
                    found += 1
                    break

        ratio = found / len(expected) if expected else 1.0
        return {"passed": found == len(expected), "found": found, "total": len(expected), "ratio": ratio}
    except Exception as e:
        return {"passed": False, "error": str(e), "ratio": 0}


# --------------- Docker / Auth Primitives ---------------

_token_cache = {}


def p12_docker_exec(inputs: dict, context: dict = None) -> dict:
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        if isinstance(context, dict):
            inputs = {k: (_incl_sub(v, context) if isinstance(v, str) else v)
                      for k, v in inputs.items()}
    except Exception:
        pass
    command = inputs["command"]
    container = inputs.get("container", config.APP_CONTAINER)
    expect_success = inputs.get("expect_success", True)
    expect_contains = inputs.get("expect_output_contains")

    result = utils.docker_exec(command, container)
    output = (result.stdout or '') + (result.stderr or '')
    success = result.returncode == 0

    passed = success if expect_success else not success
    if expect_contains and expect_contains not in output:
        passed = False

    return {"passed": passed, "returncode": result.returncode, "stdout": result.stdout[:2000], "stderr": result.stderr[:1000]}


def p13_auth_login(inputs: dict, context: dict = None) -> dict:
    role = inputs.get("role", "admin")

    if role in _token_cache:
        token = _token_cache[role]
        if context is not None:
            context["auth_token"] = token
        return {"passed": True, "token": token, "cached": True}

    user_info = config.TEST_USERS.get(role)
    if not user_info:
        return {"passed": False, "error": f"Unknown role: {role}"}

    username = user_info["username"]

    # Step 1: Try creating user via CLI (tolerate "already exists")
    for cmd_prefix in ["app", "kimai"]:
        utils.docker_exec(
            f"php bin/console {cmd_prefix}:user:create {username} {user_info['email']} {user_info['role']} {user_info['password']} 2>/dev/null"
        )

    # Step 2: Try API-based token endpoint
    try:
        resp = requests.post(
            config.API_BASE_URL + "/tokens",
            json={"username": username, "password": user_info["password"]},
            headers={"Content-Type": "application/json"},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            token = resp.json().get("token", "")
            if token:
                _token_cache[role] = token
                if context is not None:
                    context["auth_token"] = token
                return {"passed": True, "token": token, "method": "api_tokens"}
    except Exception:
        pass

    # Step 3: Create token directly in DB — preferred over legacy headers because
    try:
        import pymysql
        import secrets as _secrets
        conn = pymysql.connect(
            host=config.DB_HOST, port=config.DB_PORT,
            user=config.DB_USER, password=config.DB_PASSWORD,
            database=config.DB_NAME, cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
        )
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [list(r.values())[0] for r in cur.fetchall()]
            users_tbl = next((t for t in tables if t.endswith("_users") or t == "users" or t == "user"), None)
            token_tbl = next((t for t in tables if "access_token" in t), None)

            if not users_tbl or not token_tbl:
                conn.close()
                return {"passed": False, "error": f"Tables not found: users={users_tbl}, token={token_tbl}"}

            cur.execute(f"SELECT id FROM `{users_tbl}` WHERE username=%s", (username,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return {"passed": False, "error": f"User '{username}' not found in {users_tbl}"}
            user_id = row["id"]

            eval_token_name = f"eval_{role}"
            cur.execute(f"DELETE FROM `{token_tbl}` WHERE name=%s", (eval_token_name,))
            conn.commit()

            new_token = _secrets.token_hex(32)
            cur.execute(
                f"INSERT INTO `{token_tbl}` (user_id, token, name) VALUES (%s, %s, %s)",
                (user_id, new_token, eval_token_name),
            )
            conn.commit()
        conn.close()

        resp = requests.get(
            config.API_BASE_URL + "/ping",
            headers={"Authorization": f"Bearer {new_token}"},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            _token_cache[role] = new_token
            if context is not None:
                context["auth_token"] = new_token
            return {"passed": True, "token": new_token, "method": "db_direct"}
        else:
            return {"passed": False, "error": f"DB token created but API returned {resp.status_code}"}

    except Exception as e:
        pass

    # Step 4: Last resort — legacy X-AUTH-USER header (note: this only works for
    headers = {"X-AUTH-USER": username, "X-AUTH-TOKEN": user_info["password"]}
    try:
        resp = requests.get(config.API_BASE_URL + "/ping", headers=headers, timeout=config.HTTP_TIMEOUT)
        if resp.status_code == 200:
            _token_cache[role] = user_info["password"]
            if context is not None:
                context["auth_token"] = user_info["password"]
                context["auth_method"] = "legacy"
                context["auth_headers_" + role] = headers
            return {"passed": True, "token": user_info["password"], "method": "legacy_header"}
    except Exception:
        pass

    return {"passed": False, "error": "All auth methods failed"}


def p14_permission_check(inputs: dict, context: dict = None) -> dict:
    action = inputs["action"]
    expected_result = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status", 403)

    role = inputs.get("role", inputs.get("token"))
    headers = None
    if role is not None:
        login_result = p13_auth_login({"role": role}, context={})
        if not login_result["passed"]:
            return {"passed": False, "error": "Could not authenticate as " + str(role)}
        token = login_result["token"]
        if "auth_headers" in login_result:
            headers = login_result["auth_headers"]
    elif context and context.get("auth_token"):
        token = context["auth_token"]
    else:
        login_result = p13_auth_login({"role": "user"}, context={})
        if not login_result["passed"]:
            return {"passed": False, "error": "Could not authenticate"}
        token = login_result["token"]
    if headers is None:
        headers = {"Authorization": f"Bearer {token}"}

    parts = action.split(" ", 1)
    method = parts[0]
    path = _resolve_placeholders_str(parts[1], context) if context else parts[1]
    url = config.APP_BASE_URL + path

    try:
        resp = requests.request(method, url, headers=headers, timeout=config.HTTP_TIMEOUT)
        if expected_result == "denied":
            passed = resp.status_code in (403, 404, expected_status)
        else:
            passed = resp.status_code < 400
        return {"passed": passed, "status_code": resp.status_code, "expected_status": expected_status}
    except Exception as e:
        return {"passed": False, "error": str(e)}


def p15_status_code_assert(inputs: dict, prev_result: dict = None) -> dict:
    actual = prev_result.get("status_code", 0) if prev_result else 0
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

    if accepted:
        passed = actual in accepted
    else:
        passed = 200 <= actual < 400

    return {"passed": passed, "actual_status": actual,
            "expected": sorted(accepted) if accepted else "2xx/3xx",
            "message": f"Status: {actual} (expected {sorted(accepted) if accepted else '2xx/3xx'})"}


def p16_response_time_check(inputs: dict, prev_result: dict = None) -> dict:
    max_ms = inputs.get("max_ms", 500)
    actual = prev_result.get("response_time_ms", 0) if prev_result else 0
    return {"passed": actual <= max_ms, "actual_ms": actual, "max_ms": max_ms}


def _collect_php_evidence(files_to_sample: list, rubric: str = "",
                          max_files: int = 30, per_file: int = 3500,
                          total: int = 60000) -> str:
    import glob as _g
    SKIP = ("/tests/", "/test/", "/var/", "/vendor/", "/node_modules/", "/.git/")
    _kw = set(w.lower() for w in re.findall(r"[A-Za-z]{4,}", str(rubric) or ""))
    uniq = {}
    for fp in files_to_sample:
        full = _resolve_path(fp)
        if os.path.isdir(full):
            for m in _g.glob(os.path.join(full, "**", "*.php"), recursive=True):
                rel = os.path.relpath(m, full).replace(os.sep, "/").lower()
                if any(s in ("/" + rel) for s in SKIP):
                    continue
                uniq[m] = rel
        elif os.path.isfile(full):
            uniq[full] = os.path.basename(full).lower()
    from collections import defaultdict as _dd
    groups = _dd(list)
    for m, rel in uniq.items():
        top = rel.split("/", 1)[0]
        bn = rel.rsplit("/", 1)[-1]
        relevance = sum(2 for w in _kw if w in rel) + (1 if any(
            t in bn for t in ("voter", "service", "controller", "repository",
                              "security", "rate", "permission", "entity")) else 0)
        groups[top].append((-relevance, rel, m))
    for g in groups.values():
        g.sort()
    ordered = []
    while len(ordered) < max_files and any(groups.values()):
        for t in list(groups.keys()):
            if groups[t]:
                ordered.append(groups[t].pop(0)[2])
                if len(ordered) >= max_files:
                    break
    _base = getattr(config, "WORKSPACE_DIR", "") or ""
    parts = []
    for m in ordered:
        try:
            label = os.path.relpath(m, _base) if _base else m
        except Exception:
            label = m
        try:
            with open(m, "r", errors="ignore") as fh:
                parts.append(f"\n--- {label} ---\n" + fh.read()[:per_file])
        except Exception:
            pass
    return "".join(parts)[:total]


def p17_llm_judge(inputs: dict, prev_result: dict = None, context: dict = None) -> dict:
    score_range = inputs.get("score_range", [0, 5])
    if getattr(config, "SKIP_LLM_JUDGE", False):
        return {"passed": False, "skipped": True, "llm_api_failure": False,
                "score": 0, "max_score": score_range[1],
                "reason": "LLM judge skipped: SKIP_LLM_JUDGE is set"}
    if not config.LLM_API_KEY:
        return {"passed": False, "skipped": True, "llm_api_failure": True,
                "score": 0, "max_score": score_range[1],
                "reason": "LLM judge skipped: LLM_API_KEY is unset"}

    rubric = inputs.get("rubric_prompt", "")
    evidence_type = inputs.get("evidence_type", "")
    evidence = ""
    ctx = context or {}

    if evidence_type in ("rendered_dom", "screenshot_dom"):
        dom = ctx.get("rendered_dom") or ctx.get("last_body") or ""
        if not dom and isinstance(prev_result, dict):
            dom = (prev_result.get("rendered_dom") or prev_result.get("html")
                   or prev_result.get("body") or "")
        if isinstance(dom, bytes):
            dom = dom.decode("utf-8", "replace")
        evidence = dom[:24000] if isinstance(dom, str) else ""
    elif evidence_type in ("http_response_html", "http_response_body", "api_response"):
        body = ""
        if isinstance(prev_result, dict):
            body = prev_result.get("body", "")
        if not body:
            lr = ctx.get("last_response") or {}
            body = lr.get("body", "") if isinstance(lr, dict) else ""
        evidence = body[:8000] if isinstance(body, str) else json.dumps(body)[:8000]
    elif evidence_type == "code_files":
        evidence = _collect_php_evidence(inputs.get("files_to_sample", []), rubric)

    if not (evidence or "").strip():
        return {"passed": False, "score": 0, "max_score": score_range[1],
                "reason": f"no {evidence_type or 'evidence'} captured"}

    prompt = f"""You are an expert code reviewer. Score the following evidence on a scale of {score_range[0]} to {score_range[1]}.

Rubric: {rubric}

Evidence:
{evidence[:20000]}

Respond with ONLY a JSON object: {{"score": <number>, "reason": "<brief explanation>"}}"""

    from _llm_judge_safe import safe_chat_completion

    def _robust_judge_json(_raw):
        import json as _j, re as _re
        _s = (_raw or "").strip()
        if _s.startswith("```"):
            _s = _re.sub(r"^```[a-zA-Z0-9]*\s*", "", _s)
            _s = _re.sub(r"\s*```$", "", _s).strip()
        try:
            _v = _j.loads(_s)
            if isinstance(_v, dict):
                return _v
            if isinstance(_v, (int, float)):
                return {"score": float(_v)}
        except Exception:
            pass
        _i = _s.find("{")
        if _i != -1:
            _d = 0
            for _k in range(_i, len(_s)):
                if _s[_k] == "{":
                    _d += 1
                elif _s[_k] == "}":
                    _d -= 1
                    if _d == 0:
                        try:
                            return _j.loads(_s[_i:_k + 1])
                        except Exception:
                            break
        _m = _re.search(r'"?score"?\s*[:=]\s*(-?\d+(?:\.\d+)?)', _s, _re.I)
        if _m:
            _o = {"score": float(_m.group(1))}
            _rm = _re.search(r'"?reason(?:ing)?"?\s*[:=]\s*"([^"]*)"', _s, _re.I)
            if _rm:
                _o["reason"] = _rm.group(1)
                _o["reasoning"] = _rm.group(1)
            return _o
        _m2 = _re.search(r"-?\d+", _s)
        if _m2:
            return {"score": float(_m2.group())}
        raise ValueError("no JSON/score in LLM reply")

    _RETRIES = 6
    _last = ""
    for _attempt in range(_RETRIES):
        res = safe_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE,
            temperature=0,
        )
        if res.skipped:
            _last = f"api failure: {res.exception_class or ''} {res.error or ''}".strip()
            time.sleep(min(2.0 * (_attempt + 1), 8.0))
            continue
        try:
            result = _robust_judge_json(res.raw)
            return {"passed": True, "score": result.get("score", 0),
                    "max_score": score_range[1], "reason": result.get("reason", "")}
        except Exception as e:
            _last = f"parse error: {e}; raw={(res.raw or '')[:120]!r}"
            time.sleep(min(1.5 * (_attempt + 1), 6.0))
            continue

    return {"passed": False, "skipped": True, "llm_api_failure": True,
            "score": 0, "max_score": score_range[1],
            "reason": f"LLM judge unavailable after {_RETRIES} attempts (last: {_last})"}


# --------------- Helpers ---------------

def _get_nested(obj: Any, path: str) -> Any:
    if obj is None:
        return None
    parts = re.split(r'\.|\[(\d+)\]', path)
    parts = [p for p in parts if p is not None and p != '' and p != '$']
    if not parts:
        return obj
    for key in parts:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list):
            try:
                idx = int(key)
                obj = obj[idx] if idx < len(obj) else None
            except (ValueError, IndexError):
                return None
        else:
            return None
    return obj


def _resolve_placeholders(obj: Any, context: dict) -> Any:
    if context is None:
        return obj
    if isinstance(obj, str):
        return _resolve_placeholders_str(obj, context)
    if isinstance(obj, dict):
        return {k: _resolve_placeholders(v, context) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_placeholders(v, context) for v in obj]
    return obj


def _resolve_placeholders_str(s: str, context: dict) -> Any:
    if context is None:
        return s
    import re as _re
    def replacer(m):
        key = m.group(1)
        val = context.get(key, m.group(0))
        return str(val) if not isinstance(val, str) else val

    result = _re.sub(r"\{\{(\w+)\}\}", replacer, s)
    if result != s and result.isdigit():
        return int(result)
    return result
