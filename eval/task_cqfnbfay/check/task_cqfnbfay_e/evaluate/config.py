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

APP_HOST = os.getenv("APP_HOST", "localhost")
APP_PORT = int(os.getenv("APP_PORT", "8021"))
BASE_URL = os.getenv("BASE_URL", f"http://{APP_HOST}:{APP_PORT}")
API_BASE = f"{BASE_URL}/api"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5445"))
DB_NAME = os.getenv("DB_NAME", "app_cqfnbfay")
DB_USER = os.getenv("DB_USER", "appcqfnbfay")
DB_PASSWORD = os.getenv("DB_PASSWORD", "app123cqfnbfay")
DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

DOCKER_COMPOSE_DIR = os.getenv("DOCKER_COMPOSE_DIR", "")
APP_CONTAINER = os.getenv("APP_CONTAINER", "cqfnbfay-app-1")

SETUP_USER = {
    "first_name": os.environ.get("ADMIN_FIRST_NAME", "Eval"),
    "last_name": os.environ.get("ADMIN_LAST_NAME", "Admin"),
    "email": os.environ.get("ADMIN_EMAIL", "eval@test.com"),
    "password": os.environ.get("ADMIN_PASSWORD", "EvalPass123!"),
}
SETUP_ACCOUNT = {"name": os.environ.get("ACCOUNT_NAME", "EvalCo")}
SETUP_APP_URL = BASE_URL

TEST_USERS = {
    "admin": {
        "email": SETUP_USER["email"],
        "password": SETUP_USER["password"],
        "first_name": SETUP_USER["first_name"],
        "last_name": SETUP_USER["last_name"],
    },
}
ACCOUNT_NAME = SETUP_ACCOUNT["name"]

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.commonstack.ai/v1")
SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20250929")

WEBHOOK_LISTEN_PORT = int(os.getenv("WEBHOOK_LISTEN_PORT", "18900"))

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))
DB_QUERY_TIMEOUT = int(os.getenv("DB_QUERY_TIMEOUT", "10"))
POLL_INTERVAL_MS = int(os.getenv("POLL_INTERVAL_MS", "2000"))

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
DAG_PATH = os.path.join(EVAL_DIR, "dag.json")
SCORING_CONFIG_PATH = os.path.join(EVAL_DIR, "scoring_config.json")
RESULTS_DIR = os.path.join(EVAL_DIR, "results")
