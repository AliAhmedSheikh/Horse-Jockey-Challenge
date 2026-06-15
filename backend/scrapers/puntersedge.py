import logging
import os
import time
import threading
from typing import Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.puntersedge.online/v1"
BOOKMAKER_KEYS = ["tab", "pointsbetau", "sportsbet", "betright", "betr_au", "ladbrokes_au"]
CACHE_TTL = 120

_shared_cache = None
_shared_cache_time = 0
_shared_cache_lock = threading.Lock()


class PuntersEdgeScraper:
    def __init__(self):
        self.api_key = os.environ.get("PUNTERSEDGE_API_KEY", "")
        self._client = httpx.Client(timeout=20)
        self.enabled = bool(self.api_key)

    def fetch_prices(self) -> Dict[str, Dict[int, Dict[str, Dict[str, float]]]]:
        if not self.enabled:
            return {}

        global _shared_cache, _shared_cache_time
        now = time.time()
        with _shared_cache_lock:
            if _shared_cache is not None and now - _shared_cache_time < CACHE_TTL:
                return _shared_cache

        try:
            r = self._client.get(
                f"{API_BASE}/racing/next-to-go",
                params={
                    "num_races": 50,
                    "categories": "horse,harness",
                    "bookmakers": ",".join(BOOKMAKER_KEYS),
                },
                headers={"X-API-Key": self.api_key},
            )
            if r.status_code != 200:
                logger.warning(f"PuntersEdge API returned {r.status_code}")
                return {}

            races = r.json()
            result = {}
            for race in races:
                venue = (race.get("venue") or "").strip().lower()
                race_num = race.get("race_number")
                if not venue or not race_num:
                    continue
                if venue not in result:
                    result[venue] = {}
                result[venue][race_num] = {}
                for runner in race.get("runners", []):
                    horse_name = (runner.get("name") or "").strip().lower()
                    if not horse_name:
                        continue
                    prices = {}
                    for bk in runner.get("bookmakers", []):
                        key = bk.get("key", "")
                        win_price = bk.get("win_price")
                        if key and win_price and win_price > 0:
                            prices[key] = win_price
                    if prices:
                        result[venue][race_num][horse_name] = prices

            with _shared_cache_lock:
                _shared_cache = result
                _shared_cache_time = time.time()
            logger.info(
                f"PuntersEdge: got {sum(len(r) for v in result.values() for r in v.values())} "
                f"runner prices across {len(result)} venues"
            )
            return result
        except Exception as e:
            logger.warning(f"PuntersEdge API error: {e}")
            return {}

    def fetch_venue_ratios(self) -> Dict[str, Dict[str, float]]:
        """Returns {venue: {bookmaker_key: price_ratio_vs_ladbrokes}}.
        
        Computes average price ratio per bookmaker vs Ladbrokes for each venue.
        A ratio > 1.0 means the bookmaker prices higher than Ladbrokes at this venue.
        Returns empty dict if no data or Ladbrokes baseline unavailable.
        """
        prices = self.fetch_prices()
        if not prices:
            return {}

        result = {}
        for venue, races in prices.items():
            bk_sum = {}
            bk_count = {}
            for race_num, horses in races.items():
                for horse, bks in horses.items():
                    lad_price = bks.get("ladbrokes_au")
                    if not lad_price or lad_price <= 0:
                        continue
                    for bk_key, bk_price in bks.items():
                        if bk_key == "ladbrokes_au" or not bk_price or bk_price <= 0:
                            continue
                        ratio = bk_price / lad_price
                        if bk_key not in bk_sum:
                            bk_sum[bk_key] = 0.0
                            bk_count[bk_key] = 0
                        bk_sum[bk_key] += ratio
                        bk_count[bk_key] += 1

            if bk_sum:
                result[venue] = {
                    bk: round(bk_sum[bk] / bk_count[bk], 4)
                    for bk in bk_sum
                }
        return result

    def close(self):
        self._client.close()
