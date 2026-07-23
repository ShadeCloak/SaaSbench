#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

from config import DAG_PATH, SCORING_CONFIG_PATH, RESULTS_DIR, APP_BASE_URL
from harness import load_dag, load_scoring_config, execute_dag, aggregate_results, generate_report
from utils import wait_for_app, print_result


def main():
    parser = argparse.ArgumentParser(description="Run evaluation DAG against deployed application")
    parser.add_argument("--output", default=None,
                        help="Output JSON report path (default: results/eval_<timestamp>.json)")
    parser.add_argument("--dag", default=DAG_PATH,
                        help="Path to dag.json")
    parser.add_argument("--scoring-config", default=SCORING_CONFIG_PATH,
                        help="Path to scoring_config.json")
    parser.add_argument("--with-llm", action="store_true",
                        help="Enable LLM-judge nodes (requires LLM_API_KEY)")
    parser.add_argument("--only-category", default=None,
                        help="Run only nodes in this category")
    parser.add_argument("--dry-run", action="store_true",
                        help="List nodes without executing")
    parser.add_argument("--skip-wait", action="store_true",
                        help="Skip waiting for application to be ready")
    parser.add_argument("--no-seed", action="store_true",
                        help="Skip running the seed script")
    parser.add_argument("--help-categories", action="store_true",
                        help="List all categories in the DAG and exit")
    args = parser.parse_args()

    dag = load_dag(args.dag)
    scoring_config = load_scoring_config(args.scoring_config)

    if args.help_categories:
        cats = sorted(set(n["scoring"]["category"] for n in dag["nodes"]))
        print(f"Categories in DAG ({len(cats)}):")
        for c in cats:
            count = sum(1 for n in dag["nodes"] if n["scoring"]["category"] == c)
            score = sum(n["scoring"]["maxScore"] for n in dag["nodes"] if n["scoring"]["category"] == c)
            print(f"  {c}: {count} nodes, {score} pts")
        return

    print(f"=== Evaluation Harness ===")
    print(f"DAG: {os.path.basename(args.dag)} ({dag['meta']['total_nodes']} nodes)")
    print(f"Target: {APP_BASE_URL}")
    print()

    if not args.skip_wait and not args.dry_run:
        print("Waiting for application to be ready...", end=" ", flush=True)
        if wait_for_app(max_wait=90):
            print("ready.")
        else:
            print("TIMEOUT — proceeding anyway.")
        print()

    if not args.dry_run and not args.no_seed:
        try:
            from seed import run_seed
            from primitives import context as eval_context
            print("Running seed script to provision prerequisite data...")
            seed_ctx = run_seed()
            eval_context.update(seed_ctx)
            print(f"Seed complete — {len(seed_ctx)} context entries loaded.\n")
        except ModuleNotFoundError:
            print("Seed module not present in this distribution — skipping seed step. "
                  "Primitives will operate against live application state only.\n")

    start = time.time()
    results = execute_dag(dag, scoring_config,
                          only_category=args.only_category,
                          with_llm=args.with_llm,
                          dry_run=args.dry_run)
    elapsed = time.time() - start

    summary = aggregate_results(results, scoring_config)

    print(f"\n{'=' * 60}")
    print(f"RESULTS — {summary['percentage']:.1f}% ({summary['total_score']}/{summary['total_max']})")
    print(f"{'=' * 60}")
    print(f"Nodes: {summary['node_count']} | Time: {elapsed:.1f}s")
    print(f"Status: {dict(summary['status_distribution'])}")
    print()
    print("Categories:")
    for cat in summary["categories"]:
        bar = "█" * int(cat["percentage"] / 5) + "░" * (20 - int(cat["percentage"] / 5))
        print(f"  {cat['category']:25s} {cat['total_score']:6.1f}/{cat['max_score']:3d}  "
              f"{bar} {cat['percentage']:5.1f}%")
    print()
    if summary.get("trajectories"):
        print("Trajectories:")
        for name, t in summary["trajectories"].items():
            print(f"  {name}: {t['score']:.1f}/{t['max_score']} ({t['percentage']:.1f}%)")
    print()

    print("Node details:")
    for r in results:
        print_result(r)

    output = args.output
    if not output:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        output = os.path.join(RESULTS_DIR, f"eval_{ts}.json")

    full_report = generate_report(results, scoring_config, output)
    print(f"\nReport saved: {output}")
    return 0 if summary["percentage"] >= 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
