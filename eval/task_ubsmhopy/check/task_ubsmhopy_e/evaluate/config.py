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

BASE_URL = os.getenv("EVAL_BASE_URL", "http://localhost:8035")
API_URL = f"{BASE_URL}/api"
IDENTITY_URL = f"{BASE_URL}/identity"
ADMIN_URL = f"{BASE_URL}/admin"

DB_HOST = os.getenv("EVAL_DB_HOST", "localhost")
DB_PORT = int(os.getenv("EVAL_DB_PORT", "5456"))
DB_NAME = os.getenv("EVAL_DB_NAME", "app_ubsmhopy")
DB_USER = os.getenv("EVAL_DB_USER", "appubsmhopy")
DB_PASS = os.getenv("EVAL_DB_PASS", "app123ubsmhopy")

CONTAINER_NAME = os.getenv("EVAL_CONTAINER", "app_ubsmhopy")
WORKSPACE_PATH = os.getenv("EVAL_WORKSPACE", "/app")

ADMIN_TOKEN = os.getenv("EVAL_ADMIN_TOKEN", "admin_token_ubsmhopy")

import base64, hashlib

def _make_master_hash(password: str, email: str, iterations: int = 600000) -> str:
    derived = hashlib.pbkdf2_hmac('sha256', password.encode(), email.encode(), iterations)
    master = hashlib.pbkdf2_hmac('sha256', derived, password.encode(), 1)
    return base64.b64encode(master).decode()

_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "eval_admin@test.com")
_USER_EMAIL = os.environ.get("USER_EMAIL", "eval_user@test.com")
_USERB_EMAIL = os.environ.get("USERB_EMAIL", "eval_user_b@test.com")
_EVAL_PASSWORD = os.environ.get("EVAL_PASSWORD", "EvalMasterPassword123!")

TEST_USERS = {
    "admin": {
        "email": _ADMIN_EMAIL,
        "name": "Eval Admin",
        "password_hash": _make_master_hash(_EVAL_PASSWORD, _ADMIN_EMAIL),
        "key": "2.eval_admin_encrypted_key_placeholder",
    },
    "user": {
        "email": _USER_EMAIL,
        "name": "Eval User",
        "password_hash": _make_master_hash(_EVAL_PASSWORD, _USER_EMAIL),
        "key": "2.eval_user_encrypted_key_placeholder",
    },
    "user_b": {
        "email": _USERB_EMAIL,
        "name": "Eval User B",
        "password_hash": _make_master_hash(_EVAL_PASSWORD, _USERB_EMAIL),
        "key": "2.eval_userb_encrypted_key_placeholder",
    },
}

REQUEST_TIMEOUT = int(os.getenv("EVAL_TIMEOUT", "30"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.getenv("LLM_API_BASE", "")

SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")
