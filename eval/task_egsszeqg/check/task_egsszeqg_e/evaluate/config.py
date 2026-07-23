from __future__ import annotations
import os

_DOCKER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "task_egsszeqg", "docker"))
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

APP_PORT = int(os.environ.get("APP_PORT", "8029"))
APP_BASE_URL = os.environ.get("APP_BASE_URL", f"http://localhost:{APP_PORT}")

DB_HOST = os.environ.get("DATABASE_HOST", "localhost")
DB_PORT = int(os.environ.get("DATABASE_PORT", "5451"))
DB_NAME = os.environ.get("DATABASE_NAME", "app_egsszeqg")
DB_USER = os.environ.get("DATABASE_USER", "appegsszeqg")
DB_PASSWORD = os.environ.get("DATABASE_PASSWORD", "app123egsszeqg")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6384/0")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "task_egsszeqg_app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "task_egsszeqg_postgres")

TEST_USERS = {
    "owner": {
        "email": os.environ.get("OWNER_EMAIL", "owner@example.com"),
        "password": os.environ.get("OWNER_PASSWORD", "App123egsszeqG!"),
        "firstName": os.environ.get("OWNER_FIRST_NAME", "Eval"),
        "lastName": os.environ.get("OWNER_LAST_NAME", "Owner"),
    },
    "member": {
        "email": os.environ.get("MEMBER_EMAIL", "member@example.com"),
        "password": os.environ.get("MEMBER_PASSWORD", "Testpassword1!"),
    },
}

PUBLIC_API_KEY_HEADER = os.environ.get("PUBLIC_API_KEY_HEADER", "X-PLATFORM-API-KEY")
PUBLIC_API_KEY_SCOPES = ["workflow:create"]

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
HTTP_TIMEOUT = 20

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
