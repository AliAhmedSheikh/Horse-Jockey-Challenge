import sys
sys.path.insert(0, '/opt/jockey/backend/backend')
from scrapers.tabtouch import _get_jockey_challenge_events
from time_utils import today_aus

date_str = today_aus()
print(f"Date: {date_str}")

# Try today
events_today = _get_jockey_challenge_events(date_str)
print(f"\nToday ({date_str}) jockey challenge events: {len(events_today)}")
for e in events_today:
    print(f"  {e.get('event_name')} (id={e.get('event_id')})")

# Try yesterday too
from datetime import datetime, timedelta
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
events_yesterday = _get_jockey_challenge_events(yesterday)
print(f"\nYesterday ({yesterday}) jockey challenge events: {len(events_yesterday)}")
for e in events_yesterday:
    print(f"  {e.get('event_name')} (id={e.get('event_id')})")
