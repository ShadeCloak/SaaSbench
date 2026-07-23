import os
from pathlib import Path

# ---- Paths ----
EVAL_DIR = Path(__file__).resolve().parent
_DEFAULT_WORKSPACE = (EVAL_DIR.parent.parent / "tasks" / "task_sgdoserd" / "docker" / "workspace").resolve()
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", str(_DEFAULT_WORKSPACE))).resolve()
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---- Application URLs ----
APP_HOST = os.environ.get("APP_HOST", "localhost")
APP_PORT = int(os.environ.get("APP_PORT", "8036"))
APP_BASE_URL = f"http://{APP_HOST}:{APP_PORT}"
API_BASE_URL = f"{APP_BASE_URL}/api/v4"
WEBSOCKET_URL = f"ws://{APP_HOST}:{APP_PORT}/api/v4/websocket"

# ---- Database ----
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5450"))
DB_NAME = os.environ.get("DB_NAME", "app_sgdoserd")
DB_USER = os.environ.get("DB_USER", "appsgdoserd")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123sgdoserd")

# ---- Docker ----
APP_CONTAINER = os.environ.get("APP_CONTAINER", "app-sgdoserd")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "db-sgdoserd")
REDIS_CONTAINER = os.environ.get("REDIS_CONTAINER", "redis-sgdoserd")

# ---- LLM (for P17 llm-judge) ----
LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

# ---- Test users (created by AUTH_CREATE_* nodes; reused throughout the suite) ----
TEST_USERS = {
    "admin": {
        "username": os.environ.get("ADMIN_USERNAME", "evaladmin"),
        "email": os.environ.get("ADMIN_EMAIL", "evaladmin@test.local"),
        "password": os.environ.get("ADMIN_PASSWORD", "Admin12345!"),
        "first_name": "Eval",
        "last_name": "Admin",
    },
    "user": {
        "username": os.environ.get("USER_USERNAME", "eval_user"),
        "email": os.environ.get("USER_EMAIL", "evaluser@test.local"),
        "password": os.environ.get("USER_PASSWORD", "User12345!"),
        "first_name": "Eval",
        "last_name": "User",
    },
    "guest": {
        "username": os.environ.get("GUEST_USERNAME", "eval_guest"),
        "email": os.environ.get("GUEST_EMAIL", "evalguest@test.local"),
        "password": os.environ.get("GUEST_PASSWORD", "Guest12345!"),
        "first_name": "Eval",
        "last_name": "Guest",
    },
}

# ---- Test team / channel names ----
TEST_TEAM_NAME = "evalteam"
TEST_TEAM_DISPLAY_NAME = "Eval Team"
TEST_PUB_CHANNEL_NAME = "eval-pub"
TEST_PRIV_CHANNEL_NAME = "eval-priv"

# ---- Timeouts ----
HTTP_TIMEOUT = 15
DB_TIMEOUT = 10
DOCKER_EXEC_TIMEOUT = 30
WS_TIMEOUT = 10

# ---- Misc ----
TZ = os.environ.get("TZ", "UTC")

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
