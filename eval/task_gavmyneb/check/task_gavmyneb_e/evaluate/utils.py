from __future__ import annotations
import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config

# =============================================================================
# =============================================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("harness")


# =============================================================================
# =============================================================================
@dataclass
class StepResult:
    primitive: str
    inputs: dict
    output: Any = None
    passed: bool = False
    elapsed_ms: float = 0.0
    error: str | None = None


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    max_score: float
    chain_results: list[StepResult] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    message: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "score": round(self.score, 3),
            "max_score": self.max_score,
            "ratio": round(self.score / self.max_score, 3) if self.max_score else 0.0,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "message": self.message,
            "chain": [
                {
                    "primitive": s.primitive,
                    "passed": s.passed,
                    "elapsed_ms": round(s.elapsed_ms, 1),
                    "error": s.error,
                }
                for s in self.chain_results
            ],
            "evidence_keys": list(self.evidence.keys()),
        }


# =============================================================================
# =============================================================================
class ArtifactStore:
    def __init__(self):
        self.evidence: dict[str, dict] = {}
        self._stack: list[str] = []

    def push_context(self, node_id: str) -> None:
        self._stack.append(node_id)
        self.evidence.setdefault(node_id, {})

    def pop_context(self) -> str | None:
        return self._stack.pop() if self._stack else None

    @property
    def current(self) -> str | None:
        return self._stack[-1] if self._stack else None

    def store(self, key: str, value: Any) -> None:
        if not self.current:
            return
        self.evidence[self.current][key] = value

    def fetch(self, node_id: str, key: str, default: Any = None) -> Any:
        return self.evidence.get(node_id, {}).get(key, default)


# =============================================================================
# =============================================================================
PLACEHOLDER_RE = re.compile(r"\{\{(\w[\w_]*)\}\}")
COLON_PLACEHOLDER_RE = re.compile(r"(?<![:\w]):([a-zA-Z_][a-zA-Z0-9_]*)")


def substitute(template: Any, context: dict) -> Any:
    if isinstance(template, str):
        m_full = PLACEHOLDER_RE.fullmatch(template.strip())
        if m_full and m_full.group(1) in context:
            return context[m_full.group(1)]

        def repl(m):
            key = m.group(1)
            return str(context.get(key, m.group(0)))
        out = PLACEHOLDER_RE.sub(repl, template)

        def repl_colon(m):
            key = m.group(1)
            return str(context[key]) if key in context else m.group(0)
        out = COLON_PLACEHOLDER_RE.sub(repl_colon, out)
        return out
    if isinstance(template, dict):
        return {k: substitute(v, context) for k, v in template.items()}
    if isinstance(template, list):
        return [substitute(v, context) for v in template]
    return template


# =============================================================================
# =============================================================================
def jsonpath_get(obj: Any, path: str) -> Any:
    if path in ("$", ""):
        return obj
    p = path.lstrip("$").lstrip(".")
    out = obj
    for part in re.split(r"\.(?![^\[]*\])", p):
        if not part:
            continue
        m = re.match(r"^(\w+)?(\[(\d+)\])+$", part)
        if m:
            key = m.group(1)
            indices = re.findall(r"\[(\d+)\]", part)
            if key:
                if isinstance(out, dict):
                    out = out.get(key)
                else:
                    return None
            for idx in indices:
                try:
                    out = out[int(idx)]
                except (IndexError, KeyError, TypeError):
                    return None
            continue
        if isinstance(out, dict):
            out = out.get(part)
        elif isinstance(out, list):
            try:
                out = out[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return out


# =============================================================================
# =============================================================================
def run_command(cmd: list[str] | str, timeout: int = 30, capture_output: bool = True) -> subprocess.CompletedProcess:
    is_shell = isinstance(cmd, str)
    log.debug(f"run_command: {cmd!r}")
    try:
        return subprocess.run(
            cmd, shell=is_shell, timeout=timeout, capture_output=capture_output, text=True
        )
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(args=cmd, returncode=124, stdout="", stderr=f"TIMEOUT after {timeout}s: {e}")
    except FileNotFoundError as e:
        return subprocess.CompletedProcess(args=cmd, returncode=127, stdout="", stderr=str(e))


def docker_exec(container: str, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return run_command(["docker", "exec", container, "sh", "-c", command], timeout=timeout)


# =============================================================================
# =============================================================================
def load_dag(path: Path = config.DAG_FILE) -> dict:
    return json.loads(Path(path).read_text())


def topological_sort(nodes: list[dict]) -> list[str]:
    by_id = {n["id"]: n for n in nodes}
    in_deg = {nid: 0 for nid in by_id}
    fwd = {nid: set() for nid in by_id}
    for nid, node in by_id.items():
        for p in node.get("prereqs", []):
            if p in by_id:
                fwd[p].add(nid)
                in_deg[nid] += 1
    queue = sorted([nid for nid, d in in_deg.items() if d == 0])
    out = []
    while queue:
        nid = queue.pop(0)
        out.append(nid)
        for child in sorted(fwd[nid]):
            in_deg[child] -= 1
            if in_deg[child] == 0:
                queue.append(child)
    if len(out) != len(by_id):
        raise RuntimeError(f"Cycle detected: visited {len(out)}/{len(by_id)} nodes")
    return out


def all_prereqs_passed(prereqs: list[str], results: dict[str, NodeResult]) -> bool:
    for p in prereqs:
        r = results.get(p)
        if not r:
            return False
        if r.status in ("FAILED", "SKIPPED_DEPENDENCY", "ERROR"):
            return False
    return True


# =============================================================================
# =============================================================================
class Timer:
    def __enter__(self):
        self._t0 = time.perf_counter()
        return self
    def __exit__(self, *_):
        self.elapsed_ms = (time.perf_counter() - self._t0) * 1000.0
