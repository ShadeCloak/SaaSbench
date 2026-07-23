from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
EVAL_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

_DEFAULT_WORKSPACE = (EVAL_ROOT / ".." / ".." / "task_hhrdixum" / "docker" / "workspace").resolve()
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", str(_DEFAULT_WORKSPACE))).resolve()

DAG_PATH = EVAL_ROOT / "dag.json"
SCORING_CONFIG_PATH = EVAL_ROOT / "scoring_config.json"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8014")
API_BASE_URL = APP_BASE_URL.rstrip("/") + "/api"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("APP_DB_HOST_EXTERNAL", "localhost")
DB_PORT = int(os.environ.get("APP_DB_PORT_EXTERNAL", "5439"))
DB_NAME = os.environ.get("APP_DB_NAME", "app_hhrdixum")
DB_USER = os.environ.get("APP_DB_USER", "apphhrdixum")
DB_PASSWORD = os.environ.get("APP_DB_PASSWORD", "app123hhrdixum")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
CACHE_HOST = os.environ.get("APP_CACHE_HOST_EXTERNAL", "localhost")
CACHE_PORT = int(os.environ.get("APP_CACHE_PORT_EXTERNAL", "6380"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
APP_CONTAINER = os.environ.get("APP_CONTAINER", "task_hhrdixum-app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "task_hhrdixum-db")
CACHE_CONTAINER = os.environ.get("CACHE_CONTAINER", "task_hhrdixum-cache")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
TEST_USERS = {
    "admin": {
        "username": os.environ.get("ADMIN_USERNAME", "admin"),
        "email": os.environ.get("ADMIN_EMAIL", "admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "Admin123!@#"),
        "is_superuser": True,
        "is_staff": True,
        "groups": [],
    },
    "user": {
        "username": os.environ.get("USER_USERNAME", "reader"),
        "email": os.environ.get("USER_EMAIL", "reader@test.com"),
        "password": os.environ.get("USER_PASSWORD", "Reader123!"),
        "is_superuser": False,
        "is_staff": False,
        "groups": ["Read Only"],
    },
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.0"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "60"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "15"))
DB_CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
TOKEN_TABLE_NAME = os.environ.get("TOKEN_TABLE_NAME", "users_apitoken")
USERS_TABLE_NAME = os.environ.get("USERS_TABLE_NAME", "auth_user")
TOKEN_PREFIX = os.environ.get("TOKEN_PREFIX", "app-")
SKIP_LLM_JUDGE_IF_NO_KEY = os.environ.get("SKIP_LLM_JUDGE_IF_NO_KEY", "1") == "1"
STRICT_PREREQ_PASSED_ONLY = os.environ.get("STRICT_PREREQ_PASSED_ONLY", "1") == "1"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
DAG_SMOKE_PATH = EVAL_ROOT / "dag_smoke.json"
