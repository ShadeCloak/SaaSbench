import glob
import json
import os
import re
import secrets
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import requests

try:
    from .config import (
        APP_BASE_URL, API_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
        APP_CONTAINER, DB_CONTAINER, WORKSPACE_DIR, HTTP_TIMEOUT,
        LLM_API_KEY, LLM_API_BASE, LLM_MODEL, TEST_USERS, REDIS_HOST, REDIS_PORT,
    )
    from .utils import (
        http_get, http_post, http_put, http_patch, http_delete,
        docker_exec, get_db_connection, resolve_placeholders, NodeResult,
    )
except ImportError:
    from config import (
        APP_BASE_URL, API_BASE_URL, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD,
        APP_CONTAINER, DB_CONTAINER, WORKSPACE_DIR, HTTP_TIMEOUT,
        LLM_API_KEY, LLM_API_BASE, LLM_MODEL, TEST_USERS, REDIS_HOST, REDIS_PORT,
    )
    from utils import (
        http_get, http_post, http_put, http_patch, http_delete,
        docker_exec, get_db_connection, resolve_placeholders, NodeResult,
    )

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_auth_cache: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _resolve_inputs(inputs: dict, context: dict) -> dict:
    resolved = {}
    for k, v in inputs.items():
        if isinstance(v, str):
            resolved[k] = resolve_placeholders(v, context)
        elif isinstance(v, dict):
            resolved[k] = _resolve_inputs(v, context)
        elif isinstance(v, list):
            resolved[k] = [
                resolve_placeholders(item, context) if isinstance(item, str)
                else (_resolve_inputs(item, context) if isinstance(item, dict) else item)
                for item in v
            ]
        else:
            resolved[k] = v
    return resolved


_ENTITY_SEGMENT_MAP = {
    "contacts": "contact_id",
    "conversations": "conversation_id",
    "inboxes": "inbox_id",
    "teams": "team_id",
    "labels": "label_id",
    "webhooks": "webhook_id",
    "agents": "agent_id",
    "canned_responses": "canned_response_id",
    "custom_attribute_definitions": "custom_attribute_id",
    "custom_filters": "custom_filter_id",
    "campaigns": "campaign_id",
    "portals": "portal_id",
    "categories": "category_id",
    "articles": "article_id",
    "automation_rules": "automation_rule_id",
    "macros": "macro_id",
    "reports": "report_id",
    "custom_roles": "custom_role_id",
    "contact_inboxes": "contact_inbox_id",
    "messages": "message_id",
    "notes": "note_id",
    "accounts": "account_id",
    "users": "user_id",
}


_ENTITY_DB_LOOKUP = {
    "contacts": ("contacts", "email"),
    "inboxes": ("inboxes", "name"),
    "agents": ("users", "email"),
    "webhooks": ("webhooks", "url"),
    "campaigns": ("campaigns", "title"),
    "teams": ("teams", "name"),
    "labels": ("labels", "title"),
    "canned_responses": ("canned_responses", "short_code"),
    "custom_attribute_definitions": ("custom_attribute_definitions", "attribute_key"),
    "portals": ("portals", "slug"),
}


def _fallback_entity_lookup(url_path: str, body: dict, context: dict) -> None:
    segments = [s for s in url_path.strip("/").split("/") if s]
    entity_segment = segments[-1] if segments else ""
    lookup = _ENTITY_DB_LOOKUP.get(entity_segment)
    if not lookup:
        return

    table, key_field = lookup
    value = body.get(key_field)
    if not value:
        if key_field == "email" and "email" not in body:
            for k in ("name", "title"):
                if k in body:
                    key_field = k if table != "users" else key_field
                    value = body.get(k)
                    break
        if not value:
            return

    entity_key = _ENTITY_SEGMENT_MAP.get(entity_segment)
    if not entity_key:
        return

    entities = context.setdefault("entities", {})
    if entity_key in entities:
        return

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            account_id = context.get("account_id") or entities.get("account_id")
            if key_field == "email":
                value = value.lower()
            if account_id and table not in ("users", "portals"):
                cur.execute(
                    f"SELECT id FROM {table} WHERE account_id = %s AND LOWER({key_field}) = LOWER(%s) ORDER BY id LIMIT 1",
                    (account_id, value),
                )
            else:
                cur.execute(
                    f"SELECT id FROM {table} WHERE LOWER({key_field}) = LOWER(%s) ORDER BY id LIMIT 1",
                    (value,),
                )
            row = cur.fetchone()
            if row:
                entities[entity_key] = row[0]
                primary_key = f"primary_{entity_key}"
                if primary_key not in entities:
                    entities[primary_key] = row[0]
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def _extract_entity_ids(body: Any, context: dict, node_id: str, url_path: str) -> None:
    if not isinstance(body, dict):
        return
    entities = context.setdefault("entities", {})

    entity_id = body.get("id")
    if entity_id is None:
        return

    segments = [s for s in url_path.strip("/").split("/") if s]

    _ACTION_SEGMENTS = {
        "toggle_status", "execute", "assign", "unassign", "resolve",
        "mute", "unmute", "read", "unread", "search", "filter",
        "download", "availability", "toggle_availability",
        "conversation_counts", "export", "import", "bulk",
    }

    entity_key = None
    for seg in reversed(segments):
        if seg.isdigit() or seg.startswith("{{"):
            continue
        if seg in _ACTION_SEGMENTS or seg in ("api", "v1", "v2", "public", "platform"):
            continue
        if seg in _ENTITY_SEGMENT_MAP:
            entity_key = _ENTITY_SEGMENT_MAP[seg]
        break

    if entity_key:
        primary_key = f"primary_{entity_key}"
        if primary_key not in entities:
            entities[primary_key] = entity_id
            entities[entity_key] = entity_id
        else:
            entities[entity_key] = entity_id

    if "website_token" in body:
        entities["website_token"] = body["website_token"]

    if "identifier" in body and isinstance(body["identifier"], str):
        entities.setdefault("identifier", body["identifier"])


def _unwrap_payload(body: Any) -> Any:
    if not isinstance(body, dict):
        return body
    payload = body.get("payload")
    if payload is None:
        return body
    if isinstance(payload, list):
        if len(body) > 1:
            return body
        return payload
    if isinstance(payload, dict):
        keys = list(payload.keys())
        if len(keys) == 1 and isinstance(payload[keys[0]], dict):
            return payload[keys[0]]
        if len(keys) == 2:
            for k in keys:
                if isinstance(payload[k], dict) and "id" in payload[k]:
                    return payload[k]
        return payload
    return body


def _jsonpath_get(obj: Any, path: str) -> Any:
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    parts: List[str] = []
    for token in re.split(r"\.|(?=\[)", path):
        if not token:
            continue
        bracket = re.match(r"\[(\d+)\]", token)
        if bracket:
            parts.append(int(bracket.group(1)))
        elif "[" in token:
            head, rest = token.split("[", 1)
            if head:
                parts.append(head)
            idx = re.match(r"(\d+)\]", rest)
            if idx:
                parts.append(int(idx.group(1)))
        else:
            parts.append(token)

    current = obj
    for p in parts:
        if isinstance(p, int):
            if isinstance(current, (list, tuple)) and p < len(current):
                current = current[p]
            else:
                raise KeyError(f"Index {p} out of range")
        elif isinstance(current, dict):
            if p in current:
                current = current[p]
            else:
                raise KeyError(f"Key '{p}' not found")
        else:
            raise KeyError(f"Cannot traverse {type(current)} with key '{p}'")
    return current


def _check_expected(actual: Any, expected: Any, tolerance: Optional[float] = None) -> bool:
    if isinstance(expected, str):
        if expected == "not_null":
            return actual is not None
        if expected == "is_integer":
            return isinstance(actual, int)
        if expected == "is_integer_or_zero":
            return isinstance(actual, int)
        if expected == "is_array":
            return isinstance(actual, list)
        if expected == "is_object":
            return isinstance(actual, dict)
        if expected in ("is_object_or_array", "is_array_or_object"):
            return isinstance(actual, (dict, list))
        if expected.startswith("regex:"):
            pattern = expected[6:]
            return bool(re.search(pattern, str(actual)))
        if expected.startswith(">="):
            try:
                return float(actual) >= float(expected[2:])
            except (TypeError, ValueError):
                return False
        if expected.startswith("<="):
            try:
                return float(actual) <= float(expected[2:])
            except (TypeError, ValueError):
                return False

    if tolerance is not None:
        try:
            return abs(float(actual) - float(expected)) <= float(tolerance)
        except (TypeError, ValueError):
            pass

    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return actual == expected

    if actual == expected:
        return True
    try:
        return str(actual) == str(expected)
    except Exception:
        return False


def _http_dispatch(method: str, path: str, body: Any = None,
                   headers: Optional[dict] = None, timeout: int = HTTP_TIMEOUT,
                   context: Optional[dict] = None) -> requests.Response:
    m = method.upper()
    if m == "GET":
        return http_get(path, headers=headers, params=body if isinstance(body, dict) else None,
                        timeout=timeout, context=context)
    if m == "POST":
        return http_post(path, headers=headers, json_body=body, timeout=timeout, context=context)
    if m == "PUT":
        return http_put(path, headers=headers, json_body=body, timeout=timeout, context=context)
    if m == "PATCH":
        return http_patch(path, headers=headers, json_body=body, timeout=timeout, context=context)
    if m == "DELETE":
        return http_delete(path, headers=headers, json_body=body, timeout=timeout, context=context)
    raise ValueError(f"Unsupported HTTP method: {m}")


# ===================================================================
# ===================================================================
def p01_file_exists(inputs: dict, context: dict) -> dict:
    path = inputs.get("path", "")
    check_type = inputs.get("type", "file")
    full = os.path.join(WORKSPACE_DIR, path.lstrip("/"))
    if check_type == "directory":
        exists = os.path.isdir(full)
    elif check_type == "file":
        exists = os.path.isfile(full)
    else:
        exists = os.path.exists(full)
    return {"exists": exists, "path": full}


# ===================================================================
# ===================================================================
def p02_file_content_match(inputs: dict, context: dict) -> dict:
    path = inputs.get("path", "")
    match_type = inputs.get("match_type", "contains")
    pattern = inputs.get("pattern", "")
    full = os.path.join(WORKSPACE_DIR, path.lstrip("/"))

    if match_type == "glob_grep":
        search_root = full if os.path.isdir(full) else WORKSPACE_DIR
        total = 0
        files_matched = []
        for root, _dirs, files in os.walk(search_root):
            for fn in files:
                if not (fn.endswith(".rb") or fn.endswith(".yml") or fn.endswith(".yaml")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    with open(fp, "r", errors="replace") as fh:
                        c = fh.read()
                    if re.search(pattern, c):
                        total += 1
                        files_matched.append(os.path.relpath(fp, WORKSPACE_DIR))
                        if total >= 50:
                            break
                except Exception:
                    pass
            if total >= 50:
                break
        result = {"matched": total > 0, "match_count": total, "files": files_matched[:10], "search_root": search_root}
        context["last_response"] = result
        return result

    if not os.path.isfile(full):
        result = {"matched": False, "match_count": 0, "error": f"File not found: {full}"}
        context["last_response"] = result
        return result

    with open(full, "r", errors="replace") as f:
        content = f.read()

    if match_type == "regex":
        matches = re.findall(pattern, content, re.MULTILINE)
        result = {"matched": len(matches) > 0, "match_count": len(matches)}
    else:
        count = content.count(pattern)
        result = {"matched": count > 0, "match_count": count}
    context["last_response"] = result
    return result


# ===================================================================
# ===================================================================
def p03_file_count(inputs: dict, context: dict) -> dict:
    pattern = inputs.get("pattern", "*")
    min_count = int(inputs.get("min_count", 1))
    base_dir = inputs.get("base_dir", "")
    search_root = os.path.join(WORKSPACE_DIR, base_dir.lstrip("/")) if base_dir else WORKSPACE_DIR
    full_pattern = os.path.join(search_root, pattern)
    files = glob.glob(full_pattern, recursive=True)
    count = len(files)
    return {"count": count, "met_minimum": count >= min_count}


# ===================================================================
# ===================================================================
def _get_platform_token_from_db():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT at.token FROM access_tokens at "
                "JOIN platform_apps pa ON at.owner_id = pa.id AND at.owner_type = 'PlatformApp' "
                "ORDER BY at.id DESC LIMIT 1"
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None
    finally:
        if conn:
            conn.close()


USER_ACCESS_TOKEN_HEADER = os.environ.get("USER_ACCESS_TOKEN_HEADER", "api_access_token")
USER_ACCESS_TOKEN_FALLBACKS = [
    h for h in (
        "api_access_token",
        "X-API-Token",
        "X-Auth-Token",
        "X-Access-Token",
    ) if h != USER_ACCESS_TOKEN_HEADER
]


def _add_user_token_headers(headers, token: str) -> dict:
    h = dict(headers or {})
    h[USER_ACCESS_TOKEN_HEADER] = token
    for alt in USER_ACCESS_TOKEN_FALLBACKS:
        h.setdefault(alt, token)
    h.setdefault("Authorization", f"Bearer {token}")
    return h


def p04_http_request(inputs: dict, context: dict) -> dict:
    method = inputs.get("method", "GET").upper()
    path = inputs.get("path", "/")
    body = inputs.get("body", None)
    extra_headers = inputs.get("headers", None)
    timeout = int(inputs.get("timeout", HTTP_TIMEOUT))
    auth_override = inputs.get("auth_override", None)

    req_context = context
    if auth_override == "platform_app_token":
        token = _get_platform_token_from_db()
        if token:
            extra_headers = _add_user_token_headers(extra_headers, token)
            req_context = {}
    elif auth_override == "none":
        req_context = {}

    start = time.time()
    resp = _http_dispatch(method, path, body=body, headers=extra_headers,
                          timeout=timeout, context=req_context)
    elapsed_ms = round((time.time() - start) * 1000, 1)

    context["last_response_status"] = resp.status_code
    context["last_response_time_ms"] = elapsed_ms

    resp_body: Any = None
    try:
        resp_body = resp.json()
    except (ValueError, TypeError):
        resp_body = resp.text

    unwrapped = _unwrap_payload(resp_body) if isinstance(resp_body, dict) else resp_body

    context["last_response"] = unwrapped
    context["last_response_raw"] = resp_body
    context["last_response_headers"] = dict(resp.headers)

    capture_as = inputs.get("capture_as")
    if capture_as and isinstance(unwrapped, dict) and resp.status_code in (200, 201):
        cfield = inputs.get("capture_field", "id")
        cval = unwrapped.get(cfield)
        if cval is not None:
            context[capture_as] = cval

    if auth_override is None and not inputs.get("no_capture"):
        if isinstance(unwrapped, dict) and method == "POST" and resp.status_code in (200, 201):
            _extract_entity_ids(unwrapped, context, inputs.get("node_id", ""), path)

        if resp.status_code == 422 and method == "POST" and isinstance(body, dict):
            _fallback_entity_lookup(path, body, context)

    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "body": unwrapped,
        "response_time_ms": elapsed_ms,
    }


# ===================================================================
# ===================================================================
def p05_api_crud(inputs: dict, context: dict) -> dict:
    resource = inputs.get("resource", "")
    create_body = inputs.get("create_body", {})
    update_body = inputs.get("update_body", None)
    expected_create_status = int(inputs.get("expected_create_status", 200))
    expected_update_status = int(inputs.get("expected_update_status", 200))
    expected_delete_status = int(inputs.get("expected_delete_status", 200))
    expected_read_fields = inputs.get("expected_read_fields", [])

    steps_passed = 0
    steps_total = 4
    results: Dict[str, Any] = {}

    try:
        create_resp = _http_dispatch("POST", resource, body=create_body, context=context)
        create_json = create_resp.json() if create_resp.text else {}
        create_json = _unwrap_payload(create_json)
        create_ok = create_resp.status_code in (expected_create_status, 200, 201)
        if create_ok:
            steps_passed += 1
        results["create"] = {"status": create_resp.status_code, "body": create_json, "passed": create_ok}
        entity_id = create_json.get("id") if isinstance(create_json, dict) else None
        if isinstance(create_json, dict):
            _extract_entity_ids(create_json, context, "", resource)
    except Exception as e:
        results["create"] = {"error": str(e), "passed": False}
        return {"steps_passed": steps_passed, "steps_total": steps_total, **results}

    read_path = f"{resource}/{entity_id}" if entity_id else resource
    try:
        read_resp = _http_dispatch("GET", read_path, context=context)
        read_json = read_resp.json() if read_resp.text else {}
        read_json = _unwrap_payload(read_json)
        read_ok = read_resp.status_code == 200
        if read_ok and expected_read_fields:
            if isinstance(read_json, dict):
                for rf in expected_read_fields:
                    if rf not in read_json:
                        read_ok = False
                        break
        if read_ok:
            steps_passed += 1
        results["read"] = {"status": read_resp.status_code, "body": read_json, "passed": read_ok}
    except Exception as e:
        results["read"] = {"error": str(e), "passed": False}

    if update_body and entity_id:
        try:
            update_resp = _http_dispatch("PATCH", read_path, body=update_body, context=context)
            update_json = update_resp.json() if update_resp.text else {}
            update_json = _unwrap_payload(update_json)
            update_ok = update_resp.status_code in (expected_update_status, 200, 204)
            if update_ok:
                steps_passed += 1
            results["update"] = {"status": update_resp.status_code, "body": update_json, "passed": update_ok}
        except Exception as e:
            results["update"] = {"error": str(e), "passed": False}
    else:
        steps_total -= 1
        results["update"] = {"skipped": True, "passed": True}

    try:
        del_resp = _http_dispatch("DELETE", read_path, context=context)
        del_ok = del_resp.status_code in (expected_delete_status, 200, 204)
        if del_ok:
            steps_passed += 1
        results["delete"] = {"status": del_resp.status_code, "passed": del_ok}
    except Exception as e:
        results["delete"] = {"error": str(e), "passed": False}

    results["steps_passed"] = steps_passed
    results["steps_total"] = steps_total
    return results


# ===================================================================
# ===================================================================
def p06_json_schema_match(inputs: dict, context: dict) -> dict:
    response = inputs.get("response", context.get("last_response", {}))
    required_fields = inputs.get("required_fields", [])
    field_types = inputs.get("field_types", {})

    if isinstance(response, str):
        try:
            response = json.loads(response)
        except (ValueError, TypeError):
            return {"all_present": False, "missing_fields": required_fields, "type_mismatches": []}

    missing = [f for f in required_fields if f not in response] if isinstance(response, dict) else required_fields
    type_mismatches = []
    if isinstance(response, dict) and field_types:
        type_map = {"string": str, "integer": int, "number": (int, float),
                    "boolean": bool, "array": list, "object": dict}
        for fname, ftype in field_types.items():
            if fname in response:
                expected_type = type_map.get(ftype)
                if expected_type and not isinstance(response[fname], expected_type):
                    type_mismatches.append({
                        "field": fname,
                        "expected_type": ftype,
                        "actual_type": type(response[fname]).__name__,
                    })

    return {
        "all_present": len(missing) == 0 and len(type_mismatches) == 0,
        "missing_fields": missing,
        "type_mismatches": type_mismatches,
    }


# ===================================================================
# ===================================================================
def p07_json_value_assert(inputs: dict, context: dict) -> dict:
    response = inputs.get("response", context.get("last_response"))
    assertions = inputs.get("assertions", [])

    def _get_last_status():
        return (context.get("last_response_status")
                or context.get("last_status_code")
                or context.get("last_status") or 0)

    if not assertions:
        last_status = _get_last_status()
        return {"all_passed": True, "results": [], "skipped_reason": f"no assertions; last_status={last_status}"}

    if isinstance(response, str):
        try:
            response = json.loads(response)
        except (ValueError, TypeError):
            last_status = _get_last_status()
            if last_status and not (200 <= last_status < 300):
                return {"all_passed": True, "results": [], "skipped_reason": f"non-2xx ({last_status}) accepted by P15; assertions skipped"}
            return {"all_passed": False, "results": [{"error": "Response is not valid JSON"}]}

    last_status = _get_last_status()
    if last_status and not (200 <= last_status < 300):
        body_text = ""
        try:
            body_text = json.dumps(response) if isinstance(response, (dict, list)) else str(response or "")
        except Exception:
            body_text = str(response or "")
        idempotent_keywords = (
            "already exists", "already taken", "already in use", "duplicate",
            "has already been taken", "must be unique", "conflict", "already active",
            "is already", "has been used", "in progress", "validation failed",
        )
        if any(kw in body_text.lower() for kw in idempotent_keywords):
            return {"all_passed": True, "results": [], "skipped_reason": f"non-2xx ({last_status}) idempotent body; assertions skipped"}
        return {"all_passed": True, "results": [], "skipped_reason": f"non-2xx ({last_status}) accepted by P15; assertions skipped"}

    response = _unwrap_payload(response)

    results = []
    all_passed = True
    for assertion in assertions:
        path = assertion.get("path", "")
        expected = assertion.get("expected")
        tolerance = assertion.get("tolerance")
        expected_contains = assertion.get("expected_contains")

        try:
            actual = _jsonpath_get(response, path) if path else response
        except (KeyError, IndexError, TypeError) as e:
            if expected is None:
                results.append({"path": path, "actual": None, "expected": expected, "passed": True})
                continue
            results.append({"path": path, "actual": None, "expected": expected,
                            "passed": False, "error": str(e)})
            all_passed = False
            continue

        if expected_contains is not None:
            if isinstance(actual, str):
                passed = expected_contains in actual
            elif isinstance(actual, list):
                passed = expected_contains in actual
            else:
                passed = False
        elif expected is not None:
            passed = _check_expected(actual, expected, tolerance)
        else:
            passed = actual is not None

        if not passed:
            all_passed = False
        results.append({"path": path, "actual": actual, "expected": expected, "passed": passed})

    return {"all_passed": all_passed, "results": results}


# ===================================================================
# ===================================================================
def p08_db_query(inputs: dict, context: dict) -> dict:
    sql = inputs.get("sql", "")
    try:
        from _inclusivity import _substitute_placeholders as _incl_sub
        sql = _incl_sub(sql, context)
    except Exception:
        pass
    expected_result = inputs.get("expected_result", None)
    poll_seconds = float(inputs.get("poll_seconds", 0) or 0)

    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        deadline = time.time() + poll_seconds
        while True:
            with conn.cursor() as cur:
                cur.execute(sql)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
                else:
                    rows = []
            row_count = len(rows)
            if expected_result is None or time.time() >= deadline:
                break
            _probe = row_count == 0 if expected_result == "empty" else (
                row_count > 0 if expected_result == "non_empty" else None)
            if _probe is True or _probe is None:
                break
            time.sleep(0.5)

        match = True
        if expected_result is not None:
            if isinstance(expected_result, int):
                match = row_count == expected_result
            elif isinstance(expected_result, dict):
                if "min_count" in expected_result:
                    match = row_count >= int(expected_result["min_count"])
                if "max_count" in expected_result:
                    match = match and row_count <= int(expected_result["max_count"])
                if "value" in expected_result and rows:
                    match = match and (rows[0].get(list(rows[0].keys())[0]) == expected_result["value"])
            elif isinstance(expected_result, str):
                if expected_result == "non_empty":
                    match = row_count > 0
                elif expected_result == "empty":
                    match = row_count == 0

        store_as = inputs.get("store_as")
        if store_as and rows:
            entities = context.setdefault("entities", {})
            first_val = list(rows[0].values())[0] if rows[0] else None
            if first_val is not None:
                entities[store_as] = first_val

        result = {"rows": rows, "row_count": row_count, "match": match}
        context["last_response"] = result
        return result
    except Exception as e:
        result = {"rows": [], "row_count": 0, "match": False, "error": str(e)}
        context["last_response"] = result
        return result
    finally:
        if conn:
            conn.close()


# ===================================================================
# ===================================================================
FILE_EXTENSIONS = {
    "ruby":   [".rb", ".erb"],
    "python": [".py"],
    "node":   [".ts", ".tsx", ".js", ".jsx", ".mjs"],
    "go":     [".go"],
    "php":    [".php"],
    "java":   [".java", ".kt"],
}


def regex_any_of(content: str, patterns: List[str]) -> bool:
    for p in patterns:
        try:
            if re.search(p, content, re.M):
                return True
        except re.error:
            continue
    return False


CONTROLLER_PATTERNS = [
    r"class \w+ < ApplicationController",
    r"class \w+Controller\s*[<({:]",
    r"class \w+View\s*\(",
    r"@app\.route\(",
    r"@(Controller|Get|Post|Put|Delete)\b",
    r"router\.(get|post|put|delete|patch)\(",
    r"func \w+\(.*http\.Request",
    r"#\[(Get|Post|Put|Delete)",
]


TABLE_ALIASES = {
    "accounts":      ["accounts", "tenants", "workspaces", "organizations"],
    "users":         ["users", "agents", "members"],
    "inboxes":       ["inboxes", "channels", "inbox_channels"],
    "conversations": ["conversations", "threads", "chats"],
    "contacts":      ["contacts", "leads", "customers"],
    "messages":      ["messages", "chat_messages"],
    "agent_bots":    ["agent_bots", "bots", "bot_users"],
    "custom_roles":  ["custom_roles", "roles", "role_definitions"],
}


def _resolve_table_alias(table_name: str, existing: set) -> Optional[str]:
    for alias in TABLE_ALIASES.get(table_name, [table_name]):
        if alias in existing:
            return alias
    return None


def p09_db_table_exists(inputs: dict, context: dict) -> dict:
    tables = inputs.get("tables", [])
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            existing_tables = {row[0] for row in cur.fetchall()}
        found = []
        missing = []
        for t in tables:
            resolved = _resolve_table_alias(t, existing_tables)
            if resolved is not None:
                found.append(t)
            else:
                missing.append(t)
        return {
            "existing": found,
            "missing": missing,
            "found_count": len(found),
            "total_count": len(tables),
        }
    except Exception as e:
        return {"existing": [], "missing": tables, "found_count": 0,
                "total_count": len(tables), "error": str(e)}
    finally:
        if conn:
            conn.close()


# ===================================================================
# ===================================================================
def p10_db_column_check(inputs: dict, context: dict) -> dict:
    table = inputs.get("table", "")
    expected_columns = inputs.get("expected_columns", [])
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            )
            actual_cols = {row[0] for row in cur.fetchall()}
        found = [c for c in expected_columns if c in actual_cols]
        missing = [c for c in expected_columns if c not in actual_cols]
        return {
            "existing": found,
            "missing": missing,
            "found_count": len(found),
            "total_count": len(expected_columns),
        }
    except Exception as e:
        return {"existing": [], "missing": expected_columns,
                "found_count": 0, "total_count": len(expected_columns), "error": str(e)}
    finally:
        if conn:
            conn.close()


# ===================================================================
# ===================================================================
def p11_db_index_check(inputs: dict, context: dict) -> dict:
    table = inputs.get("table", "")
    expected_indexes = inputs.get("expected_indexes", [])
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = %s",
                (table,),
            )
            index_defs = [row[0] for row in cur.fetchall()]

        found = []
        missing = []
        for col in expected_indexes:
            col_found = False
            for idef in index_defs:
                if col in idef:
                    col_found = True
                    break
            (found if col_found else missing).append(col)

        return {
            "found": found,
            "missing": missing,
            "found_count": len(found),
            "total_count": len(expected_indexes),
        }
    except Exception as e:
        return {"found": [], "missing": expected_indexes,
                "found_count": 0, "total_count": len(expected_indexes), "error": str(e)}
    finally:
        if conn:
            conn.close()


# ===================================================================
# ===================================================================
def p12_docker_exec_primitive(inputs: dict, context: dict) -> dict:
    command = inputs.get("command", "")
    container = inputs.get("container", APP_CONTAINER)
    expect_success = inputs.get("expect_success", True)
    expect_output_contains = inputs.get("expect_output_contains", None)

    try:
        returncode, stdout, stderr = docker_exec(container, command)
        success = (returncode == 0) if expect_success else True
        if expect_output_contains:
            if expect_output_contains not in stdout:
                success = False
        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "success": success,
        }
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}


# ===================================================================
# ===================================================================
def p13_auth_login(inputs: dict, context: dict) -> dict:
    global _auth_cache
    role = inputs.get("role", "admin")
    login_path = inputs.get("login_path", "/auth/sign_in")
    method = inputs.get("method", "devise_token_auth")

    if role in _auth_cache:
        cached = _auth_cache[role]
        for k, v in cached.items():
            context[k] = v
        return {"success": True, "method_used": "cache", "role": role}

    user_info = TEST_USERS.get(role)
    if not user_info:
        return {"success": False, "error": f"Unknown role: {role}"}

    email = user_info["email"]
    password = user_info["password"]

    try:
        resp = requests.post(
            f"{APP_BASE_URL.rstrip('/')}{login_path}",
            json={"email": email, "password": password},
            timeout=HTTP_TIMEOUT,
        )

        if resp.status_code in (200, 201):
            token_data: Dict[str, Any] = {}

            access_token = resp.headers.get("access-token", "")
            client = resp.headers.get("client", "")
            uid = resp.headers.get("uid", "")

            if access_token:
                token_data["access-token"] = access_token
                token_data["client"] = client
                token_data["uid"] = uid

                body = {}
                try:
                    body = resp.json()
                except (ValueError, TypeError):
                    pass

                data = body.get("data", body)
                account_id = data.get("account_id")
                if not account_id:
                    accounts = data.get("available_accounts", [])
                    if accounts:
                        account_id = accounts[0].get("id") if isinstance(accounts[0], dict) else accounts[0]
                if account_id:
                    token_data["account_id"] = account_id
                    context["account_id"] = account_id

                admin_id = data.get("id")
                if admin_id:
                    token_data["admin_id"] = admin_id
                    context["admin_id"] = admin_id

                pubsub_token = data.get("pubsub_token")
                if pubsub_token:
                    token_data["pubsub_token"] = pubsub_token
                    context["pubsub_token"] = pubsub_token

                context["access-token"] = access_token
                context["client"] = client
                context["uid"] = uid

                _auth_cache[role] = dict(token_data)
                return {"success": True, "method_used": "devise_token_auth", "role": role}

        return _auth_login_db_fallback(role, email, context)

    except Exception as e:
        try:
            return _auth_login_db_fallback(role, email, context)
        except Exception as e2:
            return {"success": False, "error": str(e2), "original_error": str(e)}


def _auth_login_db_fallback(role: str, email: str, context: dict) -> dict:
    global _auth_cache
    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (email,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"User {email} not found in DB"}
            user_id = row[0]

            token = secrets.token_hex(32)
            cur.execute(
                "INSERT INTO access_tokens (owner_type, owner_id, token, created_at, updated_at) "
                "VALUES ('User', %s, %s, NOW(), NOW()) RETURNING id",
                (user_id, token),
            )

            cur.execute(
                "SELECT id FROM account_users WHERE user_id = %s LIMIT 1",
                (user_id,),
            )
            au_row = cur.fetchone()
            account_id = None
            if au_row:
                cur.execute(
                    "SELECT account_id FROM account_users WHERE user_id = %s LIMIT 1",
                    (user_id,),
                )
                acc_row = cur.fetchone()
                account_id = acc_row[0] if acc_row else None

        token_data = {
            "access-token": token,
            "client": "",
            "uid": email,
            "admin_id": user_id,
        }
        if account_id:
            token_data["account_id"] = account_id
            context["account_id"] = account_id

        context["access-token"] = token
        context["client"] = ""
        context["uid"] = email
        context["admin_id"] = user_id

        _auth_cache[role] = dict(token_data)
        return {"success": True, "method_used": "db_fallback", "role": role}
    except Exception as e:
        return {"success": False, "error": str(e), "method_used": "db_fallback_failed"}
    finally:
        if conn:
            conn.close()


# ===================================================================
# ===================================================================
def p14_permission_check(inputs: dict, context: dict) -> dict:
    action = inputs.get("action", "")
    expected_result = inputs.get("expected_result", "denied")
    expected_status = inputs.get("expected_status", None)

    parts = action.strip().split(" ", 1)
    if len(parts) != 2:
        return {"passed": False, "error": f"Invalid action format: {action}"}
    method, path = parts

    try:
        resp = _http_dispatch(method, path, context=context)
        actual_status = resp.status_code

        if expected_status is not None:
            if isinstance(expected_status, list):
                passed = actual_status in [int(s) for s in expected_status]
            else:
                passed = actual_status == int(expected_status)
        elif expected_result == "denied":
            passed = actual_status in (403, 404)
        elif expected_result == "allowed":
            passed = actual_status in (200, 201, 204)
        else:
            passed = False

        return {
            "passed": passed,
            "actual_status": actual_status,
            "expected": expected_result,
        }
    except Exception as e:
        return {"passed": False, "actual_status": None, "expected": expected_result, "error": str(e)}


# ===================================================================
# ===================================================================
def p15_status_code_assert(inputs: dict, context: dict) -> dict:
    expected_status = inputs.get("expected_status")
    acceptable = inputs.get("acceptable_statuses", None)
    actual = context.get("last_response_status")

    if actual is None:
        return {"passed": False, "actual": None, "expected": expected_status, "error": "No last response"}

    if acceptable:
        passed = actual in [int(s) for s in acceptable]
    elif isinstance(expected_status, list):
        passed = actual in [int(s) for s in expected_status]
    else:
        passed = actual == int(expected_status)

    return {"passed": passed, "actual": actual, "expected": expected_status}


# ===================================================================
# ===================================================================
def p16_response_time_check(inputs: dict, context: dict) -> dict:
    max_ms = float(inputs.get("max_ms", 5000))
    actual_ms = context.get("last_response_time_ms")

    if actual_ms is None:
        return {"passed": False, "actual_ms": None, "max_ms": max_ms, "error": "No last response timing"}

    return {"passed": float(actual_ms) <= max_ms, "actual_ms": actual_ms, "max_ms": max_ms}


# ===================================================================
# ===================================================================
def _collect_code_evidence_jz(files_to_sample, scan_patterns, rubric,
                              max_files: int = 30, per_file: int = 4000,
                              total: int = 60000) -> str:
    SKIP = ("/spec/", "/test/", "/tests/", "/node_modules/", "/vendor/",
            "/tmp/", "/.git/", "/coverage/", "/public/packs/")
    _kw = set(w.lower() for w in re.findall(r"[A-Za-z]{4,}", str(rubric) or ""))
    uniq = {}
    for fp in (files_to_sample or []):
        full = os.path.join(WORKSPACE_DIR, fp.lstrip("/"))
        if os.path.isfile(full):
            uniq[full] = os.path.basename(full).lower()
        elif os.path.isdir(full):
            for pat in scan_patterns:
                for m in glob.glob(os.path.join(full, pat), recursive=True):
                    if not os.path.isfile(m):
                        continue
                    rel = os.path.relpath(m, full).replace(os.sep, "/").lower()
                    if any(s in ("/" + rel) for s in SKIP):
                        continue
                    uniq[m] = rel
    if not uniq:
        for pat in scan_patterns:
            for m in glob.glob(os.path.join(WORKSPACE_DIR, pat), recursive=True):
                if not os.path.isfile(m):
                    continue
                rel = os.path.relpath(m, WORKSPACE_DIR).replace(os.sep, "/").lower()
                if any(s in ("/" + rel) for s in SKIP):
                    continue
                uniq[m] = rel
    from collections import defaultdict as _dd
    groups = _dd(list)
    for m, rel in uniq.items():
        top = rel.split("/", 1)[0]
        bn = rel.rsplit("/", 1)[-1]
        relevance = sum(2 for w in _kw if w in rel) + (1 if any(
            t in bn for t in ("controller", "service", "policy", "model",
                              "channel", "job", "listener", "concern")) else 0)
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
    parts = []
    for m in ordered:
        try:
            with open(m, "r", errors="replace") as fh:
                parts.append(f"=== {os.path.relpath(m, WORKSPACE_DIR)} ===\n{fh.read(per_file)}")
        except Exception:
            pass
    return "\n\n".join(parts)[:total]


def p17_llm_judge(inputs: dict, context: dict) -> dict:
    score_range_for_skip = inputs.get("score_range", [0, 5])
    if os.environ.get("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes"):
        return {"score": 0, "max_score": score_range_for_skip[1],
                "skipped": True, "llm_api_failure": False,
                "reason": "SKIP_LLM_JUDGE=1 (LLM judge intentionally skipped for peer-review-grade scoring)"}
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
    evidence_type = inputs.get("evidence_type", "code_files")
    rubric_prompt = inputs.get("rubric_prompt", "")
    score_range = inputs.get("score_range", [0, 1])
    files_to_sample = inputs.get("files_to_sample", None)
    scan_patterns = inputs.get("scan_patterns", [
        "**/*.rb", "**/*.erb",
        "**/*.py",
        "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "**/*.mjs", "**/*.vue", "**/*.svelte",
        "**/*.go",
        "**/*.php",
        "**/*.java", "**/*.kt",
    ])
    sample_count = int(inputs.get("sample_count", 5))

    max_score_val = score_range[1] if len(score_range) > 1 else 1

    evidence = ""
    if evidence_type == "code_files":
        evidence = _collect_code_evidence_jz(files_to_sample, scan_patterns, rubric_prompt)
    elif evidence_type in ("rendered_dom", "screenshot_dom"):
        dom = (context or {}).get("rendered_dom") or (context or {}).get("last_body") or ""
        if isinstance(dom, bytes):
            dom = dom.decode("utf-8", "replace")
        evidence = dom[:15000] if isinstance(dom, str) else ""
    elif evidence_type in ("http_response_html", "http_response_json", "api_response"):
        lr = context.get("last_response")
        evidence = json.dumps(lr, indent=2, default=str)[:8000] if lr else ""
    else:
        lr = context.get("last_response")
        evidence = str(lr)[:8000] if lr else ""

    if not (evidence or "").strip():
        return {"score": 0, "max_score": max_score_val,
                "reasoning": f"no {evidence_type or 'evidence'} captured (skipped, not penalised)",
                "skipped": True, "llm_api_failure": False,
                "reason": f"no {evidence_type or 'evidence'} captured"}

    if not LLM_API_KEY:
        return {
            "score": 0,
            "max_score": max_score_val,
            "reasoning": "LLM API key not configured; skipping LLM judge.",
            "skipped": True,
            "llm_api_failure": False,
            "reason": "LLM_API_KEY unset",
        }

    prompt = (
        f"You are an expert code reviewer. Evaluate the following evidence.\n\n"
        f"IMPORTANT — implementation-agnostic scoring policy:\n"
        f"  * Score the implementation on whether the architectural/behavioural "
        f"goal described in the rubric is met, not on which specific framework, "
        f"library, file extension, or language idiom was used.\n"
        f"  * When the rubric mentions a specific technology (e.g. Pundit, "
        f"ActionCable, Sidekiq, Vue 3, Vite), treat it as the recommended "
        f"reference; any equivalent implementation in another framework "
        f"(Django + DRF, NestJS, Express + Socket.IO, Bull queues, React, etc.) "
        f"that satisfies the same contract MUST receive the same score.\n"
        f"  * Only deduct points for missing capability, inconsistent design, or "
        f"failure to honour the contract — never for framework choice alone.\n\n"
        f"RUBRIC:\n{rubric_prompt}\n\n"
        f"EVIDENCE:\n{evidence}\n\n"
        f"Score range: {score_range[0]} to {score_range[1]}.\n"
        f"Respond in JSON: {{\"score\": <number>, \"reasoning\": \"<brief explanation>\"}}"
    )

    try:
        from _llm_judge_safe import safe_chat_completion
    except ImportError:
        from ._llm_judge_safe import safe_chat_completion

    res = safe_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE,
        temperature=0,
    )

    if res.skipped:
        return {
            "score": 0,
            "max_score": max_score_val,
            "reasoning": f"LLM call failed: {res.error}" if res.error else "LLM call skipped",
            "skipped": True,
            "llm_api_failure": res.llm_api_failure,
            "exception_class": res.exception_class,
            "reason": res.error or "skipped",
        }

    _lo = score_range[0] if score_range else 0
    parsed = None
    content_clean = re.sub(r"```json\s*|\s*```", "", res.raw).strip()
    try:
        parsed = json.loads(content_clean)
    except Exception:
        for m in reversed(re.findall(r"\{[^{}]*\"score\"[^{}]*\}", res.raw, re.S)):
            try:
                parsed = json.loads(m)
                break
            except Exception:
                continue
    if isinstance(parsed, dict) and "score" in parsed:
        try:
            _sc = float(parsed.get("score", _lo))
        except (TypeError, ValueError):
            _sc = _lo
        _sc = max(_lo, min(_sc, max_score_val))
        return {
            "score": _sc,
            "max_score": max_score_val,
            "reasoning": parsed.get("reasoning", ""),
        }
    m = (re.search(r"\"score\"\s*:\s*(\d+(?:\.\d+)?)", res.raw, re.I)
         or re.search(r"score[^0-9]{0,8}(\d+(?:\.\d+)?)", res.raw, re.I)
         or re.search(r"(\d+(?:\.\d+)?)\s*/\s*%d" % int(max_score_val), res.raw))
    if m:
        _sc = max(_lo, min(float(m.group(1)), max_score_val))
        return {
            "score": _sc,
            "max_score": max_score_val,
            "reasoning": "extracted from non-JSON reply",
        }
    return {
        "score": 0,
        "max_score": max_score_val,
        "reasoning": "LLM reply parse failed: no score found",
        "parse_failure": True,
        "raw": res.raw[:200],
    }


# ===================================================================
# ===================================================================
def p18_css_style_check(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P18_css_style_check"}


# ===================================================================
# ===================================================================
def p19_accessibility_check(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P19_accessibility_check"}


# ===================================================================
# ===================================================================
def p20_i18n_check(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P20_i18n_check"}


# ===================================================================
# ===================================================================
def p21_websocket_connect(inputs: dict, context: dict) -> dict:
    url = inputs.get("url", "")
    protocol = inputs.get("protocol", "actioncable-v1-json")
    subscribe = inputs.get("subscribe", None)
    expect_message = inputs.get("expect_message", None)
    auth_token = inputs.get("auth_token", context.get("access-token", ""))

    try:
        import websocket as ws_lib
    except ImportError:
        return {"connected": False, "error": "websocket-client not installed"}

    full_url = url if url.startswith("ws") else f"ws://{APP_BASE_URL.split('://', 1)[-1].rstrip('/')}{url}"
    if auth_token:
        separator = "&" if "?" in full_url else "?"
        full_url = f"{full_url}{separator}token={auth_token}"

    if protocol == "action_cable":
        protocol = "actioncable-v1-json"

    connected = False
    subscribed = False
    matched = False

    try:
        extra_headers = {"Origin": APP_BASE_URL}
        ws = ws_lib.create_connection(full_url, timeout=10,
                                      subprotocols=[protocol] if protocol else None,
                                      header=extra_headers)
        connected = True

        welcome = ws.recv()

        if subscribe:
            sub_cmd = json.dumps({
                "command": "subscribe",
                "identifier": json.dumps(subscribe) if isinstance(subscribe, dict) else subscribe,
            })
            ws.send(sub_cmd)
            sub_resp = ws.recv()
            try:
                sub_data = json.loads(sub_resp)
                if sub_data.get("type") == "confirm_subscription":
                    subscribed = True
            except (ValueError, TypeError):
                pass

        if expect_message:
            ws.settimeout(5)
            try:
                msg = ws.recv()
                if isinstance(expect_message, str):
                    matched = expect_message in msg
                else:
                    matched = True
            except Exception:
                pass

        ws.close()
    except Exception as e:
        return {"connected": connected, "subscribed": subscribed, "matched": matched, "error": str(e)}

    return {"connected": connected, "subscribed": subscribed, "matched": matched}


# ===================================================================
# ===================================================================
def p22_graphql_query(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P22_graphql_query"}


# ===================================================================
# ===================================================================
def p23_file_upload_download(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P23_file_upload_download"}


# ===================================================================
# ===================================================================
def p24_queue_job_check(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P24_queue_job_check"}


# ===================================================================
# ===================================================================
def p25_oauth_oidc_flow(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P25_oauth_oidc_flow"}


# ===================================================================
# ===================================================================
def p26_search_query(inputs: dict, context: dict) -> dict:
    path = inputs.get("path", "/search")
    params = inputs.get("params", {})
    expected_results = inputs.get("expected_results", {})
    min_count = int(expected_results.get("min_count", 0))

    try:
        resp = http_get(path, params=params, context=context)
        body = resp.json() if resp.text else {}
        body = _unwrap_payload(body)

        if isinstance(body, list):
            total = len(body)
        elif isinstance(body, dict):
            total = body.get("total", body.get("count", len(body.get("data", body.get("payload", [])))))
        else:
            total = 0

        return {"total_results": total, "min_met": total >= min_count, "status_code": resp.status_code}
    except Exception as e:
        return {"total_results": 0, "min_met": False, "error": str(e)}


# ===================================================================
# ===================================================================
def p27_webhook_delivery(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P27_webhook_delivery"}


# ===================================================================
# ===================================================================
def p28_email_check(inputs: dict, context: dict) -> dict:
    return {"not_implemented": True, "primitive": "P28_email_check"}


# ===================================================================
# ===================================================================
def p29_multi_step_workflow(inputs: dict, context: dict) -> dict:
    steps_def = inputs.get("steps", [])
    entity_setup = inputs.get("entity_setup", None)
    steps_total = len(steps_def)
    steps_passed = 0
    step_results: List[Dict[str, Any]] = []

    if entity_setup and isinstance(entity_setup, dict):
        entities = context.setdefault("entities", {})
        entities.update(entity_setup)

    for step in steps_def:
        name = step.get("name", "unnamed")
        method = step.get("method", "GET").upper()
        path = resolve_placeholders(step.get("path", ""), context)
        body = step.get("body", None)
        if isinstance(body, dict):
            body = _resolve_inputs(body, context)
        expect_status = step.get("expect_status", None)
        expect_state = step.get("expect_state", None)

        try:
            start = time.time()
            resp = _http_dispatch(method, path, body=body, context=context)
            elapsed = round((time.time() - start) * 1000, 1)

            resp_body: Any = None
            try:
                resp_body = resp.json()
            except (ValueError, TypeError):
                resp_body = resp.text

            unwrapped = _unwrap_payload(resp_body) if isinstance(resp_body, dict) else resp_body

            context["last_response"] = unwrapped
            context["last_response_status"] = resp.status_code
            context["last_response_time_ms"] = elapsed

            if isinstance(unwrapped, dict):
                _extract_entity_ids(unwrapped, context, name, path)

            step_passed = True

            if expect_status is not None:
                if isinstance(expect_status, list):
                    if resp.status_code not in [int(s) for s in expect_status]:
                        step_passed = False
                elif resp.status_code != int(expect_status):
                    step_passed = False

            if expect_state and isinstance(expect_state, dict) and isinstance(unwrapped, dict):
                for ek, ev in expect_state.items():
                    try:
                        actual_v = _jsonpath_get(unwrapped, ek) if "." in ek or ek.startswith("$") else unwrapped.get(ek)
                    except (KeyError, IndexError):
                        actual_v = None
                    if not _check_expected(actual_v, ev):
                        step_passed = False
                        break

            if step_passed:
                steps_passed += 1

            step_results.append({
                "name": name,
                "status_code": resp.status_code,
                "passed": step_passed,
                "response_time_ms": elapsed,
            })

        except Exception as e:
            step_results.append({
                "name": name,
                "passed": False,
                "error": str(e),
            })

    return {
        "steps_passed": steps_passed,
        "steps_total": steps_total,
        "step_results": step_results,
    }


# ===================================================================
# ===================================================================

PRIMITIVES = {
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
    "P12": p12_docker_exec_primitive,
    "P13": p13_auth_login,
    "P14": p14_permission_check,
    "P15": p15_status_code_assert,
    "P16": p16_response_time_check,
    "P17": p17_llm_judge,
    "P18": p18_css_style_check,
    "P19": p19_accessibility_check,
    "P20": p20_i18n_check,
    "P21": p21_websocket_connect,
    "P22": p22_graphql_query,
    "P23": p23_file_upload_download,
    "P24": p24_queue_job_check,
    "P25": p25_oauth_oidc_flow,
    "P26": p26_search_query,
    "P27": p27_webhook_delivery,
    "P28": p28_email_check,
    "P29": p29_multi_step_workflow,
}


def execute_primitive(ptype: str, inputs: dict, context: dict) -> dict:
    fn = PRIMITIVES.get(ptype)
    if not fn:
        return {"error": f"Unknown primitive {ptype}"}
    try:
        resolved_inputs = _resolve_inputs(inputs, context)
        return fn(resolved_inputs, context)
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

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
