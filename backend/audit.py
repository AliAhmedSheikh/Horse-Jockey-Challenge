"""Audit script: compare Ladbrokes API data vs database for Sunny Coast and Globe Derby."""
import httpx, json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from scrapers.base import _get_client, API_BASE
from time_utils import today_aus
from database import SessionLocal
from models import Meeting, Participant, Price, Result

today = today_aus()
client = _get_client()

def fetch_api_meetings():
    r = client.get(f'{API_BASE}/racing/meetings',
                   params={'date_from': today, 'date_to': today, 'country': 'AUS', 'type': ' ', 'limit': 200})
    if r.status_code != 200:
        print(f'API error: {r.status_code}')
        return []
    return r.json().get('data', {}).get('meetings', [])

def fetch_race_event(race_id):
    r2 = client.get(f'{API_BASE}/racing/events/{race_id}')
    if r2.status_code == 200:
        return r2.json().get('data', {})
    return None

# === 1. SUNNY COAST ===
print("=" * 70)
print("SUNNY COAST MEETING VALIDATION")
print("=" * 70)

api_meetings = fetch_api_meetings()
sunny_coast_api = None
for m in api_meetings:
    name = m.get('name', '')
    if 'sunny' in name.lower() and 'coast' in name.lower():
        sunny_coast_api = m
        break

if sunny_coast_api:
    print(f"\nLADBROKES API:")
    print(f"  Meeting name: {sunny_coast_api.get('name')}")
    print(f"  Category: {sunny_coast_api.get('category_name', '')}")
    all_races = sunny_coast_api.get('races', [])
    real_races = [r for r in all_races if r.get('race_number', 0) > 0]
    print(f"  Total races (API races array): {len(all_races)}")
    print(f"  Total races (race_number > 0): {len(real_races)}")
    print(f"\n  Per-race status:")
    for race in all_races:
        rn = race.get('race_number', 0)
        if rn == 0:
            continue
        data = fetch_race_event(race['id'])
        if data:
            status = data.get('race', {}).get('status', 'unknown')
            results = data.get('results', [])
            print(f"    Race {rn}: status={status}, results={len(results)}")
            for res in results:
                runner = next((ru for ru in data.get('runners', []) if ru.get('runner_number') == res.get('runner_number')), None)
                jockey = (runner.get('jockey') or '').strip() if runner else ''
                print(f"      pos={res['position']} runner={res['runner_number']} horse={res.get('name','')} jockey={jockey}")
        else:
            print(f"    Race {rn}: FAILED TO FETCH")
else:
    print("\n  NOT FOUND in Ladbrokes API for today")

# Check database
print(f"\nDATABASE:")
db = SessionLocal()
db_meetings = db.query(Meeting).filter(Meeting.date == today).all()
sunny_db = None
for m in db_meetings:
    if 'sunny' in m.name.lower() and 'coast' in m.name.lower():
        sunny_db = m
        break

if sunny_db:
    print(f"  Meeting: {sunny_db.name}")
    print(f"  Type: {sunny_db.type}")
    print(f"  Status: {sunny_db.status}")
    print(f"  total_races: {sunny_db.total_races}")
    print(f"  completed_races: {sunny_db.completed_races}")
    print(f"  remaining: {sunny_db.total_races - sunny_db.completed_races}")
    
    results = db.query(Result).filter(Result.meeting_id == sunny_db.id).order_by(Result.race_number).all()
    completed_race_nums = set(r.race_number for r in results)
    print(f"  Results in DB: {len(results)} rows across {len(completed_race_nums)} races")
    print(f"  Race numbers in DB: {sorted(completed_race_nums)}")
    
    participants = db.query(Participant).filter(Participant.meeting_id == sunny_db.id).all()
    print(f"  Participants: {len(participants)}")
    for p in participants:
        print(f"    {p.name}: points={p.current_points} completed={p.completed_races} remaining={p.remaining_races}")
else:
    print(f"  NOT FOUND in database")
db.close()

# === 2. GLOBE DERBY ===
print("\n" + "=" * 70)
print("GLOBE DERBY DRIVER CHALLENGE VALIDATION")
print("=" * 70)

globe_derby_api = None
for m in api_meetings:
    name = m.get('name', '')
    if 'globe' in name.lower() and 'derby' in name.lower():
        globe_derby_api = m
        break

if globe_derby_api:
    print(f"\nLADBROKES API:")
    print(f"  Meeting name: {globe_derby_api.get('name')}")
    print(f"  Category: {globe_derby_api.get('category_name', '')}")
    all_races = globe_derby_api.get('races', [])
    real_races = [r for r in all_races if r.get('race_number', 0) > 0]
    print(f"  Total races (race_number > 0): {len(real_races)}")
    
    # Collect all jockey/driver names and their results per race
    print(f"\n  Per-race results (driver view):")
    for race in all_races:
        rn = race.get('race_number', 0)
        if rn == 0:
            continue
        data = fetch_race_event(race['id'])
        if data:
            status = data.get('race', {}).get('status', 'unknown')
            results = data.get('results', [])
            runners = data.get('runners', [])
            print(f"    Race {rn}: status={status}, results={len(results)}")
            for res in results:
                runner = next((ru for ru in runners if ru.get('runner_number') == res.get('runner_number')), None)
                driver = (runner.get('driver') or runner.get('jockey') or '').strip() if runner else ''
                horse = res.get('name', '')
                print(f"      pos={res['position']} #{res['runner_number']} {horse} driver={driver}")
        else:
            print(f"    Race {rn}: FAILED TO FETCH")
else:
    print("\n  NOT FOUND in Ladbrokes API for today")

# Database check
print(f"\nDATABASE:")
db = SessionLocal()
globe_db = None
for m in db_meetings:
    if 'globe' in m.name.lower() and 'derby' in m.name.lower():
        globe_db = m
        break

if globe_db:
    print(f"  Meeting: {globe_db.name}")
    print(f"  Type: {globe_db.type}")
    print(f"  Status: {globe_db.status}")
    print(f"  total_races: {globe_db.total_races}")
    print(f"  completed_races: {globe_db.completed_races}")
    
    results = db.query(Result).filter(Result.meeting_id == globe_db.id).order_by(Result.race_number, Result.position).all()
    print(f"  Results in DB: {len(results)} rows")
    
    participants = db.query(Participant).filter(Participant.meeting_id == globe_db.id).all()
    print(f"  Participants: {len(participants)}")
    
    # Build race-by-race view
    from collections import defaultdict
    race_results = defaultdict(list)
    for r in results:
        race_results[r.race_number].append(r)
    
    for rn in sorted(race_results.keys()):
        print(f"  Race {rn}:")
        for r in race_results[rn]:
            p = next((x for x in participants if x.id == r.participant_id), None)
            pname = p.name if p else 'UNKNOWN'
            print(f"    {pname}: pos={r.position} pts_added={r.points_added} final_pts={r.final_points}")
    
    # Show cumulative points after each race
    print(f"\n  Cumulative points per race:")
    cum = {p.id: 0 for p in participants}
    for rn in sorted(race_results.keys()):
        print(f"  After Race {rn}:")
        for r in race_results[rn]:
            p = next((x for x in participants if x.id == r.participant_id), None)
            if p:
                cum[p.id] += r.points_added
        for p in sorted(participants, key=lambda x: cum[x.id], reverse=True):
            print(f"    {p.name}: {cum[p.id]}")
    
    # Show current database standings
    print(f"\n  Current DB Leaderboard (sorted by currentPoints DESC):")
    sorted_p = sorted(participants, key=lambda x: x.current_points, reverse=True)
    for i, p in enumerate(sorted_p, 1):
        print(f"    {i}. {p.name}: {p.current_points}pts (races={p.completed_races})")
else:
    print(f"  NOT FOUND in database")
db.close()

# === 3. COMPARISON SUMMARY ===
print("\n" + "=" * 70)
print("COMPARISON SUMMARY")
print("=" * 70)
print("\nCheck the API data above vs database data for discrepancies.")
print("Key things to verify:")
print("  1. Total races match between API and DB")
print("  2. Race completion status matches")
print("  3. Driver names match between API runners and DB participants")
print("  4. Points are correctly assigned by position")
print("  5. No duplicate result rows per participant per race")
