from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_isolation_test_key_prod_submission(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "method": "GET",
            "path": "/api/submissions/{{submission_id}}",
            "headers": {
                "X-Auth-Token": "{{test_token}}"
            }
        }
        ok_0, ratio_0 = execute_primitive("P04", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P04"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "expected_status": 403
        }
        ok_1, ratio_1 = execute_primitive("P15", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P15"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "assertions": [
                {
                    "path": "$.error",
                    "op": "contains",
                    "expected": "not found using testing API key"
                }
            ]
        }
        ok_2, ratio_2 = execute_primitive("P07", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P07"] = {"passed": True, "ratio": ratio_2}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="ISOLATION_TEST_KEY_PROD_SUBMISSION",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ISOLATION_TEST_KEY_PROD_SUBMISSION",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_isolation_prod_key_test_submission(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 5
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"ta=Account.find_by(name:'TestAcct'); t=Template.first; s=Submission.create!(account:ta,template:t,source:'api',template_fields:t.fields,template_schema:t.schema,template_submitters:t.submitters); puts s.id\"",
            "expect_success": True,
            "capture_stdout_as": "test_submission_id"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "role": "admin"
        }
        ok_1, ratio_1 = execute_primitive("P13", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P13"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P13"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "method": "GET",
            "path": "/api/submissions/{{test_submission_id}}"
        }
        ok_2, ratio_2 = execute_primitive("P04", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P04"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "expected_status": 403
        }
        ok_3, ratio_3 = execute_primitive("P15", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P15"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "assertions": [
                {
                    "path": "$.error",
                    "op": "contains",
                    "expected": "not found using production API key"
                }
            ]
        }
        ok_4, ratio_4 = execute_primitive("P07", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P07"] = {"passed": True, "ratio": ratio_4}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="ISOLATION_PROD_KEY_TEST_SUBMISSION",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ISOLATION_PROD_KEY_TEST_SUBMISSION",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_isolation_test_key_prod_template(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "method": "GET",
            "path": "/api/templates/{{template_id}}",
            "headers": {
                "X-Auth-Token": "{{test_token}}"
            }
        }
        ok_0, ratio_0 = execute_primitive("P04", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P04"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "expected_status": 403
        }
        ok_1, ratio_1 = execute_primitive("P15", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P15"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "assertions": [
                {
                    "path": "$.error",
                    "op": "contains",
                    "expected": "not found using testing API key"
                }
            ]
        }
        ok_2, ratio_2 = execute_primitive("P07", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P07"] = {"passed": True, "ratio": ratio_2}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="ISOLATION_TEST_KEY_PROD_TEMPLATE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ISOLATION_TEST_KEY_PROD_TEMPLATE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_isolation_test_key_prod_submitter(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "method": "GET",
            "path": "/api/submitters/{{submitter_id}}",
            "headers": {
                "X-Auth-Token": "{{test_token}}"
            }
        }
        ok_0, ratio_0 = execute_primitive("P04", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P04"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "expected_status": 403
        }
        ok_1, ratio_1 = execute_primitive("P15", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P15"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "assertions": [
                {
                    "path": "$.error",
                    "op": "contains",
                    "expected": "not found using testing API key"
                }
            ]
        }
        ok_2, ratio_2 = execute_primitive("P07", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P07"] = {"passed": True, "ratio": ratio_2}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="ISOLATION_TEST_KEY_PROD_SUBMITTER",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ISOLATION_TEST_KEY_PROD_SUBMITTER",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "ISOLATION_TEST_KEY_PROD_SUBMISSION": test_isolation_test_key_prod_submission,
    "ISOLATION_PROD_KEY_TEST_SUBMISSION": test_isolation_prod_key_test_submission,
    "ISOLATION_TEST_KEY_PROD_TEMPLATE": test_isolation_test_key_prod_template,
    "ISOLATION_TEST_KEY_PROD_SUBMITTER": test_isolation_test_key_prod_submitter,
}
