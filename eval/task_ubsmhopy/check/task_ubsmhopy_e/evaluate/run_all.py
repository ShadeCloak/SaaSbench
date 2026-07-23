#!/usr/bin/env python3
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness
import utils


def main():
    parser = argparse.ArgumentParser(description="Run evaluation DAG")
    parser.add_argument("--dag", default="dag.json", help="Path to DAG JSON file")
    parser.add_argument("--output", default="results/eval_result.json", help="Output report path")
    parser.add_argument("--wait", type=int, default=60, help="Seconds to wait for app startup")
    parser.add_argument("--help-nodes", action="store_true", help="List all DAG nodes")
    args = parser.parse_args()

    if args.help_nodes:
        import json
        dag = harness.load_dag(args.dag)
        for n in dag["nodes"]:
            print(f"  {n['id']}: {n['description']} [{n['scoring']['category']}] {n['scoring']['maxScore']}pts")
        return

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    print(f"Waiting for app at {utils.config.BASE_URL} (max {args.wait}s)...")
    if not utils.wait_for_app(args.wait):
        print("ERROR: App not responding. Proceeding anyway (nodes will fail).")

    report = harness.run_dag(args.dag, args.output)
    sys.exit(0 if report["percentage"] > 0 else 1)


if __name__ == "__main__":
    main()
