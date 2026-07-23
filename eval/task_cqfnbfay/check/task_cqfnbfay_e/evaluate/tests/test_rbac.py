from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_rbac_admin_can_manage(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "role": "admin",
            "action": "GET /api/templates",
            "token": "{{admin_token}}",
            "expected_result": "allowed",
            "expected_status": 200
        }
        ok_0, ratio_0 = execute_primitive("P14", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P14"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P14"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "role": "admin",
            "action": "GET /api/submissions",
            "token": "{{admin_token}}",
            "expected_result": "allowed",
            "expected_status": 200
        }
        ok_1, ratio_1 = execute_primitive("P14", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P14"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P14"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "role": "admin",
            "action": "GET /api/submitters",
            "token": "{{admin_token}}",
            "expected_result": "allowed",
            "expected_status": 200
        }
        ok_2, ratio_2 = execute_primitive("P14", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P14"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P14"] = {"passed": True, "ratio": ratio_2}

        score = round((pass_count / 3) * 4, 2) if 3 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="RBAC_ADMIN_CAN_MANAGE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="RBAC_ADMIN_CAN_MANAGE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_rbac_non_admin_denied(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; u=User.find_or_initialize_by(email:'normal@test.com'); u.assign_attributes(account:a,first_name:'Normal',last_name:'User',password:'NormPass123!'); u.role='user'; u.save!; t=(u.access_token||u.create_access_token!).token; puts t\"",
            "expect_success": True,
            "capture_stdout_as": "normal_user_token"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"b=Account.find_or_create_by!(name:'OtherCo'){|x| x.timezone='UTC'; x.locale='en'}; bu=User.find_or_initialize_by(email:'other@test.com'); bu.assign_attributes(account:b,first_name:'Other',last_name:'Adm',password:'OtherPass123!'); bu.role='admin'; bu.save!; ot=Template.find_or_initialize_by(account:b,name:'Other Account Template'); ot.author=bu; ot.slug ||= 'otheracct'+SecureRandom.hex(3); ot.shared_link=false; ot.submitters=[{'name'=>'x','uuid'=>SecureRandom.uuid}]; ot.schema=[{'attachment_uuid'=>SecureRandom.uuid,'name'=>'D'}]; ot.fields=[]; ot.save!; puts ot.id\"",
            "expect_success": True,
            "capture_stdout_as": "other_account_template_id"
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "role": "user",
            "action": "GET /api/user",
            "token": "{{normal_user_token}}",
            "expected_result": "allowed",
            "expected_status": 200
        }
        ok_2, ratio_2 = execute_primitive("P14", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P14"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P14"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "role": "user",
            "action": "DELETE /api/templates/{{other_account_template_id}}",
            "token": "{{normal_user_token}}",
            "expected_result": "denied",
            "expected_status": 403
        }
        ok_3, ratio_3 = execute_primitive("P14", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P14"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P14"] = {"passed": True, "ratio": ratio_3}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="RBAC_NON_ADMIN_DENIED",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="RBAC_NON_ADMIN_DENIED",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_rbac_account_data_isolation(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "method": "POST",
            "path": "/api/submissions",
            "body": {
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "iso-data@example.com"
                    }
                ]
            },
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
            "acceptable_statuses": [
                403,
                404,
                422
            ]
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
                    "expected": "not found"
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
            node_id="RBAC_ACCOUNT_DATA_ISOLATION",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="RBAC_ACCOUNT_DATA_ISOLATION",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_rbac_permission_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 ={
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/controllers/application_controller.rb",
                "app/controllers/templates_controller.rb",
                "app/controllers/submissions_controller.rb",
                "app/controllers/users_controller.rb",
                "app/models/ability.rb",
                "app/models/abilities"
            ],
            "rubric_prompt": "GOAL: Judge the role-based authorisation system.\nEVIDENCE: ApplicationController + sample resource controllers + Ability class (or Abilities namespace).\nSCORE RANGE: 0-4\n\nCONTEXT (task.md §7 + KB-048 + KB-049): Authorization is CanCanCan-based with account-level data isolation. The Ability class may be a single `app/models/ability.rb` file OR organised as an `Abilities::*` namespace under `app/models/abilities/` (per KB-048 Abilities::TemplateConditions). admin is the only role (task.md §7.1) and users can `manage` resources within their own account (account_id-scoped). Controllers may use `load_and_authorize_resource`, `authorize_resource`, or explicit `authorize!(:action, Resource)` calls. Public endpoints opt out via `skip_authorization_check`.\n\nCRITERIA:\n  C1. ApplicationController enables CanCanCan globally (e.g. `check_authorization unless: :devise_controller?`) so authorize calls are mandatory by default.\n  C2. An Ability class or Abilities namespace defines the permission matrix (admin can manage account-scoped resources; account_id condition is part of the rule).\n  C3. Resource controllers invoke load_and_authorize_resource / authorize_resource / authorize! on at least 2 distinct resources (e.g. Template and Submission).\n  C4. Account isolation is visibly enforced — queries are scoped via current_user.account / account_id, not global ActiveRecord.all on tenant data; public endpoints (e.g. signing form) explicitly opt out via skip_authorization_check rather than skipping silently.\n\nSCORING ANCHORS:\n  - 0 (none):       0 or 1 of C1-C4.\n  - 1 (basic):      2 of C1-C4.\n  - 3 (good):       3 of C1-C4.\n  - 4 (excellent):  All 4 of C1-C4; tenant isolation visibly enforced.\n\nOUTPUT: {\"score\": <0..4>, \"reasoning\": \"<1-3 sentences referencing C1..C4>\"}",
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
            node_id="RBAC_PERMISSION_QUALITY",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="RBAC_PERMISSION_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "RBAC_ADMIN_CAN_MANAGE": test_rbac_admin_can_manage,
    "RBAC_NON_ADMIN_DENIED": test_rbac_non_admin_denied,
    "RBAC_ACCOUNT_DATA_ISOLATION": test_rbac_account_data_isolation,
    "RBAC_PERMISSION_QUALITY": test_rbac_permission_quality,
}
