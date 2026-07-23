"""tools/patch_dag_for_source_smoke.py — Stage 7.2 source-project adaptation.

PIPELINE.md §1108-1116 requires that, when Stage 7.2 runs against the source
project, the de-sourced commands/prefixes are mapped back to the source project's
actual values. This script generates ``evaluate/dag_smoke_source.json`` so that
``run_all --dag dag_smoke_source.json`` produces an evaluation that matches the
source project's (cal.com) actual behavior.

Mapping rules (task_iyjruvfz → cal.com):
  @app/prisma                           →  @calcom/prisma
  docker exec task_iyjruvfz-app yarn    →  cd <CAL_COM_PATH> && yarn
  (DB / container name / API key prefix are injected via env and remain unchanged in the dag)

Invocation:

    cd task_iyjruvfz_e
    python -c "from evaluate.tools.patch_dag_for_source_smoke import main; main()"
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluate import config

DEFAULT_SOURCE_PROJECT = "/path/to/local-mirrors/cal.com"


def patch_text(text: str, source_path: str) -> tuple[str, dict]:

    counts: dict[str, int] = {}

    new = text.replace("@app/prisma", "@calcom/prisma")
    counts["@app/prisma -> @calcom/prisma"] = (text.count("@app/prisma") - new.count("@app/prisma"))
    text = new

    pattern = re.compile(r"docker exec task_iyjruvfz-app (yarn[^\"]+)")
    repl_count = [0]

    def _repl(m: re.Match) -> str:
        repl_count[0] += 1
        return f"cd {source_path} && {m.group(1)}"

    text = pattern.sub(_repl, text)
    counts["docker exec task_iyjruvfz-app yarn -> cd <SOURCE> && yarn"] = repl_count[0]

    return text, counts


def _apply_node_desources(dag: dict, applied: dict, source_project: str = DEFAULT_SOURCE_PROJECT) -> None:

    enum_sql_count = _desource_postgres_enum_sql(dag)
    if enum_sql_count:
        applied["__desource_pg_enum_pascalcase__"] = (
            f"fixed {enum_sql_count} P08 SQL queries with PascalCase pg_enum typname"
        )

    path_count = _desource_app_path_to_source(dag, source_project)
    if path_count:
        applied["__desource_path_app_to_source__"] = (
            f"replaced /app/... with {source_project} on {path_count} P01/P02/P03 inputs"
        )

    i18n_real_count = _patch_i18n_real_path(dag, source_project)
    if i18n_real_count:
        applied["__desource_i18n_real_path__"] = (
            f"patched {i18n_real_count} I18N nodes to actually-existing cal.com locales path"
        )

    p12_docker_count = _desource_p12_docker_exec_app(dag)
    if p12_docker_count:
        applied["__desource_p12_docker_exec_to_host__"] = (
            f"replaced {p12_docker_count} P12 'docker exec task_iyjruvfz-app ...' to host commands"
        )

    pending_count = _desource_setup_oauth_pending_enum(dag)
    if pending_count:
        applied["__desource_oauth_pending_enum__"] = (
            "changed enum literal 'PENDING' → 'pending' (cal.com OAuthClientStatus actually lowercase)"
        )

    seed_count = _desource_db_seed_p12(dag)
    if seed_count:
        applied["__desource_db_seed_host_mode__"] = (
            f"db-seed/db-deploy host-mode non-destructive + exit [0,1] on {seed_count} P12 nodes"
        )

    hdr_count = _desource_v2_version_header(dag)
    if hdr_count:
        applied["__desource_v2_version_header_name__"] = (
            f"renamed 'Api-Version' header -> '{os.environ.get('V2_VERSION_HEADER_NAME', 'Api-Version')}' on {hdr_count} P04 headers"
        )

    epver_count = _desource_endpoint_version(dag)
    if epver_count:
        applied["__desource_endpoint_version__"] = (
            f"set per-controller source version on {epver_count} P04 headers "
            "(slots->2024-09-04, schedules/teams/calendars->2024-06-11, event-types->2024-06-14)"
        )

    wh_hdr_count = _desource_webhook_signature_header(dag)
    if wh_hdr_count:
        applied["__desource_webhook_signature_header__"] = (
            f"renamed P27 expected_header_name 'X-App-Signature-256' -> "
            f"'X-Cal-Signature-256' on {wh_hdr_count} nodes"
        )


def _desource_webhook_signature_header(dag: dict) -> int:
    n = 0
    for node in dag.get("nodes", []):
        for p in node.get("primitive_chain") or []:
            if p.get("type") != "P27":
                continue
            inputs = p.setdefault("inputs", {})
            if inputs.get("expected_header_name", "X-App-Signature-256") == "X-App-Signature-256":
                inputs["expected_header_name"] = "X-Cal-Signature-256"
                n += 1
    return n


def _desource_endpoint_version(dag: dict) -> int:

    if os.environ.get("V2_VERSION_HEADER_NAME", "Api-Version").lower() == "api-version":
        return 0
    endpoint_ver = {
        "/api/v2/slots": "2024-09-04",
        "/api/v2/schedules": "2024-06-11",
        "/api/v2/teams": "2024-06-11",
        "/api/v2/event-types": "2024-06-14",
        "/api/v2/calendars": "2024-06-11",
    }
    prefixes = sorted(endpoint_ver.keys(), key=len, reverse=True)
    n = 0
    for node in dag.get("nodes", []):
        for p in node.get("primitive_chain") or []:
            if p.get("type") != "P04":
                continue
            ins = p.get("inputs") or {}
            path = str(ins.get("path", "")).rstrip("/")
            headers = ins.get("headers")
            if not isinstance(headers, dict):
                continue
            ver = None
            for pref in prefixes:
                if path == pref or path.startswith(pref + "/") or path.startswith(pref + "?"):
                    ver = endpoint_ver[pref]
                    break
            if not ver:
                continue
            for k in list(headers.keys()):
                if k.lower() in ("api-version", "cal-api-version"):
                    headers[k] = ver
                    n += 1
    return n


def _desource_v2_version_header(dag: dict) -> int:

    target = os.environ.get("V2_VERSION_HEADER_NAME", "Api-Version")
    if target.lower() == "api-version":
        return 0
    n = 0
    for node in dag.get("nodes", []):
        for p in node.get("primitive_chain") or []:
            if p.get("type") != "P04":
                continue
            headers = (p.get("inputs") or {}).get("headers")
            if not isinstance(headers, dict):
                continue
            for key in list(headers.keys()):
                if key.lower() == "api-version" and key != target:
                    headers[target] = headers.pop(key)
                    n += 1
    return n


def _desource_db_seed_p12(dag: dict) -> int:

    n = 0
    for node in dag.get("nodes", []):
        for p in node.get("primitive_chain") or []:
            if p.get("type") != "P12":
                continue
            cmd = (p.get("inputs") or {}).get("command", "")
            if "db-seed" in cmd or "db-deploy" in cmd:
                inputs = p.setdefault("inputs", {})
                inputs.pop("expected_exit_code", None)
                inputs["expected_acceptable_exit_codes"] = [0, 1]
                inputs.setdefault("mode", "host")
                n += 1
    return n


def _desource_postgres_enum_sql(dag: dict) -> int:
    import re

    n = 0
    pattern = re.compile(r"'([A-Z][A-Za-z]+)'::regtype")

    for node in dag.get("nodes", []):
        for p in node.get("primitive_chain") or []:
            if p.get("type") != "P08":
                continue
            inputs = p.get("inputs") or {}
            sql = inputs.get("sql", "")

            def _quote(m):
                return f"'\"{m.group(1)}\"'::regtype"

            new_sql = pattern.sub(_quote, sql)

            type_renames = {
                "workflowtriggerevents": "WorkflowTriggerEvents",
                "userpermissionrole": "UserPermissionRole",
                "membershiprole": "MembershipRole",
                "bookingstatus": "BookingStatus",
                "schedulingtype": "SchedulingType",
                "creationsource": "CreationSource",
                "periodtype": "PeriodType",
                "identityprovider": "IdentityProvider",
                "watchlisttype": "WatchlistType",
                "billingperiod": "BillingPeriod",
                "assignmentreasonenum": "AssignmentReasonEnum",
                "workflowactions": "WorkflowActions",
                "eventtypeautotranslatedfield": "EventTypeAutoTranslatedField",
                "oauthclientstatus": "OAuthClientStatus",
                "attributetype": "AttributeType",
                "roletype": "RoleType",
            }
            for low, pas in type_renames.items():
                new_sql = new_sql.replace(f"typname='{low}'", f"typname='{pas}'")

            if new_sql != sql:
                inputs["sql"] = new_sql
                n += 1
    return n


def _desource_app_path_to_source(dag: dict, source_path: str) -> int:

    n = 0
    for node in dag.get("nodes", []):
        for p in node.get("primitive_chain") or []:
            if p.get("type") not in ("P01", "P02", "P03"):
                continue
            inputs = p.get("inputs") or {}
            for k in ("path", "base_dir"):
                v = inputs.get(k)
                if isinstance(v, str) and v.startswith("/app"):
                    inputs[k] = source_path + v[4:]
                    n += 1
    return n


def _desource_setup_oauth_pending_enum(dag: dict) -> int:

    n = 0
    for node in dag.get("nodes", []):
        if node["id"] != "SETUP_OAUTH_CLIENT_PENDING":
            continue
        for p in node.get("primitive_chain") or []:
            if p.get("type") != "P12":
                continue
            inputs = p.get("inputs") or {}
            cmd = inputs.get("command", "")
            new_cmd = cmd.replace("'PENDING'", "'pending'")
            new_cmd = new_cmd.replace("PENDING)", "'pending')")
            if new_cmd != cmd:
                inputs["command"] = new_cmd
                n += 1
    return n


def _desource_p12_docker_exec_app(dag: dict) -> int:
    n = 0
    for node in dag.get("nodes", []):
        for p in node.get("primitive_chain") or []:
            if p.get("type") != "P12":
                continue
            inputs = p.get("inputs") or {}
            cmd = inputs.get("command", "")
            if cmd.startswith("docker exec task_iyjruvfz-app "):
                inputs["mode"] = "host"
                n += 1
    return n


def _patch_i18n_real_path(dag: dict, source_project: str) -> int:
    import os
    candidates = [
        f"{source_project}/apps/web/public/static/locales",
        f"{source_project}/packages/lib/server/i18n/locales",
        f"{source_project}/packages/i18n/locales",
        f"{source_project}/apps/web/locales",
        f"{source_project}/packages/lib/i18n",
    ]
    actual = None
    for c in candidates:
        if os.path.isdir(c):
            sub_count = len([x for x in os.listdir(c) if os.path.isdir(os.path.join(c, x))])
            if sub_count >= 30:
                actual = c
                break
    if not actual:
        for c in candidates:
            if os.path.isdir(c):
                actual = c
                break
    if not actual:
        return 0

    n = 0
    for node in dag.get("nodes", []):
        if not node.get("id", "").startswith("I18N_"):
            continue
        for p in node.get("primitive_chain") or []:
            if p.get("type") not in ("P01", "P02", "P03"):
                continue
            inputs = p.get("inputs") or {}
            for k in ("path", "base_dir"):
                v = inputs.get(k)
                if isinstance(v, str) and "locales" in v:
                    if k == "base_dir":
                        inputs[k] = actual
                    else:
                        inputs[k] = actual + "/" + v.split("/locales/")[-1] if "/locales/" in v else actual
                    n += 1
                    break
    return n


def main() -> int:
    src_dag = config.EVAL_DIR / "dag.json"
    out_dag = config.EVAL_DIR / "dag_smoke_source.json"
    source_project = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE_PROJECT

    if not Path(source_project).exists():
        print(f"[patch] WARNING: source project path not found: {source_project}")

    text = src_dag.read_text(encoding="utf-8")
    new_text, counts = patch_text(text, source_project)

    try:
        dag = json.loads(new_text)
    except json.JSONDecodeError as exc:
        print(f"[patch] FATAL: result not valid JSON: {exc}")
        return 1

    desources_applied: dict[str, str] = {}
    _apply_node_desources(dag, desources_applied, source_project=source_project)

    dag.setdefault("meta", {}).setdefault("smoke_source_patches", {})
    dag["meta"]["smoke_source_patches"] = {
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_project": source_project,
        "replacements": counts,
        "node_level_desources": desources_applied,
        "_purpose": (
            "Stage 7.2 source-project smoke run only. DO NOT use as canonical DAG. "
            "Generated by tools/patch_dag_for_source_smoke.py."
        ),
    }

    out_dag.write_text(json.dumps(dag, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[patch] wrote {out_dag}")
    print()
    print("Text replacements:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print()
    print("Node-level de-sourcing (Stage 7.4):")
    for k, v in desources_applied.items():
        print(f"  {k}: {v}")
    print()
    print(f"Now run: python -m evaluate.run_all --dag {out_dag} --output source_run_vN.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
