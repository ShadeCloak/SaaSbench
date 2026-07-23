import argparse
import json
import os
import sys
import time

from harness import execute_dag, aggregate_results, load_dag, load_scoring_config
from utils import print_summary
from config import RESULTS_DIR, DAG_PATH


def main() -> int:
    default_output = os.path.join(RESULTS_DIR, "eval_results.json")
    parser = argparse.ArgumentParser(description="SaaSBench DAG evaluation runner")
    parser.add_argument("-o", "--output", default=default_output, help="Output JSON path")
    parser.add_argument("--with-llm", action="store_true", help="Enable LLM judge nodes")
    parser.add_argument("--only-category", type=str, help="Run only nodes in specified category")
    parser.add_argument("--dry-run", action="store_true", help="Print execution plan without running")
    parser.add_argument("--dag", type=str, default=DAG_PATH, help="Path to dag.json")
    args = parser.parse_args()

    dag_path = args.dag
    output_path = args.output
    if not os.path.isabs(output_path):
        base = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.normpath(os.path.join(base, output_path))

    dag = load_dag(dag_path)
    scoring_config = load_scoring_config()

    nodes = dag.get("nodes", [])
    categories = set()
    for n in nodes:
        cat = n.get("scoring", {}).get("category")
        if cat:
            categories.add(cat)

    print(f"DAG loaded: {len(nodes)} nodes, categories: {sorted(categories)}")

    start = time.perf_counter()
    results = execute_dag(
        dag,
        scoring_config,
        only_category=args.only_category,
        dry_run=args.dry_run,
        with_llm=args.with_llm,
    )
    elapsed = time.perf_counter() - start

    print(f"Execution completed in {elapsed:.2f}s")

    aggregated = aggregate_results(results, scoring_config, dag)
    print_summary(results)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(aggregated, f, indent=2)

    print(f"\nResults saved to {output_path}")
    print(f"Total: {aggregated['total_score']}/{aggregated['total_max_score']} ({aggregated['percentage']}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
