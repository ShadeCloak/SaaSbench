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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8001")
API_BASE_URL = APP_BASE_URL + "/api"

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3307"))
DB_NAME = os.environ.get("DB_NAME", "timetracker_db")
DB_USER = os.environ.get("DB_USER", "tt_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "tt_pass")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "timetracker-app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "timetracker-db")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

RESULTS_DIR = os.environ.get("RESULTS_DIR", os.path.join(os.path.dirname(__file__), "results"))

HTTP_TIMEOUT = 120

TEST_USERS = {
    "admin": {
        "username": os.environ.get("ADMIN_USERNAME", "eval_admin"),
        "email": os.environ.get("ADMIN_EMAIL", "eval_admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalPass123!"),
        "role": "ROLE_SUPER_ADMIN",
    },
    "teamlead": {
        "username": os.environ.get("TEAMLEAD_USERNAME", "teamlead"),
        "email": os.environ.get("TEAMLEAD_EMAIL", "teamlead@test.com"),
        "password": os.environ.get("TEAMLEAD_PASSWORD", "Teamlead123!"),
        "role": "ROLE_TEAMLEAD",
    },
    "user": {
        "username": os.environ.get("USER_USERNAME", "testuser"),
        "email": os.environ.get("USER_EMAIL", "user@test.com"),
        "password": os.environ.get("USER_PASSWORD", "User123!@#"),
        "role": "ROLE_USER",
    },
}

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")

FRONTEND_BASE_URL = APP_BASE_URL
FRONTEND_LOGIN = {
    "url": "{{base_url}}/en/login_check",
    "method": "POST",
    "data": {
        "_username": TEST_USERS["admin"]["username"],
        "_password": TEST_USERS["admin"]["password"],
    },
    "csrf": {
        "url": "{{base_url}}/en/login",
        "regex": r'name="_csrf_token"[^>]*value="([^"]+)"',
        "field": "_csrf_token",
    },
    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
    "post_login": [
        {"method": "GET", "url": "{{base_url}}/en/wizard/intro"},
        {"method": "FORM_POST", "url": "{{base_url}}/en/wizard/profile"},
    ],
}
