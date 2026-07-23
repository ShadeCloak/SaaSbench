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

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8020")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5444"))
DB_NAME = os.environ.get("DB_NAME", "app_aoiwqoiq")
DB_USER = os.environ.get("DB_USER", "appaoiwqoiq")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123aoiwqoiq")

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6383"))

APP_CONTAINER = os.environ.get("APP_CONTAINER", "task_aoiwqoiq-app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "task_aoiwqoiq-db")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

HTTP_TIMEOUT = 15
DOCKER_EXEC_TIMEOUT = 300

TEST_USERS = {
    "admin": {
        "username": "eval_admin",
        "email": "eval_admin@eval.test",
        "password": "EvalPass12345!",
    },
    "moderator": {
        "username": "eval_moderator",
        "email": "eval_mod@eval.test",
        "password": "EvalPass12345!",
    },
    "user": {
        "username": "eval_user",
        "email": "eval_user@eval.test",
        "password": "EvalPass12345!",
    },
}

AUTH_HEADER_KEY = os.environ.get("AUTH_HEADER_KEY", "Api-Key")
AUTH_HEADER_USER = os.environ.get("AUTH_HEADER_USER", "Api-Username")

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
