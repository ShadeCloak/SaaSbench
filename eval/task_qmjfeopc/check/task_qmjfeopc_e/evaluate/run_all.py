#!/usr/bin/env python3

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import config
from harness import load_dag, load_scoring_config, execute_dag, aggregate_results, topological_sort
from utils import save_results, print_summary


def main():
    parser = argparse.ArgumentParser(description="SaaSBench Evaluation Runner")
    parser.add_argument("--output", default="results.json",
                        help="Output filename (in results/ dir)")
    parser.add_argument("--with-llm", action="store_true",
                        help="Enable LLM-judge nodes")
    parser.add_argument("--only-category", default=None,
                        help="Run only nodes in this category")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print execution order without running")
    parser.add_argument("--dag", default=None,
                        help="Path to DAG JSON file (default: dag.json)")
    args = parser.parse_args()

    dag_path = args.dag or config.DAG_PATH
    dag = load_dag(dag_path)
    scoring_config = load_scoring_config(config.SCORING_CONFIG_PATH)

    print(f"Loaded DAG: {dag['meta']['total_nodes']} nodes from {dag_path}")
    print(f"App URL: {config.APP_BASE_URL}")
    print(f"MongoDB: {config.MONGO_HOST}:{config.MONGO_PORT}/{config.MONGO_DB}")
    print()

    if args.dry_run:
        ordered = topological_sort(dag["nodes"])
        for i, n in enumerate(ordered, 1):
            s = n["scoring"]
            print(f"  {i:3d}. {n['id']:45s} [{s['category']:20s}] max={s['maxScore']}")
        print(f"\nTotal: {len(ordered)} nodes, {sum(n['scoring']['maxScore'] for n in ordered)} points")
        return

    print("=" * 60)
    print("  Evaluation Run")
    print("=" * 60)

    results = execute_dag(dag, scoring_config,
                          only_category=args.only_category,
                          with_llm=args.with_llm)

    report = aggregate_results(results, scoring_config)
    path = save_results(report, args.output)

    print_summary(results)
    print(f"\nDetailed results saved to: {path}")


if __name__ == "__main__":
    main()
