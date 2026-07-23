from __future__ import annotations

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

REPO_ROOT = str(Path(__file__).resolve().parents[3])


def _detect_workspace_dir() -> str:
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
    return "/var/www/html"


def _detect_kb_path() -> str:
    env_val = os.environ.get("KB_PATH")
    if env_val:
        return env_val
    here = os.path.dirname(os.path.abspath(__file__))
    task_e_dir = os.path.dirname(here)
    check_dir = os.path.dirname(task_e_dir)
    repo_root = os.path.dirname(check_dir)
    task_e_name = os.path.basename(task_e_dir)
    if task_e_name.endswith("_e"):
        task_name = task_e_name[:-2]
        candidate = os.path.join(repo_root, "tasks", task_name, "kb", "knowledge_base.json")
        if os.path.isfile(candidate):
            return candidate
    return ""


EVALUATE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = Path(_detect_workspace_dir())
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", str(EVALUATE_DIR / "results")))
RESULTS_DIR.mkdir(exist_ok=True)
DAG_PATH = EVALUATE_DIR / "dag.json"
SCORING_CONFIG_PATH = EVALUATE_DIR / "scoring_config.json"
KB_PATH = Path(_detect_kb_path()) if _detect_kb_path() else None

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

APP_PORT = int(os.environ.get("TASK_APP_PORT", "8030"))
APP_BASE_URL = os.environ.get("TASK_APP_BASE_URL", f"http://localhost:{APP_PORT}")
SITE_ID = os.environ.get("TASK_SITE_ID", "default")
API_BASE_URL = f"{APP_BASE_URL}/apis/{SITE_ID}/api"
FHIR_BASE_URL = f"{APP_BASE_URL}/apis/{SITE_ID}/fhir"
PORTAL_BASE_URL = f"{APP_BASE_URL}/apis/{SITE_ID}/portal"
OAUTH2_BASE_URL = f"{APP_BASE_URL}/oauth2/{SITE_ID}"
WELL_KNOWN_BASE_URL = f"{APP_BASE_URL}/.well-known"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

DB_HOST = os.environ.get("TASK_DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("TASK_DB_PORT", "3310"))
DB_NAME = os.environ.get("TASK_DB_NAME", "app_lgzivily")
DB_USER = os.environ.get("TASK_DB_USER", "applgzivily")
DB_PASSWORD = os.environ.get("TASK_DB_PASSWORD", "app123lgzivily")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

APP_CONTAINER = os.environ.get("TASK_APP_CONTAINER", "task_lgzivily_app")
DB_CONTAINER = os.environ.get("TASK_DB_CONTAINER", "task_lgzivily_db")
COMPOSE_PROJECT = os.environ.get("TASK_COMPOSE_PROJECT", "task_lgzivily")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_DEFAULT_PW = os.environ.get("EVAL_DEFAULT_PASSWORD", "pass")

TEST_USERS = {
    "admin": {
        "username": os.environ.get("ADMIN_USERNAME", "admin"),
        "password": os.environ.get("ADMIN_PASSWORD", _DEFAULT_PW),
        "aro_group": "admin",
        "description": "Administrators (super-user)",
    },
    "phys": {
        "username": os.environ.get("PHYS_USERNAME", "evalphys"),
        "password": os.environ.get("PHYS_PASSWORD", _DEFAULT_PW),
        "aro_group": "phys",
        "description": "Physicians (created by harness if missing)",
    },
    "clin": {
        "username": os.environ.get("CLIN_USERNAME", "evalclin"),
        "password": os.environ.get("CLIN_PASSWORD", _DEFAULT_PW),
        "aro_group": "clin",
        "description": "Clinicians",
    },
    "front": {
        "username": os.environ.get("FRONT_USERNAME", "evalfo"),
        "password": os.environ.get("FRONT_PASSWORD", _DEFAULT_PW),
        "aro_group": "front",
        "description": "Front Office",
    },
    "acct": {
        "username": os.environ.get("ACCT_USERNAME", "evalacct"),
        "password": os.environ.get("ACCT_PASSWORD", _DEFAULT_PW),
        "aro_group": "acct",
        "description": "Accounting",
    },
    "recep": {
        "username": os.environ.get("RECEP_USERNAME", "evalrec"),
        "password": os.environ.get("RECEP_PASSWORD", _DEFAULT_PW),
        "aro_group": "recep",
        "description": "Receptionist",
    },
    "emergency": {
        "username": os.environ.get("EMERGENCY_USERNAME", "evalemerg"),
        "password": os.environ.get("EMERGENCY_PASSWORD", _DEFAULT_PW),
        "aro_group": "emergency",
        "description": "Emergency Login (break-glass)",
    },
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", APP_BASE_URL)
FRONTEND_LOGIN = {
    "mode": "browser",
    "url": f"{APP_BASE_URL}/interface/login/login.php?site={SITE_ID}",
    "user_selector": "#authUser",
    "pass_selector": "#clearPass",
    "submit_selector": "#login-button",
    "user": TEST_USERS["admin"]["username"],
    "password": TEST_USERS["admin"]["password"],
    "wait_after": "networkidle",
    "timeout_ms": 30000,
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

OAUTH2_DEFAULT_REDIRECT_URI = os.environ.get(
    "TASK_OAUTH2_REDIRECT_URI",
    "http://localhost/eval-callback",
)
OAUTH2_ACCESS_TOKEN_LIFETIME = int(
    os.environ.get("TASK_OAUTH2_ACCESS_TOKEN_LIFETIME", "600"),
)
OAUTH2_REFRESH_TOKEN_LIFETIME = int(
    os.environ.get("TASK_OAUTH2_REFRESH_TOKEN_LIFETIME", "3600"),
)
OAUTH2_KEYS_DIR_IN_CONTAINER = os.environ.get(
    "TASK_OAUTH2_KEYS_DIR",
    "/var/www/html/sites/default/documents/oauth2",
)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

LLM_API_BASE = os.environ.get(
    "LLM_API_BASE",
    os.environ.get("TASK_LLM_API_BASE", "https://api.commonstack.ai/v1"),
)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_MODEL = os.environ.get(
    "LLM_MODEL",
    os.environ.get("TASK_LLM_MODEL", "claude-sonnet-4-5-20250929"),
)
LLM_TIMEOUT_SEC = int(os.environ.get("TASK_LLM_TIMEOUT_SEC", "60"))
LLM_MAX_TOKENS = int(os.environ.get("TASK_LLM_MAX_TOKENS", "1024"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

HTTP_TIMEOUT_SEC = int(os.environ.get("TASK_HTTP_TIMEOUT_SEC", "15"))
DOCKER_EXEC_TIMEOUT_SEC = int(os.environ.get("TASK_DOCKER_EXEC_TIMEOUT_SEC", "120"))
POLL_INTERVAL_SEC = int(os.environ.get("TASK_POLL_INTERVAL_SEC", "5"))
POLL_MAX_SEC = int(os.environ.get("TASK_POLL_MAX_SEC", "60"))


def get_user_context(role: str) -> dict:
    return TEST_USERS.get(role, TEST_USERS["admin"])


SOURCE_PROJECT_TABLE_RENAMES = {
    "calendar_events": "openemr_postcalendar_events",
    "calendar_categories": "openemr_postcalendar_categories",
    "module_vars": "openemr_module_vars",
    "module_registry": "openemr_modules",
}

