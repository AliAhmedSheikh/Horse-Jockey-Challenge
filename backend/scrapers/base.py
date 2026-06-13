import logging
from typing import List, Dict, Tuple
from datetime import datetime, timezone
import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.ladbrokes.com.au/affiliates/v1"
API_HEADERS = {
    "From": "dev@racing-dashboard.local",
    "X-Partner": "JockeyDriverDashboard",
}

_shared_client = None
_all_cache = None


def _get_client():
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.Client(timeout=15, headers=API_HEADERS)
    return _shared_client


def invalidate_cache():
    global _all_cache
    _all_cache = None


def _fetch_all_meetings() -> Tuple[List[Dict], List[Dict]]:
    global _all_cache
    if _all_cache is not None:
        return _all_cache

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    client = _get_client()
    try:
        r = client.get(
            f"{API_BASE}/racing/meetings",
            params={"date_from": today, "date_to": today, "country": "AUS", "type": "T", "limit": 200},
        )
        if r.status_code != 200:
            _all_cache = ([], [])
            return _all_cache
        meetings = r.json().get("data", {}).get("meetings", [])
    except Exception as e:
        logger.error(f"Failed to fetch meetings: {e}")
        _all_cache = ([], [])
        return _all_cache

    jockey_markets = []
    driver_markets = []

    for m in meetings:
        category = m.get("category", "")
        meeting_name = m.get("name", "")
        races = m.get("races", [])
        if not races:
            continue

        # Skip greyhound meetings
        if category == "G":
            continue

        # Determine type from meeting category
        challenge_type = "driver" if category == "H" else "jockey"

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
                    name = (runner.get("jockey") or "").strip() or (runner.get("driver") or "").strip()
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
            market = {
                "meeting_name": meeting_name,
                "type": challenge_type,
                "participants": parts,
                "bookmaker": "Ladbrokes",
            }
            if challenge_type == "driver":
                driver_markets.append(market)
            else:
                jockey_markets.append(market)

    _all_cache = (jockey_markets, driver_markets)
    logger.info(f"Fetched {len(jockey_markets)} jockey and {len(driver_markets)} driver meetings")
    return _all_cache


class LadbrokesAPIScraper:
    def __init__(self):
        self.name = "Ladbrokes"

    def fetch_jockey_challenge_meetings(self) -> List[Dict]:
        jockey, _ = _fetch_all_meetings()
        return jockey

    def fetch_driver_challenge_meetings(self) -> List[Dict]:
        _, driver = _fetch_all_meetings()
        return driver

    def close(self):
        pass
