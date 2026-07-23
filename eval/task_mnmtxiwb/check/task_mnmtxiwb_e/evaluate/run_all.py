#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

from config import RESULTS_DIR
from harness import load_dag, execute_dag, aggregate_results
from utils import save_results


def main():
    parser = argparse.ArgumentParser(description="Run DAG-based evaluation")
    parser.add_argument("--dag", default=None, help="Path to dag.json")
    parser.add_argument("--scoring-config", default=None, help="Path to scoring_config.json")
    parser.add_argument("--output", default="eval_results.json", help="Output filename")
    parser.add_argument("--only-category", default=None, help="Run only nodes in this category")
    parser.add_argument("--dry-run", action="store_true", help="List nodes without executing")
    parser.add_argument("--with-llm", action="store_true", help="Enable LLM-judge scoring")
    parser.add_argument("--no-test-fns", action="store_true", help="Use DAG-only execution")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    dag_path = args.dag or os.path.join(base_dir, "dag.json")
    sc_path = args.scoring_config or os.path.join(base_dir, "scoring_config.json")

    if not os.path.exists(dag_path):
        print(f"ERROR: dag.json not found at {dag_path}")
        sys.exit(1)

    dag = load_dag(dag_path)
    scoring_config = None
    if os.path.exists(sc_path):
        with open(sc_path, encoding="utf-8") as f:
            scoring_config = json.load(f)

    print(f"Loaded DAG: {dag['meta']['total_nodes']} nodes")
    print(f"Task ID: {dag['meta']['task_id']}")

    start = time.time()
    results = execute_dag(
        dag, scoring_config,
        only_category=args.only_category,
        dry_run=args.dry_run,
        use_test_fns=not args.no_test_fns
    )
    elapsed = time.time() - start

    report = aggregate_results(results, scoring_config)
    report["meta"] = {
        "task_id": dag["meta"]["task_id"],
        "elapsed_seconds": round(elapsed, 2),
        "dag_path": dag_path,
    }

    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"  EVALUATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Score: {s['total_score']}/{s['total_max_score']} ({s['normalized_score']}%)")
    print(f"  Nodes: {s['total_nodes']} | Time: {report['meta']['elapsed_seconds']}s")
    print(f"  Status: {dict(s['status_counts'])}")

    print(f"\n  --- By Category ---")
    for cat, data in sorted(report["categories"].items()):
        pct = round(data["score"] / data["max_score"] * 100, 1) if data["max_score"] > 0 else 0
        print(f"  {cat:25s} {data['score']:6.1f}/{data['max_score']:5.1f} ({pct:5.1f}%) [{data['passed']}/{data['nodes']} passed]")

    if "trajectories" in report:
        print(f"\n  --- Trajectories ---")
        for tname, tdata in report["trajectories"].items():
            print(f"  {tname:25s} {tdata['score']:6.1f}/{tdata['max_score']:5.1f} ({tdata['rate']:5.1f}%)")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, args.output)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Report saved to: {out_path}")


if __name__ == "__main__":
    main()
