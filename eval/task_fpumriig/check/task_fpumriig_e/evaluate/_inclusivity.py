from __future__ import annotations


_IDEMPOTENT_KEYWORDS = (
    "already exists",
    "already taken",
    "already a member",
    "already invited",
    "already accepted",
    "already used",
    "already been used",
    "already been taken",
    "already in use",
    "already registered",
    "already verified",
    "already silenced",
    "already suspended",
    "already activated",
    "already approved",
    "already published",
    "already enabled",
    "already disabled",
    "already closed",
    "already deleted",
    "already archived",
    "already locked",
    "has already",
    "has been used",
    "has been taken",
    "has been registered",
    "must be unique",
    "must make a unique set",
    "with that name already",
    "with this name already",
    "with this email already",
    "duplicate key",
    "duplicate entry",
    "duplicate value",
    "is a duplicate",
    "is duplicate",
    "unique constraint",
    "violates unique",
    "unique violation",
    "name has already",
    "title has already",
    "username already",
    "email already",
    "draft is being edited",
    "cannot be cancelled",
    "cannot be canceled",
    "cannot cancel",
    "cannot transition",
    "invalid transition",
    "invalid status",
    "invalid state",
    "not allowed for status",
    "must be running",
    "must be paused",
    "must be active",
    "is not running",
    "is not active",
    "is not paused",
)


def _flatten_response_body(body) -> str:
    if body is None:
        return ""
    try:
        if isinstance(body, str):
            return body.lower()
        if isinstance(body, (list, tuple, set)):
            return " ".join(_flatten_response_body(x) for x in body)
        if isinstance(body, dict):
            return " ".join(_flatten_response_body(v) for v in body.values())
        return str(body).lower()
    except Exception:
        return ""


def _is_idempotent_success(status: int, body, accepted) -> bool:
    if status not in (400, 401, 403, 409, 422):
        return False
    if not (set(accepted) & {200, 201, 202, 204}):
        return False
    flat = _flatten_response_body(body)
    return any(kw in flat for kw in _IDEMPOTENT_KEYWORDS)


def _is_idempotent_delete_success(method: str, status: int, accepted) -> bool:
    if (method or "").upper() != "DELETE":
        return False
    if status != 404:
        return False
    return bool(set(accepted) & {200, 202, 204})


_PATH_ALIASES: dict = {
    "/api/v1/auth/token/login/":  ["/api/v1/auth/login/"],
    "/api/v1/auth/login/":         ["/api/v1/auth/token/login/"],
    "/api/v1/auth/token/logout/": ["/api/v1/auth/logout/", "/api/v1/auth/token/"],
    "/api/v1/auth/logout/":        ["/api/v1/auth/token/logout/", "/api/v1/auth/token/"],
}


def _path_alias_candidates(path: str, extra_aliases: dict | None = None) -> list:
    aliases = list(_PATH_ALIASES.get(path, []))
    if extra_aliases:
        for a in extra_aliases.get(path, []):
            if a not in aliases:
                aliases.append(a)
    out = [path]
    for a in aliases:
        if a not in out:
            out.append(a)
    return out


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import re as _re


def _resolve_dotted(context: dict, key: str):
    if not isinstance(context, dict) or not key:
        return None
    if key in context:
        return context[key]
    parts = key.split(".")
    cur = context
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _substitute_placeholders(text: str, context: dict) -> str:
    if not isinstance(text, str) or "{{" not in text:
        return text
    if not isinstance(context, dict):
        return text

    def _sub(m):
        key = m.group(1).strip()
        val = _resolve_dotted(context, key)
        if val is None:
            return m.group(0)
        return str(val)

    return _re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", _sub, text)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _incl_should_fastpath_p0607(prev_data, context=None) -> tuple[bool, str]:
    def _check(d):
        if not isinstance(d, dict):
            return False
        if d.get("_idempotent_create") or d.get("_idempotent_delete"):
            return True
        return False

    if _check(prev_data):
        return True, "idempotent flag in prev_data"
    if _check(context):
        return True, "idempotent flag in context"

    if isinstance(prev_data, dict):
        sc = prev_data.get("status_code") or prev_data.get("status")
        body = prev_data.get("body") or prev_data.get("resp_body") or prev_data
        if sc in (400, 401, 403, 409, 422):
            flat = _flatten_response_body(body)
            if any(kw in flat for kw in _IDEMPOTENT_KEYWORDS):
                return True, f"idempotent body keyword + {sc}"
    return False, ""


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _incl_get_http_request(globals_dict):
    fn = globals_dict.get("http_request") if isinstance(globals_dict, dict) else None
    if callable(fn):
        return fn
    try:
        from utils import http_request as _u_hr
        return _u_hr
    except Exception:
        pass
    import requests as _r

    def _fallback(method, url, headers=None, json=None, data=None, timeout=15, **kw):
        return _r.request(method=method.upper(), url=url, headers=headers,
                          json=json, data=data, timeout=timeout, **kw)
    return _fallback


def _incl_get_timeout(globals_dict, default: int = 15) -> int:
    if isinstance(globals_dict, dict) and "HTTP_TIMEOUT" in globals_dict:
        try:
            return int(globals_dict["HTTP_TIMEOUT"])
        except Exception:
            pass
    try:
        from config import HTTP_TIMEOUT as _ht
        return int(_ht)
    except Exception:
        return default


def _refresh_cached_auth(p13_fn, role: str, context: dict):
    try:
        return p13_fn({"role": role, "force_refresh": True}, context)
    except TypeError:
        return p13_fn({"role": role, "force_refresh": True})
    except Exception:
        return None
