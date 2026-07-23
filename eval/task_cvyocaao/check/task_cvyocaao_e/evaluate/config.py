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

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8027")
ADMIN_API_URL = APP_BASE_URL + "/admin/realms"
TOKEN_URL_TEMPLATE = APP_BASE_URL + "/realms/{realm}/protocol/openid-connect/token"
WELL_KNOWN_TEMPLATE = APP_BASE_URL + "/realms/{realm}/.well-known/openid-configuration"

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5449"))
DB_NAME = os.environ.get("DB_NAME", "app_cvyocaao")
DB_USER = os.environ.get("DB_USER", "appcvyocaao")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123cvyocaao")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "app_cvyocaao")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "db_cvyocaao")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

TEST_REALM = os.environ.get("TEST_REALM", "eval-test-realm")

TEST_USERS = {
    "admin": {
        "realm": os.environ.get("ADMIN_REALM", "master"),
        "username": os.environ.get("ADMIN_USERNAME", "admin"),
        "password": os.environ.get("ADMIN_PASSWORD", "admin"),
        "client_id": os.environ.get("ADMIN_CLIENT_ID", "admin-cli"),
    },
}

TEST_CLIENT = {
    "clientId": "eval-test-client",
    "enabled": True,
    "publicClient": False,
    "directAccessGrantsEnabled": True,
    "serviceAccountsEnabled": True,
    "secret": "eval-secret",
    "protocol": "openid-connect",
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

REQUEST_TIMEOUT = 15
