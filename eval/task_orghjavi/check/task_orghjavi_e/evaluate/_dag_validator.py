from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("dag_validator")


def _step_type(step: Dict[str, Any]) -> str:
    return str(step.get("type") or step.get("primitive") or "")


def _iter_p17_steps(chain: List[Dict[str, Any]]):
    for step in chain or []:
        if _step_type(step) == "P17":
            yield step


def _step_score_range(inp: Dict[str, Any]) -> Optional[List[Any]]:
    if "score_range" in inp:
        return inp["score_range"]
    if "max_score" in inp:
        try:
            return [0, int(inp["max_score"])]
        except (TypeError, ValueError):
            return None
    return None


def validate(dag: Dict[str, Any],
             scoring_cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    issues: List[str] = []
    nodes = dag.get("nodes", []) if isinstance(dag, dict) else []

    valid_categories: Optional[set] = None
    if scoring_cfg and isinstance(scoring_cfg.get("categories"), dict):
        valid_categories = set(scoring_cfg["categories"].keys())

    for node in nodes:
        nid = node.get("id", "<unknown>")
        scoring = node.get("scoring", {}) or {}
        method = scoring.get("method", "")
        max_score = scoring.get("maxScore")
        category = scoring.get("category")
        chain = node.get("primitive_chain", []) or []

        if max_score is None:
            issues.append(f"[{nid}] scoring.maxScore is missing")
        elif not isinstance(max_score, (int, float)) or max_score < 0:
            issues.append(f"[{nid}] scoring.maxScore must be a non-negative number, got {max_score!r}")

        if valid_categories is not None and category and category not in valid_categories:
            issues.append(f"[{nid}] scoring.category={category!r} is not declared in scoring_config.categories")

        if method == "llm-judge":
            p17_steps = list(_iter_p17_steps(chain))
            if not p17_steps:
                issues.append(f"[{nid}] method=llm-judge but no P17 in primitive_chain")
            for step in p17_steps:
                inp = step.get("inputs", {}) or {}
                rng = _step_score_range(inp)
                if rng is None:
                    if isinstance(max_score, (int, float)):
                        issues.append(
                            f"[{nid}] WARN P17 missing explicit score_range / max_score; "
                            f"runtime will auto-derive [0, {int(max_score)}] from "
                            f"scoring.maxScore. Prefer declaring it explicitly.")
                    else:
                        issues.append(
                            f"[{nid}] P17 missing score_range / max_score "
                            f"(and scoring.maxScore is missing too)")
                    continue
                if not (isinstance(rng, (list, tuple)) and len(rng) == 2):
                    issues.append(f"[{nid}] P17 score_range must be [low, high], got {rng!r}")
                    continue
                low, high = rng[0], rng[1]
                if not (isinstance(low, (int, float)) and isinstance(high, (int, float))):
                    issues.append(f"[{nid}] P17 score_range members must be numeric, got {rng!r}")
                    continue
                if high <= low:
                    issues.append(f"[{nid}] P17 score_range high ({high}) must exceed low ({low})")
                if isinstance(max_score, (int, float)) and high != max_score:
                    issues.append(
                        f"[{nid}] P17 score_range[1]={high} but scoring.maxScore={max_score} "
                        f"(silent clamp / unreachable max)")
    return issues


def _split_issues(issues: List[str]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    for msg in issues:
        if " WARN " in msg or "] WARN" in msg:
            warnings.append(msg)
        else:
            errors.append(msg)
    return errors, warnings


def validate_or_die(dag: Dict[str, Any],
                    scoring_cfg: Optional[Dict[str, Any]] = None,
                    *, strict: bool = True,
                    exit_code: int = 2) -> None:
    issues = validate(dag, scoring_cfg)
    errors, warnings = _split_issues(issues)
    for msg in warnings:
        logger.warning("dag validation: %s", msg)
    if not errors:
        logger.info("dag validation: OK (%d nodes, %d warning(s))",
                       len(dag.get("nodes", [])), len(warnings))
        return
    for msg in errors:
        logger.error("dag validation: %s", msg)
    if strict:
        sys.stderr.write(
            f"\nDAG validation failed: {len(errors)} error(s) "
            f"(+ {len(warnings)} warning(s)); aborting.\n"
        )
        for msg in errors[:50]:
            sys.stderr.write(f"  - {msg}\n")
        if len(errors) > 50:
            sys.stderr.write(f"  ... ({len(errors) - 50} more errors)\n")
        sys.exit(exit_code)


def validate_task_dir(eval_dir: Optional[str] = None,
                       *, strict: bool = True,
                       exit_code: int = 2) -> None:
    import inspect
    import json
    import os

    if eval_dir is None:
        frame = inspect.stack()[1]
        eval_dir = os.path.dirname(os.path.abspath(frame.filename))

    dag_path = os.path.join(eval_dir, "dag.json")
    scoring_path = os.path.join(eval_dir, "scoring_config.json")

    if not os.path.isfile(dag_path):
        logger.warning("validate_task_dir: dag.json not found at %s — skipping", dag_path)
        return

    try:
        with open(dag_path, encoding="utf-8") as f:
            dag = json.load(f)
    except Exception as e:
        logger.warning("validate_task_dir: failed to parse dag.json: %s", e)
        return

    scoring_cfg: Optional[Dict[str, Any]] = None
    if os.path.isfile(scoring_path):
        try:
            with open(scoring_path, encoding="utf-8") as f:
                scoring_cfg = json.load(f)
        except Exception as e:
            logger.warning("validate_task_dir: failed to parse scoring_config.json: %s", e)

    validate_or_die(dag, scoring_cfg, strict=strict, exit_code=exit_code)


__all__ = ["validate", "validate_or_die", "validate_task_dir"]
