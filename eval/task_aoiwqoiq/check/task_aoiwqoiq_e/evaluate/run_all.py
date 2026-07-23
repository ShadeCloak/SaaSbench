import argparse
import json
import os
import sys
from harness import load_dag, execute_dag, aggregate_results, generate_report
from utils import print_summary, save_results
from config import RESULTS_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SaaSBench DAG-driven evaluation runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dag", type=str, default="./dag.json",
        help="Path to dag.json (default: ./dag.json)",
    )
    parser.add_argument(
        "--config", type=str, default="./scoring_config.json",
        help="Path to scoring_config.json (default: ./scoring_config.json)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help=f"Output directory (default: {RESULTS_DIR})",
    )
    parser.add_argument(
        "--with-llm", action="store_true", default=False,
        help="Enable LLM-judge evaluation (default: False)",
    )
    parser.add_argument(
        "--only-category", type=str, default=None, metavar="CAT",
        help="Only run nodes in this category. WARNING: cross-category prereqs "
             "will cause SKIPPED_DEPENDENCY for nodes depending on other categories.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Print execution plan without running",
    )
    return parser


def print_execution_plan(dag: dict, only_category: str = None):
    nodes = dag.get("nodes", [])
    if only_category:
        nodes = [n for n in nodes if n.get("scoring", {}).get("category") == only_category]

    categories: dict[str, int] = {}
    for n in nodes:
        cat = n.get("scoring", {}).get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\n{'='*60}")
    print(f"  Execution Plan")
    print(f"{'='*60}")
    print(f"  Total nodes: {len(nodes)}")
    print(f"  Categories:")
    for cat, count in sorted(categories.items()):
        print(f"    {cat}: {count} nodes")
    print(f"{'='*60}\n")


def main():
    parser = build_parser()
    args = parser.parse_args()
    output_dir = args.output or RESULTS_DIR

    if not os.path.isfile(args.dag):
        print(f"Error: DAG file not found: {args.dag}", file=sys.stderr)
        sys.exit(1)

    dag = load_dag(args.dag)

    if os.path.isfile(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            scoring_config = json.load(f)
    else:
        scoring_config = dag.get("scoring_config", {})

    print_execution_plan(dag, args.only_category)

    if args.dry_run:
        print("[DRY RUN] Showing execution order without running primitives.\n")

    results = execute_dag(
        dag,
        scoring_config,
        only_category=args.only_category,
        dry_run=args.dry_run,
        with_llm=args.with_llm,
    )

    report = aggregate_results(results, scoring_config)
    print_summary(results, scoring_config)

    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "report.json")
    saved_path = generate_report(results, scoring_config, report_path)
    print(f"\nResults saved to: {saved_path}")

    save_results(results, os.path.join(output_dir, "node_results.json"))

    overall_score = report.get("overall", {}).get("score", 0)
    sys.exit(0 if overall_score > 0 else 1)


if __name__ == "__main__":
    main()
