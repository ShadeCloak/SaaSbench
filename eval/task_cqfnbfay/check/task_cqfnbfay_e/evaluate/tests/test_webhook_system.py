from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_webhook_delivery_submission_created(ctx: EvalContext) -> NodeResult:
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; wu=WebhookUrl.create!(account:a,url:'http://host.docker.internal:{{webhook_port}}/hook',events:['submission.created'],secret:{}); puts wu.id\"",
            "expect_success": True,
            "capture_stdout_as": "webhook_url_id"
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "trigger": {
                "method": "POST",
                "path": "/api/submissions",
                "body": {
                    "template_id": "{{template_id}}",
                    "send_email": False,
                    "submitters": [
                        {
                            "role": "First Party",
                            "email": "webhook-test@example.com"
                        }
                    ]
                }
            },
            "expect_delivery": {
                "timeout_ms": 15000,
                "body_contains": {
                    "event_type": "submission.created"
                },
                "headers_contain": {
                    "Content-Type": "application/json"
                }
            }
        }
        ok_2, ratio_2 = execute_primitive("P27", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P27"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P27"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "sql": "SELECT COUNT(*) AS cnt FROM webhook_events WHERE webhook_url_id = {{webhook_url_id}} AND event_type = 'submission.created'",
            "expected_result": {
                "cnt": 1
            },
            "retry_ms": 5000
        }
        ok_3, ratio_3 = execute_primitive("P08", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P08"] = {"passed": True, "ratio": ratio_3}

        score = 5.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="WEBHOOK_DELIVERY_SUBMISSION_CREATED",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="WEBHOOK_DELIVERY_SUBMISSION_CREATED",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_webhook_event_filter(ctx: EvalContext) -> NodeResult:
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; wu=WebhookUrl.create!(account:a,url:'http://host.docker.internal:19999/filter-test',events:['form.completed'],secret:{}); puts wu.id\"",
            "expect_success": True,
            "capture_stdout_as": "filter_webhook_id"
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
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "filter-test@example.com"
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
            "sql": "SELECT COUNT(*) AS cnt FROM webhook_events WHERE webhook_url_id = {{filter_webhook_id}} AND event_type = 'submission.created'",
            "expected_result": {
                "cnt": 0
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
            node_id="WEBHOOK_EVENT_FILTER",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="WEBHOOK_EVENT_FILTER",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_webhook_secret_headers(ctx: EvalContext) -> NodeResult:
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; wu=WebhookUrl.create!(account:a,url:'http://host.docker.internal:{{webhook_port}}/secret-test',events:['submission.created'],secret:{'X-Custom-Auth'=>'secret123','X-Webhook-Key'=>'eval-key'}); puts wu.id\"",
            "expect_success": True,
            "capture_stdout_as": "secret_webhook_id"
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "trigger": {
                "method": "POST",
                "path": "/api/submissions",
                "body": {
                    "template_id": "{{template_id}}",
                    "send_email": False,
                    "submitters": [
                        {
                            "role": "First Party",
                            "email": "secret-test@example.com"
                        }
                    ]
                }
            },
            "expect_delivery": {
                "timeout_ms": 15000,
                "headers_contain": {
                    "X-Custom-Auth": "secret123",
                    "X-Webhook-Key": "eval-key"
                }
            }
        }
        ok_2, ratio_2 = execute_primitive("P27", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P27"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P27"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "sql": "SELECT COUNT(*) AS cnt FROM webhook_events WHERE webhook_url_id = {{secret_webhook_id}} AND event_type = 'submission.created'",
            "expected_result": {
                "cnt": 1
            },
            "retry_ms": 5000
        }
        ok_3, ratio_3 = execute_primitive("P08", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P08"] = {"passed": True, "ratio": ratio_3}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="WEBHOOK_SECRET_HEADERS",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="WEBHOOK_SECRET_HEADERS",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_webhook_form_completed(ctx: EvalContext) -> NodeResult:
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; wu=WebhookUrl.find_or_create_by!(account:a,url:'http://host.docker.internal:{{webhook_port}}/form-complete',events:['form.completed'],secret:{}); puts wu.id\"",
            "expect_success": True,
            "capture_stdout_as": "fc_webhook_id"
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
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "fc-webhook@example.com",
                        "completed": True
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
            "sql": "SELECT COUNT(*) AS cnt FROM webhook_events WHERE webhook_url_id = {{fc_webhook_id}} AND event_type = 'form.completed'",
            "expected_result": {
                "cnt": 1
            },
            "retry_ms": 10000
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
            node_id="WEBHOOK_FORM_COMPLETED",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="WEBHOOK_FORM_COMPLETED",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_webhook_retry_behavior(ctx: EvalContext) -> NodeResult:
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; wu=WebhookUrl.create!(account:a,url:'http://host.docker.internal:19998/always-fail',events:['submission.created'],secret:{}); puts wu.id\"",
            "expect_success": True,
            "capture_stdout_as": "retry_webhook_id"
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
                "template_id": "{{template_id}}",
                "send_email": False,
                "submitters": [
                    {
                        "role": "First Party",
                        "email": "retry-test@example.com"
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
            "sql": "SELECT COUNT(*) AS cnt FROM webhook_events WHERE webhook_url_id = {{retry_webhook_id}} AND event_type = 'submission.created'",
            "expected_result": {
                "cnt": 1
            },
            "retry_ms": 10000
        }
        ok_4, ratio_4 = execute_primitive("P08", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P08"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "sql": "SELECT COUNT(*) AS cnt FROM webhook_attempts wa JOIN webhook_events we ON we.id = wa.webhook_event_id WHERE we.webhook_url_id = {{retry_webhook_id}}",
            "expected_result": {
                "cnt": {
                    "op": ">=",
                    "value": 1
                }
            },
            "retry_ms": 15000
        }
        ok_5, ratio_5 = execute_primitive("P08", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P08"] = {"passed": True, "ratio": ratio_5}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="WEBHOOK_RETRY_BEHAVIOR",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="WEBHOOK_RETRY_BEHAVIOR",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_webhook_payload_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/models/",
                "app/jobs/"
            ],
            "rubric_prompt": "GOAL: Judge the design of the outbound webhook delivery system.\nEVIDENCE: code-files listing for app/lib/serialize_for_webhook* and app/jobs/*webhook*.\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. A dedicated SerializeForWebhook (or similar) module/class formats the outbound payload.\n  C2. Payload contains the full submitter context (email, values, documents/attachments).\n  C3. The HTTP request sets a meaningful User-Agent (e.g. 'AppName/1.0 Webhook').\n  C4. Payload includes an event_type / type field so consumers can route.\n  C5. Retries use exponential backoff via perform_in / Sidekiq retries (not a busy loop).\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C5 satisfied.\n  - 2 (basic):      2 of C1-C5.\n  - 4 (good):       3 or 4 of C1-C5; retry logic or User-Agent often missing.\n  - 5 (excellent):  All 5 of C1-C5.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
            "score_range": [
                0,
                5
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

        score = min(llm_score, 5.0) if llm_score is not None else 0.0
        status = "PASSED" if score > 0 else "FAILED"

        return NodeResult(
            node_id="WEBHOOK_PAYLOAD_QUALITY",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="WEBHOOK_PAYLOAD_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "WEBHOOK_DELIVERY_SUBMISSION_CREATED": test_webhook_delivery_submission_created,
    "WEBHOOK_EVENT_FILTER": test_webhook_event_filter,
    "WEBHOOK_SECRET_HEADERS": test_webhook_secret_headers,
    "WEBHOOK_FORM_COMPLETED": test_webhook_form_completed,
    "WEBHOOK_RETRY_BEHAVIOR": test_webhook_retry_behavior,
    "WEBHOOK_PAYLOAD_QUALITY": test_webhook_payload_quality,
}
