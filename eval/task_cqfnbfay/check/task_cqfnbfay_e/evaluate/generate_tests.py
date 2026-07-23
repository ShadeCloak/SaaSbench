#!/usr/bin/env python3
import json
import os
import re
import textwrap
from collections import defaultdict

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
DAG_PATH = os.path.join(EVAL_DIR, "dag.json")
TESTS_DIR = os.path.join(EVAL_DIR, "tests")


def category_to_filename(cat: str) -> str:
    name = cat.replace("API_", "api_").replace("PDF_", "pdf_")
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()
    name = re.sub(r"_+", "_", name).strip("_")
    return f"test_{name}.py"


def node_id_to_func(nid: str) -> str:
    return f"test_{nid.lower()}"


def generate_chain_code(chain: list[dict], indent: str = "        ") -> str:
    lines = []
    for i, step in enumerate(chain):
        ptype = step["type"]
        inputs_json = json.dumps(step.get("inputs", {}), indent=4, ensure_ascii=False)
        inputs_json = re.sub(r'\btrue\b(?=\s*[,}\]\n])', 'True', inputs_json)
        inputs_json = re.sub(r'\bfalse\b(?=\s*[,}\]\n])', 'False', inputs_json)
        inputs_json = re.sub(r'\bnull\b(?=\s*[,}\]\n])', 'None', inputs_json)
        ij_lines = inputs_json.split("\n")
        ij_indented = ij_lines[0]
        for jl in ij_lines[1:]:
            ij_indented += "\n" + indent + jl
        lines.append(f"{indent}inputs_{i} = {ij_indented}")
        lines.append(f'{indent}ok_{i}, ratio_{i} = execute_primitive("{ptype}", inputs_{i}, ctx)')
        lines.append(f"{indent}if not ok_{i}:")
        lines.append(f'{indent}    chain_pass = False')
        lines.append(f'{indent}    evidence["step_{i}_{ptype}"] = {{"passed": False}}')
        lines.append(f"{indent}else:")
        lines.append(f'{indent}    pass_count += 1')
        lines.append(f'{indent}    evidence["step_{i}_{ptype}"] = {{"passed": True, "ratio": ratio_{i}}}')

        if ptype == "P17":
            lines.append(f'{indent}    llm_score = ctx.captured.get("_llm_score", 0.0)')
        lines.append("")
    return "\n".join(lines)


def generate_test_function(node: dict) -> str:
    nid = node["id"]
    desc = node.get("description", "")
    scoring = node["scoring"]
    method = scoring["method"]
    max_score = scoring["maxScore"]
    chain = node.get("primitive_chain", [])
    prereqs = node.get("prereqs", [])

    func_name = node_id_to_func(nid)
    total_steps = len(chain)

    chain_code = generate_chain_code(chain)

    ind = "        "
    if method == "binary":
        score_logic = f"{ind}score = {max_score}.0 if chain_pass else 0.0"
    elif method == "weighted":
        score_logic = f"{ind}score = round((pass_count / {total_steps}) * {max_score}, 2) if {total_steps} > 0 else 0.0"
    elif method == "llm-judge":
        score_logic = f"{ind}score = min(llm_score, {max_score}.0) if llm_score is not None else 0.0"
    else:
        score_logic = f"{ind}score = {max_score}.0 if chain_pass else 0.0"

    status_logic = f'{ind}status = "PASSED" if chain_pass else "FAILED"'
    if method == "weighted":
        status_logic = f'{ind}status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")'
    if method == "llm-judge":
        status_logic = f'{ind}status = "PASSED" if score > 0 else "FAILED"'

    func_code = f'''
def {func_name}(ctx: EvalContext) -> NodeResult:
    """{desc}"""
    chain_pass = True
    pass_count = 0
    total_steps = {total_steps}
    evidence = {{}}
    llm_score = None

    try:
{chain_code}
{score_logic}
{status_logic}

{ind}return NodeResult(
{ind}    node_id="{nid}",
{ind}    status=status,
{ind}    score=score,
{ind}    max_score={max_score}.0,
{ind}    evidence=evidence,
{ind}    message=f"pass={{pass_count}}/{{total_steps}}",
{ind})
    except Exception as exc:
        return NodeResult(
            node_id="{nid}",
            status="ERROR",
            score=0.0,
            max_score={max_score}.0,
            evidence=evidence,
            message=str(exc),
        )
'''
    return func_code


def generate_test_file(category: str, nodes: list[dict]) -> str:
    filename = category_to_filename(category)
    func_names = [node_id_to_func(n["id"]) for n in nodes]

    registry_entries = ",\n    ".join(
        f'"{n["id"]}": {node_id_to_func(n["id"])}' for n in nodes
    )

    functions_code = "\n".join(generate_test_function(n) for n in nodes)

    file_content = f'''"""Tests for category: {category}"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive

{functions_code}

REGISTRY = {{
    {registry_entries},
}}
'''
    return file_content


def main():
    with open(DAG_PATH) as f:
        dag = json.load(f)

    categories = defaultdict(list)
    for node in dag["nodes"]:
        cat = node["scoring"]["category"]
        categories[cat].append(node)

    os.makedirs(TESTS_DIR, exist_ok=True)

    for cat in sorted(categories.keys()):
        nodes = categories[cat]
        filename = category_to_filename(cat)
        filepath = os.path.join(TESTS_DIR, filename)
        content = generate_test_file(cat, nodes)
        with open(filepath, "w") as f:
            f.write(content)
        print(f"  Generated {filename} ({len(nodes)} nodes)")

    init_path = os.path.join(TESTS_DIR, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w") as f:
            f.write("")

    print(f"\nTotal: {len(categories)} test files, {sum(len(v) for v in categories.values())} test functions")


if __name__ == "__main__":
    main()
