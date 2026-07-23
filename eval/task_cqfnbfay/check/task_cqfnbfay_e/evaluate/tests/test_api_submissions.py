from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_api_submission_create(ctx: EvalContext) -> NodeResult:
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
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "john.doe@example.com"
                    }
                ]
            },
            "capture_response_as": "create_sub_resp"
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
            "response": "{{create_sub_resp}}",
            "assertions": [
                {
                    "path": "$[0].email",
                    "expected": "john.doe@example.com"
                },
                {
                    "path": "$[0].status",
                    "expected": "awaiting"
                },
                {
                    "path": "$[0].role",
                    "expected": "First Party"
                },
                {
                    "path": "$[0].submission_id",
                    "op": "not_null",
                    "capture_as": "submission_id"
                },
                {
                    "path": "$[0].id",
                    "op": "not_null",
                    "capture_as": "submitter_id"
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
            "response": "{{create_sub_resp}}",
            "required_fields": [
                "id",
                "submission_id",
                "uuid",
                "email",
                "slug",
                "status",
                "role",
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

        score = 5.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_CREATE",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_CREATE",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_create_completed(ctx: EvalContext) -> NodeResult:
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
                        "email": "completed@example.com",
                        "completed": True
                    }
                ]
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
                    "path": "$[0].status",
                    "expected": "completed"
                },
                {
                    "path": "$[0].completed_at",
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

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_CREATE_COMPLETED",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_CREATE_COMPLETED",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_create_partial_roles(ctx: EvalContext) -> NodeResult:
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
                "template_id": "{{three_party_template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "first@example.com"
                    },
                    {
                        "email": "second@example.com"
                    },
                    {
                        "email": "third@example.com"
                    }
                ]
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
                    "path": "$[0].role",
                    "expected": "First Party"
                },
                {
                    "path": "$[1].role",
                    "expected": "Second Party"
                },
                {
                    "path": "$[2].role",
                    "expected": "Third Party"
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

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_CREATE_PARTIAL_ROLES",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_CREATE_PARTIAL_ROLES",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_emails(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/submissions/emails",
            "body": {
                "template_id": "{{template_id}}",
                "emails": "sub1@example.com,sub2@example.com"
            },
            "capture_response_as": "bulk_resp"
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
            "response": "{{bulk_resp}}",
            "assertions": [
                {
                    "path": "$.length",
                    "op": ">=",
                    "expected": 2
                },
                {
                    "path": "$[0].email",
                    "expected": "sub1@example.com"
                },
                {
                    "path": "$[1].email",
                    "expected": "sub2@example.com"
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
            node_id="API_SUBMISSION_EMAILS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_EMAILS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_order_preserved(ctx: EvalContext) -> NodeResult:
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
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "order": "preserved",
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "order-test@example.com"
                    }
                ]
            },
            "capture_response_as": "order_resp"
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
            "response": "{{order_resp}}",
            "assertions": [
                {
                    "path": "$[0].submission_id",
                    "op": "not_null",
                    "capture_as": "order_sub_id"
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
            "sql": "SELECT submitters_order FROM submissions WHERE id = {{order_sub_id}}",
            "expected_result": {
                "submitters_order": "preserved"
            }
        }
        ok_4, ratio_4 = execute_primitive("P08", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P08"] = {"passed": True, "ratio": ratio_4}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_ORDER_PRESERVED",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_ORDER_PRESERVED",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_show(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/submissions/{{submission_id}}"
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
                "slug",
                "status",
                "submitters",
                "documents",
                "submission_events",
                "template",
                "created_at"
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
                    "path": "$.status",
                    "op": "in",
                    "expected": [
                        "pending",
                        "completed",
                        "declined",
                        "expired"
                    ]
                },
                {
                    "path": "$.id",
                    "expected": "{{submission_id}}"
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
            node_id="API_SUBMISSION_SHOW",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_SHOW",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_list(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/submissions"
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
                },
                {
                    "path": "$.data[0].id",
                    "op": "not_null"
                },
                {
                    "path": "$.data[0].status",
                    "op": "in",
                    "expected": [
                        "pending",
                        "completed",
                        "declined",
                        "expired"
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
            node_id="API_SUBMISSION_LIST",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_LIST",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_nested(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/templates/{{template_id}}/submissions"
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
                    "path": "$.data[0].template.id",
                    "op": "not_null"
                },
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
            node_id="API_SUBMISSION_NESTED",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_NESTED",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_filter_status(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/submissions?status=pending"
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
                    "path": "$.data[0].status",
                    "expected": "pending"
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
            "path": "/api/submissions?status=completed"
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
            node_id="API_SUBMISSION_FILTER_STATUS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_FILTER_STATUS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_filter_date(ctx: EvalContext) -> NodeResult:
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
            "method": "GET",
            "path": "/api/submissions?created_at_from=2020-01-01&created_at_to=2099-12-31"
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
            "method": "GET",
            "path": "/api/submissions?created_at_from=2099-01-01&created_at_to=2099-12-31"
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
                    "path": "$.pagination.count",
                    "expected": 0
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_FILTER_DATE",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_FILTER_DATE",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_pagination(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/submissions?limit=1",
            "capture_response_as": "page1_resp"
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
            "response": "{{page1_resp}}",
            "assertions": [
                {
                    "path": "$.data.length",
                    "expected": 1
                },
                {
                    "path": "$.pagination.next",
                    "op": "not_null",
                    "capture_as": "next_cursor"
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
            "path": "/api/submissions?limit=1&after={{next_cursor}}"
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

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_PAGINATION",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_PAGINATION",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_archive(ctx: EvalContext) -> NodeResult:
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
                        "email": "archive-test@example.com"
                    }
                ]
            },
            "capture_response_as": "archive_create_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{archive_create_resp}}",
            "assertions": [
                {
                    "path": "$[0].submission_id",
                    "op": "not_null",
                    "capture_as": "archive_sub_id"
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
            "method": "DELETE",
            "path": "/api/submissions/{{archive_sub_id}}"
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
                    "path": "$.archived_at",
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_ARCHIVE",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_ARCHIVE",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_hard_delete(ctx: EvalContext) -> NodeResult:
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
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "harddelete@example.com"
                    }
                ]
            },
            "capture_response_as": "hd_create_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{hd_create_resp}}",
            "assertions": [
                {
                    "path": "$[0].submission_id",
                    "op": "not_null",
                    "capture_as": "hd_sub_id"
                },
                {
                    "path": "$[0].id",
                    "op": "not_null",
                    "capture_as": "hd_submitter_id"
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
            "method": "DELETE",
            "path": "/api/submissions/{{hd_sub_id}}?permanently=true"
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
            "sql": "SELECT COUNT(*) AS cnt FROM submissions WHERE id = {{hd_sub_id}}",
            "expected_result": {
                "cnt": 0
            }
        }
        ok_5, ratio_5 = execute_primitive("P08", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P08"] = {"passed": True, "ratio": ratio_5}

        inputs_6 = {
            "sql": "SELECT COUNT(*) AS cnt FROM submitters WHERE id = {{hd_submitter_id}}",
            "expected_result": {
                "cnt": 0
            }
        }
        ok_6, ratio_6 = execute_primitive("P08", inputs_6, ctx)
        if not ok_6:
            chain_pass = False
            evidence["step_6_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_6_P08"] = {"passed": True, "ratio": ratio_6}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_HARD_DELETE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_HARD_DELETE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_init(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/submissions/init",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "init-test@example.com"
                    }
                ]
            },
            "capture_response_as": "init_resp"
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
            "response": "{{init_resp}}",
            "assertions": [
                {
                    "path": "$.id",
                    "op": "not_null"
                },
                {
                    "path": "$.submitters[0].uuid",
                    "op": "not_null"
                },
                {
                    "path": "$.submitters[0].slug",
                    "op": "not_null"
                },
                {
                    "path": "$.submitters[0].embed_src",
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

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_SUBMISSION_INIT",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_INIT",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_submission_nested_create(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/templates/{{template_id}}/submissions",
            "body": {
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "nested-create@example.com"
                    }
                ]
            },
            "capture_response_as": "nested_create_resp"
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
            "response": "{{nested_create_resp}}",
            "assertions": [
                {
                    "path": "$[0].submission_id",
                    "op": "not_null"
                },
                {
                    "path": "$[0].email",
                    "expected": "nested-create@example.com"
                },
                {
                    "path": "$[0].role",
                    "expected": "First Party"
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
            node_id="API_SUBMISSION_NESTED_CREATE",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_SUBMISSION_NESTED_CREATE",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "API_SUBMISSION_CREATE": test_api_submission_create,
    "API_SUBMISSION_CREATE_COMPLETED": test_api_submission_create_completed,
    "API_SUBMISSION_CREATE_PARTIAL_ROLES": test_api_submission_create_partial_roles,
    "API_SUBMISSION_EMAILS": test_api_submission_emails,
    "API_SUBMISSION_ORDER_PRESERVED": test_api_submission_order_preserved,
    "API_SUBMISSION_SHOW": test_api_submission_show,
    "API_SUBMISSION_LIST": test_api_submission_list,
    "API_SUBMISSION_NESTED": test_api_submission_nested,
    "API_SUBMISSION_FILTER_STATUS": test_api_submission_filter_status,
    "API_SUBMISSION_FILTER_DATE": test_api_submission_filter_date,
    "API_SUBMISSION_PAGINATION": test_api_submission_pagination,
    "API_SUBMISSION_ARCHIVE": test_api_submission_archive,
    "API_SUBMISSION_HARD_DELETE": test_api_submission_hard_delete,
    "API_SUBMISSION_INIT": test_api_submission_init,
    "API_SUBMISSION_NESTED_CREATE": test_api_submission_nested_create,
}
