import json
from collections import Counter

d = json.load(open(r"C:\Users\mcn\AppData\Local\Temp\opencode\dash.json"))
rr = d.get("recentResults", [])
types = Counter(r.get("type", "?") for r in rr)
print(f"Total results: {len(rr)}")
print(f"By type: {dict(types)}")
for r in rr[:5]:
    print(f"  {r['type']}: {r['meetingName']} R{r['raceNumber']} - {r['participant']}")
