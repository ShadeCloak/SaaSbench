from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import EvalContext, NodeResult
from primitives import execute_primitive


def test_setup_eval_template(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 2
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; u=User.first; f=a.default_template_folder; t=a.templates.find_by(name:'Eval Template'); unless t; suuid=SecureRandom.uuid; fuuid=SecureRandom.uuid; pdf=HexaPDF::Document.new; page=pdf.pages.add([0,0,595,842]); canvas=page.canvas; canvas.font('Helvetica',size:20); canvas.text('Eval Document',at:[200,700]); io=StringIO.new; pdf.write(io); io.rewind; t=Template.create!(account:a,author:u,folder:f,name:'Eval Template',slug:'eval-tpl',fields:[],submitters:[{'name'=>'First Party','uuid'=>suuid}],schema:[],preferences:{},shared_link:true,source:'native'); t.documents.attach(io:io,filename:'eval.pdf',content_type:'application/pdf'); att=t.documents_attachments.last; doc_uuid=att.uuid; t.update!(schema:[{'attachment_uuid'=>doc_uuid,'name'=>'eval.pdf'}],fields:[{'uuid'=>fuuid,'submitter_uuid'=>suuid,'name'=>'Full Name','type'=>'text','required'=>true,'areas'=>[{'uuid'=>SecureRandom.uuid,'x'=>0.1,'y'=>0.1,'w'=>0.3,'h'=>0.05,'attachment_uuid'=>doc_uuid,'page'=>0}]}]); SearchEntries.index_template(t) rescue nil; end; puts t.id\"",
            "expect_success": True,
            "capture_stdout_as": "template_id"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "sql": "SELECT COUNT(*) AS cnt FROM templates WHERE name = 'Eval Template'",
            "expected_result": {
                "cnt": 1
            }
        }
        ok_1, ratio_1 = execute_primitive("P08", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P08"] = {"passed": True, "ratio": ratio_1}

        score = 2.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="SETUP_EVAL_TEMPLATE",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="SETUP_EVAL_TEMPLATE",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


def test_setup_three_party_template(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 2
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"a=Account.first; u=User.first; f=a.default_template_folder; t=a.templates.find_by(name:'ThreeParty Template'); unless t; s1=SecureRandom.uuid; s2=SecureRandom.uuid; s3=SecureRandom.uuid; t=Template.create!(account:a,author:u,folder:f,name:'ThreeParty Template',fields:[{'uuid'=>SecureRandom.uuid,'submitter_uuid'=>s1,'name'=>'F1','type'=>'text','required'=>true,'areas'=>[]}],submitters:[{'name'=>'First Party','uuid'=>s1},{'name'=>'Second Party','uuid'=>s2},{'name'=>'Third Party','uuid'=>s3}],schema:[],preferences:{},source:'native'); end; puts t.id\"",
            "expect_success": True,
            "capture_stdout_as": "three_party_template_id"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        inputs_1 = {
            "sql": "SELECT COUNT(*) AS cnt FROM templates WHERE name = 'ThreeParty Template'",
            "expected_result": {
                "cnt": 1
            }
        }
        ok_1, ratio_1 = execute_primitive("P08", inputs_1, ctx)
        if not ok_1:
            chain_pass = False
            evidence["step_1_P08"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_1_P08"] = {"passed": True, "ratio": ratio_1}

        score = 2.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="SETUP_THREE_PARTY_TEMPLATE",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="SETUP_THREE_PARTY_TEMPLATE",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


def test_setup_test_account(ctx: EvalContext) -> NodeResult:
    chain_pass = True
    pass_count = 0
    total_steps = 1
    evidence = {}
    llm_score = None

    try:
        inputs_0 = {
            "command": "cd /app && RAILS_ENV=production bundle exec rails runner \"prod=Account.first; ta=Account.find_or_create_by!(name:'TestAcct') { |a| a.timezone='UTC'; a.locale='en-US' }; tu=User.find_or_create_by!(email:'test.user@eval.com') { |u| u.account=ta; u.first_name='Test'; u.last_name='User'; u.password='TestPass123!'; u.role='admin' }; AccountLinkedAccount.find_or_create_by!(account:prod,linked_account:ta) { |l| l.account_type='testing' }; tok=(tu.access_token||tu.create_access_token!).token; puts tok\"",
            "expect_success": True,
            "capture_stdout_as": "test_token"
        }
        ok_0, ratio_0 = execute_primitive("P12", inputs_0, ctx)
        if not ok_0:
            chain_pass = False
            evidence["step_0_P12"] = {"passed": False}
        else:
            pass_count += 1
            evidence["step_0_P12"] = {"passed": True, "ratio": ratio_0}

        score = 2.0 if chain_pass else 0.0
        status = "PASSED" if chain_pass else "FAILED"

        return NodeResult(
            node_id="SETUP_TEST_ACCOUNT",
            status=status,
            score=score,
            max_score=2.0,
            evidence=evidence,
            message=f"pass={pass_count}/{total_steps}",
        )
    except Exception as exc:
        return NodeResult(
            node_id="SETUP_TEST_ACCOUNT",
            status="ERROR",
            score=0.0,
            max_score=2.0,
            evidence=evidence,
            message=str(exc),
        )


REGISTRY = {
    "SETUP_EVAL_TEMPLATE": test_setup_eval_template,
    "SETUP_THREE_PARTY_TEMPLATE": test_setup_three_party_template,
    "SETUP_TEST_ACCOUNT": test_setup_test_account,
}
