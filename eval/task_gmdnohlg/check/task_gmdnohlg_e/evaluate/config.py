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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8033")
API_BASE_URL = APP_BASE_URL

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5454"))
DB_NAME = os.environ.get("DB_NAME", "app_gmdnohlg")
DB_USER = os.environ.get("DB_USER", "appgmdnohlg")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123gmdnohlg")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "cloudcollab_app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "cloudcollab_db")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

TEST_USERS = {
    "admin": {
        "username": os.environ.get("ADMIN_USERNAME", "eval_admin"),
        "password": os.environ.get("ADMIN_PASSWORD", "evalAdmin123!"),
        "groups": ["admin"],
    },
    "user": {
        "username": os.environ.get("USER_USERNAME", "eval_user1"),
        "password": os.environ.get("USER_PASSWORD", "evalUser123!"),
        "groups": ["testgroup1", "testgroup2"],
    },
    "user2": {
        "username": os.environ.get("USER2_USERNAME", "eval_user2"),
        "password": os.environ.get("USER2_PASSWORD", "evalUser456!"),
        "groups": ["testgroup1"],
    },
    "subadmin": {
        "username": os.environ.get("SUBADMIN_USERNAME", "eval_subadmin"),
        "password": os.environ.get("SUBADMIN_PASSWORD", "evalSubadmin123!"),
        "groups": ["testgroup1"],
    },
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DAG_PATH = os.path.join(os.path.dirname(__file__), "dag.json")
SCORING_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scoring_config.json")

HTTP_TIMEOUT = 60
TABLE_PREFIX = "cc_"


FRONTEND_BASE_URL = APP_BASE_URL
FRONTEND_LOGIN = {
    "mode": "browser",
    "url": "{{base_url}}/login",
    "user": TEST_USERS["admin"]["username"],
    "password": TEST_USERS["admin"]["password"],
    "user_selector": "#user",
    "pass_selector": "#password",
    "submit_selector": "button[type=submit]",
    "wait_after": "networkidle",
    "timeout_ms": 30000,
}
