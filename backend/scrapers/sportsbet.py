import logging
import threading
from typing import List, Dict, Tuple, Optional
import httpx

from time_utils import today_aus

logger = logging.getLogger(__name__)

API_BASE = "https://www.sportsbet.com.au/apigw/sportsbet-racing"
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


MEETINGS_QUERY = {
    "operationName": "getMeetings",
    "variables": {},
    "query": """
    query getMeetings {
      racingMeetings(
        filter: {date: null, jurisdictions: [], meetingCodes: [], pageSize: 200, pageNumber: 1}
      ) {
        items {
          id
          meetingName
          meetingType
          raceType
          races {
            id
            raceNumber
          }
        }
      }
    }
    """,
}

EVENT_QUERY = {
    "operationName": "getRaceDetails",
    "variables": {},
    "query": """
    query getRaceDetails($raceId: ID!) {
      race(id: $raceId) {
        id
        raceNumber
        status
        advertisedStartTime
        runners {
          id
          runnerName
          jockeyName
          driverName
          scratched
          fixedWinPrice
          fixedPlacePrice
          odds {
            fixedWin
            fixedPlace
          }
        }
        results {
          position
          runnerId
          runnerName
        }
      }
    }
    """,
}


def _fetch_all_meetings() -> Tuple[List[Dict], List[Dict]]:
    global _all_cache
    with _cache_lock:
        if _all_cache is not None:
            return _all_cache

    today = today_aus()
    client = _get_client()

    meetings_payload = {
        "operationName": "getMeetings",
        "variables": {"date": today},
        "query": MEETINGS_QUERY["query"].replace(
            "date: null", f'date: "{today}"'
        ),
    }

    try:
        r = client.post(f"{API_BASE}/graphql", json=meetings_payload)
        if r.status_code != 200:
            logger.warning(f"Sportsbet API returned {r.status_code}, will retry on next request")
            return ([], [])
        body = r.json()
        items = (body.get("data", {}).get("racingMeetings", {})
                 .get("items", []))
        meetings = items
    except Exception as e:
        logger.error(f"Failed to fetch Sportsbet meetings: {e}, will retry on next request")
        return ([], [])

    jockey_markets = []
    driver_markets = []

    for m in meetings:
        meeting_name = m.get("meetingName", m.get("name", ""))
        race_type = (m.get("raceType", m.get("meetingType", "") or "").upper())
        races = m.get("races", [])

        if race_type == "G":
            continue

        challenge_type = "driver" if race_type == "H" else "jockey"

        seen = {}
        races_data = []
        for race in races:
            race_id = race.get("id", "")
            race_num = race.get("raceNumber", 0)
            if not race_id or race_num == 0:
                continue
            try:
                payload = {
                    "operationName": "getRaceDetails",
                    "variables": {"raceId": race_id},
                    "query": EVENT_QUERY["query"],
                }
                r2 = client.post(f"{API_BASE}/graphql", json=payload)
                if r2.status_code != 200:
                    continue
                race_body = r2.json()
                race_data = race_body.get("data", {}).get("race", {})
                runners = race_data.get("runners", [])
                races_data.append({
                    "race_number": race_num,
                    "status": race_data.get("status", ""),
                    "start_time": race_data.get("advertisedStartTime", ""),
                    "results": race_data.get("results", []),
                    "runners": runners,
                })
                for runner in runners:
                    if runner.get("scratched"):
                        continue
                    rider = (runner.get("jockeyName", "") or
                             runner.get("driverName", "") or "").strip()
                    if not rider or rider.lower() in ("unknown", "n/a", "not declared"):
                        continue
                    price = (runner.get("fixedWinPrice") or
                             runner.get("odds", {}).get("fixedWin", 0) or 0)
                    if isinstance(price, str):
                        try:
                            price = float(price)
                        except (ValueError, TypeError):
                            price = 0
                    if price <= 0:
                        continue
                    if rider not in seen or price < seen[rider]:
                        seen[rider] = price
            except Exception:
                continue

        if seen:
            parts = [{"name": n, "price": p} for n, p in seen.items()]
            parts.sort(key=lambda x: x["price"] if x["price"] > 0 else 999)
            market = {
                "meeting_name": meeting_name,
                "type": challenge_type,
                "participants": parts,
                "bookmaker": "Sportsbet",
                "total_races": len(races),
                "races": races_data,
            }
            if challenge_type == "driver":
                driver_markets.append(market)
            else:
                jockey_markets.append(market)

    _all_cache = (jockey_markets, driver_markets)
    logger.info(f"Sportsbet: fetched {len(jockey_markets)} jockey and {len(driver_markets)} driver meetings")
    return _all_cache


def fetch_single_race_results(meeting_name: str, race_number: int) -> Optional[Dict]:
    today = today_aus()
    client = _get_client()
    meetings_payload = {
        "operationName": "getMeetings",
        "variables": {"date": today},
        "query": MEETINGS_QUERY["query"].replace(
            "date: null", f'date: "{today}"'
        ),
    }
    try:
        r = client.post(f"{API_BASE}/graphql", json=meetings_payload)
        if r.status_code != 200:
            return None
        body = r.json()
        items = body.get("data", {}).get("racingMeetings", {}).get("items", [])
    except Exception:
        return None

    race_id = None
    for m in items:
        if m.get("meetingName", "").lower().strip() == meeting_name.lower().strip():
            for race in m.get("races", []):
                if race.get("raceNumber") == race_number:
                    race_id = race.get("id")
                    break
            break

    if not race_id:
        return None

    try:
        payload = {
            "operationName": "getRaceDetails",
            "variables": {"raceId": race_id},
            "query": EVENT_QUERY["query"],
        }
        r2 = client.post(f"{API_BASE}/graphql", json=payload)
        if r2.status_code != 200:
            return None
        data = r2.json().get("data", {}).get("race", {})
        return {
            "race_number": race_number,
            "status": data.get("status", ""),
            "results": data.get("results", []),
            "runners": data.get("runners", []),
        }
    except Exception:
        return None


class SportsbetAPIScraper:
    def __init__(self):
        self.name = "Sportsbet"

    def fetch_jockey_challenge_meetings(self) -> List[Dict]:
        jockey, _ = _fetch_all_meetings()
        return jockey

    def fetch_driver_challenge_meetings(self) -> List[Dict]:
        _, driver = _fetch_all_meetings()
        return driver

    def close(self):
        pass
