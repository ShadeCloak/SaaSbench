#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import config
import harness
import utils

log = utils.log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LMS evaluation harness")
    ap.add_argument("--dag", default=None, help="alternate dag.json path")
    ap.add_argument("--output", "-o", default=None, help="output report JSON path")
    ap.add_argument("--category", "-c", action="append", default=[],
                     help="filter to one or more categories (repeat for multi)")
    ap.add_argument("--node", "-n", action="append", default=[],
                     help="filter to specific node IDs (repeat for multi)")
    ap.add_argument("--stop-on-failure", action="store_true",
                     help="halt execution at first FAILED/ERROR node")
    ap.add_argument("--list-nodes", action="store_true",
                     help="print all node IDs grouped by category and exit")
    ap.add_argument("--quiet", "-q", action="store_true",
                     help="reduce log verbosity to WARNING")
    ap.add_argument("--verbose", "-v", action="store_true",
                     help="increase log verbosity to DEBUG")
    ap.add_argument("--no-llm", action="store_true",
                     help="skip llm-judge nodes (saves API cost in CI)")
    ap.add_argument("--dry-run", action="store_true",
                     help="print planned executions without running primitives")
    args = ap.parse_args(argv)

    if args.quiet:
        log.setLevel("WARNING")
    elif args.verbose:
        log.setLevel("DEBUG")

    if args.dag:
        config.DAG_FILE = Path(args.dag)
        log.info(f"Using DAG: {config.DAG_FILE}")

    if args.list_nodes:
        dag = utils.load_dag()
        from collections import defaultdict
        by_cat = defaultdict(list)
        for n in dag["nodes"]:
            by_cat[n["scoring"]["category"]].append(n["id"])
        for cat in sorted(by_cat):
            print(f"\n=== {cat} ({len(by_cat[cat])} nodes) ===")
            for nid in sorted(by_cat[cat]):
                print(f"  {nid}")
        return 0

    log.info("=" * 60)
    log.info(f"Starting evaluation harness")
    log.info(f"  DAG file:        {config.DAG_FILE}")
    log.info(f"  API base URL:    {config.API_BASE_URL}")
    log.info(f"  DB:              {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
    log.info(f"  Filter category: {args.category or 'ALL'}")
    log.info(f"  Filter nodes:    {args.node or 'ALL'}")
    log.info("=" * 60)

    report = harness.execute_dag(
        filter_categories=set(args.category) if args.category else None,
        only_node_ids=set(args.node) if args.node else None,
        stop_on_first_failure=args.stop_on_failure,
        with_llm=not args.no_llm,
        dry_run=args.dry_run,
    )

    output_path = Path(args.output) if args.output else (config.RESULTS_DIR / "latest.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    log.info(f"Report written → {output_path}")

    print()
    print("=" * 60)
    print(f"FINAL SCORE: {report['total_score']}/{report['max_total_score']} ({report['percentage']}%)")
    print("=" * 60)
    print(f"Counts: {report['summary_counts']}")
    print(f"Trajectories:")
    for tname, t in report.get("trajectories", {}).items():
        print(f"  {tname}: {t['score']}/{t['max_score']} ({t['ratio']*100:.1f}%, {t['node_count']} nodes)")
    print(f"\nCategories:")
    for c in report["categories"]:
        print(f"  {c['category']:25s} {c['score']:7.1f}/{c['max_score']:7.1f}  "
              f"P:{c['passed']:3d} PA:{c['partial']:3d} F:{c['failed']:3d} "
              f"S:{c['skipped']:3d} E:{c['error']:3d}")

    return 0 if report["percentage"] > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
