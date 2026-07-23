#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from config import RESULTS_DIR
from harness import load_dag, execute_dag, aggregate_results
from utils import save_results


def main():
    parser = argparse.ArgumentParser(description="Run evaluation DAG")
    parser.add_argument("--dag", default=os.path.join(os.path.dirname(__file__), "dag.json"), help="Path to dag.json")
    parser.add_argument("--output", default=os.path.join(RESULTS_DIR, "eval_results.json"), help="Output file path")
    parser.add_argument("--with-llm", action="store_true", help="Enable LLM-judge nodes")
    parser.add_argument("--only-category", type=str, help="Run only nodes in this category")
    parser.add_argument("--dry-run", action="store_true", help="Print execution plan without running")
    args = parser.parse_args()

    dag = load_dag(args.dag)
    scoring_config = dag.get("scoring_config", {})

    if args.only_category:
        dag["nodes"] = [n for n in dag["nodes"] if n["scoring"].get("category") == args.only_category]
        print(f"Filtering to category '{args.only_category}': {len(dag['nodes'])} nodes")

    if args.dry_run:
        print(f"\nDry run — {len(dag['nodes'])} nodes would execute:")
        for n in dag["nodes"]:
            print(f"  {n['id']} ({n['scoring']['category']}/{n['scoring']['subcategory']}) maxScore={n['scoring']['maxScore']}")
        return

    print(f"\nStarting evaluation at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    start = time.time()

    results = execute_dag(dag)
    report = aggregate_results(results, scoring_config)
    report["meta"] = dag["meta"]
    report["elapsed_seconds"] = round(time.time() - start, 1)

    save_results(report, args.output)

    print(f"\n{'='*60}")
    print(f"  EVALUATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Total Score: {report['total_score']}/{report['total_maxScore']} ({report['percentage']}%)")
    print(f"  Nodes: {report['summary']['passed']} passed / {report['summary']['failed']} failed / {report['summary']['skipped']} skipped / {report['summary']['errors']} errors")
    print(f"  Time: {report['elapsed_seconds']}s")
    print(f"\n  Category Breakdown:")
    for cat in report["categories"]:
        pct = (cat["total_score"] / cat["max_score"] * 100) if cat["max_score"] > 0 else 0
        print(f"    {cat['category']:25s} {cat['total_score']:6.1f}/{cat['max_score']:6.1f} ({pct:5.1f}%) [{cat['passed']}P/{cat['failed']}F/{cat['skipped']}S/{cat['errors']}E]")
    if report.get("trajectories"):
        print(f"\n  Trajectories:")
        for tname, tdata in report["trajectories"].items():
            print(f"    {tname:25s} {tdata['score']:6.1f}/{tdata['maxScore']:6.1f} ({tdata['percentage']:5.1f}%)")
    print(f"\n  Results saved to: {args.output}")


if __name__ == "__main__":
    main()
