import argparse
import json
import os
import sys
from pathlib import Path

import config
import utils
from harness import execute_dag

def main():
    p = argparse.ArgumentParser(description="Run evaluation DAG")
    p.add_argument("--output", "-o", default=None, help="Output JSON report path")
    p.add_argument("--with-llm", action="store_true", help="Enable LLM judge nodes")
    p.add_argument("--only-category", default=None, help="Run only this category")
    p.add_argument("--dag", default=None, help="Path to DAG JSON file")
    p.add_argument("--dry-run", action="store_true", help="Load DAG only, do not execute")
    args = p.parse_args()

    eval_dir = Path(__file__).resolve().parent
    dag_path = Path(args.dag) if args.dag else eval_dir / "dag.json"
    scoring_path = eval_dir / "scoring_config.json"
    if not dag_path.exists() or not scoring_path.exists():
        print("Missing dag.json or scoring_config.json", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        from harness import load_dag, topological_sort
        dag = load_dag(str(dag_path))
        nodes = topological_sort(dag["nodes"])
        print(f"Loaded {len(nodes)} nodes")
        sys.exit(0)

    output_path = args.output or str(Path(config.RESULTS_DIR) / "report.json")
    print("Executing DAG..." + (f" (category={args.only_category})" if args.only_category else ""))
    results, scoring_config = execute_dag(str(dag_path), str(scoring_path), only_category=args.only_category)
    report = utils.save_results(results, output_path, scoring_config)
    total = report["total_score"]
    total_max = report["total_max_score"]
    pct = report["percentage"]
    print(f"Total: {total}/{total_max} ({pct}%)")
    for c in report.get("categories", []):
        print(f"  {c['category']}: {c['total_score']}/{c['max_score']}")
    print(f"Report saved to {output_path}")

if __name__ == "__main__":
    main()
