
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

APP_HOST = os.getenv("APP_HOST", "localhost")
APP_PORT = int(os.getenv("APP_PORT", "8019"))
APP_BASE_URL = f"http://{APP_HOST}:{APP_PORT}"
GRAPHQL_ENDPOINT = f"{APP_BASE_URL}/api/graphql"
HEALTH_ENDPOINT = f"{APP_BASE_URL}/health"

FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "9002"))
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", f"http://{APP_HOST}:{FRONTEND_PORT}")
FRONTEND_LOGIN = {
    "method": "POST",
    "url": f"{FRONTEND_BASE_URL}/logIn",
    "json": {
        "username": os.getenv("ADMIN_USERNAME", "datahub"),
        "password": os.getenv("ADMIN_PASSWORD", "datahub"),
    },
}

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3308"))
DB_NAME = os.getenv("DB_NAME", "app_ychlukjm")
DB_USER = os.getenv("DB_USER", "appychlukjm")
DB_PASSWORD = os.getenv("DB_PASSWORD", "app123ychlukjm")

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = int(os.getenv("ES_PORT", "9201"))
ES_BASE_URL = f"http://{ES_HOST}:{ES_PORT}"

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9093")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j_pass_ychlukjm")

APP_CONTAINER = os.getenv("APP_CONTAINER", "metadata-platform-app")
WORKSPACE_PATH = os.getenv("WORKSPACE_PATH", "/app")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
LOGIN_ENDPOINT = f"{APP_BASE_URL}/logIn"
ADMIN_ACTOR_URN = f"urn:li:corpuser:{ADMIN_USERNAME}"
SYSTEM_CLIENT_ID = os.getenv("SYSTEM_CLIENT_ID", "__system_service")
SYSTEM_CLIENT_SECRET = os.getenv("SYSTEM_CLIENT_SECRET", "SystemServiceSecret2026")

LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-5-20250929")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.commonstack.ai/v1")
SKIP_LLM_JUDGE = os.getenv("SKIP_LLM_JUDGE", "0") in ("1", "true", "True", "yes")

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))
DB_TIMEOUT = int(os.getenv("DB_TIMEOUT", "15"))
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DAG_PATH = os.path.join(os.path.dirname(__file__), "dag.json")
SCORING_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scoring_config.json")
