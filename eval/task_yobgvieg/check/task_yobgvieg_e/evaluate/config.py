import os as _os
from pathlib import Path as _Path
REPO_ROOT = str(_Path(__file__).resolve().parents[3])
HOME = _os.path.expanduser('~')
import os

def _detect_workspace_dir():
    env_val = os.environ.get("WORKSPACE_DIR")
    if env_val:
        return env_val
    here = os.path.dirname(os.path.abspath(__file__))
    task_e_dir = os.path.dirname(here)
    check_dir = os.path.dirname(task_e_dir)
    repo_root = os.path.dirname(check_dir)
    task_e_name = os.path.basename(task_e_dir)
    if task_e_name.endswith("_e"):
        task_name = task_e_name[:-2]
        candidate = os.path.join(repo_root, "tasks", task_name, "docker", "workspace")
        if os.path.isdir(candidate):
            return candidate
    return "/app"

WORKSPACE_DIR = _detect_workspace_dir()
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8032")
API_BASE_URL = APP_BASE_URL + "/api"
AUTH_BASE_URL = APP_BASE_URL + "/auth"

FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:8033")

FRONTEND_LOGIN = {
    "mode": "cookie",
    "url": "{{base_url}}/auth/sign-in/",
    "method": "POST",
    "data": {
        "email": os.environ.get("ADMIN_EMAIL", "eval_admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalAdmin123!"),
        "medium": "email",
    },
    "csrf": {
        "url": "{{base_url}}/auth/get-csrf-token/",
        "cookie": "csrftoken",
        "header": "X-CSRFToken",
    },
}

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5453"))
DB_NAME = os.environ.get("DB_NAME", "app_yobgvieg")
DB_USER = os.environ.get("DB_USER", "appyobgvieg")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123yobgvieg")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "app_yobgvieg")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "db_yobgvieg")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

HTTP_TIMEOUT = 15

TEST_USERS = {
    "admin": {
        "username": os.environ.get("ADMIN_USERNAME", "eval_admin"),
        "email": os.environ.get("ADMIN_EMAIL", "eval_admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalAdmin123!"),
        "role": 20,
    },
    "member": {
        "username": os.environ.get("MEMBER_USERNAME", "eval_member"),
        "email": os.environ.get("MEMBER_EMAIL", "eval_member@test.com"),
        "password": os.environ.get("MEMBER_PASSWORD", "EvalMember123!"),
        "role": 15,
    },
    "guest": {
        "username": os.environ.get("GUEST_USERNAME", "eval_guest"),
        "email": os.environ.get("GUEST_EMAIL", "eval_guest@test.com"),
        "password": os.environ.get("GUEST_PASSWORD", "EvalGuest123!"),
        "role": 5,
    },
}

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
