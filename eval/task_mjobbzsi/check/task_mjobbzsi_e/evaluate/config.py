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
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8026")

APP_CONTAINER = os.environ.get("APP_CONTAINER", "task-app-1")
XMPP_CONTAINER = os.environ.get("XMPP_CONTAINER", "task-xmpp-1")
FOCUS_CONTAINER = os.environ.get("FOCUS_CONTAINER", "task-focus-1")
JVB_CONTAINER = os.environ.get("JVB_CONTAINER", "task-jvb-1")

XMPP_DOMAIN = os.environ.get("XMPP_DOMAIN", "meet.local")
XMPP_MUC_DOMAIN = os.environ.get("XMPP_MUC_DOMAIN", f"muc.{XMPP_DOMAIN}")
XMPP_WS_URL = os.environ.get("XMPP_WS_URL", f"ws://localhost:8026/xmpp-websocket")
XMPP_BOSH_URL = os.environ.get("XMPP_BOSH_URL", f"{APP_BASE_URL}/http-bind")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "REPLACE_WITH_YOUR_API_KEY")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.commonstack.ai/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DAG_PATH = os.path.join(os.path.dirname(__file__), "dag.json")
SCORING_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scoring_config.json")

HTTP_TIMEOUT = 15
WS_TIMEOUT = 10000
BROWSER_TIMEOUT = 15000

