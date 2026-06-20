import json

with open('/tmp/racecard_full.json') as f:
    data = json.load(f)
rc = data['data']['raceCard']

# Extract runners from finalField
ff = rc.get('finalField', {})
runners = ff.get('runners', [])
print(f'Runners: {len(runners)}')
for r in runners[:3]:
    if isinstance(r, dict):
        print(json.dumps(r, indent=2)[:1000])
        print('---')

# Check runnerRows
rr = ff.get('runnerRows', [])
print(f'\nrunnerRows: {len(rr)}')
for row in rr[:2]:
    if isinstance(row, dict):
        print(json.dumps(row, indent=2)[:1000])
        print('---')
    elif isinstance(row, list):
        for cell in row[:2]:
            print(json.dumps(cell, indent=2)[:500])
        print('---')

# Search for challenge-related fields in full response
text = json.dumps(data).lower()
for kw in ['challenge', 'driverwinner', 'jockeywinner', 'meeting', '321', 'points']:
    count = text.count(kw)
    if count > 0:
        print(f"\n'{kw}' found {count} times")
