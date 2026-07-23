#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

from config import DAG_PATH, SCORING_CONFIG_PATH, RESULTS_DIR
from harness import load_dag, load_scoring_config, execute_dag, aggregate_results
from utils import print_result, save_results


def main():
    parser = argparse.ArgumentParser(description="XM Platform Evaluation Harness")
    parser.add_argument("--output", default="evaluation_results.json", help="Output filename")
    parser.add_argument("--dag", default=DAG_PATH, help="Path to dag.json")
    parser.add_argument("--scoring", default=SCORING_CONFIG_PATH, help="Path to scoring_config.json")
    parser.add_argument("--with-llm", action="store_true", help="Enable LLM-judge nodes")
    parser.add_argument("--only-category", type=str, default=None, help="Run only nodes in this category")
    parser.add_argument("--dry-run", action="store_true", help="List nodes without executing")
    args = parser.parse_args()

    print("=" * 70)
    print("  XM Platform Evaluation Harness")
    print("=" * 70)

    dag = load_dag(args.dag)
    scoring_config = load_scoring_config(args.scoring)

    print(f"\nDAG: {dag['meta']['total_nodes']} nodes")
    print(f"Scoring: {scoring_config['total_maxScore']} max points")
    print(f"LLM Judge: {'enabled' if args.with_llm else 'disabled'}")
    if args.only_category:
        print(f"Category filter: {args.only_category}")
    print()

    if args.dry_run:
        for node in dag["nodes"]:
            cat = node["scoring"]["category"]
            if args.only_category and cat != args.only_category:
                continue
            print(f"  [{cat}] {node['id']}: {node['description']} (maxScore={node['scoring']['maxScore']}, method={node['scoring']['method']})")
        return

    start_time = time.time()

    results = execute_dag(dag, scoring_config, with_llm=args.with_llm, only_category=args.only_category)

    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("  Results")
    print("=" * 70)

    for nid, result in results.items():
        print_result(result)

    report = aggregate_results(results, scoring_config)
    report["elapsed_seconds"] = round(elapsed, 2)
    report["meta"] = dag["meta"]

    print("\n" + "-" * 70)
    print("  Category Summary")
    print("-" * 70)
    for cat in report["categories"]:
        pct = cat["percentage"]
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {cat['category']:25s} {bar} {cat['total_score']:6.1f}/{cat['max_score']:6.1f} ({pct:5.1f}%) [{cat['passed']}/{cat['nodes']} passed]")

    print("\n" + "=" * 70)
    print(f"  TOTAL: {report['total_score']:.1f}/{report['total_max']:.1f} ({report['percentage']:.1f}%)")
    print(f"  Nodes: {report['passed']} passed, {report['failed']} failed, {report['skipped']} skipped")
    print(f"  Time: {elapsed:.1f}s")
    print("=" * 70)

    save_results(report, args.output)


if __name__ == "__main__":
    main()
