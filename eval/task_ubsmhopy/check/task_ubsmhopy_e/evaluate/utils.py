import json
import subprocess
import time
import traceback
import uuid as uuid_mod
import base64
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any, Optional

import psycopg2
import requests

import config


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    max_score: float
    evidence: dict = field(default_factory=dict)
    message: str = ""


class EvalContext:

    def __init__(self):
        self.auth_tokens: dict[str, str] = {}
        self.entity_ids: dict[str, str] = {}
        self.entity_ids["admin_token_form"] = f"token={config.ADMIN_TOKEN}"
        self.entity_ids["admin_email"] = config.TEST_USERS["admin"]["email"]
        self.entity_ids["admin_hash"] = config.TEST_USERS["admin"]["password_hash"]
        self.entity_ids["new_admin_hash"] = config._make_master_hash(
            "NewEvalPassword456!", config.TEST_USERS["admin"]["email"])
        self.entity_ids["user_email"] = config.TEST_USERS["user"]["email"]
        self.entity_ids["user_hash"] = config.TEST_USERS["user"]["password_hash"]
        if "user_b" in config.TEST_USERS:
            self.entity_ids["user_b_email"] = config.TEST_USERS["user_b"]["email"]
            self.entity_ids["user_b_hash"] = config.TEST_USERS["user_b"]["password_hash"]
        _safe = datetime.now(timezone.utc) + timedelta(days=7)
        self.entity_ids["deletion_date"] = _safe.strftime("%Y-%m-%dT%H:%M:%SZ")
        self._session = requests.Session()
        self._current_role = "admin"

    def set_token(self, role: str, token: str):
        self.auth_tokens[role] = token

    def get_token(self, role: str = "admin") -> Optional[str]:
        return self.auth_tokens.get(role)

    def store_id(self, key: str, value: str):
        self.entity_ids[key] = value

    def get_id(self, key: str) -> Optional[str]:
        return self.entity_ids.get(key)

    def store_send_access_id(self, send_uuid: str):
        try:
            u = uuid_mod.UUID(send_uuid)
            aid = base64.urlsafe_b64encode(u.bytes).rstrip(b'=').decode()
            self.store_id("send_access_id", aid)
        except Exception:
            pass

    def resolve(self, template) -> Any:
        if isinstance(template, str):
            result = template
            for k, v in self.entity_ids.items():
                result = result.replace(f"{{{{{k}}}}}", str(v))
            for k, v in self.auth_tokens.items():
                result = result.replace(f"{{{{{k}_token}}}}", str(v))
            return result
        elif isinstance(template, dict):
            return {k: self.resolve(v) for k, v in template.items()}
        elif isinstance(template, list):
            return [self.resolve(v) for v in template]
        return template


def get_db_conn():
    return psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        dbname=config.DB_NAME, user=config.DB_USER, password=config.DB_PASS)


def db_query(sql: str) -> list[dict]:
    try:
        conn = get_db_conn()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        else:
            rows = []
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        return [{"error": str(e)}]


def http_request(method: str, path: str, headers: dict = None, body=None,
                 token: str = None, timeout: int = None,
                 session: requests.Session = None) -> dict:
    url = path if path.startswith("http") else f"{config.BASE_URL}{path}"
    hdrs = dict(headers or {})
    if token and "Authorization" not in hdrs:
        hdrs["Authorization"] = f"Bearer {token}"
    if body is not None and "Content-Type" not in hdrs:
        if isinstance(body, str):
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            hdrs["Content-Type"] = "application/json"

    requester = session or requests

    try:
        resp = requester.request(
            method, url, headers=hdrs,
            json=body if isinstance(body, (dict, list)) else None,
            data=body if isinstance(body, str) else None,
            timeout=timeout or config.REQUEST_TIMEOUT,
            allow_redirects=False)
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text
        return {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": resp_body,
            "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
        }
    except Exception as e:
        return {"status_code": 0, "headers": {}, "body": str(e),
                "response_time_ms": 0, "error": str(e)}


def docker_exec(command: str) -> dict:
    try:
        result = subprocess.run(
            ["docker", "exec", config.CONTAINER_NAME, "bash", "-c", command],
            capture_output=True, text=True, timeout=60)
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def wait_for_app(timeout: int = 60) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{config.BASE_URL}/alive", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False
