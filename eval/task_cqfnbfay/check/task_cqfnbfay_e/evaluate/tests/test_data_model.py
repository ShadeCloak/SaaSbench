from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_db_tables_core(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "tables": [
                "accounts",
                "users",
                "templates",
                "submissions",
                "submitters",
                "access_tokens"
            ]
        }
        ok_0, ratio_0 = execute_primitive("P09", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P09"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P09"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 4, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_TABLES_CORE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_TABLES_CORE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_tables_supporting(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "tables": [
                "account_configs",
                "encrypted_configs",
                "template_folders",
                "submission_events",
                "completed_submitters",
                "completed_documents",
                "document_generation_events",
                "email_events",
                "email_messages",
                "search_entries",
                "lock_events",
                "webhook_urls",
                "webhook_events",
                "webhook_attempts"
            ]
        }
        ok_0, ratio_0 = execute_primitive("P09", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P09"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P09"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 4, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_TABLES_SUPPORTING",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_TABLES_SUPPORTING",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_tables_oauth(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "tables": [
                "oauth_applications",
                "oauth_access_grants",
                "oauth_access_tokens"
            ]
        }
        ok_0, ratio_0 = execute_primitive("P09", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P09"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P09"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 2, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_TABLES_OAUTH",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_TABLES_OAUTH",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_columns_users(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "table": "users",
            "expected_columns": [
                "id",
                "first_name",
                "last_name",
                "email",
                "role",
                "encrypted_password",
                "account_id",
                "reset_password_token",
                "sign_in_count",
                "failed_attempts",
                "unlock_token",
                "locked_at",
                "archived_at",
                "uuid",
                "otp_secret",
                "otp_required_for_login"
            ]
        }
        ok_0, ratio_0 = execute_primitive("P10", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P10"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P10"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 3, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_COLUMNS_USERS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_COLUMNS_USERS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_columns_templates(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "table": "templates",
            "expected_columns": [
                "id",
                "slug",
                "name",
                "schema",
                "fields",
                "submitters",
                "author_id",
                "account_id",
                "folder_id",
                "archived_at",
                "source",
                "external_id",
                "preferences",
                "shared_link",
                "created_at",
                "updated_at"
            ]
        }
        ok_0, ratio_0 = execute_primitive("P10", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P10"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P10"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 3, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_COLUMNS_TEMPLATES",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_COLUMNS_TEMPLATES",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_columns_submitters(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "table": "submitters",
            "expected_columns": [
                "id",
                "submission_id",
                "account_id",
                "uuid",
                "email",
                "slug",
                "values",
                "ua",
                "ip",
                "sent_at",
                "opened_at",
                "completed_at",
                "declined_at",
                "name",
                "phone",
                "external_id",
                "preferences",
                "metadata"
            ]
        }
        ok_0, ratio_0 = execute_primitive("P10", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P10"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P10"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 3, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_COLUMNS_SUBMITTERS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_COLUMNS_SUBMITTERS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_columns_submissions(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "table": "submissions",
            "expected_columns": [
                "id",
                "account_id",
                "template_id",
                "slug",
                "template_fields",
                "template_schema",
                "template_submitters",
                "source",
                "submitters_order",
                "preferences",
                "expire_at",
                "archived_at",
                "created_at",
                "updated_at"
            ]
        }
        ok_0, ratio_0 = execute_primitive("P10", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P10"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P10"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 3, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_COLUMNS_SUBMISSIONS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_COLUMNS_SUBMISSIONS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_columns_webhooks(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "table": "webhook_urls",
            "expected_columns": [
                "id",
                "account_id",
                "url",
                "events",
                "sha1",
                "secret",
                "created_at",
                "updated_at"
            ]
        }
        ok_0, ratio_0 = execute_primitive("P10", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P10"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P10"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "table": "webhook_events",
            "expected_columns": [
                "id",
                "uuid",
                "webhook_url_id",
                "account_id",
                "record_id",
                "record_type",
                "event_type",
                "status"
            ]
        }
        ok_1, ratio_1 = execute_primitive("P10", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P10"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P10"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "table": "webhook_attempts",
            "expected_columns": [
                "id",
                "webhook_event_id",
                "response_body",
                "response_status_code",
                "attempt"
            ]
        }
        ok_2, ratio_2 = execute_primitive("P10", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P10"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P10"] = {"passed": True, "ratio": ratio_2}

        score = round((pass_count / 3) * 3, 2) if 3 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_COLUMNS_WEBHOOKS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_COLUMNS_WEBHOOKS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_index_submitters(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "table": "submitters",
            "expected_indexes": [
                {
                    "columns": [
                        "account_id"
                    ]
                },
                {
                    "columns": [
                        "submission_id"
                    ]
                },
                {
                    "columns": [
                        "slug"
                    ]
                },
                {
                    "columns": [
                        "email"
                    ]
                }
            ]
        }
        ok_0, ratio_0 = execute_primitive("P11", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P11"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P11"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 3, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_INDEX_SUBMITTERS",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_INDEX_SUBMITTERS",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_index_templates(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "table": "templates",
            "expected_indexes": [
                {
                    "columns": [
                        "account_id"
                    ]
                },
                {
                    "columns": [
                        "slug"
                    ]
                },
                {
                    "columns": [
                        "external_id"
                    ]
                }
            ]
        }
        ok_0, ratio_0 = execute_primitive("P11", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P11"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P11"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 2, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_INDEX_TEMPLATES",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_INDEX_TEMPLATES",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_index_search_entries(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "table": "search_entries",
            "expected_indexes": [
                {
                    "columns": [
                        "record_type"
                    ]
                }
            ]
        }
        ok_0, ratio_0 = execute_primitive("P11", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P11"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P11"] = {"passed": True, "ratio": ratio_0}

        score = round((pass_count / 1) * 2, 2) if 1 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DB_INDEX_SEARCH_ENTRIES",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_INDEX_SEARCH_ENTRIES",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


def test_db_design_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "db/",
                "app/models/"
            ],
            "rubric_prompt": "GOAL: Judge the relational database design.\nEVIDENCE: code-files listing for db/migrate/, db/schema.rb (or db/structure.sql) and app/models/**.\nSCORE RANGE: 0-6\n\nCRITERIA:\n  C1. Indexes are appropriate: foreign-key indexes, unique indexes on natural keys, GIN/JSONB or tsvector indexes where needed.\n  C2. Migration files are timestamped and grouped logically by feature.\n  C3. Models declare validates / has_many / belongs_to / scope, not just empty class bodies.\n  C4. JSON / JSONB columns (fields, schema, submitters, values) use a documented serializer.\n  C5. A UUID column exists on user-facing public records (for non-guessable URLs).\n  C6. Sensitive columns use ActiveRecord encrypted attributes (e.g. encrypts :api_key).\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C6 satisfied.\n  - 2 (basic):      2 of C1-C6 (usually basic indexes + migrations only).\n  - 4 (good):       3 or 4 of C1-C6; encryption or UUIDs typically missing.\n  - 6 (excellent):  5 or 6 of C1-C6; design is production-ready.\n\nOUTPUT: {\"score\": <0..6>, \"reasoning\": \"<1-3 sentences referencing C1..C6>\"}",
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
            node_id="DB_DESIGN_QUALITY",
            status=status,
            score=score,
            max_score=6.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DB_DESIGN_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=6.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "DB_TABLES_CORE": test_db_tables_core,
    "DB_TABLES_SUPPORTING": test_db_tables_supporting,
    "DB_TABLES_OAUTH": test_db_tables_oauth,
    "DB_COLUMNS_USERS": test_db_columns_users,
    "DB_COLUMNS_TEMPLATES": test_db_columns_templates,
    "DB_COLUMNS_SUBMITTERS": test_db_columns_submitters,
    "DB_COLUMNS_SUBMISSIONS": test_db_columns_submissions,
    "DB_COLUMNS_WEBHOOKS": test_db_columns_webhooks,
    "DB_INDEX_SUBMITTERS": test_db_index_submitters,
    "DB_INDEX_TEMPLATES": test_db_index_templates,
    "DB_INDEX_SEARCH_ENTRIES": test_db_index_search_entries,
    "DB_DESIGN_QUALITY": test_db_design_quality,
}
