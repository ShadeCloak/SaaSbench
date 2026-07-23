#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import config
import harness
from utils import save_results, print_result


def main():
    parser = argparse.ArgumentParser(description="task_sgdoserd evaluator")
    parser.add_argument("--output", default=None, help="Output JSON path (default: results/run_<ts>.json)")
    parser.add_argument("--with-llm", action="store_true", help="Enable P17 llm-judge nodes (requires LLM_API_KEY)")
    parser.add_argument("--only-category", default=None, help="Only run nodes in this category")
    parser.add_argument("--only-nodes", default=None, help="Comma-separated node IDs to run")
    parser.add_argument("--dry-run", action="store_true", help="Skip primitives; report what would run")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-node output")
    parser.add_argument("--dag", default=None, help="Path to alternate dag.json (e.g., dag_baseline.json)")
    args = parser.parse_args()

    eval_dir = Path(__file__).resolve().parent
    dag_path = Path(args.dag) if args.dag else (eval_dir / "dag.json")
    if not dag_path.is_absolute():
        dag_path = (eval_dir / dag_path).resolve()
    sc_path = eval_dir / "scoring_config.json"

    print(f"Loading DAG from {dag_path}", file=sys.stderr)
    dag = json.loads(dag_path.read_text())
    sc = json.loads(sc_path.read_text())

    only_nodes = None
    if args.only_nodes:
        only_nodes = [s.strip() for s in args.only_nodes.split(",") if s.strip()]

    print(f"Executing {len(dag['nodes'])} nodes (with_llm={args.with_llm}, "
          f"only_category={args.only_category}, dry_run={args.dry_run})", file=sys.stderr)

    results = harness.execute_dag(dag, sc,
                                    only_category=args.only_category,
                                    with_llm=args.with_llm,
                                    dry_run=args.dry_run,
                                    only_nodes=only_nodes)

    if not args.quiet:
        print(file=sys.stderr)
        for r in results:
            print_result(r)

    summary = harness.aggregate_results(results, sc)

    print(file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"TOTAL: {summary['total_score']:.1f} / {summary['total_max']} = {summary['percentage']:.1f}%",
          file=sys.stderr)
    print(f"Status counts: {summary['status_counts']}", file=sys.stderr)
    print(f"Trajectories: happy_path={summary['trajectories']['happy_path']['pct']:.1f}%, "
          f"advanced_workflows={summary['trajectories']['advanced_workflows']['pct']:.1f}%",
          file=sys.stderr)
    print("Categories:", file=sys.stderr)
    for cat, info in sorted(summary["categories"].items(), key=lambda x: -x[1]["score"]):
        print(f"  {cat:30s} {info['score']:>6.1f}/{info['max']:<5} ({info['pct']:.1f}%) "
              f"— {info['passed']}/{info['node_count']} passed", file=sys.stderr)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.output) if args.output else config.RESULTS_DIR / f"run_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    full = {
        "task_id": "task_sgdoserd",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "args": vars(args),
        "summary": summary,
        "results": [r.to_dict() for r in results],
    }
    out_path.write_text(json.dumps(full, ensure_ascii=False, indent=2))
    print(f"\nReport saved to {out_path}", file=sys.stderr)
    return 0 if summary["status_counts"].get("ERROR", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
