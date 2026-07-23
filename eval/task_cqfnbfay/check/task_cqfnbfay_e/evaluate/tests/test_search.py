from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_search_template_by_name(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 5
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"SearchEntries.enqueue_reindex(Template.all); sleep 2\"",
            "expect_success": True
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "path": "/api/templates",
            "method": "GET",
            "params": {
                "q": "Eval"
            },
            "token": "{{admin_token}}",
            "expected_results": {
                "min_count": 1,
                "first_result_contains": "Eval"
            }
        }
        ok_2, ratio_2 = execute_primitive("P26", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P26"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P26"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "assertions": [
                {
                    "path": "$.data[0].name",
                    "op": "contains",
                    "expected": "Eval"
                },
                {
                    "path": "$.pagination.count",
                    "op": ">=",
                    "expected": 1
                }
            ]
        }
        ok_3, ratio_3 = execute_primitive("P07", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P07"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "sql": "SELECT COUNT(*) AS cnt FROM search_entries WHERE record_type = 'Template'",
            "expected_result": {
                "cnt": {
                    "op": ">=",
                    "value": 1
                }
            }
        }
        ok_4, ratio_4 = execute_primitive("P08", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P08"] = {"passed": True, "ratio": ratio_4}

        score = round((pass_count / 5) * 4, 2) if 5 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="SEARCH_TEMPLATE_BY_NAME",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="SEARCH_TEMPLATE_BY_NAME",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_search_submitter_by_email(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"SearchEntries.enqueue_reindex(Submitter.all); sleep 2\"",
            "expect_success": True
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "path": "/api/submitters",
            "method": "GET",
            "params": {
                "q": "john.doe"
            },
            "token": "{{admin_token}}",
            "expected_results": {
                "min_count": 1,
                "first_result_contains": "john.doe"
            }
        }
        ok_2, ratio_2 = execute_primitive("P26", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P26"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P26"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "assertions": [
                {
                    "path": "$.data[0].email",
                    "op": "contains",
                    "expected": "john.doe"
                }
            ]
        }
        ok_3, ratio_3 = execute_primitive("P07", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P07"] = {"passed": True, "ratio": ratio_3}

        score = round((pass_count / 4) * 3, 2) if 4 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="SEARCH_SUBMITTER_BY_EMAIL",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="SEARCH_SUBMITTER_BY_EMAIL",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_search_implementation_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/models/search_entry.rb",
                "app/models/concerns/",
                "db/"
            ],
            "rubric_prompt": "GOAL: Judge the maturity of the full-text-search implementation.\nEVIDENCE: code-files listing for app/models/search_entry*, db/migrate/*search*, lib/tasks/search*.\nSCORE RANGE: 0-4\n\nCRITERIA:\n  C1. A SearchEntry (or equivalent) model exists, bridging searchable records.\n  C2. PostgreSQL tsvector and/or pg_trgm/ngram indexes are used.\n  C3. A GIN index backs the search column.\n  C4. The search engine indexes >= 3 distinct record_types (e.g. Template, Submission, Submitter).\n\nSCORING ANCHORS:\n  - 0 (none):       0 or 1 of C1-C4.\n  - 1 (basic):      2 of C1-C4.\n  - 3 (good):       3 of C1-C4.\n  - 4 (excellent):  All 4 of C1-C4.\n\nOUTPUT: {\"score\": <0..4>, \"reasoning\": \"<1-3 sentences referencing C1..C4>\"}",
            "score_range": [
                0,
                4
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

        score = min(llm_score, 4.0) if llm_score is not None else 0.0
        status = "PASSED" if score > 0 else "FAILED"

        return NodeResult(
            node_id="SEARCH_IMPLEMENTATION_QUALITY",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="SEARCH_IMPLEMENTATION_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "SEARCH_TEMPLATE_BY_NAME": test_search_template_by_name,
    "SEARCH_SUBMITTER_BY_EMAIL": test_search_submitter_by_email,
    "SEARCH_IMPLEMENTATION_QUALITY": test_search_implementation_quality,
}
