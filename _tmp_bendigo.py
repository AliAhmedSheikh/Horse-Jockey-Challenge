import json, urllib.request
data = json.loads(urllib.request.urlopen('http://localhost:8000/meetings/m2/participants', timeout=10).read())
print(f"Bendigo total participants: {len(data)}")
print(f"All same price: {all(p['aiPrice'] == 49.0 for p in data)}")
print(f"Sample prices: {[p['aiPrice'] for p in data[:5]]}")
