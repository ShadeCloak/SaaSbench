
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


if __package__ in (None, ""):
    HERE = Path(__file__).resolve().parent
    sys.path.insert(0, str(HERE.parent))
    __package__ = HERE.name

from . import config, harness, utils
from . import __version__ as _evaluate_version


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run task_iyjruvfz evaluation DAG")
    p.add_argument("--dag", default=str(config.DAG_FILE), help="dag.json path")
    p.add_argument(
        "--scoring-config",
        default=str(config.SCORING_CONFIG_FILE),
        help="scoring_config.json path",
    )
    p.add_argument(
        "--output",
        default=str(config.RESULTS_DIR / f"run_{time.strftime('%Y%m%d_%H%M%S')}.json"),
        help="path to write the JSON report (relative paths are resolved against config.RESULTS_DIR)",
    )
    p.add_argument(
        "--only-category",
        nargs="*",
        default=None,
        help="restrict to listed categories (e.g. Deployment Setup)",
    )
    p.add_argument(
        "--only-node-ids",
        nargs="*",
        default=None,
        help="restrict to listed node ids",
    )
    p.add_argument(
        "--with-llm",
        action="store_true",
        help="enable LLM judge (default: enabled if openai installed + LLM_API_KEY set)",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print DAG metadata and exit"
    )
    p.add_argument(
        "--teardown",
        action="store_true",
        help="include Teardown category (overrides SKIP_TEARDOWN)",
    )
    p.add_argument(
        "--cleanup",
        action="store_true",
        help="run fixtures.cleanup_eval_artifacts() AFTER the evaluation finishes "
             "(removes eval_*_<RANDOM_SUFFIX> rows; keeps seed users)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="suppress per-node line output",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.teardown:
        config.SKIP_TEARDOWN = False

    dag = harness.load_dag(args.dag)
    scoring_config = harness.load_scoring_config(args.scoring_config)

    print(f"[run_all] framework_version = {_evaluate_version}")
    print(f"[run_all] task_id           = {dag.get('meta', {}).get('task_id')}")
    print(f"[run_all] total nodes       = {len(dag.get('nodes', []))}")
    print(f"[run_all] APP_BASE_URL      = {config.APP_BASE_URL}")
    print(f"[run_all] DB                = {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
    print(f"[run_all] WORKSPACE_DIR     = {config.WORKSPACE_DIR}")
    print(f"[run_all] LLM judge enabled = {config.llm_judge_enabled()}")

    if args.dry_run:
        print("[run_all] dry-run: skipping execution.")
        return 0

    on_done = None if args.quiet else utils.print_result

    started = time.perf_counter()
    results = harness.execute_dag(
        dag,
        only_categories=args.only_category,
        only_node_ids=args.only_node_ids,
        on_node_done=on_done,
    )
    elapsed = time.perf_counter() - started

    report = harness.aggregate_results(results, dag, scoring_config)
    report["wall_time_sec"] = round(elapsed, 2)
    report["framework_version"] = _evaluate_version
    report["env"] = {
        "APP_BASE_URL": config.APP_BASE_URL,
        "APP_HOST": config.APP_HOST,
        "APP_PORT": config.APP_PORT,
        "DB_HOST": config.DB_HOST,
        "DB_PORT": config.DB_PORT,
        "DB_NAME": config.DB_NAME,
        "REDIS_PORT": config.REDIS_PORT,
        "WORKSPACE_DIR": str(config.WORKSPACE_DIR),
        "APP_CONTAINER": config.APP_CONTAINER,
        "DB_CONTAINER": config.DB_CONTAINER,
        "REDIS_CONTAINER": config.REDIS_CONTAINER,
        "API_KEY_PREFIX": os.environ.get("API_KEY_PREFIX", "app_"),
        "API_VERSION": config.DEFAULT_V2_HEADERS.get("Api-Version"),
        "LLM_JUDGE_ENABLED": config.llm_judge_enabled(),
        "LLM_MODEL": config.LLM_MODEL if config.llm_judge_enabled() else None,
        "RANDOM_SUFFIX": config.RANDOM_SUFFIX,
        "MOCK_WEBHOOK_PORT": config.MOCK_WEBHOOK_PORT,
        "SKIP_TEARDOWN": config.SKIP_TEARDOWN,
        "TEST_USER_EMAILS": {
            role: u["email"] for role, u in config.TEST_USERS.items()
        },
    }

    out_path = args.output
    if not os.path.isabs(out_path):
        out_path = str(config.RESULTS_DIR / out_path)
    utils.save_results(report, out_path)
    print(f"[run_all] saved report to {out_path}")
    harness.print_summary(report)

    if args.cleanup:
        from . import fixtures

        print("[run_all] running cleanup_eval_artifacts() ...")
        counts = fixtures.cleanup_eval_artifacts(verbose=True)
        report["cleanup_counts"] = counts
        utils.save_results(report, out_path)
        print(f"[run_all] cleanup done: {counts}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
