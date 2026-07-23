#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(THIS_DIR.parent))

from evaluate import config, harness
from evaluate.utils import save_results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument("--output", default=None,
                          help="Output JSON path (default: results/run_<ts>.json)")
    parser.add_argument("--only-category", default=None,
                          help="Only run nodes in this category")
    parser.add_argument("--only-node", action="append", default=None,
                          help="Restrict to one or more node IDs")
    parser.add_argument("--dag", default=None,
                          help="Path to DAG JSON (default: dag.json)")
    parser.add_argument("--dry-run", action="store_true",
                          help="Skip primitive execution, score everything as max")
    parser.add_argument("--with-llm", action="store_true",
                          help="Include LLM-judge nodes (calls the LLM API). "
                                "When omitted, LLM-judge nodes are excluded from the "
                                "scored total entirely.")
    args = parser.parse_args()

    dag_path = Path(args.dag) if args.dag else config.DAG_PATH
    print(f"Loading DAG: {dag_path}")
    dag = harness.load_dag(dag_path)
    print(f"  {len(dag['nodes'])} nodes / "
          f"total maxScore = {sum(n['scoring']['maxScore'] for n in dag['nodes'])}")

    if not args.with_llm:
        before = len(dag["nodes"])
        llm_ids = {n["id"] for n in dag["nodes"]
                    if n["scoring"]["method"] == "llm-judge"}
        dag["nodes"] = [n for n in dag["nodes"] if n["id"] not in llm_ids]
        for n in dag["nodes"]:
            if n.get("prereqs"):
                n["prereqs"] = [p for p in n["prereqs"] if p not in llm_ids]
        print(f"  --with-llm not set: dropped {before - len(dag['nodes'])} llm-judge nodes "
              f"and stripped them from {len(llm_ids)} prereq references")
    print()

    t0 = time.time()
    results = harness.execute_dag(
        dag,
        only_category=args.only_category,
        only_node_ids=set(args.only_node) if args.only_node else None,
        dry_run=args.dry_run,
    )
    elapsed = time.time() - t0

    summary = harness.aggregate(results)
    summary["elapsed_seconds"] = round(elapsed, 1)
    summary["dag_path"] = str(dag_path)
    summary["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    summary["dry_run"] = args.dry_run
    summary["only_category"] = args.only_category
    summary["only_node"] = args.only_node

    print()
    print("=" * 70)
    print("=== Results summary ===")
    print(f"Total: {summary['total_score']}/{summary['total_max']}  "
          f"({summary['percentage']}%)  in {elapsed:.1f}s")
    print(f"Nodes: {summary['executed']} executed, {summary['skipped']} skipped, "
          f"{summary['node_count'] - summary['executed'] - summary['skipped']} other")
    print()
    print("By category:")
    for cat, info in summary["category_breakdown"].items():
        print(f"  {cat:25s} {info['score']:>6.1f}/{info['max']:<5.1f}  "
              f"({info['pct']:>5.1f}%)  [{info['executed']}/{info['node_count']} executed]")
    print("=" * 70)

    out_path = (Path(args.output) if args.output
                else config.RESULTS_DIR / f"run_{int(time.time())}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_results(results, out_path)
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"\nWrote per-node results to: {out_path}")
    print(f"Wrote summary to:           {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
