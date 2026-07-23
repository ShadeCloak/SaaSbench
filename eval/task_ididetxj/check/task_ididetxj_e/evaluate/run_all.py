#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config
from harness import execute_dag, load_dag
from utils import save_results, log, fmt_result


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the SaaSBench DAG evaluation.")
    ap.add_argument("--output", "-o", default=None, help="Output JSON path (default: results/<ts>.json)")
    ap.add_argument("--only-category", default=None, help="Run only nodes in this category")
    ap.add_argument("--dry-run", action="store_true", help="Skip primitive execution; report all PASS")
    ap.add_argument("--dag", default=str(HERE / "dag.json"), help="Path to dag.json")
    args = ap.parse_args()

    dag = load_dag(args.dag)
    log.info("Loaded DAG: %d nodes", dag["meta"]["total_nodes"])

    results, agg = execute_dag(dag, only_category=args.only_category, dry_run=args.dry_run)

    if not args.output:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        args.output = str(config.RESULTS_DIR / f"run_{ts}.json")

    save_results(results, args.output)
    agg_path = Path(args.output).with_suffix(".summary.json")
    with open(agg_path, "w") as f:
        json.dump({"aggregate": agg, "results_file": args.output,
                    "ts": datetime.datetime.utcnow().isoformat() + "Z"}, f, indent=2)

    print()
    print("=" * 80)
    print(f"AGGREGATE  total = {agg['total_score']} / {agg['total_maxScore']}  ({agg['percentage']:.1f}%)")
    print(f"  status: {agg['by_status']}")
    print()
    print(f"{'Category':30s} {'Score':>10s} {'/Max':>6s} {'%':>6s} {'PASS':>5s} {'FAIL':>5s} {'SKIP':>5s}")
    print("-" * 80)
    for cat, d in sorted(agg["by_category"].items(), key=lambda x: -x[1]["maxScore"]):
        pct = d["score"] / d["maxScore"] * 100 if d["maxScore"] else 0
        print(f"{cat:30s} {d['score']:>10.1f} {d['maxScore']:>6.0f} {pct:>5.1f}% {d['n_passed']:>5d} {d['n_failed']:>5d} {d['n_skipped']:>5d}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
