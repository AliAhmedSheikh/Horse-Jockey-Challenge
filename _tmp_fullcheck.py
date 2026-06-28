import json, urllib.request, sys
sys.path.insert(0, '/opt/jockey/backend/backend')

print("=" * 60)
print("CHECK 1: API Response for each meeting")
print("=" * 60)

meetings = ["m1", "m2", "m3", "m4", "m5", "m15"]
labels = {"m1": "Wyong", "m2": "Bendigo", "m3": "Casino", "m4": "Ipswich", "m5": "Northam", "m15": "Pukekohe"}

for mid in meetings:
    try:
        url = f"http://localhost:8000/meetings/{mid}/participants"
        data = json.loads(urllib.request.urlopen(url, timeout=10).read())
        if data:
            p = data[0]
            print(f"{mid} ({labels.get(mid)}): aiPrice={p.get('aiPrice')} tabtouchPrice={p.get('tabtouchPrice')}")
        else:
            print(f"{mid} ({labels.get(mid)}): NO PARTICIPANTS")
    except Exception as e:
        print(f"{mid} ({labels.get(mid)}): ERROR - {e}")

print()
print("=" * 60)
print("CHECK 2: TABtouch jockey challenge events (today)")
print("=" * 60)

from scrapers.tabtouch import _get_jockey_challenge_events
from time_utils import today_aus

date_str = today_aus()
events = _get_jockey_challenge_events(date_str)
print(f"TABtouch events for {date_str}: {len(events)}")
for e in events:
    print(f"  '{e.get('event_name')}' (id={e.get('event_id')})")

print()
print("=" * 60)
print("CHECK 3: Our meetings in DB")
print("=" * 60)

import sqlite3
db = sqlite3.connect('/opt/jockey/backend/jockey_driver.db')
c = db.cursor()
for r in c.execute("SELECT id, name, type, status FROM meetings WHERE date=?", (date_str,)):
    print(f"  {r[0]}: '{r[1]}' ({r[2]}) [{r[3]}]")

print()
print("=" * 60)
print("CHECK 4: Name matching analysis")
print("=" * 60)

our_names = [r[1].lower() for r in c.execute("SELECT name FROM meetings WHERE date=?", (date_str,)).fetchall()]
tab_names = [e.get('event_name', '').lower() for e in events]

print(f"Our meeting names: {our_names}")
print(f"TAB event names:   {tab_names}")

for our_name in our_names:
    matched = False
    for tab_name in tab_names:
        if our_name == tab_name:
            print(f"  EXACT: '{our_name}' == '{tab_name}'")
            matched = True
            break
        elif our_name in tab_name or tab_name in our_name:
            print(f"  PARTIAL: '{our_name}' ~ '{tab_name}'")
            matched = True
            break
        else:
            our_words = set(our_name.split())
            tab_words = set(tab_name.split())
            overlap = our_words & tab_words
            if overlap and len(overlap) >= min(len(our_words), len(tab_words)):
                print(f"  WORD OVERLAP: '{our_name}' ~ '{tab_name}' (shared: {overlap})")
                matched = True
                break
    if not matched:
        print(f"  NO MATCH: '{our_name}'")

db.close()
