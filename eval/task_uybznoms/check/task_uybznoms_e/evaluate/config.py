import os
from pathlib import Path

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
if not os.path.isabs(WORKSPACE_DIR):
    WORKSPACE_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "task_uybznoms" / "docker" / "workspace")

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8006")
API_BASE_URL = APP_BASE_URL.rstrip("/") + "/api"

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5435"))
DB_NAME = os.environ.get("DB_NAME", "app_uybznoms")
DB_USER = os.environ.get("DB_USER", "appuybznoms")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123uybznoms")
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

APP_CONTAINER = os.environ.get("APP_CONTAINER", "app_uybznoms")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "db_uybznoms")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

TEST_USERS = {
    "admin": {
        "email": os.environ.get("ADMIN_EMAIL", "admin@example.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "admin123"),
    },
    "editor": {
        "email": os.environ.get("USER_EMAIL", "editor@test.com"),
        "password": os.environ.get("USER_PASSWORD", "Test1234!"),
    },
    "user": {
        "email": os.environ.get("USER_EMAIL", "editor@test.com"),
        "password": os.environ.get("USER_PASSWORD", "Test1234!"),
    },
    "restricted_user": {
        "email": os.environ.get("RESTRICTED_EMAIL", "restricted@test.com"),
        "password": os.environ.get("RESTRICTED_PASSWORD", "Test1234!"),
    },
}

RESULTS_DIR = os.environ.get("RESULTS_DIR", str(Path(__file__).resolve().parent / "results"))
os.makedirs(RESULTS_DIR, exist_ok=True)

HTTP_TIMEOUT = 30

