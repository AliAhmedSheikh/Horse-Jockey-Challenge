import logging
import re
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import httpx
import urllib3
from bs4 import BeautifulSoup
from utils import MIN_PRICE

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BASE = "https://www.tabtouch.com.au"

_NON_AU_PATTERN = re.compile(r'\s+-\s+\w{2,4}\s*$')
_JOCKEY_CHALLENGE_RE = re.compile(r'(.+?)\s+Jockey Challenge\s+3,2,1\s+Points', re.IGNORECASE)
_DRIVER_WINS_RE = re.compile(r'Driver Wins\s*-\s*(.+?)\s*\((.+?)\)', re.IGNORECASE)
_GLOBALS_PATTERN = re.compile(r'globals\.fixedOddsBettingData\s*=\s*({.*?});\s*\n', re.DOTALL)
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
CACHE_TTL = 120


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
            if isinstance(entry, tuple) and now - entry[1] < CACHE_TTL:
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
            if isinstance(entry, tuple) and now - entry[1] < CACHE_TTL:
                return entry[0]

    url = f"{BASE}/api/fixed-odds/refresh/jockeychallenge/{date_str}/event-{event_id}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"TABtouch jockey challenge event {event_id} returned {r.status_code}")
            return None

        data = r.json()
        if data.get("responseCode") != "Success":
            code = data.get("responseCode", "unknown")
            if code == "FixedOddsEventClosed":
                logger.info(f"TABtouch jockey challenge event {event_id}: closed, will use HTML fallback")
            else:
                logger.warning(f"TABtouch jockey challenge event {event_id}: {code} - {data.get('responseMessage', '')}")
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
            if isinstance(entry, tuple) and now - entry[1] < CACHE_TTL:
                return entry[0]

    url = f"{BASE}/racing/jockey-challenge/{date_str}/event-{event_id}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"TABtouch event page {url} returned {r.status_code}")
            return None

        m = _GLOBALS_PATTERN.search(r.text)
        if not m:
            logger.warning(f"TABtouch event {event_id}: fixedOddsBettingData not found")
            return None

        data = json.loads(m.group(1))
        with _event_cache_lock:
            _event_cache[cache_key] = (data, time.time())
        return data
    except Exception as e:
        logger.warning(f"TABtouch event page {event_id} error: {e}")
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
            logger.warning(f"TABtouch racing page returned {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table')
        if not table:
            logger.warning("TABtouch racing page: no table found")
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

            if _NON_AU_PATTERN.search(meeting_name):
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


class TABtouchScraper:
    def __init__(self):
        self.name = "TABtouch"

    def _scrape(self, challenge_type: str) -> List[Dict]:
        if challenge_type == "jockey":
            return self._scrape_jockey_challenges()
        elif challenge_type == "driver":
            return self._scrape_driver_challenges()
        return []

    def _scrape_jockey_challenges(self) -> List[Dict]:
        """Scrape actual jockey challenge markets from TABtouch dedicated API."""
        from time_utils import today_aus
        date_str = today_aus()

        events = _get_jockey_challenge_events(date_str)
        if not events:
            logger.info("TABtouch jockey challenge: no events found on listing page")
            return []

        meetings = _get_todays_meetings()
        meeting_race_counts = {}
        for mtg in meetings:
            if mtg["type"] == "jockey":
                meeting_race_counts[mtg["meeting_name"]] = len(mtg["races"])

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

            if not data.get("isOpen") and data.get("isChallengeResulted"):
                logger.info(f"TABtouch jockey challenge: {meeting_name} already resulted, skipping")
                continue

            propositions = data.get("propositions", [])
            if not propositions:
                continue

            participants = []
            for prop in propositions:
                if prop.get("showRacingStatusText") or not prop.get("showBetButton"):
                    continue
                name = (prop.get("name") or "").strip()
                if not name:
                    continue
                try:
                    price = float(prop.get("winReturn", 0) or 0)
                except (ValueError, TypeError):
                    continue
                if price > 0:
                    participants.append({"name": name, "price": price})

            if not participants:
                continue

            participants.sort(key=lambda x: x["price"])
            total_races = meeting_race_counts.get(meeting_name, 0)
            market = {
                "meeting_name": meeting_name,
                "type": "jockey",
                "participants": participants,
                "bookmaker": "TABtouch",
                "total_races": total_races,
                "races": [],
            }
            result.append(market)
            logger.info(
                f"TABtouch jockey: {meeting_name} "
                f"({len(participants)} participants, {total_races} races)"
            )

        return result

    def _scrape_driver_challenges(self) -> List[Dict]:
        """Scrape driver challenges from TABtouch racing pages (derived from horse win odds)."""
        from time_utils import today_aus
        date_str = today_aus()

        meetings = _get_todays_meetings()
        if not meetings:
            return []

        result = []
        for mtg in meetings:
            if mtg["type"] != "driver":
                continue

            meeting_id = mtg["meeting_id"]
            driver_prices = {}

            def _process_race(mid, ds, ri):
                rn = ri["race_number"]
                url = f"{BASE}/racing/{ds}/{mid.lower()}/{rn}"
                try:
                    client = _get_client()
                    r = client.get(url)
                    if r.status_code != 200:
                        return []

                    pattern = re.compile(r'var model = ({.*?});\s*\n', re.DOTALL)
                    m = pattern.search(r.text)
                    if not m:
                        return []

                    model = json.loads(m.group(1))
                    result = []
                    legs = model.get("pool", {}).get("legs", [])
                    for leg in legs:
                        if leg.get("raceNumber") != rn:
                            continue
                        for starter in leg.get("starters", []):
                            if starter.get("scratched"):
                                continue
                            rider = (starter.get("rider") or "").strip()
                            if not rider or rider.lower() in ("unknown", "n/a", "not declared", "n.r", "nr", "not riding", "scratching", ""):
                                continue
                            rc = re.sub(r'\s*\(.*?\)\s*$', '', rider).strip()
                            if not rc:
                                continue
                            try:
                                price = float(starter.get("winDiv", 0) or 0)
                            except (ValueError, TypeError):
                                continue
                            if price > 0:
                                result.append((rc, price))
                            else:
                                result.append((rc, MIN_PRICE))
                    return result
                except Exception as e:
                    logger.warning(f"TABtouch driver race {mid} R{rn}: {e}")
                    return []

            races = mtg["races"]
            if races:
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = {ex.submit(_process_race, meeting_id, date_str, ri): ri for ri in races}
                    for f in as_completed(futs):
                        for rc, price in f.result():
                            if rc not in driver_prices or price < driver_prices[rc]:
                                driver_prices[rc] = price

            if driver_prices:
                participants = [
                    {"name": name, "price": price}
                    for name, price in sorted(driver_prices.items(), key=lambda x: x[1])
                ]
                market = {
                    "meeting_name": mtg["meeting_name"],
                    "type": "driver",
                    "participants": participants,
                    "bookmaker": "TABtouch",
                    "total_races": len(mtg["races"]),
                    "races": [],
                }
                result.append(market)
                logger.info(
                    f"TABtouch driver: {mtg['meeting_name']} "
                    f"({len(participants)} participants, {len(mtg['races'])} races)"
                )

        return result

    def scrape_jockey_challenges(self) -> List[Dict]:
        return self._scrape("jockey")

    def scrape_driver_challenges(self) -> List[Dict]:
        return self._scrape("driver")

    def close(self):
        pass
