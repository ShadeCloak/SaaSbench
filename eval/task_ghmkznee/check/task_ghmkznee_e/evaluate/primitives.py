import os
import re
import glob
import json
import subprocess
import psycopg2
import requests
from dataclasses import dataclass, field
from typing import Any
from config import (WORKSPACE_DIR, API_BASE_URL, APP_BASE_URL,
                    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
                    APP_CONTAINER, TEST_USERS, HTTP_TIMEOUT,
                    LLM_API_KEY, LLM_API_BASE, LLM_MODEL)
from utils import context, get_auth_headers


@dataclass
class PrimitiveResult:
    passed: bool
    evidence: dict = field(default_factory=dict)
    message: str = ""


def _db_conn():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASSWORD)


def p01_file_exists(inputs):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    ftype = inputs.get("type", "file")
    exists = os.path.isfile(path) if ftype == "file" else os.path.isdir(path)
    return PrimitiveResult(passed=exists, evidence={"path": path, "exists": exists})


def p02_file_content_match(inputs):
    path = os.path.join(WORKSPACE_DIR, inputs["path"])
    if not os.path.isfile(path):
        return PrimitiveResult(passed=False, message=f"File not found: {path}")
    content = open(path).read()
    pattern = inputs["pattern"]
    if inputs.get("match_type") == "regex":
        matches = re.findall(pattern, content)
    else:
        matches = [m for m in [pattern] if m in content]
    return PrimitiveResult(passed=len(matches) > 0,
                           evidence={"match_count": len(matches), "pattern": pattern})


def p03_file_count(inputs):
    base = os.path.join(WORKSPACE_DIR, inputs.get("base_dir", "."))
    files = glob.glob(os.path.join(base, inputs["glob"]), recursive=True)
    min_expected = inputs.get("min_expected", 1)
    return PrimitiveResult(passed=len(files) >= min_expected,
                           evidence={"count": len(files), "min_expected": min_expected})


def p04_http_request(inputs):
    method = inputs.get("method", "GET").upper()
    path = inputs["path"]
    url = path if path.startswith("http") else APP_BASE_URL + path
    body = inputs.get("body")
    params = inputs.get("params")
    timeout = inputs.get("timeout", HTTP_TIMEOUT)
    headers = {"Content-Type": "application/json", **get_auth_headers()}
    try:
        resp = requests.request(method, url, json=body, params=params,
                                headers=headers, timeout=timeout, allow_redirects=False)
        try:
            resp_json = resp.json()
        except Exception:
            resp_json = None
        context["last_response"] = resp
        context["last_response_json"] = resp_json
        context["last_status"] = resp.status_code
        context.setdefault("response_log", []).append({
            "method": method, "path": path, "status": resp.status_code,
            "body": resp_json if resp_json is not None else resp.text[:800],
            "content_type": resp.headers.get("Content-Type", ""),
        })
        if resp_json and isinstance(resp_json, dict):
            for key in ["uid", "id", "orgId", "teamId", "key", "accessToken", "silenceID"]:
                if key in resp_json:
                    context[key] = resp_json[key]
            if "datasource" in resp_json and isinstance(resp_json["datasource"], dict):
                context["dsUid"] = resp_json["datasource"].get("uid")
            if "result" in resp_json and isinstance(resp_json["result"], dict):
                if "uid" in resp_json["result"]:
                    context["uid"] = resp_json["result"]["uid"]
            if method == "POST":
                if path.startswith("/api/serviceaccounts") and "id" in resp_json and "tokens" not in path:
                    context["saId"] = resp_json["id"]
                if path.startswith("/api/v1/provisioning/alert-rules") and "uid" in resp_json:
                    context["ruleUid"] = resp_json["uid"]
                if path == "/api/dashboards/db" and isinstance(resp_json, dict):
                    if "uid" in resp_json:
                        context["dashboardUid"] = resp_json["uid"]
                if path.startswith("/api/teams") and "teamId" in resp_json:
                    context["teamId"] = resp_json["teamId"]
        return PrimitiveResult(passed=True,
                               evidence={"status": resp.status_code, "body": resp_json or resp.text[:500]})
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p05_api_crud(inputs):
    resource = inputs["resource"]
    create_body = inputs.get("create_body", {})
    resp = requests.post(APP_BASE_URL + resource, json=create_body,
                         headers={**get_auth_headers(), "Content-Type": "application/json"},
                         timeout=HTTP_TIMEOUT)
    if resp.status_code not in (200, 201):
        return PrimitiveResult(passed=False, message=f"Create failed: {resp.status_code}")
    data = resp.json()
    entity_id = data.get("id") or data.get("uid")
    if not entity_id:
        return PrimitiveResult(passed=False, message="No id in create response")
    get_resp = requests.get(f"{APP_BASE_URL}{resource}/{entity_id}",
                            headers=get_auth_headers(), timeout=HTTP_TIMEOUT)
    del_resp = requests.delete(f"{APP_BASE_URL}{resource}/{entity_id}",
                               headers=get_auth_headers(), timeout=HTTP_TIMEOUT)
    return PrimitiveResult(
        passed=get_resp.status_code == 200 and del_resp.status_code in (200, 204),
        evidence={"create": resp.status_code, "get": get_resp.status_code, "delete": del_resp.status_code}
    )


def p06_json_schema_match(inputs):
    resp_json = context.get("last_response_json")
    if not resp_json:
        return PrimitiveResult(passed=False, message="No response JSON in context")
    required = inputs.get("required_fields", [])
    missing = [f for f in required if f not in resp_json]
    return PrimitiveResult(passed=len(missing) == 0,
                           evidence={"missing_fields": missing})


def _resolve_json_path(data, path):
    if data is None or not path:
        return None
    if path == "$":
        return data

    stripped = path.lstrip("$.")

    filter_match = re.match(r'\[\?\(@\.(\w+)==[\'"](.+)[\'"]\)\]', stripped)
    if filter_match and isinstance(data, list):
        field, value = filter_match.groups()
        matches = [item for item in data if isinstance(item, dict) and str(item.get(field)) == value]
        return matches[0] if matches else None

    parts = stripped.split(".")
    current = data
    for part in parts:
        if part == "length":
            if isinstance(current, (list, dict)):
                return len(current)
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            if part.isdigit():
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            elif part.startswith("[") and part.endswith("]"):
                inner = part[1:-1]
                if inner.isdigit():
                    idx = int(inner)
                    current = current[idx] if idx < len(current) else None
                elif inner.startswith("?"):
                    fm = re.match(r'\?\(@\.(\w+)==[\'"](.+)[\'"]\)', inner)
                    if fm:
                        field, value = fm.groups()
                        matches = [item for item in current if isinstance(item, dict) and str(item.get(field)) == value]
                        current = matches[0] if matches else None
                    else:
                        return None
                elif inner == "-1":
                    current = current[-1] if current else None
                else:
                    return None
            else:
                return None
        else:
            return None
    return current


def p07_json_value_assert(inputs):
    resp_json = context.get("last_response_json")
    if resp_json is None:
        return PrimitiveResult(passed=False, message="No response JSON")
    assertions = inputs.get("assertions", [])
    results = []
    all_passed = True
    for a in assertions:
        path = a.get("path", "")
        actual = _resolve_json_path(resp_json, path)
        op = a.get("operator", "eq")
        expected = a.get("expected")
        if op == "exists":
            passed = actual is not None
        elif op == "eq" or op not in ("gte", "lte", "contains", "not_contains", "is_array", "is_object"):
            passed = actual == expected
        elif op == "gte":
            passed = actual is not None and actual >= expected
        elif op == "lte":
            passed = actual is not None and actual <= expected
        elif op == "contains":
            passed = actual is not None and str(expected) in str(actual)
        elif op == "not_contains":
            passed = actual is not None and str(expected) not in str(actual)
        elif op == "is_array":
            passed = isinstance(actual if path == "$" else resp_json, list)
        elif op == "is_object":
            passed = isinstance(actual if path == "$" else resp_json, dict)
        else:
            passed = actual == expected
        if not passed:
            all_passed = False
        results.append({"path": path, "expected": expected, "actual": actual, "op": op, "passed": passed})
    return PrimitiveResult(passed=all_passed, evidence={"assertions": results})


def p08_db_query(inputs):
    query = inputs["query"]
    try:
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute(query)
        if query.strip().upper().startswith("SELECT"):
            rows = cur.fetchall()
            conn.close()
            return PrimitiveResult(passed=True, evidence={"rows": len(rows), "data": str(rows[:5])})
        else:
            conn.commit()
            conn.close()
            return PrimitiveResult(passed=True, evidence={"affected": cur.rowcount})
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p09_db_table_exists(inputs):
    tables = inputs["tables"]
    try:
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        existing = {row[0] for row in cur.fetchall()}
        conn.close()
        found = [t for t in tables if t in existing]
        missing = [t for t in tables if t not in existing]
        ratio = len(found) / len(tables) if tables else 0
        return PrimitiveResult(passed=ratio >= 0.5,
                               evidence={"found": found, "missing": missing, "ratio": ratio})
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p10_db_column_check(inputs):
    table = inputs["table"]
    expected = inputs["expected_columns"]
    try:
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (table,))
        existing = {row[0] for row in cur.fetchall()}
        conn.close()
        found = [c for c in expected if c in existing]
        missing = [c for c in expected if c not in existing]
        ratio = len(found) / len(expected) if expected else 0
        return PrimitiveResult(passed=ratio >= 0.5,
                               evidence={"found": found, "missing": missing, "ratio": ratio})
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p11_db_index_check(inputs):
    table = inputs["table"]
    expected_indexes = inputs.get("expected_indexes", [])
    try:
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT indexname, indexdef FROM pg_indexes
            WHERE tablename = %s AND schemaname = 'public'
        """, (table,))
        idx_defs = {row[0]: row[1] for row in cur.fetchall()}
        conn.close()
        found = 0
        for ei in expected_indexes:
            cols = ei["columns"]
            for _, defn in idx_defs.items():
                if all(c in defn for c in cols):
                    found += 1
                    break
        ratio = found / len(expected_indexes) if expected_indexes else 1
        return PrimitiveResult(passed=ratio >= 0.5,
                               evidence={"found": found, "total": len(expected_indexes), "indexes": list(idx_defs.keys())})
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p12_docker_exec(inputs):
    command = inputs["command"]
    container = inputs.get("container", APP_CONTAINER)
    try:
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c", command],
            capture_output=True, text=True, timeout=30
        )
        return PrimitiveResult(
            passed=result.returncode == 0,
            evidence={"exit_code": result.returncode, "stdout": result.stdout[:500], "stderr": result.stderr[:500]}
        )
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p13_auth_login(inputs):
    role = inputs.get("role", "admin")
    creds = inputs.get("credentials") or TEST_USERS.get(role, TEST_USERS["admin"])
    user = creds.get("user") or creds.get("login", "admin")
    password = creds.get("password", "admin")

    if inputs.get("method") == "basic_auth":
        from requests.auth import HTTPBasicAuth
        try:
            resp = requests.get(f"{API_BASE_URL}/user", auth=HTTPBasicAuth(user, password), timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                import base64
                token = base64.b64encode(f"{user}:{password}".encode()).decode()
                context["auth_token"] = None
                context["auth_headers"] = {"Authorization": f"Basic {token}"}
                context["current_role"] = role
                return PrimitiveResult(passed=True, evidence={"method": "basic_auth", "role": role})
        except Exception:
            pass

    try:
        resp = requests.post(f"{APP_BASE_URL}/login",
                             json={"user": user, "password": password}, timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            cookies = resp.cookies
            context["auth_headers"] = {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}
            context["auth_token"] = None
            context["current_role"] = role
            return PrimitiveResult(passed=True, evidence={"method": "session", "role": role})
    except Exception:
        pass

    return PrimitiveResult(passed=False, message=f"Auth failed for role={role}, user={user}")


def p14_permission_check(inputs):
    action = inputs["action"]
    expected = inputs["expected_result"]
    expected_status = inputs.get("expected_status")
    body = inputs.get("body")

    parts = action.split(" ", 1)
    method = parts[0]
    path = parts[1] if len(parts) > 1 else "/"
    url = APP_BASE_URL + path

    try:
        resp = requests.request(method, url, json=body,
                                headers={**get_auth_headers(), "Content-Type": "application/json"},
                                timeout=HTTP_TIMEOUT)
        if expected == "denied":
            passed = resp.status_code in (401, 403)
            if expected_status:
                passed = resp.status_code == expected_status or resp.status_code in (401, 403)
        else:
            passed = resp.status_code in (200, 201, 202)
            if expected_status:
                passed = resp.status_code == expected_status

        return PrimitiveResult(passed=passed,
                               evidence={"action": action, "expected": expected,
                                         "actual_status": resp.status_code})
    except Exception as e:
        return PrimitiveResult(passed=False, message=str(e))


def p15_status_code_assert(inputs):
    status = context.get("last_status", 0)
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
        passed = status in accepted
    else:
        passed = 200 <= status < 300

    return PrimitiveResult(
        passed=passed,
        evidence={"expected": sorted(accepted) if accepted else "2xx",
                  "actual": status},
        message=f"Status: {status} (expected {sorted(accepted) if accepted else '2xx'})",
    )


def p16_response_time_check(inputs):
    resp = context.get("last_response")
    if resp and hasattr(resp, "elapsed"):
        ms = resp.elapsed.total_seconds() * 1000
        max_ms = inputs.get("max_ms", 5000)
        return PrimitiveResult(passed=ms <= max_ms, evidence={"elapsed_ms": ms, "max_ms": max_ms})
    return PrimitiveResult(passed=False, message="No response timing data")


_CODE_EXTS = {".go", ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".rb",
              ".java", ".kt", ".rs", ".php", ".ex", ".exs", ".scala", ".c",
              ".cc", ".cpp", ".h", ".sql", ".proto"}
_MARKUP_EXTS = {".html", ".htm", ".scss", ".css", ".md", ".txt", ".json",
                ".yaml", ".yml", ".toml", ".lock", ".svg", ".snap"}
_SKIP_SUBSTR = ("/node_modules/", "/dist/", "/build/", "/target/", "/.git/",
                "/vendor/", "/__pycache__/", "/coverage/", "/.next/",
                "/testdata/", "/mocks/", "/mock/", "/generated/", "/.yarn/")
_RUBRIC_STOP = set(
    "the a an and or of to in for with on at by from is are be this that goal "
    "evidence score range integer criteria judge quality design equivalent does "
    "implementation uses use using used must should each any all its their code "
    "codebase source helpers logic definitions handling whether well overall".split())


def _gather_and_rank(root, files_to_sample, rubric, max_files=16):
    root = (root or "").rstrip("/")
    entries = list(files_to_sample) or ["."]
    cands = []
    for ent in entries:
        base = os.path.join(root, str(ent))
        if os.path.isfile(base):
            cands.append(base)
            continue
        if not os.path.isdir(base):
            try:
                cands.extend(p for p in glob.glob(base, recursive=True)
                             if os.path.isfile(p))
            except Exception:
                pass
            continue
        n = 0
        for dp, dirs, fns in os.walk(base):
            low = ("/" + dp.lower() + "/")
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
    for p in re.findall(r"(?:pkg|internal|src|public|packages|app|lib)/[\w./*-]+",
                        rubric or ""):
        for seg in re.split(r"[/.*]", p):
            if len(seg) >= 3:
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
                sc += 8
        for w in kws:
            if w in low:
                sc += 3
        sc += 2.0 if ext in _CODE_EXTS else (0.0 if ext in _MARKUP_EXTS else 0.5)
        if "_test." in base or ".test." in base or ".spec." in base:
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
    evidence_type = inputs.get("evidence_type", "")
    rubric = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])

    evidence_text = ""
    if evidence_type == "http_response_html":
        resp = context.get("last_response")
        evidence_text = resp.text[:3000] if resp else "No response"
    elif evidence_type == "http_responses":
        log = context.get("response_log", []) or []
        errs, seen_k = [], set()
        for e in log:
            st = e.get("status", 0)
            if isinstance(st, int) and st >= 400:
                k = (st, e.get("path", ""))
                if k not in seen_k:
                    seen_k.add(k)
                    errs.append(e)
        chosen = errs if errs else log[-12:]
        if chosen:
            parts = []
            for i, e in enumerate(chosen[:12], 1):
                parts.append(
                    f"--- response {i}: {e.get('method','GET')} {e.get('path','')} "
                    f"-> {e.get('status','')} ({e.get('content_type','')}) ---\n"
                    + json.dumps(e.get("body", ""), indent=2, default=str)[:1800])
            evidence_text = "\n\n".join(parts)
        else:
            evidence_text = ""
    elif evidence_type == "code_files":
        files_to_sample = inputs.get("files_to_sample", [])
        for rel, fp in _gather_and_rank(WORKSPACE_DIR, files_to_sample, rubric,
                                        max_files=16):
            if len(evidence_text) > 38000:
                break
            try:
                with open(fp, errors="replace") as _fh:
                    evidence_text += f"\n--- {rel} ---\n" + _fh.read()[:3000]
            except Exception:
                pass

    prompt = f"""You are an evaluation judge. Score the following evidence on a scale of {score_range[0]} to {score_range[1]}.

Rubric: {rubric}

Evidence:
{evidence_text[:24000]}

Respond with ONLY a JSON object: {{"score": <number>, "reasoning": "<brief explanation>"}}"""

    from _llm_judge_safe import safe_chat_completion

    _judge_messages = [{"role": "user", "content": prompt}]

    def _judge_call(msgs):
        return safe_chat_completion(
            messages=msgs,
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            temperature=0.1,
            max_tokens=1024,
        )

    res = _judge_call(_judge_messages)

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

    def _try_parse(_res):
        try:
            return _robust_judge_json(_res.raw)
        except Exception:
            return None

    result = None if res.skipped else _try_parse(res)
    if result is None:
        retry = _judge_call(_judge_messages + [
            {"role": "assistant", "content": (res.raw or "")[:2000]},
            {"role": "user", "content": (
                f"You did not output a score. Reply with ONLY a single integer "
                f"between {score_range[0]} and {score_range[1]} — no words, no "
                f"explanation, just the number."
            )},
        ])
        if not retry.skipped:
            result = _try_parse(retry)

    if result is None:
        _infra = bool(res.skipped) or bool(retry.skipped)
        return PrimitiveResult(passed=False,
                               evidence={"skipped": True, "llm_api_failure": _infra,
                                         "parse_failure": not _infra,
                                         "raw": (res.raw or "")[:200]},
                               message="LLM judge SKIPPED (no usable verdict after retries)")

    score = max(score_range[0], min(score_range[1], result.get("score", 0)))
    return PrimitiveResult(passed=score > score_range[0],
                           evidence={"score": score, "reasoning": result.get("reasoning", "")})


PRIMITIVE_MAP = {
    "P01": p01_file_exists, "P02": p02_file_content_match, "P03": p03_file_count,
    "P04": p04_http_request, "P05": p05_api_crud, "P06": p06_json_schema_match,
    "P07": p07_json_value_assert, "P08": p08_db_query, "P09": p09_db_table_exists,
    "P10": p10_db_column_check, "P11": p11_db_index_check, "P12": p12_docker_exec,
    "P13": p13_auth_login, "P14": p14_permission_check, "P15": p15_status_code_assert,
    "P16": p16_response_time_check, "P17": p17_llm_judge,
}

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
