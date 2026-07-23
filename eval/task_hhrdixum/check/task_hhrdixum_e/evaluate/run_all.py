from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from evaluate import config as cfg
from evaluate.harness import (
    execute_dag,
    generate_report,
    load_dag,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="run_all", description="task_hhrdixum evaluation harness")
    p.add_argument("--dag", default=str(cfg.DAG_PATH), help="path to dag.json (default: %(default)s)")
    p.add_argument("--scoring-config", default=str(cfg.SCORING_CONFIG_PATH), help="path to scoring_config.json")
    p.add_argument("--output", default=str(cfg.RESULTS_DIR / "run.json"), help="where to write the JSON report")
    p.add_argument("--only-category", default=None, help="limit execution to a single category")
    p.add_argument("--only-node", nargs="+", default=None, help="limit execution to specific node IDs (and their prereqs)")
    p.add_argument("--dry-run", action="store_true", help="skip primitive execution; mark every reachable node PASSED")
    p.add_argument("--no-llm", action="store_true", help="treat llm-judge nodes as deterministic (no API call)")
    p.add_argument("--quiet", action="store_true", help="suppress per-node log lines")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.no_llm:
        cfg.LLM_API_KEY = ""

    if args.quiet:
        import logging
        logging.getLogger("evaluate.utils").setLevel(logging.WARNING)

    if not args.dry_run and not args.no_llm and not cfg.LLM_API_KEY:
        print("# WARNING: LLM_API_KEY is unset — every P17 (ArchitectureQuality) node",
              "         will be SKIPPED and removed from BOTH score and maxScore.",
              "         To get a complete evaluation, copy evaluate/.env.example to",
              "         evaluate/.env, set LLM_API_KEY there, then `set -a; source",
              "         evaluate/.env; set +a` before re-running.",
              sep="\n")

    dag = load_dag(Path(args.dag))
    scoring_cfg = json.loads(Path(args.scoring_config).read_text())

    print(f"# task = {dag['meta'].get('task_id')}  total_nodes = {len(dag['nodes'])}")
    print(f"# dag        = {args.dag}")
    print(f"# scoring    = {args.scoring_config}")
    print(f"# output     = {args.output}")
    if args.only_category: print(f"# only-cat   = {args.only_category}")
    if args.only_node:     print(f"# only-node  = {args.only_node}")
    if args.dry_run:       print(f"# dry-run    = True")

    only_node_with_prereqs = None
    if args.only_node:
        by_id = {n["id"]: n for n in dag["nodes"]}
        wanted = set(args.only_node)
        frontier = list(wanted)
        while frontier:
            nid = frontier.pop()
            for p in by_id.get(nid, {}).get("prereqs", []):
                if p not in wanted and p in by_id:
                    wanted.add(p); frontier.append(p)
        only_node_with_prereqs = sorted(wanted)
        print(f"# expanded   = {only_node_with_prereqs}")

    t0 = time.perf_counter()
    results = execute_dag(
        dag,
        only_category=args.only_category,
        only_node_ids=only_node_with_prereqs,
        dry_run=args.dry_run,
    )
    elapsed = time.perf_counter() - t0

    report = generate_report(results, scoring_cfg)
    report["elapsed_seconds"] = round(elapsed, 2)
    eval_root = Path(__file__).resolve().parent
    def _rel(p: str) -> str:
        try:
            return str(Path(p).resolve().relative_to(eval_root))
        except (ValueError, OSError):
            return p
    args_dict = vars(args).copy()
    for k in ("dag", "scoring_config", "output"):
        if k in args_dict and args_dict[k]:
            args_dict[k] = _rel(args_dict[k])
    report["args"] = args_dict

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    s = report["summary"]
    print()
    print("=" * 72)
    print(f"TOTAL     {s['total_score']:>8.2f} / {s['total_maxScore']:<8.0f}  ({s['total_pct']:>5.2f}%)  in {elapsed:.1f}s")
    print(f"by_status {s['node_status_counts']}")
    print()
    print("by_category:")
    for k, v in s["by_category"].items():
        print(f"  {k:30s} {v['score']:>7.2f} / {v['maxScore']:<7.0f}  ({v['pct']:>5.2f}%)  n={v['node_count']}")
    print()
    print("by_complexity_tier:")
    for k, v in s["by_complexity_tier"].items():
        print(f"  {k:25s} {v['score']:>7.2f} / {v['maxScore']:<7.0f}  ({v['pct']:>5.2f}%)  n={v['node_count']}")
    print()
    print("trajectories:")
    for k, v in s["trajectories"].items():
        print(f"  {k:25s} {v['score']:>7.2f} / {v['maxScore']:<7.0f}  ({v['pct']:>5.2f}%)  n={v['node_count']}")
    print(f"\nreport: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
