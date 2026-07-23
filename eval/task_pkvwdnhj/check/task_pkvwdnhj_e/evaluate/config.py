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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8010")
API_BASE_URL = APP_BASE_URL + "/api"
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5436"))
DB_NAME = os.environ.get("DB_NAME", "app_pkvwdnhj")
DB_USER = os.environ.get("DB_USER", "apppkvwdnhj")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123pkvwdnhj")
APP_CONTAINER = os.environ.get("APP_CONTAINER", "docker-app-1")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "docker-db-1")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

TEST_USERS = {
    "admin": {
        "username": os.environ.get("ADMIN_USERNAME", "evaladmin"),
        "email": os.environ.get("ADMIN_EMAIL", "admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalPass123"),
    },
    "api_admin": {
        "username": os.environ.get("API_ADMIN_USERNAME", "evalapiuser"),
        "name": "Eval API",
        "type": "api",
    },
    "limited": {
        "username": os.environ.get("LIMITED_USERNAME", "limitedapi"),
        "name": "Limited API",
        "type": "api",
    },
}

_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(_EVAL_DIR, "results")
DAG_PATH = os.path.join(_EVAL_DIR, "dag.json")
SCORING_CONFIG_PATH = os.path.join(_EVAL_DIR, "scoring_config.json")

HTTP_TIMEOUT = 15

FRONTEND_BASE_URL = APP_BASE_URL
FRONTEND_LOGIN = {
    "url": "{{base_url}}/admin/login",
    "method": "POST",
    "data": {
        "username": TEST_USERS["admin"]["username"],
        "password": TEST_USERS["admin"]["password"],
    },
    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
}

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
