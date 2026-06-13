import logging
from typing import List, Dict
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.ladbrokes.com.au/affiliates/v1"
API_HEADERS = {
    "From": "dev@racing-dashboard.local",
    "X-Partner": "JockeyDriverDashboard",
}

_shared_client = None
_jockey_cache = None
_driver_cache = None


def _get_client():
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.Client(timeout=15, headers=API_HEADERS)
    return _shared_client


def invalidate_cache():
    global _jockey_cache, _driver_cache
    _jockey_cache = None
    _driver_cache = None


def _fetch_meetings(racing_type: str, challenge_type: str) -> List[Dict]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    client = _get_client()
    try:
        r = client.get(
            f"{API_BASE}/racing/meetings",
            params={"date_from": today, "date_to": today, "country": "AUS", "type": racing_type, "limit": 200},
        )
        if r.status_code != 200:
            return []
        meetings = r.json().get("data", {}).get("meetings", [])
    except Exception as e:
        logger.error(f"Failed to fetch meetings: {e}")
        return []

    markets = []
    for m in meetings:
        meeting_name = m.get("name", "")
        races = m.get("races", [])
        if not races:
            continue
        seen = {}
        for race in races[:2]:
            if race.get("race_number", 0) == 0:
                continue
            try:
                r2 = client.get(f"{API_BASE}/racing/events/{race['id']}")
                if r2.status_code != 200:
                    continue
                race_data = r2.json().get("data", {})
                for runner in race_data.get("runners", []):
                    if runner.get("is_scratched"):
                        continue
                    name = (runner.get("driver") or runner.get("jockey") or "").strip()
                    if not name or name == "Unknown":
                        continue
                    odds = runner.get("odds", {})
                    price = odds.get("fixed_win", 0)
                    if name not in seen or price > seen[name]:
                        seen[name] = price
            except Exception:
                continue
        if seen:
            parts = [{"name": n, "price": p} for n, p in seen.items()]
            parts.sort(key=lambda x: x["price"] if x["price"] > 0 else 999)
            markets.append({
                "meeting_name": meeting_name,
                "type": challenge_type,
                "participants": parts,
                "bookmaker": "Ladbrokes",
            })
    return markets


class LadbrokesAPIScraper:
    def __init__(self):
        self.name = "Ladbrokes"

    def fetch_jockey_challenge_meetings(self) -> List[Dict]:
        global _jockey_cache
        if _jockey_cache is not None:
            return _jockey_cache
        _jockey_cache = _fetch_meetings("T", "jockey")
        return _jockey_cache

    def fetch_driver_challenge_meetings(self) -> List[Dict]:
        global _driver_cache
        if _driver_cache is not None:
            return _driver_cache
        _driver_cache = _fetch_meetings("H", "driver")
        return _driver_cache

    def close(self):
        pass
