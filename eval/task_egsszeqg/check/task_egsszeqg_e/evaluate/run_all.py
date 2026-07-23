#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys, os, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import RESULTS_DIR
from harness import load_dag, execute_dag, aggregate_results
from utils import save_results, print_summary


def main():
    parser = argparse.ArgumentParser(description="Run the evaluation harness.")
    parser.add_argument("--dag", default=str(Path(__file__).parent / "dag.json"),
                        help="Path to dag.json")
    parser.add_argument("--scoring", default=str(Path(__file__).parent / "scoring_config.json"),
                        help="Path to scoring_config.json")
    parser.add_argument("--output", default=None,
                        help="Path to write JSON results (default: results/<timestamp>.json)")
    parser.add_argument("--with-llm", action="store_true",
                        help="Enable LLM-judge nodes (requires LLM_API_KEY)")
    parser.add_argument("--only-category", default=None,
                        help="Run only nodes in this category")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load DAG and print topology, but don't execute")
    args = parser.parse_args()

    dag = load_dag(args.dag)
    scoring_config = json.loads(Path(args.scoring).read_text("utf-8"))

    print(f"Loaded DAG: {dag['meta']['total_nodes']} nodes")
    print(f"Task ID: {dag['meta']['task_id']}")

    if args.dry_run:
        from harness import topological_sort
        ordered = topological_sort(dag["nodes"])
        for i, n in enumerate(ordered):
            deps = n.get("prereqs", [])
            print(f"  [{i+1:3d}] {n['id']} (prereqs={deps})")
        print(f"\nDry run complete. {len(ordered)} nodes in topological order.")
        return

    print(f"Executing{'(LLM enabled)' if args.with_llm else ''}...")
    start = time.time()

    results = execute_dag(dag, with_llm=args.with_llm,
                          only_category=args.only_category)

    elapsed = time.time() - start
    report = aggregate_results(results, scoring_config)
    report["elapsed_seconds"] = round(elapsed, 1)
    report["dag_file"] = args.dag
    report["task_id"] = dag["meta"]["task_id"]

    print_summary(report)

    if args.output:
        out_path = args.output
    else:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(RESULTS_DIR, f"run_{ts}.json")

    detailed = {
        **report,
        "node_results": {
            nid: {
                "status": r.status,
                "score": r.score,
                "maxScore": r.maxScore,
                "category": r.category,
                "message": r.message,
                "evidence": r.evidence,
            }
            for nid, r in results.items()
        },
    }
    save_results(detailed, out_path)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
