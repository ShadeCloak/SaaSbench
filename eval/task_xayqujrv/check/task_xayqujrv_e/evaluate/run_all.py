"""Stage 6.1 — Main entry point for the evaluation harness.

Usage:
    python run_all.py                              # full DAG, no LLM judge
    python run_all.py --with-llm                   # include P17 llm-judge nodes
    python run_all.py --only-category Webhook      # subset by category
    python run_all.py --dag dag_smoke.json         # use a smoke variant
    python run_all.py --dry-run                    # show plan only

Exit code 0 if total_score > 0 (i.e. anything ran successfully), else 1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from config import RESULTS_DIR
from harness import aggregate_results, execute_dag, generate_report, load_dag
from utils import print_summary, save_results


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SaaSBench DAG-driven evaluation runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dag", default="./dag.json",
                   help="Path to dag.json (default: ./dag.json)")
    p.add_argument("--config", default="./scoring_config.json",
                   help="Path to scoring_config.json")
    p.add_argument("--output", default=None,
                   help=f"Output directory (default: {RESULTS_DIR})")
    p.add_argument("--with-llm", action="store_true", default=False,
                   help="Enable LLM-judge (P17) nodes")
    p.add_argument("--only-category", default=None,
                   help="Run only the named category. Cross-category prereqs "
                        "may force SKIPPED_DEPENDENCY for downstream nodes.")
    p.add_argument("--dry-run", action="store_true", default=False,
                   help="Print execution plan without running primitives")
    return p


def print_plan(dag: dict, only_category: str | None = None) -> None:
    nodes = dag.get("nodes", [])
    if only_category:
        nodes = [n for n in nodes
                 if n.get("scoring", {}).get("category") == only_category]
    cats: dict[str, int] = {}
    for n in nodes:
        c = n.get("scoring", {}).get("category", "Unknown")
        cats[c] = cats.get(c, 0) + 1
    print(f"\n{'='*64}")
    print(f"  EXECUTION PLAN")
    print(f"{'='*64}")
    print(f"  Total nodes: {len(nodes)}")
    print(f"  Categories:")
    for c in sorted(cats):
        print(f"    {c:<32} {cats[c]:>3} nodes")
    print(f"{'='*64}\n")


def main() -> int:
    args = build_parser().parse_args()
    output_dir = args.output or RESULTS_DIR

    if not os.path.isfile(args.dag):
        print(f"Error: DAG not found: {args.dag}", file=sys.stderr)
        return 1
    dag = load_dag(args.dag)

    scoring_config: dict = {}
    if os.path.isfile(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            scoring_config = json.load(f)

    print_plan(dag, args.only_category)
    if args.dry_run:
        print("[DRY RUN] no primitives will be executed.\n")
    if args.with_llm:
        from config import assert_llm_configured
        assert_llm_configured()

    results = execute_dag(
        dag, scoring_config,
        only_category=args.only_category,
        dry_run=args.dry_run,
        with_llm=args.with_llm,
    )

    print_summary(results, scoring_config)

    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "report.json")
    saved = generate_report(results, scoring_config, report_path)
    print(f"\nReport: {saved}")

    nodes_path = os.path.join(output_dir, "node_results.json")
    save_results(results, nodes_path)
    print(f"Per-node results: {nodes_path}")

    overall = aggregate_results(results, scoring_config).get("overall", {})
    return 0 if overall.get("score", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
