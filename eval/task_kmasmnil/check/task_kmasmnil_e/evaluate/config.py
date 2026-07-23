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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8024")
API_BASE_URL = APP_BASE_URL + "/api"

FRONTEND_LOGIN = {
    "mode": "browser",
    "url": "{{base_url}}/auth/login",
    "reveal_selector": "button:has-text('Login with Email')",
    "user_selector": "#email",
    "pass_selector": "#password",
    "submit_press_enter": True,
    "user": os.environ.get("ADMIN_EMAIL", "eval_admin@test.com"),
    "password": os.environ.get("ADMIN_PASSWORD", "EvalAdmin123!@#"),
    "wait_after": "networkidle",
    "timeout_ms": 30000,
}

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5447"))
DB_NAME = os.environ.get("DB_NAME", "app_kmasmnil")
DB_USER = os.environ.get("DB_USER", "appkmasmnil")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123kmasmnil")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

APP_CONTAINER = os.environ.get("APP_CONTAINER", "xm_app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "xm_db")
REDIS_CONTAINER = os.environ.get("REDIS_CONTAINER", "xm_redis")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

NEXTAUTH_SECRET = os.environ.get("NEXTAUTH_SECRET", "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0")
CRON_SECRET = os.environ.get("CRON_SECRET", "xm_cron_secret_k8m7n6p5q4r3s2t1")

TEST_USERS = {
    "admin": {
        "name":     os.environ.get("ADMIN_NAME",     "Eval Admin"),
        "email":    os.environ.get("ADMIN_EMAIL",    "eval_admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalAdmin123!@#"),
        "role":     os.environ.get("ADMIN_ROLE",     "owner"),
    },
    "member": {
        "name":     os.environ.get("MEMBER_NAME",     "Eval Member"),
        "email":    os.environ.get("MEMBER_EMAIL",    "eval_member@test.com"),
        "password": os.environ.get("MEMBER_PASSWORD", "EvalMember123!@#"),
        "role":     os.environ.get("MEMBER_ROLE",     "member"),
    },
}

ROLE_ALIASES = {
    "owner":  ["owner", "admin", "Owner", "Admin", "administrator", "Administrator"],
    "member": ["member", "user", "Member", "User", "developer", "Developer"],
}

def role_match(impl_role: str, expected_role: str) -> bool:
    if not isinstance(impl_role, str) or not isinstance(expected_role, str):
        return False
    aliases = ROLE_ALIASES.get(expected_role, [expected_role])
    impl_lower = impl_role.lower()
    return impl_lower in [a.lower() for a in aliases]

API_V1_PREFIX = os.environ.get("API_V1_PREFIX", "/api/v1")
API_V2_PREFIX = os.environ.get("API_V2_PREFIX", "/api/v2")
API_V3_PREFIX = os.environ.get("API_V3_PREFIX", "/api/v3")

API_KEY_HASH_FIELD = os.environ.get("API_KEY_HASH_FIELD", "hashedKey")
API_KEY_TABLE = os.environ.get("API_KEY_TABLE", "ApiKey")
API_KEY_TABLE_FALLBACKS = ["ApiKey", "api_keys", "api_key", "ApiKeys"]
API_KEY_HASH_FIELD_FALLBACKS = ["hashedKey", "hashed_key", "key_hash", "keyHash"]

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DAG_PATH = os.path.join(os.path.dirname(__file__), "dag.json")
SCORING_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scoring_config.json")

HTTP_TIMEOUT = 15
MAX_RETRIES = 2

EVAL_API_KEY = os.environ.get("EVAL_API_KEY", "xmk_evalTestSecretForSmoke2026")
EVAL_READ_API_KEY = os.environ.get("EVAL_READ_API_KEY", "xmk_evalReadKey2026")
EVAL_WRITE_API_KEY = os.environ.get("EVAL_WRITE_API_KEY", "xmk_evalWriteKey2026")
EVAL_WRONG_ENV_API_KEY = os.environ.get("EVAL_WRONG_ENV_API_KEY", "xmk_evalWrongEnvKey2026")
EVAL_ORG_ID = os.environ.get("EVAL_ORG_ID", "c19d51cebo3od2b1d7homp9wl")
EVAL_PROJECT_ID = os.environ.get("EVAL_PROJECT_ID", "c19d51ceb0zesjg8y6fiy8gly")
EVAL_ENV_PROD = os.environ.get("EVAL_ENV_PROD", "c19d51ceb5j2rsrlpzc2svv9a")
EVAL_ENV_DEV = os.environ.get("EVAL_ENV_DEV", "c19d51ceb0hl9iiqoe3nvn3ig")
EVAL_ADMIN_EMAIL = os.environ.get("EVAL_ADMIN_EMAIL", "eval_admin@test.com")

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
