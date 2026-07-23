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

APP_PORT = int(os.environ.get("APP_PORT", "8003"))
APP_BASE_URL = os.environ.get("APP_BASE_URL", f"http://localhost:{APP_PORT}")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "app_db")
DB_USER = os.environ.get("DB_USER", "app")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123")

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

APP_CONTAINER = os.environ.get("APP_CONTAINER", "ecommerce-app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "ecommerce-db")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")

HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "15"))

TEST_USERS = {
    "admin": {
        "email": os.environ.get("ADMIN_EMAIL", "eval_admin@test.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "EvalAdmin123!"),
    },
    "super_admin": {
        "email": os.environ.get("SUPER_ADMIN_EMAIL", "eval_superadmin@test.com"),
        "password": os.environ.get("SUPER_ADMIN_PASSWORD", "EvalSuperAdmin123!"),
    },
    "limited_admin": {
        "email": os.environ.get("LIMITED_ADMIN_EMAIL", "eval_limited@test.com"),
        "password": os.environ.get("LIMITED_ADMIN_PASSWORD", "EvalLimited123!"),
    },
    "no_role_user": {
        "email": os.environ.get("NO_ROLE_USER_EMAIL", "eval_norole@test.com"),
        "password": os.environ.get("NO_ROLE_USER_PASSWORD", "EvalNoRole123!"),
    },
    "product_reader": {
        "email": os.environ.get("PRODUCT_READER_EMAIL", "eval_prodreader@test.com"),
        "password": os.environ.get("PRODUCT_READER_PASSWORD", "EvalProdReader123!"),
    },
    "product_full_reader": {
        "email": os.environ.get("PRODUCT_FULL_READER_EMAIL", "eval_prodfull@test.com"),
        "password": os.environ.get("PRODUCT_FULL_READER_PASSWORD", "EvalProdFull123!"),
    },
    "customer": {
        "email": os.environ.get("CUSTOMER_EMAIL", "eval_customer@test.com"),
        "password": os.environ.get("CUSTOMER_PASSWORD", "EvalCustomer123!"),
    },
}

FRONTEND_LOGIN = {
    "mode": "browser",
    "url": "{{base_url}}/app/login",
    "user_selector": "input[name='email']",
    "pass_selector": "input[name='password']",
    "submit_selector": "button[type='submit']",
    "user": TEST_USERS["admin"]["email"],
    "password": TEST_USERS["admin"]["password"],
    "wait_after": "networkidle",
    "timeout_ms": 30000,
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DAG_PATH = os.path.join(os.path.dirname(__file__), "dag.json")
SCORING_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scoring_config.json")

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
