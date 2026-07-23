import json
import time
from collections import defaultdict

import os
import config
import utils
from primitives import PRIMITIVES, _context, _resolve_inputs

import requests




try:
    from _dag_validator import validate_task_dir
    validate_task_dir(strict=True)
except SystemExit:
    raise
except Exception as _vh_exc:
    import logging as _vh_log
    _vh_log.getLogger("dag_validator").warning(
        "validate_task_dir failed: %s", _vh_exc)

def smoke_setup():
    base = config.APP_BASE_URL.rstrip("/")
    users_cfg = getattr(config, "TEST_USERS", {})
    admin = users_cfg.get("admin", {})
    admin_email = admin.get("email", "admin@example.com")
    admin_pw = admin.get("password", "admin123")

    for attempt in range(30):
        try:
            r = requests.get(f"{base}/api/users", timeout=5)
            if r.status_code != 502:
                break
        except Exception:
            pass
        time.sleep(2)

    try:
        r = requests.post(f"{base}/api/users/first-register",
                          json={"email": admin_email, "password": admin_pw}, timeout=15)
        if r.status_code in (200, 201):
            print(f"[setup] first-register OK: {admin_email}")
    except Exception:
        pass

    import psycopg2
    try:
        conn = psycopg2.connect(host=config.DB_HOST, port=config.DB_PORT,
                                dbname=config.DB_NAME, user=config.DB_USER, password=config.DB_PASSWORD)
        cur = conn.cursor()
        cur.execute("UPDATE users SET role='admin', login_attempts=0, lock_until=NULL WHERE email=%s", (admin_email,))
        conn.commit()
        cur.execute("SELECT id FROM users WHERE email=%s", (admin_email,))
        row = cur.fetchone()
        if row:
            from primitives import _context
            _context["admin_id"] = row[0]
        cur.close()
        conn.close()
        print("[setup] admin role ensured")
    except Exception as e:
        print(f"[setup] DB role update: {e}")

    token = None
    for attempt in range(3):
        try:
            r = requests.post(f"{base}/api/users/login",
                              json={"email": admin_email, "password": admin_pw}, timeout=15)
            if r.status_code in (200, 201):
                token = r.json().get("token")
                break
        except Exception:
            time.sleep(2)
    if not token:
        print("[setup] WARN: could not login as admin")
        return

    for role_key in ("editor", "restricted_user"):
        creds = users_cfg.get(role_key, {})
        email = creds.get("email")
        pw = creds.get("password")
        role_val = "editor" if "editor" in role_key else "user"
        if not email:
            continue
        try:
            r = requests.post(f"{base}/api/users",
                              json={"email": email, "password": pw, "role": role_val},
                              headers={"Authorization": f"Bearer {token}"}, timeout=15)
            if r.status_code in (200, 201):
                print(f"[setup] created {role_key}: {email}")
            else:
                print(f"[setup] {role_key} status={r.status_code} (may already exist)")
        except Exception as e:
            print(f"[setup] {role_key}: {e}")


def load_dag(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def topological_sort(nodes):
    id_to_node = {n["id"]: n for n in nodes}
    node_ids = set(id_to_node)
    in_degree = defaultdict(int)
    for n in nodes:
        for pre in n.get("prereqs") or []:
            if pre in node_ids:
                in_degree[n["id"]] += 1
    queue = [n["id"] for n in nodes if in_degree[n["id"]] == 0]
    order = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for n in nodes:
            if cur in (n.get("prereqs") or []):
                in_degree[n["id"]] -= 1
                if in_degree[n["id"]] == 0:
                    queue.append(n["id"])
    return [id_to_node[i] for i in order] if len(order) == len(nodes) else nodes


_NODE_CONTEXT_MAP = {
    "CRUD_CREATE_201":        ["post_id"],
    "CRUD_FINDBYID":          [],
    "CRUD_UPDATE_PATCH":      [],
    "CRUD_DELETE_BYID":       [],
    "CRUD_BULK_UPDATE":       [],
    "CRUD_BULK_DELETE":       [],
    "CRUD_COUNT":             [],
    "CRUD_DUPLICATE":         [],
    "CRUD_INVALID_JSON_400":  [],
    "CRUD_PAGINATION_LIMITS": [],
    "ACCESS_COLLECTION_DENY_403":    ["access_post_id", "deny_post_id"],
    "ACCESS_READ_DENIED_FIELD":      ["access_post_id", "deny_post_id"],
    "ACCESS_QUERY_DENIED_FIELD_400": [],
    "ACCESS_FIELD_UPDATE_DENIED":    [],
    "ACCESS_BYID_WHERE_403":         [],
    "ACCESS_HIDDEN_WHERE_FILTER":    [],
    "ACCESS_OVERRIDE_TRUE":          [],
    "ACCESS_COLLECTION_ALLOW_ADMIN": [],
    "ACCESS_READ_ALLOWED_FIELD":     [],
    "ACCESS_QUERY_ALLOWED_FIELD":    [],
    "ACCESS_BYID_ALLOWED":          [],
    "VERSION_DRAFT_CREATE":   ["draft_post_id"],
    "VERSION_PUBLISH":        [],
    "VERSION_RESTORE":        [],
    "VERSION_AUTOSAVE":       [],
    "VERSION_MAX_PER_DOC":    [],
    "VERSION_LIST":           [],
    "VERSION_LATEST_SNAPSHOT": [],
    "HOOK_BEFORE_CHANGE_MODIFY": ["hooks_test_id"],
    "HOOK_AFTER_CHANGE_RECEIVES_DOC": [],
    "HOOK_AFTER_READ_MODIFY": [],
    "HOOK_FALSY_RETURN_PRESERVES": [],
    "HOOK_TX_ROLLBACK":       [],
    "FIELD_GROUP_PATCH_REPLACE": ["group_post_id"],
    "FIELD_RELATIONSHIP_POPULATE": ["rel_post_id"],
    "FIELD_BLOCKS_CRUD":      [],
    "FIELD_ARRAY_CRUD":       [],
    "FIELD_TEXT_DEFAULT":     [],
    "FIELD_POINT_GEO":        [],
    "FIELD_RICHTEXT_JSON":    [],
    "FIELD_RELATIONSHIP_NULL": [],
    "LOCK_PREVENTS_UPDATE":   ["lock_post_id"],
    "LOCK_EXPIRATION":        [],
    "LOCK_OVERRIDE":          [],
    "TRASH_SOFT_DELETE":      ["trash_post_id"],
    "TRASH_RESTORE":          [],
    "TRASH_WITHOUT_PARAM":    [],
    "LOCALE_FIELD_STORE":     ["locale_page_id"],
    "LOCALE_ALL_MODE":        [],
    "LOCALE_FALLBACK":        [],
    "LOCALE_DB_STRUCTURE":    [],
    "GQL_MUTATION_CREATE":    ["gql_post_id"],
    "GQL_QUERY_FIND":         [],
    "GQL_QUERY_SINGLE":       [],
    "GQL_WHERE_SORT":         [],
    "GQL_BATCH_QUERY":        [],
    "GQL_COUNT_QUERY":        [],
    "GQL_LOCALE_PARAM":       [],
    "GQL_ERROR_FORMAT":       [],
    "GQL_TX_INDEPENDENCE":    [],
    "GQL_INTROSPECTION_DISABLED": [],
    "QUERY_DEPTH":            ["depth_post_id"],
    "UPLOAD_CREATE_FILE":     ["media_id"],
    "UPLOAD_IMAGE_SIZES":     [],
    "UPLOAD_SERVE_FILE":      [],
    "FOLDER_CRUD_POPULATE":   ["parent_folder_id"],
    "FOLDER_CASCADE_DELETE":  ["child_folder_id"],
    "SELECT_FIELDS":          [],
    "SELECT_EXCLUDE":         [],
}


_ENTITY_ENVELOPE_KEYS = ("doc", "data", "result", "payload", "item", "record", "object", "entity")
_ENTITY_ID_FIELDS = ("id", "_id", "uuid", "uid", "pk", "key", "slug", "code", "guid")
_API_KEY_FIELDS = ("apiKey", "api_key", "apikey", "API_KEY", "accessKey", "access_key", "token")
_FILENAME_FIELDS = ("filename", "fileName", "file_name", "name", "originalName", "original_name", "originalFilename")
_LIST_ENVELOPE_KEYS = ("docs", "data", "items", "results", "records", "list", "entries")


def _normalize_payload(body):
    if not isinstance(body, dict):
        return body
    for env in _ENTITY_ENVELOPE_KEYS:
        sub = body.get(env)
        if isinstance(sub, dict):
            return sub
    return body


def _read_first_field(d, fields):
    if not isinstance(d, dict):
        return None
    for f in fields:
        if d.get(f) not in (None, ""):
            return d[f]
    return None


def _extract_entity_ids(node_id, response_body, context):
    if not response_body or not isinstance(response_body, dict):
        return
    doc = _normalize_payload(response_body)
    nid = node_id.upper()

    eid = _read_first_field(doc, _ENTITY_ID_FIELDS)
    if eid is not None:
        context["new_post_id"] = eid

        explicit_vars = _NODE_CONTEXT_MAP.get(nid)
        if explicit_vars is not None:
            for var in explicit_vars:
                context[var] = eid
        else:
            if "FOLDER" in nid:
                if "parent_folder_id" not in context:
                    context["parent_folder_id"] = eid
                else:
                    context["child_folder_id"] = eid
            elif "UPLOAD" in nid or "MEDIA" in nid:
                context["media_id"] = eid
            elif "LOCK" in nid:
                context["lock_post_id"] = eid
            elif "TRASH" in nid:
                context["trash_post_id"] = eid
            elif "LOCALE" in nid:
                context["locale_page_id"] = eid
            elif "GQL" in nid or "GRAPHQL" in nid:
                context["gql_post_id"] = eid
            elif "DEPTH" in nid:
                context["depth_post_id"] = eid
            elif "HOOK" in nid:
                context["hooks_test_id"] = eid
            elif "GROUP" in nid:
                context["group_post_id"] = eid
            elif "REL" in nid:
                context["rel_post_id"] = eid
            elif "DRAFT" in nid or "VERSION" in nid:
                context["draft_post_id"] = eid
            elif "ACCESS" in nid:
                if "DENIED" in nid or "DENY" in nid:
                    context["access_post_id"] = eid
                    context["deny_post_id"] = eid
            elif "CREATE" in nid and "FOLDER" not in nid:
                context.setdefault("post_id", eid)

        fname = _read_first_field(doc, _FILENAME_FIELDS)
        if fname:
            context["media_filename"] = fname

    api_key_val = _read_first_field(doc, _API_KEY_FIELDS)
    if api_key_val:
        context["api_key"] = api_key_val

    docs_list = None
    for list_env in _LIST_ENVELOPE_KEYS:
        candidate = response_body.get(list_env)
        if isinstance(candidate, list):
            docs_list = candidate
            break
    if isinstance(docs_list, list) and docs_list:
        first = docs_list[0] if isinstance(docs_list[0], dict) else {}
        first_id = _read_first_field(first, _ENTITY_ID_FIELDS)
        if "VERSION" in nid and first_id is not None:
            context["version_id"] = first_id


ASSERT_TYPES = frozenset({"P01", "P02", "P06", "P07", "P14", "P15", "P17"})


def execute_chain(chain, context, results, node_id=""):
    last_response = None
    all_passed = True
    passed_steps = 0
    total_steps = 0
    llm_skipped = False
    llm_skip_reason = ""
    for step in chain:
        ptype = step.get("type", "")
        fn = PRIMITIVES.get(ptype)
        if not fn:
            continue
        total_steps += 1
        inp = _resolve_inputs(step.get("inputs") or {}, context)
        try:
            out = fn(inp, context, last_response)
        except Exception as e:
            out = {"passed": False, "message": str(e)}
        if ptype == "P17" and isinstance(out, dict):
            _p17d = out.get("data") or {}
            if isinstance(_p17d, dict) and _p17d.get("skipped"):
                llm_skipped = True
                llm_skip_reason = _p17d.get("reason") or "llm judge unavailable"
        if not out.get("passed", True):
            all_passed = False
        else:
            passed_steps += 1
        if ptype not in ASSERT_TYPES:
            new_resp = out.get("data") or out.get("last_response")
            if new_resp:
                last_response = new_resp
            if last_response and isinstance(last_response, dict) and "body" in last_response:
                _extract_entity_ids(node_id, last_response.get("body"), context)
    pass_ratio = (passed_steps / total_steps) if total_steps else 1.0
    return all_passed, pass_ratio, last_response, llm_skipped, llm_skip_reason


def _inject_test_user_placeholders():
    users_cfg = getattr(config, "TEST_USERS", {}) or {}
    role_to_keys = {
        "admin": ("admin_email", "admin_password"),
        "editor": ("editor_email", "editor_password"),
        "user": ("user_email", "user_password"),
        "restricted_user": ("restricted_email", "restricted_password"),
    }
    for role, (ek, pk) in role_to_keys.items():
        creds = users_cfg.get(role) or {}
        if creds.get("email"):
            _context.setdefault(ek, creds["email"])
        if creds.get("password"):
            _context.setdefault(pk, creds["password"])
    _context.setdefault("locktest_email", os.environ.get("LOCKTEST_EMAIL", "locktest@test.com"))
    _context.setdefault("wrong_password", "WrongPassword!")


def execute_dag(dag_path, scoring_config_path, only_category=None):
    _inject_test_user_placeholders()
    if os.environ.get("SMOKE_SETUP", "0") == "1":
        smoke_setup()
    dag = load_dag(dag_path)
    with open(scoring_config_path, encoding="utf-8") as f:
        scoring_config = json.load(f)
    nodes = dag["nodes"]
    if only_category:
        id_to_node = {n["id"]: n for n in nodes}
        keep = set(nid for nid, n in id_to_node.items() if n.get("scoring", {}).get("category") == only_category)
        while True:
            added = set()
            for nid in keep:
                for pre in id_to_node.get(nid, {}).get("prereqs") or []:
                    if pre not in keep:
                        added.add(pre)
            if not added:
                break
            keep |= added
        nodes = [id_to_node[nid] for nid in keep]
    nodes = topological_sort(nodes)
    results = {}
    context = {}
    for k, v in _context.items():
        if k != "auth_token":
            context[k] = v
    node_delay = float(os.environ.get("NODE_DELAY", "0.2"))
    for node in nodes:
        nid = node["id"]
        prereqs = node.get("prereqs") or []
        if node_delay > 0:
            time.sleep(node_delay)
        if not all(rid in results and results[rid].status == "EXECUTED" for rid in prereqs):
            results[nid] = utils.NodeResult(
                node_id=nid,
                status="SKIPPED_DEPENDENCY",
                score=0,
                max_score=node["scoring"]["maxScore"],
                category=node["scoring"]["category"],
                subcategory=node["scoring"].get("subcategory", ""),
            )
            continue
        try:
            all_passed, pass_ratio, evidence, llm_skipped, llm_skip_reason = execute_chain(node.get("primitive_chain") or [], context, results, node.get("id", ""))
        except Exception as e:
            results[nid] = utils.NodeResult(
                node_id=nid, status="ERROR", score=0, max_score=node["scoring"]["maxScore"],
                category=node["scoring"]["category"], subcategory=node["scoring"].get("subcategory", ""),
                message=str(e),
            )
            continue
        method = node["scoring"].get("method", "binary")
        max_score = node["scoring"]["maxScore"]
        if method == "binary":
            score = max_score if all_passed else 0
        elif method == "weighted":
            score = round(pass_ratio * max_score, 2)
        else:
            score = max_score if all_passed else 0
        _status = "EXECUTED"
        if llm_skipped:
            _status = "SKIPPED_LLM"
            score = 0
        results[nid] = utils.NodeResult(
            node_id=nid,
            status=_status,
            score=score,
            max_score=max_score,
            category=node["scoring"]["category"],
            subcategory=node["scoring"].get("subcategory", ""),
            evidence=evidence,
        )
    return results, scoring_config


SKIP_FROM_TOTAL = {"SKIPPED_LLM"}


def aggregate_results(results, scoring_config):
    by_cat = defaultdict(lambda: {"score": 0, "max": 0, "nodes": 0, "skipped_llm": 0})
    skipped_llm_max = 0.0
    for r in results.values():
        by_cat[r.category]["nodes"] += 1
        if r.status in SKIP_FROM_TOTAL:
            by_cat[r.category]["skipped_llm"] += 1
            skipped_llm_max += r.max_score
        else:
            by_cat[r.category]["score"] += r.score
            by_cat[r.category]["max"] += r.max_score
    out = {k: dict(v) for k, v in by_cat.items()}
    out["llm_judge_skipped_maxScore"] = round(skipped_llm_max, 3)
    return out
