import json

with open("results/source_run_final.json", encoding="utf-8") as f:
    final = json.load(f)

with open("results/smoke_test_results.json", encoding="utf-8") as f:
    current = json.load(f)

key_nodes = [
    "DEPLOY_BUILD_SUCCESS", "DEPLOY_FEATURE_MODULE_COUNT", "DEPLOY_I18N_LANGUAGES",
    "CONF_ROOM_HTML", "CONF_WELCOME_PAGE", "CONF_PREJOIN_SCREEN", "CONF_JOIN_AND_TOOLBAR",
    "IFRAME_API_LOADS", "CHAT_OPEN_SEND_VERIFY", "RBAC_MOD_CAN_KICK",
    "RBAC_PARTICIPANT_CANNOT_KICK", "LOBBY_ENABLE_VERIFY", "LOBBY_DISPLAY_NAME_REQUIRED",
    "HAND_RAISE_TOGGLE", "E2EE_TOGGLE", "RECORDING_UI"
]

print("NODE_ID                         | ORIGINAL              | CURRENT               | DIFF")
print("-" * 110)
for nid in key_nodes:
    orig = final.get(nid, {})
    curr = current.get(nid, {})
    o_status = orig.get("status", "N/A")
    o_score = orig.get("score", "?")
    o_max = orig.get("maxScore", "?")
    c_status = curr.get("status", "N/A")
    c_score = curr.get("score", "?")
    c_max = curr.get("maxScore", "?")
    diff = "SAME" if o_status == c_status else f"{o_status} -> {c_status}"
    print(f"{nid:35s} | {o_status:8s} {o_score:>4}/{o_max:<4} | {c_status:18s} {c_score:>4}/{c_max:<4} | {diff}")

print("\n=== ORIGINAL: Failed/Skipped nodes ===")
for nid, v in final.items():
    if isinstance(v, dict) and v.get("status") in ("FAILED", "SKIPPED_DEPENDENCY"):
        print(f"  {nid}: {v.get('status')} msg={str(v.get('message',''))[:100]}")

print(f"\n=== ORIGINAL total nodes: {len([k for k,v in final.items() if isinstance(v,dict)])} ===")
print(f"=== CURRENT  total nodes: {len([k for k,v in current.items() if isinstance(v,dict)])} ===")
