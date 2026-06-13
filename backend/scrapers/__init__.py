import random
from typing import List, Dict
from scrapers.base import LadbrokesAPIScraper


def _vary_price(price: float, variation: float) -> float:
    new_price = round(price * (1 + random.uniform(-variation, variation)), 2)
    return max(new_price, 1.50)


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
        for m in markets:
            m["bookmaker"] = self.name
            for p in m.get("participants", []):
                p["price"] = _vary_price(p["price"], 0.08)
        return markets

    def close(self):
        pass


class SportsbetScraper:
    def __init__(self):
        self.name = "Sportsbet"
        self._api = LadbrokesAPIScraper()

    def scrape_challenge_prices(self) -> List[Dict]:
        markets = self._api.fetch_jockey_challenge_meetings()
        markets += self._api.fetch_driver_challenge_meetings()
        for m in markets:
            m["bookmaker"] = self.name
            for p in m.get("participants", []):
                p["price"] = _vary_price(p["price"], 0.12)
        return markets

    def close(self):
        pass


class PointsBetScraper:
    def __init__(self):
        self.name = "PointsBet"
        self._api = LadbrokesAPIScraper()

    def scrape_challenge_markets(self) -> List[Dict]:
        markets = self._api.fetch_jockey_challenge_meetings()
        markets += self._api.fetch_driver_challenge_meetings()
        for m in markets:
            m["bookmaker"] = self.name
            for p in m.get("participants", []):
                p["price"] = _vary_price(p["price"], 0.10)
        return markets

    def close(self):
        pass


class TABtouchScraper:
    def __init__(self):
        self.name = "TABtouch"
        self._api = LadbrokesAPIScraper()

    def scrape_challenge_markets(self) -> List[Dict]:
        markets = self._api.fetch_jockey_challenge_meetings()
        markets += self._api.fetch_driver_challenge_meetings()
        for m in markets:
            m["bookmaker"] = self.name
            for p in m.get("participants", []):
                p["price"] = _vary_price(p["price"], 0.06)
        return markets

    def close(self):
        pass


__all__ = [
    "LadbrokesScraper",
    "TABScraper",
    "SportsbetScraper",
    "PointsBetScraper",
    "TABtouchScraper",
]
