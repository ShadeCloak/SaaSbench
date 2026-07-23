from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_api_submitter_list(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/submitters"
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
                    "path": "$.data[0].role",
                    "op": "not_null"
                },
                {
                    "path": "$.data[0].email",
                    "op": "not_null"
                },
                {
                    "path": "$.data[0].status",
                    "op": "in",
                    "expected": [
                        "awaiting",
                        "completed",
                        "declined",
                        "opened",
                        "sent",
                        "awaiting"
                    ]
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

        score = round((pass_count / 5) * 3, 2) if 5 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="API_SUBMITTER_LIST",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_LIST",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_show(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/submitters/{{submitter_id}}"
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
                "id",
                "submission_id",
                "uuid",
                "email",
                "status",
                "slug",
                "role",
                "template",
                "values",
                "documents"
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
                    "path": "$.email",
                    "expected": "john.doe@example.com"
                },
                {
                    "path": "$.role",
                    "expected": "First Party"
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
            node_id="API_SUBMITTER_SHOW",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_SHOW",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_update(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 6
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
            "method": "PUT",
            "path": "/api/submitters/{{submitter_id}}",
            "body": {
                "email": "john.doe+updated@example.com"
            }
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
            "assertions": [
                {
                    "path": "$.email",
                    "expected": "john.doe+updated@example.com"
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
            "required_fields": [
                "embed_src"
            ]
        }
        ok_4, ratio_4 = execute_primitive("P06", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P06"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P06"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "method": "PUT",
            "path": "/api/submitters/{{submitter_id}}",
            "body": {
                "email": "john.doe@example.com"
            }
        }
        ok_5, ratio_5 = execute_primitive("P04", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P04"] = {"passed": True, "ratio": ratio_5}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMITTER_UPDATE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_UPDATE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_values(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 6
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
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "values-test@example.com"
                    }
                ]
            },
            "capture_response_as": "val_create_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{val_create_resp}}",
            "assertions": [
                {
                    "path": "$[0].id",
                    "op": "not_null",
                    "capture_as": "val_submitter_id"
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

        inputs_3 = {
            "method": "PUT",
            "path": "/api/submitters/{{val_submitter_id}}",
            "body": {
                "values": {
                    "Full Name": "John Doe"
                }
            }
        }
        ok_3, ratio_3 = execute_primitive("P04", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P04"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "expected_status": 200
        }
        ok_4, ratio_4 = execute_primitive("P15", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P15"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "assertions": [
                {
                    "path": "$.values",
                    "op": "not_null"
                }
            ]
        }
        ok_5, ratio_5 = execute_primitive("P07", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P07"] = {"passed": True, "ratio": ratio_5}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMITTER_VALUES",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_VALUES",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_phone_normalize(ctx: EvalContext) -> NodeResult:
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
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "phone-test@example.com",
                        "phone": "+12345678900"
                    }
                ]
            },
            "capture_response_as": "phone_resp"
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
            "response": "{{phone_resp}}",
            "assertions": [
                {
                    "path": "$[0].phone",
                    "expected": "+12345678900"
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMITTER_PHONE_NORMALIZE",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_PHONE_NORMALIZE",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_complete(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 6
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
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "complete-test@example.com"
                    }
                ]
            },
            "capture_response_as": "comp_create_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{comp_create_resp}}",
            "assertions": [
                {
                    "path": "$[0].id",
                    "op": "not_null",
                    "capture_as": "comp_submitter_id"
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

        inputs_3 = {
            "method": "PUT",
            "path": "/api/submitters/{{comp_submitter_id}}",
            "body": {
                "completed": True
            }
        }
        ok_3, ratio_3 = execute_primitive("P04", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P04"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "expected_status": 200
        }
        ok_4, ratio_4 = execute_primitive("P15", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P15"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "assertions": [
                {
                    "path": "$.status",
                    "expected": "completed"
                },
                {
                    "path": "$.completed_at",
                    "op": "not_null"
                }
            ]
        }
        ok_5, ratio_5 = execute_primitive("P07", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P07"] = {"passed": True, "ratio": ratio_5}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMITTER_COMPLETE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_COMPLETE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_decline(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 6
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
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "decline-test@example.com"
                    }
                ]
            },
            "capture_response_as": "dec_create_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{dec_create_resp}}",
            "assertions": [
                {
                    "path": "$[0].id",
                    "op": "not_null",
                    "capture_as": "dec_submitter_id"
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

        inputs_3 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"s=Submitter.find({{dec_submitter_id}}); s.update!(declined_at: Time.current); puts s.reload.declined_at\"",
            "expect_success": True
        }
        ok_3, ratio_3 = execute_primitive("P12", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P12"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "method": "GET",
            "path": "/api/submitters/{{dec_submitter_id}}"
        }
        ok_4, ratio_4 = execute_primitive("P04", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P04"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "assertions": [
                {
                    "path": "$.status",
                    "expected": "declined"
                },
                {
                    "path": "$.declined_at",
                    "op": "not_null"
                }
            ]
        }
        ok_5, ratio_5 = execute_primitive("P07", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P07"] = {"passed": True, "ratio": ratio_5}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMITTER_DECLINE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_DECLINE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_complete_already(ctx: EvalContext) -> NodeResult:
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
            "method": "PUT",
            "path": "/api/submitters/{{comp_submitter_id}}",
            "body": {
                "completed": True
            }
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "expected_status": 422
        }
        ok_2, ratio_2 = execute_primitive("P15", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P15"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "assertions": [
                {
                    "path": "$.error",
                    "op": "contains",
                    "expected": "already completed"
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMITTER_COMPLETE_ALREADY",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_COMPLETE_ALREADY",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_decline_already(ctx: EvalContext) -> NodeResult:
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
            "method": "PUT",
            "path": "/api/submitters/{{dec_submitter_id}}",
            "body": {
                "completed": True
            }
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "expected_status": 422
        }
        ok_2, ratio_2 = execute_primitive("P15", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P15"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "assertions": [
                {
                    "path": "$.error",
                    "op": "contains",
                    "expected": "already declined"
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMITTER_DECLINE_ALREADY",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_DECLINE_ALREADY",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submitter_pagination(ctx: EvalContext) -> NodeResult:
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
            "method": "GET",
            "path": "/api/submitters?limit=1",
            "capture_response_as": "sub_page1"
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
            "response": "{{sub_page1}}",
            "assertions": [
                {
                    "path": "$.data.length",
                    "expected": 1
                },
                {
                    "path": "$.pagination.next",
                    "op": "not_null"
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMITTER_PAGINATION",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMITTER_PAGINATION",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "API_SUBMITTER_LIST": test_api_submitter_list,
    "API_SUBMITTER_SHOW": test_api_submitter_show,
    "API_SUBMITTER_UPDATE": test_api_submitter_update,
    "API_SUBMITTER_VALUES": test_api_submitter_values,
    "API_SUBMITTER_PHONE_NORMALIZE": test_api_submitter_phone_normalize,
    "API_SUBMITTER_COMPLETE": test_api_submitter_complete,
    "API_SUBMITTER_DECLINE": test_api_submitter_decline,
    "API_SUBMITTER_COMPLETE_ALREADY": test_api_submitter_complete_already,
    "API_SUBMITTER_DECLINE_ALREADY": test_api_submitter_decline_already,
    "API_SUBMITTER_PAGINATION": test_api_submitter_pagination,
}
