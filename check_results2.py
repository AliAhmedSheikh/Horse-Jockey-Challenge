import json, urllib.request
from collections import Counter

url = "https://horse-jockey-challenge-2.onrender.com/dashboard"
req = urllib.request.Request(url, headers={"User-Agent": "Python"})
data = json.loads(urllib.request.urlopen(req, timeout=15).read())
rr = data["recentResults"]
types = Counter(r["type"] for r in rr)
print(f"Total results: {len(rr)}")
print(f"By type: {dict(types)}")
print(f"\nJockey count: {sum(1 for r in rr if r['type'] == 'jockey')}")
print(f"Driver count: {sum(1 for r in rr if r['type'] == 'driver')}")
for r in rr:
    print(f"  [{r['type']}] {r['meetingName']} R{r['raceNumber']} - {r['participant']}")
