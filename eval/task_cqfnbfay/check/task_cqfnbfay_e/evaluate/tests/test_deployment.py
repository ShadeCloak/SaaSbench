from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_deploy_health(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 2
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "method": "GET",
            "path": "/",
            "timeout": 15
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
                301,
                302,
                401
            ]
        }
        ok_1, ratio_1 = execute_primitive("P15", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P15"] = {"passed": True, "ratio": ratio_1}

        score = 1.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="DEPLOY_HEALTH",
            status=status,
            score=score,
            max_score=1.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DEPLOY_HEALTH",
            status="ERROR",
            score=0.0,
            max_score=1.0,
            evidence=evidence,
            message=str(exc),
        )


def test_deploy_gemfile(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 7
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "path": "Gemfile"
        }
        ok_0, ratio_0 = execute_primitive("P01", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P01"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P01"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "path": "Gemfile",
            "match_type": "contains",
            "pattern": "rails"
        }
        ok_1, ratio_1 = execute_primitive("P02", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P02"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "path": "Gemfile",
            "match_type": "contains",
            "pattern": "hexapdf"
        }
        ok_2, ratio_2 = execute_primitive("P02", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P02"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "path": "Gemfile",
            "match_type": "contains",
            "pattern": "sidekiq"
        }
        ok_3, ratio_3 = execute_primitive("P02", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P02"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "path": "Gemfile",
            "match_type": "contains",
            "pattern": "devise"
        }
        ok_4, ratio_4 = execute_primitive("P02", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P02"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "path": "Gemfile",
            "match_type": "contains",
            "pattern": "cancancan"
        }
        ok_5, ratio_5 = execute_primitive("P02", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P02"] = {"passed": True, "ratio": ratio_5}

        inputs_6 = {
            "path": "Gemfile",
            "match_type": "contains",
            "pattern": "pagy"
        }
        ok_6, ratio_6 = execute_primitive("P02", inputs_6, ctx)
        if not ok_6:
            chain_pass = False
            evidence["step_6_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_6_P02"] = {"passed": True, "ratio": ratio_6}

        score = round((pass_count / 7) * 2, 2) if 7 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DEPLOY_GEMFILE",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DEPLOY_GEMFILE",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


def test_deploy_db_connect(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "sql": "SELECT 1 AS ok",
            "expected_result": {
                "ok": 1
            }
        }
        ok_0, ratio_0 = execute_primitive("P08", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P08"] = {"passed": True, "ratio": ratio_0}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="DEPLOY_DB_CONNECT",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DEPLOY_DB_CONNECT",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_deploy_frontend_deps(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 4
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "path": "package.json"
        }
        ok_0, ratio_0 = execute_primitive("P01", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P01"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P01"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "path": "package.json",
            "match_type": "contains",
            "pattern": "vue"
        }
        ok_1, ratio_1 = execute_primitive("P02", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P02"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "path": "package.json",
            "match_type": "contains",
            "pattern": "tailwindcss"
        }
        ok_2, ratio_2 = execute_primitive("P02", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P02"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "path": "package.json",
            "match_type": "contains",
            "pattern": "daisyui"
        }
        ok_3, ratio_3 = execute_primitive("P02", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P02"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P02"] = {"passed": True, "ratio": ratio_3}

        score = round((pass_count / 4) * 2, 2) if 4 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="DEPLOY_FRONTEND_DEPS",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="DEPLOY_FRONTEND_DEPS",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "DEPLOY_HEALTH": test_deploy_health,
    "DEPLOY_GEMFILE": test_deploy_gemfile,
    "DEPLOY_DB_CONNECT": test_deploy_db_connect,
    "DEPLOY_FRONTEND_DEPS": test_deploy_frontend_deps,
}
