#!/usr/bin/env python3

import argparse
import atexit
import json
import os
import re
import signal
import subprocess
import sys
import shutil
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_ACTIVE_DOCKER_DIRS: set[str] = set()
_CLEANUP_LOCK = threading.Lock()


_LLM_METHOD_VALUES = {"llm-judge", "llm_judge"}


def _dag_has_llm_nodes(check_dir: str, task_id: str) -> bool:
    dag_path = os.path.join(check_dir, f"{task_id}_e", "evaluate", "dag.json")
    try:
        with open(dag_path, encoding="utf-8") as f:
            dag = json.load(f)
    except Exception:
        return False
    for n in dag.get("nodes") or []:
        sc = n.get("scoring") or {}
        sc_m = sc.get("method") if isinstance(sc, dict) else None
        if sc_m in _LLM_METHOD_VALUES or n.get("method") in _LLM_METHOD_VALUES:
            return True
    return False


def _emergency_docker_cleanup(reason: str = "atexit") -> None:
    with _CLEANUP_LOCK:
        dirs = list(_ACTIVE_DOCKER_DIRS)
        _ACTIVE_DOCKER_DIRS.clear()
    if not dirs:
        return
    print(f"\n[emergency-cleanup:{reason}] downing {len(dirs)} docker stack(s)...",
          file=sys.stderr, flush=True)
    for d in dirs:
        try:
            subprocess.run(
                ["docker", "compose", "down", "-v", "--remove-orphans"],
                cwd=d, timeout=60,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f"  cleaned: {d}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"  failed:  {d}: {e}", file=sys.stderr, flush=True)


def _signal_handler(signum, frame):
    _emergency_docker_cleanup(reason=f"signal-{signum}")
    sys.exit(128 + signum)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
atexit.register(_emergency_docker_cleanup)

import yaml


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _expand_compose_env(value: str) -> str:
    return re.sub(r"\$\{[^:}]+:-([^}]+)\}", r"\1", value)


def _extract_host_port(entry) -> int | None:
    if isinstance(entry, dict):
        p = entry.get("published") or entry.get("target")
        try:
            return int(p) if p is not None else None
        except (ValueError, TypeError):
            return None
    s = _expand_compose_env(str(entry).strip().strip('"').strip("'"))
    s = s.split("/")[0]
    parts = s.split(":")
    if len(parts) == 1:
        host_str = parts[0]
    elif len(parts) == 2:
        host_str = parts[0]
    else:
        host_str = parts[1]
    host_str = host_str.split("-")[0]
    try:
        return int(host_str)
    except ValueError:
        return None


def _parse_compose_host_ports(compose_path: str) -> list[int]:
    try:
        with open(compose_path, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []
    ports: set[int] = set()
    for svc in (data.get("services") or {}).values():
        for entry in (svc.get("ports") or []):
            hp = _extract_host_port(entry)
            if hp:
                ports.add(hp)
    return sorted(ports)


def _preflight_port_conflict(task_id: str, docker_dir: str) -> None:
    compose = os.path.join(docker_dir, "docker-compose.yml")
    if not os.path.exists(compose):
        return
    ports = _parse_compose_host_ports(compose)
    if not ports:
        return

    own_prefix = f"{task_id}-" if task_id.startswith("task_") else f"task_{task_id}-"

    occupiers: dict[str, list[int]] = {}
    for port in ports:
        try:
            r = subprocess.run(
                ["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=15,
            )
        except Exception:
            continue
        for name in r.stdout.strip().splitlines():
            name = name.strip()
            if not name or name.startswith(own_prefix):
                continue
            if not name.startswith("task_"):
                log.warning(f"[{task_id}] preflight: port {port} is held by non-task_* container {name}, skipping (prepare may fail)")
                continue
            occupiers.setdefault(name, []).append(port)

    if not occupiers:
        return

    log.warning(f"[{task_id}] preflight: found {len(occupiers)} sibling task container(s) holding this task's ports, cleaning up")
    for name, ps in occupiers.items():
        log.warning(f"[{task_id}]   rm -f {name} (holds {ps})")
        try:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True, text=True, timeout=30,
            )
        except Exception as e:
            log.warning(f"[{task_id}]   rm {name} failed: {e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def discover_tasks(tasks_dir: str) -> list[str]:
    return sorted(
        d for d in os.listdir(tasks_dir)
        if d.startswith("task_") and os.path.isdir(os.path.join(tasks_dir, d))
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def _stream_subprocess(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict | None = None,
    timeout: int | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
) -> dict:
    start = time.time()
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []

    out_f = open(stdout_path, "wb") if stdout_path else None
    err_f = open(stderr_path, "wb") if stderr_path else None

    def _pump(stream, chunks, sink):
        try:
            for line in iter(stream.readline, b""):
                chunks.append(line)
                if sink is not None:
                    try:
                        sink.write(line)
                        sink.flush()
                    except Exception:
                        pass
        except Exception:
            pass

    t1 = threading.Thread(target=_pump, args=(proc.stdout, out_chunks, out_f), daemon=True)
    t2 = threading.Thread(target=_pump, args=(proc.stderr, err_chunks, err_f), daemon=True)
    t1.start()
    t2.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=15)
        except Exception:
            pass

    t1.join(timeout=10)
    t2.join(timeout=10)

    if out_f:
        try:
            out_f.close()
        except Exception:
            pass
    if err_f:
        try:
            err_f.close()
        except Exception:
            pass

    elapsed = time.time() - start
    stdout = b"".join(out_chunks).decode("utf-8", errors="replace")
    stderr = b"".join(err_chunks).decode("utf-8", errors="replace")

    return {
        "returncode": proc.returncode if proc.returncode is not None else -1,
        "stdout": stdout,
        "stderr": stderr,
        "elapsed_seconds": elapsed,
        "timed_out": timed_out,
    }


# ---------------------------------------------------------------------------
# In-container (docker exec) support — mirrors run_benchmark_claude.py so codex
# runs INSIDE the app container (like Claude Code). A portable, statically-linked
# codex binary is bind-mounted into the container via
# tasks/_overlays/docker-compose.codex.yml. This is the only supported execution
# mode; there is no host-side sandbox fallback.
# ---------------------------------------------------------------------------
DOCKER_BIN = shutil.which("docker") or "docker"


def _docker_cmd(*args: str) -> list[str]:
    return [DOCKER_BIN, *args]


def _with_docker_env(env: dict | None = None) -> dict:
    merged = dict(env or os.environ.copy())
    merged["DOCKER_BIN"] = DOCKER_BIN
    docker_dir = os.path.dirname(DOCKER_BIN) if os.path.sep in DOCKER_BIN else ""
    if docker_dir:
        path_parts = [p for p in merged.get("PATH", "").split(os.pathsep) if p]
        if docker_dir not in path_parts:
            merged["PATH"] = os.pathsep.join([docker_dir, *path_parts])
    return merged


_DEFAULT_CODEX_RUNTIME_DIR = os.path.expanduser("~/.saasbench/codex-runtime")
_CODEX_OVERLAY_REL = os.path.join("tasks", "_overlays", "docker-compose.codex.yml")

_NON_AGENT_SERVICE_NAMES = frozenset({
    "db", "redis", "postgres", "postgresql", "mysql", "mariadb",
    "mongo", "mongodb", "rabbitmq", "kafka", "zookeeper",
    "elasticsearch", "memcached", "minio", "neo4j", "clickhouse",
    "schema-registry", "mock-receiver", "worker", "queue",
    "scheduler", "cache", "broker", "celery", "ollama",
    "milvus", "qdrant", "weaviate", "vault", "consul",
})


def _resolve_codex_runtime_dir() -> str:
    return os.path.abspath(
        os.environ.get("SAASBENCH_CODEX_RUNTIME_DIR") or _DEFAULT_CODEX_RUNTIME_DIR
    )


def _check_codex_runtime_ready(runtime_dir: str) -> tuple[bool, str]:
    if not os.path.isdir(runtime_dir):
        return False, f"Directory does not exist: {runtime_dir}"
    codex_bin = os.path.join(runtime_dir, "bin", "codex")
    if not os.path.isfile(codex_bin):
        return False, f"{codex_bin} not found (runtime bundle incomplete)"
    if not os.access(codex_bin, os.X_OK):
        return False, f"{codex_bin} is not executable"
    return True, ""


def _pick_agent_entry_service(services: dict) -> str:
    if not isinstance(services, dict) or not services:
        return "app"
    if "app" in services:
        return "app"
    if "web" in services:
        return "web"
    for name in sorted(services.keys()):
        if name in _NON_AGENT_SERVICE_NAMES:
            continue
        return name
    return "app"


def _extract_compose_container_name(docker_dir: str, task_id: str) -> str:
    compose = os.path.join(docker_dir, "docker-compose.yml")
    short = task_id.removeprefix("task_")
    fallback = f"app_{short}"
    try:
        with open(compose, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return fallback
    services = data.get("services") or {}
    entry_svc = _pick_agent_entry_service(services)
    if entry_svc != "app":
        fallback = f"{entry_svc}_{short}"
    app_svc = services.get(entry_svc) or {}
    name = app_svc.get("container_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return fallback


def _resolve_actual_app_container_name(docker_dir: str, task_id: str, declared: str) -> str:
    docker_dir = os.path.abspath(docker_dir)
    entry_svc = "app"
    try:
        with open(os.path.join(docker_dir, "docker-compose.yml"), "r") as f:
            data = yaml.safe_load(f) or {}
        entry_svc = _pick_agent_entry_service(data.get("services") or {})
    except Exception:
        pass
    if declared:
        try:
            r = subprocess.run(
                _docker_cmd("inspect", "--format", "{{.Name}}", declared),
                capture_output=True, text=True, timeout=10, env=_with_docker_env(),
            )
            if r.returncode == 0 and r.stdout.strip():
                return declared
        except Exception:
            pass
    try:
        r = subprocess.run(
            _docker_cmd(
                "ps", "--format", "{{.Names}}",
                "--filter", f"label=com.docker.compose.project.working_dir={docker_dir}",
                "--filter", f"label=com.docker.compose.service={entry_svc}",
            ),
            capture_output=True, text=True, timeout=10, env=_with_docker_env(),
        )
        if r.returncode == 0:
            names = [n for n in r.stdout.strip().splitlines() if n.strip()]
            if names:
                return names[0]
    except Exception:
        pass
    return ""


def _get_codex_overlay_abspath() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _CODEX_OVERLAY_REL)


def _get_codex_overlay_for_service(entry_svc: str) -> str:
    base = _get_codex_overlay_abspath()
    if entry_svc == "app":
        return base
    out_dir = "/tmp/saasbench_overlays"
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    out_path = os.path.join(out_dir, f"docker-compose.codex.{entry_svc}.yml")
    try:
        with open(base, "r") as f:
            content = f.read()
        patched = content.replace("services:\n  app:\n", f"services:\n  {entry_svc}:\n")
        if patched == content:
            patched = content.replace("\n  app:\n", f"\n  {entry_svc}:\n", 1)
        with open(out_path, "w") as f:
            f.write(patched)
        return out_path
    except Exception:
        return base


def _compose_files_for_in_container(docker_dir: str) -> str:
    base = os.path.abspath(os.path.join(docker_dir, "docker-compose.yml"))
    entry_svc = "app"
    try:
        with open(base, "r") as f:
            data = yaml.safe_load(f) or {}
        entry_svc = _pick_agent_entry_service(data.get("services") or {})
    except Exception:
        pass
    overlay = _get_codex_overlay_for_service(entry_svc)
    parts = [base, overlay]
    extra = os.environ.get("SAASBENCH_EXTRA_COMPOSE_OVERLAYS", "").strip()
    if extra:
        for p in extra.split(os.pathsep):
            p = p.strip()
            if p:
                parts.append(os.path.abspath(p))
    return os.pathsep.join(parts)


def _in_container_prepare_env(docker_dir: str) -> dict:
    return {
        "COMPOSE_FILE": _compose_files_for_in_container(docker_dir),
        "SAASBENCH_CODEX_RUNTIME_DIR": _resolve_codex_runtime_dir(),
    }


def _detect_score_leak(task_id: str, results_dir: str, check_dir: str) -> dict:
    events_file = os.path.join(results_dir, "codex_events.jsonl")
    out = {"eval_hits": 0, "check_hits": 0, "samples": [],
           "events_file": events_file, "scanned": False}
    if not os.path.exists(events_file):
        return out

    eval_substr = f"/check/{task_id}_e/evaluate"
    check_substr = f"/check/{task_id}/"
    samples: list[dict] = []
    eval_hits = check_hits = 0
    try:
        with open(events_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if eval_substr in line:
                    eval_hits += 1
                    if len(samples) < 5:
                        samples.append({"kind": "eval", "snippet": line[:400].rstrip()})
                elif check_substr in line:
                    check_hits += 1
                    if len(samples) < 5:
                        samples.append({"kind": "check", "snippet": line[:400].rstrip()})
    except Exception as e:
        log.warning(f"[{task_id}] leak detection failed to read events: {e}")
        return out

    out.update({"eval_hits": eval_hits, "check_hits": check_hits,
                "samples": samples, "scanned": True})
    return out


def _codex_events_to_trajectory(events_file: str, out_path: str) -> int:
    if not os.path.exists(events_file):
        return 0
    seen_ids: set[str] = set()
    actions: list[dict] = []
    try:
        with open(events_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") not in ("item.started", "item.completed"):
                    continue
                item = obj.get("item") or {}
                if item.get("type") != "command_execution":
                    continue
                iid = str(item.get("id") or "")
                if iid and iid in seen_ids:
                    continue
                if iid:
                    seen_ids.add(iid)
                cmd = item.get("command") or ""
                if not cmd:
                    continue
                actions.append({
                    "id": iid or None,
                    "source": "agent",
                    "action": "run",
                    "args": {"command": cmd},
                    "timestamp": obj.get("timestamp"),
                })
    except OSError as e:
        log.warning(f"_codex_events_to_trajectory: read {events_file} failed: {e}")
        return 0

    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(actions, f, indent=2, ensure_ascii=False)
    except OSError as e:
        log.warning(f"_codex_events_to_trajectory: write {out_path} failed: {e}")
        return 0
    return len(actions)


def _to_float(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _pick_max(d: dict) -> float:
    for k in ("total_max", "total_maxScore", "total_max_score", "maxScore", "max_score"):
        v = d.get(k)
        if v:
            return _to_float(v)
    return 0.0


def _pick_pct(d: dict) -> float:
    for k in ("percentage", "normalized_score", "pct", "percent"):
        v = d.get(k)
        if v is not None:
            return _to_float(v)
    return 0.0


def _sum_categories_max(r: dict) -> float:
    cats = r.get("by_category") or r.get("categories") or {}
    if isinstance(cats, dict):
        return sum((_to_float(c.get("maxScore") or c.get("max_score") or c.get("max") or 0))
                   for c in cats.values() if isinstance(c, dict))
    if isinstance(cats, list):
        return sum((_to_float(c.get("maxScore") or c.get("max_score") or c.get("max") or 0))
                   for c in cats if isinstance(c, dict))
    return 0.0


def _node_max(node: dict) -> float:
    for k in ("maxScore", "max_score", "max"):
        v = node.get(k)
        if v is not None:
            return _to_float(v)
    return 0.0


def _overall_from_report(r) -> dict | None:
    if isinstance(r, list):
        if not r or not isinstance(r[0], dict):
            return None
        s = sum(_to_float(n.get("score")) for n in r if isinstance(n, dict))
        m = sum(_node_max(n) for n in r if isinstance(n, dict))
        return {"score": s, "max": m, "percentage": (100.0 * s / m) if m else 0.0}

    if not isinstance(r, dict) or not r:
        return None

    if isinstance(r.get("overall"), dict):
        o = r["overall"]
        return {
            "score": _to_float(o.get("score")),
            "max": _to_float(o.get("maxScore") or o.get("max_score")),
            "percentage": _to_float(o.get("pct")),
        }

    if "total_score" in r:
        mx = _pick_max(r) or _sum_categories_max(r)
        return {
            "score": _to_float(r.get("total_score")),
            "max": mx,
            "percentage": _pick_pct(r),
        }

    if isinstance(r.get("summary"), dict) and "total_score" in r["summary"]:
        s = r["summary"]
        mx = _pick_max(s) or _sum_categories_max(r)
        return {
            "score": _to_float(s.get("total_score")),
            "max": mx,
            "percentage": _pick_pct(s),
        }

    if all(
        isinstance(v, dict) and "score" in v
        and ("maxScore" in v or "max_score" in v or "max" in v)
        for v in r.values()
    ):
        s = sum(_to_float(v.get("score") or 0) for v in r.values())
        m = sum(_node_max(v) for v in r.values())
        return {
            "score": s,
            "max": m,
            "percentage": (100.0 * s / m) if m else 0.0,
        }

    if all(
        isinstance(v, dict)
        and "score" in v
        and ("max" in v or "max_score" in v or "maxScore" in v)
        and "status" not in v
        for v in r.values()
    ):
        s = sum(_to_float(v.get("score") or 0) for v in r.values())
        m = sum(_to_float(v.get("max") or v.get("max_score") or v.get("maxScore") or 0)
                for v in r.values())
        return {
            "score": s,
            "max": m,
            "percentage": (100.0 * s / m) if m else 0.0,
        }

    return None


def _extract_score_from_reports(eval_reports_dir: str) -> dict | None:
    if not os.path.isdir(eval_reports_dir):
        return None

    candidates: list[tuple[int, str]] = []
    for name in sorted(os.listdir(eval_reports_dir)):
        if not name.endswith(".json"):
            continue
        lname = name.lower()
        if "node_result" in lname:
            priority = -1
        elif "llm" in lname and "report" in lname:
            priority = 3
        elif "llm" in lname:
            priority = 2
        elif "report" in lname or "model_test" in lname:
            priority = 1
        else:
            priority = 0
        candidates.append((priority, name))
    candidates.sort(key=lambda x: -x[0])

    for _, name in candidates:
        fpath = os.path.join(eval_reports_dir, name)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        scored = _overall_from_report(data)
        if scored is not None and (scored.get("max") or 0) > 0:
            scored["source"] = name
            if not scored.get("percentage") and scored["max"] > 0:
                scored["percentage"] = round(100.0 * scored["score"] / scored["max"], 2)
            return scored
    return None


def build_prompt(task_id: str, check_dir: str, tasks_dir: str, workspace_path: str = "") -> str:
    prompt_path = os.path.join(check_dir, task_id, "prompt_for_model.md")
    task_md_path = os.path.join(tasks_dir, task_id, "task", "task.md")
    kb_path = os.path.join(tasks_dir, task_id, "kb", "knowledge_base.json")

    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"prompt_for_model.md not found: {prompt_path}")
    if not os.path.exists(task_md_path):
        raise FileNotFoundError(f"task.md not found: {task_md_path}")

    has_kb = os.path.exists(kb_path)

    if workspace_path:
        os.makedirs(workspace_path, exist_ok=True)
        shutil.copy2(task_md_path, os.path.join(workspace_path, "task.md"))
        if has_kb:
            shutil.copy2(kb_path, os.path.join(workspace_path, "knowledge_base.json"))

    with open(prompt_path, "r") as f:
        prompt_content = f.read()

    start_marker = "## Prompt"
    end_marker = "## Tester Workflow"

    start_idx = prompt_content.find(start_marker)
    end_idx = prompt_content.find(end_marker)

    if start_idx != -1 and end_idx != -1:
        prompt_body = prompt_content[start_idx + len(start_marker):end_idx].strip()
    elif start_idx != -1:
        prompt_body = prompt_content[start_idx + len(start_marker):].strip()
    else:
        prompt_body = prompt_content

    docs_section = (
        "The complete product requirements document has been placed in the working "
        "directory at `/app/task.md`. Read it carefully and implement everything it "
        "describes."
    )
    if has_kb:
        docs_section += (
            "\n\nIn addition, the working directory contains a supplementary knowledge "
            "base at `/app/knowledge_base.json` that clarifies ambiguous points in the "
            "PRD. Each entry has the shape `{id, question, answer, source_reference, "
            "confidence}`. Consult it as a reference when task.md is unclear on details "
            "such as field semantics, state transitions, serialization, filtering, or "
            "permissions. You can read it on demand with `jq`, `cat`, or `grep` (e.g. "
            "`jq '.clarifications[] | {id, question, answer}' /app/knowledge_base.json`); "
            "you do not have to read the whole file at once."
        )

    full_prompt = prompt_body + "\n\n### Requirements Document\n\n" + docs_section + \
        "\n\n### Important Reminder\n\n" + \
        "**After you finish writing all code, you MUST start the application server.** " + \
        "The evaluation script will immediately verify the application's behavior over HTTP " + \
        "as soon as you are done. If the server is not listening on the designated port, " + \
        "every test will fail. Make sure you:\n" + \
        "1. Install all dependencies\n" + \
        "2. Run the database migrations\n" + \
        "3. Create the test users required for evaluation (see the instructions above)\n" + \
        "4. **Start the application server and keep it running on the designated port**\n"

    return full_prompt


def run_prepare_workspace(task_id: str, check_dir: str, extra_env: dict | None = None) -> bool:
    script = os.path.join(check_dir, task_id, "prepare_workspace.sh")
    if not os.path.exists(script):
        log.warning(f"[{task_id}] prepare_workspace.sh not found, skipping")
        return True

    log.info(f"[{task_id}] running prepare_workspace.sh...")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            ["bash", script],
            capture_output=True, text=True, timeout=1800, env=env,
        )
        if result.returncode != 0:
            log.error(f"[{task_id}] prepare_workspace.sh failed: {result.stderr[-300:]}")
            return False
        log.info(f"[{task_id}] environment ready")
        return True
    except subprocess.TimeoutExpired:
        log.error(f"[{task_id}] prepare_workspace.sh timed out (1800s)")
        return False


def _looks_like_transient_codex_failure(events: list[dict]) -> bool:
    for e in events:
        if not isinstance(e, dict):
            continue
        msg = ""
        if e.get("type") == "turn.failed":
            err = e.get("error")
            if isinstance(err, dict):
                msg = err.get("message", "") or ""
            elif isinstance(e.get("message"), str):
                msg = e["message"]
        elif e.get("type") == "error" and isinstance(e.get("message"), str):
            msg = e["message"]
        if not msg:
            continue
        m = msg.lower()
        if (
            "high demand" in m
            or "rate limit" in m
            or "reconnecting" in m
            or "stream disconnected" in m
            or "websocket closed" in m
        ):
            return True
    return False


def run_codex(
    task_id: str,
    prompt: str,
    workspace_path: str,
    model: str = "gpt-5.4",
    timeout: int = 10800,
    results_dir: str = "",
    api_key: str = "",
    base_url: str = "",
    max_retries: int = 1,
    check_dir: str = "",
    container_name: str = "",
    workdir: str = "/app",
) -> dict:
    _prov_id = os.environ.get("CODEX_PROVIDER_ID", "")
    _prov_base = os.environ.get("CODEX_PROVIDER_BASE_URL", "")
    _provider_flags = []
    if _prov_id and _prov_base:
        _prov_name = os.environ.get("CODEX_PROVIDER_NAME", _prov_id)
        _prov_wire = os.environ.get("CODEX_PROVIDER_WIRE_API", "responses")
        _prov_envkey = os.environ.get("CODEX_PROVIDER_ENV_KEY", "LB_API_KEY")
        _provider_flags = [
            "-c", f'model_provider="{_prov_id}"',
            "-c", f'model_providers.{_prov_id}.name="{_prov_name}"',
            "-c", f'model_providers.{_prov_id}.base_url="{_prov_base}"',
            "-c", f'model_providers.{_prov_id}.wire_api="{_prov_wire}"',
            "-c", f'model_providers.{_prov_id}.env_key="{_prov_envkey}"',
        ]
    inner_cmd = [
        "codex", "exec",
        "--model", model,
        "--json",
        *_provider_flags,
        "--sandbox", "danger-full-access",
        "--skip-git-repo-check",
        "--", prompt,
    ]
    # --- Secrets shared by both execution modes -------------------------------
    _exec_secrets: dict[str, str] = {}
    if api_key:
        _exec_secrets["OPENAI_API_KEY"] = api_key
    if base_url:
        _exec_secrets["OPENAI_BASE_URL"] = base_url
    if _prov_id and _prov_base:
        _envkey = os.environ.get("CODEX_PROVIDER_ENV_KEY", "LB_API_KEY")
        _keyval = os.environ.get(_envkey) or api_key
        if _keyval:
            _exec_secrets[_envkey] = _keyval

    # ---- in-container: run codex INSIDE the app container via docker exec ----
    # The evaluator is never mounted into the container, so the agent cannot
    # read the scoring code — container isolation provides the sandbox.
    if not container_name:
        log.error(f"[{task_id}] container_name is empty; cannot run codex in-container")
        return {
            "returncode": -1, "turn_completed": False, "events_count": 0,
            "elapsed_seconds": 0.0, "token_usage": {}, "error": "no_container",
        }
    exec_env = dict(_exec_secrets)
    exec_env.setdefault("CODEX_HOME", "/tmp/.codex")  # writable state dir inside container
    exec_args = ["-i", "-w", workdir]
    for _k, _v in exec_env.items():
        exec_args.extend(["-e", f"{_k}={_v}"])
    cmd = _docker_cmd("exec", *exec_args, container_name, *inner_cmd)
    run_env = _with_docker_env()
    run_cwd = None
    log.info(f"[{task_id}] codex runs IN-CONTAINER: docker exec -w {workdir} {container_name} ...")

    events_file = os.path.join(results_dir, "codex_events.jsonl") if results_dir else "/tmp/codex_events.jsonl"
    stderr_file = os.path.join(results_dir, "codex_stderr.log") if results_dir else "/tmp/codex_stderr.log"

    attempts: list[dict] = []
    last_proc: dict = {}
    last_events: list[dict] = []
    last_token_usage: dict = {}

    for attempt in range(max_retries + 1):
        if attempt > 0:
            for path in (events_file, stderr_file):
                if os.path.exists(path):
                    archived = f"{path}.attempt{attempt}"
                    try:
                        os.replace(path, archived)
                    except OSError as e:
                        log.warning(f"[{task_id}] archiving {path} -> {archived} failed: {e}")
            log.warning(
                f"[{task_id}] Codex retry {attempt}/{max_retries}"
                f" (previous attempt failed due to high-demand / Reconnecting; sleeping 60s before retrying)"
            )
            time.sleep(60)

        log.info(
            f"[{task_id}] launching Codex (model={model}, timeout={timeout}s, "
            f"attempt={attempt + 1}/{max_retries + 1}, "
            f"isolation=in-container）..."
        )
        proc_res = _stream_subprocess(
            cmd,
            cwd=run_cwd,
            env=run_env,
            timeout=timeout,
            stdout_path=events_file,
            stderr_path=stderr_file,
        )
        last_proc = proc_res

        events: list[dict] = []
        token_usage: dict = {}
        for line in proc_res["stdout"].splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(obj)
            if obj.get("type") == "turn.completed" and isinstance(obj.get("usage"), dict):
                token_usage = obj["usage"]
        last_events = events
        last_token_usage = token_usage

        completed = any(e.get("type") == "turn.completed" for e in events)
        attempts.append({
            "attempt": attempt + 1,
            "elapsed_seconds": round(proc_res["elapsed_seconds"], 1),
            "returncode": proc_res["returncode"],
            "events_count": len(events),
            "turn_completed": completed,
            "timed_out": proc_res["timed_out"],
        })

        if completed:
            break
        if proc_res["timed_out"]:
            break
        if attempt >= max_retries:
            break
        if not _looks_like_transient_codex_failure(events):
            break

    total_elapsed = round(sum(a["elapsed_seconds"] for a in attempts), 1)
    completed_final = any(e.get("type") == "turn.completed" for e in last_events)
    result = {
        "success": last_proc.get("returncode") == 0 and completed_final,
        "elapsed_seconds": total_elapsed,
        "returncode": last_proc.get("returncode", -1),
        "events_count": len(last_events),
        "turn_completed": completed_final,
        "token_usage": last_token_usage,
        "stdout_tail": last_proc.get("stdout", "")[-4000:],
        "stderr_tail": last_proc.get("stderr", "")[-4000:],
    }
    if last_proc.get("timed_out"):
        result["error"] = "timeout"
        result["success"] = False
    if len(attempts) > 1:
        result["attempts"] = attempts
    return result


def run_evaluation(
    task_id: str,
    check_dir: str,
    *,
    timeout: int = 5400,
    results_dir: str = "",
) -> dict:
    script = os.path.join(check_dir, task_id, "test_model_output.sh")
    if not os.path.exists(script):
        log.error(f"[{task_id}] test_model_output.sh not found")
        return {"success": False, "error": "script_not_found"}

    stdout_log = os.path.join(results_dir, "eval.stdout.log") if results_dir else None
    stderr_log = os.path.join(results_dir, "eval.stderr.log") if results_dir else None

    log.info(f"[{task_id}] running test_model_output.sh (timeout={timeout}s)...")
    proc_res = _stream_subprocess(
        ["bash", script],
        cwd=os.path.join(check_dir, task_id),
        timeout=timeout,
        stdout_path=stdout_log,
        stderr_path=stderr_log,
    )

    if proc_res["timed_out"]:
        log.warning(
            f"[{task_id}] test_model_output.sh timed out ({timeout}s), "
            f"killed; intermediate output at {stdout_log or '(memory only)'}"
        )
        return {
            "success": False,
            "error": "timeout",
            "returncode": -1,
            "elapsed_seconds": round(proc_res["elapsed_seconds"], 1),
            "stdout_tail": proc_res["stdout"][-8000:],
            "stderr_tail": proc_res["stderr"][-4000:],
        }

    return {
        "success": proc_res["returncode"] == 0,
        "returncode": proc_res["returncode"],
        "elapsed_seconds": round(proc_res["elapsed_seconds"], 1),
        "stdout_tail": proc_res["stdout"][-8000:],
        "stderr_tail": proc_res["stderr"][-4000:],
    }


def run_single(
    task_id: str,
    model: str,
    config: dict,
    api_key: str = "",
    base_url: str = "",
    dry_run: bool = False,
) -> dict:
    paths = config["paths"]
    codex_config = config.get("codex", {})

    model_slug = model.replace("/", "_").replace(" ", "_")
    run_id = f"{task_id}__{model_slug}__{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    results_dir = os.path.join(paths["results_dir"], run_id)
    os.makedirs(results_dir, exist_ok=True)

    log.info(f"[{task_id}] === start === model: {model}  results: {results_dir}")

    if dry_run:
        log.info(f"[{task_id}] [DRY RUN] skipped")
        return {"task": task_id, "model": model, "dry_run": True}

    result = {
        "task": task_id,
        "model": model,
        "agent": "codex",
        "run_id": run_id,
        "started_at": datetime.now().isoformat(),
    }

    docker_dir_for_cleanup = os.path.join(paths["tasks_dir"], task_id, "docker")
    _ACTIVE_DOCKER_DIRS.add(docker_dir_for_cleanup)

    container_name = _extract_compose_container_name(docker_dir_for_cleanup, task_id)
    prepare_extra_env = _in_container_prepare_env(docker_dir_for_cleanup)
    result["aci"] = {
        "mode": "agent_in_container",
        "container_name": container_name,
        "compose_file_env": prepare_extra_env["COMPOSE_FILE"],
        "runtime_dir": prepare_extra_env["SAASBENCH_CODEX_RUNTIME_DIR"],
    }

    try:
        # Step 0: preflight port conflict cleanup (serial mode only)
        if config.get("_concurrency", 1) <= 1:
            _preflight_port_conflict(task_id, docker_dir_for_cleanup)

        # Step 1: prepare the environment
        log.info(f"[{task_id}] Step 1: prepare environment")
        prepare_ok = run_prepare_workspace(task_id, paths["check_dir"], extra_env=prepare_extra_env)
        if prepare_ok:
            actual_name = _resolve_actual_app_container_name(
                docker_dir_for_cleanup, task_id, container_name
            )
            if actual_name and actual_name != container_name:
                log.info(
                    f"[{task_id}] container name corrected: declared={container_name!r} "
                    f"→ actual={actual_name!r}"
                )
                container_name = actual_name
                result["aci"]["container_name"] = container_name
            elif not actual_name:
                log.warning(
                    f"[{task_id}] could not resolve the running app container, "
                    f"falling back to declared={container_name!r} (docker exec may fail)"
                )
        if not prepare_ok:
            log.error(f"[{task_id}] prepare_workspace failed, skipping this task")
            result["finished_at"] = datetime.now().isoformat()
            result["status"] = "PREPARE_FAILED"
            try:
                with open(os.path.join(results_dir, "result.json"), "w") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return result

        # Step 2: build the prompt
        log.info(f"[{task_id}] Step 2: build prompt")
        workspace_path = os.path.join(paths["tasks_dir"], task_id, "docker", "workspace")
        try:
            prompt = build_prompt(task_id, paths["check_dir"], paths["tasks_dir"], workspace_path=workspace_path)
            prompt_path = os.path.join(results_dir, "prompt.md")
            with open(prompt_path, "w") as f:
                f.write(prompt)
            log.info(f"[{task_id}] Prompt {len(prompt)} chars")
        except FileNotFoundError as e:
            log.error(f"[{task_id}] {e}")
            result["finished_at"] = datetime.now().isoformat()
            result["status"] = "PROMPT_BUILD_FAILED"
            try:
                with open(os.path.join(results_dir, "result.json"), "w") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return result

        # Step 3: run Codex
        log.info(f"[{task_id}] Step 3: run Codex")
        codex_result = run_codex(
            task_id=task_id,
            prompt=prompt,
            workspace_path=workspace_path,
            model=model,
            timeout=codex_config.get("timeout", 10800),
            results_dir=results_dir,
            api_key=api_key,
            base_url=base_url,
            max_retries=codex_config.get("max_retries", 1),
            check_dir=paths["check_dir"],
            container_name=container_name,
        )
        result["codex"] = codex_result

        with open(os.path.join(results_dir, "codex_output.json"), "w") as f:
            json.dump(codex_result, f, indent=2, ensure_ascii=False)

        if codex_result.get("error") == "timeout":
            log.warning(f"[{task_id}] Codex timed out ({codex_result['elapsed_seconds']}s)")
        elif codex_result["turn_completed"]:
            usage = codex_result.get("token_usage", {})
            log.info(f"[{task_id}] Codex completed ({codex_result['elapsed_seconds']}s, "
                     f"{codex_result['events_count']} events, "
                     f"tokens: in={usage.get('input_tokens', '?')} out={usage.get('output_tokens', '?')})")
        else:
            log.warning(f"[{task_id}] Codex did not complete normally (exit={codex_result['returncode']}, "
                        f"{codex_result['events_count']} events)")

        # Step 3.5: anti-cheat L1 — aligned with run_benchmark.py. Convert
        try:
            from audits.anti_cheat_l1 import scan_trajectory
            ac_events_file = os.path.join(results_dir, "codex_events.jsonl")
            ac_traj_path = os.path.join(results_dir, "anti_cheat_trajectory.json")
            n_actions = _codex_events_to_trajectory(ac_events_file, ac_traj_path)
            if n_actions == 0:
                log.info(f"[{task_id}] anti-cheat L1: no command_execution events to scan")
                result["anti_cheat"] = {
                    "verdict": "skipped",
                    "hit_count": 0,
                    "scanned_actions": 0,
                    "reason": "no command_execution events in codex_events.jsonl",
                }
            else:
                ac_report = scan_trajectory(ac_traj_path)
                result["anti_cheat"] = {
                    "verdict": ac_report["verdict"],
                    "hit_count": ac_report["hit_count"],
                    "scanned_actions": ac_report["scanned_actions"],
                    "categories_hit": ac_report.get("categories_hit", []),
                }
                if ac_report["verdict"] == "suspected":
                    cats = ",".join(ac_report.get("categories_hit", []))
                    log.warning(
                        f"[{task_id}] ⚠️ anti-cheat L1: SUSPECTED "
                        f"(hits={ac_report['hit_count']}, categories=[{cats}]) "
                        f"→ see {os.path.join(results_dir, 'anti_cheat_report.json')}"
                    )
                elif ac_report["verdict"] == "error":
                    log.warning(
                        f"[{task_id}] anti-cheat L1: ERROR — {ac_report.get('error')}"
                    )
                else:
                    log.info(
                        f"[{task_id}] anti-cheat L1: clean "
                        f"(scanned {ac_report['scanned_actions']} actions)"
                    )
        except Exception as e:
            log.warning(f"[{task_id}] anti-cheat L1 scan failed (does not affect evaluation): {e}")

        try:
            workspace_snapshot = os.path.join(results_dir, "workspace_snapshot")
            if os.path.exists(workspace_path) and os.listdir(workspace_path):
                shutil.copytree(
                    workspace_path, workspace_snapshot, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(
                        'node_modules', 'vendor', '__pycache__', '*.pyc',
                        '.pnpm-store', '.yarn', '.npm',
                        '.turbo', '.next', '.nuxt', '.svelte-kit', '.cache',
                        '.git', '.idea', '.vscode',
                    ),
                )
                log.info(f"[{task_id}] saved workspace snapshot")
        except Exception as e:
            log.warning(f"[{task_id}] saving snapshot failed: {e}")

        # Step 4: run evaluation
        log.info(f"[{task_id}] Step 4: evaluation")
        eval_result = run_evaluation(
            task_id,
            paths["check_dir"],
            timeout=codex_config.get("eval_timeout", 5400),
            results_dir=results_dir,
        )
        result["evaluation"] = eval_result

        with open(os.path.join(results_dir, "evaluation_output.json"), "w") as f:
            json.dump(eval_result, f, indent=2, ensure_ascii=False)

        eval_results_dst = os.path.join(results_dir, "eval_reports")
        try:
            import glob
            eval_dir = os.path.join(paths["check_dir"], f"{task_id}_e", "evaluate")
            os.makedirs(eval_results_dst, exist_ok=True)
            for src_dir in ["results_smoke/model_test", "results_smoke/model_test_llm",
                             "results/model_test", "results/model_test_llm"]:
                src_path = os.path.join(eval_dir, src_dir)
                if os.path.isfile(src_path):
                    shutil.copy2(src_path, os.path.join(eval_results_dst, os.path.basename(src_dir) + ".json"))
                    log.info(f"[{task_id}] copied evaluation results: {src_dir}")
                elif os.path.isdir(src_path):
                    for f in glob.glob(os.path.join(src_path, "*.json")):
                        shutil.copy2(f, os.path.join(eval_results_dst, os.path.basename(src_dir) + "_" + os.path.basename(f)))
                    log.info(f"[{task_id}] copied evaluation results: {src_dir}/")
        except Exception as e:
            log.warning(f"[{task_id}] copying evaluation results failed: {e}")

        scored = _extract_score_from_reports(eval_results_dst)
        if scored:
            s, m, p = scored["score"], scored["max"], scored["percentage"]
            result["score"] = scored
            result["score_line"] = f"{s}/{m} = {p:.1f}%  ({scored['source']})"
            result["score_total"] = result["score_line"]
            log.info(f"[{task_id}] 📊 {result['score_line']}")

        _TOTAL_PREFIXES = ("Total Score:", "Total:", "Score:")
        if eval_result.get("stdout_tail"):
            for line in eval_result["stdout_tail"].split("\n"):
                s = line.strip()
                if "score_total" not in result and any(s.startswith(p) for p in _TOTAL_PREFIXES):
                    result["score_total"] = s
                    result["score_line"] = s
                elif s.startswith("Non-LLM nodes only:") and "score_non_llm" not in result:
                    result["score_non_llm"] = s
            if result.get("score_non_llm"):
                log.info(f"[{task_id}] 📊 {result['score_non_llm']}")
            if not result.get("score_line"):
                for line in eval_result["stdout_tail"].split("\n"):
                    if "%" in line and ("/" in line or "=" in line):
                        result["score_line"] = line.strip()
                if "score_line" in result:
                    log.info(f"[{task_id}] 📊 (stdout fallback) {result['score_line']}")

        if (not result.get("score_non_llm")
                and _dag_has_llm_nodes(paths["check_dir"], task_id)):
            log.warning(
                f"[{task_id}] ⚠️ score_non_llm missing: dag has LLM nodes but _print_score.py "
                "produced no 'Non-LLM nodes only:' line (likely the evaluator's report schema "
                "lacks a node-level list, or _print_score.py doesn't recognize it)"
            )

        result["finished_at"] = datetime.now().isoformat()

        #
        leak = _detect_score_leak(task_id, results_dir, paths["check_dir"])
        result["leak_check"] = {
            "eval_hits": leak["eval_hits"],
            "check_hits": leak["check_hits"],
            "samples": leak["samples"],
            "scanned": leak["scanned"],
        }

        leak_voided = False
        if leak["eval_hits"] > 0:
            log.error(
                f"[{task_id}] ⚠️ EVALUATOR LEAK: eval_hits={leak['eval_hits']} "
                f"check_hits={leak['check_hits']} → score voided"
            )
            result["original_score"] = result.get("score")
            result["original_score_line"] = result.get("score_line")
            result["original_score_total"] = result.get("score_total")
            result["original_score_non_llm"] = result.get("score_non_llm")
            max_v = (result.get("score") or {}).get("max", 0.0)
            result["score"] = {
                "score": 0.0, "max": max_v, "percentage": 0.0,
                "source": "VOIDED_BY_LEAK",
            }
            result["score_line"] = (
                f"VOIDED (leak: eval={leak['eval_hits']} "
                f"check={leak['check_hits']})"
            )
            result["score_total"] = result["score_line"]
            result["score_non_llm"] = result["score_line"]
            leak_voided = True
        elif leak["check_hits"] > 0:
            log.warning(
                f"[{task_id}] mild leak: check_hits={leak['check_hits']} "
                f"(no evaluator core) — score kept and flagged in status_notes"
            )
            result.setdefault("status_notes", []).append("MILD_LEAK")

        ev = result.get("evaluation", {})
        if leak_voided:
            result["status"] = "VOIDED_BY_LEAK"
        elif ev.get("error") == "timeout":
            result["status"] = "EVAL_TIMEOUT"
        elif not ev.get("success", False):
            result["status"] = "EVAL_FAILED"
        elif not result.get("score_line"):
            result["status"] = "COMPLETED_NO_SCORE"
        else:
            result["status"] = "COMPLETED"

        with open(os.path.join(results_dir, "result.json"), "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        _summary_bits = [result.get("score_total") or result.get("score_line") or "no score"]
        if result.get("score_non_llm"):
            _summary_bits.append(result["score_non_llm"])
        log.info(f"[{task_id}] === done === " + " | ".join(_summary_bits))
        return result

    finally:
        # Step 5: clean up Docker containers (free memory, avoid accumulation)
        log.info(f"[{task_id}] Step 5: clean up containers (including volumes)")
        try:
            subprocess.run(
                ["docker", "compose", "down", "-v", "--remove-orphans"],
                capture_output=True, text=True, timeout=120,
                cwd=docker_dir_for_cleanup,
            )
            log.info(f"[{task_id}] containers cleaned up")
        except Exception as e:
            log.warning(f"[{task_id}] container cleanup failed: {e}")
        finally:
            _ACTIVE_DOCKER_DIRS.discard(docker_dir_for_cleanup)


def main():
    parser = argparse.ArgumentParser(description="SaaSBench Benchmark — Codex Edition")
    parser.add_argument("--config", default="benchmark_config.yaml", help="path to the config file")
    parser.add_argument("--tasks", nargs="*", help="run only the given tasks")
    parser.add_argument("--model", default="gpt-5.4", help="model used by Codex (default gpt-5.4)")
    parser.add_argument("--api-key", default="", help="OpenAI API Key (can also use the OPENAI_API_KEY env var)")
    parser.add_argument("--base-url", default="", help="custom API base URL")
    parser.add_argument("--concurrency", type=int, default=1, help="number of concurrent tasks (default 1, serial)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan only, do not execute")
    args = parser.parse_args()

    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(SCRIPT_DIR, config_path)
    config = load_config(config_path)
    config["_concurrency"] = args.concurrency

    all_tasks = discover_tasks(config["paths"]["tasks_dir"])
    if args.tasks:
        tasks = [t for t in args.tasks if t in all_tasks]
    elif config.get("tasks") and len(config["tasks"]) > 0:
        tasks = [t for t in config["tasks"] if t in all_tasks]
    else:
        tasks = all_tasks

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL", "")
    model = args.model
    concurrency = args.concurrency

    # Codex always runs in-container using the portable codex bind-mounted into
    # the app container; the host codex CLI is not required.
    runtime_dir = _resolve_codex_runtime_dir()
    ok, why = _check_codex_runtime_ready(runtime_dir)
    if not ok:
        print(f"❌ codex runtime not ready for in-container mode: {why}")
        print(f"   → build it, e.g.:")
        print(f"     mkdir -p {runtime_dir}/bin && cp <static-codex> {runtime_dir}/bin/codex && chmod +x {runtime_dir}/bin/codex")
        sys.exit(1)
    codex_version = f"in-container runtime @ {runtime_dir}"

    if not api_key:
        print("❌ OPENAI_API_KEY not set. Please run: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    isolation_status = "in-container (evaluator not mounted → no host FS exposure)"

    os.makedirs(config["paths"]["results_dir"], exist_ok=True)

    print(f"SaaSBench Benchmark — Codex Edition")
    print(f"  Codex version: {codex_version}")
    print(f"  Model: {model}")
    print(f"  Tasks: {len(tasks)}")
    print(f"  Concurrency: {concurrency}")
    print(f"  API Key: {api_key[:12]}...{api_key[-4:]}")
    print(f"  Isolation: {isolation_status}")
    print(f"  Leak detection: always enabled (eval_hits≥1 → VOIDED_BY_LEAK)")
    if base_url:
        print(f"  Base URL: {base_url}")
    print()

    if args.dry_run:
        for task_id in tasks:
            print(f"  [DRY RUN] {task_id} × {model}")
        return

    all_results = []
    results_lock = threading.Lock()

    def worker(task_id: str) -> dict:
        try:
            result = run_single(
                task_id, model, config,
                api_key=api_key, base_url=base_url,
            )
        except Exception as e:
            log.error(f"[{task_id}] uncaught exception: {e}")
            result = {
                "task": task_id,
                "model": model,
                "agent": "codex",
                "status": "ERROR",
                "error": str(e),
            }
        with results_lock:
            all_results.append(result)
        return result

    if concurrency <= 1:
        for task_id in tasks:
            worker(task_id)
    else:
        log.info(f"launching {concurrency} concurrent workers")
        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="task") as executor:
            futures = {executor.submit(worker, t): t for t in tasks}
            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    future.result()
                except Exception as e:
                    log.error(f"[{task_id}] worker exception: {e}")

    summary_path = os.path.join(
        config["paths"]["results_dir"],
        f"summary_codex_{model.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(summary_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"All done! Summary: {summary_path}")
    print(f"{'='*70}")

    print(f"\n{'Task':<20} {'Model':<20} {'Elapsed':>8} {'events':>8} {'Status':<14} {'Total':<28} {'Non-LLM total':<28}")
    print("-" * 140)
    for r in sorted(all_results, key=lambda x: x.get("task", "")):
        total = r.get("score_total") or r.get("score_line") or "N/A"
        non_llm = r.get("score_non_llm") or "—"
        status = r.get("status", "?")
        elapsed = r.get("codex", {}).get("elapsed_seconds", "?")
        events = r.get("codex", {}).get("events_count", "?")
        print(f"{r['task']:<20} {r['model']:<20} {elapsed:>7}s {events:>7} {status:<14} {total:<28} {non_llm:<28}")


if __name__ == "__main__":
    main()
