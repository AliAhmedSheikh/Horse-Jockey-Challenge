import logging
import re
import json
import time
import threading
from typing import List, Dict, Optional
import httpx
import urllib3
from bs4 import BeautifulSoup
from utils import MIN_PRICE, MAX_PRICE, CHALLENGE_MARGINS, CHALLENGE_STRATEGIES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BASE = "https://www.tabtouch.com.au"

_NON_AU_PATTERN = re.compile(r'\s+-\s+\w{2,4}\s*$')
_NZ_VENUES = {"ellerslie", "riccarton", "addington", "forbury park", "invercargill", "cambridge", "alexandra park", "manukau", "christchurch"}
_JOCKEY_CHALLENGE_RE = re.compile(r'(.+?)\s+Jockey Challenge\s+3,2,1\s+Points', re.IGNORECASE)
_DRIVER_CHALLENGE_RE = re.compile(r'(.+?)\s+Driver\s+(?:Challenge|Wins)\s+3,2,1\s+Points', re.IGNORECASE)
_GLOBALS_PATTERN = re.compile(r'globals\.fixedOddsBettingData\s*=\s*({.*?});', re.DOTALL)
_EVENT_ID_PATTERN = re.compile(r'/event-(\d+)')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-AU,en;q=0.9",
}

_shared_client = None
_client_lock = threading.Lock()
_event_cache = {}
_event_cache_lock = threading.Lock()
_CACHE_TTL = 120


def _get_client():
    global _shared_client
    if _shared_client is None:
        with _client_lock:
            if _shared_client is None:
                _shared_client = httpx.Client(
                    headers=HEADERS,
                    follow_redirects=True,
                    timeout=20,
                    verify=False,
                )
    return _shared_client


def _get_jockey_challenge_events(date_str: str) -> List[Dict]:
    """Fetch the TABtouch jockey challenge listing page and extract events."""
    cache_key = f"events_{date_str}"
    now = time.time()
    with _event_cache_lock:
        if cache_key in _event_cache:
            entry = _event_cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < _CACHE_TTL:
                return entry[0]

    url = f"{BASE}/racing/jockey-challenge/{date_str}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"TABtouch jockey challenge listing returned {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table')
        if not table:
            logger.info("TABtouch jockey challenge listing: no events table found")
            return []

        events = []
        rows = table.find_all('tr')
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            link = cells[2].find('a')
            if not link:
                continue
            event_name = link.get_text(strip=True)
            href = link.get('href', '')
            m = _EVENT_ID_PATTERN.search(href)
            if not m:
                continue
            event_id = int(m.group(1))
            events.append({
                "event_id": event_id,
                "event_name": event_name,
                "href": href,
            })

        with _event_cache_lock:
            _event_cache[cache_key] = (events, time.time())
        return events
    except Exception as e:
        logger.warning(f"TABtouch jockey challenge listing error: {e}")
        return []


def _fetch_jockey_challenge_event(event_id: int, date_str: str) -> Optional[Dict]:
    """Fetch a specific jockey challenge event from the TABtouch JSON API."""
    cache_key = f"event_{event_id}"
    now = time.time()
    with _event_cache_lock:
        if cache_key in _event_cache:
            entry = _event_cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < _CACHE_TTL:
                return entry[0]

    url = f"{BASE}/api/fixed-odds/refresh/jockeychallenge/{date_str}/event-{event_id}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            return None

        data = r.json()
        if data.get("responseCode") != "Success":
            return None

        with _event_cache_lock:
            _event_cache[cache_key] = (data, time.time())
        return data
    except Exception as e:
        logger.warning(f"TABtouch jockey challenge event {event_id} error: {e}")
        return None


def _fetch_event_from_html(event_id: int, date_str: str) -> Optional[Dict]:
    """Fallback: fetch event page HTML and extract globals.fixedOddsBettingData."""
    cache_key = f"event_{event_id}"
    now = time.time()
    with _event_cache_lock:
        if cache_key in _event_cache:
            entry = _event_cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < _CACHE_TTL:
                return entry[0]

    url = f"{BASE}/racing/jockey-challenge/{date_str}/event-{event_id}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            return None

        m = _GLOBALS_PATTERN.search(r.text)
        if not m:
            return None

        data = json.loads(m.group(1))
        with _event_cache_lock:
            _event_cache[cache_key] = (data, time.time())
        return data
    except Exception as e:
        logger.warning(f"TABtouch event page {event_id} error: {e}")
        return None


def _get_driver_challenge_events(date_str: str) -> List[Dict]:
    """Fetch the TABtouch driver challenge listing page and extract events."""
    cache_key = f"driver_events_{date_str}"
    now = time.time()
    with _event_cache_lock:
        if cache_key in _event_cache:
            entry = _event_cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < _CACHE_TTL:
                return entry[0]

    url = f"{BASE}/racing/driver-challenge/{date_str}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"TABtouch driver challenge listing returned {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table')
        if not table:
            logger.info("TABtouch driver challenge listing: no events table found")
            return []

        events = []
        rows = table.find_all('tr')
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            link = cells[2].find('a')
            if not link:
                continue
            event_name = link.get_text(strip=True)
            href = link.get('href', '')
            m = _EVENT_ID_PATTERN.search(href)
            if not m:
                continue
            event_id = int(m.group(1))
            events.append({
                "event_id": event_id,
                "event_name": event_name,
                "href": href,
            })

        with _event_cache_lock:
            _event_cache[cache_key] = (events, time.time())
        return events
    except Exception as e:
        logger.warning(f"TABtouch driver challenge listing error: {e}")
        return []


def _fetch_driver_challenge_event(event_id: int, date_str: str) -> Optional[Dict]:
    """Fetch a specific driver challenge event from the TABtouch JSON API."""
    cache_key = f"driver_event_{event_id}"
    now = time.time()
    with _event_cache_lock:
        if cache_key in _event_cache:
            entry = _event_cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < _CACHE_TTL:
                return entry[0]

    url = f"{BASE}/api/fixed-odds/refresh/driverchallenge/{date_str}/event-{event_id}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            return None

        data = r.json()
        if data.get("responseCode") != "Success":
            return None

        with _event_cache_lock:
            _event_cache[cache_key] = (data, time.time())
        return data
    except Exception as e:
        logger.warning(f"TABtouch driver challenge event {event_id} error: {e}")
        return None


def _fetch_driver_event_from_html(event_id: int, date_str: str) -> Optional[Dict]:
    """Fallback: fetch driver challenge event page HTML and extract globals.fixedOddsBettingData."""
    cache_key = f"driver_event_{event_id}"
    now = time.time()
    with _event_cache_lock:
        if cache_key in _event_cache:
            entry = _event_cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < _CACHE_TTL:
                return entry[0]

    url = f"{BASE}/racing/driver-challenge/{date_str}/event-{event_id}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            return None

        m = _GLOBALS_PATTERN.search(r.text)
        if not m:
            return None

        data = json.loads(m.group(1))
        with _event_cache_lock:
            _event_cache[cache_key] = (data, time.time())
        return data
    except Exception as e:
        logger.warning(f"TABtouch driver challenge event page {event_id} error: {e}")
        return None


def _get_todays_meetings() -> List[Dict]:
    """Get all AU horse and harness meetings from TABtouch racing page."""
    from time_utils import today_aus
    date_str = today_aus()
    url = f"{BASE}/racing/{date_str}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table')
        if not table:
            return []

        rows = table.find_all('tr')
        meetings = {}
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 7:
                continue
            code = cells[2].get_text(strip=True)
            meeting_id = cells[3].get_text(strip=True)
            meeting_name = cells[4].get_text(strip=True)
            race_num_str = cells[5].get_text(strip=True)

            if code == "Horse Race":
                mtype = "jockey"
            elif code == "Harness Race":
                mtype = "driver"
            else:
                continue

            if _NON_AU_PATTERN.search(meeting_name) or meeting_name.lower().strip() in _NZ_VENUES:
                continue

            try:
                race_num = int(race_num_str)
            except ValueError:
                continue
            if race_num <= 0:
                continue

            if meeting_id not in meetings:
                meetings[meeting_id] = {
                    "meeting_name": meeting_name,
                    "meeting_id": meeting_id,
                    "type": mtype,
                    "races": [],
                    "seen": set(),
                }
            elif meetings[meeting_id]["type"] != mtype:
                continue

            if race_num not in meetings[meeting_id]["seen"]:
                meetings[meeting_id]["races"].append({
                    "race_number": race_num,
                })
                meetings[meeting_id]["seen"].add(race_num)

        result = []
        for mid, info in meetings.items():
            info["races"].sort(key=lambda x: x["race_number"])
            result.append(info)
        return result
    except Exception as e:
        logger.warning(f"TABtouch racing page error: {e}")
        return []


def _fetch_race_page_horse_data(meeting_id: str, date_str: str, races: List[Dict], role: str = "driver") -> Dict[str, Dict]:
    """Fetch horse names + per-race odds from TAB race pages for a meeting.

    Args:
        meeting_id: TAB meeting ID (e.g. "WAG")
        date_str: Date string (e.g. "2026-06-19")
        races: List of dicts with "race_number" key
        role: "driver" for harness, "jockey" for thoroughbred

    Returns:
        Dict mapping name -> {race_num: {"odds": float, "horse": str}}
    """
    name_race_odds = {}

    def _fetch_one(mid, ds, ri):
        rn = ri["race_number"]
        url = f"{BASE}/racing/{ds}/{mid.lower()}/{rn}"
        try:
            client = _get_client()
            r = client.get(url)
            if r.status_code != 200:
                return rn, []

            pattern = re.compile(r'var model = ({.*?});', re.DOTALL)
            m = pattern.search(r.text)
            if not m:
                return rn, []

            model = json.loads(m.group(1))
            results = []

            starters = model.get("allStarters", [])
            if not starters:
                legs = model.get("pool", {}).get("legs", [])
                if legs:
                    starters = legs[0].get("starters", [])

            for starter in starters:
                if starter.get("isScratched") or starter.get("isFobScratched"):
                    continue
                name = (starter.get("jockey") or starter.get("associatedName") or starter.get("rider") or "").strip()
                if not name or name.lower() in ("unknown", "n/a", "not declared", "n.r", "nr", "not riding", "scratching", ""):
                    continue
                horse = (starter.get("horseName") or starter.get("runnerName") or starter.get("name") or starter.get("horse") or "").strip()
                try:
                    raw_price = starter.get("fixedWinDividendDollars") or starter.get("winDividendDollars") or starter.get("fixedWinDiv") or "0"
                    price_str = str(raw_price).replace("-", "").strip()
                    price = float(price_str) if price_str else 0
                except (ValueError, TypeError):
                    continue
                if price > 0 and horse:
                    results.append((name, round(max(MIN_PRICE, min(MAX_PRICE, price)), 2), horse))
            return rn, results
        except Exception as e:
            logger.warning(f"TAB {role} race page {mid} R{rn}: {e}")
            return rn, []

    if not races:
        return name_race_odds

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(_fetch_one, meeting_id, date_str, ri): ri for ri in races}
        for f in as_completed(futs):
            rn, race_results = f.result()
            for name, price, horse in race_results:
                name_race_odds.setdefault(name, {})[rn] = {"odds": price, "horse": horse}

    return name_race_odds


class TABScraper:
    """Scrape TAB jockey/driver challenge odds via TABtouch API.

    TAB and TABtouch are both Tabcorp brands sharing the same data.
    Uses the TABtouch JSON API endpoints which are publicly accessible.
    """

    def __init__(self):
        self.name = "TAB"

    def scrape_jockey_challenges(self) -> List[Dict]:
        from time_utils import today_aus
        date_str = today_aus()

        events = _get_jockey_challenge_events(date_str)
        if not events:
            return self._scrape_jockey_from_race_pages(date_str)

        meetings = _get_todays_meetings()
        meeting_race_counts = {}
        meeting_map = {}
        for mtg in meetings:
            if mtg["type"] == "jockey":
                meeting_race_counts[mtg["meeting_name"]] = len(mtg["races"])
                meeting_map[mtg["meeting_name"]] = mtg

        result = []
        for event in events:
            event_name = event["event_name"]
            event_id = event["event_id"]

            m = _JOCKEY_CHALLENGE_RE.match(event_name)
            if not m:
                continue
            meeting_name = m.group(1).strip()

            data = _fetch_jockey_challenge_event(event_id, date_str)
            if not data:
                data = _fetch_event_from_html(event_id, date_str)
            if not data:
                continue

            propositions = data.get("propositions", [])
            if not propositions:
                continue

            participants = []
            for prop in propositions:
                name = (prop.get("name") or "").strip()
                if not name:
                    continue
                if "/" in name or "Any Other" in name or "Dead Heat" in name:
                    continue
                if "must complete" in name.lower():
                    continue
                is_open = data.get("isOpen", False)
                if is_open and (prop.get("showRacingStatusText") or not prop.get("showBetButton")):
                    continue
                try:
                    price = float(prop.get("winReturn", 0) or 0)
                except (ValueError, TypeError):
                    continue
                if price > 0:
                    price = round(max(MIN_PRICE, min(MAX_PRICE, price)), 2)
                    participants.append({"name": name, "price": price})

            if not participants:
                continue

            participants.sort(key=lambda x: x["price"])
            total_races = meeting_race_counts.get(meeting_name, 0)

            race_page_data = _fetch_race_page_horse_data(
                meeting_map[meeting_name]["meeting_id"] if meeting_name in meeting_map else "",
                date_str,
                meeting_map[meeting_name]["races"] if meeting_name in meeting_map else [],
                "jockey",
            )

            for p in participants:
                if p["name"] in race_page_data:
                    p["race_odds"] = race_page_data[p["name"]]

            market = {
                "meeting_name": meeting_name,
                "type": "jockey",
                "participants": participants,
                "bookmaker": "TAB",
                "total_races": total_races,
                "races": [],
            }
            result.append(market)
            logger.info(
                f"TAB jockey: {meeting_name} "
                f"({len(participants)} participants, {total_races} races, "
                f"{sum(1 for p in participants if 'race_odds' in p)} with horse data)"
            )

        return result

    def scrape_driver_challenges(self) -> List[Dict]:
        """TABtouch driver challenges via dedicated endpoint, falling back to race pages."""
        from time_utils import today_aus
        date_str = today_aus()

        result = self._scrape_driver_from_endpoint(date_str)
        if result:
            return result

        return self._scrape_driver_from_race_pages(date_str)

    def _scrape_driver_from_endpoint(self, date_str: str) -> List[Dict]:
        """Try the dedicated driver challenge listing + event API."""
        events = _get_driver_challenge_events(date_str)
        if not events:
            return []

        meetings = _get_todays_meetings()
        meeting_race_counts = {}
        meeting_map = {}
        for mtg in meetings:
            if mtg["type"] == "driver":
                meeting_race_counts[mtg["meeting_name"]] = len(mtg["races"])
                meeting_map[mtg["meeting_name"]] = mtg

        result = []
        for event in events:
            event_name = event["event_name"]
            event_id = event["event_id"]

            m = _DRIVER_CHALLENGE_RE.match(event_name)
            if not m:
                continue
            meeting_name = m.group(1).strip()

            data = _fetch_driver_challenge_event(event_id, date_str)
            if not data:
                data = _fetch_driver_event_from_html(event_id, date_str)
            if not data:
                continue

            propositions = data.get("propositions", [])
            if not propositions:
                continue

            participants = []
            for prop in propositions:
                name = (prop.get("name") or "").strip()
                if not name:
                    continue
                if "/" in name or "Any Other" in name or "Dead Heat" in name:
                    continue
                if "must complete" in name.lower():
                    continue
                is_open = data.get("isOpen", False)
                if is_open and (prop.get("showRacingStatusText") or not prop.get("showBetButton")):
                    continue
                try:
                    price = float(prop.get("winReturn", 0) or 0)
                except (ValueError, TypeError):
                    continue
                if price > 0:
                    price = round(max(MIN_PRICE, min(MAX_PRICE, price)), 2)
                    participants.append({"name": name, "price": price})

            if not participants:
                continue

            participants.sort(key=lambda x: x["price"])
            total_races = meeting_race_counts.get(meeting_name, 0)

            race_page_data = _fetch_race_page_horse_data(
                meeting_map[meeting_name]["meeting_id"] if meeting_name in meeting_map else "",
                date_str,
                meeting_map[meeting_name]["races"] if meeting_name in meeting_map else [],
                "driver",
            )

            for p in participants:
                if p["name"] in race_page_data:
                    p["race_odds"] = race_page_data[p["name"]]

            market = {
                "meeting_name": meeting_name,
                "type": "driver",
                "participants": participants,
                "bookmaker": "TAB",
                "total_races": total_races,
                "races": [],
            }
            result.append(market)
            logger.info(
                f"TAB driver (endpoint): {meeting_name} "
                f"({len(participants)} participants, {total_races} races, "
                f"{sum(1 for p in participants if 'race_odds' in p)} with horse data)"
            )

        return result

    def _scrape_driver_from_race_pages(self, date_str: str) -> List[Dict]:
        """Fallback: derive driver challenge prices from individual race pages."""
        meetings = _get_todays_meetings()
        if not meetings:
            return []

        result = []
        for mtg in meetings:
            if mtg["type"] != "driver":
                continue

            meeting_id = mtg["meeting_id"]

            def _process_race(mid, ds, rn_info):
                rn = rn_info["race_number"]
                url = f"{BASE}/racing/{ds}/{mid.lower()}/{rn}"
                try:
                    client = _get_client()
                    r = client.get(url)
                    if r.status_code != 200:
                        return rn, []

                    pattern = re.compile(r'var model = ({.*?});', re.DOTALL)
                    m = pattern.search(r.text)
                    if not m:
                        return rn, []

                    model = json.loads(m.group(1))
                    results = []

                    starters = model.get("allStarters", [])
                    if not starters:
                        legs = model.get("pool", {}).get("legs", [])
                        if legs:
                            starters = legs[0].get("starters", [])

                    for starter in starters:
                        if starter.get("isScratched") or starter.get("isFobScratched"):
                            continue
                        driver = (starter.get("jockey") or starter.get("associatedName") or starter.get("rider") or "").strip()
                        if not driver or driver.lower() in ("unknown", "n/a", "not declared", "n.r", "nr", "not riding", "scratching", ""):
                            continue
                        horse = (starter.get("horseName") or starter.get("runnerName") or starter.get("name") or starter.get("horse") or "").strip()
                        try:
                            raw_price = starter.get("fixedWinDividendDollars") or starter.get("winDividendDollars") or starter.get("fixedWinDiv") or "0"
                            price_str = str(raw_price).replace("-", "").strip()
                            price = float(price_str) if price_str else 0
                        except (ValueError, TypeError):
                            continue
                        if price > 0:
                            results.append((driver, round(max(MIN_PRICE, min(MAX_PRICE, price)), 2), horse))
                    return rn, results
                except Exception as e:
                    logger.warning(f"TAB driver race {mid} R{rn}: {e}")
                    return rn, []

            races = mtg["races"]
            if races:
                all_driver_prices = {}
                all_race_odds = {}
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = {ex.submit(_process_race, meeting_id, date_str, ri): ri for ri in races}
                    for f in as_completed(futs):
                        rn, race_results = f.result()
                        for driver, price, horse in race_results:
                            all_driver_prices.setdefault(driver, []).append(price)
                            if horse:
                                all_race_odds.setdefault(driver, {})[rn] = {"odds": price, "horse": horse}

                bm = "TAB"
                margin = CHALLENGE_MARGINS.get(bm, 0)
                strategy = CHALLENGE_STRATEGIES.get(bm, "best")
                driver_prices = {}
                for name, prices in all_driver_prices.items():
                    if strategy == "avg":
                        derived = sum(prices) / len(prices)
                    elif strategy == "median":
                        s = sorted(prices)
                        mid_idx = len(s) // 2
                        derived = s[mid_idx] if len(s) % 2 else (s[mid_idx - 1] + s[mid_idx]) / 2
                    else:
                        derived = min(prices)
                    driver_prices[name] = round(max(MIN_PRICE, min(MAX_PRICE, derived * (1 + margin))), 2)

                total_races_count = len(mtg["races"])
                min_rides = max(1, int(total_races_count * 0.3))
                filtered_driver_prices = {
                    name: price for name, price in driver_prices.items()
                    if len(all_driver_prices.get(name, [])) >= min_rides
                }
                filtered_count = len(driver_prices) - len(filtered_driver_prices)
                if filtered_count > 0:
                    logger.info(
                        f"TAB driver (race pages): {mtg['meeting_name']} "
                        f"filtered {filtered_count} drivers with <{min_rides} rides "
                        f"({len(filtered_driver_prices)} remain of {len(driver_prices)})"
                    )

                if filtered_driver_prices:
                    participants = []
                    for name, price in sorted(filtered_driver_prices.items(), key=lambda x: x[1]):
                        p = {"name": name, "price": price}
                        if name in all_race_odds:
                            p["race_odds"] = all_race_odds[name]
                        participants.append(p)
                    market = {
                        "meeting_name": mtg["meeting_name"],
                        "type": "driver",
                        "participants": participants,
                        "bookmaker": "TAB",
                        "total_races": total_races_count,
                        "races": [],
                    }
                    result.append(market)
                    logger.info(
                        f"TAB driver (race pages): {mtg['meeting_name']} "
                        f"({len(participants)} participants, {total_races_count} races)"
                    )

        return result

    def _scrape_jockey_from_race_pages(self, date_str: str) -> List[Dict]:
        """Fallback: derive jockey challenge prices from individual race pages."""
        meetings = _get_todays_meetings()
        if not meetings:
            return []

        from concurrent.futures import ThreadPoolExecutor, as_completed

        result = []
        for mtg in meetings:
            if mtg["type"] != "jockey":
                continue

            meeting_id = mtg["meeting_id"]

            def _process_race(mid, ds, ri):
                rn = ri["race_number"]
                url = f"{BASE}/racing/{ds}/{mid.lower()}/{rn}"
                try:
                    client = _get_client()
                    r = client.get(url)
                    if r.status_code != 200:
                        return rn, []

                    pattern = re.compile(r'var model = ({.*?});', re.DOTALL)
                    m = pattern.search(r.text)
                    if not m:
                        return rn, []

                    model = json.loads(m.group(1))
                    results = []

                    starters = model.get("allStarters", [])
                    if not starters:
                        legs = model.get("pool", {}).get("legs", [])
                        if legs:
                            starters = legs[0].get("starters", [])

                    for starter in starters:
                        if starter.get("isScratched") or starter.get("isFobScratched"):
                            continue
                        jockey = (starter.get("jockey") or starter.get("associatedName") or starter.get("rider") or "").strip()
                        if not jockey or jockey.lower() in ("unknown", "n/a", "not declared", "n.r", "nr", "not riding", "scratching", ""):
                            continue
                        horse = (starter.get("horseName") or starter.get("runnerName") or starter.get("name") or starter.get("horse") or "").strip()
                        try:
                            raw_price = starter.get("fixedWinDividendDollars") or starter.get("winDividendDollars") or starter.get("fixedWinDiv") or "0"
                            price_str = str(raw_price).replace("-", "").strip()
                            price = float(price_str) if price_str else 0
                        except (ValueError, TypeError):
                            continue
                        if price > 0:
                            results.append((jockey, round(max(MIN_PRICE, min(MAX_PRICE, price)), 2), horse))
                    return rn, results
                except Exception as e:
                    logger.warning(f"TAB jockey race {mid} R{rn}: {e}")
                    return rn, []

            races = mtg["races"]
            if races:
                all_jockey_prices = {}
                all_race_odds = {}
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = {ex.submit(_process_race, meeting_id, date_str, ri): ri for ri in races}
                    for f in as_completed(futs):
                        rn, race_results = f.result()
                        for jockey, price, horse in race_results:
                            all_jockey_prices.setdefault(jockey, []).append(price)
                            if horse:
                                all_race_odds.setdefault(jockey, {})[rn] = {"odds": price, "horse": horse}

                bm = "TAB"
                margin = CHALLENGE_MARGINS.get(bm, 0)
                strategy = CHALLENGE_STRATEGIES.get(bm, "best")
                jockey_prices = {}
                for name, prices in all_jockey_prices.items():
                    if strategy == "avg":
                        derived = sum(prices) / len(prices)
                    elif strategy == "median":
                        s = sorted(prices)
                        mid_idx = len(s) // 2
                        derived = s[mid_idx] if len(s) % 2 else (s[mid_idx - 1] + s[mid_idx]) / 2
                    else:
                        derived = min(prices)
                    jockey_prices[name] = round(max(MIN_PRICE, min(MAX_PRICE, derived * (1 + margin))), 2)

                total_races_count = len(mtg["races"])
                min_rides = max(1, int(total_races_count * 0.3))
                filtered_jockey_prices = {
                    name: price for name, price in jockey_prices.items()
                    if len(all_jockey_prices.get(name, [])) >= min_rides
                }
                filtered_count = len(jockey_prices) - len(filtered_jockey_prices)
                if filtered_count > 0:
                    logger.info(
                        f"TAB jockey (race pages): {mtg['meeting_name']} "
                        f"filtered {filtered_count} jockeys with <{min_rides} rides "
                        f"({len(filtered_jockey_prices)} remain of {len(jockey_prices)})"
                    )

                if filtered_jockey_prices:
                    participants = []
                    for name, price in sorted(filtered_jockey_prices.items(), key=lambda x: x[1]):
                        p = {"name": name, "price": price}
                        if name in all_race_odds:
                            p["race_odds"] = all_race_odds[name]
                        participants.append(p)
                    market = {
                        "meeting_name": mtg["meeting_name"],
                        "type": "jockey",
                        "participants": participants,
                        "bookmaker": "TAB",
                        "total_races": total_races_count,
                        "races": [],
                    }
                    result.append(market)
                    logger.info(
                        f"TAB jockey (race pages): {mtg['meeting_name']} "
                        f"({len(participants)} participants, {total_races_count} races)"
                    )

        return result

    def close(self):
        pass
