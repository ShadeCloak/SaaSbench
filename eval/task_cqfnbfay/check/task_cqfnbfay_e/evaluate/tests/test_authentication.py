from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_auth_setup_flow(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"account = Account.find_or_create_by!(name: 'EvalCo'); user = account.users.find_or_create_by!(email: 'eval@test.com') { |u| u.first_name='Eval'; u.last_name='Admin'; u.password='EvalPass123!' }; account.encrypted_configs.find_or_create_by!(key: EncryptedConfig::APP_URL_KEY) { |c| c.value='http://localhost:8021' }; account.encrypted_configs.find_or_create_by!(key: EncryptedConfig::ESIGN_CERTS_KEY) { |c| c.value = {cert: 'placeholder'} }; account.account_configs.find_or_create_by!(key: :fulltext_search) { |c| c.value=true } if SearchEntry.table_exists?; puts 'SETUP_OK'\"",
            "expect_success": True,
            "expect_output_contains": "SETUP_OK"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_2 = {
            "sql": "SELECT COUNT(*) AS cnt FROM accounts WHERE name = 'EvalCo'",
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

        inputs_3 = {
            "sql": "SELECT COUNT(*) AS cnt FROM users WHERE email = 'eval@test.com'",
            "expected_result": {
                "cnt": 1
            }
        }
        ok_3, ratio_3 = execute_primitive("P08", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P08"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "sql": "SELECT COUNT(*) AS cnt FROM encrypted_configs WHERE key = 'esign_certs'",
            "expected_result": {
                "cnt": 1
            }
        }
        ok_4, ratio_4 = execute_primitive("P08", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P08"] = {"passed": True, "ratio": ratio_4}

        score = 5.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="AUTH_SETUP_FLOW",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="AUTH_SETUP_FLOW",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_auth_setup_guard(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "method": "POST",
            "path": "/setup",
            "body": {
                "user": {
                    "first_name": "X",
                    "last_name": "Y",
                    "email": "x@y.com",
                    "password": "Pass123!"
                },
                "account": {
                    "name": "X"
                }
            },
            "timeout": 10
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
                302,
                403,
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
            "sql": "SELECT COUNT(*) AS cnt FROM accounts WHERE name = 'X'",
            "expected_result": {
                "cnt": 0
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
            node_id="AUTH_SETUP_GUARD",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="AUTH_SETUP_GUARD",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_auth_api_token(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"u=User.find_by(email:'eval@test.com'); t=u.access_token||u.create_access_token!; puts t.token\"",
            "expect_success": True,
            "capture_stdout_as": "admin_token"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "method": "GET",
            "path": "/api/user",
            "headers": {
                "X-Auth-Token": "{{admin_token}}"
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
                    "expected": "eval@test.com"
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
            node_id="AUTH_API_TOKEN",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="AUTH_API_TOKEN",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_auth_invalid_token(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "method": "GET",
            "path": "/api/user",
            "headers": {
                "X-Auth-Token": "invalid_token_xyz_12345"
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
            "expected_status": 401
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
                    "expected": "Not authenticated"
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

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="AUTH_INVALID_TOKEN",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="AUTH_INVALID_TOKEN",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_auth_security_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/models/user.rb",
                "app/controllers/api/",
                "config/initializers/devise.rb"
            ],
            "rubric_prompt": "GOAL: Judge the strength of authentication and credential handling.\nEVIDENCE: code-files listing for app/models/user.rb, app/controllers/sessions*, db/schema.rb, Gemfile.\nSCORE RANGE: 0-6\n\nCRITERIA:\n  C1. Passwords stored hashed via bcrypt / Devise (encrypted_password column or has_secure_password).\n  C2. API tokens live in a dedicated access_tokens table separate from password.\n  C3. OTP / two-factor auth is implemented (otp_secret + otp_required_for_login or similar columns).\n  C4. Failed-login lockout is implemented (Devise :lockable + failed_attempts + locked_at columns).\n  C5. CSRF protection is enabled (protect_from_forgery in ApplicationController, or session-mode forms).\n  C6. Tokens are generated with SecureRandom or equivalent crypto-strength generator (>= 32 chars / >= 192 bits).\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C6 satisfied.\n  - 2 (basic):      2 of C1-C6 (typically C1 + C5 only).\n  - 4 (good):       3 or 4 of C1-C6; OTP or lockout missing.\n  - 6 (excellent):  5 or 6 of C1-C6; defence-in-depth posture.\n\nOUTPUT: {\"score\": <0..6>, \"reasoning\": \"<1-3 sentences referencing C1..C6>\"}",
            "score_range": [
                0,
                6
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

        score = min(llm_score, 6.0) if llm_score is not None else 0.0
        status = "PASSED" if score > 0 else "FAILED"

        return NodeResult(
            node_id="AUTH_SECURITY_QUALITY",
            status=status,
            score=score,
            max_score=6.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="AUTH_SECURITY_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=6.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_user_management(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 5
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; u=User.find_or_initialize_by(email:'team.member@eval.com'); u.assign_attributes(account:a,first_name:'Team',last_name:'Member',password:'TeamPass123!'); u.role='admin'; u.save!; puts u.id\"",
            "expect_success": True,
            "capture_stdout_as": "team_user_id"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "sql": "SELECT email, role FROM users WHERE email = 'team.member@eval.com'",
            "expected_result": {
                "email": "team.member@eval.com",
                "role": "admin"
            }
        }
        ok_1, ratio_1 = execute_primitive("P08", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P08"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"begin; a=Account.first; User.create!(account:a,first_name:'Dup',last_name:'User',email:'team.member@eval.com',password:'DupPass123!',role:'admin'); rescue => e; puts e.message; end\"",
            "expect_success": True,
            "expect_output_contains": "taken"
        }
        ok_2, ratio_2 = execute_primitive("P12", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P12"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"u=User.find_by(email:'team.member@eval.com'); u.update!(archived_at:Time.current); puts u.archived_at.present?\"",
            "expect_success": True,
            "expect_output_contains": "true"
        }
        ok_3, ratio_3 = execute_primitive("P12", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P12"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "sql": "SELECT archived_at IS NOT NULL AS is_archived FROM users WHERE email = 'team.member@eval.com'",
            "expected_result": {
                "is_archived": True
            }
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
            node_id="API_USER_MANAGEMENT",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_USER_MANAGEMENT",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "AUTH_SETUP_FLOW": test_auth_setup_flow,
    "AUTH_SETUP_GUARD": test_auth_setup_guard,
    "AUTH_API_TOKEN": test_auth_api_token,
    "AUTH_INVALID_TOKEN": test_auth_invalid_token,
    "AUTH_SECURITY_QUALITY": test_auth_security_quality,
    "API_USER_MANAGEMENT": test_api_user_management,
}
