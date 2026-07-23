import glob as globmod
import json
import os
import re
from typing import Any

import config
import utils


def p01_file_exists(inputs: dict, ctx: utils.EvalContext) -> dict:
    path = os.path.join(config.WORKSPACE_PATH, inputs["path"])
    result = utils.docker_exec(f"test -e {path} && echo EXISTS || echo MISSING")
    exists = "EXISTS" in result["stdout"]
    return {"passed": exists, "exists": exists, "path": path}


def p02_file_content_match(inputs: dict, ctx: utils.EvalContext) -> dict:
    path = os.path.join(config.WORKSPACE_PATH, inputs["path"])
    result = utils.docker_exec(f"cat {path} 2>/dev/null")
    content = result["stdout"]
    if inputs.get("match_type") == "regex":
        matches = re.findall(inputs["pattern"], content)
    else:
        matches = [m for m in [inputs["pattern"]] if m in content]
    return {"passed": len(matches) > 0, "matched": len(matches) > 0, "match_count": len(matches)}


def p03_file_count(inputs: dict, ctx: utils.EvalContext) -> dict:
    glob_pattern = inputs["glob"]
    base = os.path.join(config.WORKSPACE_PATH, inputs.get("base_dir", ""))
    result = utils.docker_exec(f"find {base} -path '{glob_pattern}' 2>/dev/null | wc -l")
    try:
        count = int(result["stdout"].strip())
    except ValueError:
        count = 0
    min_exp = inputs.get("min_expected", 1)
    return {"passed": count >= min_exp, "count": count, "min_expected": min_exp}


def p04_http_request(inputs: dict, ctx: utils.EvalContext) -> dict:
    method = inputs.get("method", "GET")
    path = ctx.resolve(inputs["path"])
    headers = dict(inputs.get("headers", {}))
    body = inputs.get("body")
    if body is not None:
        body = ctx.resolve(body)

    public_paths = ["/alive", "/api/alive", "/api/config", "/api/version",
                    "/identity/", "/api/sends/access/"]
    is_admin = path.startswith("/admin")
    is_public = any(path.startswith(p) or path == p for p in public_paths)

    if is_admin:
        resp = utils.http_request(method, path, headers=headers, body=body,
                                  timeout=inputs.get("timeout", config.REQUEST_TIMEOUT),
                                  session=ctx._session)
        return {"passed": True, "response": resp}

    if "Authorization" not in headers and not is_public:
        token = ctx.get_token("admin") or ctx.get_token(ctx._current_role)
        if token:
            headers["Authorization"] = f"Bearer {token}"

    if "Authorization" in headers and "{{" in headers.get("Authorization", ""):
        auth_val = headers["Authorization"]
        for role in ["admin", "user", "user_b", "org_admin", "org_user"]:
            auth_val = auth_val.replace(f"{{{{{role}_token}}}}", ctx.get_token(role) or "")
        headers["Authorization"] = auth_val

    resp = utils.http_request(method, path, headers=headers, body=body,
                              timeout=inputs.get("timeout", config.REQUEST_TIMEOUT))
    return {"passed": True, "response": resp}


def p05_api_crud(inputs: dict, ctx: utils.EvalContext) -> dict:
    resource = inputs["resource"]
    token = ctx.get_token("admin")
    steps_passed = 0
    total = 4
    evidence = {}

    resp = utils.http_request("POST", resource, body=inputs["create_body"], token=token)
    create_ok = resp["status_code"] in [200, 201, inputs.get("expected_create_status", 200)]
    if create_ok and isinstance(resp["body"], dict):
        entity_id = resp["body"].get("id")
        evidence["create"] = {"id": entity_id, "status": resp["status_code"]}
        steps_passed += 1

        r2 = utils.http_request("GET", f"{resource}/{entity_id}", token=token)
        if r2["status_code"] == 200:
            steps_passed += 1
            evidence["read"] = {"status": r2["status_code"]}

        if inputs.get("update_body"):
            r3 = utils.http_request("PUT", f"{resource}/{entity_id}", body=inputs["update_body"], token=token)
            if r3["status_code"] in [200, inputs.get("expected_update_status", 200)]:
                steps_passed += 1
                evidence["update"] = {"status": r3["status_code"]}

        r4 = utils.http_request("DELETE", f"{resource}/{entity_id}", token=token)
        if r4["status_code"] in [200, 204, inputs.get("expected_delete_status", 200)]:
            steps_passed += 1
            evidence["delete"] = {"status": r4["status_code"]}

    ctx._last_response = {
        "status_code": 200 if steps_passed == total else 500,
        "headers": {},
        "body": {"steps_passed": steps_passed, "steps_total": total, "evidence": evidence},
    }
    return {"passed": steps_passed == total, "steps_passed": steps_passed, "steps_total": total, "evidence": evidence}


def p06_json_schema_match(inputs: dict, ctx: utils.EvalContext) -> dict:
    response = ctx._last_response if hasattr(ctx, '_last_response') else {}
    body = response.get("body", {}) if isinstance(response, dict) else {}
    if not isinstance(body, dict):
        return {"passed": False, "missing_fields": inputs.get("required_fields", []), "all_present": False}
    required = inputs.get("required_fields", [])
    missing = [f for f in required if f not in body]
    return {"passed": len(missing) == 0, "all_present": len(missing) == 0, "missing_fields": missing}


def p07_json_value_assert(inputs: dict, ctx: utils.EvalContext) -> dict:
    response = ctx._last_response if hasattr(ctx, '_last_response') else {}
    body = response.get("body", {}) if isinstance(response, dict) else {}
    assertions = inputs.get("assertions", [])
    results = []
    all_passed = True
    for a in assertions:
        path = a.get("path", "$")
        expected = a.get("expected")
        if isinstance(expected, str):
            expected = ctx.resolve(expected)
        operator = a.get("operator", "equals")
        actual = _resolve_json_path(body, path)
        if operator == "not_null":
            passed = actual is not None
        elif operator == "is_null":
            passed = actual is None
        elif operator == "exists":
            passed = actual is not None
        elif operator == "is_array":
            passed = isinstance(actual, list)
        elif operator == "matches_regex":
            passed = bool(re.search(str(expected), str(actual))) if actual else False
        elif operator == "contains_text":
            passed = str(expected) in str(actual) if actual else False
        elif operator == "not_contains_id":
            passed = not any(item.get("id") == expected for item in actual) if isinstance(actual, list) else True
        else:
            passed = actual == expected
        if not passed:
            all_passed = False
        results.append({"path": path, "expected": expected, "actual": actual, "passed": passed, "operator": operator})
    return {"passed": all_passed, "all_passed": all_passed, "results": results}


def p08_db_query(inputs: dict, ctx: utils.EvalContext) -> dict:
    sql = ctx.resolve(inputs["sql"])
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, ctx)
    except Exception:
        pass
    rows = utils.db_query(sql)
    expected = inputs.get("expected_result")
    if isinstance(expected, dict):
        expected = {k: (ctx.resolve(v) if isinstance(v, str) else v)
                    for k, v in expected.items()}
    if expected and rows and not rows[0].get("error"):
        def _check_val(actual, expected_val):
            if expected_val == "{{not_null}}":
                return actual is not None
            if isinstance(expected_val, str) and expected_val.startswith("{{gte_"):
                threshold = int(expected_val.split("_")[1].rstrip("}}"))
                try:
                    return int(actual) >= threshold
                except (TypeError, ValueError):
                    return False
            return str(actual) == str(expected_val)
        match = all(_check_val(rows[0].get(k), v) for k, v in expected.items())
    elif expected and not rows:
        match = False
    else:
        match = True
    return {"passed": match, "rows": rows, "row_count": len(rows), "match": match}


def p09_db_table_exists(inputs: dict, ctx: utils.EvalContext) -> dict:
    tables = inputs["tables"]
    rows = utils.db_query("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    existing = {r["table_name"] for r in rows if "table_name" in r}
    found = [t for t in tables if t in existing]
    missing = [t for t in tables if t not in existing]
    return {"passed": len(missing) == 0, "existing": found, "missing": missing,
            "found_count": len(found), "total_count": len(tables)}


def p10_db_column_check(inputs: dict, ctx: utils.EvalContext) -> dict:
    table = inputs["table"]
    expected = inputs["expected_columns"]
    rows = utils.db_query(f"SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='{table}'")
    existing = {r["column_name"] for r in rows if "column_name" in r}
    found = [c for c in expected if c in existing]
    missing = [c for c in expected if c not in existing]
    return {"passed": len(missing) == 0, "existing": found, "missing": missing,
            "found_count": len(found), "total_count": len(expected)}


def p13_auth_login(inputs: dict, ctx: utils.EvalContext) -> dict:
    role = inputs.get("role", "admin")
    user = config.TEST_USERS.get(role, config.TEST_USERS["admin"])
    password_hash = user["password_hash"]

    utils.http_request("POST", "/identity/accounts/register", body={
        "email": user["email"], "name": user["name"],
        "masterPasswordHash": password_hash,
        "key": user["key"], "kdf": 0, "kdfIterations": 600000,
    })

    resp = utils.http_request("POST", "/identity/connect/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=f"grant_type=password&username={user['email']}&password={password_hash}"
             f"&scope=api%20offline_access&client_id=web&deviceType=9"
             f"&deviceIdentifier=eval-{role}-device&deviceName=EvalHarness")

    if resp["status_code"] != 200:
        saved_memberships = []
        try:
            conn = utils.get_db_conn()
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT uuid FROM users WHERE email = %s", (user["email"],))
            row = cur.fetchone()
            if row:
                uid = row[0]
                cur.execute("SELECT uuid, org_uuid, access_all, akey, status, atype, reset_password_key "
                           "FROM users_organizations WHERE user_uuid = %s", (uid,))
                saved_memberships = [dict(zip(
                    ["uuid","org_uuid","access_all","akey","status","atype","reset_password_key"], r))
                    for r in cur.fetchall()]

                for sql in [
                    f"DELETE FROM folders_ciphers WHERE cipher_uuid IN (SELECT uuid FROM ciphers WHERE user_uuid='{uid}')",
                    f"DELETE FROM ciphers_collections WHERE cipher_uuid IN (SELECT uuid FROM ciphers WHERE user_uuid='{uid}')",
                    f"DELETE FROM folders_ciphers WHERE folder_uuid IN (SELECT uuid FROM folders WHERE user_uuid='{uid}')",
                ]:
                    try: cur.execute(sql)
                    except: pass
                for tbl, col in [("sends","user_uuid"),("emergency_access","grantor_uuid"),
                    ("emergency_access","grantee_uuid"),("favorites","user_uuid"),
                    ("ciphers","user_uuid"),("folders","user_uuid"),("users_collections","user_uuid"),
                    ("users_organizations","user_uuid"),("devices","user_uuid"),("twofactor","user_uuid"),
                    ("twofactor_incomplete","user_uuid"),("auth_requests","user_uuid"),("sso_users","user_uuid")]:
                    try: cur.execute(f"DELETE FROM {tbl} WHERE {col} = %s", (uid,))
                    except: pass
                try: cur.execute("DELETE FROM users WHERE uuid = %s", (uid,))
                except: pass
            cur.close()
            conn.close()
        except Exception:
            pass

        utils.http_request("POST", "/identity/accounts/register", body={
            "email": user["email"], "name": user["name"],
            "masterPasswordHash": password_hash,
            "key": user["key"], "kdf": 0, "kdfIterations": 600000,
        })

        if saved_memberships:
            try:
                conn = utils.get_db_conn()
                conn.autocommit = True
                cur = conn.cursor()
                cur.execute("SELECT uuid FROM users WHERE email = %s", (user["email"],))
                new_row = cur.fetchone()
                if new_row:
                    new_uid = new_row[0]
                    for m in saved_memberships:
                        try:
                            cur.execute(
                                "INSERT INTO users_organizations (uuid, user_uuid, org_uuid, access_all, akey, status, atype, reset_password_key) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                                (m["uuid"], new_uid, m["org_uuid"], m["access_all"],
                                 m["akey"], m["status"], m["atype"], m.get("reset_password_key")))
                        except Exception:
                            pass
                cur.close()
                conn.close()
            except Exception:
                pass

        resp = utils.http_request("POST", "/identity/connect/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=f"grant_type=password&username={user['email']}&password={password_hash}"
                 f"&scope=api%20offline_access&client_id=web&deviceType=9"
                 f"&deviceIdentifier=eval-{role}-device&deviceName=EvalHarness")

    if resp["status_code"] == 200 and isinstance(resp["body"], dict):
        token = resp["body"].get("access_token")
        if token:
            ctx.set_token(role, token)
            ctx._current_role = role
            user_uuid = resp["body"].get("sub")
            if not user_uuid:
                rows = utils.db_query(f"SELECT uuid FROM users WHERE email='{user['email']}'")
                if rows:
                    user_uuid = rows[0].get("uuid")
            if user_uuid:
                ctx.store_id(f"{role}_user_id", str(user_uuid))

            if role in ("org_admin", "org_user") and ctx.get_id("org_id"):
                org_id = ctx.get_id("org_id")
                admin_token = ctx.get_token("admin")
                membership_type = 1 if role == "org_admin" else 2

                existing = utils.db_query(
                    f"SELECT uuid, status, atype FROM users_organizations "
                    f"WHERE org_uuid='{org_id}' AND user_uuid='{user_uuid}'")
                
                if not existing:
                    utils.http_request("POST",
                        f"/api/organizations/{org_id}/users/invite",
                        body={"emails": [user["email"]], "groups": [], "type": membership_type, "collections": []},
                        token=admin_token)

                members = utils.db_query(
                    f"SELECT uuid, status, atype FROM users_organizations "
                    f"WHERE org_uuid='{org_id}' AND user_uuid='{user_uuid}'")
                
                if members:
                    mid = members[0]["uuid"]
                    status = members[0]["status"]
                    atype = members[0]["atype"]
                    ctx.store_id(f"{role}_mid", str(mid))
                    
                    try:
                        conn = utils.get_db_conn()
                        conn.autocommit = True
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE users_organizations SET status=%s, atype=%s, akey=%s WHERE uuid=%s",
                            (2, membership_type, "2.dGVzdA==|orgkey", mid))
                        cur.close()
                        conn.close()
                    except Exception as e:
                        pass

                all_members = utils.db_query(
                    f"SELECT uuid, atype, user_uuid FROM users_organizations WHERE org_uuid='{org_id}'")
                for m in all_members:
                    if m.get("atype") == 0:
                        ctx.store_id("owner_mid", str(m["uuid"]))
                        ctx.store_id("owner_member_id", str(m["uuid"]))
                    if m.get("atype") == 1:
                        ctx.store_id("admin_mid", str(m["uuid"]))

            return {"passed": True, "role": role, "token_obtained": True}

    return {"passed": False, "role": role, "token_obtained": False, "status": resp["status_code"], "body": resp.get("body")}


def p14_permission_check(inputs: dict, ctx: utils.EvalContext) -> dict:
    action = inputs["action"]
    expected = inputs["expected_result"]
    expected_status = inputs.get("expected_status", [403, 404])
    if isinstance(expected_status, int):
        expected_status = [expected_status]

    parts = action.split(" ", 1)
    method = parts[0]
    path = ctx.resolve(parts[1]) if len(parts) > 1 else "/"

    role = getattr(ctx, '_current_role', None) or inputs.get("_current_role", "user")
    token = ctx.get_token(role)
    if not token:
        p13_result = p13_auth_login({"role": role}, ctx)
        token = ctx.get_token(role)
    resp = utils.http_request(method, path, token=token)

    if expected == "denied":
        passed = resp["status_code"] in expected_status
    else:
        passed = resp["status_code"] in [200, 201, 204]

    return {"passed": passed, "status_code": resp["status_code"], "expected_result": expected,
            "role_used": role}


def p15_status_code_assert(inputs: dict, ctx: utils.EvalContext) -> dict:
    response = ctx._last_response if hasattr(ctx, '_last_response') else {}
    actual = response.get("status_code", 0) if isinstance(response, dict) else 0
    if "acceptable_statuses" in inputs:
        acceptable = inputs["acceptable_statuses"]
    else:
        acceptable = inputs.get("expected_status", 200)
    if isinstance(acceptable, int):
        acceptable = [acceptable]
    elif isinstance(acceptable, list):
        flat = []
        for x in acceptable:
            if isinstance(x, list):
                flat.extend(x)
            else:
                flat.append(x)
        acceptable = flat
    passed = actual in acceptable
    return {"passed": passed, "actual_status": actual, "expected": acceptable}


_CODE_EXTS = {".rs", ".go", ".py", ".rb", ".ts", ".tsx", ".js", ".jsx",
              ".java", ".kt", ".cs", ".ex", ".exs", ".php", ".scala",
              ".swift", ".c", ".cc", ".cpp", ".h", ".hpp"}
_MARKUP_EXTS = {".hbs", ".html", ".htm", ".scss", ".css", ".vue", ".svelte",
                ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".lock", ".svg"}
_SKIP_SUBSTR = ("/node_modules/", "/dist/", "/build/", "/target/", "/.git/",
                "/vendor/", "/__pycache__/", "/coverage/", "/.next/",
                "/test/", "/tests/", "/spec/", "/__tests__/", "/fixtures/")
_RUBRIC_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling".split())


def _rank_code_files(all_paths, root, rubric, max_files=18):
    root = (root or "").rstrip("/")
    mentioned = {p.lower() for p in re.findall(r"[\w./-]+\.\w{1,5}", rubric or "")}
    pathwords = set()
    for p in re.findall(r"(?:src|app|lib|server|backend)/[\w./*-]+", rubric or ""):
        for seg in re.split(r"[/.*]", p):
            if len(seg) >= 3:
                pathwords.add(seg.lower())
    kws = {}
    for t in re.findall(r"[A-Za-z_]{3,}", (rubric or "").lower()):
        if t not in _RUBRIC_STOP:
            kws[t] = kws.get(t, 0) + 1
    wants_tpl = any(k in kws for k in ("template", "templates", "email", "admin",
                                       "handlebars", "bootstrap", "html", "view"))
    scored = []
    for full in all_paths:
        full = full.strip()
        if not full:
            continue
        rel = full[len(root):].lstrip("/") if root and full.startswith(root) else full
        low = rel.lower()
        if any(s in "/" + low for s in _SKIP_SUBSTR):
            continue
        base = os.path.basename(low)
        ext = os.path.splitext(low)[1]
        rel_score = 0.0
        for m in mentioned:
            mb = m.split("/")[-1]
            if mb and (mb == base or low.endswith(m)):
                rel_score += 50
        for w in pathwords:
            if w in low:
                rel_score += 8
        for w, c in kws.items():
            if w in low:
                rel_score += 2
        ext_p = 2.0 if ext in _CODE_EXTS else (0.0 if ext in _MARKUP_EXTS else 0.5)
        noise = 0.0
        if "/static/" in "/" + low or "/templates/" in "/" + low or "template" in low:
            noise = 1.0 if wants_tpl else -4.0
        parts = rel.split("/")
        strat = parts[1] if len(parts) > 1 else parts[0]
        scored.append((rel_score + ext_p + noise, strat, rel, full))
    scored.sort(key=lambda x: (-x[0], x[2]))
    groups = {}
    order = []
    for tot, strat, rel, full in scored:
        if strat not in groups:
            groups[strat] = []
            order.append(strat)
        groups[strat].append(full)
    picked = []
    while len(picked) < max_files and any(groups[k] for k in order):
        for k in order:
            if groups[k]:
                picked.append(groups[k].pop(0))
                if len(picked) >= max_files:
                    break
    return picked


_CODE_EXTS = {".rs", ".go", ".py", ".rb", ".ts", ".tsx", ".js", ".jsx",
              ".java", ".kt", ".cs", ".ex", ".exs", ".php", ".scala",
              ".swift", ".c", ".cc", ".cpp", ".h", ".hpp"}
_MARKUP_EXTS = {".hbs", ".html", ".htm", ".scss", ".css", ".vue", ".svelte",
                ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".lock", ".svg"}
_SKIP_SUBSTR = ("/node_modules/", "/dist/", "/build/", "/target/", "/.git/",
                "/vendor/", "/__pycache__/", "/coverage/", "/.next/",
                "/test/", "/tests/", "/spec/", "/__tests__/", "/fixtures/")
_RUBRIC_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling".split())


def _rank_code_files(all_paths, root, rubric, max_files=18):
    root = (root or "").rstrip("/")
    mentioned = {p.lower() for p in re.findall(r"[\w./-]+\.\w{1,5}", rubric or "")}
    pathwords = set()
    for p in re.findall(r"(?:src|app|lib|server|backend)/[\w./*-]+", rubric or ""):
        for seg in re.split(r"[/.*]", p):
            if len(seg) >= 3:
                pathwords.add(seg.lower())
    kws = {}
    for t in re.findall(r"[A-Za-z_]{3,}", (rubric or "").lower()):
        if t not in _RUBRIC_STOP:
            kws[t] = kws.get(t, 0) + 1
    wants_tpl = any(k in kws for k in ("template", "templates", "email", "admin",
                                       "handlebars", "bootstrap", "html", "view"))
    scored = []
    for full in all_paths:
        full = full.strip()
        if not full:
            continue
        rel = full[len(root):].lstrip("/") if root and full.startswith(root) else full
        low = rel.lower()
        if any(s in "/" + low for s in _SKIP_SUBSTR):
            continue
        base = os.path.basename(low)
        ext = os.path.splitext(low)[1]
        rel_score = 0.0
        for m in mentioned:
            mb = m.split("/")[-1]
            if mb and (mb == base or low.endswith(m)):
                rel_score += 50
        for w in pathwords:
            if w in low:
                rel_score += 8
        for w, c in kws.items():
            if w in low:
                rel_score += 2
        ext_p = 2.0 if ext in _CODE_EXTS else (0.0 if ext in _MARKUP_EXTS else 0.5)
        noise = 0.0
        if "/static/" in "/" + low or "/templates/" in "/" + low or "template" in low:
            noise = 1.0 if wants_tpl else -4.0
        parts = rel.split("/")
        strat = parts[1] if len(parts) > 1 else parts[0]
        scored.append((rel_score + ext_p + noise, strat, rel, full))
    scored.sort(key=lambda x: (-x[0], x[2]))
    groups = {}
    order = []
    for tot, strat, rel, full in scored:
        if strat not in groups:
            groups[strat] = []
            order.append(strat)
        groups[strat].append(full)
    picked = []
    while len(picked) < max_files and any(groups[k] for k in order):
        for k in order:
            if groups[k]:
                picked.append(groups[k].pop(0))
                if len(picked) >= max_files:
                    break
    return picked


def p17_llm_judge(inputs: dict, ctx: utils.EvalContext) -> dict:
    score_range_for_skip = inputs.get("score_range", [0, 5])
    if getattr(config, "SKIP_LLM_JUDGE", False):
        return {"score": 0, "max_score": score_range_for_skip[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "SKIP_LLM_JUDGE=1 (LLM judge intentionally skipped for peer-review-grade scoring)"}
    evidence_type = inputs.get("evidence_type", "code_files")
    rubric = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])

    evidence_text = ""
    if evidence_type == "code_files":
        files_to_sample = inputs.get("files_to_sample", ["src/"])
        _exts = ["*.rs", "*.hbs", "*.html", "*.go", "*.ts", "*.tsx", "*.js",
                 "*.jsx", "*.py", "*.rb", "*.java", "*.kt", "*.cs", "*.ex",
                 "*.exs", "*.php", "*.scala", "*.c", "*.cc", "*.cpp", "*.h",
                 "*.scss", "*.css"]
        _name_expr = " -o ".join(f"-name '{e}'" for e in _exts)
        candidates = []
        roots = []
        for pattern in files_to_sample:
            base = f"{config.WORKSPACE_PATH}/{pattern}".rstrip("/")
            roots.append(base)
            result = utils.docker_exec(
                f"find {base} -type f \\( {_name_expr} \\) 2>/dev/null | head -800")
            candidates.extend(
                p for p in result["stdout"].strip().split("\n") if p.strip())
        rank_root = config.WORKSPACE_PATH.rstrip("/")
        selected = _rank_code_files(candidates, rank_root, rubric, max_files=18)
        total = 0
        for f in selected:
            if total > 42000:
                break
            content = utils.docker_exec(f"head -160 '{f}'")
            chunk = content["stdout"][:2800]
            rel = f[len(rank_root):].lstrip("/") if f.startswith(rank_root) else f
            evidence_text += f"\n--- {rel} ---\n{chunk}\n"
            total += len(chunk)

    if not config.LLM_API_KEY:
        return {"passed": True, "score": 0, "max_score": score_range[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "LLM_API_KEY unset"}

    prompt = f"""You are evaluating code quality. Score from {score_range[0]} to {score_range[1]}.

RUBRIC:
{rubric}

CODE EVIDENCE:
{evidence_text[:24000]}

Return ONLY a JSON object: {{"score": <number>, "reasoning": "<brief>"}}"""

    from _llm_judge_safe import safe_chat_completion
    res = safe_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=config.LLM_MODEL,
        api_key=config.LLM_API_KEY,
        api_base=getattr(config, "LLM_API_BASE", ""),
        temperature=0,
        max_tokens=500,
    )
    if res.skipped:
        return {"passed": True, "score": 0, "max_score": score_range[1],
                "skipped": True,
                "llm_api_failure": res.llm_api_failure,
                "exception_class": res.exception_class,
                "reason": res.error or "skipped"}

    raw = res.raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fence.group(1) if fence else raw
    try:
        result = json.loads(candidate)
    except Exception:
        obj = re.search(r"\{.*\}", candidate, re.DOTALL)
        try:
            result = json.loads(obj.group(0)) if obj else None
        except Exception:
            result = None
    if isinstance(result, dict):
        return {"passed": True, "score": result.get("score", 0), "max_score": score_range[1],
                "reasoning": result.get("reasoning", "")}
    return {"passed": True, "score": 0, "max_score": score_range[1],
            "parse_failure": True, "reason": "could not parse JSON from LLM output",
            "raw": res.raw[:200]}


def p29_multi_step_workflow(inputs: dict, ctx: utils.EvalContext) -> dict:
    steps_passed = 0
    step_results = []
    entity_id = None
    access_id = None

    def _resolve_token(step_or_setup: dict):
        tok_spec = step_or_setup.get("token", "{{admin_token}}")
        if tok_spec == "" or tok_spec is None:
            return None
        if tok_spec.startswith("{{") and tok_spec.endswith("}}"):
            role = tok_spec[2:-2].replace("_token", "")
            t = ctx.get_token(role)
            if not t and role != "admin":
                p13_auth_login({"role": role}, ctx)
                t = ctx.get_token(role)
            return t or ctx.get_token("admin")
        return ctx.get_token(tok_spec) or ctx.get_token("admin")

    def _replace_ids(path: str) -> str:
        result = ctx.resolve(path)
        if entity_id:
            for ph in ["{{id}}", "{{emer_id}}", "{{member_id}}"]:
                result = result.replace(ph, str(entity_id))
        if access_id:
            result = result.replace("{{accessId}}", access_id)
        return result

    pre_reg = inputs.get("entity_setup", {}).get("pre_register")
    if pre_reg:
        p13_auth_login({"role": pre_reg.get("role", "user")}, ctx)

    setup = inputs.get("entity_setup")
    if setup:
        path = _replace_ids(setup["path"])
        setup_token = _resolve_token(setup)
        body = ctx.resolve(setup.get("body")) if setup.get("body") else None
        resp = utils.http_request(setup["method"], path, body=body, token=setup_token)
        if resp["status_code"] in [200, 201, 204] and isinstance(resp["body"], dict):
            entity_id = resp["body"].get("id") or resp["body"].get("uuid")
            if entity_id:
                ctx.store_id("workflow_entity_id", str(entity_id))
            if resp["body"].get("accessId"):
                access_id = resp["body"]["accessId"]
            elif "/sends" in setup.get("path", "") and entity_id:
                import uuid as uuid_mod, base64
                try:
                    u = uuid_mod.UUID(entity_id)
                    access_id = base64.urlsafe_b64encode(u.bytes).rstrip(b'=').decode()
                except Exception:
                    pass
            step_results.append({"name": "setup", "passed": True, "entity_id": entity_id})
        else:
            return {"passed": False, "steps_passed": 0, "steps_total": len(inputs.get("steps", [])),
                    "step_results": [{"name": "setup", "passed": False, "status": resp["status_code"],
                                      "body": str(resp.get("body", ""))[:200]}]}

    steps = inputs.get("steps", [])
    for step in steps:
        path = _replace_ids(step["path"])
        step_token = _resolve_token(step)
        body = ctx.resolve(step.get("body")) if step.get("body") else None

        resp = utils.http_request(step["method"], path, body=body, token=step_token)
        expected_status = step.get("expect_status", 200)
        passed = resp["status_code"] == expected_status

        if passed and step.get("expect_state") and isinstance(resp["body"], dict):
            state_path = step["expect_state"]["path"]
            expected_val = step["expect_state"]["value"]
            actual_val = _resolve_json_path(resp["body"], state_path)
            passed = (str(actual_val) == str(expected_val))

        if passed:
            steps_passed += 1
        step_results.append({"name": step["name"], "passed": passed, "status": resp["status_code"]})

    final = inputs.get("final_verify")
    final_match = True
    if final and final.get("db_query"):
        sql = ctx.resolve(final["db_query"])
        if entity_id:
            sql = sql.replace("{{id}}", str(entity_id))
            sql = sql.replace("{{emer_id}}", str(entity_id))
            sql = sql.replace("{{member_id}}", str(entity_id))
        rows = utils.db_query(sql)
        if rows and not rows[0].get("error") and final.get("expected"):
            final_match = all(str(rows[0].get(k)) == str(v) for k, v in final["expected"].items())
        elif not rows and final.get("expected"):
            final_match = False

    all_passed = steps_passed == len(steps) and final_match
    return {"passed": all_passed, "entity_id": entity_id, "steps_passed": steps_passed,
            "steps_total": len(steps), "final_state_match": final_match, "step_results": step_results}


def _resolve_json_path(data: Any, path: str) -> Any:
    if path == "$":
        return data
    parts = path.lstrip("$.").split(".")
    current = data
    for part in parts:
        if current is None:
            return None
        m = re.match(r'(\w*)\[(\d+)\]', part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if key and isinstance(current, dict):
                current = current.get(key)
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


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
    "P13": p13_auth_login,
    "P14": p14_permission_check,
    "P15": p15_status_code_assert,
    "P17": p17_llm_judge,
    "P29": p29_multi_step_workflow,
}
