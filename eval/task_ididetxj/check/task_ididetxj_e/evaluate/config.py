from __future__ import annotations

import os
from pathlib import Path

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
TASK_DIR = Path(os.getenv("TASK_DIR", str((HERE / "../../../tasks/task_ididetxj").resolve())))
EVAL_DIR = Path(os.getenv("EVAL_DIR", str(HERE)))
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", str(TASK_DIR / "docker" / "workspace")))
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True, parents=True)

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
APP_HOST = os.getenv("APP_HOST", "localhost")
APP_PORT = int(os.getenv("APP_PORT", "8031"))
APP_BASE_URL = f"http://{APP_HOST}:{APP_PORT}"
API_BASE_URL = f"{APP_BASE_URL}/api"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5452"))
DB_NAME = os.getenv("DB_NAME", "app_ididetxj")
DB_USER = os.getenv("DB_USER", "appididetxj")
DB_PASSWORD = os.getenv("DB_PASSWORD", "app123ididetxj")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6385"))

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
APP_CONTAINER = os.getenv("APP_CONTAINER", "task_ididetxj-app")
DB_CONTAINER = os.getenv("DB_CONTAINER", "task_ididetxj-db")
REDIS_CONTAINER = os.getenv("REDIS_CONTAINER", "task_ididetxj-redis")

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
TEST_USERS = {
    "admin": {
        "email": os.getenv("ADMIN_EMAIL", "eval_admin@example.com"),
        "name": os.getenv("ADMIN_NAME", "Eval Admin"),
        "role": "admin",
    },
    "member": {
        "email": os.getenv("MEMBER_EMAIL", "eval_member@example.com"),
        "name": os.getenv("MEMBER_NAME", "Eval Member"),
        "role": "member",
    },
    "viewer": {
        "email": os.getenv("VIEWER_EMAIL", "eval_viewer@example.com"),
        "name": os.getenv("VIEWER_NAME", "Eval Viewer"),
        "role": "viewer",
    },
    "guest": {
        "email": os.getenv("GUEST_EMAIL", "eval_guest@example.com"),
        "name": os.getenv("GUEST_NAME", "Eval Guest"),
        "role": "guest",
    },
    "other_team_admin": {
        "email": os.getenv("OTHER_TEAM_ADMIN_EMAIL", "eval_other_team@example.com"),
        "name": os.getenv("OTHER_TEAM_ADMIN_NAME", "Other Team Admin"),
        "role": "admin",
        "team": "OtherTeam",
    },
}

API_KEY_NAME_PREFIX = "eval_"

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.getenv("LLM_API_BASE", "")
SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
LLM_MODEL = os.getenv("LLM_MODEL", "")
if not LLM_API_KEY or not LLM_API_BASE:
    pass

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
DEFAULT_HTTP_TIMEOUT = int(os.getenv("DEFAULT_HTTP_TIMEOUT", "15"))
WEBHOOK_RECEIVER_PORT = int(os.getenv("WEBHOOK_RECEIVER_PORT", "9019"))
LOG_LEVEL = os.getenv("EVAL_LOG_LEVEL", "INFO")
