from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_api_template_list(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 5
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
            "method": "GET",
            "path": "/api/templates"
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
            "required_fields": [
                "data",
                "pagination"
            ]
        }
        ok_3, ratio_3 = execute_primitive("P06", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P06"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P06"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "assertions": [
                {
                    "path": "$.data[0].name",
                    "op": "not_null"
                },
                {
                    "path": "$.data[0].source",
                    "op": "in",
                    "expected": [
                        "native",
                        "api"
                    ]
                },
                {
                    "path": "$.pagination.count",
                    "op": ">=",
                    "expected": 1
                }
            ]
        }
        ok_4, ratio_4 = execute_primitive("P07", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P07"] = {"passed": True, "ratio": ratio_4}

        score = round((pass_count / 5) * 3, 2) if 5 > 0 else 0.0
        status = "PASSED" if pass_count == total_steps else ("FAILED" if pass_count == 0 else "PASSED")

        return NodeResult(
            node_id="API_TEMPLATE_LIST",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_TEMPLATE_LIST",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_template_show(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 5
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
            "method": "GET",
            "path": "/api/templates/{{template_id}}"
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
                    "path": "$.name",
                    "expected": "Eval Template"
                },
                {
                    "path": "$.shared_link",
                    "expected": True
                },
                {
                    "path": "$.source",
                    "expected": "native"
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

        inputs_4 = {
            "required_fields": [
                "id",
                "slug",
                "name",
                "fields",
                "submitters",
                "schema",
                "preferences",
                "source",
                "author_id",
                "folder_id"
            ]
        }
        ok_4, ratio_4 = execute_primitive("P06", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P06"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P06"] = {"passed": True, "ratio": ratio_4}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_TEMPLATE_SHOW",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_TEMPLATE_SHOW",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_template_update(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 6
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
            "method": "PUT",
            "path": "/api/templates/{{template_id}}",
            "body": {
                "name": "Updated Template Name",
                "external_id": "eval-ext-123"
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
            "method": "GET",
            "path": "/api/templates/{{template_id}}"
        }
        ok_3, ratio_3 = execute_primitive("P04", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P04"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "assertions": [
                {
                    "path": "$.name",
                    "expected": "Updated Template Name"
                },
                {
                    "path": "$.external_id",
                    "expected": "eval-ext-123"
                }
            ]
        }
        ok_4, ratio_4 = execute_primitive("P07", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P07"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "method": "PUT",
            "path": "/api/templates/{{template_id}}",
            "body": {
                "name": "Eval Template",
                "external_id": None
            }
        }
        ok_5, ratio_5 = execute_primitive("P04", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P04"] = {"passed": True, "ratio": ratio_5}

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_TEMPLATE_UPDATE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_TEMPLATE_UPDATE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_template_clone(ctx: EvalContext) -> NodeResult:
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
            "path": "/api/templates/{{template_id}}/clone",
            "body": {
                "name": "Cloned Template Name",
                "external_id": "clone-ext-456"
            },
            "capture_response_as": "clone_response"
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
            "response": "{{clone_response}}",
            "assertions": [
                {
                    "path": "$.name",
                    "expected": "Cloned Template Name"
                },
                {
                    "path": "$.source",
                    "expected": "api"
                },
                {
                    "path": "$.id",
                    "op": "not_null",
                    "capture_as": "cloned_template_id"
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

        score = 4.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_TEMPLATE_CLONE",
            status=status,
            score=score,
            max_score=4.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_TEMPLATE_CLONE",
            status="ERROR",
            score=0.0,
            max_score=4.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_template_archive(ctx: EvalContext) -> NodeResult:
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
            "method": "DELETE",
            "path": "/api/templates/{{cloned_template_id}}"
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
                    "path": "$.archived_at",
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
            node_id="API_TEMPLATE_ARCHIVE",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_TEMPLATE_ARCHIVE",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_template_hard_delete(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 5
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
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first;u=User.first;f=a.default_template_folder;t=Template.create!(account:a,author:u,folder:f,name:'ToDelete',fields:[{'uuid'=>SecureRandom.uuid,'submitter_uuid'=>SecureRandom.uuid,'name'=>'X','type'=>'text','required'=>false,'areas'=>[]}],submitters:[{'name'=>'P1','uuid'=>SecureRandom.uuid}],schema:[],preferences:{},source:'native');puts t.id\"",
            "expect_success": True,
            "capture_stdout_as": "delete_template_id"
        }
        ok_1, ratio_1 = execute_primitive("P12", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P12"] = {"passed": True, "ratio": ratio_1}

        inputs_2 = {
            "method": "DELETE",
            "path": "/api/templates/{{delete_template_id}}?permanently=true"
        }
        ok_2, ratio_2 = execute_primitive("P04", inputs_2, ctx)
        if not ok_2:
            chain_pass = False
            evidence["step_2_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_2_P04"] = {"passed": True, "ratio": ratio_2}

        inputs_3 = {
            "expected_status": 200
        }
        ok_3, ratio_3 = execute_primitive("P15", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P15"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P15"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "sql": "SELECT COUNT(*) AS cnt FROM templates WHERE id = {{delete_template_id}}",
            "expected_result": {
                "cnt": 0
            }
        }
        ok_4, ratio_4 = execute_primitive("P08", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P08"] = {"passed": True, "ratio": ratio_4}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_TEMPLATE_HARD_DELETE",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_TEMPLATE_HARD_DELETE",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_template_shared_link(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 8
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
            "method": "PUT",
            "path": "/api/templates/{{template_id}}",
            "body": {
                "shared_link": False
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
            "method": "GET",
            "path": "/api/templates/{{template_id}}"
        }
        ok_3, ratio_3 = execute_primitive("P04", inputs_3, ctx)
        if not ok_3:
            chain_pass = False
            evidence["step_3_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_3_P04"] = {"passed": True, "ratio": ratio_3}

        inputs_4 = {
            "assertions": [
                {
                    "path": "$.shared_link",
                    "expected": False
                }
            ]
        }
        ok_4, ratio_4 = execute_primitive("P07", inputs_4, ctx)
        if not ok_4:
            chain_pass = False
            evidence["step_4_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_4_P07"] = {"passed": True, "ratio": ratio_4}

        inputs_5 = {
            "method": "PUT",
            "path": "/api/templates/{{template_id}}",
            "body": {
                "shared_link": True
            }
        }
        ok_5, ratio_5 = execute_primitive("P04", inputs_5, ctx)
        if not ok_5:
            chain_pass = False
            evidence["step_5_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_5_P04"] = {"passed": True, "ratio": ratio_5}

        inputs_6 = {
            "method": "GET",
            "path": "/api/templates/{{template_id}}"
        }
        ok_6, ratio_6 = execute_primitive("P04", inputs_6, ctx)
        if not ok_6:
            chain_pass = False
            evidence["step_6_P04"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_6_P04"] = {"passed": True, "ratio": ratio_6}

        inputs_7 = {
            "assertions": [
                {
                    "path": "$.shared_link",
                    "expected": True
                }
            ]
        }
        ok_7, ratio_7 = execute_primitive("P07", inputs_7, ctx)
        if not ok_7:
            chain_pass = False
            evidence["step_7_P07"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_7_P07"] = {"passed": True, "ratio": ratio_7}

        score = 3.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="API_TEMPLATE_SHARED_LINK",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_TEMPLATE_SHARED_LINK",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


def test_api_template_filter_query(ctx: EvalContext) -> NodeResult:
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
            "method": "GET",
            "path": "/api/templates?slug=eval-tpl"
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
                    "path": "$.data[0].name",
                    "op": "contains",
                    "expected": "Eval"
                },
                {
                    "path": "$.pagination.count",
                    "op": ">=",
                    "expected": 1
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
            node_id="API_TEMPLATE_FILTER_QUERY",
            status=status,
            score=score,
            max_score=3.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="API_TEMPLATE_FILTER_QUERY",
            status="ERROR",
            score=0.0,
            max_score=3.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "API_TEMPLATE_LIST": test_api_template_list,
    "API_TEMPLATE_SHOW": test_api_template_show,
    "API_TEMPLATE_UPDATE": test_api_template_update,
    "API_TEMPLATE_CLONE": test_api_template_clone,
    "API_TEMPLATE_ARCHIVE": test_api_template_archive,
    "API_TEMPLATE_HARD_DELETE": test_api_template_hard_delete,
    "API_TEMPLATE_SHARED_LINK": test_api_template_shared_link,
    "API_TEMPLATE_FILTER_QUERY": test_api_template_filter_query,
}
