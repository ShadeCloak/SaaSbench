#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

if __name__ == "__main__" and __package__ in (None, ""):
    _here = Path(__file__).resolve().parent
    sys.path.insert(0, str(_here.parent))
    __package__ = _here.name

from . import config
from .harness import (
    aggregate_results, execute_dag, load_dag, load_scoring_config, topological_sort,
)
from .utils import NodeResult, logger, print_result, save_results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PFM DAG evaluator")
    parser.add_argument("--output", type=str, default=None, help="JSON report path")
    parser.add_argument("--only-category", type=str, default=None)
    parser.add_argument("--only-trajectory", type=str, default=None,
                        choices=["happy_path", "advanced_workflows", None])
    parser.add_argument("--skip", type=str, default="", help="comma-separated node IDs to skip")
    parser.add_argument("--dag", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.verbose:
        import logging
        logger.setLevel(logging.DEBUG)

    dag = load_dag(args.dag)
    sc = load_scoring_config()

    print(f"PFM DAG evaluator — {len(dag['nodes'])} nodes total, "
          f"{sum(n['scoring']['maxScore'] for n in dag['nodes'])} maxScore")
    print(f"  APP_BASE_URL    = {config.APP_BASE_URL}")
    print(f"  DB_HOST:PORT    = {config.DB_HOST}:{config.DB_PORT}")
    print(f"  APP_CONTAINER   = {config.APP_CONTAINER}")
    if args.only_category:
        print(f"  FILTER category = {args.only_category}")
    if args.only_trajectory:
        print(f"  FILTER traj     = {args.only_trajectory}")

    if args.dry_run:
        ordered = topological_sort(dag["nodes"])
        print(f"\nWould execute {len(ordered)} nodes in topological order:")
        for n in ordered:
            print(f"  {n['id']:<45} {n['scoring']['category']:<30} maxScore={n['scoring']['maxScore']}")
        return 0

    start = time.time()
    skip_ids = {s.strip() for s in args.skip.split(",") if s.strip()}
    results: list[NodeResult] = execute_dag(
        dag,
        only_category=args.only_category,
        only_trajectory=args.only_trajectory,
        scoring_config=sc,
        skip_nodes=skip_ids,
    )
    elapsed = int(time.time() - start)

    print("\n=== Per-node results ===")
    for r in results:
        print_result(r)

    summary = aggregate_results(results, sc)
    print("\n=== Summary ===")
    print(f"  Total:           {summary['total_score']:.2f} / {summary['max_score']:.2f}   ({summary['percentage']:.2f}%)")
    print(f"  Nodes:           {summary['node_count']}")
    print(f"  Elapsed:         {elapsed}s")
    print(f"  Status counts:   {summary['status_counts']}")
    print("\n  Categories:")
    for cat in sorted(summary["categories"]):
        s = summary["categories"][cat]
        print(f"    {cat:<32} {s['score']:>6.2f}/{s['maxScore']:<6}  ({s['percent']:>5.1f}%)   nodes={s['nodes']}")
    print("\n  Trajectories:")
    for traj, s in summary["trajectories"].items():
        print(f"    {traj:<22} {s['score']:>6.2f}/{s['maxScore']:<6}  ({s['percent']:>5.1f}%)   nodes={s['node_count']}")

    out_path = args.output or (config.RESULTS_DIR / f"run_{time.strftime('%Y%m%d_%H%M%S')}.json")
    save_results(results, out_path)
    with open(out_path, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data["summary"] = summary
        data["elapsed_seconds"] = elapsed
        f.seek(0)
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.truncate()

    return 0 if summary["percentage"] >= 50 else 1


if __name__ == "__main__":
    sys.exit(main())
