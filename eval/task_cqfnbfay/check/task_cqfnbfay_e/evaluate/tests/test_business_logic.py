from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_biz_submission_completed_at(ctx: EvalContext) -> NodeResult:
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
                        "email": "biz-complete@example.com"
                    }
                ]
            },
            "capture_response_as": "biz_comp_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{biz_comp_resp}}",
            "assertions": [
                {
                    "path": "$[0].id",
                    "op": "not_null",
                    "capture_as": "biz_comp_submitter_id"
                },
                {
                    "path": "$[0].submission_id",
                    "op": "not_null",
                    "capture_as": "biz_comp_sub_id"
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
            "path": "/api/submitters/{{biz_comp_submitter_id}}",
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
            "sql": "SELECT s.id, (SELECT CASE WHEN COUNT(*) = COUNT(completed_at) THEN 'completed' ELSE 'pending' END FROM submitters WHERE submission_id = s.id) AS status FROM submissions s WHERE s.id = {{biz_comp_sub_id}}",
            "expected_result": {
                "status": "completed"
            },
            "retry_ms": 5000
        }
        ok_4, ratio_4 = execute_primitive("P08", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P08"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "sql": "SELECT completed_at IS NOT NULL AS has_completed FROM submitters WHERE submission_id = {{biz_comp_sub_id}} AND completed_at IS NOT NULL LIMIT 1",
            "expected_result": {
                "has_completed": True
            },
            "retry_ms": 5000
        }
        ok_5, ratio_5 = execute_primitive("P08", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P08"] = {"passed": True, "ratio": ratio_5}

        score = 5.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="BIZ_SUBMISSION_COMPLETED_AT",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_SUBMISSION_COMPLETED_AT",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_submitter_status_computed(ctx: EvalContext) -> NodeResult:
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
                        "email": "status-test@example.com"
                    }
                ]
            },
            "capture_response_as": "status_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{status_resp}}",
            "assertions": [
                {
                    "path": "$[0].status",
                    "op": "in",
                    "expected": [
                        "awaiting"
                    ]
                },
                {
                    "path": "$[0].id",
                    "op": "not_null",
                    "capture_as": "status_submitter_id"
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
            "path": "/api/submitters/{{status_submitter_id}}",
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
            "method": "GET",
            "path": "/api/submitters/{{status_submitter_id}}"
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
                    "expected": "completed"
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
            node_id="BIZ_SUBMITTER_STATUS_COMPUTED",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_SUBMITTER_STATUS_COMPUTED",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_template_snapshot(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 2
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
            "sql": "SELECT template_fields IS NOT NULL AS has_fields, template_schema IS NOT NULL AS has_schema, template_submitters IS NOT NULL AS has_submitters FROM submissions WHERE id = {{submission_id}}",
            "expected_result": {
                "has_fields": True,
                "has_schema": True,
                "has_submitters": True
            }
        }
        ok_1, ratio_1 = execute_primitive("P08", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P08"] = {"passed": True, "ratio": ratio_1}

        score = 5.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="BIZ_TEMPLATE_SNAPSHOT",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_TEMPLATE_SNAPSHOT",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_strip_attributes(ctx: EvalContext) -> NodeResult:
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
                        "email": "  strip.test@example.com  "
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
                    "path": "$[0].email",
                    "expected": "strip.test@example.com"
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
            node_id="BIZ_STRIP_ATTRIBUTES",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_STRIP_ATTRIBUTES",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_soft_delete_restore(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 8
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
                        "email": "softdel@example.com"
                    }
                ]
            },
            "capture_response_as": "sd_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{sd_resp}}",
            "assertions": [
                {
                    "path": "$[0].submission_id",
                    "op": "not_null",
                    "capture_as": "sd_sub_id"
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
            "path": "/api/submissions/{{sd_sub_id}}"
        }
        ok_3, ratio_3 = execute_primitive("P04", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P04"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "assertions": [
                {
                    "path": "$.archived_at",
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

        inputs_5 = {
            "sql": "SELECT archived_at IS NOT NULL AS is_archived FROM submissions WHERE id = {{sd_sub_id}}",
            "expected_result": {
                "is_archived": True
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"Submission.find({{sd_sub_id}}).update!(archived_at: nil)\"",
            "expect_success": True
        }
        ok_6, ratio_6 = execute_primitive("P12", inputs_6, ctx)
        if not ok_6:
            chain_pass = False
            evidence["step_6_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_6_P12"] = {"passed": True, "ratio": ratio_6}

        inputs_7 = {
            "sql": "SELECT archived_at IS NULL AS is_active FROM submissions WHERE id = {{sd_sub_id}}",
            "expected_result": {
                "is_active": True
            }
        }
        ok_7, ratio_7 = execute_primitive("P08", inputs_7, ctx)
        if not ok_7:
            chain_pass = False
            evidence["step_7_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_7_P08"] = {"passed": True, "ratio": ratio_7}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="BIZ_SOFT_DELETE_RESTORE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_SOFT_DELETE_RESTORE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_default_folder_rebuild(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; u=User.first; f=TemplateFolder.find_by(account:a,name:'Default'); if f; f2=TemplateFolder.create!(account:a,author:u,name:'TempHolder'); f.templates.update_all(folder_id:f2.id); f.destroy!; end; puts 'deleted'\"",
            "expect_success": True
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; f=a.default_template_folder; th=TemplateFolder.find_by(account:a,name:'TempHolder'); if th; th.templates.update_all(folder_id:f.id); th.destroy!; end; puts f.name\"",
            "expect_success": True,
            "expect_output_contains": "Default"
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "sql": "SELECT COUNT(*) AS cnt FROM template_folders WHERE name = 'Default'",
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="BIZ_DEFAULT_FOLDER_REBUILD",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_DEFAULT_FOLDER_REBUILD",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_decline_status_propagation(ctx: EvalContext) -> NodeResult:
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
                        "email": "decline-prop@example.com"
                    }
                ]
            },
            "capture_response_as": "dp_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "response": "{{dp_resp}}",
            "assertions": [
                {
                    "path": "$[0].id",
                    "op": "not_null",
                    "capture_as": "dp_submitter_id"
                },
                {
                    "path": "$[0].submission_id",
                    "op": "not_null",
                    "capture_as": "dp_sub_id"
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"s=Submitter.find({{dp_submitter_id}}); s.update!(declined_at: Time.current); puts s.reload.declined_at\"",
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
            "path": "/api/submissions/{{dp_sub_id}}"
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
            node_id="BIZ_DECLINE_STATUS_PROPAGATION",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_DECLINE_STATUS_PROPAGATION",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_formula_stub_zero(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"puts Submitters::SubmitValues.calculate_formula_value('0', {})\"",
            "expect_success": True,
            "expect_output_contains": "0"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="BIZ_FORMULA_STUB_ZERO",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_FORMULA_STUB_ZERO",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_expire_processing(ctx: EvalContext) -> NodeResult:
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; t=Template.find_by(name:'Eval Template'); s=Submission.create!(account:a,template:t,source:'api',template_fields:t.fields,template_schema:t.schema,template_submitters:t.submitters,expire_at:1.minute.ago); sub=Submitter.create!(account:a,submission:s,uuid:t.submitters.first['uuid'],slug:SecureRandom.hex(10),email:'expire@test.com'); puts s.id\"",
            "expect_success": True,
            "capture_stdout_as": "expired_sub_id"
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "method": "GET",
            "path": "/api/submissions/{{expired_sub_id}}"
        }
        ok_2, ratio_2 = execute_primitive("P04", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P04"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "expected_status": 200
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
                    "path": "$.status",
                    "expected": "expired"
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
            node_id="BIZ_EXPIRE_PROCESSING",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_EXPIRE_PROCESSING",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_error_msg_consistency(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/controllers/api/"
            ],
            "rubric_prompt": "GOAL: Judge whether API error responses are uniform across endpoints.\nEVIDENCE: code-files listing for app/controllers/api/** + any rescue_from / error-handling concerns.\nSCORE RANGE: 0-4\n\nCRITERIA:\n  C1. Every 422 (validation) response uses the {\"error\": \"<message>\"} shape (or a documented variant such as {\"errors\": {...}}).\n  C2. Validation messages name the offending field (e.g. \"email is invalid in `submitters[0]`\").\n  C3. 401 responses return a stable copy such as \"Not authenticated\" / \"Authentication required\".\n  C4. 403 responses distinguish testing-API-key vs production-API-key contexts (or similar fine-grained reason).\n\nSCORING ANCHORS:\n  - 0 (none):       0 or 1 of C1-C4 satisfied.\n  - 1 (basic):      2 of C1-C4.\n  - 3 (good):       3 of C1-C4.\n  - 4 (excellent):  All 4 of C1-C4.\n\nOUTPUT: {\"score\": <0..4>, \"reasoning\": \"<1-3 sentences referencing C1..C4>\"}",
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
            node_id="BIZ_ERROR_MSG_CONSISTENCY",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_ERROR_MSG_CONSISTENCY",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_workflow_signing_lifecycle(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 2
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
            "entity_setup": {
                "method": "POST",
                "path": "/api/submissions",
                "body": {
                    "template_id": "{{template_id}}",
                    "send_email": False,
                    "submitters": [
                        {
                            "role": "First Party",
                            "email": "lifecycle@example.com"
                        }
                    ]
                }
            },
            "steps": [
                {
                    "name": "verify_pending",
                    "method": "GET",
                    "path": "/api/submitters/{{id}}",
                    "expect_status": 200,
                    "expect_state": {
                        "path": "$.status",
                        "value": "awaiting"
                    }
                },
                {
                    "name": "complete_submitter",
                    "method": "PUT",
                    "path": "/api/submitters/{{id}}",
                    "body": {
                        "completed": True
                    },
                    "expect_status": 200,
                    "expect_state": {
                        "path": "$.status",
                        "value": "completed"
                    }
                }
            ],
            "final_verify": {
                "db_query": "SELECT s.archived_at IS NULL AS active FROM submissions s JOIN submitters sub ON sub.submission_id = s.id WHERE sub.email = 'lifecycle@example.com'",
                "expected": {
                    "active": True
                }
            }
        }
        ok_1, ratio_1 = execute_primitive("P29", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P29"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P29"] = {"passed": True, "ratio": ratio_1}

        score = round((pass_count / 2) * 5, 2) if 2 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="WORKFLOW_SIGNING_LIFECYCLE",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="WORKFLOW_SIGNING_LIFECYCLE",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_workflow_multi_submitter(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 2
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
            "entity_setup": {
                "method": "POST",
                "path": "/api/submissions",
                "body": {
                    "template_id": "{{three_party_template_id}}",
                    "send_email": False,
                    "order": "preserved",
                    "submitters": [
                        {
                            "role": "First Party",
                            "email": "multi1@example.com"
                        },
                        {
                            "role": "Second Party",
                            "email": "multi2@example.com"
                        },
                        {
                            "role": "Third Party",
                            "email": "multi3@example.com"
                        }
                    ]
                }
            },
            "steps": [
                {
                    "name": "complete_first",
                    "method": "PUT",
                    "path": "/api/submitters/{{submitter_ids[0]}}",
                    "body": {
                        "completed": True
                    },
                    "expect_status": 200,
                    "expect_state": {
                        "path": "$.status",
                        "value": "completed"
                    }
                },
                {
                    "name": "complete_second",
                    "method": "PUT",
                    "path": "/api/submitters/{{submitter_ids[1]}}",
                    "body": {
                        "completed": True
                    },
                    "expect_status": 200,
                    "expect_state": {
                        "path": "$.status",
                        "value": "completed"
                    }
                },
                {
                    "name": "complete_third",
                    "method": "PUT",
                    "path": "/api/submitters/{{submitter_ids[2]}}",
                    "body": {
                        "completed": True
                    },
                    "expect_status": 200,
                    "expect_state": {
                        "path": "$.status",
                        "value": "completed"
                    }
                }
            ],
            "final_verify": {
                "db_query": "SELECT COUNT(*) AS completed_count FROM submitters WHERE submission_id = {{id}} AND completed_at IS NOT NULL",
                "expected": {
                    "completed_count": 3
                }
            }
        }
        ok_1, ratio_1 = execute_primitive("P29", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P29"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P29"] = {"passed": True, "ratio": ratio_1}

        score = round((pass_count / 2) * 5, 2) if 2 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="WORKFLOW_MULTI_SUBMITTER",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="WORKFLOW_MULTI_SUBMITTER",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_role_merging(ctx: EvalContext) -> NodeResult:
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
                "template_id": "{{three_party_template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "roles": [
                            "First Party",
                            "Second Party"
                        ],
                        "email": "merged@example.com"
                    },
                    {
                        "role": "Third Party",
                        "email": "third-merge@example.com"
                    }
                ]
            },
            "capture_response_as": "merge_resp"
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "acceptable_statuses": [
                200,
                422
            ]
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
                    "path": "$[0].email",
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

        inputs_4 = {
            "sql": "SELECT COUNT(*) AS cnt FROM submitters WHERE email = 'merged@example.com'",
            "expected_result": {
                "cnt": {
                    "op": ">=",
                    "value": 1
                }
            },
            "retry_ms": 5000
        }
        ok_4, ratio_4 = execute_primitive("P08", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P08"] = {"passed": True, "ratio": ratio_4}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="BIZ_ROLE_MERGING",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_ROLE_MERGING",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_biz_conditional_fields_exist(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 2
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "find app -name '*.rb' | xargs grep -l 'conditions\\|check_field.*condition\\|evaluate.*condition' 2>/dev/null | head -5",
            "expect_success": True
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/javascript/template_builder/conditions_modal.vue",
                "app/javascript/submission_form/",
                "app/javascript/template_builder/",
                "lib/submissions/"
            ],
            "rubric_prompt": "GOAL: Judge support for conditional / dependent field logic.\nEVIDENCE: code-files listing for app/lib/**condition** and app/javascript/**condition**.\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. There is dedicated condition-evaluation logic (named like check_conditions / evaluate_conditions).\n  C2. The operator vocabulary supports at least: not_empty / empty / equal (case-sensitive equality).\n  C3. When a condition is unsatisfied, the field value is removed / skipped (not silently kept).\n  C4. Conditions support boolean composition (AND / OR groups) — not only single-clause.\n  C5. Document-level conditions can hide an entire page's worth of field values when triggered.\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C5.\n  - 2 (basic):      2 of C1-C5; only equality + not_empty.\n  - 4 (good):       3 or 4 of C1-C5; AND/OR or page-level missing.\n  - 5 (excellent):  All 5 of C1-C5.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
            "score_range": [
                0,
                5
            ]
        }
        ok_1, ratio_1 = execute_primitive("P17", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P17"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P17"] = {"passed": True, "ratio": ratio_1}
            llm_score = ctx.captured.get("_llm_score", 0.0)

        score = min(llm_score, 5.0) if llm_score is not None else 0.0
        status = "PASSED" if score > 0 else "FAILED"

        return NodeResult(
            node_id="BIZ_CONDITIONAL_FIELDS_EXIST",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="BIZ_CONDITIONAL_FIELDS_EXIST",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "BIZ_SUBMISSION_COMPLETED_AT": test_biz_submission_completed_at,
    "BIZ_SUBMITTER_STATUS_COMPUTED": test_biz_submitter_status_computed,
    "BIZ_TEMPLATE_SNAPSHOT": test_biz_template_snapshot,
    "BIZ_STRIP_ATTRIBUTES": test_biz_strip_attributes,
    "BIZ_SOFT_DELETE_RESTORE": test_biz_soft_delete_restore,
    "BIZ_DEFAULT_FOLDER_REBUILD": test_biz_default_folder_rebuild,
    "BIZ_DECLINE_STATUS_PROPAGATION": test_biz_decline_status_propagation,
    "BIZ_FORMULA_STUB_ZERO": test_biz_formula_stub_zero,
    "BIZ_EXPIRE_PROCESSING": test_biz_expire_processing,
    "BIZ_ERROR_MSG_CONSISTENCY": test_biz_error_msg_consistency,
    "WORKFLOW_SIGNING_LIFECYCLE": test_workflow_signing_lifecycle,
    "WORKFLOW_MULTI_SUBMITTER": test_workflow_multi_submitter,
    "BIZ_ROLE_MERGING": test_biz_role_merging,
    "BIZ_CONDITIONAL_FIELDS_EXIST": test_biz_conditional_fields_exist,
}
