#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from harness import load_dag, load_scoring_config, run_dag
from utils import wait_for_service


def main():
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument("--dag", default=config.DAG_PATH, help="Path to dag.json")
    parser.add_argument("--scoring", default=config.SCORING_CONFIG_PATH,
                        help="Path to scoring_config.json")
    parser.add_argument("--output", default=os.path.join(config.RESULTS_DIR, "report.json"),
                        help="Output report path")
    parser.add_argument("--wait", type=int, default=120,
                        help="Seconds to wait for app health endpoint")
    parser.add_argument("--skip-wait", action="store_true",
                        help="Skip waiting for the application")
    parser.add_argument("--help-nodes", action="store_true",
                        help="List all DAG node IDs and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("eval")

    dag = load_dag(args.dag)
    scoring_config = load_scoring_config(args.scoring)

    if args.help_nodes:
        for n in dag.get("nodes", []):
            print(f"  {n['id']:45s} {n['scoring']['category']:25s} max={n['scoring']['maxScore']}")
        return

    if not args.skip_wait:
        logger.info("Waiting for application at %s …", config.HEALTH_ENDPOINT)
        if not wait_for_service(config.HEALTH_ENDPOINT, max_wait=args.wait):
            logger.error("Application not reachable after %ds — aborting.", args.wait)
            sys.exit(1)
        logger.info("Application is ready.")

    try:
        import primitives
        primitives.p13_auth_login({"role": "admin"}, {})
        for user_id, display, email in (
            ("admin", "Eval Admin", "admin@eval.test"),
            ("editor", "Eval Editor", "editor@eval.test"),
            ("reader", "Eval Reader", "reader@eval.test"),
        ):
            urn = f"urn:li:corpuser:{user_id}"
            aspect = (
                '{"active":true,"displayName":"' + display + '",'
                '"email":"' + email + '","title":"Eval","fullName":"' + display + '"}'
            )
            try:
                primitives.p_ingest_proposal({
                    "entityType": "corpuser",
                    "entityUrn": urn,
                    "aspectName": "corpUserInfo",
                    "changeType": "UPSERT",
                    "aspectValue": aspect,
                }, {})
            except Exception as exc:
                logger.warning("Bootstrap %s failed: %s", urn, exc)
        import time as _t; _t.sleep(12)
        logger.info("Bootstrapped corpuser entities (admin/editor/reader).")
    except Exception as exc:
        logger.warning("Bootstrap step skipped (will rely on dag setup): %s", exc)

    report = run_dag(dag, scoring_config)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    pct = report["percentage"]
    logger.info("=" * 60)
    logger.info("TOTAL: %.1f / %.1f  (%.1f%%)", report["total_score"],
                report["total_max_score"], pct)
    for cat in report.get("categories", []):
        logger.info("  %-25s %6.1f / %6.1f  (%5.1f%%)",
                     cat["category"], cat["total_score"], cat["max_score"], cat["percentage"])
    logger.info("=" * 60)
    logger.info("Report written to %s", args.output)


if __name__ == "__main__":
    main()
