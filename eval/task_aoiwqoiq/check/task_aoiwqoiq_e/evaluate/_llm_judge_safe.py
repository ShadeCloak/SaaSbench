
from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger("llm_judge_safe")

ContentPart = dict
Content = Union[str, List[ContentPart]]


@dataclass
class SafeLLMResult:

    score: Optional[int] = None
    raw: str = ""
    skipped: bool = False
    llm_api_failure: bool = False
    parse_failure: bool = False
    error: str = ""
    exception_class: str = ""
    samples_count: int = 0

    @property
    def passed(self) -> bool:
        return self.score is not None and not self.skipped

    def to_evidence(self) -> dict:
        ev: dict = {
            "samples_count": self.samples_count,
            "raw": self.raw[:200],
        }
        if self.score is not None:
            ev["score"] = self.score
        if self.skipped:
            ev["llm_judge_skipped"] = True
            ev["reason"] = self.error or "skipped"
        if self.llm_api_failure:
            ev["llm_api_failure"] = True
            ev["exception_class"] = self.exception_class
            ev["error"] = self.error[:300]
        if self.parse_failure:
            ev["parse_failure"] = True
            ev["error"] = self.error[:300]
        return ev

    def reason(self) -> str:
        if self.passed:
            return f"score={self.score}"
        if self.llm_api_failure:
            return f"LLM API failure ({self.exception_class}: {self.error[:120]})"
        if self.skipped:
            return f"skipped ({self.error or 'no api key'})"
        if self.parse_failure:
            return "model reply contained no integer"
        return "unknown failure"


def _make_skip(*, reason: str = "LLM_API_KEY unset",
               api_failure: bool = False,
               exc: Optional[BaseException] = None,
               samples_count: int = 0) -> SafeLLMResult:
    return SafeLLMResult(
        skipped=True,
        llm_api_failure=api_failure,
        error=(str(exc) if exc is not None else reason)[:300],
        exception_class=(type(exc).__name__ if exc is not None else ""),
        samples_count=samples_count,
    )


_RETRY_BACKOFFS_SEC = (1.0, 4.0, 16.0)


def _is_retriable(exc: BaseException) -> bool:
    name = type(exc).__name__
    msg = str(exc).lower()

    if name in ("BadRequestError", "AuthenticationError", "PermissionDeniedError",
                "NotFoundError", "UnprocessableEntityError"):
        return False
    if any(s in msg for s in ("400 ", "401 ", "403 ", "404 ", "422 ",
                               "invalid_request", "invalid api key",
                               "model_not_found", "context_length")):
        return False

    if name in ("APITimeoutError", "APIConnectionError", "InternalServerError",
                "RateLimitError", "ServiceUnavailableError"):
        return True
    if any(s in msg for s in ("timeout", "timed out",
                               "connection", "reset by peer", "broken pipe",
                               "no healthy upstream", "service unavailable",
                               "internal server error", "bad gateway",
                               "gateway timeout", "rate limit",
                               "5xx", "503", "502", "504", "500 ",
                               "429 ", "rate_limit_exceeded")):
        return True

    return True


def safe_chat_completion(*,
                         messages: Sequence[dict],
                         model: str,
                         api_key: str,
                         api_base: str = "",
                         temperature: float = 0.0,
                         timeout: float = 120.0,
                         **extra_kwargs: Any) -> SafeLLMResult:
    if not api_key:
        return _make_skip(reason="LLM_API_KEY unset")

    try:
        from openai import OpenAI
    except Exception as e:
        logger.warning("openai SDK import failed: %s", e)
        return _make_skip(api_failure=True, exc=e)

    client_kwargs: dict = {"api_key": api_key}
    if api_base:
        client_kwargs["base_url"] = api_base

    import time as _time

    last_exc: Optional[BaseException] = None
    _create_kwargs: dict = {
        "model": model,
        "messages": list(messages),
        "temperature": temperature,
        "timeout": timeout,
    }
    _create_kwargs.update(extra_kwargs)
    for attempt in range(len(_RETRY_BACKOFFS_SEC) + 1):
        try:
            client = OpenAI(**client_kwargs)
            resp = client.chat.completions.create(**_create_kwargs)
            raw = (resp.choices[0].message.content or "").strip()
            if not raw:
                _fr = getattr(resp.choices[0], "finish_reason", None)
                _cur_mt = _create_kwargs.get("max_tokens")
                if _fr in ("length", "max_tokens") and isinstance(_cur_mt, int) and _cur_mt < 8192:
                    _create_kwargs["max_tokens"] = 8192
                    last_exc = RuntimeError(
                        "empty LLM reply (output truncated at max_tokens=%s; retrying with 8192)" % _cur_mt)
                    if attempt < len(_RETRY_BACKOFFS_SEC):
                        continue
                    return _make_skip(api_failure=True, exc=last_exc)
                last_exc = RuntimeError("empty LLM reply (no text content)")
                if attempt < len(_RETRY_BACKOFFS_SEC):
                    _time.sleep(_RETRY_BACKOFFS_SEC[attempt])
                    continue
                return _make_skip(api_failure=True, exc=last_exc)
            try:
                import os as _os, json as _json, time as _t
                _en = _os.environ.get("JUDGE_IO_LOG")
                if _en:
                    _path = (_os.path.join(_os.getcwd(), "judge_io.jsonl")
                             if _en in ("1", "true", "on", "yes") else _en)
                    _msgs = []
                    for _m in (messages or []):
                        if isinstance(_m, dict):
                            _msgs.append({"role": _m.get("role"),
                                          "content": str(_m.get("content"))[:80000]})
                    with open(_path, "a") as _fh:
                        _fh.write(_json.dumps({"ts": _t.time(), "model": model,
                                               "messages": _msgs, "raw": raw},
                                              ensure_ascii=False) + "\n")
            except Exception:
                pass
            return SafeLLMResult(raw=raw)
        except Exception as e:
            last_exc = e
            _emsg = str(e).lower()
            _dropped = False
            for _p in ("temperature", "top_p"):
                if _p in _emsg and _p in _create_kwargs and (
                        "deprecat" in _emsg or "unsupported" in _emsg
                        or "not support" in _emsg or "invalid" in _emsg):
                    _create_kwargs.pop(_p, None)
                    _dropped = True
            if _dropped and attempt < len(_RETRY_BACKOFFS_SEC):
                logger.warning(
                    "LLM judge API rejected param (attempt %d); dropped and retrying: %s",
                    attempt + 1, e,
                )
                continue
            if attempt >= len(_RETRY_BACKOFFS_SEC) or not _is_retriable(e):
                logger.warning(
                    "LLM judge API call failed (attempt %d, giving up): %s",
                    attempt + 1, e,
                )
                break
            sleep_sec = _RETRY_BACKOFFS_SEC[attempt]
            logger.warning(
                "LLM judge API call failed (attempt %d, retrying in %ss): %s",
                attempt + 1, sleep_sec, e,
            )
            _time.sleep(sleep_sec)

    return _make_skip(api_failure=True, exc=last_exc)


def _extract_score(raw: str) -> Optional[int]:
    if not raw:
        return None
    s = raw.strip()

    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "score" in obj:
            return int(obj["score"])
    except Exception:
        pass

    score_matches = re.findall(r'"score"\s*:\s*(-?\d+)', s)
    if score_matches:
        return int(score_matches[-1])

    m = re.search(r'\*\*\s*(-?\d+)\s*\*\*\s*$', s)
    if m:
        return int(m.group(1))

    for line in reversed(s.splitlines()):
        cleaned = line.strip().strip('`').strip()
        if re.fullmatch(r'-?\d+', cleaned):
            return int(cleaned)

    m = re.search(r'-?\d+', s)
    return int(m.group()) if m else None


def _compose_judge_prompt(rubric_prompt: str,
                          samples: Iterable[Tuple[str, str]],
                          score_range: Tuple[int, int]) -> str:
    composed = rubric_prompt + "\n\n=== FILE SAMPLES ===\n"
    for path, text in samples:
        composed += f"\n--- {path} ---\n{text}\n"
    composed += (
        f"\n=== INSTRUCTIONS ===\n"
        f"You are a scoring function with no tools. Do not investigate, ask for more "
        f"files, or explain your reasoning. Based only on the evidence above, "
        f"immediately return ONLY a single integer in "
        f"[{score_range[0]},{score_range[1]}]; no other text, no explanation."
    )
    return composed


def safe_llm_judge_call(*,
                        rubric_prompt: str,
                        samples: Iterable[Tuple[str, str]] = (),
                        score_range: Tuple[int, int] = (0, 5),
                        model: str,
                        api_key: str,
                        api_base: str = "",
                        temperature: float = 0.0,
                        timeout: float = 120.0,
                        **extra_kwargs: Any) -> SafeLLMResult:
    sample_list: List[Tuple[str, str]] = list(samples)
    sr = (int(score_range[0]), int(score_range[1]))

    prompt = _compose_judge_prompt(rubric_prompt, sample_list, sr)
    res = safe_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        api_key=api_key,
        api_base=api_base,
        temperature=temperature,
        timeout=timeout,
        **extra_kwargs,
    )
    res.samples_count = len(sample_list)
    if res.skipped:
        return res

    parsed = _extract_score(res.raw)
    if parsed is None:
        res.parse_failure = True
        res.error = "model reply contains no parseable score"
        return res

    res.score = max(sr[0], min(parsed, sr[1]))
    return res


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _encode_image_data_url(path: str, mime_hint: Optional[str] = None) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"image not found: {path}")
    if mime_hint:
        mime = mime_hint
    else:
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(ext, "image/png")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _compose_multimodal_content(rubric_prompt: str,
                                text_samples: Iterable[Tuple[str, str]],
                                image_paths: Iterable[str],
                                score_range: Tuple[int, int],
                                require_json: bool) -> List[ContentPart]:
    sr_lo, sr_hi = int(score_range[0]), int(score_range[1])
    parts: List[ContentPart] = [{"type": "text", "text": rubric_prompt}]
    for label, text in text_samples:
        parts.append({"type": "text",
                      "text": f"\n=== {label} ===\n{text}\n"})
    for p in image_paths:
        parts.append({"type": "image_url",
                      "image_url": {"url": _encode_image_data_url(p)}})
    if require_json:
        instr = (
            f"\n=== INSTRUCTIONS ===\n"
            "You are a scoring function with no tools; do not investigate, ask for "
            "more files, or describe a plan. "
            f"Score the implementation from {sr_lo} to {sr_hi} "
            "based STRICTLY on the rubric and the visual/textual evidence above. "
            'Reply with ONLY a JSON object of the form '
            '{"score": <integer>, "reasoning": "<≤120 words citing concrete '
            'visual elements or file paths>"}; no markdown, no extra text.'
        )
    else:
        instr = (
            f"\n=== INSTRUCTIONS ===\n"
            "You are a scoring function with no tools; do not investigate or explain. "
            f"Return ONLY a single integer in [{sr_lo},{sr_hi}]; "
            "no other text, no explanation."
        )
    parts.append({"type": "text", "text": instr})
    return parts


def safe_multimodal_judge_call(*,
                               rubric_prompt: str,
                               image_paths: Sequence[str],
                               text_samples: Iterable[Tuple[str, str]] = (),
                               score_range: Tuple[int, int] = (0, 5),
                               model: str,
                               api_key: str,
                               api_base: str = "",
                               temperature: float = 0.0,
                               timeout: float = 120.0,
                               max_tokens: int = 8192,
                               require_json: bool = True,
                               **extra_kwargs: Any) -> SafeLLMResult:
    sample_list: List[Tuple[str, str]] = list(text_samples)
    image_list: List[str] = list(image_paths)
    sr = (int(score_range[0]), int(score_range[1]))

    if not image_list:
        return _make_skip(reason="no images supplied to multimodal judge",
                          samples_count=len(sample_list))

    try:
        content = _compose_multimodal_content(rubric_prompt, sample_list,
                                              image_list, sr, require_json)
    except Exception as e:
        return _make_skip(reason=f"multimodal content compose failed: {e}",
                          exc=e, samples_count=len(sample_list))

    if require_json and "response_format" not in extra_kwargs:
        extra_kwargs["response_format"] = {"type": "json_object"}

    res = safe_chat_completion(
        messages=[{"role": "user", "content": content}],
        model=model,
        api_key=api_key,
        api_base=api_base,
        temperature=temperature,
        timeout=timeout,
        max_tokens=max_tokens,
        **extra_kwargs,
    )
    res.samples_count = len(sample_list) + len(image_list)
    if res.skipped:
        return res

    parsed_score: Optional[int] = None
    parsed_reason = ""
    if require_json:
        try:
            obj = json.loads(res.raw)
            parsed_score = int(obj.get("score"))
            parsed_reason = str(obj.get("reasoning", ""))[:500]
        except Exception:
            pass
    if parsed_score is None:
        parsed_score = _extract_score(res.raw)
        if parsed_score is None:
            res.parse_failure = True
            res.error = "model reply contains no integer or JSON"
            return res

    res.score = max(sr[0], min(parsed_score, sr[1]))
    if parsed_reason:
        res.error = parsed_reason
    return res


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _ctx_get(ctx: Any, key: str, default: Any = None) -> Any:
    if ctx is None:
        return default
    if hasattr(ctx, "get") and callable(getattr(ctx, "get")):
        try:
            v = ctx.get(key)
            return default if v is None else v
        except Exception:
            pass
    try:
        v = ctx[key]
        return default if v is None else v
    except Exception:
        pass
    if hasattr(ctx, key):
        try:
            return getattr(ctx, key)
        except Exception:
            return default
    return default


def judge_with_evidence(*,
                        evidence_type: str,
                        rubric_prompt: str,
                        score_range: Tuple[int, int],
                        ctx: Any,
                        model: str,
                        api_key: str,
                        api_base: str = "",
                        text_samples: Iterable[Tuple[str, str]] = (),
                        timeout: float = 120.0,
                        temperature: float = 0.0,
                        require_json: bool = True,
                        **extra_kwargs: Any) -> SafeLLMResult:
    sr = (int(score_range[0]), int(score_range[1]))
    text_sample_list: List[Tuple[str, str]] = list(text_samples)

    if evidence_type in ("rendered_dom", "http_response_html"):
        dom = _ctx_get(ctx, "rendered_dom") or _ctx_get(ctx, "last_body") or ""
        if not isinstance(dom, str):
            try:
                dom = dom.decode("utf-8", errors="replace")
            except Exception:
                dom = str(dom)
        if not dom.strip():
            return _make_skip(reason=f"no {evidence_type} evidence in ctx")
        url = _ctx_get(ctx, "rendered_dom_url") or _ctx_get(ctx, "last_url") or "(unknown URL)"
        label = f"RENDERED_DOM @ {url}"
        all_samples = text_sample_list + [(label, dom)]
        return safe_llm_judge_call(
            rubric_prompt=rubric_prompt,
            samples=all_samples,
            score_range=sr,
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            timeout=timeout,
            **extra_kwargs,
        )

    if evidence_type == "screenshot":
        shots = _ctx_get(ctx, "screenshots") or []
        if isinstance(shots, str):
            shots = [shots]
        shots = [s for s in shots if s]
        if not shots:
            return _make_skip(reason="no screenshots collected by upstream P19")
        try:
            start_idx = int(_ctx_get(ctx, "_chain_screenshot_start_idx") or 0)
        except Exception:
            start_idx = 0
        if start_idx >= len(shots):
            return _make_skip(reason="current node produced 0 screenshots")
        if start_idx > 0:
            shots = shots[start_idx:]
        shots = shots[-3:]
        return safe_multimodal_judge_call(
            rubric_prompt=rubric_prompt,
            image_paths=shots,
            text_samples=text_sample_list,
            score_range=sr,
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            timeout=timeout,
            require_json=require_json,
            **extra_kwargs,
        )

    return _make_skip(
        reason=f"judge_with_evidence: unsupported evidence_type={evidence_type!r}; "
               "use task-local code/api evidence path instead"
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _safe_make_pr(cls, *, passed: bool, data: Any, message: str):
    try:
        return cls(passed=passed, data=data, message=message)
    except TypeError:
        try:
            return cls(success=passed, data=data, message=message)
        except TypeError:
            try:
                return cls(passed, data, message)
            except TypeError:
                try:
                    return cls(passed=passed)
                except TypeError:
                    return cls(success=passed)


def _wrap_safe_result(res: SafeLLMResult,
                      score_range: Tuple[int, int],
                      return_type: str,
                      primitive_result_cls: Any = None) -> Any:
    sr_hi = int(score_range[1])

    if res.skipped:
        skipped_data = {
            "score": 0,
            "skipped": True,
            "llm_api_failure": bool(res.llm_api_failure),
            "exception_class": res.exception_class,
            "reason": res.error or "skipped",
            "raw": (res.raw or "")[:200],
        }
        if return_type == "primitive":
            if primitive_result_cls is None:
                raise ValueError("primitive return_type requires primitive_result_cls")
            return _safe_make_pr(
                primitive_result_cls,
                passed=True,
                data=skipped_data,
                message=f"LLM judge SKIPPED ({res.reason()})",
            )
        if return_type == "dict":
            skipped_data["passed"] = True
            skipped_data["message"] = f"LLM judge SKIPPED ({res.reason()})"
            return skipped_data
        if return_type == "float":
            return 0.0
        raise ValueError(f"unknown return_type={return_type!r}")

    score = res.score if res.score is not None else 0
    reason = (res.error or "")[:300]
    pass_data = {
        "score": float(score),
        "reason": reason,
        "samples_count": res.samples_count,
    }
    msg_suffix = f" – {reason[:200]}" if reason else ""
    if return_type == "primitive":
        if primitive_result_cls is None:
            raise ValueError("primitive return_type requires primitive_result_cls")
        return _safe_make_pr(
            primitive_result_cls,
            passed=score > 0,
            data=pass_data,
            message=f"LLM score: {score}/{sr_hi}{msg_suffix}",
        )
    if return_type == "dict":
        pass_data["passed"] = score > 0
        pass_data["message"] = f"LLM score: {score}/{sr_hi}{msg_suffix}"
        return pass_data
    if return_type == "float":
        return float(score)
    raise ValueError(f"unknown return_type={return_type!r}")


def dispatch_external_evidence(*,
                               inputs: dict,
                               ctx: Any,
                               model: str,
                               api_key: str,
                               api_base: str = "",
                               return_type: str = "primitive",
                               primitive_result_cls: Any = None,
                               temperature: float = 0.0,
                               timeout: float = 120.0,
                               extra_text_samples: Iterable[Tuple[str, str]] = (),
                               **extra_kwargs: Any):
    evidence_type = inputs.get("evidence_type")
    if evidence_type not in ("rendered_dom", "screenshot"):
        return None

    if not (api_key or "").strip():
        skipped_data = {
            "score": 0, "skipped": True, "reason": "LLM_API_KEY blank",
            "raw": "", "llm_api_failure": False, "exception_class": None,
        }
        if return_type == "primitive" and primitive_result_cls is not None:
            return _safe_make_pr(
                primitive_result_cls, passed=True, data=skipped_data,
                message="LLM judge SKIPPED (LLM_API_KEY blank)",
            )
        if return_type == "dict":
            skipped_data["passed"] = True
            skipped_data["message"] = "LLM judge SKIPPED (LLM_API_KEY blank)"
            return skipped_data
        if return_type == "float":
            return 0.0
        return None

    rubric_prompt = (inputs.get("rubric_prompt", "") or inputs.get("prompt", "")
                     or inputs.get("rubric", ""))
    score_range_raw = (inputs.get("score_range")
                       or [0, inputs.get("max_score", 5)])
    sr = (int(score_range_raw[0]), int(score_range_raw[1]))

    res = judge_with_evidence(
        evidence_type=evidence_type,
        rubric_prompt=rubric_prompt,
        score_range=sr,
        ctx=ctx,
        model=model,
        api_key=api_key,
        api_base=api_base,
        text_samples=extra_text_samples,
        temperature=temperature,
        timeout=timeout,
        **extra_kwargs,
    )
    return _wrap_safe_result(res, sr, return_type, primitive_result_cls)


__all__ = [
    "SafeLLMResult",
    "safe_chat_completion",
    "safe_llm_judge_call",
    "safe_multimodal_judge_call",
    "judge_with_evidence",
    "dispatch_external_evidence",
]
