
from __future__ import annotations

import traceback
from typing import Any

from ..utils import NodeResult
from ..primitives import (
    PrimitiveResult,
    p01_file_exists,
    p02_file_content_match,
    p03_file_count,
    p04_http_request,
    p05_api_crud,
    p06_json_schema_match,
    p07_json_value_assert,
    p08_db_query,
    p09_db_table_exists,
    p10_db_column_check,
    p11_db_index_check,
    p12_docker_exec,
    p13_auth_login,
    p14_permission_check,
    p15_status_code_assert,
    p16_response_time_check,
    p17_llm_judge,
    p18_browser_interaction,
    p19_dom_assertion,
    p20_network_fault_inject,
    p21_websocket_connect,
    p22_graphql_query,
    p23_file_upload_download,
    p24_queue_job_check,
    p25_oauth_oidc_flow,
    p26_search_query,
    p27_webhook_delivery,
    p28_email_check,
    p29_multi_step_workflow,
)


PRIMITIVE_REGISTRY = {
    "P01": p01_file_exists,
    "P02": p02_file_content_match,
    "P03": p03_file_count,
    "P04": p04_http_request,
    "P05": p05_api_crud,
    "P06": p06_json_schema_match,
    "P07": p07_json_value_assert,
    "P08": p08_db_query,
    "P09": p09_db_table_exists,
    "P10": p10_db_column_check,
    "P11": p11_db_index_check,
    "P12": p12_docker_exec,
    "P13": p13_auth_login,
    "P14": p14_permission_check,
    "P15": p15_status_code_assert,
    "P16": p16_response_time_check,
    "P17": p17_llm_judge,
    "P18": p18_browser_interaction,
    "P19": p19_dom_assertion,
    "P20": p20_network_fault_inject,
    "P21": p21_websocket_connect,
    "P22": p22_graphql_query,
    "P23": p23_file_upload_download,
    "P24": p24_queue_job_check,
    "P25": p25_oauth_oidc_flow,
    "P26": p26_search_query,
    "P27": p27_webhook_delivery,
    "P28": p28_email_check,
    "P29": p29_multi_step_workflow,
}


def execute_primitive_chain(node: dict, context: dict) -> NodeResult:

    chain = node.get("primitive_chain", []) or []
    scoring = node.get("scoring", {}) or {}
    method = scoring.get("method", "binary")
    max_score = scoring.get("maxScore", 1)
    category = scoring.get("category", "")

    expected_reference_fail = (
        scoring.get("expected_reference_fail")
        or scoring.get("baseline_limitation_reason")
    )

    evidence: dict[str, Any] = {"primitive_results": []}
    passed_count = 0
    failed_step: str | None = None
    error_message: str | None = None
    p17_raw_score: float | None = None
    p17_skipped = False
    p17_skip_reason = ""

    if category not in ("RBAC", "Setup", "Authentication", "Deployment", "DataModel"):
        if context.get("auth_role") and context.get("auth_role") != "admin":
            try:
                from ..primitives import p13_auth_login as _p13
                _p13({"role": "admin"}, context)
            except Exception:
                pass

    for i, step in enumerate(chain):
        ptype = (step.get("type") or "").upper()
        inputs = dict(step.get("inputs", {}) or {})
        # Step-level conveniences: save_as / capture_as → fold into inputs so
        if step.get("save_as") and "save_as" not in inputs:
            inputs["save_as"] = step["save_as"]
            inputs.setdefault("as", step["save_as"])
        if step.get("capture_as") and "capture_as" not in inputs:
            inputs["capture_as"] = step["capture_as"]
        fn = PRIMITIVE_REGISTRY.get(ptype)
        if fn is None:
            error_message = f"Unknown primitive type: {ptype}"
            evidence["primitive_results"].append({
                "type": ptype, "passed": False, "error": error_message,
            })
            failed_step = f"{ptype} (step {i + 1})"
            break

        try:
            result: PrimitiveResult = fn(inputs, context)
        except Exception as exc:
            failed_step = f"{ptype} (step {i + 1})"
            error_message = (
                f"Exception in {ptype}: {exc}\n{traceback.format_exc()[:400]}"
            )
            evidence["primitive_results"].append({
                "type": ptype, "passed": False, "error": error_message,
            })
            break

        result_data = getattr(result, "data", None)
        ev_entry = {
            "type": ptype,
            "passed": getattr(result, "passed", False),
            "data_summary": _summarize_data(result_data),
            "error": getattr(result, "error", None),
            "elapsed_ms": getattr(result, "elapsed_ms", 0),
        }
        if ptype == "P17" and isinstance(result_data, dict):
            ev_entry["data"] = result_data
            if result_data.get("skipped"):
                p17_skipped = True
                p17_skip_reason = result_data.get("reason") or "skipped"
        evidence["primitive_results"].append(ev_entry)

        if getattr(result, "passed", False):
            passed_count += 1
            if ptype == "P17" and isinstance(result_data, dict):
                if result_data.get("skipped"):
                    p17_skipped = True
                    p17_skip_reason = result_data.get("reason") or "skipped"
                else:
                    raw = result_data.get("score")
                    if isinstance(raw, (int, float)):
                        p17_raw_score = float(raw)
        else:
            failed_step = f"{ptype} (step {i + 1})"
            if not error_message and getattr(result, "error", None):
                error_message = result.error
            if method == "binary":
                break

    total = len(chain)
    if method == "binary":
        final_score = (
            max_score if (total > 0 and passed_count == total and not error_message) else 0
        )
    elif method == "weighted":
        final_score = round((passed_count / total) * max_score, 2) if total > 0 else 0
    elif method == "llm-judge":
        if p17_skipped:
            final_score = 0
        elif p17_raw_score is not None and p17_raw_score >= 0:
            llm_data: dict | None = None
            for ev in reversed(evidence["primitive_results"]):
                if ev.get("type") == "P17" and isinstance(ev.get("data"), dict):
                    llm_data = ev["data"]
                    break
            score_range = None
            if llm_data and isinstance(llm_data.get("score_range"), (list, tuple)):
                score_range = llm_data["score_range"]
            else:
                last_p17 = next(
                    (s for s in reversed(chain) if (s.get("type") or "").upper() == "P17"),
                    {},
                )
                score_range = (last_p17.get("inputs", {}) or {}).get("score_range", [0, 10])
            hi = score_range[1] if isinstance(score_range, (list, tuple)) and len(score_range) >= 2 else 10
            hi = hi or 10
            final_score = round((p17_raw_score / hi) * max_score, 2)
        else:
            final_score = 0
    else:
        final_score = 0

    _had_exception = bool(error_message) and "Exception in" in (error_message or "")
    _passing = final_score >= max_score * 0.5
    if p17_skipped:
        status = "SKIPPED_LLM"
    elif _had_exception and final_score == 0:
        status = "ERROR"
    elif expected_reference_fail and not _passing:
        status = "EXPECTED_REFERENCE_FAIL"
    else:
        status = "EXECUTED"
    if expected_reference_fail:
        evidence["expected_reference_fail"] = expected_reference_fail
    if status == "SKIPPED_LLM":
        message = f"LLM judge SKIPPED ({p17_skip_reason})"
    elif status == "ERROR":
        message = error_message or "error"
    elif status == "EXPECTED_REFERENCE_FAIL":
        message = (
            f"EXPECTED_REFERENCE_FAIL ({passed_count}/{total} primitives passed): "
            f"{str(expected_reference_fail)[:140]}"
        )
    elif passed_count == total:
        message = f"All {total} primitives passed"
    else:
        message = f"{passed_count}/{total} primitives passed; failed at {failed_step} ({(error_message or '')[:80]})"

    return NodeResult(
        node_id=node["id"],
        status=status,
        score=final_score,
        maxScore=max_score,
        category=scoring.get("category", "Unknown"),
        subcategory=scoring.get("subcategory", ""),
        message=message,
        evidence=evidence,
    )


def _summarize_data(data: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, bytes):
        return data[:500]
    if isinstance(data, str):
        return data[:500] if len(data) > 500 else data
    if isinstance(data, dict):
        return {k: _summarize_data(v) for k, v in list(data.items())[:20]}
    if isinstance(data, list):
        return [_summarize_data(x) for x in data[:20]]
    return data
