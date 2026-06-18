import logging
import threading
import time
from concurrent.futures import as_completed
from typing import List, Dict, Tuple, Optional
import httpx

from time_utils import today_aus
from utils import MIN_PRICE, MAX_PRICE

logger = logging.getLogger(__name__)

API_BASE = "https://api.ladbrokes.com.au/affiliates/v1"
API_HEADERS = {
    "From": "dev@racing-dashboard.local",
    "X-Partner": "JockeyDriverDashboard",
}
CACHE_TTL = 120

_client_lock = threading.Lock()
_cache_lock = threading.Lock()
_shared_client = None
_all_cache = None
_all_cache_time = 0.0


def _get_client():
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:
                _shared_client = httpx.Client(timeout=15, headers=API_HEADERS)
    return _shared_client


def invalidate_cache():
    global _all_cache, _all_cache_time
    with _cache_lock:
        _all_cache = None
        _all_cache_time = 0.0


def _fetch_all_meetings() -> Tuple[List[Dict], List[Dict]]:
    global _all_cache, _all_cache_time
    now = time.time()
    with _cache_lock:
        if _all_cache is not None and now - _all_cache_time < CACHE_TTL:
            return _all_cache

    today = today_aus()
    from datetime import date as _date, timedelta
    today_date = _date.fromisoformat(today)
    dates_to_try = [
        today,
        (today_date - timedelta(days=1)).isoformat(),
        (today_date + timedelta(days=1)).isoformat(),
    ]

    client = _get_client()
    all_meetings = []
    for d in dates_to_try:
        try:
            r = client.get(
                f"{API_BASE}/racing/meetings",
                params={"date_from": d, "date_to": d, "country": "AUS", "type": " ", "limit": 200},
            )
            if r.status_code == 200:
                meetings = r.json().get("data", {}).get("meetings", [])
                all_meetings.extend(meetings)
        except Exception as e:
            logger.warning(f"Failed to fetch meetings for {d}: {e}")

    if not all_meetings:
        logger.warning("Ladbrokes API returned no meetings on any date")
        return ([], [])

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
        jockey_race_odds = {}
        races_data = []

        def _fetch_race(client, race):
            rn = race.get("race_number", 0)
            if rn == 0:
                return None, []
            try:
                r2 = client.get(f"{API_BASE}/racing/events/{race['id']}")
                if r2.status_code != 200:
                    return None, []
                data = r2.json().get("data", {})
                ri = data.get("race", {})
                st = (ri.get("advertised_start_time") or ri.get("start_time") or
                      ri.get("commence_time") or ri.get("race_time") or
                      ri.get("time") or ri.get("advertised_start") or "")
                rd = {
                    "race_number": rn,
                    "status": ri.get("status", ""),
                    "start_time": st,
                    "results": data.get("results", []),
                    "runners": data.get("runners", []),
                }
                jp = []
                for runner in data.get("runners", []):
                    if runner.get("is_scratched", False):
                        continue
                    jockey = (runner.get("jockey") or runner.get("driver") or "").strip()
                    if not jockey:
                        continue
                    odds = runner.get("odds", {})
                    try:
                        win_price = float(odds.get("fixed_win", 0) or 0)
                    except (ValueError, TypeError):
                        continue
                    if win_price > 0:
                        win_price = max(MIN_PRICE, min(MAX_PRICE, win_price))
                    else:
                        continue
                    horse = (runner.get("horse_name") or runner.get("competitor_name") or
                             runner.get("horse") or runner.get("name") or "").strip()
                    jp.append((jockey, win_price, horse))
                return rd, jp
            except Exception as e:
                logger.warning(f"Failed to fetch race {race.get('id')}: {e}")
                return None, []

        valid = [r for r in races if r.get("race_number", 0) > 0]
        if valid:
            from scrapers.shared import get_pool
            pool = get_pool()
            futs = {pool.submit(_fetch_race, client, r): r for r in valid}
            for f in as_completed(futs):
                rd, jp = f.result()
                if rd:
                    races_data.append(rd)
                    rn = rd.get("race_number", 0)
                    for nm, pr, horse in jp:
                        if nm not in seen or pr < seen[nm][0]:
                            seen[nm] = (pr, horse)
                        jockey_race_odds.setdefault(nm, {})[rn] = {"odds": pr, "horse": horse}

        if seen:
            parts = [{"name": n, "price": p[0], "race_odds": jockey_race_odds.get(n, {})} for n, p in seen.items()]
            parts.sort(key=lambda x: x["price"] if x["price"] > 0 else float('inf'))
            total_racing_races = len([r for r in races if r.get("race_number", 0) > 0])
            market = {
                "meeting_name": meeting_name,
                "type": challenge_type,
                "participants": parts,
                "bookmaker": "Ladbrokes",
                "total_races": total_racing_races,
                "races": races_data,
            }
            if challenge_type == "driver":
                driver_markets.append(market)
            else:
                jockey_markets.append(market)

    with _cache_lock:
        _all_cache = (jockey_markets, driver_markets)
        _all_cache_time = time.time()
    logger.info(f"Fetched {len(jockey_markets)} jockey and {len(driver_markets)} driver meetings")
    return _all_cache


def fetch_single_race_results(meeting_name: str, race_number: int, date_override=None) -> Optional[Dict]:
    """Fetch results for a specific race, bypassing the global cache.

    Tries multiple dates: date_override (if provided), today, yesterday, and tomorrow.
    This handles meetings that were seeded on a different day than the Ladbrokes API entry.

    Returns dict with status, results, runners or None if unavailable.
    """
    from datetime import date as _date, timedelta
    today = today_aus()
    today_date = _date.fromisoformat(today)
    dates_to_try = []
    if date_override:
        dates_to_try.append(date_override)
    dates_to_try.append(today)
    dates_to_try.append((today_date - timedelta(days=1)).isoformat())
    dates_to_try.append((today_date + timedelta(days=1)).isoformat())

    client = _get_client()
    all_meetings = []
    for d in dates_to_try:
        try:
            r = client.get(
                f"{API_BASE}/racing/meetings",
                params={"date_from": d, "date_to": d, "country": "AUS", "type": " ", "limit": 200},
            )
            if r.status_code == 200:
                meetings = r.json().get("data", {}).get("meetings", [])
                all_meetings.extend(meetings)
        except Exception as e:
            logger.warning(f"fetch_single_race_results: failed to fetch meetings for {d}: {e}")

    if not all_meetings:
        logger.warning(f"fetch_single_race_results: no meetings found on any date")
        return None

    race_id = None
    for m in all_meetings:
        if m.get("name", "").lower().strip() == meeting_name.lower().strip():
            for race in m.get("races", []):
                if race.get("race_number") == race_number:
                    race_id = race.get("id")
                    break
            break

    if not race_id:
        available = [m.get("name", "?") for m in all_meetings[:10]]
        logger.warning(
            f"fetch_single_race_results: meeting '{meeting_name}' race {race_number} not found. "
            f"Available meetings: {available}"
        )
        return None

    try:
        r2 = client.get(f"{API_BASE}/racing/events/{race_id}")
        if r2.status_code != 200:
            logger.warning(f"fetch_single_race_results: event {race_id} returned {r2.status_code}")
            return None
        data = r2.json().get("data", {})
        return {
            "race_number": race_number,
            "status": data.get("race", {}).get("status", ""),
            "results": data.get("results", []),
            "runners": data.get("runners", []),
        }
    except Exception as e:
        logger.warning(f"fetch_single_race_results: failed to fetch event {race_id}: {e}")
        return None


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
