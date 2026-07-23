
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

EVAL_DIR: Path = Path(__file__).resolve().parent

TASK_GEN_DIR: Path = EVAL_DIR.parent.parent
TASK_DIR: Path = TASK_GEN_DIR / "task_rjhcjrst"

WORKSPACE_DIR: Path = Path(
    os.environ.get("WORKSPACE_DIR", str(TASK_DIR / "docker" / "workspace"))
)

DOCKER_DIR: Path = TASK_DIR / "docker"
RESULTS_DIR: Path = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DAG_FILE: Path = EVAL_DIR / "dag.json"
SCORING_CONFIG_FILE: Path = EVAL_DIR / "scoring_config.json"
KB_FILE: Path = TASK_DIR / "kb" / "knowledge_base.json"
QUALITY_REPORT_FILE: Path = EVAL_DIR / "dag_quality_report.json"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

APP_HOST: str = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT: int = int(os.environ.get("APP_PORT", "8022"))
APP_BASE_URL: str = os.environ.get("APP_BASE_URL", f"http://{APP_HOST}:{APP_PORT}")
API_BASE_URL: str = f"{APP_BASE_URL}/api"
API_V1_BASE: str = f"{APP_BASE_URL}/api/v1"

DEFAULT_API_HEADERS: dict = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-PFM-Client": "eval-harness/1.0",
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

DB_HOST: str = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT: int = int(os.environ.get("DB_PORT", "3309"))
DB_NAME: str = os.environ.get("DB_NAME", "app_rjhcjrst")
DB_USER: str = os.environ.get("DB_USER", "apprjhcjrst")
DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "app123rjhcjrst")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

APP_CONTAINER: str = os.environ.get("APP_CONTAINER", "task_rjhcjrst-app")
DB_CONTAINER: str = os.environ.get("DB_CONTAINER", "task_rjhcjrst-db")
MOCK_RECEIVER_CONTAINER: str = os.environ.get("MOCK_RECEIVER_CONTAINER", "task_rjhcjrst-mock-receiver")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

MOCK_RECEIVER_HOST: str = os.environ.get("MOCK_RECEIVER_HOST", "127.0.0.1")
MOCK_RECEIVER_PORT: int = int(os.environ.get("MOCK_RECEIVER_PORT", "9001"))
MOCK_RECEIVER_URL: str = f"http://{MOCK_RECEIVER_HOST}:{MOCK_RECEIVER_PORT}"
MOCK_RECEIVER_URL_FROM_APP: str = os.environ.get(
    "MOCK_RECEIVER_URL_FROM_APP", "http://host.docker.internal:9001"
)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL", "admin@pfm.local")
ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "secret123")

_EVAL_RBAC_PASS = "EvalRBACPass123!"
RBAC_USERS: dict = {
    "admin":              {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    "owner":              {"email": "owner_user@pfm.local",              "password": _EVAL_RBAC_PASS},
    "ro":                 {"email": "ro_user@pfm.local",                 "password": _EVAL_RBAC_PASS},
    "full":               {"email": "full_user@pfm.local",               "password": _EVAL_RBAC_PASS},
    "mng_trx":            {"email": "mng_trx_user@pfm.local",            "password": _EVAL_RBAC_PASS},
    "mng_meta":           {"email": "mng_meta_user@pfm.local",           "password": _EVAL_RBAC_PASS},
    "mng_budgets":        {"email": "mng_budgets_user@pfm.local",        "password": _EVAL_RBAC_PASS},
    "mng_piggies":        {"email": "mng_piggies_user@pfm.local",        "password": _EVAL_RBAC_PASS},
    "mng_subscriptions":  {"email": "mng_subscriptions_user@pfm.local",  "password": _EVAL_RBAC_PASS},
    "mng_rules":          {"email": "mng_rules_user@pfm.local",          "password": _EVAL_RBAC_PASS},
    "mng_recurring":      {"email": "mng_recurring_user@pfm.local",      "password": _EVAL_RBAC_PASS},
    "mng_webhooks":       {"email": "mng_webhooks_user@pfm.local",       "password": _EVAL_RBAC_PASS},
    "mng_currencies":     {"email": "mng_currencies_user@pfm.local",     "password": _EVAL_RBAC_PASS},
    "read_budgets":       {"email": "read_budgets_user@pfm.local",       "password": _EVAL_RBAC_PASS},
    "read_piggies":       {"email": "read_piggies_user@pfm.local",       "password": _EVAL_RBAC_PASS},
    "read_subscriptions": {"email": "read_subscriptions_user@pfm.local", "password": _EVAL_RBAC_PASS},
    "read_rules":         {"email": "read_rules_user@pfm.local",         "password": _EVAL_RBAC_PASS},
    "read_recurring":     {"email": "read_recurring_user@pfm.local",     "password": _EVAL_RBAC_PASS},
    "read_webhooks":      {"email": "read_webhooks_user@pfm.local",      "password": _EVAL_RBAC_PASS},
    "read_currencies":    {"email": "read_currencies_user@pfm.local",    "password": _EVAL_RBAC_PASS},
    "view_reports":       {"email": "view_reports_user@pfm.local",       "password": _EVAL_RBAC_PASS},
    "view_memberships":   {"email": "view_memberships_user@pfm.local",   "password": _EVAL_RBAC_PASS},
    "view_mem":           {"email": "view_memberships_user@pfm.local",   "password": _EVAL_RBAC_PASS},
    "alice":              {"email": "alice_user@pfm.local",              "password": _EVAL_RBAC_PASS},
    "user_b_diff_group":  {"email": "alice_user@pfm.local",              "password": _EVAL_RBAC_PASS},
}
RBAC_USERS = {**RBAC_USERS, **{f"rbac_{k}": v for k, v in RBAC_USERS.items() if k != "admin"}}

RBAC_USER_GROUP_B: dict = {
    "email": "alice@pfm.local", "password": "alicepass123",
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

PASSPORT_CLIENT_ID: str = os.environ.get("PASSPORT_CLIENT_ID", "3")
PASSPORT_CLIENT_SECRET: str = os.environ.get("PASSPORT_CLIENT_SECRET", "6vY0rE6ZBmkFfaogOdYP3dTJKHQLAAw3f3V2hhwn")
PASSPORT_GRANT_TYPE: str = os.environ.get("PASSPORT_GRANT_TYPE", "password")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

STATIC_CRON_TOKEN: str = os.environ.get(
    "STATIC_CRON_TOKEN", "pfm_cron_token_please_change_3xx"
)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

LLM_API_KEY: str = os.environ.get(
    "LLM_API_KEY",
    os.environ.get("OPENAI_API_KEY", ""),
)
LLM_API_BASE: str = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
LLM_TEMPERATURE: float = float(os.environ.get("LLM_TEMPERATURE", "0.0"))
LLM_TIMEOUT_SECONDS: int = int(os.environ.get("LLM_TIMEOUT_SECONDS", "120"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

HTTP_TIMEOUT: int = int(os.environ.get("HTTP_TIMEOUT", "15"))
DB_TIMEOUT: int = int(os.environ.get("DB_TIMEOUT", "10"))
DOCKER_EXEC_TIMEOUT: int = int(os.environ.get("DOCKER_EXEC_TIMEOUT", "60"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

SKIP_EMAIL_TESTS: bool = os.environ.get("SKIP_EMAIL_TESTS", "1") == "1"
SKIP_BROWSER_TESTS: bool = os.environ.get("SKIP_BROWSER_TESTS", "0") == "1"

P13_ALLOW_DB_TOKEN_FALLBACK: bool = (
    os.environ.get("P13_ALLOW_DB_TOKEN_FALLBACK", "1") == "1"
)


def dump() -> dict:
    return {
        "APP_BASE_URL": APP_BASE_URL,
        "API_BASE_URL": API_BASE_URL,
        "DB_HOST": DB_HOST,
        "DB_PORT": DB_PORT,
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "APP_CONTAINER": APP_CONTAINER,
        "DB_CONTAINER": DB_CONTAINER,
        "MOCK_RECEIVER_URL": MOCK_RECEIVER_URL,
        "ADMIN_EMAIL": ADMIN_EMAIL,
        "STATIC_CRON_TOKEN": STATIC_CRON_TOKEN[:8] + "...",
        "LLM_MODEL": LLM_MODEL,
        "HTTP_TIMEOUT": HTTP_TIMEOUT,
        "rbac_user_count": len(RBAC_USERS),
    }


FRONTEND_BASE_URL = APP_BASE_URL
FRONTEND_LOGIN = {
    "url": "{{base_url}}/login",
    "method": "POST",
    "data": {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    "csrf": {
        "url": "{{base_url}}/login",
        "regex": r'name="_token"\s+(?:type="hidden"\s+)?value="([^"]+)"',
        "field": "_token",
    },
    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
}
