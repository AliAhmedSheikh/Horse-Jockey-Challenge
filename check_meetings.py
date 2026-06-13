import json, urllib.request

url = "https://horse-jockey-challenge-2.onrender.com/meetings/today"
req = urllib.request.Request(url, headers={"User-Agent": "Python"})
data = json.loads(urllib.request.urlopen(req, timeout=15).read())
for m in data:
    print(f"{m['id']}: {m['name']} - type={m['type']} status={m['status']} completedRaces={m['completedRaces']}")
