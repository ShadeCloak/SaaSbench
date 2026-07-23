import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests
import config


@dataclass
class NodeResult:
    node_id: str
    status: str
    score: float
    max_score: float
    category: str
    subcategory: str
    message: str = ""
    evidence: dict = None

    def to_dict(self):
        d = {"node_id": self.node_id, "status": self.status, "score": self.score,
             "max_score": self.max_score, "category": self.category, "subcategory": self.subcategory,
             "message": self.message}
        if self.evidence is not None:
            d["evidence"] = self.evidence
        return d


def http_get(url, headers=None, timeout=None, cookies=None):
    return requests.get(url, headers=headers or {}, timeout=timeout or config.HTTP_TIMEOUT, cookies=cookies)


def http_post(url, json_body=None, headers=None, timeout=None, cookies=None):
    return requests.post(url, json=json_body, headers=headers or {}, timeout=timeout or config.HTTP_TIMEOUT, cookies=cookies)


def http_patch(url, json_body=None, headers=None, timeout=None, cookies=None):
    return requests.patch(url, json=json_body, headers=headers or {}, timeout=timeout or config.HTTP_TIMEOUT, cookies=cookies)


def http_delete(url, headers=None, timeout=None, cookies=None):
    return requests.delete(url, headers=headers or {}, timeout=timeout or config.HTTP_TIMEOUT, cookies=cookies)


def docker_exec(command, container=None, expect_success=True):
    container = container or config.APP_CONTAINER
    last_proc = None
    last_err = None
    for shell in ("bash", "sh", "ash"):
        try:
            proc = subprocess.run(["docker", "exec", container, shell, "-c", command],
                capture_output=True, text=True, timeout=60)
        except Exception as e:
            last_err = str(e)
            continue
        last_proc = proc
        stderr_low = (proc.stderr or "").lower()
        if proc.returncode == 127 and ("not found" in stderr_low or "executable file not found" in stderr_low):
            continue
        if expect_success and proc.returncode != 0:
            raise RuntimeError(f"docker exec failed ({shell}): " + (proc.stderr or ""))
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    if last_proc is not None:
        if expect_success and last_proc.returncode != 0:
            raise RuntimeError("docker exec failed (no shell available): " + (last_proc.stderr or ""))
        return last_proc.returncode, last_proc.stdout or "", last_proc.stderr or ""
    raise RuntimeError("docker exec failed: " + (last_err or "no shell available"))


SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def save_results(results, output_path, scoring_config):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    by_cat = {}
    skipped_llm_max = 0.0
    for r in results.values():
        c = r.category
        if c not in by_cat:
            by_cat[c] = {"total_score": 0.0, "max_score": 0.0, "nodes": [], "skipped_llm": 0}
        in_skip = r.status in SKIP_FROM_TOTAL
        if not in_skip:
            by_cat[c]["total_score"] += r.score
            by_cat[c]["max_score"] += r.max_score
        else:
            by_cat[c]["skipped_llm"] += 1
            skipped_llm_max += r.max_score
        by_cat[c]["nodes"].append(r.to_dict())
    total_score = sum(r.score for r in results.values() if r.status not in SKIP_FROM_TOTAL)
    total_max = sum(r.max_score for r in results.values() if r.status not in SKIP_FROM_TOTAL)
    report = {"total_score": total_score, "total_max_score": total_max,
              "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
              "percentage": round(total_score / total_max * 100, 2) if total_max else 0,
              "categories": [{"category": k, **v} for k, v in by_cat.items()],
              "trajectories": scoring_config.get("trajectories", {}),
              "node_results": [r.to_dict() for r in results.values()]}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report
