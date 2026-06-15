import logging
from typing import List, Dict

from scrapers.base import LadbrokesAPIScraper, _fetch_all_meetings
from scrapers.puntersedge import PuntersEdgeScraper
from scrapers.tabtouch import TABtouchScraper

logger = logging.getLogger(__name__)

# Map bookmaker names to PuntersEdge API keys (first found wins)
PE_KEY_MAP = {
    "TAB": ["tab"],
    "PointsBet": ["pointsbetau"],
    "Sportsbet": ["sportsbet", "sportsbet_au"],
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
    pe_keys = PE_KEY_MAP.get(bookmaker_name)
    if not pe_keys:
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
        # Try each PE key variant, use the first one that has data
        ratio = None
        for pk in pe_keys:
            r = vr.get(pk)
            if r and r > 0:
                ratio = r
                break
        if not ratio:
            continue
        market = dict(m)
        market["bookmaker"] = bookmaker_name
        market["participants"] = []
        for p in m.get("participants", []):
            raw = p["price"] * ratio
            derived = round(max(raw, 1.50), 2)
            if derived <= 1.51 and raw < 1.50:
                logger.warning(
                    f"{bookmaker_name}: price floor applied for {p['name']} "
                    f"(raw={raw:.2f}, ratio={ratio})"
                )
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
    """Sportsbet prices derived via PuntersEdge venue ratios."""
    def __init__(self):
        self.name = "Sportsbet"

    def scrape_jockey_challenges(self) -> List[Dict]:
        return _derive_markets("Sportsbet")

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
