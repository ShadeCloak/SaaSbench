#!/usr/bin/env python3
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import DAG_PATH, SCORING_CONFIG_PATH, RESULTS_DIR
from harness import load_dag, load_scoring_config, execute_dag, aggregate_results
from utils import save_results, print_summary


def main():
    parser = argparse.ArgumentParser(description="Video Conferencing Platform Evaluation")
    parser.add_argument("--dag", default=DAG_PATH, help="Path to dag.json")
    parser.add_argument("--scoring-config", default=SCORING_CONFIG_PATH, help="Path to scoring_config.json")
    parser.add_argument("--output", default=os.path.join(RESULTS_DIR, "results.json"), help="Output results path")
    parser.add_argument("--with-llm", action="store_true", help="Enable LLM-judge scoring")
    parser.add_argument("--only-category", type=str, default=None, help="Run only nodes in this category")
    parser.add_argument("--dry-run", action="store_true", help="Show execution plan without running")
    args = parser.parse_args()

    if not args.with_llm and "SKIP_LLM_JUDGE" not in os.environ:
        os.environ["SKIP_LLM_JUDGE"] = "1"

    dag = load_dag(args.dag)
    scoring_config = load_scoring_config(args.scoring_config)

    if args.only_category:
        dag["nodes"] = [n for n in dag["nodes"] if n["scoring"]["category"] == args.only_category]

    if args.dry_run:
        print(f"DAG: {len(dag['nodes'])} nodes")
        for n in dag["nodes"]:
            deps = ", ".join(n.get("prereqs", [])) or "(root)"
            primitives = " → ".join(p["type"] for p in n["primitive_chain"])
            print(f"  {n['id']:40s} [{n['scoring']['category']:20s}] {primitives} (max={n['scoring']['maxScore']}) deps=[{deps}]")
        return

    budget = dag.get("meta", {}).get("score_budget", {})
    print(f"Running evaluation: {len(dag['nodes'])} nodes, {budget.get('total', '?')} total points")
    print(f"Depth distribution: shallow={budget.get('shallow_pct', '?')}% deep={budget.get('deep_pct', '?')}% llm={budget.get('llm_judge_pct', '?')}%")
    print()

    results = execute_dag(dag, scoring_config)
    report = aggregate_results(results, scoring_config)

    print_summary(results, scoring_config)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    save_results(results, os.path.basename(args.output))

    report_path = os.path.join(os.path.dirname(args.output), "report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"Results saved to: {args.output}")
    print(f"Report saved to: {report_path}")
    print(f"Normalized score: {report['normalized_score']}/100")

    return report["normalized_score"]


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
