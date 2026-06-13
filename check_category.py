import json
d = json.load(open(r"C:\Users\mcn\AppData\Local\Temp\opencode\meetings.json"))
for m in d.get("data", {}).get("meetings", []):
    if m["name"] in ["Bunbury", "Belmont", "Melton", "Albion Park"]:
        print(f"{m['name']}: category={m.get('category','?')} ({m.get('category_name','?')})")
