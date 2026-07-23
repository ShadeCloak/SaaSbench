#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import sys
import time
import uuid
from typing import Any, AsyncGenerator

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
#
_SIG_CACHE: "collections.OrderedDict[str, str]" = collections.OrderedDict()
_SIG_CACHE_MAX = int(os.environ.get("SIG_CACHE_MAX", "100000"))


def _sig_remember(tool_use_id: str, sig: str) -> None:
    if not (tool_use_id and sig):
        return
    if tool_use_id in _SIG_CACHE:
        _SIG_CACHE.move_to_end(tool_use_id)
    _SIG_CACHE[tool_use_id] = sig
    while len(_SIG_CACHE) > _SIG_CACHE_MAX:
        _SIG_CACHE.popitem(last=False)


def _sig_recall(tool_use_id: str) -> str:
    return _SIG_CACHE.get(tool_use_id, "")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

UPSTREAM_MAX_RETRIES = int(os.environ.get("UPSTREAM_MAX_RETRIES", "6"))
UPSTREAM_BASE_BACKOFF = float(os.environ.get("UPSTREAM_BASE_BACKOFF", "2.0"))
UPSTREAM_MAX_BACKOFF = float(os.environ.get("UPSTREAM_MAX_BACKOFF", "60.0"))
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504, 529}


def _parse_retry_after(value: str) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        import datetime as _dt
        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        delta = (dt - _dt.datetime.now(tz=_dt.timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:
        return None


def _backoff_delay(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(retry_after, UPSTREAM_MAX_BACKOFF)
    base = UPSTREAM_BASE_BACKOFF * (2 ** (attempt - 1))
    base = min(base, UPSTREAM_MAX_BACKOFF)
    import random
    return base * (0.8 + 0.4 * random.random())


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
INJECT_NON_INTERACTIVE = os.environ.get("INJECT_NON_INTERACTIVE", "").strip() in ("1", "true", "yes")
NON_INTERACTIVE_SUFFIX = (
    "\n\n[NON_INTERACTIVE_BATCH_MODE]\n"
    "You are running in a fully non-interactive batch evaluation. There is no human "
    "in the loop and any tool that asks the user a question (e.g. AskUserQuestion) "
    "will silently fail and end your turn with zero progress.\n"
    "DO NOT call AskUserQuestion. DO NOT ask clarifying questions in text. If the "
    "task description has scope ambiguity, pick the option that most directly "
    "satisfies the explicit deliverables in the prompt and proceed implementing it. "
    "Always actually write code, run/verify it, and only stop when the deliverables "
    "described in the prompt are working end-to-end."
)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_ANTHROPIC_DROP_KEYS = {
    "anthropic_version",
    "anthropic_beta",
    "metadata",
    "system",
    "stop_sequences",
    "thinking",
    "container",
    "context_management",
    "service_tier",
    "mcp_servers",
}


def _flatten_anthropic_content(blocks: Any) -> tuple[str, list[dict]]:
    if isinstance(blocks, str):
        return blocks, []
    if not isinstance(blocks, list):
        return "", []
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        bt = b.get("type")
        if bt == "text":
            text_parts.append(b.get("text", ""))
        elif bt == "tool_use":
            tu_id = b.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            tc: dict = {
                "id": tu_id,
                "type": "function",
                "function": {
                    "name": b.get("name", ""),
                    "arguments": json.dumps(b.get("input", {}), ensure_ascii=False),
                },
            }
            sig = _sig_recall(tu_id)
            if sig:
                tc["signature"] = sig
            tool_calls.append(tc)
        elif bt == "tool_result":
            inner = b.get("content", "")
            if isinstance(inner, list):
                inner = "".join(
                    x.get("text", "") for x in inner if isinstance(x, dict) and x.get("type") == "text"
                )
            text_parts.append(str(inner))
        elif bt == "image":
            text_parts.append("[image omitted]")
    return "".join(text_parts), tool_calls


def _convert_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")

        if role == "user" and isinstance(content, list):
            text_buf: list[str] = []
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    inner = b.get("content", "")
                    if isinstance(inner, list):
                        inner = "".join(
                            x.get("text", "")
                            for x in inner
                            if isinstance(x, dict) and x.get("type") == "text"
                        )
                    out.append({
                        "role": "tool",
                        "tool_call_id": b.get("tool_use_id", ""),
                        "content": str(inner),
                    })
                elif isinstance(b, dict) and b.get("type") == "text":
                    text_buf.append(b.get("text", ""))
            if text_buf:
                out.append({"role": "user", "content": "".join(text_buf)})
            continue

        text, tool_calls = _flatten_anthropic_content(content)
        msg: dict = {"role": role}
        if tool_calls:
            msg["tool_calls"] = tool_calls
            msg["content"] = text or ""
        else:
            msg["content"] = text
        out.append(msg)
    return out


#
_SCHEMA_DROP_KEYS = frozenset({
    "$schema",
    "$id",
    "$ref",
    "$defs",
    "definitions",
    "propertyNames",
    "patternProperties",
    "additionalProperties",
    "unevaluatedProperties",
    "unevaluatedItems",
    "dependentRequired",
    "dependentSchemas",
    "if", "then", "else",
    "allOf", "oneOf", "not",
    "examples",
    "contentMediaType",
    "contentEncoding",
    "readOnly",
    "writeOnly",
    "deprecated",
})

_GEMINI_EXTRA_DROP = frozenset({
    "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf",
    "minLength", "maxLength",
    "pattern",
    "format",
    "title",
})

_STRICT_SCHEMA_MODE = os.environ.get("STRICT_SCHEMA_MODE", "").strip().lower()


def _active_drop_keys() -> frozenset:
    if _STRICT_SCHEMA_MODE == "gemini":
        return _SCHEMA_DROP_KEYS | _GEMINI_EXTRA_DROP
    return _SCHEMA_DROP_KEYS


_PROPERTY_DICT_KEYS = frozenset({"properties", "definitions", "$defs", "patternProperties"})


def _sanitize_schema_node(node):
    drop = _active_drop_keys()
    if isinstance(node, dict):
        cleaned = {}
        for k, v in node.items():
            if k in drop:
                continue
            if k in _PROPERTY_DICT_KEYS and isinstance(v, dict):
                cleaned[k] = {pn: _sanitize_schema_node(pv) for pn, pv in v.items()}
            else:
                cleaned[k] = _sanitize_schema_node(v)
        return cleaned
    if isinstance(node, list):
        return [_sanitize_schema_node(x) for x in node]
    return node


def _sanitize_schema(node):
    return _sanitize_schema_node(node)


def _convert_tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    out = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        params = t.get("input_schema", {"type": "object"})
        params = _sanitize_schema(params)
        if isinstance(params, dict) and params.get("type") == "object" and "properties" not in params:
            params["properties"] = {}
        out.append({
            "type": "function",
            "function": {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": params,
            },
        })
    return out


def anthropic_to_openai_request(body: dict) -> dict:
    messages = _convert_messages(body.get("messages", []))

    system = body.get("system")
    if isinstance(system, list):
        system = "\n".join(
            s.get("text", "") for s in system if isinstance(s, dict) and s.get("type") == "text"
        )
    if not isinstance(system, str):
        system = ""
    if INJECT_NON_INTERACTIVE:
        system = (system.rstrip() + NON_INTERACTIVE_SUFFIX) if system.strip() else NON_INTERACTIVE_SUFFIX.lstrip("\n")
    if system.strip():
        messages = [{"role": "system", "content": system}] + messages

    out: dict = {
        "model": body.get("model"),
        "messages": messages,
    }
    for k in ("max_tokens", "temperature", "top_p", "stream", "user"):
        if k in body and body[k] is not None:
            out[k] = body[k]
    if body.get("stop_sequences"):
        out["stop"] = body["stop_sequences"]
    if _STRICT_SCHEMA_MODE == "gemini":
        out.setdefault("thinking", {
            "include_thoughts": True,
            "budget_tokens": int(os.environ.get("GEMINI_THINKING_BUDGET", "8192")),
        })
    tools = _convert_tools(body.get("tools"))
    if tools:
        out["tools"] = tools
        tc = body.get("tool_choice")
        if isinstance(tc, dict):
            t = tc.get("type")
            if t == "auto":
                out["tool_choice"] = "auto"
            elif t == "any":
                out["tool_choice"] = "required"
            elif t == "tool" and tc.get("name"):
                out["tool_choice"] = {"type": "function", "function": {"name": tc["name"]}}
    return out


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _openai_message_to_anthropic_content(msg: dict) -> list[dict]:
    blocks: list[dict] = []
    text = msg.get("content")
    if isinstance(text, str) and text:
        blocks.append({"type": "text", "text": text})
    for tc in msg.get("tool_calls", []) or []:
        if tc.get("type") != "function":
            continue
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}") or "{}")
        except json.JSONDecodeError:
            args = {"_raw": fn.get("arguments", "")}
        tu_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:8]}"
        sig = tc.get("signature")
        if sig:
            _sig_remember(tu_id, sig)
        blocks.append({
            "type": "tool_use",
            "id": tu_id,
            "name": fn.get("name", ""),
            "input": args,
        })
    if not blocks:
        blocks.append({"type": "text", "text": ""})
    return blocks


def _stop_reason_oa_to_an(reason: str | None) -> str:
    return {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "function_call": "tool_use",
        "content_filter": "stop_sequence",
    }.get(reason or "stop", "end_turn")


def openai_to_anthropic_response(body: dict, model: str) -> dict:
    choice = (body.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = _openai_message_to_anthropic_content(msg)
    usage = body.get("usage") or {}
    return {
        "id": body.get("id") or f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": _stop_reason_oa_to_an(choice.get("finish_reason")),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


async def stream_openai_to_anthropic(
    upstream: AsyncGenerator[bytes, None],
    model: str,
) -> AsyncGenerator[bytes, None]:
    msg_id = f"msg_{uuid.uuid4().hex}"
    buf = b""

    started = False
    text_block_idx: int | None = None
    tool_block_indices: dict[int, int] = {}
    tu_id_by_oa_idx: dict[int, str] = {}
    next_block_idx = 0
    stop_reason = "end_turn"
    usage_in = 0
    usage_out = 0

    async def start_message():
        nonlocal started
        if started:
            return
        started = True
        yield _sse("message_start", {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        })

    async def open_text_block():
        nonlocal text_block_idx, next_block_idx
        if text_block_idx is not None:
            return
        text_block_idx = next_block_idx
        next_block_idx += 1
        yield _sse("content_block_start", {
            "type": "content_block_start",
            "index": text_block_idx,
            "content_block": {"type": "text", "text": ""},
        })

    async def close_text_block():
        nonlocal text_block_idx
        if text_block_idx is None:
            return
        idx = text_block_idx
        text_block_idx = None
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": idx})

    async def open_tool_block(oa_idx: int, tc: dict):
        nonlocal next_block_idx
        an_idx = next_block_idx
        next_block_idx += 1
        tool_block_indices[oa_idx] = an_idx
        fn = tc.get("function", {}) or {}
        tu_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:8]}"
        tu_id_by_oa_idx[oa_idx] = tu_id
        yield _sse("content_block_start", {
            "type": "content_block_start",
            "index": an_idx,
            "content_block": {
                "type": "tool_use",
                "id": tu_id,
                "name": fn.get("name", ""),
                "input": {},
            },
        })

    async for raw in upstream:
        buf += raw
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                continue
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue

            if isinstance(chunk.get("usage"), dict):
                usage_in = chunk["usage"].get("prompt_tokens", usage_in)
                usage_out = chunk["usage"].get("completion_tokens", usage_out)

            choices = chunk.get("choices") or []
            if not choices:
                continue
            ch = choices[0]
            delta = ch.get("delta") or {}

            content_piece = delta.get("content")
            if isinstance(content_piece, str) and content_piece:
                async for f in start_message():
                    yield f
                if text_block_idx is None:
                    async for f in open_text_block():
                        yield f
                yield _sse("content_block_delta", {
                    "type": "content_block_delta",
                    "index": text_block_idx,
                    "delta": {"type": "text_delta", "text": content_piece},
                })

            tool_calls = delta.get("tool_calls") or []
            if tool_calls:
                async for f in start_message():
                    yield f
                async for f in close_text_block():
                    yield f
                for tc in tool_calls:
                    oa_idx = tc.get("index", 0)
                    if oa_idx not in tool_block_indices:
                        async for f in open_tool_block(oa_idx, tc):
                            yield f
                    fn = tc.get("function") or {}
                    args_delta = fn.get("arguments")
                    if args_delta:
                        yield _sse("content_block_delta", {
                            "type": "content_block_delta",
                            "index": tool_block_indices[oa_idx],
                            "delta": {"type": "input_json_delta", "partial_json": args_delta},
                        })
                    sig = tc.get("signature")
                    if sig:
                        tu_id = tu_id_by_oa_idx.get(oa_idx, "")
                        _sig_remember(tu_id, sig)

            fr = ch.get("finish_reason")
            if fr:
                stop_reason = _stop_reason_oa_to_an(fr)

    async for f in close_text_block():
        yield f
    for an_idx in tool_block_indices.values():
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": an_idx})
    if not started:
        async for f in start_message():
            yield f
    yield _sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
    })
    yield _sse("message_stop", {"type": "message_stop"})


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

UPSTREAM_BASE_URL = os.environ.get("UPSTREAM_BASE_URL", "https://api.commonstack.ai/v1")
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY", "")
PROXY_MASTER_KEY = os.environ.get("PROXY_MASTER_KEY", "")
DEBUG = os.environ.get("PROXY_DEBUG", "0") == "1"

app = FastAPI(title="anthropic-to-openai-proxy", version="0.1.0")


def _check_client_auth(x_api_key: str | None, authorization: str | None) -> None:
    if not PROXY_MASTER_KEY:
        return
    incoming = x_api_key or ""
    if not incoming and authorization:
        if authorization.lower().startswith("bearer "):
            incoming = authorization[7:].strip()
        else:
            incoming = authorization.strip()
    if incoming != PROXY_MASTER_KEY:
        raise HTTPException(status_code=401, detail="invalid client api key")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "upstream": UPSTREAM_BASE_URL}


@app.post("/v1/messages")
async def messages_endpoint(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    authorization: str | None = Header(default=None),
):
    _check_client_auth(x_api_key, authorization)
    if not UPSTREAM_API_KEY:
        raise HTTPException(status_code=500, detail="UPSTREAM_API_KEY not configured")

    body = await request.json()
    if DEBUG:
        sys.stderr.write(f"[proxy] anthropic in: model={body.get('model')} "
                         f"tools={len(body.get('tools') or [])} "
                         f"stream={body.get('stream')}\n")

    oa_body = anthropic_to_openai_request(body)
    is_stream = bool(oa_body.get("stream"))

    headers = {
        "Authorization": f"Bearer {UPSTREAM_API_KEY}",
        "Content-Type": "application/json",
    }
    upstream_url = f"{UPSTREAM_BASE_URL.rstrip('/')}/chat/completions"

    if not is_stream:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            last_status = None
            last_text = ""
            for attempt in range(1, UPSTREAM_MAX_RETRIES + 1):
                try:
                    r = await client.post(upstream_url, json=oa_body, headers=headers)
                except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                    last_status = 599
                    last_text = f"upstream network error: {type(e).__name__}: {e}"
                    if DEBUG:
                        sys.stderr.write(f"[proxy] attempt {attempt}/{UPSTREAM_MAX_RETRIES} network err: {e}\n")
                    if attempt >= UPSTREAM_MAX_RETRIES:
                        break
                    delay = _backoff_delay(attempt, None)
                    if DEBUG:
                        sys.stderr.write(f"[proxy] sleep {delay:.1f}s then retry\n")
                    await asyncio.sleep(delay)
                    continue
                if r.status_code in RETRYABLE_STATUS and attempt < UPSTREAM_MAX_RETRIES:
                    ra = _parse_retry_after(r.headers.get("Retry-After", ""))
                    delay = _backoff_delay(attempt, ra)
                    if DEBUG:
                        sys.stderr.write(
                            f"[proxy] attempt {attempt}/{UPSTREAM_MAX_RETRIES} {r.status_code} "
                            f"retry-after={ra} sleep {delay:.1f}s body={r.text[:300]}\n"
                        )
                    await asyncio.sleep(delay)
                    last_status = r.status_code
                    last_text = r.text
                    continue
                if r.status_code >= 400:
                    if DEBUG:
                        sys.stderr.write(
                            f"[proxy] upstream {r.status_code} (attempt {attempt}): {r.text[:1000]}\n"
                        )
                    return JSONResponse(
                        status_code=r.status_code,
                        content={
                            "type": "error",
                            "error": {"type": "upstream_error", "message": r.text[:2000]},
                        },
                    )
                resp_body = r.json()
                an_resp = openai_to_anthropic_response(resp_body, oa_body["model"])
                return JSONResponse(content=an_resp)
            return JSONResponse(
                status_code=last_status or 502,
                content={
                    "type": "error",
                    "error": {
                        "type": "upstream_error_after_retries",
                        "message": f"after {UPSTREAM_MAX_RETRIES} attempts: {last_text[:1500]}",
                    },
                },
            )

    async def event_stream() -> AsyncGenerator[bytes, None]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            for attempt in range(1, UPSTREAM_MAX_RETRIES + 1):
                try:
                    cm = client.stream("POST", upstream_url, json=oa_body, headers=headers)
                    r = await cm.__aenter__()
                except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                    if DEBUG:
                        sys.stderr.write(f"[proxy] stream attempt {attempt} network err: {e}\n")
                    if attempt >= UPSTREAM_MAX_RETRIES:
                        yield _sse("error", {
                            "type": "error",
                            "error": {"type": "upstream_error", "message": f"network error: {e}"},
                        })
                        return
                    await asyncio.sleep(_backoff_delay(attempt, None))
                    continue
                try:
                    if r.status_code in RETRYABLE_STATUS and attempt < UPSTREAM_MAX_RETRIES:
                        ra = _parse_retry_after(r.headers.get("Retry-After", ""))
                        body_text = (await r.aread()).decode("utf-8", "replace")
                        if DEBUG:
                            sys.stderr.write(
                                f"[proxy] stream attempt {attempt}/{UPSTREAM_MAX_RETRIES} {r.status_code} "
                                f"retry-after={ra} body={body_text[:300]}\n"
                            )
                        await cm.__aexit__(None, None, None)
                        await asyncio.sleep(_backoff_delay(attempt, ra))
                        continue
                    if r.status_code >= 400:
                        err_text = (await r.aread()).decode("utf-8", "replace")
                        if DEBUG:
                            sys.stderr.write(
                                f"[proxy] upstream stream {r.status_code} (attempt {attempt}): {err_text[:1000]}\n"
                            )
                        yield _sse("error", {
                            "type": "error",
                            "error": {"type": "upstream_error", "message": err_text[:2000]},
                        })
                        await cm.__aexit__(None, None, None)
                        return
                    async def upstream_iter() -> AsyncGenerator[bytes, None]:
                        async for chunk in r.aiter_bytes():
                            yield chunk

                    async for frame in stream_openai_to_anthropic(upstream_iter(), oa_body["model"]):
                        yield frame
                    await cm.__aexit__(None, None, None)
                    return
                except Exception:
                    try:
                        await cm.__aexit__(None, None, None)
                    except Exception:
                        pass
                    raise
            yield _sse("error", {
                "type": "error",
                "error": {"type": "upstream_error_after_retries", "message": f"after {UPSTREAM_MAX_RETRIES} attempts"},
            })

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def main():
    global UPSTREAM_BASE_URL, DEBUG
    parser = argparse.ArgumentParser(description="Anthropic ↔ OpenAI micro-proxy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4000)
    parser.add_argument(
        "--upstream",
        default=os.environ.get("UPSTREAM_BASE_URL", "https://api.commonstack.ai/v1"),
        help="upstream OpenAI-compat /v1 base url",
    )
    parser.add_argument("--debug", action="store_true", help="print request logs to stderr")
    args = parser.parse_args()

    UPSTREAM_BASE_URL = args.upstream
    if args.debug:
        DEBUG = True
        os.environ["PROXY_DEBUG"] = "1"

    if not UPSTREAM_API_KEY:
        print("⚠️  UPSTREAM_API_KEY is not set; the server still starts, but the first real call will 500")
    print(f"anthropic-to-openai-proxy listening on {args.host}:{args.port}")
    print(f"  upstream  : {UPSTREAM_BASE_URL}")
    print(f"  master_key: {'(unset, no client auth)' if not PROXY_MASTER_KEY else '***'}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
