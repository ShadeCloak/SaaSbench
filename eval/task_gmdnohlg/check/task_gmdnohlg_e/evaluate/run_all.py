#!/usr/bin/env python3
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import DAG_PATH, SCORING_CONFIG_PATH, RESULTS_DIR
from harness import load_dag, execute_dag, aggregate_results
from utils import save_results


def main():
    parser = argparse.ArgumentParser(description="CloudCollab Platform Evaluation Harness")
    parser.add_argument("--output", default="evaluation_results.json", help="Output filename in results/")
    parser.add_argument("--dag", default=DAG_PATH, help="Path to dag.json")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM-Judge nodes")
    parser.add_argument("--only-category", default=None, help="Run only nodes from this category")
    parser.add_argument("--dry-run", action="store_true", help="Load DAG and show node list without executing")
    parser.add_argument("--help-categories", action="store_true", help="List available categories")
    args = parser.parse_args()

    dag = load_dag(args.dag)
    meta = dag.get("meta", {})
    print(f"Task: {meta.get('task_id', 'unknown')}")
    print(f"Nodes: {meta.get('total_nodes', len(dag['nodes']))}")
    print(f"Total maxScore: {meta.get('total_maxScore', '?')}")

    if args.help_categories:
        cats = set(n["scoring"]["category"] for n in dag["nodes"])
        for c in sorted(cats):
            count = sum(1 for n in dag["nodes"] if n["scoring"]["category"] == c)
            print(f"  {c}: {count} nodes")
        return

    if args.dry_run:
        print("\nDry run - node list:")
        for n in dag["nodes"]:
            prereqs = ", ".join(n.get("prereqs", [])) or "none"
            print(f"  {n['id']} ({n['scoring']['category']}/{n['scoring'].get('subcategory','')}) "
                  f"maxScore={n['scoring']['maxScore']} prereqs=[{prereqs}]")
        return

    with_llm = not args.no_llm
    results = execute_dag(dag, with_llm=with_llm, only_category=args.only_category)

    with open(SCORING_CONFIG_PATH, "r", encoding="utf-8") as f:
        scoring_config = json.load(f)

    report = aggregate_results(results, scoring_config)

    print(f"\n{'='*60}")
    print(f"EVALUATION COMPLETE")
    print(f"{'='*60}")
    print(f"Total Score: {report['summary']['total_score']}/{report['summary']['total_max']} "
          f"({report['summary']['percentage']}%)")
    print(f"Passed: {report['summary']['passed']} | Failed: {report['summary']['failed']} | "
          f"Skipped: {report['summary']['skipped']} | Errors: {report['summary']['errors']}")
    print(f"\nBy category:")
    for cat in report["categories"]:
        icon = "[OK]" if cat["percentage"] >= 70 else "[WARN]" if cat["percentage"] >= 30 else "[FAIL]"
        print(f"  {icon} {cat['category']}: {cat['total_score']}/{cat['max_score']} ({cat['percentage']}%)")

    path = save_results(report, args.output)
    print(f"\nResults saved to: {path}")


if __name__ == "__main__":
    main()
