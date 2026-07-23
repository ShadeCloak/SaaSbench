from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
EVAL_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

_DEFAULT_WORKSPACE = (EVAL_ROOT / ".." / ".." / "task_orghjavi" / "docker" / "workspace").resolve()
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", str(_DEFAULT_WORKSPACE))).resolve()

DAG_PATH = EVAL_ROOT / "dag.json"
SCORING_CONFIG_PATH = EVAL_ROOT / "scoring_config.json"
DAG_SMOKE_PATH = EVAL_ROOT / "dag_smoke.json"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8015")
API_BASE_URL = APP_BASE_URL.rstrip("/") + "/api"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("APP_DB_HOST_EXTERNAL", "localhost")
DB_PORT = int(os.environ.get("APP_DB_PORT_EXTERNAL", "5440"))
DB_NAME = os.environ.get("APP_DB_NAME", "app_orghjavi")
DB_USER = os.environ.get("APP_DB_USER", "apporghjavi")
DB_PASSWORD = os.environ.get("APP_DB_PASSWORD", "app123orghjavi")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
CH_HOST = os.environ.get("CH_HOST_EXTERNAL", "localhost")
CH_PORT = int(os.environ.get("CH_PORT_EXTERNAL", "8124"))
CH_DATABASE = os.environ.get("CH_DATABASE", "analytics_events_db")
CH_USER = os.environ.get("CH_USER", "default")
CH_PASSWORD = os.environ.get("CH_PASSWORD", "")
CH_BASE_URL = f"http://{CH_HOST}:{CH_PORT}"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
APP_CONTAINER = os.environ.get("APP_CONTAINER", "webanalytics_orghjavi_app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "webanalytics_orghjavi_postgres")
CH_CONTAINER = os.environ.get("CH_CONTAINER", "webanalytics_orghjavi_clickhouse")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
TEST_USERS = {
    "admin": {
        "email": os.environ.get("ADMIN_EMAIL", "bench-v2@example.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "BenchPass2026!@"),
        "name": "Eval Admin",
    },
    "viewer": {
        "email": os.environ.get("VIEWER_EMAIL", "bench-v2-viewer@example.com"),
        "password": os.environ.get("VIEWER_PASSWORD", "ViewerPass2026!@"),
        "name": "Eval Viewer",
    },
    "editor": {
        "email": os.environ.get("EDITOR_EMAIL", "bench-v2-editor@example.com"),
        "password": os.environ.get("EDITOR_PASSWORD", "EditorPass2026!@"),
        "name": "Eval Editor",
    },
    "billing": {
        "email": os.environ.get("BILLING_EMAIL", "bench-v2-billing@example.com"),
        "password": os.environ.get("BILLING_PASSWORD", "BillPass2026!@"),
        "name": "Eval Billing",
    },
    "guest": {
        "email": os.environ.get("GUEST_EMAIL", "bench-v2-guest@example.com"),
        "password": os.environ.get("GUEST_PASSWORD", "GuestPass2026!@"),
        "name": "Eval Guest",
    },
}

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
EVAL_API_KEY_FILE = "/tmp/eval_api_key"
EVAL_PLUGIN_TOKEN_FILE = "/tmp/eval_plugin_token"

# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.0"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "20"))
DB_CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))
CH_HTTP_TIMEOUT = int(os.environ.get("CH_HTTP_TIMEOUT", "30"))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
STRICT_PREREQ_PASSED_ONLY = os.environ.get("STRICT_PREREQ_PASSED_ONLY", "0") == "1"

SKIP_LLM_JUDGE_IF_NO_KEY = os.environ.get("SKIP_LLM_JUDGE_IF_NO_KEY", "1") == "1"
