from __future__ import annotations

from typing import Any


def _result_passed(pr: Any) -> bool:
    if hasattr(pr, "passed"):
        return bool(pr.passed)
    if hasattr(pr, "success"):
        return bool(pr.success)
    if isinstance(pr, dict):
        return bool(pr.get("passed", pr.get("success", False)))
    return bool(pr)


def _result_message(pr: Any) -> str:
    if hasattr(pr, "message"):
        return pr.message or ""
    if isinstance(pr, dict):
        return pr.get("message") or pr.get("msg") or ""
    return ""


def _result_data(pr: Any) -> Any:
    if hasattr(pr, "data"):
        return pr.data or {}
    if isinstance(pr, dict):
        return pr.get("data") or {}
    return {}


__all__ = ["_result_passed", "_result_message", "_result_data"]
