import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import requests
from config import APP_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT

API_KEY_HEADER = os.environ.get("API_KEY_HEADER", "X-Api-Key")
API_V1_PREFIX = os.environ.get("API_V1_PREFIX", "/api/v1/")


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    maxScore: float
    category: str = ""
    subcategory: str = ""
    message: str = ""
    evidence: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class PrimitiveResult:
    passed: bool
    data: Any = None
    message: str = ""
    response: Any = None


def _derive_baseline_namespace():
    settings_mod = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    if "." in settings_mod:
        return settings_mod.split(".", 1)[0]
    return os.environ.get("BASELINE_NAMESPACE", "")


context = {
    "auth_token": None,
    "auth_cookies": None,
    "current_role": None,
    "session": requests.Session(),
    "baseline_namespace": _derive_baseline_namespace(),
}


def resolve_placeholders(text, ctx=None):
    if ctx is None:
        ctx = context
    if not isinstance(text, str):
        return text
    import re
    def replacer(m):
        key = m.group(1)
        return str(ctx.get(key, m.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", replacer, text)


def resolve_dict(d, ctx=None):
    if isinstance(d, dict):
        return {k: resolve_dict(v, ctx) for k, v in d.items()}
    elif isinstance(d, list):
        return [resolve_dict(item, ctx) for item in d]
    elif isinstance(d, str):
        return resolve_placeholders(d, ctx)
    return d


def get_url(path):
    if path.startswith("http"):
        return path
    return APP_BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def get_headers(path=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if context.get("auth_cookies"):
        return headers
    if context.get("auth_token"):
        if path and API_V1_PREFIX in str(path):
            headers[API_KEY_HEADER] = context["auth_token"]
        else:
            headers["Authorization"] = f"Bearer {context['auth_token']}"
    return headers


def get_session():
    return context.get("session", requests.Session())


def http_get(path, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    s = get_session()
    return s.get(url, headers=h, timeout=timeout)


def http_post(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    s = get_session()
    return s.post(url, json=body, headers=h, timeout=timeout)


def http_patch(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    s = get_session()
    return s.patch(url, json=body, headers=h, timeout=timeout)


def http_delete(path, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    s = get_session()
    return s.delete(url, headers=h, timeout=timeout)


def http_put(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    s = get_session()
    return s.put(url, json=body, headers=h, timeout=timeout)


def docker_exec(container, command, timeout=30):
    from config import DB_NAME, DB_USER, DB_PASSWORD
    env_pairs = [
        "-e", f"DATABASE_URL=postgresql://{DB_USER}:{DB_PASSWORD}@db:5432/{DB_NAME}",
        "-e", "REDIS_URL=redis://redis:6379/0",
        "-e", f"SECRET_KEY={os.environ.get('SECRET_KEY', 'sk-eval-test-key')}",
        "-e", f"DJANGO_SETTINGS_MODULE={os.environ.get('DJANGO_SETTINGS_MODULE', 'app.settings.local')}",
        "-e", "USE_MINIO=1",
        "-e", "AWS_S3_ENDPOINT_URL=http://minio:9000",
        "-e", "AWS_ACCESS_KEY_ID=minioadmin",
        "-e", "AWS_SECRET_ACCESS_KEY=minioadmin",
        "-e", "AWS_STORAGE_BUCKET_NAME=uploads",
    ]
    cmd = ["docker", "exec"] + env_pairs + [container, "bash", "-c", command]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def save_results(results, filepath):
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)


def print_result(node_result):
    icon = "OK" if node_result.status == "PASSED" else "FAIL" if node_result.status == "FAILED" else "SKIP"
    try:
        print(f"  [{icon}] {node_result.node_id}: {node_result.score}/{node_result.maxScore} [{node_result.status}] {node_result.message}")
    except UnicodeEncodeError:
        print(f"  [{icon}] {node_result.node_id}: {node_result.score}/{node_result.maxScore}")


ENTITY_ID_MAP = {
    "CRUD_WORKSPACE": "workspace_id",
    "CRUD_PROJECT": "project_id",
    "CRUD_ISSUE": "issue_id",
    "CRUD_ISSUE_COMMENT": "comment_id",
    "CRUD_CYCLE": "cycle_id",
    "CRUD_MODULE": "module_id",
    "CRUD_LABEL": "label_id",
    "CRUD_PAGE": "page_id",
    "CRUD_ESTIMATE": "estimate_id",
    "CRUD_INTAKE": "intake_id",
    "CRUD_WEBHOOK": "webhook_id",
    "CRUD_FAVORITE": "favorite_id",
    "CRUD_STICKY": "sticky_id",
    "CRUD_DRAFT_ISSUE": "draft_id",
    "CRUD_ISSUE_VIEW": "view_id",
    "CRUD_ANALYTIC_VIEW": "analytic_id",
    "AUTH_API_KEY": "admin_token_id",
    "AUTH_CREATE_MEMBER_USER": "member_user_id",
    "AUTH_CREATE_GUEST_USER": "guest_user_id",
}


_USER_EMAIL_LOOKUP = {
    "AUTH_CREATE_MEMBER_USER": "eval_member@test.com",
    "AUTH_CREATE_GUEST_USER": "eval_guest@test.com",
}


def _resolve_user_id_by_email(email):
    try:
        cmd = (
            "psql -tA -U appyobgvieg -d app_yobgvieg "
            f"-c \"SELECT id FROM users WHERE email='{email}';\""
        )
        full_cmd = ["docker", "exec", "-e", "PGPASSWORD=app123yobgvieg", "db_yobgvieg", "bash", "-c", cmd]
        r = subprocess.run(full_cmd, capture_output=True, text=True, timeout=10)
        out = (r.stdout or "").strip()
        if out and "-" in out:
            return out.splitlines()[0].strip()
    except Exception:
        pass
    return None


def extract_entity_id(node_id, response_data):
    eid = response_data.get("id") if isinstance(response_data, dict) else None

    if not eid and node_id in _USER_EMAIL_LOOKUP:
        eid = _resolve_user_id_by_email(_USER_EMAIL_LOOKUP[node_id])

    if not eid:
        return

    mapped_key = ENTITY_ID_MAP.get(node_id)
    if mapped_key:
        context[mapped_key] = eid

    nid = node_id.lower()
    if "default_states" in nid or "state_test" in nid:
        context["new_project_id"] = eid
    if node_id == "BIZ_ISSUE_RELATION":
        context["related_issue_id"] = eid
    if node_id == "BIZ_LABEL_HIERARCHY" and context.get("label_id"):
        context["parent_label_id"] = context["label_id"]
        context["label_id"] = eid

    if isinstance(response_data, dict):
        if response_data.get("token") and "token" in nid:
            context["admin_api_token"] = response_data["token"]
        if response_data.get("anchor"):
            context["anchor"] = response_data["anchor"]
