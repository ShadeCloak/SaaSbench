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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8034")
GRAPHQL_URL = APP_BASE_URL + "/graphql"
METADATA_URL = APP_BASE_URL + "/metadata"
REST_URL = APP_BASE_URL + "/rest"

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5455"))
DB_NAME = os.environ.get("DB_NAME", "app_fpumriig")
DB_USER = os.environ.get("DB_USER", "appfpumriig")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123fpumriig")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "app_fpumriig")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "db_fpumriig")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

HTTP_TIMEOUT = 15

TEST_USERS = {
    "admin": {
        "email": os.environ.get("ADMIN_EMAIL", "eval_admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalAdmin123!"),
    },
    "member": {
        "email": os.environ.get("MEMBER_EMAIL", "eval_member@test.com"),
        "password": os.environ.get("MEMBER_PASSWORD", "EvalMember123!"),
    },
    "member_restricted": {
        "email": os.environ.get("MEMBER_RESTRICTED_EMAIL", "eval_restricted@test.com"),
        "password": os.environ.get("MEMBER_RESTRICTED_PASSWORD", "EvalRestricted123!"),
    },
    "apikey": {
        "email": os.environ.get("ADMIN_EMAIL", "eval_admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalAdmin123!"),
        "use_apikey": True,
    },
}

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
