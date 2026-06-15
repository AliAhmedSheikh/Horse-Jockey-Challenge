import logging
import threading
from typing import List, Dict, Tuple, Optional
import httpx

from time_utils import today_aus

logger = logging.getLogger(__name__)

API_BASE = "https://api.pointsbet.com.au"
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

_client_lock = threading.Lock()
_cache_lock = threading.Lock()
_shared_client = None
_all_cache = None


def _get_client():
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:
                _shared_client = httpx.Client(timeout=15, headers=API_HEADERS)
    return _shared_client


def invalidate_cache():
    global _all_cache
    with _cache_lock:
        _all_cache = None


def _fetch_all_meetings() -> Tuple[List[Dict], List[Dict]]:
    global _all_cache
    with _cache_lock:
        if _all_cache is not None:
            return _all_cache

    today = today_aus()
    client = _get_client()
    try:
        r = client.get(f"{API_BASE}/v2/racing/meetings", params={"date": today})
        if r.status_code != 200:
            logger.warning(f"PointsBet API returned {r.status_code}, will retry on next request")
            return ([], [])
        data = r.json()
        meetings = data.get("meetings", data.get("data", []))
    except Exception as e:
        logger.error(f"Failed to fetch PointsBet meetings: {e}, will retry on next request")
        return ([], [])

    jockey_markets = []
    driver_markets = []

    for m in meetings:
        meeting_name = m.get("meetingName", m.get("name", ""))
        race_type = (m.get("raceType", m.get("category", "") or "").upper())
        races = m.get("races", m.get("events", []))

        if race_type == "G":
            continue

        challenge_type = "driver" if race_type == "H" else "jockey"

        seen = {}
        races_data = []
        for race in races:
            race_num = race.get("raceNumber", race.get("race_number", 0))
            if race_num == 0:
                continue
            try:
                event_id = race.get("id", race.get("eventId", ""))
                if not event_id:
                    continue
                r2 = client.get(f"{API_BASE}/v2/racing/events/{event_id}")
                if r2.status_code != 200:
                    continue
                race_data = r2.json()
                race_info = race_data.get("race", race_data)
                runners = race_info.get("runners", race_info.get("competitors", []))
                races_data.append({
                    "race_number": race_num,
                    "status": race_info.get("status", ""),
                    "start_time": race_info.get("advertisedStartTime", ""),
                    "results": race_info.get("results", []),
                    "runners": runners,
                })
                for runner in runners:
                    if runner.get("scratched", False) or runner.get("isScratched", False):
                        continue
                    rider = (runner.get("jockey", "") or runner.get("jockeyName", "") or
                             runner.get("driver", "") or runner.get("driverName", "") or "").strip()
                    if not rider or rider.lower() in ("unknown", "n/a", "not declared"):
                        continue
                    odds = runner.get("odds", runner.get("fixedPrice", runner.get("winPrice", {})))
                    if isinstance(odds, dict):
                        price = odds.get("fixedWin", odds.get("winPrice", odds.get("price", 0)))
                    else:
                        price = float(odds) if odds else 0
                    if price <= 0:
                        continue
                    if rider not in seen or price < seen[rider]:
                        seen[rider] = price
            except Exception:
                continue

        if seen:
            parts = [{"name": n, "price": p} for n, p in seen.items()]
            parts.sort(key=lambda x: x["price"] if x["price"] > 0 else 999)
            total_racing_races = len([r for r in races if r.get("raceNumber", r.get("race_number", 0)) > 0])
            market = {
                "meeting_name": meeting_name,
                "type": challenge_type,
                "participants": parts,
                "bookmaker": "PointsBet",
                "total_races": total_racing_races,
                "races": races_data,
            }
            if challenge_type == "driver":
                driver_markets.append(market)
            else:
                jockey_markets.append(market)

    _all_cache = (jockey_markets, driver_markets)
    logger.info(f"PointsBet: fetched {len(jockey_markets)} jockey and {len(driver_markets)} driver meetings")
    return _all_cache


def fetch_single_race_results(meeting_name: str, race_number: int) -> Optional[Dict]:
    today = today_aus()
    client = _get_client()
    try:
        r = client.get(f"{API_BASE}/v2/racing/meetings", params={"date": today})
        if r.status_code != 200:
            return None
        data = r.json()
        meetings = data.get("meetings", data.get("data", []))
    except Exception:
        return None

    race_id = None
    for m in meetings:
        if m.get("meetingName", m.get("name", "")).lower().strip() == meeting_name.lower().strip():
            for race in m.get("races", m.get("events", [])):
                if race.get("raceNumber", race.get("race_number", 0)) == race_number:
                    race_id = race.get("id", race.get("eventId", ""))
                    break
            break

    if not race_id:
        return None

    try:
        r2 = client.get(f"{API_BASE}/v2/racing/events/{race_id}")
        if r2.status_code != 200:
            return None
        race_data = r2.json()
        race_info = race_data.get("race", race_data)
        runners = race_info.get("runners", race_info.get("competitors", []))
        return {
            "race_number": race_number,
            "status": race_info.get("status", ""),
            "results": race_info.get("results", []),
            "runners": runners,
        }
    except Exception:
        return None


class PointsBetAPIScraper:
    def __init__(self):
        self.name = "PointsBet"

    def fetch_jockey_challenge_meetings(self) -> List[Dict]:
        jockey, _ = _fetch_all_meetings()
        return jockey

    def fetch_driver_challenge_meetings(self) -> List[Dict]:
        _, driver = _fetch_all_meetings()
        return driver

    def close(self):
        pass
