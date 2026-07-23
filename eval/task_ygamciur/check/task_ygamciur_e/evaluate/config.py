import os

_TASK_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..")
_DOCKER_DIR = os.path.join(_TASK_ROOT, "task_ygamciur", "docker")
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

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8007")
API_BASE_URL = APP_BASE_URL + "/api/v1"

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "27017"))
DB_NAME = os.environ.get("DB_NAME", "app_ygamciur")
DB_USER = os.environ.get("DB_USER", "appygamciur")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123ygamciur")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "lowcode-platform")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

TEST_USERS = {
    "admin": {
        "email": os.environ.get("ADMIN_EMAIL", "admin@eval.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalAdmin123!"),
        "name": "Eval Admin",
    },
    "developer": {
        "email": os.environ.get("DEVELOPER_EMAIL", "dev@eval.com"),
        "password": os.environ.get("DEVELOPER_PASSWORD", "EvalDev123!"),
        "name": "Eval Developer",
    },
    "viewer": {
        "email": os.environ.get("VIEWER_EMAIL", "viewer@eval.com"),
        "password": os.environ.get("VIEWER_PASSWORD", "EvalViewer123!"),
        "name": "Eval Viewer",
    },
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
TIMEOUT = 15

FRONTEND_BASE_URL = APP_BASE_URL
FRONTEND_LOGIN = {
    "url": "{{base_url}}/api/v1/login",
    "method": "POST",
    "data": {
        "username": TEST_USERS["admin"]["email"],
        "password": TEST_USERS["admin"]["password"],
    },
    "csrf": {
        "url": "{{base_url}}/api/v1/health",
        "cookie": "XSRF-TOKEN",
        "header": "X-XSRF-TOKEN",
    },
    "headers": {
        "Origin": "{{base_url}}",
        "Content-Type": "application/x-www-form-urlencoded",
    },
}

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
