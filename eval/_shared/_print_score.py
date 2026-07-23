#!/usr/bin/env python3
import json
import os
import sys


def _try(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as fb:
            head = fb.read(200).lstrip()
            if head.startswith(b"<") or head.startswith(b"<!"):
                return None
    except Exception:
        pass
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def find_report(base):
    base_name = os.path.basename(base.rstrip("/"))

    if base.endswith(".json") and os.path.isfile(base):
        return _try(base), base

    base_parent = os.path.dirname(base.rstrip("/")) or "."

    candidates = [
        os.path.join(base, "report.json"),
        base + "_report.json",
        base + ".json",
        os.path.join(base_parent, "report.json"),
        base,
        os.path.join(base, "evaluation_results.json"),
        os.path.join("./results_smoke", base_name + "_report.json"),
        os.path.join("./results_smoke", base_name),
        os.path.join("./results_smoke", base_name, "report.json"),
        os.path.join("./results_smoke", "report.json"),
        os.path.join("results", base_name + "_report.json"),
        os.path.join("results", base_name + ".json") if not base_name.endswith(".json") else os.path.join("results", base_name),
        os.path.join("results", base_name, "report.json"),
        os.path.join("results", base_name),
        os.path.join(base, "node_results.json"),
        base + "_node_results.json",
        os.path.join("results", base_name + "_node_results.json"),
        os.path.join("./results_smoke", base_name + "_node_results.json"),
    ]
    for p in candidates:
        d = _try(p)
        if d is not None:
            return d, p

    if os.path.isdir(base):
        files = sorted(os.listdir(base))
        files = sorted(files, key=lambda n: (
            0 if "report" in n.lower() else (2 if "node_result" in n.lower() else 1),
            n,
        ))
        for fn in files:
            if fn.endswith(".json"):
                full = os.path.join(base, fn)
                d = _try(full)
                if d is not None:
                    return d, full
    return None, None


_LLM_METHOD_VALUES = {"llm-judge", "llm_judge"}


def _is_llm_method(value):
    return isinstance(value, str) and value in _LLM_METHOD_VALUES


def _llm_node_ids_from_dag(report_path):
    if not report_path:
        return None
    seen = set()
    cur = os.path.abspath(os.path.dirname(report_path))
    for _ in range(6):
        if cur in seen:
            break
        seen.add(cur)
        for name in ("dag.json", "dag_baseline.json"):
            p = os.path.join(cur, name)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        dag = json.load(f)
                    nodes = dag.get("nodes") or []
                    ids = set()
                    for n in nodes:
                        scoring = n.get("scoring") or {}
                        sc_method = scoring.get("method") if isinstance(scoring, dict) else None
                        if _is_llm_method(sc_method) or _is_llm_method(n.get("method")):
                            nid = n.get("id") or n.get("node_id")
                            if nid:
                                ids.add(nid)
                    return ids
                except Exception:
                    pass
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def _pick_pct(d):
    for k in ("percentage", "normalized_score", "pct", "percent"):
        v = d.get(k)
        if v is not None:
            return v
    return 0


def _pick_max(d):
    for k in ("total_max", "total_maxScore", "total_max_score", "maxScore", "max_score"):
        v = d.get(k)
        if v:
            return v
    return 0


def _node_max(node):
    for k in ("maxScore", "max_score", "max"):
        v = node.get(k)
        if v is not None:
            return v
    return 0


def _node_score(node):
    return node.get("score") or 0


def _sum_categories_max(r):
    cats = r.get("by_category") or r.get("categories") or {}
    if isinstance(cats, dict):
        return sum((c.get("maxScore") or c.get("max_score") or c.get("max") or 0)
                   for c in cats.values() if isinstance(c, dict))
    if isinstance(cats, list):
        return sum((c.get("maxScore") or c.get("max_score") or c.get("max") or 0)
                   for c in cats if isinstance(c, dict))
    return 0


def _sum_categories_score(r):
    cats = r.get("by_category") or r.get("categories") or {}
    if isinstance(cats, dict):
        return sum((c.get("score") or c.get("total_score") or 0)
                   for c in cats.values() if isinstance(c, dict))
    if isinstance(cats, list):
        return sum((c.get("score") or c.get("total_score") or 0)
                   for c in cats if isinstance(c, dict))
    return 0


def overall(r):
    if isinstance(r, list):
        if not r or not isinstance(r[0], dict):
            return None
        s = sum(float(_node_score(n) or 0) for n in r if isinstance(n, dict))
        m = sum(float(_node_max(n) or 0) for n in r if isinstance(n, dict))
        return s, m, (100 * s / m) if m else 0

    if not isinstance(r, dict) or not r:
        return None

    if isinstance(r.get("overall"), dict):
        o = r["overall"]
        return o.get("score", 0), o.get("maxScore", 0) or o.get("max_score", 0), o.get("pct", 0)

    if "total_score" in r:
        mx = _pick_max(r) or _sum_categories_max(r)
        return r.get("total_score", 0), mx, _pick_pct(r)

    if isinstance(r.get("summary"), dict) and "total_score" in r["summary"]:
        s = r["summary"]
        mx = _pick_max(s) or _sum_categories_max(r)
        return s.get("total_score", 0), mx, _pick_pct(s)

    if all(
        isinstance(v, dict)
        and "score" in v
        and ("maxScore" in v or "max_score" in v or "max" in v)
        for v in r.values()
    ):
        s = sum(float(_node_score(v) or 0) for v in r.values())
        m = sum(float(_node_max(v) or 0) for v in r.values())
        return s, m, (100 * s / m) if m else 0

    if all(
        isinstance(v, dict)
        and ("score" in v)
        and ("max" in v or "max_score" in v or "maxScore" in v)
        and "status" not in v
        for v in r.values()
    ):
        s = sum(float((v.get("score") or 0)) for v in r.values())
        m = sum(float((v.get("max") or v.get("max_score") or v.get("maxScore") or 0))
                for v in r.values())
        return s, m, (100 * s / m) if m else 0

    return None


def main(argv):
    if len(argv) < 2:
        print("usage: _print_score.py <output-base>", file=sys.stderr)
        return 2
    base = argv[1]
    r, report_path = find_report(base)
    if r is None:
        print(f"(no report at: {base})")
        return 1
    try:
        o = overall(r)
    except Exception as e:
        print(f"(parse error: {type(e).__name__}: {e}; root={type(r).__name__})")
        return 1
    if o is None:
        if isinstance(r, dict):
            print(f"(unknown schema; keys={list(r.keys())[:6]})")
        elif isinstance(r, list):
            print(f"(unknown schema; root=list len={len(r)})")
        else:
            print(f"(unknown schema; root={type(r).__name__})")
        return 1
    s, m, p = o
    try:
        pf = float(p)
    except (TypeError, ValueError):
        pf = 0.0
    try:
        sf, mf = float(s), float(m)
    except (TypeError, ValueError):
        sf, mf = 0.0, 0.0
    if pf == 0.0 and mf > 0:
        pf = 100.0 * sf / mf
    print(f"Total: {s}/{m} = {pf:.1f}%")

    if isinstance(r, dict):
        skipped_max = (
            r.get("llm_judge_skipped_maxScore")
            or (r.get("summary") or {}).get("llm_judge_skipped_maxScore")
        )
        try:
            sm = float(skipped_max) if skipped_max is not None else 0.0
        except (TypeError, ValueError):
            sm = 0.0
        if sm > 0:
            print(f"LLM judge skipped (excluded from Total): {sm}")

    nrs = []
    if isinstance(r, dict):
        nrs = (
            r.get("node_results")
            or r.get("results")
            or r.get("node_details")
            or r.get("nodes")
            or []
        )
    elif isinstance(r, list):
        nrs = r

    if isinstance(nrs, dict) and nrs:
        normalized = []
        for nid, nv in nrs.items():
            if isinstance(nv, dict):
                if "node_id" not in nv and "id" not in nv:
                    nv = dict(nv)
                    nv["node_id"] = nid
                normalized.append(nv)
        nrs = normalized

    if isinstance(nrs, list) and nrs and isinstance(nrs[0], dict):
        llm_ids = _llm_node_ids_from_dag(report_path)

        def _is_llm(n):
            nid = n.get("node_id") or n.get("id")
            if llm_ids is not None and nid in llm_ids:
                return True
            if _is_llm_method(n.get("method")):
                return True
            scoring = n.get("scoring") or {}
            if isinstance(scoring, dict) and _is_llm_method(scoring.get("method")):
                return True
            msg = (n.get("message") or "").lower()
            if "llm judge" in msg or "llm_judge" in msg:
                return True
            if n.get("status") == "SKIPPED_LLM":
                return True
            return False

        non_llm = [n for n in nrs if not _is_llm(n)]
        if non_llm:
            ss = sum(float(_node_score(n) or 0) for n in non_llm)
            mm = sum(float(_node_max(n) or 0) for n in non_llm)
            if mm > 0:
                print(f"Non-LLM nodes only: {ss:.2f}/{mm} = {100 * ss / mm:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
