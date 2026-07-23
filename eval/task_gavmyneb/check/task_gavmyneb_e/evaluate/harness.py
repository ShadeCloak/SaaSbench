from __future__ import annotations
import json
import os
import time
from collections import defaultdict
from typing import Any

import config
import primitives
import utils


def _inject_test_user_placeholders(ctx: dict) -> None:
    test_users = getattr(config, "TEST_USERS", None) or {}
    for role, info in test_users.items():
        if not isinstance(info, dict):
            continue
        for field, value in info.items():
            if isinstance(value, (str, int, float, bool)):
                ctx.setdefault(f"{role}_{field}", value)
                ctx.setdefault(f"eval_{role}_{field}", value)



try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

log = utils.log


# =============================================================================
# =============================================================================
ENTITY_ID_KEYWORDS = {
    "COURSE": "course_id", "CRUD_COURSE": "course_id",
    "ENROLLMENT": "enrollment_id", "ENROLL": "enrollment_id",
    "USER": "user_id", "PSEUDONYM": "pseudonym_id",
    "ACCOUNT": "account_id",
    "SECTION": "section_id",
    "ASSIGNMENT": "assignment_id",
    "SUBMISSION": "submission_id",
    "QUIZ": "quiz_id",
    "MODULE": "module_id",
    "FILE": "file_id", "ATTACHMENT": "attachment_id",
    "FOLDER": "folder_id",
    "DISCUSSION": "discussion_topic_id",
    "ANNOUNCEMENT": "announcement_id",
    "CONVERSATION": "conversation_id",
    "WIKI": "wiki_page_id", "PAGE": "wiki_page_id",
    "RUBRIC": "rubric_id",
    "OUTCOME": "outcome_id",
    "GROUP": "group_id",
    "TOOL": "tool_id", "LTI": "tool_id",
    "DEVELOPER_KEY": "developer_key_id",
    "ROLE": "role_id",
    "TERM": "enrollment_term_id",
}


def extract_entity_ids(node_id: str, response_body: dict, context: dict) -> None:
    if not isinstance(response_body, dict):
        return
    rid = response_body.get("id") or response_body.get("data", {}).get("id") if isinstance(response_body.get("data"), dict) else response_body.get("id")
    if rid is None:
        return
    context["id"] = rid
    nid_upper = node_id.upper()
    for kw, var in ENTITY_ID_KEYWORDS.items():
        if kw in nid_upper:
            context[var] = rid
            log.debug(f"  bound {kw} → {var}={rid}")
            break


# =============================================================================
# =============================================================================
def _bind_infra(context: dict) -> None:
    context.setdefault("app_container", config.APP_CONTAINER)
    context.setdefault("db_container", config.DB_CONTAINER)
    context.setdefault("redis_container", config.REDIS_CONTAINER)
    context.setdefault("worker_container", config.WORKER_CONTAINER)
    context.setdefault("base_url", config.API_BASE_URL)
    for role in ("admin", "teacher", "student", "observer", "ta", "account_admin"):
        tok = os.environ.get(f"HARNESS_{role.upper()}_TOKEN")
        if tok:
            context.setdefault(f"{role}_token", tok)
    if context.get("admin_token"):
        context.setdefault("site_admin_token", context["admin_token"])


def _seed_entities(context: dict) -> None:
    try:
        import requests
    except Exception:
        log.warning("seed: requests unavailable, skipping entity seed")
        return
    base = config.API_BASE_URL
    admin = os.environ.get("HARNESS_ADMIN_TOKEN") or context.get("admin_token")
    if not admin:
        log.warning("seed: no admin token available, skipping entity seed")
        return
    H = {"Authorization": f"Bearer {admin}"}
    T = config.DEFAULT_HTTP_TIMEOUT

    def _req(method, path, **kw):
        try:
            return requests.request(method, f"{base}{path}", headers=H, timeout=T, **kw)
        except Exception as e:
            log.warning(f"seed {method} {path} failed: {e}")
            return None

    def _jid(r):
        if r is None:
            return None
        try:
            d = r.json()
        except Exception:
            return None
        return d.get("id") if isinstance(d, dict) else None

    def _bind(keys, val):
        if val is None:
            return
        for k in keys:
            context[k] = val

    _bind(["account_id", "acct_id", "eval_account_id", "root_account_id"], 1)

    import time as _time_role
    _bind(["eval_role_id", "role_id"],
          _jid(_req("POST", "/api/v1/accounts/1/roles",
                    data={"label": f"Eval Role {int(_time_role.time())}",
                          "base_role_type": "AccountMembership"})))

    student_tok = os.environ.get("HARNESS_STUDENT_TOKEN")

    def _sreq(method, path, **kw):
        if not student_tok:
            return None
        try:
            return requests.request(method, f"{base}{path}",
                                    headers={"Authorization": f"Bearer {student_tok}"},
                                    timeout=T, **kw)
        except Exception as e:
            log.warning(f"seed(student) {method} {path} failed: {e}")
            return None

    _req("PUT", "/api/v1/users/self", json={"user": {"locale": "en"}})
    _req("POST", "/api/v1/accounts/1/authentication_providers",
         json={"auth_type": "ldap", "auth_host": "ldap.seed.test", "auth_base": "dc=seed"})
    try:
        _ruby3 = (
            "acct=Account.default; u=User.find(2); "
            "c=Course.where(name:'EvalDeepThreadCourse').order(:id).last; "
            "if c.nil?; c=acct.courses.create!(name:'EvalDeepThreadCourse'); c.offer!; "
            "c.enroll_user(u,'TeacherEnrollment', enrollment_state:'active'); end; "
            "DiscussionTopic.where(context:c, title:'EvalDeepThread').destroy_all; "
            "t=c.discussion_topics.create!(title:'EvalDeepThread', message:'root', user:u, workflow_state:'active'); "
            "cur=t.discussion_entries.create!(message:'e1', user:u); "
            "(2..50).each{|i| cur=t.discussion_entries.create!(message:'e'+i.to_s, user:u, parent_entry:cur)}; "
            "puts 'DEEP_IDS ' + c.id.to_s + ' ' + t.id.to_s + ' ' + cur.id.to_s"
        )
        _out = utils.docker_exec(config.APP_CONTAINER,
                                 f"cd /usr/src/app && bin/rails runner \"{_ruby3}\"",
                                 timeout=180)
        import re as _re3
        _m3 = _re3.search(r"DEEP_IDS\s+(\d+)\s+(\d+)\s+(\d+)", (_out.stdout or ""))
        if _m3:
            _bind(["deep_course_id"], int(_m3.group(1)))
            _bind(["deep_topic_id"], int(_m3.group(2)))
            _bind(["entry_at_depth_50_id"], int(_m3.group(3)))
    except Exception as _e:
        log.warning(f"seed deep-thread failed: {_e}")
    try:
        _lti_c = _jid(_req("POST", "/api/v1/accounts/1/courses",
                           data={"course[name]": "LTI Tool Course"}))
        if _lti_c:
            _req("PUT", f"/api/v1/courses/{_lti_c}", data={"course[event]": "offer"})
            _lti_tool = _jid(_req("POST", f"/api/v1/courses/{_lti_c}/external_tools",
                                  json={"name": "Eval DL Tool", "consumer_key": "k",
                                        "shared_secret": "s", "url": "https://tool.test/launch",
                                        "privacy_level": "public",
                                        "course_navigation": {"enabled": True,
                                                              "message_type": "LtiDeepLinkingRequest"}}))
            if _lti_tool:
                _bind(["lti_tool_id"], _lti_tool)
    except Exception as _e:
        log.warning(f"seed LTI tool failed: {_e}")
    prof = _req("GET", "/api/v1/users/self/profile")
    try:
        login_id = prof.json().get("login_id") if prof is not None else None
    except Exception:
        login_id = None
    _bind(["admin_email", "eval_admin_email"], login_id or "eval_admin@test.com")

    try:
        dkr = _req("POST", "/api/v1/accounts/1/developer_keys",
                   json={"developer_key": {"name": "eval_oauth_key",
                                           "redirect_uri": "http://localhost:9999/cb"}})
        dkj = dkr.json() if dkr is not None else {}
        if isinstance(dkj, dict) and dkj.get("id"):
            _bind(["eval_developer_key_id", "developer_key_id",
                   "eval_public_client_id"], dkj.get("id"))
            _bind(["eval_developer_secret"], dkj.get("api_key"))
    except Exception:
        pass
    if not context.get("eval_developer_key_id"):
        dk = _req("GET", "/api/v1/accounts/1/developer_keys")
        try:
            dks = dk.json() if dk is not None else None
            if isinstance(dks, dict):
                dks = dks.get("developer_keys") or dks.get("results")
            if isinstance(dks, list) and dks:
                _bind(["eval_developer_key_id", "developer_key_id",
                       "eval_public_client_id"], dks[0].get("id"))
        except Exception:
            pass

    self_uid = _jid(_req("GET", "/api/v1/users/self"))
    _bind(["self_uid"], self_uid)
    _bind(["eval_user_id"], self_uid)
    _bind(["eval_mfa_user_id"], self_uid)
    role_uid = {}
    for role, em in (("teacher", "eval_teacher@test.com"),
                     ("student", "eval_student@test.com"),
                     ("ta", "eval_ta@test.com"),
                     ("observer", "eval_observer@test.com")):
        rr = _req("GET", f"/api/v1/accounts/1/users?search_term={em}")
        try:
            arr = rr.json() if rr is not None else []
            if isinstance(arr, list) and arr:
                role_uid[role] = arr[0].get("id")
        except Exception:
            pass
    _bind(["uid", "user_id", "student_id", "sid_user", "student_uid"], role_uid.get("student"))
    _bind(["peer_uid", "other_uid", "user_b_id"], role_uid.get("teacher") or self_uid)
    try:
        _rac = _jid(_req("POST", "/api/v1/accounts/1/courses",
                         data={"course[name]": "Rubric Assess Course"}))
        if _rac and role_uid.get("student"):
            _req("PUT", f"/api/v1/courses/{_rac}", data={"course[event]": "offer"})
            _req("POST", f"/api/v1/courses/{_rac}/enrollments",
                 data={"enrollment[user_id]": role_uid["student"],
                       "enrollment[type]": "StudentEnrollment",
                       "enrollment[enrollment_state]": "active"})
            _raa = _jid(_req("POST", f"/api/v1/courses/{_rac}/assignments",
                             json={"assignment": {"name": "Rubric A", "points_possible": 10,
                                                  "submission_types": ["online_text_entry"],
                                                  "published": True}}))
            _rubric_resp = _req("POST", f"/api/v1/courses/{_rac}/rubrics",
                                json={"rubric": {"title": "Assess RB",
                                                 "criteria": {"0": {"description": "C1", "points": 10,
                                                                    "ratings": {"0": {"description": "Full", "points": 10},
                                                                                "1": {"description": "None", "points": 0}}}}},
                                      "rubric_association": {"association_type": "Assignment",
                                                             "association_id": _raa, "purpose": "grading",
                                                             "use_for_grading": True}})
            try:
                _rj = _rubric_resp.json() if _rubric_resp is not None else {}
                _assoc = (_rj.get("rubric_association") or {}).get("id")
                _crit = ((_rj.get("rubric") or {}).get("data") or [{}])[0].get("id")
                if _assoc:
                    _bind(["ra_association_id"], _assoc)
                if _crit:
                    _bind(["ra_criterion_id"], _crit)
            except Exception:
                pass
            if _raa:
                _rsub = _sreq("POST", f"/api/v1/courses/{_rac}/assignments/{_raa}/submissions",
                              json={"submission": {"submission_type": "online_text_entry", "body": "hi"}})
                try:
                    if _rsub is not None:
                        _bind(["ra_submission_id"], _rsub.json().get("id"))
                except Exception:
                    pass
    except Exception as _e:
        log.warning(f"seed rubric-assessment failed: {_e}")
    _bind(["teacher_uid", "teacher_id"], role_uid.get("teacher"))
    _bind(["ta_uid", "ta_id"], role_uid.get("ta"))
    _bind(["observer_uid", "observer_id"], role_uid.get("observer"))

    cid = _jid(_req("POST", "/api/v1/accounts/1/courses", data={"course[name]": "Seed Course"}))
    _bind(["cid", "course_id", "eval_course_id", "gql_course_id",
           "template_cid", "child_cid", "foreign_root_cid", "cid_other"], cid)
    if cid:
        _req("PUT", f"/api/v1/courses/{cid}", data={"course[event]": "offer"})
        if role_uid.get("teacher"):
            _req("POST", f"/api/v1/courses/{cid}/enrollments",
                 data={"enrollment[user_id]": role_uid["teacher"],
                       "enrollment[type]": "TeacherEnrollment",
                       "enrollment[enrollment_state]": "active"})
        if role_uid.get("student"):
            er = _req("POST", f"/api/v1/courses/{cid}/enrollments",
                      data={"enrollment[user_id]": role_uid["student"],
                            "enrollment[type]": "StudentEnrollment",
                            "enrollment[enrollment_state]": "active"})
            _bind(["eid", "enrollment_id"], _jid(er))
        if role_uid.get("ta"):
            _req("POST", f"/api/v1/courses/{cid}/enrollments",
                 data={"enrollment[user_id]": role_uid["ta"],
                       "enrollment[type]": "TaEnrollment",
                       "enrollment[enrollment_state]": "active"})
        if role_uid.get("observer"):
            odata = {"enrollment[user_id]": role_uid["observer"],
                     "enrollment[type]": "ObserverEnrollment",
                     "enrollment[enrollment_state]": "active"}
            if role_uid.get("student"):
                odata["enrollment[associated_user_id]"] = role_uid["student"]
            _req("POST", f"/api/v1/courses/{cid}/enrollments", data=odata)
        aid = _jid(_req("POST", f"/api/v1/courses/{cid}/assignments",
                        data={"assignment[name]": "Seed Assignment",
                              "assignment[submission_types][]": "online_text_entry",
                              "assignment[points_possible]": "10",
                              "assignment[published]": "true"}))
        _bind(["aid", "assignment_id"], aid)
        _bind(["mid", "module_id"], _jid(_req("POST", f"/api/v1/courses/{cid}/modules",
                                              data={"module[name]": "Seed Module"})))
        _dm = _jid(_req("POST", f"/api/v1/courses/{cid}/modules",
                        data={"module[name]": "Seed Delete Module"}))
        if _dm:
            _req("PUT", f"/api/v1/courses/{cid}/modules/{_dm}", data={"module[published]": "true"})
            _bind(["del_module_id"], _dm)
        _bind(["unpublished_module_id"],
              _jid(_req("POST", f"/api/v1/courses/{cid}/modules",
                        data={"module[name]": "Seed Unpublished Module"})))
        _bind(["topic_id", "discussion_topic_id", "gql_topic_id"],
              _jid(_req("POST", f"/api/v1/courses/{cid}/discussion_topics",
                        data={"title": "Seed Topic", "message": "seed",
                              "published": "true"})))
        _bind(["moderate_topic_id"],
              _jid(_req("POST", f"/api/v1/courses/{cid}/discussion_topics",
                        data={"title": "Seed Moderate Topic", "message": "seed",
                              "published": "true"})))
        _lt = _jid(_req("POST", f"/api/v1/courses/{cid}/discussion_topics",
                        data={"title": "Seed Locked Topic", "message": "seed",
                              "published": "true"}))
        if _lt:
            _req("PUT", f"/api/v1/courses/{cid}/discussion_topics/{_lt}",
                 data={"locked": "true"})
        _bind(["locked_topic_id"], _lt)
        _req("POST", f"/api/v1/courses/{cid}/discussion_topics",
             data={"title": "Seed Announcement", "message": "seed",
                   "is_announcement": "true", "published": "true"})
        _bind(["qid", "quiz_id"], _jid(_req("POST", f"/api/v1/courses/{cid}/quizzes",
                                            data={"quiz[title]": "Seed Quiz"})))
        if context.get("qid"):
            _bind(["quiz_question_id", "quiz_question"],
                  _jid(_req("POST", f"/api/v1/courses/{cid}/quizzes/{context['qid']}/questions",
                            data={"question[question_name]": "Q1",
                                  "question[question_type]": "multiple_choice_question",
                                  "question[question_text]": "2+2?",
                                  "question[points_possible]": "10",
                                  "question[answers][0][answer_text]": "4",
                                  "question[answers][0][answer_weight]": "100",
                                  "question[answers][1][answer_text]": "5",
                                  "question[answers][1][answer_weight]": "0"})))
        _bind(["sid", "section_id"], _jid(_req("POST", f"/api/v1/courses/{cid}/sections",
                                               data={"course_section[name]": "Seed Section"})))
        _bind(["course_context"], f"course_{cid}")
        _bind(["lpid", "late_policy_id"],
              _jid(_req("POST", f"/api/v1/courses/{cid}/late_policy",
                        data={"late_policy[missing_submission_deduction_enabled]": "true"})))
        if role_uid.get("student"):
            lpc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                            data={"course[name]": "Late Policy Course"}))
            if lpc:
                _req("PUT", f"/api/v1/courses/{lpc}", data={"course[event]": "offer"})
                _req("POST", f"/api/v1/courses/{lpc}/enrollments",
                     data={"enrollment[user_id]": role_uid["student"],
                           "enrollment[type]": "StudentEnrollment",
                           "enrollment[enrollment_state]": "active"})
                _req("POST", f"/api/v1/courses/{lpc}/late_policy",
                     data={"late_policy[late_submission_deduction_enabled]": "true",
                           "late_policy[late_submission_deduction]": "10",
                           "late_policy[late_submission_interval]": "day"})
                lpa = _jid(_req("POST", f"/api/v1/courses/{lpc}/assignments",
                                json={"assignment": {"name": "Late A",
                                                     "points_possible": 1000,
                                                     "submission_types": ["online_text_entry"],
                                                     "published": True}}))
                if lpa:
                    _req("PUT",
                         f"/api/v1/courses/{lpc}/assignments/{lpa}/submissions/{role_uid['student']}",
                         json={"submission": {"posted_grade": "1000",
                                              "late_policy_status": "late",
                                              "seconds_late_override": 90000}})
                _bind(["lp_course_id"], lpc)
                _bind(["lp_assignment_id"], lpa)
        ovc2 = _jid(_req("POST", "/api/v1/accounts/1/courses",
                         data={"course[name]": "Override Res Course"}))
        if ovc2:
            _req("PUT", f"/api/v1/courses/{ovc2}", data={"course[event]": "offer"})
            ov_sec = _jid(_req("POST", f"/api/v1/courses/{ovc2}/sections",
                               data={"course_section[name]": "OV Section"}))
            ova = _jid(_req("POST", f"/api/v1/courses/{ovc2}/assignments",
                            json={"assignment": {"name": "OV A", "points_possible": 10,
                                                 "due_at": "2026-09-01T00:00:00Z",
                                                 "published": True}}))
            if ova and ov_sec:
                _req("POST", f"/api/v1/courses/{ovc2}/assignments/{ova}/overrides",
                     json={"assignment_override": {"course_section_id": ov_sec,
                                                   "due_at": "2026-09-10T00:00:00Z"}})
            _bind(["ov_course_id"], ovc2)
            _bind(["ov_assignment_id"], ova)
        pcc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                        data={"course[name]": "Paced Course"}))
        if pcc:
            _req("PUT", f"/api/v1/courses/{pcc}",
                 json={"course": {"event": "offer", "enable_course_paces": True}})
            _req("POST", f"/api/v1/courses/{pcc}/late_policy",
                 json={"late_policy": {"late_submission_deduction_enabled": True,
                                       "late_submission_deduction": 10,
                                       "late_submission_interval": "day"}})
            _req("POST", f"/api/v1/courses/{pcc}/blackout_dates",
                 json={"blackout_date": {"event_title": "Winter Holiday",
                                         "start_date": "2026-12-24",
                                         "end_date": "2026-12-26"}})
            pace = _req("POST", f"/api/v1/courses/{pcc}/course_pacing",
                        json={"course_pace": {"exclude_weekends": True}})
            try:
                pj = pace.json() if pace is not None else {}
                pid = (pj.get("course_pace") or pj).get("id")
            except Exception:
                pid = None
            _bind(["pace_course_id"], pcc)
            if pid:
                _bind(["pace_id"], pid)
        mbp = _jid(_req("POST", "/api/v1/accounts/1/courses",
                        data={"course[name]": "Blueprint Master"}))
        if mbp:
            _req("PUT", f"/api/v1/courses/{mbp}", json={"course": {"blueprint": True}})
            mbp_a = _jid(_req("POST", f"/api/v1/courses/{mbp}/assignments",
                              json={"assignment": {"name": "BP Assign",
                                                   "points_possible": 10,
                                                   "published": True}}))
            mbp_child = _jid(_req("POST", "/api/v1/accounts/1/courses",
                                  data={"course[name]": "Blueprint Child"}))
            if mbp_child:
                _req("PUT", f"/api/v1/courses/{mbp}/blueprint_templates/default/update_associations",
                     json={"course_ids_to_add": [mbp_child]})
                _req("POST", f"/api/v1/courses/{mbp}/blueprint_templates/default/migrations",
                     json={"comment": "seed sync"})
                _bind(["mbp_child_cid", "child_cid"], mbp_child)
            _bind(["mbp_master_cid", "mcid"], mbp)
            if mbp_a:
                _bind(["mbp_assignment_id"], mbp_a)
            try:
                import primitives as _prim
                import time as _t2
                _c = _prim.get_db_connection()
                if _c is not None:
                    _tid = None
                    for _ in range(10):
                        with _c.cursor() as _cur:
                            _cur.execute("SELECT id FROM master_courses_master_templates WHERE course_id=%s",
                                         (int(mbp) % 10_000_000_000_000,))
                            _r = _cur.fetchone()
                            _tid = _r[0] if _r else None
                            if _tid:
                                _cur.execute("SELECT count(*) FROM master_courses_master_content_tags WHERE master_template_id=%s", (_tid,))
                                if (_cur.fetchone() or [0])[0] > 0:
                                    break
                        _t2.sleep(3)
                    if _tid:
                        _bind(["mbp_template_id"], _tid)
                        with _c.cursor() as _cur:
                            _cur.execute("SELECT id FROM master_courses_master_content_tags WHERE master_template_id=%s ORDER BY id LIMIT 1", (_tid,))
                            _r = _cur.fetchone()
                            if _r:
                                _bind(["mctid"], _r[0])
            except Exception as _e:
                log.warning(f"seed blueprint tag lookup failed: {_e}")
        if role_uid.get("student"):
            rjc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                            data={"course[name]": "Reject WF Course"}))
            if rjc:
                _req("PUT", f"/api/v1/courses/{rjc}", data={"course[event]": "offer"})
                rj_eid = _jid(_req("POST", f"/api/v1/courses/{rjc}/enrollments",
                                   data={"enrollment[user_id]": role_uid["student"],
                                         "enrollment[type]": "StudentEnrollment",
                                         "enrollment[enrollment_state]": "invited"}))
                if rj_eid:
                    _sreq("POST", f"/api/v1/courses/{rjc}/enrollments/{rj_eid}/reject")
                    _bind(["rejected_enrollment_id"], rj_eid)
        _bind(["ag_id", "appointment_group_id"],
              _jid(_req("POST", "/api/v1/appointment_groups",
                        data={"appointment_group[context_codes][]": f"course_{cid}",
                              "appointment_group[title]": "Seed AG"})))
        _bind(["template_cid"],
              _jid(_req("POST", "/api/v1/accounts/1/courses",
                        json={"course": {"name": "Seed Template", "template": True}})))
        _bind(["eval_sub_account_id"],
              _jid(_req("POST", "/api/v1/accounts/1/sub_accounts",
                        json={"account": {"name": "Seed Sub Account"}})))
        if context.get("mid"):
            mi_data = {"module_item[title]": "Seed Item"}
            if context.get("aid"):
                mi_data.update({"module_item[type]": "Assignment",
                                "module_item[content_id]": context["aid"],
                                "module_item[completion_requirement][type]": "must_mark_done"})
            else:
                mi_data["module_item[type]"] = "SubHeader"
            _bind(["module_item_id", "item_id"],
                  _jid(_req("POST", f"/api/v1/courses/{cid}/modules/{context['mid']}/items",
                            data=mi_data)))
            _req("PUT", f"/api/v1/courses/{cid}/modules/{context['mid']}",
                 data={"module[published]": "true"})
        rr = _req("POST", f"/api/v1/courses/{cid}/rubrics",
                  data=[("rubric[title]", "Seed Rubric"),
                        ("rubric_association[association_type]", "Course"),
                        ("rubric_association[association_id]", str(cid)),
                        ("rubric_association[purpose]", "bookmark"),
                        ("rubric[criteria][0][description]", "C1"),
                        ("rubric[criteria][0][points]", "5"),
                        ("rubric[criteria][0][ratings][0][description]", "Full"),
                        ("rubric[criteria][0][ratings][0][points]", "5"),
                        ("rubric[criteria][0][ratings][1][description]", "None"),
                        ("rubric[criteria][0][ratings][1][points]", "0"),
                        ("rubric[criteria][1][description]", "C2"),
                        ("rubric[criteria][1][points]", "3"),
                        ("rubric[criteria][1][ratings][0][description]", "Full"),
                        ("rubric[criteria][1][ratings][0][points]", "3"),
                        ("rubric[criteria][1][ratings][1][description]", "None"),
                        ("rubric[criteria][1][ratings][1][points]", "0")])
        rid = None
        if rr is not None:
            try:
                rd = rr.json()
                rid = (rd.get("rubric") or {}).get("id") or rd.get("id")
            except Exception:
                pass
        _bind(["rid", "rubric_id"], rid)
        rog = _req("GET", f"/api/v1/courses/{cid}/root_outcome_group")
        try:
            gid = rog.json().get("id") if rog is not None else None
        except Exception:
            gid = None
        if gid:
            oc = _req("POST", f"/api/v1/courses/{cid}/outcome_groups/{gid}/outcomes",
                      data={"title": "Seed Outcome",
                            "calculation_method": "decaying_average",
                            "calculation_int": "65"})
            oid = None
            try:
                oid = (oc.json().get("outcome") or {}).get("id") if oc is not None else None
            except Exception:
                pass
            _bind(["outcome_id", "ocmid", "learning_outcome_id"], oid)
        gc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                       data={"course[name]": "Seed Grade Course"}))
        if gc:
            _req("PUT", f"/api/v1/courses/{gc}", data={"course[event]": "offer"})
            for _u, _t in ((role_uid.get("teacher"), "TeacherEnrollment"),
                           (role_uid.get("ta"), "TaEnrollment"),
                           (role_uid.get("student"), "StudentEnrollment")):
                if _u:
                    _req("POST", f"/api/v1/courses/{gc}/enrollments",
                         data={"enrollment[user_id]": _u,
                               "enrollment[type]": _t,
                               "enrollment[enrollment_state]": "active"})
            _bind(["grade_course_id"], gc)
            _bind(["grade_assignment_id"],
                  _jid(_req("POST", f"/api/v1/courses/{gc}/assignments",
                            data={"assignment[name]": "Grade Assignment",
                                  "assignment[submission_types][]": "online_text_entry",
                                  "assignment[points_possible]": "10",
                                  "assignment[published]": "true"})))
            _bind(["disc_course_id"], gc)
            _bind(["disc_topic_id"],
                  _jid(_req("POST", f"/api/v1/courses/{gc}/discussion_topics",
                            data={"title": "Grade Disc Topic", "message": "seed",
                                  "published": "true"})))
            _dlt = _jid(_req("POST", f"/api/v1/courses/{gc}/discussion_topics",
                             data={"title": "Grade Disc Locked", "message": "seed",
                                   "published": "true"}))
            if _dlt:
                _req("PUT", f"/api/v1/courses/{gc}/discussion_topics/{_dlt}",
                     data={"locked": "true"})
            _bind(["disc_locked_topic_id"], _dlt)
        ovc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                        data={"course[name]": "Seed Override Course",
                              "course[allow_final_grade_override]": "true"}))
        if ovc and role_uid.get("student"):
            _req("PUT", f"/api/v1/courses/{ovc}", data={"course[event]": "offer"})
            _req("PUT", f"/api/v1/courses/{ovc}/features/flags/final_grades_override",
                 data={"state": "on"})
            ov_eid = _jid(_req("POST", f"/api/v1/courses/{ovc}/enrollments",
                               data={"enrollment[user_id]": role_uid["student"],
                                     "enrollment[type]": "StudentEnrollment",
                                     "enrollment[enrollment_state]": "active"}))
            ov_aid = _jid(_req("POST", f"/api/v1/courses/{ovc}/assignments",
                               data={"assignment[name]": "Override Assignment",
                                     "assignment[points_possible]": "10",
                                     "assignment[published]": "true"}))
            if ov_aid:
                _req("PUT", f"/api/v1/courses/{ovc}/assignments/{ov_aid}/submissions/{role_uid['student']}",
                     data={"submission[posted_grade]": "5"})
            if ov_eid:
                _req("POST", "/api/graphql",
                     json={"query": "mutation($e:ID!,$s:Float!){ setOverrideScore(input:{enrollmentId:$e, overrideScore:$s}){ grades{ overrideScore } errors{ message } } }",
                           "variables": {"e": str(ov_eid), "s": 88}})
            _bind(["override_course_id"], ovc)
            _bind(["override_enrollment_id"], ov_eid)
        import datetime as _dt
        gp_term = _jid(_req("POST", "/api/v1/accounts/1/terms",
                            data={"enrollment_term[name]": "Seed GP Term"}))
        if gp_term and role_uid.get("student"):
            gpset = None
            gpset_r = _req("POST", "/api/v1/accounts/1/grading_period_sets",
                           data={"enrollment_term_ids[]": gp_term,
                                 "grading_period_set[title]": "Seed GP Set"})
            try:
                gpset = (gpset_r.json().get("grading_period_set") or {}).get("id") if gpset_r is not None else None
            except Exception:
                pass
            if gpset:
                now = _dt.datetime.utcnow()
                cur_start = (now - _dt.timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
                cur_end = (now + _dt.timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
                due_in = now.strftime("%Y-%m-%dT00:00:00Z")
                pr = _req("PATCH", f"/api/v1/grading_period_sets/{gpset}/grading_periods/batch_update",
                          data=[("grading_periods[][title]", "Closed"),
                                ("grading_periods[][start_date]", "2020-01-01T00:00:00Z"),
                                ("grading_periods[][end_date]", "2020-03-01T00:00:00Z"),
                                ("grading_periods[][close_date]", "2020-03-01T00:00:00Z"),
                                ("grading_periods[][title]", "Current"),
                                ("grading_periods[][start_date]", cur_start),
                                ("grading_periods[][end_date]", cur_end),
                                ("grading_periods[][close_date]", cur_end)])
                closed_id = cur_id = None
                try:
                    for p in (pr.json().get("grading_periods", []) if pr is not None else []):
                        if p.get("is_closed"):
                            closed_id = p.get("id")
                        else:
                            cur_id = p.get("id")
                except Exception:
                    pass
                _bind(["gpid"], closed_id)
                _bind(["gp_current_id"], cur_id)
                gpc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                                data={"course[name]": "Seed GP Course",
                                      "course[term_id]": gp_term}))
                if gpc:
                    _req("PUT", f"/api/v1/courses/{gpc}", data={"course[event]": "offer"})
                    _req("POST", f"/api/v1/courses/{gpc}/enrollments",
                         data={"enrollment[user_id]": role_uid["student"],
                               "enrollment[type]": "StudentEnrollment",
                               "enrollment[enrollment_state]": "active"})
                    gp_aid = _jid(_req("POST", f"/api/v1/courses/{gpc}/assignments",
                                       data={"assignment[name]": "GP Assignment",
                                             "assignment[points_possible]": "10",
                                             "assignment[published]": "true",
                                             "assignment[due_at]": due_in}))
                    if gp_aid:
                        _req("PUT", f"/api/v1/courses/{gpc}/assignments/{gp_aid}/submissions/{role_uid['student']}",
                             data={"submission[posted_grade]": "5"})
                    _bind(["gp_course_id"], gpc)
        muc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                        data={"course[name]": "Seed Mute Course"}))
        if muc and role_uid.get("student"):
            _req("PUT", f"/api/v1/courses/{muc}", data={"course[event]": "offer"})
            _req("POST", f"/api/v1/courses/{muc}/enrollments",
                 data={"enrollment[user_id]": role_uid["student"],
                       "enrollment[type]": "StudentEnrollment",
                       "enrollment[enrollment_state]": "active"})
            mu_a1 = _jid(_req("POST", f"/api/v1/courses/{muc}/assignments",
                              data={"assignment[name]": "Mute A1",
                                    "assignment[points_possible]": "10",
                                    "assignment[published]": "true"}))
            _req("POST", f"/api/v1/courses/{muc}/assignments",
                 data={"assignment[name]": "Mute A2",
                       "assignment[points_possible]": "10",
                       "assignment[published]": "true"})
            if mu_a1:
                _req("PUT", f"/api/v1/courses/{muc}/assignments/{mu_a1}/submissions/{role_uid['student']}",
                     data={"submission[posted_grade]": "5"})
            _bind(["mute_course_id"], muc)
        drc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                        data={"course[name]": "Seed Drop Course"}))
        if drc and role_uid.get("student"):
            _req("PUT", f"/api/v1/courses/{drc}", data={"course[event]": "offer"})
            _req("POST", f"/api/v1/courses/{drc}/enrollments",
                 data={"enrollment[user_id]": role_uid["student"],
                       "enrollment[type]": "StudentEnrollment",
                       "enrollment[enrollment_state]": "active"})
            dr_grp = _jid(_req("POST", f"/api/v1/courses/{drc}/assignment_groups",
                               data={"name": "Drop Group"}))
            dr_a1 = _jid(_req("POST", f"/api/v1/courses/{drc}/assignments",
                              data={"assignment[name]": "Drop A1",
                                    "assignment[points_possible]": "10",
                                    "assignment[published]": "true",
                                    "assignment[assignment_group_id]": dr_grp}))
            dr_a2 = _jid(_req("POST", f"/api/v1/courses/{drc}/assignments",
                              data={"assignment[name]": "Drop A2",
                                    "assignment[points_possible]": "10",
                                    "assignment[published]": "true",
                                    "assignment[assignment_group_id]": dr_grp}))
            if dr_grp:
                _req("PUT", f"/api/v1/courses/{drc}/assignment_groups/{dr_grp}",
                     data={"rules": "drop_lowest:1"})
            if dr_a1:
                _req("PUT", f"/api/v1/courses/{drc}/assignments/{dr_a1}/submissions/{role_uid['student']}",
                     data={"submission[posted_grade]": "5"})
            if dr_a2:
                _req("PUT", f"/api/v1/courses/{drc}/assignments/{dr_a2}/submissions/{role_uid['student']}",
                     data={"submission[posted_grade]": "0"})
            _bind(["drop_course_id"], drc)
        gsc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                        data={"course[name]": "Seed GS Course"}))
        if gsc and role_uid.get("student"):
            _req("PUT", f"/api/v1/courses/{gsc}", data={"course[event]": "offer"})
            _req("POST", f"/api/v1/courses/{gsc}/enrollments",
                 data={"enrollment[user_id]": role_uid["student"],
                       "enrollment[type]": "StudentEnrollment",
                       "enrollment[enrollment_state]": "active"})
            gsid = _jid(_req("POST", f"/api/v1/courses/{gsc}/grading_standards",
                             data=[("title", "Seed GS"),
                                   ("grading_scheme_entry[][name]", "A"), ("grading_scheme_entry[][value]", "90"),
                                   ("grading_scheme_entry[][name]", "B"), ("grading_scheme_entry[][value]", "55"),
                                   ("grading_scheme_entry[][name]", "C+"), ("grading_scheme_entry[][value]", "45"),
                                   ("grading_scheme_entry[][name]", "C"), ("grading_scheme_entry[][value]", "40"),
                                   ("grading_scheme_entry[][name]", "F"), ("grading_scheme_entry[][value]", "0")]))
            gs_aid = _jid(_req("POST", f"/api/v1/courses/{gsc}/assignments",
                               data={"assignment[name]": "GS Assignment",
                                     "assignment[points_possible]": "100",
                                     "assignment[published]": "true",
                                     "assignment[grading_type]": "letter_grade",
                                     "assignment[grading_standard_id]": gsid}))
            if gs_aid:
                _req("PUT", f"/api/v1/courses/{gsc}/assignments/{gs_aid}/submissions/{role_uid['student']}",
                     data={"submission[posted_grade]": "49.98"})
            dv_aid = _jid(_req("POST", f"/api/v1/courses/{gsc}/assignments",
                               data={"assignment[name]": "Derivation Assignment",
                                     "assignment[points_possible]": "100",
                                     "assignment[published]": "true",
                                     "assignment[grading_type]": "letter_grade",
                                     "assignment[grading_standard_id]": gsid}))
            if dv_aid:
                _req("PUT", f"/api/v1/courses/{gsc}/assignments/{dv_aid}/submissions/{role_uid['student']}",
                     data={"submission[posted_grade]": "86"})
            _bind(["gs_course_id", "deriv_course_id"], gsc)
            _bind(["gs_assignment_id"], gs_aid)
            _bind(["deriv_assignment_id"], dv_aid)
            _bind(["grading_standard_id", "gsid"], gsid)
        pp_aid = _jid(_req("POST", f"/api/v1/courses/{cid}/assignments",
                           data={"assignment[name]": "Post Policy Assignment",
                                 "assignment[points_possible]": "10",
                                 "assignment[published]": "true"}))
        if pp_aid:
            _req("POST", "/api/graphql",
                 json={"query": "mutation($a:ID!){ setAssignmentPostPolicy(input:{assignmentId:$a, postManually:true}){ postPolicy{ postManually } errors{ message } } }",
                       "variables": {"a": str(pp_aid)}})
            _bind(["post_policy_assignment_id"], pp_aid)
        bp = _jid(_req("POST", "/api/v1/accounts/1/courses",
                       data={"course[name]": "Seed Blueprint Master"}))
        if bp:
            _req("PUT", f"/api/v1/courses/{bp}", data={"course[event]": "offer"})
            _req("PUT", f"/api/v1/courses/{bp}", data={"course[blueprint]": "true"})
            _bind(["mcid", "master_course_id", "blueprint_course_id"], bp)
            bpc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                            data={"course[name]": "Seed Blueprint Child"}))
            if bpc:
                _req("PUT", f"/api/v1/courses/{bpc}", data={"course[event]": "offer"})
                _req("PUT", f"/api/v1/courses/{bp}/blueprint_templates/default/update_associations",
                     data={"course_ids_to_add[]": bpc})
                _bind(["blueprint_child_course_id", "child_course_id"], bpc)
        if cid:
            import base64 as _b64
            _bind(["course_relay_id"],
                  _b64.b64encode(f"Course-{cid}".encode()).decode())
        _bind(["del_topic_id"],
              _jid(_req("POST", f"/api/v1/courses/{cid}/discussion_topics",
                        data={"title": "Seed Delete Topic", "message": "seed"})))
        if context.get("topic_id"):
            _bind(["entry_id", "discussion_entry_id"],
                  _jid(_req("POST",
                            f"/api/v1/courses/{cid}/discussion_topics/{context['topic_id']}/entries",
                            data={"message": "seed entry"})))
        if context.get("aid") and role_uid.get("student"):
            sr = _req("GET",
                      f"/api/v1/courses/{cid}/assignments/{context['aid']}/submissions/{role_uid['student']}")
            _bind(["submission_id", "sub_id"], _jid(sr))
        _own_recips = [r for r in (role_uid.get("teacher"), role_uid.get("student")) if r] or [self_uid]
        cr = _req("POST", "/api/v1/conversations",
                  data={"recipients[]": _own_recips, "body": "seed"})
        conv_id = None
        if cr is not None:
            try:
                cd = cr.json()
                if isinstance(cd, list) and cd:
                    conv_id = cd[0].get("id") or (cd[0].get("conversation") or {}).get("id")
                elif isinstance(cd, dict):
                    conv_id = cd.get("id") or (cd.get("conversation") or {}).get("id")
            except Exception:
                pass
        _bind(["own_conversation_id", "conversation_id"], conv_id)
        if role_uid.get("student"):
            fcr = _req("POST", "/api/v1/conversations",
                       data={"recipients[]": [role_uid["student"]], "body": "foreign seed"})
            fconv = None
            if fcr is not None:
                try:
                    fd = fcr.json()
                    if isinstance(fd, list) and fd:
                        fconv = fd[0].get("id") or (fd[0].get("conversation") or {}).get("id")
                    elif isinstance(fd, dict):
                        fconv = fd.get("id") or (fd.get("conversation") or {}).get("id")
                except Exception:
                    pass
            _bind(["foreign_conversation_id", "private_conv_id"], fconv)
        teacher_tok = os.environ.get("HARNESS_TEACHER_TOKEN")
        if teacher_tok and role_uid.get("student"):
            try:
                tcr = requests.post(f"{base}/api/v1/conversations",
                                    headers={"Authorization": f"Bearer {teacher_tok}"},
                                    data={"recipients[]": [role_uid["student"]], "body": "teacher seed"},
                                    timeout=T)
                td = tcr.json()
                tconv = (td[0].get("id") if isinstance(td, list) and td
                         else td.get("id") if isinstance(td, dict) else None)
                _bind(["teacher_conversation_id"], tconv)
            except Exception as e:
                log.warning(f"seed teacher conversation failed: {e}")
        _bind(["folder_id", "fid"],
              _jid(_req("POST", f"/api/v1/courses/{cid}/folders",
                        data={"name": "Seed Folder"})))
        _req("POST", "/api/v1/calendar_events",
             data={"calendar_event[context_code]": f"course_{cid}",
                   "calendar_event[title]": "Seed Recurring Event",
                   "calendar_event[start_at]": "2026-08-01T10:00:00Z",
                   "calendar_event[end_at]": "2026-08-01T11:00:00Z",
                   "calendar_event[rrule]": "FREQ=WEEKLY;INTERVAL=1;COUNT=3"})
        _lf = _jid(_req("POST", f"/api/v1/courses/{cid}/folders",
                        data={"name": "Seed Locked Folder"}))
        if _lf:
            _req("PUT", f"/api/v1/folders/{_lf}", data={"locked": "true"})
            _bind(["locked_folder_id"], _lf)
        def _upload_file(name):
            try:
                r1 = _req("POST", f"/api/v1/courses/{cid}/files",
                          data={"name": name, "size": "5", "content_type": "text/plain"})
                d = r1.json() if r1 is not None else {}
                up = d.get("upload_url")
                if not up:
                    return None
                r2 = requests.post(up, data=d.get("upload_params", {}),
                                   files={"file": (name, b"hello", "text/plain")},
                                   allow_redirects=False, timeout=T)
                loc = r2.headers.get("Location")
                if not loc:
                    return None
                fr = requests.get(loc, headers=H, timeout=T)
                return fr.json() if fr.content else None
            except Exception as e:
                log.warning(f"seed file upload failed: {e}")
                return None
        _pub = _upload_file("seed_pub.txt")
        if isinstance(_pub, dict):
            _bind(["file_id", "attachment_id", "pub_file_id"], _pub.get("id"))
            try:
                import primitives as _prim
                _c = _prim.get_db_connection()
                if _c is not None and _pub.get("id"):
                    _local = int(_pub.get("id")) % 10_000_000_000_000
                    with _c.cursor() as _cur:
                        _cur.execute("SELECT uuid FROM attachments WHERE id=%s", (_local,))
                        _row = _cur.fetchone()
                        if _row and _row[0]:
                            _bind(["file_uuid", "file_verifier"], _row[0])
            except Exception as _e:
                log.warning(f"seed file uuid lookup failed: {_e}")
        _ufd = _upload_file("seed_hidden.txt")
        _uf = _ufd.get("id") if isinstance(_ufd, dict) else _ufd
        if _uf:
            _req("PUT", f"/api/v1/files/{_uf}",
                 data={"lock_at": "2020-01-01T00:00:00Z",
                       "unlock_at": "2035-01-01T00:00:00Z",
                       "hidden": "true"})
            _bind(["unpublished_file_id", "locked_file_id"], _uf)
        if role_uid.get("student"):
            import time as _t
            cc = _req("POST",
                      f"/api/v1/users/{role_uid['student']}/communication_channels",
                      data={"communication_channel[address]": f"seed_cc_{int(_t.time())}@test.com",
                            "communication_channel[type]": "email",
                            "skip_confirmation": "1"})
            cc_id = _jid(cc)
            if cc_id is None:
                lst = _req("GET",
                           f"/api/v1/users/{role_uid['student']}/communication_channels")
                try:
                    arr = lst.json() if lst is not None else []
                    if isinstance(arr, list) and arr:
                        cc_id = arr[0].get("id")
                except Exception:
                    pass
            _bind(["cc", "ccid", "communication_channel_id"], cc_id)
        _req("POST", f"/api/v1/courses/{cid}/pages",
             data={"wiki_page[title]": "Seed Home",
                   "wiki_page[body]": "home",
                   "wiki_page[published]": "true",
                   "wiki_page[front_page]": "true"})
        try:
            import primitives as _prim
            conn = _prim.get_db_connection()
            if conn is not None:
                with conn.cursor() as _cur:
                    _cur.execute("SELECT wiki_id FROM courses WHERE id=%s", (cid,))
                    row = _cur.fetchone()
                    if row and row[0]:
                        _bind(["wid", "wiki_id"], row[0])
        except Exception as e:
            log.warning(f"seed wid lookup failed: {e}")
        dc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                       data={"course[name]": "Seed Delete Course"}))
        if dc:
            _req("PUT", f"/api/v1/courses/{dc}", data={"course[event]": "offer"})
            _bind(["del_course_id", "throwaway_course_id"], dc)
            _bind(["aid_other", "foreign_assignment_id"],
                  _jid(_req("POST", f"/api/v1/courses/{dc}/assignments",
                            data={"assignment[name]": "Foreign Assignment",
                                  "assignment[submission_types][]": "online_text_entry",
                                  "assignment[points_possible]": "10",
                                  "assignment[published]": "true"})))
        emc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                        data={"course[name]": "Seed Enroll Mut Course"}))
        if emc:
            _req("PUT", f"/api/v1/courses/{emc}", data={"course[event]": "offer"})
            if role_uid.get("student"):
                _bind(["mut_enrollment_id"],
                      _jid(_req("POST", f"/api/v1/courses/{emc}/enrollments",
                                data={"enrollment[user_id]": role_uid["student"],
                                      "enrollment[type]": "StudentEnrollment",
                                      "enrollment[enrollment_state]": "active",
                                      "enrollment[start_at]": "2026-01-10T00:00:00Z",
                                      "enrollment[end_at]": "2026-05-01T00:00:00Z"})))
            if role_uid.get("observer"):
                _bind(["del_enrollment_id"],
                      _jid(_req("POST", f"/api/v1/courses/{emc}/enrollments",
                                data={"enrollment[user_id]": role_uid["observer"],
                                      "enrollment[type]": "StudentEnrollment",
                                      "enrollment[enrollment_state]": "active"})))
            _bind(["mut_course_id"], emc)
        _bind(["del_section_id", "throwaway_section_id"],
              _jid(_req("POST", f"/api/v1/courses/{cid}/sections",
                        data={"course_section[name]": "Seed Delete Section"})))
        if role_uid.get("observer"):
            ce = _req("POST", f"/api/v1/courses/{cid}/enrollments",
                      data={"enrollment[user_id]": role_uid["observer"],
                            "enrollment[type]": "ObserverEnrollment",
                            "enrollment[enrollment_state]": "active"})
            _bind(["complete_enrollment_id", "throwaway_enrollment_id"], _jid(ce))
        if context.get("qid"):
            _req("PUT", f"/api/v1/courses/{cid}/quizzes/{context['qid']}",
                 data={"quiz[published]": "true"})
            qs = _sreq("POST",
                       f"/api/v1/courses/{cid}/quizzes/{context['qid']}/submissions")
            if qs is not None:
                try:
                    qsd = qs.json().get("quiz_submissions", [])
                    if qsd:
                        _qsid = qsd[0].get("id")
                        _att = qsd[0].get("attempt")
                        _vt = qsd[0].get("validation_token")
                        _bind(["qsid", "quiz_submission_id"], _qsid)
                        if _qsid and _att is not None and _vt:
                            _sreq("POST",
                                  f"/api/v1/courses/{cid}/quizzes/{context['qid']}/submissions/{_qsid}/complete",
                                  data={"attempt": _att, "validation_token": _vt})
                            _req("PUT",
                                 f"/api/v1/courses/{cid}/quizzes/{context['qid']}/submissions/{_qsid}",
                                 json={"quiz_submissions": [{"attempt": _att, "fudge_points": 10}]})
                except Exception:
                    pass
        try:
            import datetime as _dt3
            _lock = (_dt3.datetime.utcnow() + _dt3.timedelta(minutes=59)).strftime("%Y-%m-%dT%H:%M:%SZ")
            _tqc = _jid(_req("POST", "/api/v1/accounts/1/courses",
                             data={"course[name]": "Timed Quiz Course"}))
            if _tqc and role_uid.get("student"):
                _req("PUT", f"/api/v1/courses/{_tqc}", data={"course[event]": "offer"})
                _req("POST", f"/api/v1/courses/{_tqc}/enrollments",
                     data={"enrollment[user_id]": role_uid["student"],
                           "enrollment[type]": "StudentEnrollment",
                           "enrollment[enrollment_state]": "active"})
                _sa = _jid(_req("POST", f"/api/v1/courses/{_tqc}/assignments",
                                json={"assignment": {"name": "Sub Cycle A",
                                                     "points_possible": 10,
                                                     "submission_types": ["online_text_entry"],
                                                     "published": True}}))
                if _sa:
                    _req("PUT", f"/api/v1/courses/{_tqc}/assignments/{_sa}/submissions/{role_uid['student']}",
                         json={"submission": {"posted_grade": "8"}})
                    _bind(["sub_course_id"], _tqc)
                    _bind(["sub_assignment_id"], _sa)
                    _bind(["sub_user_id"], role_uid["student"])
                _tq = _jid(_req("POST", f"/api/v1/courses/{_tqc}/quizzes",
                                json={"quiz": {"title": "Timed Quiz", "quiz_type": "assignment",
                                               "time_limit": 60, "lock_at": _lock,
                                               "published": True}}))
                if _tq:
                    _req("POST", f"/api/v1/courses/{_tqc}/quizzes/{_tq}/questions",
                         json={"question": {"question_name": "TQ1",
                                            "question_type": "multiple_choice_question",
                                            "question_text": "2+2?", "points_possible": 10,
                                            "answers": [{"answer_text": "4", "answer_weight": 100}]}})
                    _req("PUT", f"/api/v1/courses/{_tqc}/quizzes/{_tq}",
                         data={"quiz[published]": "true"})
                    _tsub = _sreq("POST", f"/api/v1/courses/{_tqc}/quizzes/{_tq}/submissions")
                    _bind(["tq_course_id"], _tqc)
                    _bind(["tq_quiz_id"], _tq)
                    if _tsub is not None:
                        try:
                            _tsd = _tsub.json().get("quiz_submissions", [])
                            if _tsd:
                                _bind(["tq_submission_id"], _tsd[0].get("id"))
                        except Exception:
                            pass
        except Exception as _e:
            log.warning(f"seed timed-quiz failed: {_e}")
    # --- LTI 1.3 Advantage deployment (NRPS + AGS) ----------------------
    try:
        _cid = context.get("cid")
        if _cid:
            _ruby_lti = (
                "acct=Account.default; c=Course.find(" + str(_cid) + "); "
                "scopes=['https://purl.imsglobal.org/spec/lti-ags/scope/lineitem',"
                "'https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly',"
                "'https://purl.imsglobal.org/spec/lti-ags/scope/score',"
                "'https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly',"
                "'https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly']; "
                "dk=DeveloperKey.where(name:'Eval LTI Advantage').first || DeveloperKey.create!(name:'Eval LTI Advantage', account:acct); "
                "dk.update_columns(scopes:scopes, require_scopes:true, client_credentials_audience:'external', workflow_state:'active'); "
                "b=dk.developer_key_account_bindings.where(account_id:acct.id).first_or_initialize; b.workflow_state='on'; b.save!; "
                "t=ContextExternalTool.where(context_type:'Course', context_id:c.id, name:'Eval LTI Adv Tool').first; "
                "if t.nil?; t=c.context_external_tools.new(name:'Eval LTI Adv Tool', consumer_key:'N/A', shared_secret:'N/A', url:'https://tool.test/launch', privacy_level:'public'); t.developer_key=dk; t.lti_version='1.3'; t.save!; end; "
                "reg=dk.lti_registration || Lti::Registration.create!(account:acct, name:'Eval LTI Adv Reg', admin_nickname:'evallti', developer_key:dk); "
                "t.update_columns(lti_registration_id:reg.id) if t.lti_registration_id!=reg.id; "
                "rid=acct.resolved_root_account_id; rid=acct.id if rid.nil?||rid==0; "
                "cc=Lti::ContextControl.where(deployment_id:t.id, course_id:c.id).first_or_initialize; "
                "cc.registration_id=reg.id; cc.available=true; cc.path='a'+acct.id.to_s+'.c'+c.id.to_s+'.'; cc.root_account_id=rid; cc.workflow_state='active'; cc.save!; "
                "iso=User.where(name:'Eval Iso Student').first; "
                "if iso.nil?; iso=User.create!(name:'Eval Iso Student'); "
                "iso.pseudonyms.create!(account:acct, unique_id:'eval_iso_student@example.edu'); end; "
                "en=c.enrollments.where(user_id:iso.id, type:'StudentEnrollment').first; "
                "en=c.enroll_user(iso,'StudentEnrollment', enrollment_state:'active') if en.nil?; "
                "en.update!(workflow_state:'active') unless en.workflow_state=='active'; "
                "puts 'ISO_STUDENT id='+iso.id.to_s+' lti='+iso.lti_id.to_s; "
                "puts 'LTI_SEED dk='+dk.global_id.to_s+' secret='+dk.api_key.to_s"
            )
            _lout = utils.docker_exec(
                config.APP_CONTAINER,
                "cd /usr/src/app && bin/rails runner \"" + _ruby_lti + "\"",
                timeout=120)
            import re as _reL
            _mIso = _reL.search(r"ISO_STUDENT id=(\d+) lti=(\S+)", (_lout.stdout or ""))
            if _mIso:
                _bind(["iso_student_id"], int(_mIso.group(1)))
                _bind(["lti_student_sub"], _mIso.group(2))
            _mL = _reL.search(r"LTI_SEED dk=(\S+) secret=(\S+)", (_lout.stdout or ""))
            if _mL:
                _dkid, _secret = _mL.group(1), _mL.group(2)
                _tok_url = f"{base}/login/oauth2/token"
                _full_scope = ("https://purl.imsglobal.org/spec/lti-ags/scope/lineitem "
                               "https://purl.imsglobal.org/spec/lti-ags/scope/score "
                               "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly")
                _lim_scope = ("https://purl.imsglobal.org/spec/lti-ags/scope/lineitem "
                              "https://purl.imsglobal.org/spec/lti-ags/scope/score")

                def _mint(scope):
                    try:
                        rr = requests.post(_tok_url,
                                           data={"grant_type": "client_credentials",
                                                 "client_id": _dkid, "client_secret": _secret,
                                                 "scope": scope}, timeout=T)
                        return rr.json().get("access_token") if rr.status_code == 200 else None
                    except Exception:
                        return None

                _tool_tok = _mint(_full_scope)
                _lim_tok = _mint(_lim_scope)
                if _tool_tok:
                    _bind(["tool_token", "auth_token_tool"], _tool_tok)
                    _bind(["lti_course_id"], _cid)
                    try:
                        _li = requests.post(
                            f"{base}/api/lti/courses/{_cid}/line_items",
                            headers={"Authorization": f"Bearer {_tool_tok}",
                                     "Content-Type": "application/vnd.ims.lis.v2.lineitem+json"},
                            json={"scoreMaximum": 100, "label": "Eval AGS LI"}, timeout=T)
                        if _li.status_code in (200, 201):
                            _lid = str(_li.json().get("id", "")).rstrip("/").split("/")[-1]
                            if _lid.isdigit():
                                _bind(["lti_line_item_id"], int(_lid))
                    except Exception:
                        pass
                    try:
                        _nr = requests.get(
                            f"{base}/api/lti/courses/{_cid}/names_and_roles",
                            headers={"Authorization": f"Bearer {_tool_tok}",
                                     "Accept": "application/vnd.ims.lti-nrps.v2.membershipcontainer+json"},
                            timeout=T)
                        _members = _nr.json().get("members", []) if _nr.status_code == 200 else []
                        if not context.get("lti_student_sub"):
                            for _m in _members:
                                if any("Learner" in str(_r) for _r in _m.get("roles", [])):
                                    _bind(["lti_student_sub"], _m.get("user_id"))
                                    break
                    except Exception:
                        pass
                if _lim_tok:
                    _bind(["limited_token"], _lim_tok)
            log.info(f"seed LTI: course={context.get('lti_course_id')} "
                     f"tool_token={'set' if context.get('tool_token') else 'MISSING'} "
                     f"line_item={context.get('lti_line_item_id')} "
                     f"sub={context.get('lti_student_sub')} "
                     f"limited={'set' if context.get('limited_token') else 'MISSING'}")
    except Exception as _e:
        log.warning(f"seed LTI Advantage failed: {_e}")

    # --- Outcome rollup (aggregate_score average round(2)) --------------
    try:
        _cid = context.get("cid")
        if _cid:
            _ruby_ro = (
                "c=Course.find(" + str(_cid) + "); "
                "stu=c.student_enrollments.where(workflow_state:'active').first.user; "
                "LearningOutcome.where(context:c, short_description:'Eval Rollup Outcome').each{|x| LearningOutcomeResult.where(learning_outcome:x).delete_all; OutcomeRollup.where(outcome_id:x.id).delete_all}; "
                "o=LearningOutcome.create!(context:c, short_description:'Eval Rollup Outcome', calculation_method:'average'); "
                "c.root_outcome_group.add_outcome(o); "
                "[2.0,3.0,3.0].each_with_index{|s,i| a=c.assignments.create!(title:'Eval Rollup Asg '+i.to_s, points_possible:5); tag=o.align(a,c); LearningOutcomeResult.create!(learning_outcome:o, user:stu, context:c, alignment:tag, association_type:'Assignment', association_id:a.id, score:s, possible:5.0, mastery:(s>=3), context_code:c.asset_string, title:stu.name+', Eval Rollup Asg '+i.to_s, created_at:Time.now, submitted_at:Time.now+i)}; "
                "Outcomes::StudentOutcomeRollupCalculationService.new(course_id:c.id, student_id:stu.id).call; "
                "r=OutcomeRollup.where(course_id:c.id, user_id:stu.id, outcome_id:o.id, workflow_state:'active').first; "
                "puts 'ROLLUP_SEED rid='+(r ? r.id.to_s : 'nil')+' agg='+(r ? r.aggregate_score.to_s : 'nil')"
            )
            _rout = utils.docker_exec(
                config.APP_CONTAINER,
                "cd /usr/src/app && bin/rails runner \"" + _ruby_ro + "\"",
                timeout=120)
            import re as _reR
            _mR = _reR.search(r"ROLLUP_SEED rid=(\d+) agg=(\S+)", (_rout.stdout or ""))
            if _mR:
                _bind(["outcome_rollup_id"], int(_mR.group(1)))
                log.info(f"seed outcome_rollup: id={_mR.group(1)} agg={_mR.group(2)}")
    except Exception as _e:
        log.warning(f"seed outcome rollup failed: {_e}")

    # --- Moderated grading workflow fixture -----------------------------
    try:
        _cid = context.get("cid")
        if _cid:
            _ruby_mw = (
                "c=Course.find(" + str(_cid) + "); "
                "teacher=c.teacher_enrollments.where(workflow_state:'active').first.user; "
                "ta=c.ta_enrollments.where(workflow_state:'active').first.user; "
                "iso=User.where(name:'Eval Iso Student').first; "
                "iso_en=iso && c.enrollments.where(user_id:iso.id, type:'StudentEnrollment').first; "
                "iso_en.update!(workflow_state:'active') if iso_en && iso_en.workflow_state!='active'; "
                "stu=(iso && iso_en) ? iso : c.student_enrollments.where(workflow_state:'active').first.user; "
                "a=c.assignments.where(title:'Eval Moderated WF').order(:id).last; "
                "if a.nil?; a=c.assignments.create!(title:'Eval Moderated WF', points_possible:10, submission_types:'online_text_entry', moderated_grading:true, grader_count:2, final_grader:teacher, workflow_state:'published'); end; "
                "sub=a.submit_homework(stu, submission_type:'online_text_entry', body:'work'); "
                "pg_ta=sub.find_or_create_provisional_grade!(ta, score:8); "
                "sub.find_or_create_provisional_grade!(teacher, score:9); "
                "puts 'MODWF_SEED aid='+a.id.to_s+' sid='+sub.id.to_s+' stu='+stu.id.to_s+' pgta='+pg_ta.id.to_s"
            )
            _mwout = utils.docker_exec(
                config.APP_CONTAINER,
                "cd /usr/src/app && bin/rails runner \"" + _ruby_mw + "\"",
                timeout=120)
            import re as _reM
            _mM = _reM.search(r"MODWF_SEED aid=(\d+) sid=(\d+) stu=(\d+) pgta=(\d+)", (_mwout.stdout or ""))
            if _mM:
                _bind(["mod_aid"], int(_mM.group(1)))
                _bind(["mod_sub_id"], int(_mM.group(2)))
                _bind(["mod_stu_id"], int(_mM.group(3)))
                _bind(["mod_pg_ta_id"], int(_mM.group(4)))
                log.info(f"seed moderated-wf: aid={_mM.group(1)} sub={_mM.group(2)} "
                         f"stu={_mM.group(3)} pg_ta={_mM.group(4)}")
    except Exception as _e:
        log.warning(f"seed moderated workflow failed: {_e}")

    log.info(f"seed bound: cid={context.get('cid')} aid={context.get('aid')} "
             f"mid={context.get('mid')} topic={context.get('topic_id')} "
             f"qid={context.get('qid')} sid={context.get('sid')} "
             f"uid={context.get('uid')} eid={context.get('eid')}")


# =============================================================================
# =============================================================================
def execute_chain(chain: list[dict], context: dict,
                   store: utils.ArtifactStore,
                   node_id: str = "") -> tuple[list[utils.StepResult], dict]:
    step_results: list[utils.StepResult] = []
    last_output = None
    for k in [k for k in list(context.keys()) if k.startswith("from_P")]:
        context.pop(k, None)
    context.pop("last_response", None)
    snap = context.get("__seed_snapshot__")
    if snap:
        context.update(snap)
    for step in chain:
        ptype = step.get("type")
        raw_inputs = step.get("inputs", {})
        if ptype == "P29":
            resolved = raw_inputs
        else:
            resolved = utils.substitute(raw_inputs, context)
        with utils.Timer() as t:
            result = primitives.dispatch(ptype, resolved, context, store)
        step_result = utils.StepResult(
            primitive=ptype, inputs=resolved,
            output=result.get("output"),
            passed=bool(result.get("passed", False)),
            elapsed_ms=t.elapsed_ms,
            error=result.get("error"),
        )
        step_results.append(step_result)
        last_output = result.get("output")
        for ev_key, ev_val in (result.get("evidence") or {}).items():
            store.store(ev_key, ev_val)
        context[f"from_{ptype}"] = result.get("output")
        context["last_response"] = result.get("output")
        if isinstance(last_output, dict) and "body" in last_output:
            body = last_output["body"]
            if isinstance(body, dict):
                if "id" in body and body["id"] is not None:
                    context["id"] = body["id"]
                if node_id:
                    extract_entity_ids(node_id, body, context)
    return step_results, last_output


# =============================================================================
# =============================================================================
def score_node(node: dict, chain_results: list[utils.StepResult]) -> tuple[float, str]:
    method = node.get("scoring", {}).get("method", "binary")
    max_score = float(node.get("scoring", {}).get("maxScore", 0))
    if not chain_results:
        return 0.0, "ERROR"
    if method == "binary":
        all_pass = all(s.passed for s in chain_results)
        return (max_score if all_pass else 0.0,
                "PASSED" if all_pass else "FAILED")
    if method == "weighted":
        n_pass = sum(1 for s in chain_results if s.passed)
        ratio = n_pass / len(chain_results)
        score = round(ratio * max_score, 3)
        if ratio == 1.0:
            return score, "PASSED"
        if ratio >= config.PARTIAL_PASS_RATIO:
            return score, "PARTIAL"
        if ratio > 0:
            return score, "PARTIAL"
        return 0.0, "FAILED"
    if method == "llm-judge":
        for s in chain_results:
            if s.primitive == "P17" and isinstance(s.output, dict):
                if s.output.get("skipped"):
                    return 0.0, "SKIPPED_LLM"
                judged = s.output.get("score", 0)
                judged_max = s.output.get("max", 5)
                ratio = judged / max(judged_max, 1)
                score = round(ratio * max_score, 3)
                if ratio >= config.LLM_JUDGE_PASS_RATIO:
                    return score, "PASSED"
                if ratio > 0:
                    return score, "PARTIAL"
                return 0.0, "FAILED"
        return 0.0, "ERROR"
    return 0.0, "ERROR"


# =============================================================================
# =============================================================================
def execute_dag(filter_categories: set[str] | None = None,
                 only_node_ids: set[str] | None = None,
                 stop_on_first_failure: bool = False,
                 with_llm: bool = True,
                 dry_run: bool = False) -> dict:
    dag = utils.load_dag()
    nodes_by_id = {n["id"]: n for n in dag["nodes"]}
    sorted_ids = utils.topological_sort(dag["nodes"])
    log.info(f"Topo sorted {len(sorted_ids)} nodes")

    store = utils.ArtifactStore()
    context: dict[str, Any] = {}
    _inject_test_user_placeholders(context)
    _bind_infra(context)
    if not dry_run:
        _seed_entities(context)
    _SNAP_SKIP = ("auth_token", "from_", "last_response")
    context["__seed_snapshot__"] = {
        k: v for k, v in context.items()
        if not any(k.startswith(p) for p in _SNAP_SKIP)
        and k not in ("admin_token", "__seed_snapshot__")
    }
    results: dict[str, utils.NodeResult] = {}

    t_start = time.time()
    for nid in sorted_ids:
        node = nodes_by_id[nid]
        if only_node_ids and nid not in only_node_ids:
            continue
        if filter_categories and node["scoring"]["category"] not in filter_categories:
            continue

        if not with_llm and node["scoring"].get("method") == "llm-judge":
            results[nid] = utils.NodeResult(
                node_id=nid, status="SKIPPED_LLM_DISABLED", score=0,
                max_score=float(node["scoring"].get("maxScore", 0)),
                message="llm-judge skipped (--no-llm flag set)",
            )
            continue

        if dry_run:
            results[nid] = utils.NodeResult(
                node_id=nid, status="DRY_RUN", score=0,
                max_score=float(node["scoring"].get("maxScore", 0)),
                message=f"would execute {len(node['primitive_chain'])} primitives",
            )
            log.info(f"  [DRY] {nid}: {[p['type'] for p in node['primitive_chain']]}")
            continue

        if not utils.all_prereqs_passed(node.get("prereqs", []), results):
            results[nid] = utils.NodeResult(
                node_id=nid, status="SKIPPED_DEPENDENCY", score=0,
                max_score=float(node["scoring"].get("maxScore", 0)),
                message=f"prereq failed: {node.get('prereqs', [])}",
            )
            continue

        store.push_context(nid)
        node_t0 = time.perf_counter()
        try:
            chain_results, _ = execute_chain(node["primitive_chain"], context, store, nid)
            score_val, status = score_node(node, chain_results)
            elapsed = (time.perf_counter() - node_t0) * 1000
            nr = utils.NodeResult(
                node_id=nid, status=status, score=score_val,
                max_score=float(node["scoring"].get("maxScore", 0)),
                chain_results=chain_results,
                evidence=dict(store.evidence.get(nid, {})),
                elapsed_ms=elapsed,
                message=f"{sum(1 for s in chain_results if s.passed)}/{len(chain_results)} steps passed",
            )
        except Exception as e:
            log.exception(f"node {nid} crashed")
            nr = utils.NodeResult(
                node_id=nid, status="ERROR", score=0,
                max_score=float(node["scoring"].get("maxScore", 0)),
                message=f"crash: {e}",
            )
        finally:
            store.pop_context()
        results[nid] = nr
        log.info(f"  {nid}: {nr.status} ({nr.score}/{nr.max_score})")
        if stop_on_first_failure and nr.status in ("FAILED", "ERROR"):
            log.warning(f"stop_on_first_failure triggered at {nid}")
            break

    return aggregate(results, dag, time.time() - t_start)


# =============================================================================
# =============================================================================
def aggregate(results: dict[str, utils.NodeResult], dag: dict, elapsed_s: float) -> dict:
    score_cfg_path = config.SCORING_CONFIG_FILE
    try:
        score_cfg = json.loads(score_cfg_path.read_text())
    except Exception:
        score_cfg = {"trajectories": {}}

    nodes_by_id = {n["id"]: n for n in dag["nodes"]}
    by_cat = defaultdict(lambda: {"score": 0.0, "max_score": 0.0, "node_count": 0,
                                    "passed": 0, "failed": 0, "skipped": 0, "partial": 0, "error": 0})
    by_complexity = defaultdict(lambda: {"score": 0.0, "max_score": 0.0, "count": 0})
    total_score = 0.0
    total_max = 0.0
    skipped_llm_max = 0.0

    SKIP_FROM_TOTAL = {"SKIPPED_LLM", "SKIPPED_LLM_DISABLED"}

    for nid, r in results.items():
        node = nodes_by_id[nid]
        cat = node["scoring"]["category"]
        if r.status in SKIP_FROM_TOTAL:
            skipped_llm_max += r.max_score
            by_cat[cat]["node_count"] += 1
            by_cat[cat]["skipped"] += 1
            continue
        by_cat[cat]["score"] += r.score
        by_cat[cat]["max_score"] += r.max_score
        by_cat[cat]["node_count"] += 1
        by_cat[cat][r.status.lower() if r.status in ("PASSED", "FAILED", "PARTIAL", "ERROR")
                     else "skipped"] += 1
        ctier = node.get("complexity_tier", "unknown")
        by_complexity[ctier]["score"] += r.score
        by_complexity[ctier]["max_score"] += r.max_score
        by_complexity[ctier]["count"] += 1
        total_score += r.score
        total_max += r.max_score

    trajectories = {}
    for tname, tspec in (score_cfg.get("trajectories") or {}).items():
        ids = tspec.get("node_ids", [])
        ts = sum(results[i].score for i in ids
                 if i in results and results[i].status not in SKIP_FROM_TOTAL)
        tm = sum(results[i].max_score for i in ids
                 if i in results and results[i].status not in SKIP_FROM_TOTAL)
        trajectories[tname] = {
            "score": round(ts, 3),
            "max_score": round(tm, 3),
            "ratio": round(ts / tm, 3) if tm else 0.0,
            "node_count": len(ids),
        }

    return {
        "meta": {
            "task_id": "task_gavmyneb",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_s": round(elapsed_s, 1),
            "harness_version": "1.0",
            "node_count": len(results),
        },
        "total_score": round(total_score, 3),
        "max_total_score": round(total_max, 3),
        "percentage": round(total_score / total_max * 100, 2) if total_max else 0.0,
        "llm_judge_skipped_maxScore": round(skipped_llm_max, 3),
        "categories": [
            {"category": cat, **{k: round(v, 3) if isinstance(v, float) else v for k, v in stats.items()}}
            for cat, stats in sorted(by_cat.items(), key=lambda kv: -kv[1]["max_score"])
        ],
        "complexity_tiers": {
            tier: {**{k: round(v, 3) if isinstance(v, float) else v for k, v in stats.items()},
                   "ratio": round(stats["score"] / stats["max_score"], 3) if stats["max_score"] else 0.0}
            for tier, stats in by_complexity.items()
        },
        "trajectories": trajectories,
        "node_results": [r.to_dict() for r in results.values()],
        "summary_counts": {
            "PASSED": sum(1 for r in results.values() if r.status == "PASSED"),
            "PARTIAL": sum(1 for r in results.values() if r.status == "PARTIAL"),
            "FAILED": sum(1 for r in results.values() if r.status == "FAILED"),
            "SKIPPED_DEPENDENCY": sum(1 for r in results.values() if r.status == "SKIPPED_DEPENDENCY"),
            "SKIPPED_LLM_DISABLED": sum(1 for r in results.values() if r.status == "SKIPPED_LLM_DISABLED"),
            "SKIPPED_LLM": sum(1 for r in results.values() if r.status == "SKIPPED_LLM"),
            "DRY_RUN": sum(1 for r in results.values() if r.status == "DRY_RUN"),
            "ERROR": sum(1 for r in results.values() if r.status == "ERROR"),
        },
    }
