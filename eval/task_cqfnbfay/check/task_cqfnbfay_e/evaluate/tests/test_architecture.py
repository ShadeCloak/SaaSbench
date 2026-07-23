from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_arch_code_organization(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/",
                "config/",
                "db/"
            ],
            "rubric_prompt": "GOAL: Judge whether the Rails-style codebase is organised into the conventional model/controller/view layers with proper extraction.\nEVIDENCE: code-files listing under app/ + Gemfile.\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. app/models, app/controllers and app/views are present as separate directories.\n  C2. Business logic is extracted into app/services, app/lib or concerns (controllers stay thin; controllers should NOT exceed ~200 LoC each on average).\n  C3. db/migrate/ exists and migration filenames follow the timestamped Rails convention.\n  C4. Gemfile groups dependencies meaningfully (e.g. group :development/:test/:production blocks).\n  C5. Models inherit from a project ApplicationRecord base class (not directly from ActiveRecord::Base).\n\nSCORING ANCHORS:\n  - 0 (none):       Fewer than 2 of C1-C5 satisfied; structure is ad-hoc.\n  - 2 (basic):      Exactly 2 of C1-C5 satisfied (typically C1 + C3 only).\n  - 4 (good):       3 or 4 of C1-C5 satisfied; controllers are mostly thin.\n  - 5 (excellent):  All 5 of C1-C5 satisfied; controllers visibly delegate to services/concerns.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="ARCH_CODE_ORGANIZATION",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ARCH_CODE_ORGANIZATION",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_arch_api_design(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/controllers/api/",
                "config/routes.rb"
            ],
            "rubric_prompt": "GOAL: Judge the quality of the public REST API surface in this Rails app.\nEVIDENCE: code-files listing for app/controllers/api/** + config/routes.rb.\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. API controllers live under an Api:: module / app/controllers/api/ namespace.\n  C2. Authentication is centralised via a before_action (e.g. require X-Auth-Token header).\n  C3. Errors return a uniform JSON envelope, e.g. {\"error\": \"<message>\"}.\n  C4. List endpoints support cursor-style pagination (after / before / page_after / next_cursor).\n  C5. HTTP status codes are used correctly: 200/201 success, 401 unauthenticated, 403 forbidden, 422 validation, 404 not-found.\n\nSCORING ANCHORS:\n  - 0 (none):       Fewer than 2 of C1-C5 satisfied; the API looks ad-hoc.\n  - 2 (basic):      Exactly 2 of C1-C5; API works but inconsistent.\n  - 4 (good):       3 or 4 of C1-C5; minor lapses (e.g. missing pagination on a few endpoints).\n  - 5 (excellent):  All 5 of C1-C5; consistent across every controller.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="ARCH_API_DESIGN",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ARCH_API_DESIGN",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_arch_route_organization(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "config/routes.rb"
            ],
            "rubric_prompt": "GOAL: Judge how routes.rb organises the URL surface.\nEVIDENCE: code-files listing for config/routes.rb (and any partial route files it imports).\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. API routes are grouped under namespace :api or scope '/api'.\n  C2. Resource nesting is used where it makes semantic sense (e.g. templates → submissions).\n  C3. Webhook / events / tools / oauth subsystems each have a clearly delimited block in routes.rb.\n  C4. Constraints or default formats are applied where appropriate (e.g. constraints: { format: :json }).\n  C5. Route names are RESTful (resources :foo) instead of ad-hoc string matchers.\n\nSCORING ANCHORS:\n  - 0 (none):       Fewer than 2 of C1-C5; routes file is a flat dump.\n  - 2 (basic):      Exactly 2 of C1-C5.\n  - 4 (good):       3 or 4 of C1-C5; structure is mostly clean.\n  - 5 (excellent):  All 5 of C1-C5.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="ARCH_ROUTE_ORGANIZATION",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ARCH_ROUTE_ORGANIZATION",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_arch_i18n_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 ={
            "evidence_type": "code_files",
            "files_to_sample": [
                "config/locales/i18n.yml",
                "Gemfile",
                "app/views/layouts/application.html.erb"
            ],
            "rubric_prompt": "GOAL: Judge the depth of internationalisation support.\nEVIDENCE: locale YAML file(s), Gemfile, application layout.\nSCORE RANGE: 0-5\n\nCONTEXT (task.md §2.3 + KB-030): The application is required to support 7 admin UI languages and 14 signing-form languages (per task.md §2.3) using Rails I18n with rails-i18n and twitter_cldr gems. The reference implementation may organize locale data as a single YAML file with multiple top-level locale keys (e.g. `en: &en`, `es: &es`, ...) using YAML anchors; this is an acceptable, idiomatic pattern.\n\nCRITERIA:\n  C1. Locale data exists under config/locales/ (one or more YAML/JSON files; single-file with multiple top-level locale anchors is acceptable).\n  C2. The combined locale data covers at least 7 distinct top-level locale codes intended for the admin UI (e.g. en, es, fr, de, it, pt, nl or regional variants such as en-US/en-GB).\n  C3. The combined locale data covers at least 14 distinct top-level locale codes for the signing form (e.g. additionally pl, uk, cs, he, ar, ko, ja).\n  C4. Gemfile declares rails-i18n and twitter_cldr (or equivalent) gems for locale fallback and CLDR-based formatting.\n  C5. The application layout / views invoke Rails I18n via t() / I18n.t helpers (not hard-coded English strings).\n\nSCORING ANCHORS:\n  - 0 (none):       0 or 1 of C1-C5 satisfied.\n  - 2 (basic):      2 of C1-C5; only a handful of locales.\n  - 4 (good):       3 or 4 of C1-C5; coverage is broad but a tier is missing (often C4).\n  - 5 (excellent):  All 5 of C1-C5; admin and public flows are both fully localised with proper gem stack.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="ARCH_I18N_QUALITY",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ARCH_I18N_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_arch_mailer_design(ctx: EvalContext) -> NodeResult:
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
                "app/views/submitter_mailer/",
                "app/views/user_mailer/",
                "app/views/template_mailer/",
                "app/views/settings_mailer/"
            ],
            "rubric_prompt": "GOAL: Judge the structure of the email-delivery layer.\nEVIDENCE: code-files listing for app/mailers/** and app/views/*_mailer/**.\nSCORE RANGE: 0-4\n\nCRITERIA:\n  C1. >= 4 distinct mailer classes exist (e.g. SubmitterMailer, UserMailer, TemplateMailer, SettingsMailer).\n  C2. Each mailer has at least one matching view template under app/views/.\n  C3. At least one mailer is invoked with deliver_later (Active Job async delivery).\n  C4. Mailer templates use a layout / partials and include some inline CSS or a shared style.\n\nSCORING ANCHORS:\n  - 0 (none):       0 or 1 of C1-C4 satisfied.\n  - 1 (basic):      2 of C1-C4 (typically C1 + C2 only).\n  - 3 (good):       3 of C1-C4.\n  - 4 (excellent):  All 4 of C1-C4 satisfied.\n\nOUTPUT: {\"score\": <0..4>, \"reasoning\": \"<1-3 sentences referencing C1..C4>\"}",
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
            node_id="ARCH_MAILER_DESIGN",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ARCH_MAILER_DESIGN",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_arch_audit_trail_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "lib/submissions/generate_audit_trail.rb",
                "lib/submissions/ensure_audit_generated.rb",
                "app/models/submission_event.rb",
                "lib/submission_events.rb",
                "lib/submissions.rb"
            ],
            "rubric_prompt": "GOAL: Judge the audit-trail subsystem.\nEVIDENCE: code files for the audit-trail PDF generator (lib/submissions/generate_audit_trail.rb,\nlib/submissions/ensure_audit_generated.rb) plus the SubmissionEvent event-stream model\n(app/models/submission_event.rb, lib/submission_events.rb) that backs the timeline.\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. A GenerateAuditTrail (or comparable) module renders a per-submission audit PDF.\n  C2. Document-level integrity is anchored by SHA256 (or stronger) checksums recorded in the audit log.\n  C3. Either a configurable cap exists on the number of checksums per audit (e.g. CHECKSUM_LIMIT) OR\n      a Zip64-style overflow handling exists for very large submissions.\n  C4. Party-state changes are recorded as an append-only event stream\n      (e.g. SubmissionEvent rows: send_email -> open_email -> view_form -> start_form -> complete_form / decline_form),\n      regardless of whether the model is named `audit_log`, `submission_event`, or similar.\n  C5. Inclusion of field values and the sender e-mail is opt-in via flags or per-account configuration\n      (e.g. WITH_AUDIT_VALUES / WITH_AUDIT_SENDER, or AccountConfig keys).\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C5.\n  - 2 (basic):      2 of C1-C5.\n  - 4 (good):       3 or 4 of C1-C5; flags or cap missing.\n  - 5 (excellent):  All 5 of C1-C5.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="ARCH_AUDIT_TRAIL_QUALITY",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="ARCH_AUDIT_TRAIL_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "ARCH_CODE_ORGANIZATION": test_arch_code_organization,
    "ARCH_API_DESIGN": test_arch_api_design,
    "ARCH_ROUTE_ORGANIZATION": test_arch_route_organization,
    "ARCH_I18N_QUALITY": test_arch_i18n_quality,
    "ARCH_MAILER_DESIGN": test_arch_mailer_design,
    "ARCH_AUDIT_TRAIL_QUALITY": test_arch_audit_trail_quality,
}
