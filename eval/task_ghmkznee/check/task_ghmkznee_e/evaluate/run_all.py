#!/usr/bin/env python3

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import RESULTS_DIR
from harness import load_dag, load_scoring_config, execute_dag, aggregate_results
from utils import NodeResult, print_result, save_results


def main():
    parser = argparse.ArgumentParser(description="Run evaluation DAG")
    parser.add_argument("--dag", default=os.path.join(os.path.dirname(__file__), "dag.json"))
    parser.add_argument("--scoring", default=os.path.join(os.path.dirname(__file__), "scoring_config.json"))
    parser.add_argument("--output", default=os.path.join(RESULTS_DIR, "results.json"))
    parser.add_argument("--only-category", help="Run only nodes in this category")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM-judge nodes")
    parser.add_argument("--dry-run", action="store_true", help="Print DAG info without executing")
    args = parser.parse_args()

    dag = load_dag(args.dag)
    scoring_config = load_scoring_config(args.scoring)

    if args.dry_run:
        print(f"DAG: {dag['meta']['total_nodes']} nodes")
        print(f"Categories: {list(scoring_config['categories'].keys())}")
        print(f"Total maxScore: {scoring_config['total_maxScore']}")
        return

    print(f"=== Evaluation Harness ===")
    print(f"DAG: {dag['meta']['total_nodes']} nodes")
    print(f"Mode: {'no-llm' if args.no_llm else 'full'}")
    if args.only_category:
        print(f"Category filter: {args.only_category}")
    print()

    results = execute_dag(dag, scoring_config,
                          only_category=args.only_category,
                          with_llm=not args.no_llm)

    print("\n=== Node Results ===")
    for nid in sorted(results.keys()):
        print_result(results[nid])

    report = aggregate_results(results, scoring_config)

    print(f"\n=== Summary ===")
    print(f"Score: {report['total_score']}/{report['total_maxScore']} ({report['normalized_score']}%)")
    print(f"Nodes: {report['passed']} passed, {report['failed']} failed, {report['skipped']} skipped")

    print(f"\n=== Categories ===")
    for cat, info in sorted(report["categories"].items()):
        pct = round(info["score"] / info["maxScore"] * 100, 1) if info["maxScore"] else 0
        print(f"  {cat}: {info['score']}/{info['maxScore']} ({pct}%) [{info['passed']}P/{info['failed']}F/{info['skipped']}S]")

    if report.get("trajectories"):
        print(f"\n=== Trajectories ===")
        for tname, tinfo in report["trajectories"].items():
            print(f"  {tname}: {tinfo['score']}/{tinfo['maxScore']} ({tinfo['rate']}%)")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    full_report = {
        "summary": report,
        "nodes": {nid: {"status": r.status, "score": r.score, "max_score": r.max_score,
                         "category": r.category, "message": r.message,
                         "evidence": (r.evidence or {})}
                  for nid, r in results.items()}
    }
    with open(args.output, "w") as f:
        json.dump(full_report, f, indent=2)
    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
