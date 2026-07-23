from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_frontend_dom_dashboard(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 3
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "method": "GET",
            "path": "/"
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
                200,
                302
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
            "url": "/",
            "authenticate": True,
            "assertions": [
                {
                    "selector": "a[href*=\"/templates\"]",
                    "shouldExist": True
                },
                {
                    "selector": ".menu, .dropdown-content, #drawer",
                    "shouldExist": True
                },
                {
                    "selector": "dashboard-dropzone, a[href*=\"/templates/new\"]",
                    "shouldExist": True
                }
            ]
        }
        ok_2, ratio_2 = execute_primitive("P19", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P19"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P19"] = {"passed": True, "ratio": ratio_2}

        score = round((pass_count / 3) * 3, 2) if 3 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="FRONTEND_DOM_DASHBOARD",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="FRONTEND_DOM_DASHBOARD",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_frontend_dom_signing_form(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"t=Template.find_by(name:'Eval Template'); t.update_columns(shared_link:true, archived_at:nil) if t; puts t&.slug\"",
            "expect_success": True,
            "capture_stdout_as": "template_slug"
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
            "path": "/d/{{template_slug}}",
            "headers": {"Accept": "text/html"}
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
                302
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
            "url": "/d/{{template_slug}}",
            "assertions": [
                {
                    "selector": "input[type=email], input[name*=email], input[placeholder*=email]",
                    "shouldExist": True
                },
                {
                    "selector": "button[type=submit], input[type=submit], button.btn",
                    "shouldExist": True
                },
                {
                    "selector": "form, [data-controller]",
                    "shouldExist": True
                }
            ]
        }
        ok_3, ratio_3 = execute_primitive("P19", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P19"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P19"] = {"passed": True, "ratio": ratio_3}

        score = round((pass_count / 4) * 4, 2) if 4 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="FRONTEND_DOM_SIGNING_FORM",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="FRONTEND_DOM_SIGNING_FORM",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_frontend_dashboard_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/controllers/dashboard_controller.rb",
                "app/controllers/templates_dashboard_controller.rb",
                "app/controllers/submissions_dashboard_controller.rb",
                "app/views/templates_dashboard/index.html.erb",
                "app/views/submissions_dashboard/index.html.erb",
                "app/views/dashboard/_toggle_view.html.erb",
                "app/views/layouts/application.html.erb"
            ],
            "rubric_prompt": "GOAL: Judge the dashboard implementation quality (server-rendered ERB views + Hotwire/Turbo dispatch, per task.md §6.1 + §6.2 Dashboard).\nEVIDENCE: dashboard controller(s) + index ERB views + layout.\nSCORE RANGE: 0-5\n\nCONTEXT (task.md §6.2 Dashboard `/`): The root path renders a dashboard with: a Template list (name + author), a 'Create' button, a search input, an empty-state CTA, a view toggle between Templates and Submissions, and a dashboard dropzone for drag-and-drop PDF upload to instantly create a new template. The reference implementation may dispatch `/` to TemplatesDashboardController or SubmissionsDashboardController based on a `dashboard_view` cookie, and renders a marketing landing page when not signed in.\n\nCRITERIA:\n  C1. Top-level navigation / header is present in the application layout (e.g. <nav>, <header>, or a topbar partial) with brand + user menu.\n  C2. Templates dashboard view renders a primary content region with a list / table / card grid of templates (iterates @templates / Template records).\n  C3. A visible 'Create' / 'New' CTA (button or link) is rendered, linking to template creation flow.\n  C4. A search or filter input is present on the dashboard (input[type=search] or filter form).\n  C5. CSS class names show a modern utility framework — Tailwind classes (`flex|grid|p-\\d+|w-\\d+|rounded-xl`) or DaisyUI tokens (`btn|card|badge`).\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C5; the views are placeholder or missing.\n  - 2 (basic):      2 of C1-C5; navigation present but content is sparse.\n  - 4 (good):       3 or 4 of C1-C5; usable but missing one major affordance (e.g. search or view toggle).\n  - 5 (excellent):  All 5 of C1-C5; coherent operator console with Tailwind/DaisyUI styling.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="FRONTEND_DASHBOARD_QUALITY",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="FRONTEND_DASHBOARD_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_frontend_signing_form_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/controllers/start_form_controller.rb",
                "app/controllers/submit_form_controller.rb",
                "app/views/start_form/show.html.erb",
                "app/views/submit_form/show.html.erb",
                "app/views/layouts/form.html.erb",
                "app/javascript/submission_form"
            ],
            "rubric_prompt": "GOAL: Judge the public signer-facing form implementation (Multi-Step Signing Form per task.md §4.5 + §6.2).\nEVIDENCE: start_form / submit_form controllers + their show.html.erb views + form layout + Vue submission_form components.\nSCORE RANGE: 0-5\n\nCONTEXT (task.md §6.2 + §4.5 + KB-033 + KB-066): The signing form is reachable via /d/{template_slug} (start_form_controller, the shared link entry per KB-033) and /s/{submitter_slug} (submit_form_controller, the per-submitter URL per KB-066). Both endpoints opt out of authentication via `skip_before_action :authenticate_user!` and `skip_authorization_check`. The form must be multi-step with mobile-responsive layout, support a signature pad (canvas), file upload dropzone, and optional 2FA verification.\n\nCRITERIA:\n  C1. start_form_controller and submit_form_controller exist and explicitly skip authentication + authorization (skip_before_action :authenticate_user! + skip_authorization_check) — public access.\n  C2. The form view contains a <form> element (or form_with / form_for) wrapping signer input fields, plus an email input field for the signer.\n  C3. A primary action button labelled Start / Continue / Submit / Sign is rendered.\n  C4. CSS evidence of modern styling (Tailwind / DaisyUI tokens — `flex|grid|p-\\d+|btn|card|rounded-xl`) and a mobile-friendly viewport meta in the form layout.\n  C5. Vue submission_form components exist (e.g. signature pad, multi-step navigation, file dropzone) under app/javascript/submission_form/.\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C5.\n  - 2 (basic):      2 of C1-C5; bare functional form.\n  - 4 (good):       3 or 4 of C1-C5; mostly polished but missing viewport or Vue components.\n  - 5 (excellent):  All 5 of C1-C5.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="FRONTEND_SIGNING_FORM_QUALITY",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="FRONTEND_SIGNING_FORM_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_frontend_template_builder(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 ={
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/javascript/template_builder/builder.vue",
                "app/javascript/template_builder/area.vue",
                "app/javascript/template_builder/field_type.vue",
                "app/javascript/template_builder/conditions_modal.vue",
                "app/javascript/template_builder/dropzone.vue",
                "app/javascript/template_builder/dynamic_document.vue",
                "app/javascript/template_builder/controls.vue"
            ],
            "rubric_prompt": "GOAL: Judge the maturity of the Vue 3 template-builder front-end.\nEVIDENCE: representative .vue components from app/javascript/template_builder/.\nSCORE RANGE: 0-5\n\nCONTEXT (task.md §6.2 Template Builder + KB-019 + KB-054): The template builder is a Vue 3 SPA at /templates/:id/edit comprising 42 components. It supports WYSIWYG PDF field placement with drag-and-drop and resize handles, a field palette covering all 16 field types (text, signature, date, checkbox, image, file, initials, stamp, payment, phone, number, cells, radio, multiple, select, formula), multi-submitter role management, a condition builder for conditional fields, a formula editor for computed fields, and a dynamic document HTML editor. Field area coordinates are 0-1 ratio values relative to the page (KB-019).\n\nCRITERIA:\n  C1. Vue 3 single-file components: each .vue file uses <template> + <script> sections; components register via export default {} or <script setup>; components are composable (e.g. builder.vue imports area.vue, field_type.vue, etc.).\n  C2. Drag-and-drop field placement is implemented (e.g. mousedown/mousemove handlers in area.vue/dropzone.vue; an `area` object with x, y, w, h ratio coordinates per KB-019).\n  C3. Multi-party signer management is implemented (a roles list / add-submitter UI, evident in builder.vue or a dedicated roles modal; references to `submitters` array).\n  C4. A field-type picker that exposes the 16 field types in field_type.vue (or equivalent) — look for a list/array of type identifiers covering text/signature/date/checkbox/etc.\n  C5. A condition builder (conditions_modal.vue) for conditional fields and / or a formula editor / dynamic-document editor (dynamic_document.vue) for advanced authoring.\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C5.\n  - 2 (basic):      2 of C1-C5; basic editor only.\n  - 4 (good):       3 or 4 of C1-C5; missing one advanced feature.\n  - 5 (excellent):  All 5 of C1-C5.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="FRONTEND_TEMPLATE_BUILDER",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="FRONTEND_TEMPLATE_BUILDER",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


def test_frontend_responsive_design(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "app/views/layouts/",
                "app/javascript/"
            ],
            "rubric_prompt": "GOAL: Judge whether the front-end is genuinely responsive.\nEVIDENCE: code-files listing for app/views/layouts/** and app/javascript/**.\nSCORE RANGE: 0-4\n\nCRITERIA:\n  C1. The application layout includes <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">.\n  C2. Tailwind responsive prefixes (`sm:`, `md:`, `lg:`, `xl:`) appear in templates / components.\n  C3. The signing form has explicit mobile-first styling (e.g. min-h-screen, single-column at small breakpoints).\n  C4. Navigation collapses into a hamburger / drawer on small screens (component or class evidence).\n\nSCORING ANCHORS:\n  - 0 (none):       0 or 1 of C1-C4.\n  - 1 (basic):      2 of C1-C4.\n  - 3 (good):       3 of C1-C4.\n  - 4 (excellent):  All 4 of C1-C4.\n\nOUTPUT: {\"score\": <0..4>, \"reasoning\": \"<1-3 sentences referencing C1..C4>\"}",
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
            node_id="FRONTEND_RESPONSIVE_DESIGN",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="FRONTEND_RESPONSIVE_DESIGN",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_frontend_settings_pages(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "config/routes.rb",
                "app/controllers/",
                "app/views/settings/"
            ],
            "rubric_prompt": "GOAL: Judge the breadth of the operator-settings surface.\nEVIDENCE: code-files listing for app/controllers/settings/** and app/views/settings/**.\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. A settings/ namespace exists (controller + route).\n  C2. A Users / Team management page exists.\n  C3. An API-token management page exists (display + revoke).\n  C4. A Webhook configuration page exists.\n  C5. Email / SMTP and Storage configuration pages exist (count as one criterion when both present).\n  C6. Notifications configuration (BCC, completion notice, reminders) is exposed.\n\nSCORING ANCHORS:\n  - 0 (none):       <= 1 of C1-C6.\n  - 2 (basic):      2 of C1-C6 (typically C1 + C2 only).\n  - 4 (good):       3 or 4 of C1-C6; webhooks or notifications often missing.\n  - 5 (excellent):  5 or 6 of C1-C6 satisfied.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C6>\"}",
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
            node_id="FRONTEND_SETTINGS_PAGES",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="FRONTEND_SETTINGS_PAGES",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "FRONTEND_DOM_DASHBOARD": test_frontend_dom_dashboard,
    "FRONTEND_DOM_SIGNING_FORM": test_frontend_dom_signing_form,
    "FRONTEND_DASHBOARD_QUALITY": test_frontend_dashboard_quality,
    "FRONTEND_SIGNING_FORM_QUALITY": test_frontend_signing_form_quality,
    "FRONTEND_TEMPLATE_BUILDER": test_frontend_template_builder,
    "FRONTEND_RESPONSIVE_DESIGN": test_frontend_responsive_design,
    "FRONTEND_SETTINGS_PAGES": test_frontend_settings_pages,
}
