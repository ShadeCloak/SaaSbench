
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

EVAL_DIR: Path = Path(__file__).resolve().parent

TASK_GEN_DIR: Path = EVAL_DIR.parent.parent
TASK_DIR: Path = TASK_GEN_DIR / "task_iyjruvfz"

WORKSPACE_DIR: Path = Path(
    os.environ.get("WORKSPACE_DIR", str(TASK_DIR / "docker" / "workspace"))
)

DOCKER_DIR: Path = TASK_DIR / "docker"
RESULTS_DIR: Path = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DAG_FILE: Path = EVAL_DIR / "dag.json"
SCORING_CONFIG_FILE: Path = EVAL_DIR / "scoring_config.json"
KB_FILE: Path = TASK_DIR / "kb" / "knowledge_base.json"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

APP_HOST: str = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT: int = int(os.environ.get("APP_PORT", "8016"))
APP_BASE_URL: str = os.environ.get("APP_BASE_URL", f"http://{APP_HOST}:{APP_PORT}")

API_V1_BASE: str = f"{APP_BASE_URL}/api/v1"
API_V2_BASE: str = f"{APP_BASE_URL}/api/v2"
TRPC_BASE: str = f"{APP_BASE_URL}/api/trpc"

DEFAULT_V2_HEADERS: dict = {
    os.environ.get("V2_VERSION_HEADER_NAME", "Api-Version"): os.environ.get("API_VERSION", "2024-08-13"),
    "Content-Type": "application/json",
    "Accept": "application/json",
}

DB_HOST: str = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT: int = int(os.environ.get("DB_PORT", "5441"))
DB_NAME: str = os.environ.get("DB_NAME", "app_iyjruvfz")
DB_USER: str = os.environ.get("DB_USER", "appiyjruvfz")
DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "app123iyjruvfz")

REDIS_HOST: str = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6391"))

APP_CONTAINER: str = os.environ.get("APP_CONTAINER", "task_iyjruvfz-app")
DB_CONTAINER: str = os.environ.get("DB_CONTAINER", "task_iyjruvfz-postgres")
REDIS_CONTAINER: str = os.environ.get("REDIS_CONTAINER", "task_iyjruvfz-redis")

# ---------------------------------------------------------------------------
#
#
#
# ---------------------------------------------------------------------------

_DEFAULT_USER_PASSWORD = os.environ.get("EVAL_USER_DEFAULT_PASSWORD", "ChangeMe!2026")

TEST_USERS: dict = {
    "admin": {
        "username": os.environ.get("EVAL_USER_ADMIN_USERNAME", "admin"),
        "email": os.environ.get("EVAL_USER_ADMIN_EMAIL", "admin@example.com"),
        "password": os.environ.get("EVAL_USER_ADMIN_PASSWORD", _DEFAULT_USER_PASSWORD),
        "user_permission_role": "ADMIN",
        "membership_role": "ADMIN",
    },
    "owner": {
        "username": os.environ.get("EVAL_USER_OWNER_USERNAME", "owner"),
        "email": os.environ.get("EVAL_USER_OWNER_EMAIL", "owner@example.com"),
        "password": os.environ.get("EVAL_USER_OWNER_PASSWORD", _DEFAULT_USER_PASSWORD),
        "user_permission_role": "USER",
        "membership_role": "OWNER",
    },
    "member": {
        "username": os.environ.get("EVAL_USER_MEMBER_USERNAME", "member"),
        "email": os.environ.get("EVAL_USER_MEMBER_EMAIL", "member@example.com"),
        "password": os.environ.get("EVAL_USER_MEMBER_PASSWORD", _DEFAULT_USER_PASSWORD),
        "user_permission_role": "USER",
        "membership_role": "MEMBER",
    },
    "user": {
        "_inclusivity_2026_04_30_alias": "Alias for 'member' — dag.json uses role='user' for some RBAC tests. Cal.com baseline only seeds admin/pro/free, so 'user' role maps to the same credentials as 'member' (role-based privileges still validated via membership_role).",
        "username": os.environ.get("EVAL_USER_MEMBER_USERNAME", "member"),
        "email": os.environ.get("EVAL_USER_MEMBER_EMAIL", "member@example.com"),
        "password": os.environ.get("EVAL_USER_MEMBER_PASSWORD", _DEFAULT_USER_PASSWORD),
        "user_permission_role": "USER",
        "membership_role": "MEMBER",
    },
    "global_admin": {
        "_inclusivity_2026_04_30_alias": "Alias for 'admin' — dag.json uses role='global_admin' for some RBAC tests. Cal.com baseline doesn't seed a separate global_admin so this maps to the same credentials as 'admin' (which has user_permission_role=ADMIN i.e. global admin in Cal.com).",
        "username": os.environ.get("EVAL_USER_ADMIN_USERNAME", "admin"),
        "email": os.environ.get("EVAL_USER_ADMIN_EMAIL", "admin@example.com"),
        "password": os.environ.get("EVAL_USER_ADMIN_PASSWORD", _DEFAULT_USER_PASSWORD),
        "user_permission_role": "ADMIN",
        "membership_role": "ADMIN",
    },
}


def role_match(actual, expected) -> bool:
    if actual is None or expected is None:
        return actual == expected
    return str(actual).casefold() == str(expected).casefold()

RANDOM_SUFFIX: str = os.environ.get("EVAL_RANDOM_SUFFIX", "evaliyj")

# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------

LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE: str = os.environ.get("LLM_API_BASE", "")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "claude-sonnet-4-6")

LLM_TIMEOUT_SEC: int = int(os.environ.get("LLM_TIMEOUT_SEC", "60"))


def llm_judge_enabled() -> bool:
    return bool(LLM_API_KEY and LLM_API_BASE)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

HTTP_TIMEOUT_SEC: int = int(os.environ.get("HTTP_TIMEOUT_SEC", "15"))
DB_TIMEOUT_SEC: int = int(os.environ.get("DB_TIMEOUT_SEC", "10"))

SKIP_TEARDOWN: bool = os.environ.get("SKIP_TEARDOWN", "1") == "1"

MOCK_WEBHOOK_PORT: int = int(os.environ.get("MOCK_WEBHOOK_PORT", "9012"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def db_connection_kwargs() -> dict:

    return {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "connect_timeout": DB_TIMEOUT_SEC,
    }


def database_url(driver: str = "postgresql") -> str:
    return f"{driver}://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def app_url(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return f"{APP_BASE_URL}{path}"

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
