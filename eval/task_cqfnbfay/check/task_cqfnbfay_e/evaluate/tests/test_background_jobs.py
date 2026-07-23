from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_job_sidekiq_config(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "path": "config/sidekiq.yml",
            "match_type": "contains",
            "pattern": "default"
        }
        ok_0, ratio_0 = execute_primitive("P02", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P02"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "path": "config/sidekiq.yml",
            "match_type": "contains",
            "pattern": "webhooks"
        }
        ok_1, ratio_1 = execute_primitive("P02", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P02"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "path": "config/sidekiq.yml",
            "match_type": "contains",
            "pattern": "mailers"
        }
        ok_2, ratio_2 = execute_primitive("P02", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P02"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "path": "config/sidekiq.yml",
            "match_type": "contains",
            "pattern": "images"
        }
        ok_3, ratio_3 = execute_primitive("P02", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P02"] = {"passed": True, "ratio": ratio_3}

        score = round((pass_count / 4) * 3, 2) if 4 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="JOB_SIDEKIQ_CONFIG",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="JOB_SIDEKIQ_CONFIG",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_job_completion_processing(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "role": "admin"
        }
        ok_0, ratio_0 = execute_primitive("P13", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P13"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P13"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "trigger": {
                "type": "http",
                "method": "POST",
                "path": "/api/submissions",
                "body": {
                    "template_id": "{{template_id}}",
                    "send_email": False,
                    "submitters": [
                        {
                            "role": "First Party",
                            "email": "job-test@example.com",
                            "completed": True
                        }
                    ]
                }
            },
            "verify": {
                "strategy": "db_query",
                "sql": "SELECT COUNT(*) AS cnt FROM completed_submitters cs JOIN submitters s ON s.id = cs.submitter_id WHERE s.email = 'job-test@example.com'",
                "expected_result": {
                    "cnt": 1
                },
                "max_wait_ms": 15000
            }
        }
        ok_1, ratio_1 = execute_primitive("P24", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P24"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P24"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "sql": "SELECT COUNT(*) AS cnt FROM completed_submitters cs JOIN submitters s ON s.id = cs.submitter_id WHERE s.email = 'job-test@example.com'",
            "expected_result": {
                "cnt": 1
            }
        }
        ok_2, ratio_2 = execute_primitive("P08", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P08"] = {"passed": True, "ratio": ratio_2}

        score = 5.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="JOB_COMPLETION_PROCESSING",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="JOB_COMPLETION_PROCESSING",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_job_architecture_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/jobs/",
                "config/sidekiq.yml"
            ],
            "rubric_prompt": "GOAL: Judge the structure of the background-job layer.\nEVIDENCE: code-files listing for app/jobs/** and config/sidekiq.yml (or equivalent).\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. Job classes live under app/jobs/ as separate files (one class per file).\n  C2. Queues are partitioned by concern (e.g. webhooks / mailers / images / default).\n  C3. Sidekiq async APIs (perform_async / perform_in / set(wait: ...).perform_later) are used.\n  C4. Webhook job has its own retry logic (not solely Sidekiq's default 25 retries) — e.g. exponential backoff with cap.\n  C5. >= 10 distinct Job classes exist (the system has real async work).\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C5.\n  - 2 (basic):      2 of C1-C5.\n  - 4 (good):       3 or 4 of C1-C5.\n  - 5 (excellent):  All 5 of C1-C5.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
            "score_range": [
                0,
                5
            ]
        }
        ok_0, ratio_0 = execute_primitive("P17", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P17"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P17"] = {"passed": True, "ratio": ratio_0}
            llm_score = ctx.captured.get("_llm_score", 0.0)

        score = min(llm_score, 5.0) if llm_score is not None else 0.0
        status = "PASSED" if score > 0 else "FAILED"

        return NodeResult(
            node_id="JOB_ARCHITECTURE_QUALITY",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="JOB_ARCHITECTURE_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "JOB_SIDEKIQ_CONFIG": test_job_sidekiq_config,
    "JOB_COMPLETION_PROCESSING": test_job_completion_processing,
    "JOB_ARCHITECTURE_QUALITY": test_job_architecture_quality,
}
