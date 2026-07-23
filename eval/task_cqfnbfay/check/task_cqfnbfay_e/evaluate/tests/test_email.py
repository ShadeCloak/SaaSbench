from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_email_mailer_classes(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "glob": "**/*_mailer.rb",
            "base_dir": "app/mailers",
            "min_expected": 4
        }
        ok_0, ratio_0 = execute_primitive("P03", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P03"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P03"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 3, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="EMAIL_MAILER_CLASSES",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="EMAIL_MAILER_CLASSES",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_email_invitation_delivery(ctx: EvalContext) -> NodeResult:
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
                "send_email": True,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "email-test@example.com"
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
            "sql": "SELECT COUNT(*) AS cnt FROM submitters WHERE email = 'email-test@example.com' AND sent_at IS NOT NULL",
            "expected_result": {
                "cnt": 1
            },
            "retry_ms": 10000
        }
        ok_2, ratio_2 = execute_primitive("P08", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P08"] = {"passed": True, "ratio": ratio_2}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="EMAIL_INVITATION_DELIVERY",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="EMAIL_INVITATION_DELIVERY",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_email_design_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/mailers/",
                "app/views/submitter_mailer/"
            ],
            "rubric_prompt": "GOAL: Judge the depth of the customer-facing email system.\nEVIDENCE: code-files listing for app/mailers/submitter_mailer.rb and its views + EmailMessage model.\nSCORE RANGE: 0-4\n\nCRITERIA:\n  C1. SubmitterMailer defines invitation_email, completed_email and declined_email actions.\n  C2. Mailer templates accept a locale param and render localised copy via I18n.t.\n  C3. Both HTML and plain-text variants exist for each mailer action.\n  C4. A precedence chain resolves email content (EmailMessage > preferences > AccountConfig > I18n default).\n\nSCORING ANCHORS:\n  - 0 (none):       0 or 1 of C1-C4.\n  - 1 (basic):      2 of C1-C4.\n  - 3 (good):       3 of C1-C4.\n  - 4 (excellent):  All 4 of C1-C4.\n\nOUTPUT: {\"score\": <0..4>, \"reasoning\": \"<1-3 sentences referencing C1..C4>\"}",
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
            node_id="EMAIL_DESIGN_QUALITY",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="EMAIL_DESIGN_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "EMAIL_MAILER_CLASSES": test_email_mailer_classes,
    "EMAIL_INVITATION_DELIVERY": test_email_invitation_delivery,
    "EMAIL_DESIGN_QUALITY": test_email_design_quality,
}
