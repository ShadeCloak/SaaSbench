#!/usr/bin/env python3
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import RESULTS_DIR
from harness import load_dag, execute_dag, aggregate_results
from utils import save_results


def main():
    parser = argparse.ArgumentParser(description="IAM Platform Evaluation Runner")
    parser.add_argument("--output", default=os.path.join(RESULTS_DIR, "eval_results.json"), help="Output JSON file")
    parser.add_argument("--dag", default=os.path.join(os.path.dirname(__file__), "dag.json"), help="DAG definition file")
    parser.add_argument("--scoring-config", default=os.path.join(os.path.dirname(__file__), "scoring_config.json"), help="Scoring config file")
    parser.add_argument("--with-llm", action="store_true", default=False, help="Enable LLM-judge nodes")
    parser.add_argument("--only-category", type=str, default=None, help="Run only nodes in this category")
    parser.add_argument("--dry-run", action="store_true", default=False, help="List nodes without executing")
    parser.add_argument("--help-categories", action="store_true", default=False, help="List all categories")
    args = parser.parse_args()

    dag = load_dag(args.dag)

    with open(args.scoring_config, encoding="utf-8") as f:
        scoring_config = json.load(f)

    if args.help_categories:
        print("Available categories:")
        for cat, info in sorted(scoring_config.get("categories", {}).items()):
            print(f"  {cat}: {info['node_count']} nodes, {info['maxScore']} pts")
        return

    if args.dry_run:
        print(f"DAG: {dag['meta']['total_nodes']} nodes")
        for n in dag["nodes"]:
            deps = ", ".join(n.get("prereqs", [])) or "(root)"
            print(f"  {n['id']}: {n['scoring']['category']}/{n['scoring'].get('subcategory','')} [{n['scoring']['method']}, {n['scoring']['maxScore']}pts] deps=[{deps}]")
        return

    print(f"Loading DAG: {dag['meta']['total_nodes']} nodes")
    print(f"LLM-judge: {'enabled' if args.with_llm else 'disabled'}")
    if args.only_category:
        print(f"Filtering: {args.only_category}")

    results = execute_dag(dag, scoring_config, only_category=args.only_category, with_llm=args.with_llm)

    summary = aggregate_results(results, scoring_config)

    print(f"\n{'='*60}")
    print(f"  EVALUATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Total Score: {summary['total_score']}/{summary['total_max']} ({summary['percentage']}%)")
    print(f"  Passed: {summary['passed_nodes']}, Failed: {summary['failed_nodes']}, Skipped: {summary['skipped_nodes']}, Error: {summary['error_nodes']}")
    print(f"\n  By Category:")
    for cat in summary["categories"]:
        pct = round(cat["total_score"] / cat["max_score"] * 100, 1) if cat["max_score"] > 0 else 0
        print(f"    {cat['category']}: {cat['total_score']}/{cat['max_score']} ({pct}%) [{cat['passed']}/{cat['nodes']} passed]")

    report = {
        "meta": dag["meta"],
        "summary": summary,
        "results": [r.to_dict() for r in results],
    }
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Report saved to: {args.output}")


if __name__ == "__main__":
    main()
