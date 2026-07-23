from __future__ import annotations

import glob as glob_mod
import json
import logging
import os
import re
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

import requests

import config
from utils import (
    EvalContext, ChainResult, http_request, db_connect, db_query,
    db_query_with_retry, docker_exec, json_path_get,
)

logger = logging.getLogger("eval")


_LAST_JUDGE_INFO: dict = {}


def get_last_judge_info() -> dict:
    return dict(_LAST_JUDGE_INFO)



def p01_file_exists(inputs: dict, ctx: EvalContext) -> bool:
    path = ctx.resolve(inputs["path"])
    rc, out, _ = docker_exec(f"test -e {path} && echo EXISTS", ctx)
    return "EXISTS" in out



def p02_file_content_match(inputs: dict, ctx: EvalContext) -> bool:
    path = ctx.resolve(inputs["path"])
    pattern = ctx.resolve(inputs["pattern"])
    match_type = inputs.get("match_type", "contains")
    rc, out, _ = docker_exec(f"cat {path} 2>/dev/null", ctx)
    if rc != 0:
        return False
    if match_type == "contains":
        return pattern in out
    if match_type == "regex":
        return bool(re.search(pattern, out))
    return False



def p03_file_count(inputs: dict, ctx: EvalContext) -> bool:
    g = ctx.resolve(inputs.get("glob", "**/*"))
    base = ctx.resolve(inputs.get("base_dir", "."))
    min_exp = inputs.get("min_expected", 1)
    fname = g.split("/")[-1] if "/" in g else g
    rc, out, _ = docker_exec(f"find {base} -name '{fname}' 2>/dev/null | wc -l", ctx)
    try:
        count = int(out.strip())
    except (ValueError, AttributeError):
        count = 0
    ctx.captured["_p03_count"] = count
    return count >= min_exp



def p04_http_request(inputs: dict, ctx: EvalContext) -> bool:
    method = inputs["method"]
    path = ctx.resolve(inputs["path"])
    body = ctx.resolve(inputs.get("body"))
    headers = ctx.resolve(inputs.get("headers")) if inputs.get("headers") else None
    timeout = inputs.get("timeout", config.HTTP_TIMEOUT)
    capture_as = inputs.get("capture_response_as")

    try:
        resp = http_request(method, path, ctx=ctx, body=body, headers=headers, timeout=timeout)
    except Exception:
        return False

    if capture_as:
        try:
            ctx.captured[capture_as] = resp.json()
        except (ValueError, json.JSONDecodeError):
            ctx.captured[capture_as] = resp.text
    return True



def p06_json_schema_match(inputs: dict, ctx: EvalContext) -> bool:
    data = _get_response_data(inputs, ctx)
    if data is None:
        return False
    required = inputs.get("required_fields", [])
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return False
    missing = [f for f in required if f not in data]
    return len(missing) == 0



def p07_json_value_assert(inputs: dict, ctx: EvalContext) -> bool:
    data = _get_response_data(inputs, ctx)
    if data is None:
        return False
    assertions = inputs.get("assertions", [])
    for a in assertions:
        path = a["path"]
        actual = json_path_get(data, path)
        capture_as = a.get("capture_as")
        if capture_as and actual is not None:
            ctx.captured[capture_as] = actual

        op = a.get("op", "==")
        expected = ctx.resolve(a.get("expected")) if "expected" in a else None

        if op == "not_null":
            if actual is None:
                return False
        elif op == "contains":
            if actual is None or str(expected) not in str(actual):
                return False
        elif op == ">=":
            if actual is None or actual < expected:
                return False
        elif op == "<=":
            if actual is None or actual > expected:
                return False
        elif op == "in":
            if actual not in expected:
                return False
        elif op == "==":
            tolerance = a.get("tolerance", 0)
            if tolerance and isinstance(actual, (int, float)):
                if abs(actual - expected) > tolerance:
                    return False
            elif actual != expected:
                if isinstance(actual, (int, float)) and isinstance(expected, str):
                    try:
                        if actual != type(actual)(expected):
                            return False
                    except (ValueError, TypeError):
                        return False
                elif isinstance(expected, (int, float)) and isinstance(actual, str):
                    try:
                        if expected != type(expected)(actual):
                            return False
                    except (ValueError, TypeError):
                        return False
                else:
                    return False
        else:
            if actual != expected:
                return False
    return True



def p08_db_query(inputs: dict, ctx: EvalContext) -> bool:
    sql = ctx.resolve(inputs["sql"])
    expected = ctx.resolve(inputs.get("expected_result", {}))
    retry_ms = inputs.get("retry_ms", 0)

    if retry_ms:
        rows = db_query_with_retry(sql, expected, ctx, retry_ms)
    else:
        rows = db_query(sql, ctx)

    if not rows:
        return not expected
    row = rows[0]

    for k, v in expected.items():
        actual = row.get(k)
        if isinstance(v, dict) and "op" in v:
            from utils import _compare_op
            if not _compare_op(actual, v):
                return False
        elif isinstance(v, bool):
            if bool(actual) != v:
                return False
        elif actual != v:
            return False
    return True



def p09_db_table_exists(inputs: dict, ctx: EvalContext) -> tuple[bool, float]:
    tables = inputs["tables"]
    sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    rows = db_query(sql, ctx)
    existing = {r["table_name"] for r in rows}
    found = [t for t in tables if t in existing]
    ratio = len(found) / len(tables) if tables else 1.0
    return len(found) == len(tables), ratio



def p10_db_column_check(inputs: dict, ctx: EvalContext) -> tuple[bool, float]:
    table = inputs["table"]
    expected = inputs["expected_columns"]
    sql = f"SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='{table}'"
    rows = db_query(sql, ctx)
    existing = {r["column_name"] for r in rows}
    found = [c for c in expected if c in existing]
    ratio = len(found) / len(expected) if expected else 1.0
    return len(found) == len(expected), ratio



def p11_db_index_check(inputs: dict, ctx: EvalContext) -> tuple[bool, float]:
    table = inputs["table"]
    expected_indexes = inputs["expected_indexes"]
    sql = f"""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = '{table}'
    """
    rows = db_query(sql, ctx)
    found_count = 0
    for ei in expected_indexes:
        cols = ei["columns"]
        for row in rows:
            indexdef = row.get("indexdef", "")
            if all(c in indexdef for c in cols):
                found_count += 1
                break
    ratio = found_count / len(expected_indexes) if expected_indexes else 1.0
    return found_count == len(expected_indexes), ratio



def p12_docker_exec(inputs: dict, ctx: EvalContext) -> bool:
    command = inputs["command"]
    expect_success = inputs.get("expect_success", True)
    expect_contains = inputs.get("expect_output_contains")
    capture_as = inputs.get("capture_stdout_as")

    rc, stdout, stderr = docker_exec(command, ctx, timeout=120)

    if capture_as and stdout:
        lines = [l for l in stdout.strip().splitlines() if l.strip()]
        if lines:
            ctx.captured[capture_as] = lines[-1].strip()

    if expect_success and rc != 0:
        logger.warning("P12 command failed (rc=%d): %s", rc, stderr[:200])
        return False
    if expect_contains and expect_contains not in stdout:
        logger.warning("P12 output missing '%s'", expect_contains)
        return False
    return True



def p13_auth_login(inputs: dict, ctx: EvalContext) -> bool:
    role = inputs.get("role", "admin")
    if role in ctx.auth_tokens:
        ctx.active_role = role
        return True

    if role == "admin" and "admin_token" in ctx.captured:
        ctx.auth_tokens["admin"] = ctx.captured["admin_token"]
        ctx.active_role = "admin"
        return True

    logger.warning("P13: no token available for role '%s'", role)
    return False



def p14_permission_check(inputs: dict, ctx: EvalContext) -> bool:
    role = inputs.get("role", "user")
    action = inputs["action"]
    token = ctx.resolve(inputs.get("token", ""))
    expected_result = inputs.get("expected_result", "allowed")
    expected_status = inputs.get("expected_status")

    parts = action.split(" ", 1)
    method = parts[0]
    path = parts[1] if len(parts) > 1 else "/"

    headers = {"X-Auth-Token": token} if token else {}
    try:
        resp = http_request(method, path, ctx=ctx, headers=headers)
    except Exception:
        return expected_result == "denied"

    if expected_result == "denied":
        return resp.status_code in (401, 403, 404, expected_status or 403)
    if expected_result == "allowed":
        ok = resp.status_code < 400
        if expected_status:
            ok = resp.status_code == expected_status
        return ok
    return False



def p15_status_code_assert(inputs: dict, ctx: EvalContext) -> bool:
    resp = ctx.last_response
    if resp is None:
        return False
    expected = inputs.get("expected_status")
    acceptable = inputs.get("acceptable_statuses") or inputs.get("acceptable")
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

    actual = getattr(resp, "status_code", 0)
    try: actual_i = int(actual)
    except (TypeError, ValueError): actual_i = 0

    if accepted:
        passed = actual_i in accepted
    elif expected is None and not acceptable:
        passed = True
    else:
        passed = 200 <= actual_i < 300

    if not passed:
        try:
            from _inclusivity import _is_idempotent_success, _is_idempotent_delete_success
            body = ""
            try:
                body = resp.text if hasattr(resp, "text") else str(getattr(resp, "content", ""))
            except Exception:
                pass
            method = ""
            try:
                req = getattr(resp, "request", None)
                method = (getattr(req, "method", "") or "").upper()
            except Exception:
                pass
            if _is_idempotent_success(actual_i, body, accepted) or _is_idempotent_delete_success(method, actual_i, accepted):
                passed = True
        except Exception:
            pass

    return passed



def p17_llm_judge(inputs: dict, ctx: EvalContext) -> float:
    _LAST_JUDGE_INFO.clear()
    if not (config.LLM_API_KEY or "").strip():
        _LAST_JUDGE_INFO.update({
            "skipped": True,
            "llm_api_failure": False,
            "reason": "LLM_API_KEY unset",
        })
        return 0.0
    def _llm_dump(record):
        import os, json
        path = os.environ.get("SAASBENCH_DUMP_LLM")
        if not path:
            return
        try:
            with open(path, "a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass
    try:
        from _llm_judge_safe import dispatch_external_evidence as _dee
        _ext_ctx = ctx
        _ext_result = _dee(
            inputs=inputs,
            ctx=_ext_ctx,
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_API_BASE or "",
            return_type='float',
        )
        if _ext_result is not None:
            return _ext_result
    except Exception as _ext_exc:
        import logging as _ext_logging
        _ext_logging.getLogger("p17_dispatch").warning(
            "dispatch_external_evidence failed for evidence_type=%r: %s",
            inputs.get("evidence_type"), _ext_exc)
    _LAST_JUDGE_INFO.clear()

    rubric = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 5])
    evidence_type = inputs.get("evidence_type", "code_files")

    evidence_text = ""
    if evidence_type == "http_response_html":
        resp = ctx.last_response
        if resp:
            evidence_text = resp.text[:8000]
    elif evidence_type == "code_files":
        files_to_sample = inputs.get("files_to_sample", [])
        per_fp_budget = 8000 // max(1, len(files_to_sample))
        find_glob = (
            r"\( -name '*.rb' -o -name '*.yml' -o -name '*.yaml' -o -name '*.json' "
            r"-o -name '*.vue' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' -o -name '*.jsx' "
            r"-o -name '*.erb' -o -name '*.html.erb' -o -name '*.html' "
            r"-o -name '*.scss' -o -name '*.css' \)"
        )
        for fp in files_to_sample:
            rc_isfile, _, _ = docker_exec(f"test -f {fp}", ctx)
            if rc_isfile == 0:
                _, content, _ = docker_exec(f"head -200 {fp} 2>/dev/null", ctx)
                if content:
                    if len(content) > per_fp_budget:
                        content = content[:per_fp_budget] + "\n… [truncated]\n"
                    evidence_text += f"\n--- {fp} ---\n{content}\n"
                    _, _nlines, _ = docker_exec(f"wc -l < {fp} 2>/dev/null", ctx)
                    try:
                        if int((_nlines or "0").strip()) > 200:
                            _, _outline, _ = docker_exec(
                                f"grep -nE '^[A-Za-z]' {fp} 2>/dev/null | head -80", ctx)
                            if _outline and _outline.strip():
                                evidence_text += f"\n--- {fp} (top-level keys outline) ---\n{_outline}\n"
                    except Exception:
                        pass
                if len(evidence_text) > 12000:
                    break
                continue
            rc, out, _ = docker_exec(f"find {fp} -type f {find_glob} 2>/dev/null | head -20", ctx)
            if out:
                fp_chars = 0
                for fn in out.strip().splitlines()[:5]:
                    rc2, content, _ = docker_exec(f"head -80 {fn.strip()} 2>/dev/null", ctx)
                    if content:
                        evidence_text += f"\n--- {fn.strip()} ---\n{content}\n"
                        fp_chars += len(content)
                        if fp_chars >= per_fp_budget:
                            break
            if len(evidence_text) > 12000:
                break

    if not evidence_text.strip() and evidence_type == "code_files":
        for _regather in range(4):
            time.sleep(2)
            for fp in inputs.get("files_to_sample", []):
                rc_isfile, _, _ = docker_exec(f"test -f {fp}", ctx)
                if rc_isfile == 0:
                    _, content, _ = docker_exec(f"head -200 {fp} 2>/dev/null", ctx)
                    if content:
                        evidence_text += f"\n--- {fp} ---\n{content}\n"
                    if len(evidence_text) > 12000:
                        break
                    continue
                rc, out, _ = docker_exec(f"find {fp} -type f {find_glob} 2>/dev/null | head -20", ctx)
                if out:
                    fp_chars = 0
                    for fn in out.strip().splitlines()[:5]:
                        _, content, _ = docker_exec(f"head -80 {fn.strip()} 2>/dev/null", ctx)
                        if content:
                            evidence_text += f"\n--- {fn.strip()} ---\n{content}\n"
                            fp_chars += len(content)
                            if fp_chars >= per_fp_budget:
                                break
                if len(evidence_text) > 12000:
                    break
            if evidence_text.strip():
                break

    if not evidence_text.strip():
        _llm_dump({
            "phase": "evidence_empty",
            "node_id": (ctx.current_node_id if hasattr(ctx, 'current_node_id') else None),
            "evidence_type": evidence_type,
            "files_to_sample": inputs.get("files_to_sample", []),
            "score": 0.0,
            "reason": "evidence_text empty after sampling",
        })
        return 0.0

    prompt = f"""You are a strict, terse code reviewer. Grade the evidence against the rubric.

Rubric:
{rubric}

Score range: integer between {score_range[0]} and {score_range[1]} (inclusive).

Evidence:
{evidence_text[:10000]}

CRITICAL OUTPUT FORMAT:
Reply with ONE integer between {score_range[0]} and {score_range[1]} and NOTHING ELSE.
No reasoning. No markdown. No quotes. No "Score:" prefix. No newline before the number.
Your entire reply must be just the digit, e.g. for a score of 3 reply exactly: 3"""

    from _llm_judge_safe import safe_chat_completion

    res = safe_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=config.LLM_MODEL,
        api_key=config.LLM_API_KEY,
        api_base=config.LLM_API_BASE,
        temperature=0.0,
        max_tokens=8192,
    )

    if res.skipped:
        _LAST_JUDGE_INFO.update({
            "skipped": True,
            "llm_api_failure": res.llm_api_failure,
            "exception_class": res.exception_class,
            "reason": res.error or "LLM unavailable",
        })
        logger.warning("P17 LLM judge skipped: %s", res.reason())
        _llm_dump({
            "phase": "llm_skipped",
            "node_id": (ctx.current_node_id if hasattr(ctx, 'current_node_id') else None),
            "evidence_type": evidence_type,
            "evidence_len": len(evidence_text),
            "evidence_preview": evidence_text[:500],
            "files_to_sample": inputs.get("files_to_sample", []),
            "score": 0.0,
            "skipped": True,
            "llm_api_failure": res.llm_api_failure,
            "reason": res.error or "LLM unavailable",
        })
        return 0.0

    m = re.search(r"\d+\.?\d*", res.raw)
    if not m:
        _LAST_JUDGE_INFO.update({
            "skipped": True,
            "parse_failure": True,
            "llm_api_failure": False,
            "reason": "model reply contains no number",
        })
        logger.warning("P17 parse failure: %r", res.raw[:120])
        _llm_dump({
            "phase": "parse_failure",
            "node_id": (ctx.current_node_id if hasattr(ctx, 'current_node_id') else None),
            "evidence_type": evidence_type,
            "evidence_len": len(evidence_text),
            "evidence_preview": evidence_text[:500],
            "files_to_sample": inputs.get("files_to_sample", []),
            "llm_raw": res.raw[:500],
            "score": 0.0,
            "skipped": True,
            "parse_failure": True,
        })
        return 0.0

    score = float(m.group())
    final_score = max(score_range[0], min(score, score_range[1]))
    _llm_dump({
        "phase": "ok",
        "node_id": (ctx.current_node_id if hasattr(ctx, 'current_node_id') else None),
        "evidence_type": evidence_type,
        "evidence_len": len(evidence_text),
        "evidence_files": [ln.split('---')[1].strip() for ln in evidence_text.split('\n') if ln.startswith('--- ')],
        "evidence_preview": evidence_text[:500],
        "files_to_sample": inputs.get("files_to_sample", []),
        "score_range": score_range,
        "llm_raw": res.raw[:500],
        "parsed_score": score,
        "final_score": final_score,
    })
    return final_score



def _devise_sign_in_cookies() -> dict | None:
    try:
        import re as _re
        sess = requests.Session()
        r = sess.get(f"{config.BASE_URL}/sign_in", timeout=config.HTTP_TIMEOUT)
        m = _re.search(r'name="authenticity_token"\s+value="([^"]+)"', r.text)
        token = m.group(1) if m else ""
        creds = getattr(config, "SETUP_USER", {}) or {}
        r2 = sess.post(
            f"{config.BASE_URL}/sign_in",
            data={
                "authenticity_token": token,
                "user[email]": creds.get("email", ""),
                "user[password]": creds.get("password", ""),
            },
            timeout=config.HTTP_TIMEOUT,
            allow_redirects=False,
        )
        if r2.status_code in (301, 302, 303):
            return sess.cookies.get_dict()
    except Exception:
        return None
    return None


def p19_dom_assertion(inputs: dict, ctx: EvalContext) -> tuple[bool, float]:
    url_path = ctx.resolve(inputs.get("url", "/"))
    assertions = inputs.get("assertions", [])
    url = f"{config.BASE_URL}{url_path}"

    cookies = _devise_sign_in_cookies() if inputs.get("authenticate") else None

    try:
        resp = requests.get(url, timeout=config.HTTP_TIMEOUT, allow_redirects=True, cookies=cookies)
        html = resp.text
    except Exception:
        return False, 0.0

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    passed = 0
    for a in assertions:
        sel = a.get("selector", "")
        should_exist = a.get("shouldExist", True)
        elements = soup.select(sel) if sel else []
        found = len(elements) > 0
        if found == should_exist:
            passed += 1

    ratio = passed / len(assertions) if assertions else 1.0
    return passed == len(assertions), ratio



def p24_queue_job_check(inputs: dict, ctx: EvalContext) -> bool:
    trigger = inputs.get("trigger", {})
    verify = inputs.get("verify", {})

    ttype = trigger.get("type", "http")
    if ttype == "http":
        method = trigger.get("method", "POST")
        path = ctx.resolve(trigger.get("path", "/"))
        body = ctx.resolve(trigger.get("body"))
        try:
            http_request(method, path, ctx=ctx, body=body)
        except Exception:
            return False
    elif ttype == "rails_runner":
        cmd = ctx.resolve(trigger.get("command", ""))
        docker_exec(f"rails runner \"{cmd}\"", ctx)

    strategy = verify.get("strategy", "db_query")
    max_wait = verify.get("max_wait_ms", 15000)
    if strategy == "db_query":
        sql = ctx.resolve(verify.get("sql", "SELECT 1"))
        expected = ctx.resolve(verify.get("expected_result", {}))
        rows = db_query_with_retry(sql, expected, ctx, max_wait)
        if not rows:
            return False
        from utils import _row_matches
        return _row_matches(rows[0], expected)
    return False



def p26_search_query(inputs: dict, ctx: EvalContext) -> bool:
    path = ctx.resolve(inputs.get("path", "/api/search"))
    method = inputs.get("method", "GET")
    params = ctx.resolve(inputs.get("params", {}))
    token = ctx.resolve(inputs.get("token", ""))
    expected = inputs.get("expected_results", {})

    query_str = "&".join(f"{k}={v}" for k, v in params.items())
    full_path = f"{path}?{query_str}" if query_str else path

    headers = {"X-Auth-Token": token} if token else {}
    try:
        resp = http_request(method, full_path, ctx=ctx, headers=headers)
        data = resp.json()
    except Exception:
        return False

    results = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(results, list):
        results = [results] if results else []

    min_count = expected.get("min_count", 0)
    if len(results) < min_count:
        return False

    first_contains = expected.get("first_result_contains")
    if first_contains and results:
        first_str = json.dumps(results[0])
        if first_contains not in first_str:
            return False

    return True



_webhook_received: list[dict] = []
_webhook_lock = threading.Lock()


class _WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        with _webhook_lock:
            _webhook_received.append({
                "path": self.path,
                "headers": dict(self.headers),
                "body": body.decode("utf-8", errors="replace"),
            })
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, fmt, *args):
        pass


def p27_webhook_delivery(inputs: dict, ctx: EvalContext) -> bool:
    global _webhook_received
    trigger = inputs.get("trigger", {})
    expect = inputs.get("expect_delivery", {})
    timeout_ms = expect.get("timeout_ms", 15000)

    port = ctx.webhook_port
    with _webhook_lock:
        _webhook_received.clear()

    try:
        docker_exec(
            "grep -q host.docker.internal /etc/hosts || "
            "( gw=$(ip route 2>/dev/null | awk '/default/{print $3; exit}'); "
            "  [ -n \"$gw\" ] && echo \"$gw host.docker.internal\" >> /etc/hosts )",
            ctx, timeout=10,
        )
    except Exception as exc:
        logger.debug("P27 host.docker.internal mapping inject skipped: %s", exc)

    try:
        server = HTTPServer(("0.0.0.0", port), _WebhookHandler)
    except OSError as exc:
        logger.warning("P27 cannot bind port %s: %s", port, exc)
        return False
    server.timeout = 1
    _stop_flag = threading.Event()
    thread = threading.Thread(target=lambda: _serve_until(server, timeout_ms / 1000.0, _stop_flag), daemon=True)
    thread.start()

    try:
        method = trigger.get("method", "POST")
        path = ctx.resolve(trigger.get("path", "/"))
        body = ctx.resolve(trigger.get("body"))
        http_request(method, path, ctx=ctx, body=body)
    except Exception as exc:
        logger.warning("P27 trigger failed: %s", exc)

    thread.join(timeout=timeout_ms / 1000.0 + 2)
    _stop_flag.set()
    try:
        server.server_close()
    except Exception:
        pass

    with _webhook_lock:
        received = list(_webhook_received)

    if not received:
        return False

    body_contains = expect.get("body_contains", {})
    headers_contain = expect.get("headers_contain", {})

    for entry in received:
        body_ok = True
        for k, v in body_contains.items():
            if str(v) not in entry["body"]:
                body_ok = False
                break
        headers_ok = True
        for k, v in headers_contain.items():
            header_val = entry["headers"].get(k, "")
            if str(v) not in str(header_val):
                headers_ok = False
                break
        if body_ok and headers_ok:
            return True
    return False


def _serve_until(server, duration, stop_flag=None):
    deadline = time.time() + duration
    while time.time() < deadline:
        if stop_flag and stop_flag.is_set():
            break
        server.handle_request()
    try:
        server.server_close()
    except Exception:
        pass



def p28_email_check(inputs: dict, ctx: EvalContext) -> bool:
    trigger = inputs.get("trigger", {})
    mailserver_api = inputs.get("mailserver_api", "http://localhost:8025/api/v2/messages")
    expect = inputs.get("expect", {})
    timeout_ms = expect.get("timeout_ms", 15000)

    method = trigger.get("method", "POST")
    path = ctx.resolve(trigger.get("path", "/"))
    body = ctx.resolve(trigger.get("body"))
    try:
        http_request(method, path, ctx=ctx, body=body)
    except Exception:
        pass

    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        try:
            resp = requests.get(mailserver_api, timeout=5)
            messages = resp.json().get("items", resp.json().get("messages", []))
            for msg in messages:
                to_match = True
                if "to" in expect:
                    to_addrs = json.dumps(msg.get("To", msg.get("to", [])))
                    if expect["to"] not in to_addrs:
                        to_match = False
                subj_match = True
                if "subject_contains" in expect:
                    subj = msg.get("Subject", msg.get("subject", ""))
                    if expect["subject_contains"].lower() not in subj.lower():
                        subj_match = False
                if to_match and subj_match:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False



def p29_multi_step_workflow(inputs: dict, ctx: EvalContext) -> tuple[bool, float]:
    setup = inputs.get("entity_setup", {})
    steps = inputs.get("steps", [])
    final_verify = inputs.get("final_verify")

    method = setup.get("method", "POST")
    path = ctx.resolve(setup.get("path", "/"))
    body = ctx.resolve(setup.get("body"))
    try:
        resp = http_request(method, path, ctx=ctx, body=body)
        data = resp.json()
    except Exception:
        return False, 0.0

    entity_id = None
    submitter_ids = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                submitter_ids.append(item.get("id"))
                if entity_id is None:
                    entity_id = item.get("submission_id", item.get("id"))
    elif isinstance(data, dict):
        entity_id = data.get("id")

    ctx.captured["_wf_entity_id"] = entity_id
    ctx.captured["_wf_submitter_ids"] = submitter_ids

    passed = 0
    for step in steps:
        step_path = ctx.resolve(step.get("path", "/"))
        step_path = step_path.replace("{{id}}", str(entity_id) if entity_id else "")
        for i, sid in enumerate(submitter_ids):
            step_path = step_path.replace(f"{{{{submitter_ids[{i}]}}}}", str(sid))

        step_method = step.get("method", "PUT")
        step_body = ctx.resolve(step.get("body"))
        expected_status = step.get("expect_status", 200)
        expect_state = step.get("expect_state")

        try:
            resp = http_request(step_method, step_path, ctx=ctx, body=step_body)
            if resp.status_code != expected_status:
                continue
            if expect_state:
                data = resp.json()
                actual = json_path_get(data, expect_state["path"])
                if str(actual) == str(expect_state["value"]):
                    passed += 1
            else:
                passed += 1
        except Exception:
            continue

    if final_verify:
        fv_sql = ctx.resolve(final_verify.get("db_query", ""))
        fv_expected = ctx.resolve(final_verify.get("expected", {}))
        if fv_sql:
            fv_sql = fv_sql.replace("{{id}}", str(entity_id) if entity_id else "")
            rows = db_query(fv_sql, ctx)
            if rows:
                from utils import _row_matches
                if _row_matches(rows[0], fv_expected):
                    passed += 1

    total = len(steps) + (1 if final_verify else 0)
    ratio = passed / total if total else 0.0
    return passed == total, ratio



def _get_response_data(inputs: dict, ctx: EvalContext) -> Any:
    ref = inputs.get("response")
    if ref and isinstance(ref, str) and ref.startswith("{{") and ref.endswith("}}"):
        key = ref[2:-2]
        return ctx.captured.get(key)
    return ctx.last_response_json


def execute_primitive(ptype: str, inputs: dict, ctx: EvalContext) -> tuple[bool, float | None]:
    resolved_inputs = ctx.resolve(inputs)

    if ptype == "P01":
        return p01_file_exists(resolved_inputs, ctx), None
    elif ptype == "P02":
        return p02_file_content_match(resolved_inputs, ctx), None
    elif ptype == "P03":
        return p03_file_count(resolved_inputs, ctx), None
    elif ptype == "P04":
        return p04_http_request(resolved_inputs, ctx), None
    elif ptype == "P06":
        return p06_json_schema_match(resolved_inputs, ctx), None
    elif ptype == "P07":
        return p07_json_value_assert(resolved_inputs, ctx), None
    elif ptype == "P08":
        return p08_db_query(resolved_inputs, ctx), None
    elif ptype == "P09":
        ok, ratio = p09_db_table_exists(resolved_inputs, ctx)
        return ok, ratio
    elif ptype == "P10":
        ok, ratio = p10_db_column_check(resolved_inputs, ctx)
        return ok, ratio
    elif ptype == "P11":
        ok, ratio = p11_db_index_check(resolved_inputs, ctx)
        return ok, ratio
    elif ptype == "P12":
        return p12_docker_exec(resolved_inputs, ctx), None
    elif ptype == "P13":
        return p13_auth_login(resolved_inputs, ctx), None
    elif ptype == "P14":
        return p14_permission_check(resolved_inputs, ctx), None
    elif ptype == "P15":
        return p15_status_code_assert(resolved_inputs, ctx), None
    elif ptype == "P17":
        score = p17_llm_judge(resolved_inputs, ctx)
        ctx.captured["_llm_score"] = score
        return True, None
    elif ptype == "P19":
        ok, ratio = p19_dom_assertion(resolved_inputs, ctx)
        return ok, ratio
    elif ptype == "P24":
        return p24_queue_job_check(resolved_inputs, ctx), None
    elif ptype == "P26":
        return p26_search_query(resolved_inputs, ctx), None
    elif ptype == "P27":
        return p27_webhook_delivery(resolved_inputs, ctx), None
    elif ptype == "P28":
        return p28_email_check(resolved_inputs, ctx), None
    elif ptype == "P29":
        ok, ratio = p29_multi_step_workflow(resolved_inputs, ctx)
        return ok, ratio
    elif ptype == "RENDER_DOM":
        from _browser_primitives import p18_render_dom as _shared_render_dom
        res = _shared_render_dom(resolved_inputs, ctx)
        return bool(res.get("passed")), None
    elif ptype == "SCREENSHOT":
        from _browser_primitives import p19_screenshot as _shared_screenshot
        res = _shared_screenshot(resolved_inputs, ctx)
        return bool(res.get("passed")), None
    else:
        logger.warning("Unknown primitive type: %s", ptype)
        return False, None
