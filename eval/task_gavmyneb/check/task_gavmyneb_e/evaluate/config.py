import os
from pathlib import Path

# =============================================================================
# =============================================================================
EVAL_DIR = Path(__file__).resolve().parent
TASK_DIR = EVAL_DIR.parent.parent.parent / "tasks" / "task_gavmyneb"
WORKSPACE_DIR = TASK_DIR / "docker" / "workspace"
DOCKER_COMPOSE_FILE = TASK_DIR / "docker" / "docker-compose.yml"
DAG_FILE = EVAL_DIR / "dag.json"
SCORING_CONFIG_FILE = EVAL_DIR / "scoring_config.json"
KB_FILE = TASK_DIR / "kb" / "knowledge_base.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# =============================================================================
APP_HOST = os.getenv("HARNESS_APP_HOST", "localhost")
APP_PORT = int(os.getenv("HARNESS_APP_PORT", "8017"))
API_BASE_URL = f"http://{APP_HOST}:{APP_PORT}"
GRAPHQL_ENDPOINT = "/api/graphql"
HEALTH_ENDPOINT = "/health_check"
READINESS_ENDPOINT = "/readiness"

# =============================================================================
# =============================================================================
DB_HOST = os.getenv("HARNESS_DB_HOST", "localhost")
DB_PORT = int(os.getenv("HARNESS_DB_PORT", "5442"))
DB_NAME = os.getenv("HARNESS_DB_NAME", "app_gavmyneb")
DB_USER = os.getenv("HARNESS_DB_USER", "appgavmyneb")
DB_PASSWORD = os.getenv("HARNESS_DB_PASSWORD", "app123gavmyneb")

# =============================================================================
# =============================================================================
REDIS_HOST = os.getenv("HARNESS_REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("HARNESS_REDIS_PORT", "6381"))
REDIS_DB = int(os.getenv("HARNESS_REDIS_DB", "0"))

# =============================================================================
# =============================================================================
APP_CONTAINER = os.getenv("HARNESS_APP_CONTAINER", "lms-web")
DB_CONTAINER = os.getenv("HARNESS_DB_CONTAINER", "lms-db")
REDIS_CONTAINER = os.getenv("HARNESS_REDIS_CONTAINER", "lms-redis")
WORKER_CONTAINER = os.getenv("HARNESS_WORKER_CONTAINER", "lms-worker")

# =============================================================================
# =============================================================================
_DEFAULT_PWD = os.getenv("DEFAULT_PASSWORD", "Admin123!@#")

TEST_USERS = {
    "admin":         {
        "email":    os.getenv("ADMIN_EMAIL",         "eval_admin@test.com"),
        "password": os.getenv("ADMIN_PASSWORD",      _DEFAULT_PWD),
        "role_aliases": ["admin", "administrator", "site_admin"],
    },
    "teacher":       {
        "email":    os.getenv("TEACHER_EMAIL",       "eval_teacher@test.com"),
        "password": os.getenv("TEACHER_PASSWORD",    _DEFAULT_PWD),
        "role_aliases": ["teacher", "instructor", "educator"],
    },
    "student":       {
        "email":    os.getenv("STUDENT_EMAIL",       "eval_student@test.com"),
        "password": os.getenv("STUDENT_PASSWORD",    _DEFAULT_PWD),
        "role_aliases": ["student", "learner", "pupil"],
    },
    "observer":      {
        "email":    os.getenv("OBSERVER_EMAIL",      "eval_observer@test.com"),
        "password": os.getenv("OBSERVER_PASSWORD",   _DEFAULT_PWD),
        "role_aliases": ["observer", "parent", "guardian"],
    },
    "ta":            {
        "email":    os.getenv("TA_EMAIL",            "eval_ta@test.com"),
        "password": os.getenv("TA_PASSWORD",         _DEFAULT_PWD),
        "role_aliases": ["ta", "teaching_assistant", "grader"],
    },
    "account_admin": {
        "email":    os.getenv("ACCOUNT_ADMIN_EMAIL", "eval_account_admin@test.com"),
        "password": os.getenv("ACCOUNT_ADMIN_PASSWORD", _DEFAULT_PWD),
        "role_aliases": ["account_admin", "org_admin", "tenant_admin"],
    },
}

SESSION_COOKIE_NAME = "_session_id"
SESSION_COOKIE_CANDIDATES = ["_session_id", "_normandy_session", "session_id",
                              "_lms_session", "_app_session"]

FRONTEND_LOGIN = {
    "mode": "cookie",
    "url": f"{API_BASE_URL}/login/canvas",
    "method": "POST",
    "data": {
        "pseudonym_session[unique_id]": TEST_USERS["admin"]["email"],
        "pseudonym_session[password]": TEST_USERS["admin"]["password"],
    },
    "csrf": {
        "url": f"{API_BASE_URL}/login/canvas",
        "regex": r'name="authenticity_token"[^>]*value="([^"]*)"',
        "field": "authenticity_token",
    },
}

# =============================================================================
# =============================================================================
LLM_JUDGE_PROVIDER = os.getenv("HARNESS_LLM_JUDGE_PROVIDER", "openai")
LLM_JUDGE_MODEL    = os.getenv("HARNESS_LLM_JUDGE_MODEL",    "gpt-4o-mini")
LLM_JUDGE_API_KEY  = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
LLM_JUDGE_API_BASE = os.getenv("HARNESS_LLM_JUDGE_API_BASE", "https://api.openai.com/v1")
LLM_JUDGE_TIMEOUT  = int(os.getenv("HARNESS_LLM_JUDGE_TIMEOUT", "120"))
LLM_JUDGE_PASS_RATIO = float(os.getenv("HARNESS_LLM_JUDGE_PASS_RATIO", "0.6"))
PARTIAL_PASS_RATIO   = float(os.getenv("HARNESS_PARTIAL_PASS_RATIO",   "0.5"))

# =============================================================================
# =============================================================================
DEFAULT_HTTP_TIMEOUT = int(os.getenv("HARNESS_HTTP_TIMEOUT", "30"))
DEFAULT_DB_QUERY_TIMEOUT = int(os.getenv("HARNESS_DB_TIMEOUT", "15"))
DEFAULT_DOCKER_EXEC_TIMEOUT = int(os.getenv("HARNESS_DOCKER_TIMEOUT", "60"))
PRIMITIVE_CHAIN_PARALLEL = False

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
