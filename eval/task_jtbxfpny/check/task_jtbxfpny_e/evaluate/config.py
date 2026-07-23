import os

def _find_workspace():
    _eval_dir = os.path.dirname(os.path.abspath(__file__))
    for up in ["..", "../.."]:
        candidate = os.path.abspath(os.path.join(_eval_dir, up, "docker", "workspace"))
        if os.path.isdir(candidate):
            return candidate
    task_base = os.path.basename(os.path.dirname(_eval_dir)).replace("_e", "")
    candidate = os.path.join(os.path.dirname(os.path.dirname(_eval_dir)), task_base, "docker", "workspace")
    if os.path.isdir(candidate):
        return candidate
    return "/app"

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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8013")
API_BASE_URL = APP_BASE_URL + "/api/v1"
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5438"))
DB_NAME = os.environ.get("DB_NAME", "app_jtbxfpny")
DB_USER = os.environ.get("DB_USER", "appjtbxfpny")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "app123jtbxfpny")
APP_CONTAINER = os.environ.get("APP_CONTAINER", "app_jtbxfpny")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "postgres_jtbxfpny")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@test.com")
_GAMMA_USERNAME = os.environ.get("GAMMA_USERNAME", "gamma_eval")
_GAMMA_PASSWORD = os.environ.get("GAMMA_PASSWORD", "GammaPass123")
_GAMMA_EMAIL = os.environ.get("GAMMA_EMAIL", "gamma_eval@test.com")
_ALPHA_USERNAME = os.environ.get("ALPHA_USERNAME", "alpha_eval")
_ALPHA_PASSWORD = os.environ.get("ALPHA_PASSWORD", "AlphaPass123")
_ALPHA_EMAIL = os.environ.get("ALPHA_EMAIL", "alpha_eval@test.com")

TEST_USERS = {
    "admin": {
        "username": _ADMIN_USERNAME,
        "password": _ADMIN_PASSWORD,
        "email": _ADMIN_EMAIL,
        "firstname": "Admin",
        "lastname": "User",
        "role_aliases": ["Admin", "admin", "administrator", "site_admin", "superuser"],
        "cli_create_candidates": [
            f"app fab create-admin --username {_ADMIN_USERNAME} --firstname Admin --lastname User --email {_ADMIN_EMAIL} --password {_ADMIN_PASSWORD}",
            f"flask fab create-admin --username {_ADMIN_USERNAME} --firstname Admin --lastname User --email {_ADMIN_EMAIL} --password {_ADMIN_PASSWORD}",
            f"python manage.py createsuperuser --username {_ADMIN_USERNAME} --email {_ADMIN_EMAIL} --noinput",
        ],
    },
    "gamma": {
        "username": _GAMMA_USERNAME,
        "password": _GAMMA_PASSWORD,
        "email": _GAMMA_EMAIL,
        "role_aliases": ["Gamma", "gamma", "viewer", "regular_user", "member", "user", "reader"],
        "cli_create_candidates": [
            f"app fab create-user --username {_GAMMA_USERNAME} --firstname Gamma --lastname Eval --email {_GAMMA_EMAIL} --password {_GAMMA_PASSWORD} --role Gamma",
            f"flask fab create-user --username {_GAMMA_USERNAME} --firstname Gamma --lastname Eval --email {_GAMMA_EMAIL} --password {_GAMMA_PASSWORD} --role Gamma",
        ],
    },
    "alpha": {
        "username": _ALPHA_USERNAME,
        "password": _ALPHA_PASSWORD,
        "email": _ALPHA_EMAIL,
        "role_aliases": ["Alpha", "alpha", "editor", "contributor", "power_user", "author"],
        "cli_create_candidates": [
            f"app fab create-user --username {_ALPHA_USERNAME} --firstname Alpha --lastname Eval --email {_ALPHA_EMAIL} --password {_ALPHA_PASSWORD} --role Alpha",
            f"flask fab create-user --username {_ALPHA_USERNAME} --firstname Alpha --lastname Eval --email {_ALPHA_EMAIL} --password {_ALPHA_PASSWORD} --role Alpha",
        ],
    },
}


def get_role_for_user(user_key: str, available_roles: list) -> str:
    cfg = TEST_USERS.get(user_key, {})
    aliases = cfg.get("role_aliases") or []
    available_lower = {ar.lower(): ar for ar in (available_roles or [])}
    for alias in aliases:
        if alias.lower() in available_lower:
            return available_lower[alias.lower()]
    return aliases[0] if aliases else user_key

_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(_EVAL_DIR, "results")
DAG_PATH = os.path.join(_EVAL_DIR, "dag.json")

HTTP_TIMEOUT = 15

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")

FRONTEND_BASE_URL = APP_BASE_URL
FRONTEND_LOGIN = {
    "url": "{{base_url}}/login/",
    "method": "POST",
    "data": {"username": _ADMIN_USERNAME, "password": _ADMIN_PASSWORD},
    "csrf": {
        "url": "{{base_url}}/login/",
        "regex": r'name="csrf_token"[^>]*value="([^"]+)"',
        "field": "csrf_token",
    },
    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
}
