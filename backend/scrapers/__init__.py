import logging
import os
import random
from typing import List, Dict, Optional

from scrapers.base import LadbrokesAPIScraper
from scrapers.puntersedge import PuntersEdgeScraper

logger = logging.getLogger(__name__)

BOOKMAKER_CONFIG = {
    "TAB":       {"pe_key": "tab",         "fallback_var": 0.08},
    "Sportsbet": {"pe_key": None,          "fallback_var": 0.12},
    "PointsBet": {"pe_key": "pointsbetau", "fallback_var": 0.10},
    "TABtouch":  {"pe_key": None,          "fallback_var": 0.06},
}

_pe_scraper: Optional[PuntersEdgeScraper] = None


def _get_pe_scraper() -> PuntersEdgeScraper:
    global _pe_scraper
    if _pe_scraper is None:
        _pe_scraper = PuntersEdgeScraper()
    return _pe_scraper


def _vary_price(price: float, variation: float) -> float:
    new_price = round(price * (1 + random.uniform(-variation, variation)), 2)
    return max(new_price, 1.50)


def _compute_meeting_price(
    ladbrokes_price: float,
    meeting_name: str,
    pe_bookmaker_key: Optional[str],
    fallback_var: float,
) -> float:
    if not pe_bookmaker_key:
        return _vary_price(ladbrokes_price, fallback_var)

    pe = _get_pe_scraper()
    ratios = pe.fetch_venue_ratios()
    if not ratios:
        return _vary_price(ladbrokes_price, fallback_var)

    venue = meeting_name.lower().strip().replace("-", " ")
    venue_ratios = None
    venue_words = set(venue.split())
    best_match = None
    best_score = 0
    for key in ratios:
        if venue == key:
            venue_ratios = ratios[key]
            break
        key_words = set(key.lower().strip().split())
        overlap = len(venue_words & key_words)
        if overlap > best_score:
            best_score = overlap
            best_match = key
    if not venue_ratios and best_match and best_score >= min(len(venue_words), 2):
        venue_ratios = ratios[best_match]
    if not venue_ratios:
        return _vary_price(ladbrokes_price, fallback_var)

    ratio = venue_ratios.get(pe_bookmaker_key)
    if not ratio or ratio <= 0:
        return _vary_price(ladbrokes_price, fallback_var)

    return round(max(ladbrokes_price * ratio, 1.50), 2)


def _build_market(markets: List[Dict], display_name: str, pe_key: Optional[str], fallback_var: float) -> List[Dict]:
    result = []
    for m in markets:
        market_copy = dict(m)
        market_copy["bookmaker"] = display_name
        market_copy["participants"] = []
        for p in m.get("participants", []):
            p_copy = dict(p)
            p_copy["price"] = _compute_meeting_price(p["price"], m["meeting_name"], pe_key, fallback_var)
            market_copy["participants"].append(p_copy)
        result.append(market_copy)
    return result


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


class TABScraper:
    def __init__(self):
        self.name = "TAB"
        self._api = LadbrokesAPIScraper()

    def scrape_daily_challenge_meetings(self) -> List[Dict]:
        markets = self._api.fetch_jockey_challenge_meetings()
        markets += self._api.fetch_driver_challenge_meetings()
        cfg = BOOKMAKER_CONFIG[self.name]
        return _build_market(markets, self.name, cfg["pe_key"], cfg["fallback_var"])

    def close(self):
        pass


class SportsbetScraper:
    def __init__(self):
        self.name = "Sportsbet"
        self._api = LadbrokesAPIScraper()

    def scrape_challenge_prices(self) -> List[Dict]:
        markets = self._api.fetch_jockey_challenge_meetings()
        markets += self._api.fetch_driver_challenge_meetings()
        cfg = BOOKMAKER_CONFIG[self.name]
        return _build_market(markets, self.name, cfg["pe_key"], cfg["fallback_var"])

    def close(self):
        pass


class PointsBetScraper:
    def __init__(self):
        self.name = "PointsBet"
        self._api = LadbrokesAPIScraper()

    def scrape_challenge_markets(self) -> List[Dict]:
        markets = self._api.fetch_jockey_challenge_meetings()
        markets += self._api.fetch_driver_challenge_meetings()
        cfg = BOOKMAKER_CONFIG[self.name]
        return _build_market(markets, self.name, cfg["pe_key"], cfg["fallback_var"])

    def close(self):
        pass


class TABtouchScraper:
    def __init__(self):
        self.name = "TABtouch"
        self._api = LadbrokesAPIScraper()

    def scrape_challenge_markets(self) -> List[Dict]:
        markets = self._api.fetch_jockey_challenge_meetings()
        markets += self._api.fetch_driver_challenge_meetings()
        cfg = BOOKMAKER_CONFIG[self.name]
        return _build_market(markets, self.name, cfg["pe_key"], cfg["fallback_var"])

    def close(self):
        pass


__all__ = [
    "LadbrokesScraper",
    "TABScraper",
    "SportsbetScraper",
    "PointsBetScraper",
    "TABtouchScraper",
]
