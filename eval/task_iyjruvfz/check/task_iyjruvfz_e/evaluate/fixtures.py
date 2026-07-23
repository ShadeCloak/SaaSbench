
from __future__ import annotations

import hashlib
import json as _json
import os
import secrets
import time

from . import config
from .utils import db_query, http_request


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def verify_seed_users() -> dict[str, int | None]:

    out: dict[str, int | None] = {}
    for role, info in config.TEST_USERS.items():
        res = db_query(
            "SELECT id FROM users WHERE email=%s OR username=%s LIMIT 1",
            (info["email"], info["username"]),
        )
        if res["ok"] and res["rows"]:
            out[role] = res["rows"][0]["id"]
        else:
            out[role] = None
    return out


def ensure_seed_users() -> dict[str, int | None]:
    import warnings

    warnings.warn(
        "ensure_seed_users is deprecated; use verify_seed_users (only verifies, never creates)",
        DeprecationWarning,
        stacklevel=2,
    )
    return verify_seed_users()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


_TEAM_DEFAULTS: dict = {
    "metadata": "{}",
    "bookingLimits": "{}",
    "isOrganization": False,
    "isPrivate": False,
    "hideBookATeamMember": False,
    "hideBranding": False,
    "isPlatform": False,
    "smsLockState": "UNLOCKED",
    "smsLockReviewedByAdmin": False,
    "createdAt": "NOW()",
    "pendingPayment": False,
    "isLocationDataDirty": True,
    "rrTimestampBasis": "CREATED_AT",
    "rrResetInterval": "MONTH",
    "weekStart": "Sunday",
}


def ensure_team(creator_role: str = "owner") -> dict | None:

    users = verify_seed_users()
    if not all(users.values()):
        return None

    slug = f"eval-team-{config.RANDOM_SUFFIX}"
    name = f"Eval Test Team [{config.RANDOM_SUFFIX}]"

    res = db_query('SELECT id FROM "Team" WHERE slug=%s LIMIT 1', (slug,))
    if res["ok"] and res["rows"]:
        team_id = res["rows"][0]["id"]
    else:
        cols = ['slug', 'name']
        vals: list = [slug, name]
        placeholders: list[str] = ["%s", "%s"]
        for col, default in _TEAM_DEFAULTS.items():
            cols.append(f'"{col}"')
            if default == "NOW()":
                placeholders.append("NOW()")
            elif isinstance(default, bool):
                vals.append(default)
                placeholders.append("%s")
            elif isinstance(default, (int, float)):
                vals.append(default)
                placeholders.append("%s")
            else:
                vals.append(default)
                placeholders.append("%s")
        sql = (
            f'INSERT INTO "Team" ({", ".join(cols[:2] + cols[2:])}) '
            f'VALUES ({", ".join(placeholders)}) RETURNING id'
        )
        ins = db_query(sql, tuple(vals))
        if not ins["ok"] or not ins["rows"]:
            return None
        team_id = ins["rows"][0]["id"]

    members: dict[str, int] = {}
    role_to_membership = {"owner": "OWNER", "admin": "ADMIN", "member": "MEMBER"}
    for role, m_role in role_to_membership.items():
        uid = users[role]
        check = db_query(
            'SELECT id FROM "Membership" WHERE "userId"=%s AND "teamId"=%s LIMIT 1',
            (uid, team_id),
        )
        if check["ok"] and check["rows"]:
            members[role] = check["rows"][0]["id"]
            continue
        m_ins = db_query(
            'INSERT INTO "Membership" ("userId", "teamId", role, accepted) '
            "VALUES (%s, %s, %s, true) RETURNING id",
            (uid, team_id, m_role),
        )
        if m_ins["ok"] and m_ins["rows"]:
            members[role] = m_ins["rows"][0]["id"]

    return {"team_id": team_id, "slug": slug, "members": members}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def ensure_event_type(team: dict | None = None) -> dict | None:

    users = verify_seed_users()
    owner_id = users.get("owner") or users.get("admin")
    if not owner_id:
        return None

    slug = f"eval-et-{config.RANDOM_SUFFIX}"
    res = db_query('SELECT id FROM "EventType" WHERE slug=%s LIMIT 1', (slug,))
    if res["ok"] and res["rows"]:
        return {"event_type_id": res["rows"][0]["id"], "slug": slug}

    fields = {
        "title": f"Eval Event [{config.RANDOM_SUFFIX}]",
        "slug": slug,
        "length": 30,
        "userId": owner_id,
        "minimumBookingNotice": 0,
    }
    cols = ", ".join(f'"{k}"' for k in fields)
    placeholders = ", ".join(["%s"] * len(fields))
    ins = db_query(
        f'INSERT INTO "EventType" ({cols}) VALUES ({placeholders}) RETURNING id',
        tuple(fields.values()),
    )
    if not ins["ok"] or not ins["rows"]:
        return None
    return {"event_type_id": ins["rows"][0]["id"], "slug": slug}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def ensure_api_key(role: str = "owner") -> str | None:

    users = verify_seed_users()
    user_id = users.get(role)
    if not user_id:
        return None

    prefix = os.environ.get("API_KEY_PREFIX", "app_")
    raw = secrets.token_hex(32)
    full_key = f"{prefix}{raw}"
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    note = f"eval_{role}_{config.RANDOM_SUFFIX}"

    db_query('DELETE FROM "ApiKey" WHERE note=%s OR ("userId"=%s AND id LIKE %s)', (note, user_id, "eval\\_%"))
    ins = db_query(
        'INSERT INTO "ApiKey" (id, "userId", "hashedKey", note, "createdAt") '
        "VALUES (%s, %s, %s, %s, NOW())",
        (f"c{secrets.token_hex(12)}", user_id, hashed, note),
    )
    return full_key if ins["ok"] else None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def ensure_platform_oauth_client(api_key: str | None = None) -> dict | None:

    if api_key is None:
        api_key = ensure_api_key("admin")
    if not api_key:
        return None

    body = {
        "name": f"eval-platform-client-{config.RANDOM_SUFFIX}",
        "redirectUris": ["http://localhost:3001/callback"],
        "permissions": 1023,
        "areEmailsEnabled": False,
    }
    headers = {
        **config.DEFAULT_V2_HEADERS,
        "Authorization": f"Bearer {api_key}",
    }
    resp = http_request(
        "POST",
        "/api/v2/oauth-clients",
        json_body=body,
        headers=headers,
        timeout=config.HTTP_TIMEOUT_SEC,
    )
    if resp.get("status_code") not in (200, 201):
        return None
    data = (resp.get("body") or {}).get("data") or {}
    if not data.get("clientId") or not data.get("clientSecret"):
        return None
    return {"client_id": data["clientId"], "client_secret": data["clientSecret"]}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def mock_receiver_url() -> str:
    return f"http://localhost:{config.MOCK_WEBHOOK_PORT}"


def mock_receiver_subscriber_url() -> str:
    return f"http://host.docker.internal:{config.MOCK_WEBHOOK_PORT}/hook"


def recent_webhook_requests(within_seconds: int = 30) -> list[dict]:

    cutoff = time.time() - within_seconds
    resp = http_request(
        "GET",
        f"{mock_receiver_url()}/history?since={cutoff}",
        timeout=5,
    )
    if not resp.get("ok") or resp.get("status_code") != 200:
        return []
    body = resp.get("body") or []
    if not isinstance(body, list):
        return []
    return body


def reset_webhook_history() -> bool:
    resp = http_request(
        "DELETE",
        f"{mock_receiver_url()}/history",
        timeout=5,
    )
    return resp.get("ok", False) and resp.get("status_code") == 200


def mock_receiver_alive() -> bool:
    resp = http_request("GET", f"{mock_receiver_url()}/health", timeout=3)
    return resp.get("status_code") == 200


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def cleanup_eval_artifacts(*, verbose: bool = False) -> dict:

    suffix = config.RANDOM_SUFFIX
    counts: dict = {}
    counts["api_keys"] = db_query(
        'DELETE FROM "ApiKey" WHERE note LIKE %s', (f"eval_%_{suffix}",)
    )["rowcount"]
    counts["bookings"] = db_query(
        'DELETE FROM "Booking" WHERE "eventTypeId" IN '
        '(SELECT id FROM "EventType" WHERE slug=%s)', (f"eval-et-{suffix}",)
    )["rowcount"]
    counts["event_types"] = db_query(
        'DELETE FROM "EventType" WHERE slug=%s', (f"eval-et-{suffix}",)
    )["rowcount"]
    counts["memberships"] = db_query(
        'DELETE FROM "Membership" WHERE "teamId" IN '
        '(SELECT id FROM "Team" WHERE slug=%s)', (f"eval-team-{suffix}",)
    )["rowcount"]
    counts["teams"] = db_query(
        'DELETE FROM "Team" WHERE slug=%s', (f"eval-team-{suffix}",)
    )["rowcount"]
    counts["platform_oauth_clients"] = db_query(
        'DELETE FROM "PlatformOAuthClient" WHERE name LIKE %s',
        (f"eval-platform-client-{suffix}%",),
    )["rowcount"]
    counts["webhook_history_cleared"] = 0
    if reset_webhook_history():
        counts["webhook_history_cleared"] = 1

    if verbose:
        print(f"[cleanup] {counts}")
    return counts


EVAL_BOOKING_CUTOFF = "2026-11-01"


def cleanup_eval_bookings(cutoff: str = EVAL_BOOKING_CUTOFF, *, verbose: bool = False) -> int:

    res = db_query('DELETE FROM "Booking" WHERE "startTime" >= %s', (cutoff,))
    n = res.get("rowcount", 0) if isinstance(res, dict) else 0
    if verbose:
        print(f"[cleanup_eval_bookings] deleted {n} future bookings (>= {cutoff})")
    return n
