"""Stage 6.1 — Evaluation framework configuration for task_xayqujrv.

All host-side defaults derived from docker/docker-compose.yml:
  - app:           container 8000  → host 8023
  - postgres:      container 5432  → host 5446 (db=app_xayqujrv user=appxayqujrv)
  - redis:         container 6379  → host 6396
  - mock-receiver: container 9001  → host 9001 (in-cluster: http://mock-receiver:9001)

Override any value via environment variable (CI / different runtime).
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(_here, ".env"),
        os.path.normpath(os.path.join(_here, "..", "..", "task_xayqujrv", "docker", ".env")),
    ):
        if os.path.isfile(candidate):
            load_dotenv(candidate, override=False)
            break
except Exception:
    pass


def _detect_workspace_dir() -> str:
    env_val = os.environ.get("WORKSPACE_DIR")
    if env_val:
        return env_val
    here = os.path.dirname(os.path.abspath(__file__))
    task_e_dir = os.path.dirname(here)
    task_gen_dir = os.path.dirname(task_e_dir)
    task_e_name = os.path.basename(task_e_dir)
    if task_e_name.endswith("_e"):
        task_name = task_e_name[:-2]
        candidate = os.path.join(task_gen_dir, task_name, "docker", "workspace")
        if os.path.isdir(candidate):
            return candidate
    return "/app"


WORKSPACE_DIR = _detect_workspace_dir()

# ---------------- Network / URLs ----------------
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8023")
API_BASE_URL = os.environ.get("API_BASE_URL", APP_BASE_URL.rstrip("/") + "/api/v1")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:8024")

MOCK_RECEIVER_URL = os.environ.get("MOCK_RECEIVER_URL", "http://localhost:9011")
MOCK_RECEIVER_INTERNAL_URL = os.environ.get(
    "MOCK_RECEIVER_INTERNAL_URL", "http://mock-receiver:9001"
)

# ---------------- Database ----------------
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5446"))
DB_NAME = os.environ.get("DB_NAME", "app_xayqujrv")
DB_USER = os.environ.get("DB_USER", "appxayqujrv")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123xayqujrv")

# ---------------- Redis ----------------
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6396"))

# ---------------- Containers ----------------
APP_CONTAINER = os.environ.get("APP_CONTAINER", "task_xayqujrv-app")
WORKER_CONTAINER = os.environ.get("WORKER_CONTAINER", "task_xayqujrv-worker")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "task_xayqujrv-postgres")
REDIS_CONTAINER = os.environ.get("REDIS_CONTAINER", "task_xayqujrv-redis")
MOCK_CONTAINER = os.environ.get("MOCK_CONTAINER", "task_xayqujrv-mock-receiver")

# ---------------- LLM (P17 llm-judge) ----------------
LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")


def assert_llm_configured() -> None:
    missing = [n for n, v in [
        ("LLM_API_KEY", LLM_API_KEY),
        ("LLM_API_BASE", LLM_API_BASE),
        ("LLM_MODEL", LLM_MODEL),
    ] if not v]
    if missing:
        raise SystemExit(
            "LLM judge is enabled but the following environment variables "
            f"are not set: {missing}. Export them before running with --with-llm "
            "(e.g. LLM_API_KEY=sk-..., LLM_API_BASE=https://api.openai.com/v1, "
            "LLM_MODEL=gpt-4o-mini)."
        )

# ---------------- Filesystem ----------------
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# ---------------- Timeouts ----------------
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "20"))
DOCKER_EXEC_TIMEOUT = int(os.environ.get("DOCKER_EXEC_TIMEOUT", "300"))

# ---------------- Test users ----------------
TEST_USERS = {
    "admin": {
        "username": os.environ.get("EVAL_ADMIN_USERNAME", "eval_admin"),
        "email":    os.environ.get("EVAL_ADMIN_EMAIL", "eval_admin@eval.test"),
        "password": os.environ.get("EVAL_ADMIN_PASSWORD", "EvalPass12345!"),
    },
    "user": {
        "username": os.environ.get("EVAL_USER_USERNAME", "eval_user"),
        "email":    os.environ.get("EVAL_USER_EMAIL", "eval_user@eval.test"),
        "password": os.environ.get("EVAL_USER_PASSWORD", "EvalPass12345!"),
    },
    "approver": {
        "username": os.environ.get("EVAL_APPROVER_USERNAME", "eval_approver"),
        "email":    os.environ.get("EVAL_APPROVER_EMAIL", "eval_approver@eval.test"),
        "password": os.environ.get("EVAL_APPROVER_PASSWORD", "EvalPass12345!"),
    },
    "anonymous": {
        "username": "",
        "email": "",
        "password": "",
    },
}

FRONTEND_LOGIN = {
    "mode": "browser",
    "url": "{{base_url}}/login",
    "user_selector": "input[name='email']",
    "pass_selector": "#password",
    "submit_selector": "#login-btn",
    "user": TEST_USERS["admin"]["email"],
    "password": TEST_USERS["admin"]["password"],
    "wait_after": "networkidle",
    "timeout_ms": 30000,
}

# ---------------- Auth header style ----------------
AUTH_HEADER_NAME = "Authorization"
AUTH_HEADER_VALUE_PREFIX = "Token "
ENV_KEY_HEADER_NAME = "X-Environment-Key"

# ---------------- Default org / project / env names used by tests ----------------
EVAL_ORG_NAME = os.environ.get("EVAL_ORG_NAME", "Eval Org")
EVAL_PROJECT_NAME = os.environ.get("EVAL_PROJECT_NAME", "Eval Project")
EVAL_ENV_NAME = os.environ.get("EVAL_ENV_NAME", "Development")

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
