import logging
from typing import List, Dict

from scrapers.base import LadbrokesAPIScraper, _fetch_all_meetings
from scrapers.puntersedge import PuntersEdgeScraper

logger = logging.getLogger(__name__)

PE_KEY_MAP = {
    "TAB": "tab",
    "PointsBet": "pointsbetau",
}


class LadbrokesScraper:
    def __init__(self):
        self.name = "Ladbrokes"
        self._api = LadbrokesAPIScraper()

    def scrape_jockey_challenges(self) -> List[Dict]:
        return self._api.fetch_jockey_challenge_meetings()

    def scrape_driver_challenges(self) -> List[Dict]:
        return self._api.fetch_driver_challenge_meetings()

    def close(self):
        pass


def _derive_markets(bookmaker_name: str) -> List[Dict]:
    pe = PuntersEdgeScraper()
    if not pe.enabled:
        return []
    try:
        ratios = pe.fetch_venue_ratios()
    finally:
        pe.close()
    if not ratios:
        return []
    pe_key = PE_KEY_MAP.get(bookmaker_name)
    if not pe_key:
        return []

    jockey, driver = _fetch_all_meetings()
    markets = jockey + driver
    result = []
    for m in markets:
        venue = m.get("meeting_name", "").lower().strip().replace("-", " ")
        vr = ratios.get(venue)
        if not vr:
            vr = ratios.get(venue.replace(" ", ""))
        if not vr:
            vr = ratios.get(" ".join(w for w in venue.split() if w))
        if not vr:
            for k, v in ratios.items():
                if venue in k or k in venue:
                    vr = v
                    break
        if not vr:
            continue
        ratio = vr.get(pe_key)
        if not ratio or ratio <= 0:
            continue
        market = dict(m)
        market["bookmaker"] = bookmaker_name
        market["participants"] = []
        for p in m.get("participants", []):
            derived = round(max(p["price"] * ratio, 1.50), 2)
            market["participants"].append({"name": p["name"], "price": derived})
        result.append(market)
    return result


class TABScraper:
    def __init__(self):
        self.name = "TAB"

    def scrape_jockey_challenges(self) -> List[Dict]:
        return _derive_markets("TAB")

    def scrape_driver_challenges(self) -> List[Dict]:
        return []

    def close(self):
        pass


class PointsBetScraper:
    def __init__(self):
        self.name = "PointsBet"

    def scrape_jockey_challenges(self) -> List[Dict]:
        return _derive_markets("PointsBet")

    def scrape_driver_challenges(self) -> List[Dict]:
        return []

    def close(self):
        pass


class SportsbetScraper:
    def __init__(self):
        self.name = "Sportsbet"

    def scrape_jockey_challenges(self) -> List[Dict]:
        return []

    def scrape_driver_challenges(self) -> List[Dict]:
        return []

    def close(self):
        pass


class TABtouchScraper:
    def __init__(self):
        self.name = "TABtouch"

    def scrape_jockey_challenges(self) -> List[Dict]:
        return []

    def scrape_driver_challenges(self) -> List[Dict]:
        return []

    def close(self):
        pass


__all__ = [
    "LadbrokesScraper",
    "TABScraper",
    "SportsbetScraper",
    "PointsBetScraper",
    "TABtouchScraper",
]
