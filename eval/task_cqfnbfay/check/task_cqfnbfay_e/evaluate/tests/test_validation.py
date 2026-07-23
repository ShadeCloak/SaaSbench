from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_valid_submission_invalid_email(ctx: EvalContext) -> NodeResult:
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
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "john@example"
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
                    "expected": "email is invalid"
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
            node_id="VALID_SUBMISSION_INVALID_EMAIL",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_SUBMISSION_INVALID_EMAIL",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_submission_duplicate_roles(ctx: EvalContext) -> NodeResult:
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
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "dup1@example.com"
                    },
                    {
                        "role": "First Party",
                        "email": "dup2@example.com"
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
                    "expected": "role must be unique in `submitters`."
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
            node_id="VALID_SUBMISSION_DUPLICATE_ROLES",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_SUBMISSION_DUPLICATE_ROLES",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_submission_too_many_submitters(ctx: EvalContext) -> NodeResult:
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
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "s1@example.com"
                    },
                    {
                        "role": "Extra Party",
                        "email": "s2@example.com"
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
            node_id="VALID_SUBMISSION_TOO_MANY_SUBMITTERS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_SUBMISSION_TOO_MANY_SUBMITTERS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_submission_no_fields(ctx: EvalContext) -> NodeResult:
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first;u=User.first;f=a.default_template_folder;t=Template.create!(account:a,author:u,folder:f,name:'Empty Fields',fields:[],submitters:[{'name'=>'First Party','uuid'=>SecureRandom.uuid}],schema:[],preferences:{},source:'native');puts t.id\"",
            "expect_success": True,
            "capture_stdout_as": "empty_template_id"
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{empty_template_id}}",
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "nofields@example.com"
                    }
                ]
            }
        }
        ok_2, ratio_2 = execute_primitive("P04", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P04"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "expected_status": 422
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
                    "expected": "Template does not contain fields"
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
            node_id="VALID_SUBMISSION_NO_FIELDS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_SUBMISSION_NO_FIELDS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_submission_message_no_body(ctx: EvalContext) -> NodeResult:
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
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "msg@example.com"
                    }
                ],
                "message": {
                    "subject": "Custom Email Subject"
                }
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
                    "expected": "body is required in `message`."
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

        score = 2.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="VALID_SUBMISSION_MESSAGE_NO_BODY",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_SUBMISSION_MESSAGE_NO_BODY",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_submission_empty_message_ok(ctx: EvalContext) -> NodeResult:
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
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "emptymsg@example.com"
                    }
                ],
                "message": {}
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

        score = 1.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="VALID_SUBMISSION_EMPTY_MESSAGE_OK",
            status=status,
            score=score,
            max_score=1.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_SUBMISSION_EMPTY_MESSAGE_OK",
            status="ERROR",
            score=0.0,
            max_score=1.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_submission_bulk_invalid_emails(ctx: EvalContext) -> NodeResult:
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
                "emails": "amy.baker@example.com, george.morris@example.com@gmail.com"
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
                    "expected": "emails are invalid"
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
            node_id="VALID_SUBMISSION_BULK_INVALID_EMAILS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_SUBMISSION_BULK_INVALID_EMAILS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_setup_short_password(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 2
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"begin; u=User.new(email:'shortpw@test.com',password:'pass',role:'admin',account:Account.new(name:'X')); u.valid?; puts u.errors.full_messages.join(','); rescue => e; puts e.message; end\"",
            "expect_success": True,
            "expect_output_contains": "too short"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "sql": "SELECT COUNT(*) AS cnt FROM users WHERE email = 'shortpw@test.com'",
            "expected_result": {
                "cnt": 0
            }
        }
        ok_1, ratio_1 = execute_primitive("P08", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P08"] = {"passed": True, "ratio": ratio_1}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="VALID_SETUP_SHORT_PASSWORD",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_SETUP_SHORT_PASSWORD",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_phone_start_plus(ctx: EvalContext) -> NodeResult:
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
                        "email": "phone-invalid@example.com",
                        "phone": "12345"
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
                    "expected": "phone should start with +"
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
            node_id="VALID_PHONE_START_PLUS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_PHONE_START_PLUS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_valid_merge_minimum_files(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/tools/merge",
            "body": {
                "files": [
                    "dGVzdA=="
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
                    "expected": "At least 2 files"
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
            node_id="VALID_MERGE_MINIMUM_FILES",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="VALID_MERGE_MINIMUM_FILES",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "VALID_SUBMISSION_INVALID_EMAIL": test_valid_submission_invalid_email,
    "VALID_SUBMISSION_DUPLICATE_ROLES": test_valid_submission_duplicate_roles,
    "VALID_SUBMISSION_TOO_MANY_SUBMITTERS": test_valid_submission_too_many_submitters,
    "VALID_SUBMISSION_NO_FIELDS": test_valid_submission_no_fields,
    "VALID_SUBMISSION_MESSAGE_NO_BODY": test_valid_submission_message_no_body,
    "VALID_SUBMISSION_EMPTY_MESSAGE_OK": test_valid_submission_empty_message_ok,
    "VALID_SUBMISSION_BULK_INVALID_EMAILS": test_valid_submission_bulk_invalid_emails,
    "VALID_SETUP_SHORT_PASSWORD": test_valid_setup_short_password,
    "VALID_PHONE_START_PLUS": test_valid_phone_start_plus,
    "VALID_MERGE_MINIMUM_FILES": test_valid_merge_minimum_files,
}
