"""Neds scraper - fetches jockey/driver challenge prices from Neds GraphQL API."""
import json
import logging
import time
import threading
from typing import List, Dict
import httpx
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

from utils import MIN_PRICE, MAX_PRICE

API_BASE = "https://api.neds.com.au/gql/router"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/graphql-response+json, application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.neds.com.au",
    "Referer": "https://www.neds.com.au/racing",
    "graphql-client-name": "sportsbook",
    "graphql-client-version": "release/fe.535",
    "graphql-client-build": "a1ed1da11cb1d573cb7c87d0fc1a9d1f23da568f",
}

PERSISTED_HASHES = {
    "RacingHomeScreenWeb": "77c712df2987b69fb85009665192c9be3140c5ceb0f49bac061632deeccfe691",
    "RacingRaceCardScreenWeb": "2f586937a696c739495abb6b41b48508a22878afa59697506ca32e8e860c857d",
}

_shared_client = None
_client_lock = threading.Lock()

_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 120


def invalidate_cache():
    global _cache
    with _cache_lock:
        _cache = {}


def _get_client():
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:
                _shared_client = httpx.Client(
                    headers=HEADERS,
                    follow_redirects=True,
                    timeout=30,
                    verify=False,
                )
    return _shared_client


def _gql(operation: str, variables: dict):
    """Call Neds GraphQL API with persisted query hash."""
    cache_key = f"neds_{operation}_{json.dumps(variables, sort_keys=True)}"
    now = time.time()
    with _cache_lock:
        if cache_key in _cache:
            entry = _cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < _CACHE_TTL:
                return entry[0]

    params = {
        "operationName": operation,
        "variables": json.dumps(variables),
        "extensions": json.dumps({
            "persistedQuery": {"version": 1, "sha256Hash": PERSISTED_HASHES[operation]}
        }),
    }
    try:
        client = _get_client()
        r = client.get(API_BASE, params=params)
        if r.status_code != 200:
            logger.warning(f"Neds {operation} returned {r.status_code}")
            return None
        data = r.json()
        if "errors" in data:
            logger.warning(f"Neds {operation} errors: {data['errors']}")
            return None
        with _cache_lock:
            _cache[cache_key] = (data, now)
        return data
    except Exception as e:
        logger.warning(f"Neds API error ({operation}): {e}")
        return None


def _fetch_meetings(mtype: str) -> List[Dict]:
    """Fetch all meetings for today from Neds home screen.

    Returns list of meeting dicts with {name, id, races: [{id, number}]}
    """
    from datetime import date
    today = date.today().isoformat()
    data = _gql("RacingHomeScreenWeb", {"date": today})
    if not data:
        return []

    category = "horse" if mtype == "jockey" else "harness"
    nodes = data.get("data", {}).get(category, {}).get("nodes", [])
    
    meetings = []
    cats_seen = set()
    for node in nodes:
        venue = node.get("venue", {})
        country = (venue or {}).get("country", "")
        # Keep if country is Australia (AUS) or unknown
        if country and country not in ("AUS", ""):
            continue

        name = node.get("name", "")
        if not name:
            continue
        # Deduplicate by name (Neds returns international meetings too)
        norm_meeting = name.lower().replace(" ", "")
        if norm_meeting in cats_seen:
            continue
        cats_seen.add(norm_meeting)

        races = []
        for rn in (node.get("races", {}) or {}).get("nodes", []):
            rid = rn.get("id", "")
            if rid:
                races.append({
                    "id": rid,
                    "number": rn.get("number", 0),
                })

        meetings.append({
            "name": name,
            "id": node.get("id", ""),
            "races": sorted(races, key=lambda x: x["number"]),
        })

    return meetings


def _get_runner_fixed_odds(prices: List) -> float:
    """Extract best win fixed odds from Neds price entries."""
    if not prices:
        return None
    best = None
    for p in prices:
        odds = p.get("odds")
        if odds and isinstance(odds, dict):
            num = odds.get("numerator") or 0
            den = odds.get("denominator") or 1
            if den > 0 and num > 0:
                decimal = 1.0 + (float(num) / float(den))
                if best is None or decimal > best:
                    best = decimal
        elif odds and isinstance(odds, (int, float)):
            if odds > 0:
                if best is None or odds > best:
                    best = float(odds)
    return best


def _fetch_race_runners(race_uuid: str) -> List[Dict]:
    """Fetch runner data for a single race from Neds race card."""
    card_id = f"RacingRaceCard:{race_uuid}"
    data = _gql("RacingRaceCardScreenWeb", {
        "id": card_id,
        "isLoggedIn": False,
        "includePlaceExtra": True,
    })
    if not data:
        return []

    rc = data.get("data", {}).get("raceCard", {})
    if not rc:
        return []

    runners = rc.get("finalField", {}).get("runnerRows", [])
    result = []
    for r in runners:
        if r.get("scratchedDeduction") is not None and r.get("scratchedDeduction") != 0:
            continue
        jockey = (r.get("jockeyName") or "").replace("J: ", "").replace("D: ", "").strip()
        if not jockey:
            continue
        price = _get_runner_fixed_odds(r.get("prices", []))
        if not price:
            continue
        result.append({
            "name": (r.get("name") or "").strip(),
            "jockey": jockey,
            "price": price,
        })
    return result


def _build_jockey_prices(meetings: List[Dict], mtype: str) -> List[Dict]:
    """Build per-meeting jockey/driver challenge prices from Neds race data."""
    result = []
    for meeting in meetings:
        if not meeting.get("races"):
            continue

        jockey_prices = {}
        all_race_runners = []

        for race in meeting["races"]:
            race_uuid = race["id"].replace("RacingRace:", "")
            runners = _fetch_race_runners(race_uuid)
            for r in runners:
                rider = r["jockey"]
                price = round(max(MIN_PRICE, min(MAX_PRICE, float(r["price"]))), 2)
                if rider not in jockey_prices or price < jockey_prices[rider]:
                    jockey_prices[rider] = price
                all_race_runners.append({
                    "race_number": race["number"],
                    "runner": r["name"],
                    "rider": rider,
                    "price": price,
                })

        if not jockey_prices:
            continue

        participants = [
            {"name": name, "price": price, "race_odds": {}}
            for name, price in sorted(jockey_prices.items(), key=lambda x: x[1])
        ]

        market = {
            "meeting_name": meeting["name"],
            "type": mtype,
            "participants": participants,
            "bookmaker": "Neds",
            "total_races": len(meeting["races"]),
            "races": [],
        }
        result.append(market)
        logger.info(
            f"Neds {mtype}: {meeting['name']} "
            f"({len(participants)} participants, {len(meeting['races'])} races)"
        )

    return result


class NedsScraper:
    """Scrape Neds fixed odds via their GraphQL API.

    Neds is owned by Entain (same as Ladbrokes) and uses the same race/meeting UUIDs.
    Prices are extracted from per-race FixedWin markets.
    """

    def __init__(self):
        self.name = "Neds"

    def scrape_jockey_challenges(self) -> List[Dict]:
        meetings = _fetch_meetings("jockey")
        if not meetings:
            logger.info("Neds jockey: no AUS horse meetings found")
            return []
        return _build_jockey_prices(meetings, "jockey")

    def scrape_driver_challenges(self) -> List[Dict]:
        meetings = _fetch_meetings("driver")
        if not meetings:
            logger.info("Neds driver: no AUS harness meetings found")
            return []
        return _build_jockey_prices(meetings, "driver")

    def close(self):
        pass
