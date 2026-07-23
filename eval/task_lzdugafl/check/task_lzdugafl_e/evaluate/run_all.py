#!/usr/bin/env python3
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import config
import harness
import utils


def main():
    parser = argparse.ArgumentParser(description="SaaSBench Evaluation Harness")
    parser.add_argument("--output", default="evaluation_report.json", help="Output filename")
    parser.add_argument("--with-llm", action="store_true", help="Enable LLM-judge nodes")
    parser.add_argument("--only-category", type=str, default=None, help="Run only specified category")
    parser.add_argument("--dry-run", action="store_true", help="Load DAG and print stats without running")
    args = parser.parse_args()

    dag_path = os.path.join(os.path.dirname(__file__), "dag.json")
    scoring_path = os.path.join(os.path.dirname(__file__), "scoring_config.json")

    dag = harness.load_dag(dag_path)
    scoring_config = harness.load_scoring_config(scoring_path)

    print(f"Loaded DAG: {dag['meta']['total_nodes']} nodes")
    print(f"Task: {dag['meta']['task_id']}")

    if args.dry_run:
        ordered = harness.topological_sort(dag["nodes"])
        print(f"Topological order verified: {len(ordered)} nodes")
        from collections import Counter
        cats = Counter(n["scoring"]["category"] for n in dag["nodes"])
        for cat, cnt in sorted(cats.items()):
            print(f"  {cat}: {cnt} nodes")
        return

    print(f"\nRunning evaluation...")
    if args.with_llm:
        print("  LLM-judge: ENABLED")
    if args.only_category:
        print(f"  Category filter: {args.only_category}")

    context = {}
    results = harness.execute_dag(dag, scoring_config, context, with_llm=args.with_llm, only_category=args.only_category)

    report = harness.aggregate_results(results, scoring_config)
    utils.print_summary(report)
    utils.save_results(report, args.output)


if __name__ == "__main__":
    main()
