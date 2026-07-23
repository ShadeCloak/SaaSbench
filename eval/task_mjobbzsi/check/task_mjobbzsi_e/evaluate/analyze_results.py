import json, sys

fn = sys.argv[1] if len(sys.argv) > 1 else "results/smoke_test_v2.json"
with open(fn, encoding="utf-8") as f:
    data = json.load(f)

print(f"Reading: {fn}")
print("=== FAILED NODES ===")
for nid, ndata in data.items():
    if isinstance(ndata, dict) and ndata.get("status") == "FAILED":
        msg = str(ndata.get("message", ""))[:200]
        print(f"  {nid}: {ndata.get('score',0)}/{ndata.get('maxScore',0)} - {msg}")

print("\n=== PASSED NODES ===")
for nid, ndata in data.items():
    if isinstance(ndata, dict) and ndata.get("status") == "PASSED":
        print(f"  {nid}: {ndata.get('score',0)}/{ndata.get('maxScore',0)}")

print("\n=== SKIPPED NODES ===")
skipped = [(nid, ndata) for nid, ndata in data.items() if isinstance(ndata, dict) and ndata.get("status") == "SKIPPED_DEPENDENCY"]
for nid, _ in skipped[:15]:
    print(f"  {nid}")
print(f"  ... total skipped: {len(skipped)}")
