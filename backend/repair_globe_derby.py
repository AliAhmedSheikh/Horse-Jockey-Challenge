"""Repair Globe Derby standings using real Ladbrokes API results.

1. Drop all existing results for Globe Derby
2. Fetch real race results from Ladbrokes API
3. Rebuild standings race-by-race with correct points
4. Update participant completed_races and current_points
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from database import SessionLocal
from models import Meeting, Participant, Price, Result, MeetingStatus
from scrapers.base import _get_client, API_BASE
from time_utils import today_aus
from seed_data import _get_real_race_positions

def points_for_position(pos, all_positions=None):
    """3-2-1 scoring with dead heat sharing per official TAB rules."""
    if pos > 3:
        return 0
    base = {1: 3, 2: 2, 3: 1}[pos]
    if not all_positions:
        return base
    count = sum(1 for p in all_positions if p == pos)
    if count > 1:
        total = sum({1: 3, 2: 2, 3: 1}.get(pos + i, 0) for i in range(count))
        return total / count
    return base

def repair_meeting(meeting_name="Globe Derby"):
    today = today_aus()
    client = _get_client()
    db = SessionLocal()

    # 1. Fetch API meeting data
    print(f"Fetching Ladbrokes API data for {meeting_name}...")
    r = client.get(f'{API_BASE}/racing/meetings',
                   params={'date_from': today, 'date_to': today, 'country': 'AUS', 'type': ' ', 'limit': 200})
    if r.status_code != 200:
        print(f"API error: {r.status_code}")
        return

    meetings = r.json().get('data', {}).get('meetings', [])
    api_meeting = None
    for m in meetings:
        if m.get('name', '').lower() == meeting_name.lower():
            api_meeting = m
            break

    if not api_meeting:
        print(f"Meeting '{meeting_name}' not found in API")
        return

    print(f"Found in API: {api_meeting.get('name')} ({api_meeting.get('category_name', '')})")

    # 2. Fetch all race events
    races_data = []
    for race in api_meeting.get('races', []):
        rn = race.get('race_number', 0)
        if rn == 0:
            continue
        try:
            r2 = client.get(f'{API_BASE}/racing/events/{race["id"]}')
            if r2.status_code == 200:
                data = r2.json().get('data', {})
                races_data.append({
                    'race_number': rn,
                    'status': data.get('race', {}).get('status', ''),
                    'results': data.get('results', []),
                    'runners': data.get('runners', []),
                })
                print(f"  Race {rn}: {len(data.get('results',[]))} results, status={data.get('race',{}).get('status','')}")
            else:
                print(f"  Race {rn}: HTTP {r2.status_code}")
        except Exception as e:
            print(f"  Race {rn}: error {e}")

    # 3. Find meeting in database
    db_meeting = db.query(Meeting).filter(
        Meeting.date == today,
        Meeting.name == meeting_name,
    ).first()

    if not db_meeting:
        print(f"Meeting '{meeting_name}' not found in database")
        db.close()
        return

    print(f"\nDatabase meeting: {db_meeting.name} (id={db_meeting.id})")
    print(f"  Current status: {db_meeting.status}")
    print(f"  Current completed_races: {db_meeting.completed_races}")

    # 4. Get participants
    participants = db.query(Participant).filter(
        Participant.meeting_id == db_meeting.id
    ).all()
    print(f"  Participants: {len(participants)}")
    for p in participants:
        print(f"    {p.name}")

    # 5. Build name mapping for participant lookup
    participant_map = {p.name.strip().lower(): p for p in participants}

    # 6. Delete all existing results for this meeting
    old_count = db.query(Result).filter(Result.meeting_id == db_meeting.id).count()
    db.query(Result).filter(Result.meeting_id == db_meeting.id).delete()
    db.flush()
    print(f"\nDeleted {old_count} old results")

    # 7. Rebuild results race-by-race using real API data
    completed_count = 0
    cumulative_points = {p.id: 0 for p in participants}
    race_counts = {p.id: 0 for p in participants}

    for rd in sorted(races_data, key=lambda x: x['race_number']):
        rn = rd['race_number']
        real_positions = _get_real_race_positions(rd, participants)

        if real_positions:
            print(f"\n  Race {rn}: Using REAL results ({len(real_positions)} drivers placed)")
            placed_ids = set()
            race_positions = [pos for _, pos in real_positions]
            for p, pos in real_positions:
                added = points_for_position(pos, race_positions)
                cumulative_points[p.id] += added
                race_counts[p.id] += 1
                placed_ids.add(p.id)
                result = Result(
                    meeting_id=db_meeting.id,
                    participant_id=p.id,
                    final_points=cumulative_points[p.id],
                    position=pos,
                    race_number=rn,
                    points_added=added,
                    timestamp=datetime.now(timezone.utc),
                )
                db.add(result)
                print(f"      {p.name}: pos={pos} +{added}pts (total={cumulative_points[p.id]})")
            for p in participants:
                if p.id not in placed_ids:
                    result = Result(
                        meeting_id=db_meeting.id,
                        participant_id=p.id,
                        final_points=cumulative_points[p.id],
                        position=99,
                        race_number=rn,
                        points_added=0,
                        timestamp=datetime.now(timezone.utc),
                    )
                    db.add(result)
            completed_count += 1
        else:
            print(f"\n  Race {rn}: NO real results available (status={rd.get('status','')})")
            # Don't simulate - leave uncompleted

    # 8. Update participant records
    total_races = len([rd for rd in races_data])
    for p in participants:
        p.current_points = cumulative_points[p.id]
        p.completed_races = race_counts[p.id]
        p.remaining_races = total_races - race_counts[p.id]

    db_meeting.completed_races = completed_count
    db_meeting.total_races = total_races
    if completed_count >= total_races:
        db_meeting.status = MeetingStatus.FINISHED.value
    elif completed_count > 0:
        db_meeting.status = MeetingStatus.LIVE.value

    db.commit()

    # 9. Print final standings
    print(f"\n{'='*60}")
    print(f"REPAIRED STANDINGS - {meeting_name}")
    print(f"{'='*60}")
    print(f"Total races: {total_races}, Completed: {completed_count}")
    print(f"")
    sorted_p = sorted(participants, key=lambda x: x.current_points, reverse=True)
    print(f"{'Rank':<6} {'Driver':<25} {'Points':<8} {'Ridden':<8}")
    print(f"{'-'*6} {'-'*25} {'-'*8} {'-'*8}")
    for i, p in enumerate(sorted_p, 1):
        print(f"{i:<6} {p.name:<25} {p.current_points:<8} {p.completed_races:<8}")
    print(f"\n{'='*60}")

    db.close()

if __name__ == "__main__":
    repair_meeting("Globe Derby")
