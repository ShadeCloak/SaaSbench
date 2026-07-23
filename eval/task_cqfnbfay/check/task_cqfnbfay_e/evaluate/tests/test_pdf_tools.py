from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_pdf_tools_merge(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "role": "admin"
        }
        ok_0, ratio_0 = execute_primitive("P13", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P13"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P13"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "method": "POST",
            "path": "/api/tools/merge",
            "body": {
                "files": [
                    "JVBERi0xLjQKMSAwIG9iago8PAovVHlwZSAvQ2F0YWxvZwo+PgplbmRvYmoKCjIgMCBvYmoKPDwKL1R5cGUgL1BhZ2VzCi9LaWRzIFszIDAgUl0KL0NvdW50IDEKL01lZGlhQm94IFswIDAgNjEyIDc5Ml0KPj4KZW5kb2JqCgozIDAgb2JqCjw8Ci9UeXBlIC9QYWdlCi9QYXJlbnQgMiAwIFIKPj4KZW5kb2JqCgp4cmVmCjAgNAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAowMDAwMDAwMTUyIDAwMDAwIG4gCnRyYWlsZXIKPDwKL1NpemUgNAovUm9vdCAxIDAgUgo+PgpzdGFydHhyZWYKMjA1CiUlRU9GCg==",
                    "JVBERi0xLjQKMSAwIG9iago8PAovVHlwZSAvQ2F0YWxvZwo+PgplbmRvYmoKCjIgMCBvYmoKPDwKL1R5cGUgL1BhZ2VzCi9LaWRzIFszIDAgUl0KL0NvdW50IDEKL01lZGlhQm94IFswIDAgNjEyIDc5Ml0KPj4KZW5kb2JqCgozIDAgb2JqCjw8Ci9UeXBlIC9QYWdlCi9QYXJlbnQgMiAwIFIKPj4KZW5kb2JqCgp4cmVmCjAgNAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAowMDAwMDAwMTUyIDAwMDAwIG4gCnRyYWlsZXIKPDwKL1NpemUgNAovUm9vdCAxIDAgUgo+PgpzdGFydHhyZWYKMjA1CiUlRU9GCg=="
                ]
            }
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "expected_status": 200
        }
        ok_2, ratio_2 = execute_primitive("P15", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P15"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "assertions": [
                {
                    "path": "$.data",
                    "op": "not_null"
                }
            ]
        }
        ok_3, ratio_3 = execute_primitive("P07", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P07"] = {"passed": True, "ratio": ratio_3}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="PDF_TOOLS_MERGE",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="PDF_TOOLS_MERGE",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_pdf_tools_verify(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "role": "admin"
        }
        ok_0, ratio_0 = execute_primitive("P13", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P13"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P13"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "method": "POST",
            "path": "/api/tools/verify",
            "body": {
                "file": "JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCA1OTUgODQyXSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA0NCA+PgpzdHJlYW0KQlQgL0YxIDIwIFRmIDIwMCA3MDAgVGQgKEV2YWwgRG9jdW1lbnQpIFRqIEVUCmVuZHN0cmVhbQplbmRvYmoKNSAwIG9iago8PCAvVHlwZSAvRm9udCAvU3VidHlwZSAvVHlwZTEgL0Jhc2VGb250IC9IZWx2ZXRpY2EgPj4KZW5kb2JqCnhyZWYKMCA2CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAwOSAwMDAwMCBuIAowMDAwMDAwMDU4IDAwMDAwIG4gCjAwMDAwMDAxMTUgMDAwMDAgbiAKMDAwMDAwMDI2NiAwMDAwMCBuIAowMDAwMDAwMzYwIDAwMDAwIG4gCnRyYWlsZXIKPDwgL1NpemUgNiAvUm9vdCAxIDAgUiA+PgpzdGFydHhyZWYKNDQxCiUlRU9G"
            }
        }
        ok_1, ratio_1 = execute_primitive("P04", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P04"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "expected_status": 200
        }
        ok_2, ratio_2 = execute_primitive("P15", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P15"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "assertions": [
                {
                    "path": "$.checksum_status",
                    "op": "in",
                    "expected": [
                        "verified",
                        "not_found"
                    ]
                }
            ]
        }
        ok_3, ratio_3 = execute_primitive("P07", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P07"] = {"passed": True, "ratio": ratio_3}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="PDF_TOOLS_VERIFY",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="PDF_TOOLS_VERIFY",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_pdf_generation_quality(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "evidence_type": "code_files",
            "files_to_sample": [
                "lib/pdf_utils.rb",
                "lib/submissions/generate_audit_trail.rb",
                "app/models/submission.rb",
                "app/models/template.rb",
                "Gemfile"
            ],
            "rubric_prompt": "GOAL: Judge the PDF-generation and digital-signing pipeline.\nEVIDENCE: code-files listing for app/lib/*pdf* and app/jobs/*pdf*; check Gemfile for hexapdf.\nSCORE RANGE: 0-5\n\nCRITERIA:\n  C1. The HexaPDF gem (or comparable native PDF library) is used to produce PDFs.\n  C2. PKCS#7 digital signatures with a three-tier certificate chain (Root CA → Sub-CA → end cert) are applied.\n  C3. A GenerateAuditTrail (or similar) module produces a separate audit-log PDF per submission.\n  C4. The audit log embeds SHA256 checksums of the underlying documents.\n  C5. Multi-attachment merging is supported (GenerateCombinedAttachment or equivalent).\n\nSCORING ANCHORS:\n  - 0 (none):       0 or 1 of C1-C5.\n  - 2 (basic):      2 of C1-C5 (often just C1 + C3).\n  - 4 (good):       3 or 4 of C1-C5; signing chain or merging missing.\n  - 5 (excellent):  All 5 of C1-C5.\n\nOUTPUT: {\"score\": <0..5>, \"reasoning\": \"<1-3 sentences referencing C1..C5>\"}",
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
            node_id="PDF_GENERATION_QUALITY",
            status=status,
            score=score,
            max_score=5.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="PDF_GENERATION_QUALITY",
            status="ERROR",
            score=0.0,
            max_score=5.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "PDF_TOOLS_MERGE": test_pdf_tools_merge,
    "PDF_TOOLS_VERIFY": test_pdf_tools_verify,
    "PDF_GENERATION_QUALITY": test_pdf_generation_quality,
}
