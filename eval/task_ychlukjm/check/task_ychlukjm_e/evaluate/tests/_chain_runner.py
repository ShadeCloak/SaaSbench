
from __future__ import annotations

import json
import logging
import re
from typing import Any

from primitives import execute_primitive
from utils import NodeResult

logger = logging.getLogger("eval.chain_runner")



_PLACEHOLDER_RE = re.compile(r"\{\{([^{}]+?)\}\}")


def _walk_dotted(obj: Any, path: str) -> Any:
    cur = obj
    for raw in re.split(r"\.(?![^\[]*\])", path):
        if not raw:
            continue
        m = re.match(r"^([^\[\]]+)(\[(-?\d+)\])?$", raw)
        if not m:
            return None
        key, _bracket, idx = m.group(1), m.group(2), m.group(3)
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif hasattr(cur, key):
            cur = getattr(cur, key)
        else:
            return None
        if idx is not None and isinstance(cur, list):
            try:
                cur = cur[int(idx)]
            except (IndexError, ValueError):
                return None
        if cur is None:
            return None
    return cur


def _resolve_placeholder(token: str, step_responses: list, ctx: dict) -> Any:
    token = token.strip()
    if token.startswith("from_step_"):
        rest = token[len("from_step_"):]
        m = re.match(r"^(\d+)(?:\.(.+))?$", rest)
        if m:
            one_based = int(m.group(1))
            idx = one_based - 1
            sub = m.group(2)
            if 0 <= idx < len(step_responses):
                value = step_responses[idx]
                if sub:
                    value = _walk_dotted(value, sub)
                return value
        return None
    if "." in token:
        head, tail = token.split(".", 1)
        base = ctx.get(head)
        if base is None:
            return None
        return _walk_dotted(base, tail)
    return ctx.get(token)


def _substitute(value: Any, step_responses: list, ctx: dict) -> Any:
    if isinstance(value, str):
        if "{{" not in value:
            return value
        out = value
        for m in _PLACEHOLDER_RE.finditer(value):
            token = m.group(1)
            resolved = _resolve_placeholder(token, step_responses, ctx)
            if resolved is None:
                continue
            if isinstance(resolved, (dict, list)):
                continue
            out = out.replace(m.group(0), str(resolved))
        return out
    if isinstance(value, dict):
        return {k: _substitute(v, step_responses, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, step_responses, ctx) for v in value]
    return value


def _iter_strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)


def _step_passed(ptype: str, result: dict, inputs: dict) -> bool:
    if result.get("error") and ptype not in ("P04",):
        return False

    if ptype == "P01":
        return result.get("exists", False)

    if ptype == "P02":
        return result.get("passed", False)

    if ptype == "P04":
        return result.get("status_code", 0) > 0

    if ptype == "P06":
        return result.get("all_present", False)

    if ptype == "P07":
        return result.get("all_passed", False)

    if ptype == "P08":
        expected = inputs.get("expected_result")
        if expected is None:
            return result.get("row_count", 0) > 0
        if isinstance(expected, str):
            for row in result.get("rows", []):
                if expected in str(row):
                    return True
            return False
        if isinstance(expected, dict):
            rows = result.get("rows", [])
            row = (rows[0] if isinstance(rows, list) and rows else rows or {}) or {}
            row_count = result.get("row_count", len(rows) if isinstance(rows, list) else 0)
            for k, v in expected.items():
                if k == "row_count_gte" and row_count < v:
                    return False
                if k == "row_count_gt" and row_count <= v:
                    return False
                if k == "row_count_lte" and row_count > v:
                    return False
                if k == "row_count_lt" and row_count >= v:
                    return False
                if k == "row_count" and row_count != v:
                    return False
                if k.startswith("row_count_"):
                    continue
                for suffix, cmp in (("_gte", lambda a,b: a >= b),
                                     ("_gt",  lambda a,b: a > b),
                                     ("_lte", lambda a,b: a <= b),
                                     ("_lt",  lambda a,b: a < b)):
                    if k.endswith(suffix) and len(k) > len(suffix):
                        col = k[: -len(suffix)]
                        actual = row.get(col)
                        try:
                            if actual is None or not cmp(actual, v):
                                return False
                        except TypeError:
                            return False
                        break
                else:
                    if row.get(k) != v:
                        return False
            return True
        return result.get("row_count", 0) > 0

    if ptype == "P09":
        return result.get("exists", False)

    if ptype == "P10":
        return len(result.get("missing", ["?"])) == 0

    if ptype == "P11":
        return result.get("found", False)

    if ptype == "P12":
        expect = inputs.get("expect_success", True)
        if expect:
            return result.get("success", False)
        return True

    if ptype == "P13":
        return result.get("success", False)

    if ptype == "P14":
        return result.get("passed", False)

    if ptype == "P15":
        return result.get("passed", False)

    if ptype == "P17":
        return True

    if ptype == "P18":
        return result.get("success", False)

    if ptype == "P19":
        return result.get("all_passed", False)

    if ptype == "P22":
        ene = inputs.get("expect_no_errors", False)
        if ene:
            return not result.get("has_errors", True)
        return result.get("status_code", 0) == 200

    if ptype == "P_INGEST":
        return result.get("success", False)

    return not result.get("error")


def run_node_chain(node: dict) -> NodeResult:
    node_id = node["id"]
    scoring = node["scoring"]
    max_score = scoring["maxScore"]
    method = scoring["method"]
    category = scoring.get("category", "")
    chain = node.get("primitive_chain", [])

    ctx: dict[str, Any] = {}
    step_responses: list = []
    chain_results: list = []
    pass_count = 0
    total_count = len(chain)
    last_error = ""
    llm_score = None
    llm_skipped = False
    llm_skipped_info: dict | None = None

    for step in chain:
        ptype = step.get("type", "")
        inputs = step.get("inputs", {})

        if isinstance(inputs, dict) and any("{{" in v for v in _iter_strings(inputs)):
            inputs = _substitute(inputs, step_responses, ctx)

        if ptype == "P22" and "query" in inputs:
            import random, string
            q = inputs.get("query", "")
            if any(k in q for k in ["createDomain", "createGlossaryTerm", "createGlossaryNode",
                                     "createTag", "createOwnershipType"]):
                suffix = "".join(random.choices(string.ascii_lowercase, k=5))
                inputs = dict(inputs)
                inputs["query"] = re.sub(r'(name:\s*"[^"]*)', r'\1_' + suffix, q, count=1)

        prev_last_body = ctx.get("last_body") if isinstance(ctx, dict) else None
        try:
            result = execute_primitive(ptype, inputs, ctx)
            if (
                ptype == "P22"
                and isinstance(result, dict)
                and isinstance(result.get("body"), dict)
            ):
                body = result["body"]
                errs = body.get("errors") or []
                data = body.get("data") or {}
                if errs and any(
                    "already exists" in (e.get("message") or "").lower()
                    for e in errs
                ):
                    q_raw = inputs.get("query", "") if isinstance(inputs, dict) else ""
                    _urn_prefix_by_op = {
                        "createDomain": "urn:li:domain:",
                        "createGlossaryNode": "urn:li:glossaryNode:",
                        "createGlossaryTerm": "urn:li:glossaryTerm:",
                        "createTag": "urn:li:tag:",
                        "createOwnershipType": "urn:li:ownershipType:",
                        "createStructuredProperty": "urn:li:structuredProperty:",
                        "createDataProduct": "urn:li:dataProduct:",
                        "createPolicy": "urn:li:dataHubPolicy:",
                    }
                    import re as _re
                    for op, prefix in _urn_prefix_by_op.items():
                        if op in q_raw:
                            m = _re.search(
                                r'id:\s*"([^"]+)"', q_raw,
                            )
                            if m:
                                synthetic_urn = f"{prefix}{m.group(1)}"
                                data = dict(data) if isinstance(data, dict) else {}
                                if data.get(op) is None:
                                    data[op] = synthetic_urn
                                    body["data"] = data
                                    body["_round26_idempotent_already_exists"] = True
                                    result["body"] = body
                                    result["has_errors"] = False
                            break
            if ptype == "P_INGEST" and result.get("success"):
                import time
                time.sleep(6)
            if ptype == "P12" and isinstance(result, dict) and result.get("success"):
                cmd_str = ""
                if isinstance(inputs, dict):
                    cmd_str = str(inputs.get("command", ""))
                if any(tok in cmd_str for tok in (
                    "datahub user upsert", "datahub group upsert",
                    "datahub put", "datahub ingest run",
                    "datahub user add", "datahub group add",
                )):
                    import time
                    time.sleep(6)
            if ptype == "P08":
                import time
                time.sleep(0.5)
            #
            if ptype == "P22":
                q = inputs.get("query", "") if isinstance(inputs, dict) else ""
                _create_mutations = ("createGlossaryTerm", "createGlossaryNode",
                                     "createDomain", "createOwnershipType",
                                     "raiseIncident", "createStructuredProperty",
                                     "createDataProduct", "createTag",
                                     "upsertCustomAssertion", "createPolicy")
                _assoc_mutations = ("addOwner", "addOwners", "addTerm", "addTerms",
                                    "addLink", "addLinks", "setDomain", "setTags",
                                    "batchAssignRole", "addAssertionsToContract",
                                    "updateOwnershipType")
                _lineage_mutations = ("updateLineage",)
                if any(tok in q for tok in _create_mutations):
                    import time
                    time.sleep(5)
                elif any(tok in q for tok in _assoc_mutations):
                    import time
                    time.sleep(3)
                elif any(tok in q for tok in _lineage_mutations):
                    import time
                    time.sleep(6)
        except Exception as exc:
            logger.warning("Primitive %s raised: %s", ptype, exc)
            result = {"error": str(exc)}

        cur_last_body = ctx.get("last_body") if isinstance(ctx, dict) else None
        if cur_last_body is not None and cur_last_body is not prev_last_body:
            step_responses.append(cur_last_body)
        else:
            step_responses.append(result if isinstance(result, dict) else None)

        passed = _step_passed(ptype, result, inputs)

        if ptype == "P17":
            if isinstance(result, dict) and result.get("skipped"):
                llm_skipped = True
                llm_skipped_info = {
                    "llm_api_failure": result.get("llm_api_failure", False),
                    "exception_class": result.get("exception_class", ""),
                    "reason": result.get("reason", ""),
                }
            else:
                llm_score = result.get("score", 0)
                llm_max = result.get("max_score", max_score)
            passed = True

        #
        step_msg = ""
        if not passed and isinstance(result, dict):
            step_msg = (result.get("error") or "")[:200]
            if not step_msg:
                if ptype == "P07":
                    failed_assertions = []
                    for r in (result.get("results") or []):
                        if not r.get("passed"):
                            path = r.get("path") or "$"
                            op = r.get("op") or "eq"
                            exp = r.get("expected")
                            act = r.get("actual")
                            failed_assertions.append(
                                f"{path} expected={exp!r} actual={act!r}"
                            )
                    if failed_assertions:
                        step_msg = "; ".join(failed_assertions)[:240]
                    else:
                        step_msg = "P07 assertion failed"
                elif ptype == "P15":
                    sc = result.get("status_code")
                    accept = result.get("acceptable")
                    step_msg = f"HTTP {sc} not in {accept}"[:200] if accept else f"HTTP {sc}"
                elif "status_code" in result:
                    step_msg = f"HTTP {result.get('status_code')}"
                elif "exit_code" in result:
                    so = (result.get("stdout") or "")[:80]
                    se = (result.get("stderr") or "")[:80]
                    step_msg = (
                        f"exit_code={result.get('exit_code')} "
                        f"stdout={so!r} stderr={se!r}"
                    )[:240]
                elif "missing" in result:
                    step_msg = f"missing={result.get('missing')[:5]}"
        _step_evidence_extra: dict = {}
        if ptype in ("P22", "P_INGEST", "P04") and isinstance(result, dict):
            _body = result.get("body")
            if isinstance(_body, dict):
                try:
                    _body_s = json.dumps(_body, ensure_ascii=False)
                except Exception:
                    _body_s = str(_body)
                if len(_body_s) > 1500:
                    _body_s = _body_s[:1500] + "...(truncated)"
                _step_evidence_extra["body_preview"] = _body_s
            if "status_code" in result:
                _step_evidence_extra["status_code"] = result.get("status_code")
        chain_results.append({
            "type": ptype,
            "passed": passed,
            "message": step_msg,
            **_step_evidence_extra,
        })

        if passed:
            pass_count += 1
        else:
            last_error = result.get("error", "") or f"{ptype} failed"
            if method == "binary":
                break

    status = None
    if method == "binary":
        score = max_score if pass_count == total_count else 0.0
    elif method == "weighted":
        ratio = pass_count / total_count if total_count > 0 else 0.0
        score = round(ratio * max_score, 2)
    elif method == "llm-judge":
        if llm_skipped:
            score = 0.0
            status = "SKIPPED_LLM"
        else:
            score = float(llm_score) if llm_score is not None else 0.0
    else:
        score = max_score if pass_count == total_count else 0.0

    if status is None:
        status = "PASSED" if score > 0 else "FAILED"
    msg = (last_error[:200] if last_error and score == 0
           else f"{pass_count}/{total_count} primitives passed")

    evidence_dict = {
        "category": category,
        "pass_count": pass_count,
        "total": total_count,
        "chain_results": chain_results,
    }
    if llm_skipped and llm_skipped_info:
        evidence_dict["llm_judge_skipped"] = True
        evidence_dict.update(llm_skipped_info)

    return NodeResult(
        node_id=node_id,
        status=status,
        score=score,
        max_score=max_score,
        message=msg,
        evidence=evidence_dict,
    )
