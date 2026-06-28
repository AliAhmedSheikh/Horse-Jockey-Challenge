import json, urllib.request
data = json.loads(urllib.request.urlopen('http://localhost:8000/dashboard').read().decode())
jockeys = data.get('jockeys', [])
for j in jockeys:
    tp = j.get('tabtouchPrice')
    if tp is not None:
        print(f"{j['name']} ({j.get('meetingName')}): tabtouchPrice={tp}")
    else:
        print(f"{j['name']} ({j.get('meetingName')}): tabtouchPrice=None")
print("\n--- Drivers ---")
drivers = data.get('drivers', [])
for d in drivers:
    tp = d.get('tabtouchPrice')
    if tp is not None:
        print(f"{d['name']} ({d.get('meetingName')}): tabtouchPrice={tp}")
    else:
        print(f"{d['name']} ({d.get('meetingName')}): tabtouchPrice=None")
