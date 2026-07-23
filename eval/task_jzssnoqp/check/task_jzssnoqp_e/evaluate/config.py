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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8018")
API_BASE_URL = APP_BASE_URL

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5443"))
DB_NAME = os.environ.get("DB_NAME", "app_jzssnoqp")
DB_USER = os.environ.get("DB_USER", "appjzssnoqp")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123jzssnoqp")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "docker-app-1")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "docker-db-1")

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6382"))

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE") or "https://api.commonstack.ai/v1"
LLM_MODEL = os.environ.get("LLM_MODEL") or "claude-sonnet-4-5-20250929"

TEST_USERS = {
    "admin": {
        "email": os.environ.get("ADMIN_EMAIL", "admin@eval.test"),
        "password": os.environ.get("ADMIN_PASSWORD", "Password1!"),
        "name": "EvalAdmin",
        "role": "administrator",
    },
    "agent": {
        "email": os.environ.get("AGENT_EMAIL", "agent@eval.test"),
        "password": os.environ.get("AGENT_PASSWORD", "Password1!"),
        "name": "EvalAgent",
        "role": "agent",
    },
    "custom_report_manage": {
        "email": os.environ.get("CUSTOM_REPORT_EMAIL", "custom_report@eval.test"),
        "password": os.environ.get("CUSTOM_REPORT_PASSWORD", "Password1!"),
        "name": "EvalCustomReportManage",
        "role": "agent",
    },
    "custom_conv_manage": {
        "email": os.environ.get("CUSTOM_CONV_EMAIL", "custom_conv@eval.test"),
        "password": os.environ.get("CUSTOM_CONV_PASSWORD", "Password1!"),
        "name": "EvalCustomConvManage",
        "role": "agent",
    },
    "agent_zero_inbox": {
        "email": os.environ.get("ZERO_INBOX_EMAIL", "zero_inbox@eval.test"),
        "password": os.environ.get("ZERO_INBOX_PASSWORD", "Password1!"),
        "name": "EvalZeroInbox",
        "role": "agent",
    },
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

HTTP_TIMEOUT = 15
DB_CONNECT_TIMEOUT = 10

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
