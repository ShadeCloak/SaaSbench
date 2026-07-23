import json

with open("results/smoke_test_v2.json", encoding="utf-8") as f:
    data = json.load(f)

for nid in ["CONF_ROOM_HTML", "CONF_WELCOME_PAGE", "CONF_PREJOIN_SCREEN"]:
    if nid in data and isinstance(data[nid], dict):
        v = data[nid]
        print(f"\n=== {nid} ===")
        print(f"  status: {v.get('status')}")
        print(f"  score: {v.get('score')}/{v.get('maxScore')}")
        print(f"  message: {v.get('message', '')[:200]}")
        ev = v.get("evidence", {})
        if "chain_results" in ev:
            for i, cr in enumerate(ev["chain_results"]):
                print(f"  chain[{i}] {cr.get('type')}: passed={cr.get('passed')} msg={str(cr.get('message',''))[:150]}")
                if cr.get("output"):
                    out = cr["output"]
                    if "text" in out:
                        print(f"    text length: {len(out['text'])}")
                        print(f"    text preview: {out['text'][:200]}")
                    if "results" in out:
                        for r in out["results"]:
                            print(f"    assertion: {r}")
                    if "html" in out:
                        print(f"    html length: {len(out['html'])}")
