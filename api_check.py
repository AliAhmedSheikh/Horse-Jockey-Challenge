import urllib.request, json
data = json.loads(urllib.request.urlopen('http://localhost:8000/meetings/today').read())
for m in data:
    print(f"{m['id']:5s} {m['name']:25s} {m['type']:8s} {m['status']:12s} {m['completedRaces']}/{m['totalRaces']}")
