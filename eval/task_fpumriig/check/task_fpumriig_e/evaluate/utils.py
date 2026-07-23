import json
import os
import subprocess
import time
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import requests
from config import APP_BASE_URL, APP_CONTAINER, HTTP_TIMEOUT


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


context = {
    "auth_token": None,
    "auth_cookies": None,
    "current_role": None,
    "session": requests.Session(),
    "token_cache": {},
    "api_key_token": None,
}


def resolve_placeholders(text, ctx=None):
    if ctx is None:
        ctx = context
    if not isinstance(text, str):
        return text
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


def get_headers():
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if context.get("auth_token"):
        headers["Authorization"] = f"Bearer {context['auth_token']}"
    return headers


def get_session():
    return context.get("session", requests.Session())


def http_get(path, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    return get_session().get(url, headers=h, timeout=timeout)


def http_post(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    return get_session().post(url, json=body, headers=h, timeout=timeout)


def http_patch(path, body=None, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    return get_session().patch(url, json=body, headers=h, timeout=timeout)


def http_delete(path, headers=None, timeout=HTTP_TIMEOUT):
    url = get_url(path)
    h = headers if headers is not None else get_headers()
    return get_session().delete(url, headers=h, timeout=timeout)


def docker_exec(container, command, timeout=30):
    cmd = ["docker", "exec", container] + command.split()
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
    icon = "OK" if node_result.status == "PASSED" else "FAIL" if node_result.status == "FAILED" else "SKIP" if "SKIP" in node_result.status else "ERR"
    try:
        print(f"  [{icon}] {node_result.node_id}: {node_result.score}/{node_result.maxScore} [{node_result.status}] {node_result.message}")
    except UnicodeEncodeError:
        print(f"  [{icon}] {node_result.node_id}: {node_result.score}/{node_result.maxScore}")


ENTITY_ID_MAP = {
    "CRUD_COMPANY": "companyId",
    "CRUD_PERSON": "personId",
    "CRUD_OPPORTUNITY": "opportunityId",
    "CRUD_TASK": "taskId",
    "CRUD_NOTE": "noteId",
    "CRUD_DASHBOARD": "dashboardId",
    "CRUD_ATTACHMENT": "attachmentId",
    "WORKFLOW_CREATE": "workflowId",
    "WORKFLOW_VERSION": "versionId",
    "WORKFLOW_RUN": "runId",
    "METADATA_CREATE_OBJECT": "objectId",
    "METADATA_VIEW": "viewId",
    "METADATA_WEBHOOK": "webhookId",
    "METADATA_AI_AGENT": "agentId",
    "RBAC_ROLE": "roleId",
    "ADV_API_KEY": "apiKeyId",
    "OAUTH2_REGISTER": "oauthClientId",
    "BIZ_FAVORITE": "favoriteId",
    "BIZ_TASK_TARGET": "taskTargetId",
}


def extract_entity_id(node_id, response_data):
    if not isinstance(response_data, dict):
        return

    eid = response_data.get("id")

    if isinstance(response_data, dict) and "data" in response_data:
        data_inner = response_data["data"]
        if isinstance(data_inner, dict):
            for k, v in data_inner.items():
                if isinstance(v, dict) and v.get("id"):
                    eid = v["id"]
                    if v.get("status"):
                        context[f"last_{k}_status"] = v["status"]
                    context["last_inner_data"] = v
                    break
                elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and v[0].get("id"):
                    eid = v[0]["id"]
                    break

    if not eid:
        return

    for prefix, ctx_key in ENTITY_ID_MAP.items():
        if node_id.startswith(prefix):
            context[ctx_key] = eid
            break

    nid = node_id.upper()
    if "COMPANY" in nid and "companyId" not in context:
        context["companyId"] = eid
    if "PERSON" in nid and "personId" not in context:
        context["personId"] = eid

    if response_data.get("token"):
        context["api_key_token"] = response_data["token"]
    if response_data.get("client_id"):
        context["oauthClientId"] = response_data["client_id"]
    if response_data.get("client_secret"):
        context["oauthClientSecret"] = response_data["client_secret"]
    if response_data.get("access_token"):
        context["oauthAccessToken"] = response_data["access_token"]
        context["oauthToken"] = response_data["access_token"]
