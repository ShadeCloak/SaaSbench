import argparse
import json
import os
import sys
import time

try:
    from .harness import load_dag, load_scoring_config, execute_dag, aggregate_results, generate_report
    from .utils import NodeResult, save_results
    from .config import RESULTS_DIR
except ImportError:
    from harness import load_dag, load_scoring_config, execute_dag, aggregate_results, generate_report
    from utils import NodeResult, save_results
    from config import RESULTS_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DAG-driven evaluation runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help=f"Output path for results (default: {RESULTS_DIR})",
    )
    parser.add_argument(
        "--with-llm", action="store_true", default=False,
        help="Enable LLM-judge scoring (requires LLM_API_KEY)",
    )
    parser.add_argument(
        "--only-category", type=str, default=None, metavar="CATEGORY",
        help="Only evaluate nodes in this category",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Show execution plan without running primitives",
    )
    return parser


def print_summary_table(results: list, scoring_config: dict):
    aggregated = aggregate_results(results, scoring_config)
    summary = aggregated["summary"]
    by_category = aggregated["by_category"]
    by_trajectory = aggregated.get("by_trajectory", {})

    print(f"\n{'='*70}")
    print(f"  EVALUATION RESULTS")
    print(f"{'='*70}")
    print(f"  Score: {summary['total_score']:.1f} / {summary['max_score']:.1f} "
          f"({summary['percentage']:.1f}%)")
    print(f"  Normalized: {summary['normalized_score']:.1f}%")
    print(f"  Passed: {summary['nodes_passed']}  |  Failed: {summary['nodes_failed']}  "
          f"|  Skipped: {summary['nodes_skipped']}  |  Error: {summary['nodes_error']}")
    print(f"{'='*70}")

    if by_category:
        print(f"\n  {'Category':<25} {'Score':>8} {'Max':>8} {'Pct':>7} {'P':>4} {'F':>4} {'S':>4}")
        print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*7} {'-'*4} {'-'*4} {'-'*4}")
        for cat_name in sorted(by_category.keys()):
            cat = by_category[cat_name]
            print(f"  {cat_name:<25} {cat['score']:>8.1f} {cat['maxScore']:>8.1f} "
                  f"{cat['pct']:>6.1f}% {cat['passed']:>4} {cat['failed']:>4} {cat['skipped']:>4}")

    if by_trajectory:
        print(f"\n  {'Trajectory':<30} {'Score':>8} {'Max':>8} {'Pct':>7}")
        print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*7}")
        for traj_name, traj in by_trajectory.items():
            print(f"  {traj_name:<30} {traj['score']:>8.1f} {traj['maxScore']:>8.1f} "
                  f"{traj['pct']:>6.1f}%")

    print(f"{'='*70}\n")


def main():
    parser = build_parser()
    args = parser.parse_args()

    eval_dir = os.path.dirname(os.path.abspath(__file__))
    dag_path = os.path.join(eval_dir, "dag.json")
    config_path = os.path.join(eval_dir, "scoring_config.json")
    output_dir = args.output or RESULTS_DIR

    if not os.path.isfile(dag_path):
        print(f"Error: DAG file not found: {dag_path}", file=sys.stderr)
        sys.exit(1)

    dag = load_dag(dag_path)

    if os.path.isfile(config_path):
        scoring_config = load_scoring_config(config_path)
    else:
        scoring_config = {}

    node_count = len(dag.get("nodes", []))
    print(f"\nLoaded DAG with {node_count} nodes")

    if args.only_category:
        print(f"Filtering to category: {args.only_category}")

    if args.dry_run:
        print("[DRY RUN] Showing execution plan without running primitives.\n")

    t0 = time.time()
    results = execute_dag(
        dag,
        scoring_config,
        only_category=args.only_category,
        dry_run=args.dry_run,
        with_llm=args.with_llm,
    )
    elapsed = time.time() - t0

    print_summary_table(results, scoring_config)
    print(f"  Completed in {elapsed:.1f}s")

    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "report.json")
    report = generate_report(results, scoring_config, report_path)
    print(f"  Report saved to: {report_path}")

    node_results_path = os.path.join(output_dir, "node_results.json")
    save_results(results, node_results_path)
    print(f"  Node results saved to: {node_results_path}")

    sys.exit(0)


if __name__ == "__main__":
    main()
