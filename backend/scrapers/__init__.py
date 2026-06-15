import logging
import threading
from typing import List, Dict, Optional

from scrapers.base import LadbrokesAPIScraper
from scrapers.tab import TABAPIScraper
from scrapers.sportsbet import SportsbetAPIScraper
from scrapers.pointsbet import PointsBetAPIScraper
from scrapers.tabtouch import TABtouchAPIScraper

logger = logging.getLogger(__name__)


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
        self._api = TABAPIScraper()

    def scrape_jockey_challenges(self) -> List[Dict]:
        return self._api.fetch_jockey_challenge_meetings()

    def scrape_driver_challenges(self) -> List[Dict]:
        return self._api.fetch_driver_challenge_meetings()

    def close(self):
        pass


class SportsbetScraper:
    def __init__(self):
        self.name = "Sportsbet"
        self._api = SportsbetAPIScraper()

    def scrape_jockey_challenges(self) -> List[Dict]:
        return self._api.fetch_jockey_challenge_meetings()

    def scrape_driver_challenges(self) -> List[Dict]:
        return self._api.fetch_driver_challenge_meetings()

    def close(self):
        pass


class PointsBetScraper:
    def __init__(self):
        self.name = "PointsBet"
        self._api = PointsBetAPIScraper()

    def scrape_jockey_challenges(self) -> List[Dict]:
        return self._api.fetch_jockey_challenge_meetings()

    def scrape_driver_challenges(self) -> List[Dict]:
        return self._api.fetch_driver_challenge_meetings()

    def close(self):
        pass


class TABtouchScraper:
    def __init__(self):
        self.name = "TABtouch"
        self._api = TABtouchAPIScraper()

    def scrape_jockey_challenges(self) -> List[Dict]:
        return self._api.fetch_jockey_challenge_meetings()

    def scrape_driver_challenges(self) -> List[Dict]:
        return self._api.fetch_driver_challenge_meetings()

    def close(self):
        pass


__all__ = [
    "LadbrokesScraper",
    "TABScraper",
    "SportsbetScraper",
    "PointsBetScraper",
    "TABtouchScraper",
]
