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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8025")
API_BASE_URL = APP_BASE_URL + "/api"

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5448"))
DB_NAME = os.environ.get("DB_NAME", "app_ghmkznee")
DB_USER = os.environ.get("DB_USER", "appghmkznee")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123ghmkznee")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "app_ghmkznee_app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "app_ghmkznee_db")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

TEST_USERS = {
    "admin": {
        "login": os.environ.get("ADMIN_LOGIN", "admin"),
        "password": os.environ.get("ADMIN_PASSWORD", "admin"),
        "role": "Admin",
        "is_admin": True,
    },
    "viewer": {
        "login": os.environ.get("VIEWER_LOGIN", "testviewer"),
        "email": os.environ.get("VIEWER_EMAIL", "testviewer@test.com"),
        "password": os.environ.get("VIEWER_PASSWORD", "testpass123"),
        "role": "Viewer",
    },
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
HTTP_TIMEOUT = 15

FRONTEND_BASE_URL = APP_BASE_URL
FRONTEND_LOGIN = {
    "url": "{{base_url}}/login",
    "method": "POST",
    "json": {
        "user": os.environ.get("ADMIN_LOGIN", "admin"),
        "password": os.environ.get("ADMIN_PASSWORD", "admin"),
    },
    "headers": {"Content-Type": "application/json"},
}

