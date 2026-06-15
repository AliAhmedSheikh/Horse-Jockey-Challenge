import logging
import re
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
import httpx
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

BASE = "https://www.tabtouch.com.au"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-AU,en;q=0.9",
}

_race_cache = {}
_race_cache_lock = threading.Lock()
_shared_client = None
_client_lock = threading.Lock()
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


def _fetch_race_model(meeting_code: str, date_str: str, race_num: int) -> dict:
    cache_key = f"{meeting_code}_{race_num}"
    now = time.time()
    with _race_cache_lock:
        if cache_key in _race_cache:
            entry = _race_cache[cache_key]
            if isinstance(entry, tuple) and now - entry[1] < CACHE_TTL:
                return entry[0]

    url = f"{BASE}/racing/{date_str}/{meeting_code.lower()}/{race_num}"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"TABtouch race page {url} returned {r.status_code}")
            return None

        pattern = re.compile(r'var model = ({.*?});\s*\n', re.DOTALL)
        m = pattern.search(r.text)
        if not m:
            logger.warning(f"TABtouch race {meeting_code} R{race_num}: model pattern not found in response")
            return None

        data = json.loads(m.group(1))
        with _race_cache_lock:
            _race_cache[cache_key] = (data, time.time())
        return data
    except Exception as e:
        logger.warning(f"TABtouch race {meeting_code} R{race_num}: {e}")
        return None


def _get_todays_meetings() -> List[Dict]:
    """Get all horse and harness meetings from TABtouch."""
    url = f"{BASE}/api/raceinfo/nextraces"
    try:
        client = _get_client()
        r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"TABtouch nextraces returned {r.status_code}")
            return []

        races = r.json()
        meetings = {}
        for race in races:
                # Skip dogs
                if race.get("isDogs"):
                    continue
                # Determine type
                if race.get("isRaces"):
                    mtype = "jockey"
                elif race.get("isTrots"):
                    mtype = "driver"
                else:
                    continue

                meeting_id = race.get("meetingId", "").lower()
                if not meeting_id:
                    continue

                ground = race.get("groundDescription", "")
                meeting_name = ground.split(",")[0].strip() if "," in ground else ground

                url_path = race.get("url", "")
                try:
                    race_num = int(url_path.rsplit("/", 1)[-1])
                except (ValueError, IndexError):
                    race_num = 0

                if meeting_id not in meetings:
                    meetings[meeting_id] = {
                        "meeting_name": meeting_name,
                        "meeting_id": meeting_id.upper(),
                        "type": mtype,
                        "races": [],
                        "seen": set(),
                    }
                elif meetings[meeting_id]["type"] != mtype:
                    # If same meeting has both horse and harness (shouldn't happen), keep first
                    pass

                if race_num and race_num not in meetings[meeting_id]["seen"]:
                    meetings[meeting_id]["races"].append({
                        "race_number": race_num,
                        "url": url_path,
                    })
                    meetings[meeting_id]["seen"].add(race_num)

        result = []
        for mid, info in meetings.items():
            info["races"].sort(key=lambda x: x["race_number"])
            result.append(info)
        return result
    except Exception as e:
        logger.warning(f"TABtouch nextraces error: {e}")
        return []


class TABtouchScraper:
    def __init__(self):
        self.name = "TABtouch"

    def _scrape(self, challenge_type: str) -> List[Dict]:
        from time_utils import today_aus
        date_str = today_aus()

        meetings = _get_todays_meetings()
        if not meetings:
            return []

        result = []
        for mtg in meetings:
            if mtg["type"] != challenge_type:
                continue

            meeting_id = mtg["meeting_id"]
            jockey_prices = {}

            def _process_race(mid, ds, ri):
                rn = ri["race_number"]
                model = _fetch_race_model(mid, ds, rn)
                if not model:
                    return []
                result = []
                legs = model.get("pool", {}).get("legs", [])
                for leg in legs:
                    if leg.get("raceNumber") != rn:
                        continue
                    for starter in leg.get("starters", []):
                        if starter.get("scratched"):
                            continue
                        rider = (starter.get("rider") or "").strip()
                        if not rider or rider.lower() in ("unknown", "n/a", "not declared", ""):
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
                return result

            races = mtg["races"]
            if races:
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = {ex.submit(_process_race, meeting_id, date_str, ri): ri for ri in races}
                    for f in as_completed(futs):
                        for rc, price in f.result():
                            if rc not in jockey_prices or price < jockey_prices[rc]:
                                jockey_prices[rc] = price

            if jockey_prices:
                participants = [
                    {"name": name, "price": price}
                    for name, price in sorted(jockey_prices.items(), key=lambda x: x[1])
                ]
                market = {
                    "meeting_name": mtg["meeting_name"],
                    "type": challenge_type,
                    "participants": participants,
                    "bookmaker": "TABtouch",
                    "total_races": len(mtg["races"]),
                    "races": [],
                }
                result.append(market)
                logger.info(
                    f"TABtouch {challenge_type}: {mtg['meeting_name']} "
                    f"({len(participants)} participants, {len(mtg['races'])} races)"
                )

        return result

    def scrape_jockey_challenges(self) -> List[Dict]:
        return self._scrape("jockey")

    def scrape_driver_challenges(self) -> List[Dict]:
        return self._scrape("driver")

    def close(self):
        pass


