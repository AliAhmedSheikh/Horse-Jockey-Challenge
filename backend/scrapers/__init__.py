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


def _extract_jockey(runner: Dict) -> str:
    for field in ("jockey", "rider", "jockey_name", "driver", "driver_name"):
        val = runner.get(field)
        if val and val.strip():
            return val.strip()
    return ""


def _find_venue_key(prices: Dict, venue: str) -> str:
    v = venue.lower().strip().replace("-", " ")
    if v in prices:
        return v
    vn = v.replace(" ", "")
    if vn in prices:
        return vn
    for k in prices:
        if v in k or k in v:
            return k
    return ""


def _derive_markets(bookmaker_name: str) -> List[Dict]:
    pe = PuntersEdgeScraper()
    if not pe.enabled:
        return []
    try:
        pe_prices = pe.fetch_prices()
    finally:
        pe.close()
    if not pe_prices:
        return []

    pe_keys = PE_KEY_MAP.get(bookmaker_name)
    if not pe_keys:
        return []

    jockey, driver = _fetch_all_meetings()
    markets = jockey + driver
    result = []

    for m in markets:
        venue = m.get("meeting_name", "")
        pe_venue = _find_venue_key(pe_prices, venue)
        if not pe_venue:
            continue
        venue_data = pe_prices[pe_venue]
        races = m.get("races", [])

        # For each jockey participant, find the best price across all races
        # by matching their horse via runner_number in Ladbrokes race data
        jockey_prices = {}
        jockey_skipped = 0

        for race in races:
            race_num = race.get("race_number")
            pe_race = venue_data.get(race_num)
            if not pe_race:
                continue

            runners = race.get("runners", [])
            results_data = race.get("results", [])

            # Build runner_number → horse_name from results
            rn_to_horse = {}
            for res in results_data:
                rn = res.get("runner_number")
                name = res.get("name", "").strip().lower()
                if rn is not None and name:
                    rn_to_horse[rn] = name

            for runner in runners:
                jn = _extract_jockey(runner)
                if not jn:
                    continue
                rn = runner.get("runner_number")
                if rn is None:
                    continue
                horse = rn_to_horse.get(rn)
                if not horse:
                    continue

                horse_prices = pe_race.get(horse)
                if not horse_prices:
                    continue

                for pk in pe_keys:
                    bp = horse_prices.get(pk)
                    if bp and bp > 0:
                        price = round(max(bp, 1.50), 2)
                        if jn not in jockey_prices or price < jockey_prices[jn]:
                            jockey_prices[jn] = price
                        break

        # Also try participants from the Ladbrokes market data that have no race match
        for p in m.get("participants", []):
            pname = p["name"]
            if pname not in jockey_prices:
                jockey_skipped += 1

        if jockey_prices:
            market = dict(m)
            market["bookmaker"] = bookmaker_name
            market["participants"] = [
                {"name": name, "price": price}
                for name, price in sorted(jockey_prices.items(), key=lambda x: x[1])
            ]
            result.append(market)
            if jockey_skipped:
                logger.info(
                    f"{bookmaker_name} @ {venue}: {len(jockey_prices)} jockeys matched, "
                    f"{jockey_skipped} Ladbrokes participants had no horse match"
                )

    if not result:
        logger.warning(
            f"{bookmaker_name}: no markets derived from PuntersEdge horse-level data"
        )
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
