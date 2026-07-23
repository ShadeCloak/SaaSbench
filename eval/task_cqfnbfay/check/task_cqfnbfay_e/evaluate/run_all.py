#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from harness import run_evaluation


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SignPlatform evaluation harness — runs DAG-driven tests and produces a scored report."
    )
    parser.add_argument(
        "--dag", default=None,
        help=f"Path to DAG JSON file (default: {config.DAG_PATH})",
    )
    parser.add_argument(
        "--scoring-config", default=None,
        help=f"Path to scoring config JSON (default: {config.SCORING_CONFIG_PATH})",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output file path for results JSON (default: results/eval_results.json)",
    )
    parser.add_argument(
        "--category", "-c", action="append", default=None,
        help="Filter by category (can be specified multiple times)",
    )
    parser.add_argument(
        "--node", "-n", action="append", default=None,
        help="Filter by node ID (can be specified multiple times)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Load and validate the DAG without executing tests",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.dry_run:
        from harness import load_dag, load_scoring_config, topological_sort
        dag = load_dag(args.dag)
        cfg = load_scoring_config(args.scoring_config)
        nodes = dag["nodes"]
        ordered = topological_sort(nodes)
        print(f"DAG loaded: {len(nodes)} nodes, {len(cfg.get('categories', {}))} categories")
        print(f"Topological order validated: {len(ordered)} nodes reachable")
        total = sum(n["scoring"]["maxScore"] for n in nodes)
        print(f"Total maxScore: {total}")
        return

    report = run_evaluation(
        dag_path=args.dag,
        scoring_path=args.scoring_config,
        node_filter=args.node,
        category_filter=args.category,
    )

    output_path = args.output
    if not output_path:
        os.makedirs(config.RESULTS_DIR, exist_ok=True)
        output_path = os.path.join(config.RESULTS_DIR, "eval_results.json")

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"  Evaluation Complete")
    print(f"{'='*60}")
    print(f"  Score:    {s['total_score']:.1f} / {s['total_maxScore']:.1f}  ({s['normalized_score']:.1f}%)")
    print(f"  Passed:   {s['passed']}")
    print(f"  Failed:   {s['failed']}")
    print(f"  Skipped:  {s['skipped']}")
    print(f"  Errors:   {s['errors']}")
    print(f"  Elapsed:  {s['elapsed_seconds']:.1f}s")
    print(f"  Results:  {output_path}")
    print(f"{'='*60}\n")

    cat_scores = report.get("categories", {})
    if cat_scores:
        print(f"  {'Category':<30} {'Score':>8} {'Max':>8} {'%':>7}")
        print(f"  {'-'*55}")
        for cat in sorted(cat_scores.keys()):
            cs = cat_scores[cat]
            pct = (cs['score'] / cs['maxScore'] * 100) if cs['maxScore'] > 0 else 0
            print(f"  {cat:<30} {cs['score']:>8.1f} {cs['maxScore']:>8.1f} {pct:>6.1f}%")
        print()


if __name__ == "__main__":
    main()
