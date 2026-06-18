import logging
import time
import threading
from typing import List, Dict
import httpx
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

from utils import MIN_PRICE, MAX_PRICE

API_BASE = "https://api.au.pointsbet.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://pointsbet.com.au",
    "Referer": "https://pointsbet.com.au/racing",
}

_shared_client = None
_client_lock = threading.Lock()

_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 120


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


def _fetch_races(racing_type: int, region: int = 2) -> List[Dict]:
    """Fetch races from PointsBet API.
    
    racing_type: 1=Thoroughbred, 7=Greyhound, 3=Harness(?)
    region: 2=AUS, 1=INTL, 3=ALL
    """
    cache_key = f"races_{racing_type}_{region}"
    now = time.time()
    with _cache_lock:
        if cache_key in _cache:
            entry = _cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < _CACHE_TTL:
                return entry[0]

    url = f"{API_BASE}/api/racing/v4/races/nextup"
    params = {
        "racingType": racing_type,
        "region": region,
        "raceCount": 50,
        "runnerCount": 30,
        "fixedPricesOnly": "true",
    }
    try:
        client = _get_client()
        r = client.get(url, params=params)
        if r.status_code != 200:
            logger.warning(f"PointsBet API returned {r.status_code}")
            return []
        data = r.json()
        with _cache_lock:
            _cache[cache_key] = (data, time.time())
        return data
    except Exception as e:
        logger.warning(f"PointsBet API error: {e}")
        return []


def _build_jockey_prices(meetings_data: List[Dict], mtype: str) -> List[Dict]:
    """Build per-meeting jockey/driver challenge prices from per-race odds.
    
    For each meeting, aggregate each jockey's best (lowest) FixedWin price
    across all races at that meeting.
    """
    from time_utils import today_aus
    from utils import normalise_name

    # Group races by venue
    venue_races = {}
    for race in meetings_data:
        country = race.get("countryCode", "")
        if country != "AUS":
            continue
        venue = race.get("venue", "").strip()
        if not venue:
            continue
        if venue not in venue_races:
            venue_races[venue] = []
        venue_races[venue].append(race)

    result = []
    for venue, races in venue_races.items():
        jockey_best_price = {}
        jockey_rides = {}

        for race in races:
            runner_map = {}
            for runner in race.get("runners", []):
                runner_map[runner.get("runnerId")] = runner

            for market in race.get("markets", []):
                if market.get("marketType") != "FixedWin":
                    continue
                for sel in market.get("selections", []):
                    rid = sel.get("runnerId", "")
                    price = sel.get("price")
                    if not price or price <= 0:
                        continue
                    runner = runner_map.get(rid, {})
                    if runner.get("isScratched"):
                        continue
                    rider = ""
                    if mtype == "jockey":
                        rider = (runner.get("jockey") or "").strip()
                    else:
                        rider = (runner.get("driver") or runner.get("jockey") or "").strip()
                    if not rider:
                        continue
                    price = round(max(MIN_PRICE, min(MAX_PRICE, float(price))), 2)
                    jockey_rides[rider] = jockey_rides.get(rider, 0) + 1
                    if rider not in jockey_best_price or price < jockey_best_price[rider]:
                        jockey_best_price[rider] = price

        if not jockey_best_price:
            continue

        # Adjust prices: more rides = slightly shorter price (more chances to score)
        # adjusted_price = best_price * (0.98 ** (num_rides - 1))
        jockey_prices = {}
        for rider, best_price in jockey_best_price.items():
            num_rides = jockey_rides[rider]
            adjusted = round(best_price * (0.98 ** (num_rides - 1)), 2)
            jockey_prices[rider] = max(MIN_PRICE, min(MAX_PRICE, adjusted))

        participants = [
            {"name": name, "price": price}
            for name, price in sorted(jockey_prices.items(), key=lambda x: x[1])
        ]

        market = {
            "meeting_name": venue,
            "type": mtype,
            "participants": participants,
            "bookmaker": "PointsBet",
            "total_races": len(races),
            "races": [],
        }
        result.append(market)
        logger.info(
            f"PointsBet {mtype}: {venue} "
            f"({len(participants)} participants, {len(races)} races)"
        )

    return result


class PointsBetScraper:
    """Scrape PointsBet Australia fixed odds via their public API.
    
    PointsBet does not have a dedicated 'Jockey Challenge' product.
    Instead, we derive challenge prices from per-race FixedWin odds,
    mapping each runner's jockey/driver to their best price across all races.
    """

    def __init__(self):
        self.name = "PointsBet"

    def scrape_jockey_challenges(self) -> List[Dict]:
        from time_utils import today_aus
        races = _fetch_races(racing_type=1, region=2)  # Thoroughbred AUS
        if not races:
            logger.info("PointsBet jockey: no AUS thoroughbred races found")
            return []
        return _build_jockey_prices(races, "jockey")

    def scrape_driver_challenges(self) -> List[Dict]:
        from time_utils import today_aus
        # racingType=3 is harness racing on PointsBet
        all_races = list(_fetch_races(racing_type=3, region=2))

        if not all_races:
            # Fall back: fetch all types and filter for harness
            for rt in [1, 3, 5, 7]:
                races = _fetch_races(racing_type=rt, region=2)
                for race in races:
                    if race.get("racingType", "").lower() in ("harness", "trot"):
                        all_races.append(race)

        if not all_races:
            # Try all regions as last resort
            for rt in [1, 3, 5, 7]:
                races = _fetch_races(racing_type=rt, region=3)
                for race in races:
                    if race.get("racingType", "").lower() in ("harness", "trot"):
                        all_races.append(race)

        if not all_races:
            logger.info("PointsBet driver: no AUS harness races found")
            return []

        return _build_jockey_prices(all_races, "driver")

    def close(self):
        pass
