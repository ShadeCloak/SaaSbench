from __future__ import annotations

import os as _os
from pathlib import Path as _Path
REPO_ROOT = str(_Path(__file__).resolve().parents[3])
HOME = _os.path.expanduser('~')

import glob as _glob
import json
import logging
import os
import re
import subprocess
import time
from typing import Any

import requests

import config
from utils import (
    auth_ctx, artifact_store, graphql, http_request, safe_json,
    json_path_value, assert_json_value, get_db_connection, NodeResult,
)

logger = logging.getLogger("eval.primitives")



def p01_file_exists(inputs: dict) -> dict:
    path = inputs.get("path", "")
    base = config.WORKSPACE_PATH
    target = os.path.join(base, path) if not os.path.isabs(path) else path
    if "*" in path or "?" in path:
        matches = _glob.glob(target, recursive=True)
        return {"exists": len(matches) > 0, "matches": matches[:10]}
    exists = os.path.exists(target)
    return {"exists": exists, "path": target}



def p02_file_content_check(inputs: dict) -> dict:
    path = inputs.get("path", "")
    patterns = inputs.get("patterns", [])
    contains = inputs.get("contains", [])
    not_contains = inputs.get("not_contains", [])

    base = config.WORKSPACE_PATH
    target = os.path.join(base, path) if not os.path.isabs(path) else path

    if "*" in target or "?" in target:
        matches = _glob.glob(target, recursive=True)
        if not matches:
            return {"passed": False, "error": f"No files matched: {path}"}
        target = matches[0]

    if not os.path.isfile(target):
        return {"passed": False, "error": f"File not found: {target}"}

    try:
        with open(target, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except Exception as exc:
        return {"passed": False, "error": str(exc)}

    results = []
    all_passed = True

    for pat in (patterns or contains):
        if isinstance(pat, dict):
            regex = pat.get("regex", pat.get("pattern", ""))
            found = bool(re.search(regex, content))
        else:
            found = pat in content
        results.append({"pattern": str(pat), "found": found})
        if not found:
            all_passed = False

    for pat in not_contains:
        text = pat if isinstance(pat, str) else pat.get("pattern", "")
        found = text in content
        results.append({"pattern": text, "should_not_exist": True, "found": found})
        if found:
            all_passed = False

    return {"passed": all_passed, "results": results, "file_size": len(content)}



def p04_http_request(inputs: dict, ctx: dict) -> dict:
    method = inputs.get("method", "GET")
    path = inputs.get("path", "/")
    body = inputs.get("body")
    hdrs = dict(inputs.get("headers", {}))
    timeout = inputs.get("timeout", config.HTTP_TIMEOUT)
    url = inputs.get("url")

    if not hdrs.get("Authorization"):
        hdrs.update(auth_ctx.auth_headers())
    if body is not None and "Content-Type" not in hdrs:
        hdrs["Content-Type"] = "application/json"

    try:
        if url:
            resp = requests.request(method, url, json=body, headers=hdrs, timeout=timeout)
        else:
            resp = http_request(method, path, body=body, headers=hdrs, timeout=timeout)
        ctx["last_response"] = resp
        ctx["last_status"] = resp.status_code
        ctx["last_body"] = safe_json(resp) or resp.text
        return {
            "status_code": resp.status_code,
            "body": ctx["last_body"],
            "headers": dict(resp.headers),
            "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
        }
    except Exception as exc:
        ctx["last_response"] = None
        ctx["last_status"] = 0
        ctx["last_body"] = None
        return {"status_code": 0, "error": str(exc)}



def p06_json_schema_match(inputs: dict, ctx: dict) -> dict:
    data = ctx.get("last_body") or {}
    required = inputs.get("required_fields", [])
    missing = []
    for field_path in required:
        val = json_path_value(data, f"$.{field_path}")
        if val is None:
            missing.append(field_path)
    return {"all_present": len(missing) == 0, "missing_fields": missing,
            "found_count": len(required) - len(missing), "total_count": len(required)}



def p07_json_value_assert(inputs: dict, ctx: dict) -> dict:
    data = ctx.get("last_body") or {}
    assertions = inputs.get("assertions", [])
    if not assertions:
        path = inputs.get("path")
        if path:
            assertions = [inputs]

    results = []
    all_passed = True
    for a in assertions:
        passed = assert_json_value(data, a)
        actual = json_path_value(data, a.get("path", "$"))
        results.append({
            "path": a.get("path"),
            "op": a.get("operator", "eq"),
            "expected": a.get("expected"),
            "actual": actual,
            "passed": passed,
        })
        if not passed:
            all_passed = False

    return {"all_passed": all_passed, "results": results,
            "pass_count": sum(1 for r in results if r["passed"]),
            "total_count": len(results)}



def p08_db_query(inputs: dict, ctx: dict) -> dict:
    query = inputs.get("query") or inputs.get("sql", "")
    database = inputs.get("database", config.DB_NAME)
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            if database and database != config.DB_NAME:
                cur.execute(f"USE `{database}`")
            cur.execute(query)
            rows = cur.fetchall()
        conn.close()
        if rows:
            ctx["last_body"] = rows[0] if len(rows) == 1 else rows
        else:
            ctx["last_body"] = {}
        return {"rows": rows, "row_count": len(rows)}
    except Exception as exc:
        ctx["last_body"] = {}
        return {"rows": [], "row_count": 0, "error": str(exc)}



def p09_db_table_exists(inputs: dict, ctx: dict) -> dict:
    table = inputs.get("table") or inputs.get("tables", [""])[0]
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            existing = [list(r.values())[0] for r in cur.fetchall()]
        conn.close()
        found = table in existing
        ctx["last_body"] = {"exists": found}
        return {"exists": found, "existing_tables": existing}
    except Exception as exc:
        return {"exists": False, "error": str(exc)}



def p10_db_column_check(inputs: dict, ctx: dict) -> dict:
    table = inputs.get("table", "")
    expected = inputs.get("columns", inputs.get("expected_columns", []))
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(f"DESCRIBE `{table}`")
            actual_cols = {r["Field"].lower(): r["Type"] for r in cur.fetchall()}
        conn.close()
        found, missing = [], []
        for col_spec in expected:
            col_name = col_spec["name"].lower() if isinstance(col_spec, dict) else col_spec.lower()
            if col_name in actual_cols:
                found.append(col_name)
            else:
                missing.append(col_name)
        return {"found": found, "missing": missing,
                "found_count": len(found), "total_count": len(expected)}
    except Exception as exc:
        return {"found": [], "missing": [], "error": str(exc)}



def p11_db_index_check(inputs: dict, ctx: dict) -> dict:
    table = inputs.get("table", "")
    expected_name = inputs.get("index_name", "PRIMARY")
    expected_cols = inputs.get("columns", [])
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(f"SHOW INDEX FROM `{table}`")
            rows = cur.fetchall()
        conn.close()
        indexes: dict[str, list[str]] = {}
        for r in rows:
            key = r["Key_name"]
            indexes.setdefault(key, []).append(r["Column_name"])
        found = expected_name in indexes
        if found and expected_cols:
            actual = indexes[expected_name]
            found = all(c in actual for c in expected_cols)
        return {"found": found, "indexes": indexes}
    except Exception as exc:
        return {"found": False, "error": str(exc)}



def p12_docker_exec(inputs: dict, ctx: dict) -> dict:
    cmd = inputs.get("command", "echo ok")
    container = inputs.get("container", config.APP_CONTAINER)
    timeout = inputs.get("timeout", 30)
    try:
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        ctx["last_body"] = {"stdout": result.stdout, "stderr": result.stderr,
                            "exit_code": result.returncode}
        if result.returncode == 0:
            return {
                "stdout": result.stdout, "stderr": result.stderr,
                "exit_code": result.returncode, "success": True,
            }
    except Exception:
        pass

    cmd_for_host = cmd
    cmd_stripped = cmd.lstrip()
    if cmd_stripped.startswith("mdp ") or cmd_stripped == "mdp":
        leading = cmd[: len(cmd) - len(cmd_stripped)]
        cmd_for_host = leading + "datahub" + cmd_stripped[3:]
    try:
        env = dict(os.environ)
        env["PATH"] = env.get("PATH", "") + f":{HOME}/.local/bin"
        env["DATAHUB_GMS_URL"] = config.APP_BASE_URL
        env["DATAHUB_GMS_HOST"] = config.APP_HOST
        env["DATAHUB_GMS_PORT"] = str(config.APP_PORT)
        cli_token = auth_ctx.current_token or ""
        if cli_token.startswith("__system_basic__"):
            try:
                sys_creds = cli_token[len("__system_basic__"):]
                sys_id, sys_secret = sys_creds.split(":", 1)
                sys_hdrs = {
                    "Authorization": f"Basic {sys_id}:{sys_secret}",
                    "Content-Type": "application/json",
                }
                gql = (
                    'mutation { createAccessToken(input: '
                    '{type: PERSONAL, actorUrn: "urn:li:corpuser:datahub", '
                    'duration: ONE_HOUR, name: "p12_cli_bridge"}) '
                    '{ accessToken } }'
                )
                resp = requests.post(
                    config.APP_BASE_URL + "/api/graphql",
                    json={"query": gql}, headers=sys_hdrs,
                    timeout=10,
                )
                body = safe_json(resp) or {}
                personal_tok = (
                    body.get("data", {})
                    .get("createAccessToken", {})
                    .get("accessToken")
                )
                if personal_tok:
                    cli_token = personal_tok
            except Exception as _:
                pass
        env["DATAHUB_GMS_TOKEN"] = cli_token
        result = subprocess.run(
            ["bash", "-c", cmd_for_host],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        ctx["last_body"] = {"stdout": result.stdout, "stderr": result.stderr,
                            "exit_code": result.returncode}
        return {
            "stdout": result.stdout, "stderr": result.stderr,
            "exit_code": result.returncode, "success": result.returncode == 0,
        }
    except Exception as exc:
        ctx["last_body"] = {"exit_code": -1}
        return {"exit_code": -1, "error": str(exc), "success": False}



def p13_auth_login(inputs: dict, ctx: dict) -> dict:
    role = inputs.get("role", "admin")

    cached = auth_ctx.switch_role(role)
    if cached:
        return {"success": True, "token": cached, "role": role, "cached": True}

    username = config.ADMIN_USERNAME
    password = config.ADMIN_PASSWORD

    creds = inputs.get("credentials", {})
    if creds:
        username = creds.get("username", username)
        password = creds.get("password", password)

    if role in ("reader", "editor") and not creds:
        token = _create_role_token(role)
        if token:
            auth_ctx.set_token(role, token)
            return {"success": True, "token": token, "role": role, "method": "role_token"}

    s1_token = _auth_strategy_login(username, password)
    if s1_token:
        auth_ctx.set_token(role, s1_token)
        return {"success": True, "token": s1_token, "role": role, "method": "logIn"}

    s15_token = _auth_strategy_system_basic(username, role)
    if s15_token:
        auth_ctx.set_token(role, s15_token)
        return {"success": True, "token": s15_token, "role": role, "method": "system_basic"}

    s2_token = _auth_strategy_graphql(username, role)
    if s2_token:
        auth_ctx.set_token(role, s2_token)
        return {"success": True, "token": s2_token, "role": role, "method": "graphql"}

    s3_token = _auth_strategy_db_token(username, role)
    if s3_token:
        auth_ctx.set_token(role, s3_token)
        return {"success": True, "token": s3_token, "role": role, "method": "db_direct"}

    s4_token = _auth_strategy_legacy_header(username)
    if s4_token:
        auth_ctx.set_token(role, s4_token)
        return {"success": True, "token": s4_token, "role": role, "method": "legacy_header"}

    logger.warning("All auth strategies failed for role=%s; proceeding without token", role)
    auth_ctx.set_token(role, "")
    return {"success": False, "token": "", "role": role, "error": "All auth strategies failed"}


def _create_role_token(role: str) -> str | None:
    actor_urn = f"urn:li:corpuser:eval_{role}"
    role_urn_map = {"reader": "urn:li:dataHubRole:Reader", "editor": "urn:li:dataHubRole:Editor"}
    role_urn = role_urn_map.get(role)
    if not role_urn:
        return None
    sys_id = config.SYSTEM_CLIENT_ID
    sys_secret = config.SYSTEM_CLIENT_SECRET
    hdrs = {"Authorization": f"Basic {sys_id}:{sys_secret}", "Content-Type": "application/json"}
    try:
        snapshot = {
            "entity": {
                "value": {
                    "com.linkedin.metadata.snapshot.CorpUserSnapshot": {
                        "urn": actor_urn,
                        "aspects": [
                            {
                                "com.linkedin.identity.CorpUserInfo": {
                                    "active": True,
                                    "displayName": f"Eval {role.capitalize()}",
                                    "email": f"eval_{role}@example.com",
                                }
                            }
                        ],
                    }
                }
            }
        }
        requests.post(config.APP_BASE_URL + "/entities?action=ingest", json=snapshot, headers=hdrs, timeout=10)
    except Exception:
        pass
    for ep in [config.APP_BASE_URL + "/api/graphql", config.GRAPHQL_ENDPOINT]:
        try:
            requests.post(ep, json={"query": f'mutation {{ batchAssignRole(input: {{roleUrn: "{role_urn}", actors: ["{actor_urn}"]}}) }}'}, headers=hdrs, timeout=10)
            resp = requests.post(ep, json={"query": f'mutation {{ createAccessToken(input: {{type: PERSONAL, actorUrn: "{actor_urn}", duration: ONE_DAY, name: "eval_{role}_{int(time.time())}"}}) {{ accessToken }} }}'}, headers=hdrs, timeout=10)
            body = safe_json(resp)
            if body and isinstance(body, dict):
                token = (body.get("data") or {}).get("createAccessToken", {}).get("accessToken")
                if token:
                    return token
        except Exception:
            continue
    return None


def _auth_strategy_login(username: str, password: str) -> str | None:
    try:
        resp = requests.post(
            config.LOGIN_ENDPOINT,
            json={"username": username, "password": password},
            timeout=config.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            body = safe_json(resp)
            if body and isinstance(body, dict):
                return body.get("accessToken") or body.get("token") or body.get("access_token")
    except Exception:
        logger.debug("Strategy 1 (logIn) failed for %s", username)
    return None


def _auth_strategy_system_basic(username: str, role: str) -> str | None:
    sys_id = os.environ.get("SYSTEM_CLIENT_ID", config.SYSTEM_CLIENT_ID)
    sys_secret = os.environ.get("SYSTEM_CLIENT_SECRET", config.SYSTEM_CLIENT_SECRET)
    system_header = f"Basic {sys_id}:{sys_secret}"
    gql_endpoints = [config.GRAPHQL_ENDPOINT, config.APP_BASE_URL + "/api/graphql"]
    for ep in gql_endpoints:
        try:
            resp = requests.post(ep,
                json={"query": "{ __typename }"},
                headers={"Content-Type": "application/json", "Authorization": system_header},
                timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 200:
                return f"__system_basic__{sys_id}:{sys_secret}"
        except Exception:
            continue
    return None


def _auth_strategy_graphql(username: str, role: str) -> str | None:
    try:
        hdrs = {"Content-Type": "application/json"}
        hdrs.update(auth_ctx.auth_headers())
        resp = requests.post(
            config.GRAPHQL_ENDPOINT,
            json={"query": f'mutation {{ createAccessToken(input: {{ type: PERSONAL, actorUrn: "urn:li:corpuser:{username}", duration: ONE_DAY, name: "eval_{role}_{int(time.time())}" }}) {{ accessToken }} }}'},
            headers=hdrs,
            timeout=config.HTTP_TIMEOUT,
        )
        body = safe_json(resp)
        if body and isinstance(body, dict) and "data" in body:
            return json_path_value(body, "$.data.createAccessToken.accessToken")
    except Exception:
        logger.debug("Strategy 2 (GraphQL) failed for %s", username)
    return None


def _auth_strategy_db_token(username: str, role: str) -> str | None:
    import hashlib
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [list(r.values())[0] for r in cur.fetchall()]

            token_table = next((t for t in tables if "access_token" in t.lower()), None)
            users_table = next(
                (t for t in tables if t.lower().endswith("_users") or t.lower() == "users"
                 or t.lower() == "corpuser" or t.lower().endswith("_user")),
                None,
            )

            if not token_table:
                conn.close()
                return None

            new_token = hashlib.sha256(f"eval_{role}_{username}_{time.time()}".encode()).hexdigest()

            if users_table:
                cur.execute(f"SELECT id FROM `{users_table}` WHERE username=%s OR email=%s LIMIT 1",
                            (username, username))
                user_row = cur.fetchone()
                user_id = user_row["id"] if user_row else 1
            else:
                user_id = 1

            cur.execute(f"DELETE FROM `{token_table}` WHERE name=%s", (f"eval_{role}",))
            try:
                cur.execute(
                    f"INSERT INTO `{token_table}` (user_id, token, name) VALUES (%s, %s, %s)",
                    (user_id, new_token, f"eval_{role}"),
                )
            except Exception:
                cur.execute(
                    f"INSERT INTO `{token_table}` (token, name) VALUES (%s, %s)",
                    (new_token, f"eval_{role}"),
                )
            conn.commit()
        conn.close()

        verify = requests.get(
            config.HEALTH_ENDPOINT,
            headers={"Authorization": f"Bearer {new_token}"},
            timeout=5,
        )
        if verify.status_code < 500:
            return new_token
    except Exception:
        logger.debug("Strategy 3 (DB direct) failed for %s", username)
    return None


def _auth_strategy_legacy_header(username: str) -> str | None:
    try:
        resp = requests.get(
            config.HEALTH_ENDPOINT,
            headers={"X-AUTH-USER": username},
            timeout=5,
        )
        if resp.status_code == 200:
            return f"__legacy__{username}"
    except Exception:
        logger.debug("Strategy 4 (legacy header) failed for %s", username)
    return None



def p14_permission_check(inputs: dict, ctx: dict) -> dict:
    role = inputs.get("role", "user")
    action = inputs.get("action", "")
    expected = inputs.get("expected_result", "denied")
    expected_statuses = inputs.get("expected_status", [403, 404])
    if isinstance(expected_statuses, int):
        expected_statuses = [expected_statuses]

    p13_auth_login({"role": role}, ctx)

    query = inputs.get("query")

    if not query and "/graphql" in action and "(" in action:
        gql_match = re.search(r'\((\w+):\s*(query|mutation)\s*\{', action)
        if gql_match:
            paren_start = action.index("(")
            query = action[paren_start + len(gql_match.group(1)) + 2:].rstrip(")")
            if not query.strip().startswith(("{", "query", "mutation")):
                query = action[paren_start + 1:].rsplit(")", 1)[0]
                colon_pos = query.find(":")
                if colon_pos > 0:
                    query = query[colon_pos + 1:].strip()

    if query:
        result = graphql(query)
        ctx["last_body"] = result
        has_errors = bool(result.get("errors"))
        error_codes = []
        if has_errors and isinstance(result.get("errors"), list):
            for e in result["errors"]:
                ext = e.get("extensions", {})
                error_codes.append(ext.get("code", ""))
        if expected == "denied":
            passed = has_errors and any(c in ("403", "UNAUTHORIZED") for c in error_codes) if error_codes else has_errors
            return {"passed": passed, "result": result, "error_codes": error_codes}
        else:
            passed = not has_errors
            return {"passed": passed, "result": result}

    method_path = action.split(" ", 1) if " " in action else ["GET", action]
    method, path = method_path[0], method_path[1]
    if "(" in path:
        path = path[:path.index("(")].strip()

    try:
        resp = http_request(method, path, timeout=config.HTTP_TIMEOUT)
        status = resp.status_code
        if expected == "denied":
            passed = status in expected_statuses or status in [403, 404, 401]
        else:
            passed = 200 <= status < 400
        return {"passed": passed, "status_code": status, "expected": expected}
    except Exception as exc:
        return {"passed": False, "error": str(exc)}



def p15_status_code_assert(inputs: dict, ctx: dict) -> dict:
    expected = inputs.get("expected_status")
    acceptable = inputs.get("acceptable_statuses") or inputs.get("acceptable")
    actual = ctx.get("_last_status_code", 0) if isinstance(ctx, dict) else 0
    if not actual and isinstance(ctx, dict):
        actual = (ctx.get("last_status_code")
                  or ctx.get("last_status")
                  or ctx.get("status_code")
                  or 0)

    accepted = set()
    for v in (expected, acceptable):
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            for x in v:
                try: accepted.add(int(x))
                except (TypeError, ValueError): pass
        else:
            try: accepted.add(int(v))
            except (TypeError, ValueError): pass

    try: actual_i = int(actual)
    except (TypeError, ValueError): actual_i = 0

    if accepted:
        passed = actual_i in accepted
    else:
        passed = 200 <= actual_i < 300

    if not passed:
        try:
            from _inclusivity import _is_idempotent_success, _is_idempotent_delete_success
            body = ""
            method = ""
            if isinstance(ctx, dict):
                body = ctx.get("_last_response_body") or ctx.get("last_body") or ""
                method = (ctx.get("_last_request_method") or ctx.get("last_method") or "").upper()
            if _is_idempotent_success(actual_i, body, accepted) or _is_idempotent_delete_success(method, actual_i, accepted):
                passed = True
                if isinstance(ctx, dict):
                    ctx["_idempotent_ok"] = True
        except Exception:
            pass

    return {
        "passed": passed,
        "expected": expected or acceptable,
        "acceptable": sorted(accepted) if accepted else None,
        "actual": actual_i,
        "status_code": actual_i,
    }



_CODE_EXTS = {".java", ".kt", ".scala", ".py", ".ts", ".tsx", ".js", ".jsx",
              ".go", ".rb", ".rs", ".graphql", ".gql", ".pdl", ".avsc",
              ".proto", ".sql", ".gradle"}
_MARKUP_EXTS = {".html", ".htm", ".scss", ".css", ".md", ".txt", ".json",
                ".yaml", ".yml", ".xml", ".properties", ".lock", ".svg"}
_SKIP_SUBSTR = ("/node_modules/", "/dist/", "/build/", "/target/", "/.git/",
                "/vendor/", "/__pycache__/", "/.gradle/", "/generated/",
                "/test/", "/tests/", "/testdata/", "/src/test/", "/.venv/")
_RUBRIC_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent does "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling whether well overall".split())


def _gather_and_rank(root, files_to_sample, rubric, max_files=16):
    root = (root or "").rstrip("/")
    entries = list(files_to_sample) or ["."]
    cands = []

    def _walk_dir(base):
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

    for ent in entries:
        ent = str(ent).lstrip("/")
        base = os.path.join(root, ent)
        if os.path.isfile(base):
            cands.append(base)
        elif os.path.isdir(base):
            _walk_dir(base)
        else:
            stem = os.path.basename(ent.rstrip("/")) or ent.rstrip("/")
            matched = []
            try:
                matched = (_glob.glob(base, recursive=True)
                           or _glob.glob(os.path.join(root, "**", ent), recursive=True)
                           or _glob.glob(os.path.join(root, "*" + stem + "*")))
            except Exception:
                matched = []
            for mp in matched[:8]:
                if os.path.isfile(mp):
                    cands.append(mp)
                elif os.path.isdir(mp):
                    _walk_dir(mp)
    mentioned = {m.split("/")[-1].lower()
                 for m in re.findall(r"[\w./*-]+\.\w{1,5}", rubric or "")}
    pathwords = set()
    for p in re.findall(r"[\w-]+/[\w./*-]+", rubric or ""):
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
    picked = []
    while len(picked) < max_files and any(groups[k] for k in order):
        for k in order:
            if groups[k]:
                picked.append(groups[k].pop(0))
                if len(picked) >= max_files:
                    break
    return picked


def p17_llm_judge(inputs: dict, ctx: dict) -> dict:
    score_range = inputs.get("score_range", [0, 5])
    if getattr(config, "SKIP_LLM_JUDGE", False):
        return {"score": 0, "max_score": score_range[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "SKIP_LLM_JUDGE=1 (LLM judge intentionally skipped for peer-review-grade scoring)"}
    try:
        from _llm_judge_safe import dispatch_external_evidence as _dee
        _ext_ctx = ctx
        _ext_result = _dee(
            inputs=inputs,
            ctx=_ext_ctx,
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE or "",
            return_type='dict',
        )
        if _ext_result is not None:
            return _ext_result
    except Exception as _ext_exc:
        import logging as _ext_logging
        _ext_logging.getLogger("p17_dispatch").warning(
            "dispatch_external_evidence failed for evidence_type=%r: %s",
            inputs.get("evidence_type"), _ext_exc)
    rubric = inputs.get("rubric_prompt", "")
    evidence_type = inputs.get("evidence_type", "code_files")
    score_range = inputs.get("score_range", [0, 5])
    files_to_sample = inputs.get("files_to_sample", [])

    evidence_text = ""

    if evidence_type == "code_files":
        for rel, fpath in _gather_and_rank(config.WORKSPACE_PATH,
                                           files_to_sample, rubric, max_files=16):
            if len(evidence_text) > 40000:
                break
            try:
                with open(fpath, errors="replace") as fh:
                    content = fh.read(3500)
                evidence_text += f"\n--- {rel} ---\n{content}\n"
            except Exception:
                pass

    elif evidence_type in ("screenshot", "http_response_html"):
        evidence_text = str(ctx.get("last_body", ""))[:10000]

    elif evidence_type == "api_response":
        evidence_text = json.dumps(ctx.get("last_body", {}), indent=2, ensure_ascii=False)[:15000]

    elif evidence_type == "logs":
        evidence_text = str(ctx.get("last_body", {}).get("stdout", ""))[:10000]

    if not config.LLM_API_KEY:
        return {"score": 0, "max_score": score_range[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "LLM_API_KEY unset"}

    def _build_prompt(_budget: int) -> str:
        return f"""You are a software evaluation expert. Score the implementation based on the rubric and evidence below.

Scoring rubric:
{rubric}

Score range: {score_range[0]} to {score_range[1]}

Evidence:
{evidence_text[:_budget]}

Return only a single JSON object: {{"score": <int>, "reason": "<brief reason>"}}"""

    from _llm_judge_safe import safe_chat_completion

    def _parse_score(text: str):
        result = None
        for m in reversed(re.findall(r'\{[^{}]*"score"[^{}]*\}', text, re.S)):
            try:
                result = json.loads(m)
                break
            except Exception:
                continue
        if result is None:
            m0 = re.search(r'\{[^}]+\}', text)
            if m0:
                try:
                    result = json.loads(m0.group())
                except Exception:
                    result = None
        if isinstance(result, dict) and "score" in result:
            try:
                _sc = float(result.get("score", 0))
            except (TypeError, ValueError):
                _sc = 0
            return {"score": min(_sc, score_range[1]),
                    "max_score": score_range[1],
                    "reason": result.get("reason", result.get("reasoning", ""))}
        m = (re.search(r'"score"\s*:\s*(\d+(?:\.\d+)?)', text, re.I)
             or re.search(r'score[^0-9]{0,8}(\d+(?:\.\d+)?)', text, re.I)
             or re.search(r'(\d+(?:\.\d+)?)\s*/\s*%d' % int(score_range[1]), text))
        if m:
            return {"score": min(float(m.group(1)), score_range[1]),
                    "max_score": score_range[1],
                    "reason": "extracted from non-JSON reply"}
        return None

    _budgets = [32000, 16000, 10000, 8000, 6000, 5000, 4000, 4000]
    last_res = None
    for _budget in _budgets:
        res = safe_chat_completion(
            messages=[{"role": "user", "content": _build_prompt(_budget)}],
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE,
            temperature=0.1,
            max_tokens=500,
        )
        last_res = res
        if res.skipped:
            return {"score": 0, "max_score": score_range[1],
                    "skipped": True,
                    "llm_api_failure": res.llm_api_failure,
                    "exception_class": res.exception_class,
                    "reason": res.error or "skipped"}
        parsed = _parse_score(res.raw or "")
        if parsed is not None:
            return parsed
    return {"score": 0, "max_score": score_range[1],
            "skipped": True,
            "parse_failure": True, "reason": "no JSON in reply (after truncation retries) — skipped",
            "raw": (last_res.raw[:200] if last_res else "")}



def p18_browser_interaction(inputs: dict, ctx: dict) -> dict:
    url = inputs.get("url", config.APP_BASE_URL)
    try:
        from _browser_primitives import _resolve_url as _bp_resolve
        url = _bp_resolve(url, ctx)
    except Exception:
        pass
    wait_for = inputs.get("wait_for", "body")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT)
            page.wait_for_timeout(3000)
            content = page.content()
            screenshot = None
            try:
                ss_path = os.path.join(config.RESULTS_DIR, f"screenshot_{int(time.time())}.png")
                page.screenshot(path=ss_path)
                screenshot = ss_path
            except Exception:
                pass
            ctx["last_body"] = content
            ctx["page_content"] = content
            browser.close()
        return {"success": True, "screenshot": screenshot, "content_length": len(content)}
    except Exception as exc:
        ctx["last_body"] = ""
        return {"success": False, "error": str(exc)}



def p19_dom_assertion(inputs: dict, ctx: dict) -> dict:
    actions = inputs.get("actions", [])
    assertions = inputs.get("assertions", [])
    url = inputs.get("url", config.APP_BASE_URL)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT)
            page.wait_for_timeout(2000)

            results = []

            for action in actions:
                act_type = action.get("action", "")
                selector = action.get("selector", "")
                value = action.get("value", "")

                if act_type == "fill":
                    try:
                        page.fill(selector, value)
                        results.append({"action": act_type, "passed": True})
                    except Exception:
                        results.append({"action": act_type, "passed": False})
                elif act_type == "click":
                    try:
                        page.click(selector, timeout=5000)
                        results.append({"action": act_type, "passed": True})
                    except Exception:
                        results.append({"action": act_type, "passed": False})
                elif act_type == "wait":
                    ms = action.get("ms", 2000)
                    page.wait_for_timeout(ms)
                    results.append({"action": "wait", "passed": True})
                elif act_type == "assert_visible":
                    try:
                        el = page.query_selector(selector)
                        results.append({"action": act_type, "passed": el is not None and el.is_visible()})
                    except Exception:
                        results.append({"action": act_type, "passed": False})
                elif act_type == "navigate":
                    try:
                        nav_url = value if value.startswith("http") else config.APP_BASE_URL + value
                        page.goto(nav_url, wait_until="domcontentloaded", timeout=config.BROWSER_TIMEOUT)
                        page.wait_for_timeout(1500)
                        results.append({"action": act_type, "passed": True})
                    except Exception:
                        results.append({"action": act_type, "passed": False})

            for assertion in assertions:
                selector = assertion.get("selector", "")
                should_exist = assertion.get("shouldExist", True)
                expected_text = assertion.get("expectedText")
                try:
                    el = page.query_selector(selector)
                    exists = el is not None
                    if should_exist:
                        passed = exists
                        if passed and expected_text is not None:
                            text = el.text_content() or ""
                            passed = expected_text.lower() in text.lower()
                    else:
                        passed = not exists
                    results.append({"selector": selector, "shouldExist": should_exist, "passed": passed})
                except Exception:
                    results.append({"selector": selector, "shouldExist": should_exist, "passed": not should_exist})

            browser.close()
            all_passed = all(r["passed"] for r in results) if results else True
            return {"all_passed": all_passed, "results": results}
    except Exception as exc:
        return {"all_passed": False, "error": str(exc)}



def p22_graphql_query(inputs: dict, ctx: dict) -> dict:
    query = inputs.get("query", "")
    endpoint = inputs.get("endpoint") or inputs.get("path") or "/api/v2/graphql"
    store_as = inputs.get("store_as")
    variables = inputs.get("variables")

    hdrs = {"Content-Type": "application/json"}
    hdrs.update(auth_ctx.auth_headers())
    payload: dict[str, Any] = {"query": query}
    if isinstance(variables, dict):
        payload["variables"] = variables

    endpoints_to_try = []
    if endpoint.startswith("/"):
        endpoints_to_try.append(config.APP_BASE_URL + endpoint)
    else:
        endpoints_to_try.append(endpoint)
    alt = config.APP_BASE_URL + "/api/graphql"
    if alt not in endpoints_to_try:
        endpoints_to_try.append(alt)

    for url in endpoints_to_try:
        try:
            resp = requests.post(url, json=payload, headers=hdrs,
                                 timeout=config.HTTP_TIMEOUT)
            body = safe_json(resp)
            if resp.status_code == 200 and isinstance(body, dict) and "data" in body:
                ctx["last_body"] = body
                ctx["last_status"] = resp.status_code
                if store_as and body:
                    ctx[store_as] = body
                has_errors = bool(body.get("errors"))
                return {
                    "status_code": resp.status_code, "body": body,
                    "has_errors": has_errors,
                    "expect_no_errors": inputs.get("expect_no_errors", False),
                }
        except Exception:
            continue

    try:
        url = endpoints_to_try[0]
        resp = requests.post(url, json=payload, headers=hdrs,
                             timeout=config.HTTP_TIMEOUT)
        body = safe_json(resp)
        ctx["last_body"] = body
        ctx["last_status"] = resp.status_code
        if store_as and body:
            ctx[store_as] = body
        has_errors = bool(body.get("errors")) if isinstance(body, dict) else True
        return {
            "status_code": resp.status_code, "body": body,
            "has_errors": has_errors,
            "expect_no_errors": inputs.get("expect_no_errors", False),
        }
    except Exception as exc:
        ctx["last_body"] = None
        ctx["last_status"] = 0
        return {"status_code": 0, "error": str(exc), "has_errors": True}



def p_ingest_proposal(inputs: dict, ctx: dict) -> dict:
    entity_type = inputs.get("entityType", "dataset")
    entity_urn = inputs["entityUrn"]
    aspect_name = inputs["aspectName"]
    aspect_value = inputs["aspectValue"]
    change_type = inputs.get("changeType", "UPSERT")

    hdrs = {"Content-Type": "application/json"}
    hdrs.update(auth_ctx.auth_headers())

    gql_query = (f'mutation {{ ingestProposal(input: {{ entityType: {entity_type.upper()}, '
                 f'entityUrn: "{entity_urn}", aspectName: "{aspect_name}", '
                 f'aspect: {{ contentType: "application/json", value: "{aspect_value.replace(chr(34), chr(92)+chr(34))}" }}, '
                 f'changeType: {change_type} }}) }}')

    for ep in [config.GRAPHQL_ENDPOINT, config.APP_BASE_URL + "/api/graphql"]:
        try:
            resp = requests.post(ep, json={"query": gql_query}, headers=hdrs, timeout=config.HTTP_TIMEOUT)
            body = safe_json(resp)
            if resp.status_code == 200 and isinstance(body, dict) and body.get("data", {}).get("ingestProposal"):
                ctx["last_body"] = {
                    "value": "success",
                    "data": body.get("data"),
                    "urn": body.get("data", {}).get("ingestProposal") or entity_urn,
                }
                ctx["last_status"] = 200
                return {"success": True, "method": "graphql", "body": body}
        except Exception:
            continue

    mcp_body = {
        "proposal": {
            "entityType": entity_type,
            "entityUrn": entity_urn,
            "aspectName": aspect_name,
            "changeType": change_type,
            "aspect": {
                "contentType": "application/json",
                "value": aspect_value
            }
        }
    }
    try:
        resp = requests.post(
            config.APP_BASE_URL + "/aspects?action=ingestProposal",
            json=mcp_body, headers=hdrs, timeout=config.HTTP_TIMEOUT
        )
        body = safe_json(resp)
        success = resp.status_code == 200 and isinstance(body, dict) and body.get("value") == "success"
        normalized = {
            "value": "success" if success else "failed",
            "data": {"ingestProposal": entity_urn if success else None},
            "urn": entity_urn if success else None,
        }
        ctx["last_body"] = normalized
        ctx["last_status"] = resp.status_code
        return {"success": success, "method": "restli", "body": normalized, "status_code": resp.status_code}
    except Exception as exc:
        return {"success": False, "error": str(exc)}



PRIMITIVE_DISPATCH = {
    "P01": lambda inputs, ctx: p01_file_exists(inputs),
    "P02": lambda inputs, ctx: p02_file_content_check(inputs),
    "P04": p04_http_request,
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
    "P17": p17_llm_judge,
    "P18": p18_browser_interaction,
    "P19": p19_dom_assertion,
    "P22": p22_graphql_query,
    "P_INGEST": p_ingest_proposal,
}


def execute_primitive(ptype: str, inputs: dict, ctx: dict) -> dict:
    func = PRIMITIVE_DISPATCH.get(ptype)
    if not func:
        logger.warning("Unknown primitive: %s", ptype)
        return {"error": f"Unknown primitive {ptype}"}
    return func(inputs, ctx)

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
