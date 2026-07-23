from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_api_events_form_completed(ctx: EvalContext) -> NodeResult:
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
            "method": "GET",
            "path": "/api/events/form/completed"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "expected_status": 200
        }
        ok_2, ratio_2 = execute_primitive("P15", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P15"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "required_fields": [
                "data",
                "pagination"
            ]
        }
        ok_3, ratio_3 = execute_primitive("P06", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P06"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P06"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "assertions": [
                {
                    "path": "$.data[0].event_type",
                    "expected": "form.completed"
                },
                {
                    "path": "$.data[0].timestamp",
                    "op": "not_null"
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
            node_id="API_EVENTS_FORM_COMPLETED",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_EVENTS_FORM_COMPLETED",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_events_submission_created(ctx: EvalContext) -> NodeResult:
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
            "method": "GET",
            "path": "/api/events/submission/created"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "expected_status": 200
        }
        ok_2, ratio_2 = execute_primitive("P15", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P15"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "required_fields": [
                "data",
                "pagination"
            ]
        }
        ok_3, ratio_3 = execute_primitive("P06", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P06"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P06"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "assertions": [
                {
                    "path": "$.pagination.count",
                    "op": ">=",
                    "expected": 1
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_EVENTS_SUBMISSION_CREATED",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_EVENTS_SUBMISSION_CREATED",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_events_timestamp_pagination(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 7
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
            "method": "GET",
            "path": "/api/events/form/completed?limit=1",
            "capture_response_as": "evt_page1"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "expected_status": 200
        }
        ok_2, ratio_2 = execute_primitive("P15", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P15"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "response": "{{evt_page1}}",
            "assertions": [
                {
                    "path": "$.pagination.next",
                    "op": "not_null",
                    "capture_as": "evt_next"
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
            "method": "GET",
            "path": "/api/events/form/completed?after={{evt_next}}"
        }
        ok_4, ratio_4 = execute_primitive("P04", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P04"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "expected_status": 200
        }
        ok_5, ratio_5 = execute_primitive("P15", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P15"] = {"passed": True, "ratio": ratio_5}

        inputs_6 = {
            "required_fields": [
                "data",
                "pagination"
            ]
        }
        ok_6, ratio_6 = execute_primitive("P06", inputs_6, ctx)
        if not ok_6:
            chain_pass = False
            evidence["step_6_P06"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_6_P06"] = {"passed": True, "ratio": ratio_6}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_EVENTS_TIMESTAMP_PAGINATION",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_EVENTS_TIMESTAMP_PAGINATION",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "API_EVENTS_FORM_COMPLETED": test_api_events_form_completed,
    "API_EVENTS_SUBMISSION_CREATED": test_api_events_submission_created,
    "API_EVENTS_TIMESTAMP_PAGINATION": test_api_events_timestamp_pagination,
}
