import json, urllib.request
d = json.loads(urllib.request.urlopen('http://localhost:8000/meetings/today').read())
for m in d:
    print(f"{m['id']:5s} {m['name']:20s} {m['type']:8s} {m['status']:12s} {m['completedRaces']}/{m['totalRaces']}")
