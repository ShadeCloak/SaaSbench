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

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8002")
API_V3_PREFIX = os.environ.get("API_V3_PREFIX", "/api/v3")
API_V4_PREFIX = os.environ.get("API_V4_PREFIX", "/api/v4")
API_BASE_URL = APP_BASE_URL + API_V3_PREFIX
API_V4_BASE_URL = APP_BASE_URL + API_V4_PREFIX

MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", "27018"))
MONGO_DB = os.environ.get("MONGO_DB", "app_qmjfeopc")
MONGO_USER = os.environ.get("MONGO_USER", "appqmjfeopc")
MONGO_PASSWORD = os.environ.get("MONGO_PASSWORD", "app123qmjfeopc")
MONGO_URI = os.environ.get(
    "MONGO_URI",
    f"mongodb://{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}?directConnection=true",
)

APP_CONTAINER = os.environ.get("APP_CONTAINER", "app_qmjfeopc")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "mongo_qmjfeopc")
REDIS_CONTAINER = os.environ.get("REDIS_CONTAINER", "redis_qmjfeopc")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

_DEFAULT_USER_PASSWORD = os.environ.get("EVAL_USER_PASSWORD", "EvalPass123!@#")
_DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "AdminPass123!@#")

TEST_USERS = {
    "user": {
        "username": os.environ.get("USER_USERNAME", "eval_user1"),
        "email": os.environ.get("USER_EMAIL", "eval1@test.com"),
        "password": os.environ.get("USER_PASSWORD", _DEFAULT_USER_PASSWORD),
    },
    "user2": {
        "username": os.environ.get("USER2_USERNAME", "eval_user2"),
        "email": os.environ.get("USER2_EMAIL", "eval2@test.com"),
        "password": os.environ.get("USER2_PASSWORD", _DEFAULT_USER_PASSWORD),
    },
    "admin": {
        "username": os.environ.get("ADMIN_USERNAME", "eval_superuser1"),
        "email": os.environ.get("ADMIN_EMAIL", "superuser1@eval.test"),
        "password": _DEFAULT_ADMIN_PASSWORD,
    },
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DAG_PATH = os.path.join(os.path.dirname(__file__), "dag.json")
SCORING_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scoring_config.json")

HTTP_TIMEOUT = 15

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
