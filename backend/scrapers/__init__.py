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


def _compute_venue_ratios(
    venue_data: Dict, pe_keys: List[str], bk_name: str
) -> Dict[str, float]:
    """Compute average (bookmaker_price / ladbrokes_price) per race number."""
    ratios = {}
    for race_num_str, runners_data in venue_data.items():
        try:
            race_num = int(race_num_str)
        except (ValueError, TypeError):
            continue
        race_ratios = []
        for horse_name_str, horse_prices in runners_data.items():
            if not isinstance(horse_prices, dict):
                continue
            lad_price = horse_prices.get("ladbrokes_au")
            bp = None
            for pk in pe_keys:
                bp = horse_prices.get(pk)
                if bp and bp > 0:
                    break
            if lad_price and lad_price > 0 and bp and bp > 0:
                r = bp / lad_price
                if 0.1 <= r <= 10.0:
                    race_ratios.append(r)
        if race_ratios:
            ratios[race_num] = sum(race_ratios) / len(race_ratios)
    return ratios


def _derive_markets_via_horses(
    markets: List[Dict], pe_prices: Dict, pe_keys: List[str], bookmaker_name: str
) -> List[Dict]:
    """Per-horse matching approach - the primary method."""
    result = []
    for m in markets:
        venue = m.get("meeting_name", "")
        pe_venue = _find_venue_key(pe_prices, venue)
        if not pe_venue:
            logger.info(
                f"{bookmaker_name}: venue '{venue}' not found in PuntersEdge "
                f"(available: {list(pe_prices.keys())[:10]})"
            )
            continue
        venue_data = pe_prices[pe_venue]
        pe_race_nums = set(venue_data.keys())
        races = m.get("races", [])
        lad_race_nums = set(r.get("race_number") for r in races)
        matching_race_nums = pe_race_nums & lad_race_nums

        logger.info(
            f"{bookmaker_name} @ '{venue}': PE races={sorted(pe_race_nums)}, "
            f"Lad races={sorted(lad_race_nums)}, matching={sorted(matching_race_nums)}"
        )

        jockey_prices = {}
        jockey_skipped = 0

        for race in races:
            race_num = race.get("race_number")
            pe_race = venue_data.get(race_num)
            if not pe_race:
                continue
            runners = race.get("runners", [])
            results_data = race.get("results", [])
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

        if not jockey_prices:
            # Log why — sample a runner to show mismatch
            for race in races[:2]:
                for runner in race.get("runners", [])[:3]:
                    jn = _extract_jockey(runner)
                    rn = runner.get("runner_number")
                    horse = ""
                    for res in race.get("results", []):
                        if res.get("runner_number") == rn:
                            horse = res.get("name", "").strip().lower()
                            break
                    pe_race = venue_data.get(race.get("race_number"), {})
                    in_pe = horse in pe_race if horse else False
                    pe_keys_found = list(pe_race.get(horse, {}).keys()) if horse and in_pe else []
                    logger.info(
                        f"  sample jockey='{jn}' rn={rn} horse='{horse}' "
                        f"in_PE={in_pe} PE_keys={pe_keys_found} "
                        f"bookmaker_keys={pe_keys}"
                    )
                    break
                break

        for p in m.get("participants", []):
            if p["name"] not in jockey_prices:
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
                    f"{jockey_skipped} participants had no horse match"
                )
    return result


def _derive_markets_via_ratios(
    markets: List[Dict], pe_prices: Dict, pe_keys: List[str], bookmaker_name: str
) -> List[Dict]:
    """Venue-ratio fallback: use ladbrokes price × venue ratio per race."""
    result = []
    for m in markets:
        venue = m.get("meeting_name", "")
        pe_venue = _find_venue_key(pe_prices, venue)
        if not pe_venue:
            continue
        venue_data = pe_prices[pe_venue]
        race_ratios = _compute_venue_ratios(venue_data, pe_keys, bookmaker_name)
        if not race_ratios:
            pe_race_nums = set(venue_data.keys())
            lad_races = set(r.get("race_number") for r in m.get("races", []))
            logger.info(
                f"{bookmaker_name} fallback @ '{venue}': no ratios computed. "
                f"PE races={sorted(pe_race_nums)} Lad races={sorted(lad_races)}"
            )
            continue
        races = m.get("races", [])
        jockey_prices = {}
        for race in races:
            race_num = race.get("race_number")
            ratio = race_ratios.get(race_num)
            if not ratio:
                continue
            runners = race.get("runners", [])
            for runner in runners:
                jn = _extract_jockey(runner)
                if not jn:
                    continue
                lad_price = runner.get("odds", {}).get("fixed_win", 0)
                if not lad_price or lad_price <= 0:
                    continue
                try:
                    derived_price = round(max(float(lad_price) * ratio, 1.50), 2)
                except (ValueError, TypeError):
                    continue
                if jn not in jockey_prices or derived_price < jockey_prices[jn]:
                    jockey_prices[jn] = derived_price
        if jockey_prices:
            market = dict(m)
            market["bookmaker"] = bookmaker_name
            market["participants"] = [
                {"name": name, "price": price}
                for name, price in sorted(jockey_prices.items(), key=lambda x: x[1])
            ]
            result.append(market)
    return result


def _derive_markets(bookmaker_name: str) -> List[Dict]:
    pe = PuntersEdgeScraper()
    if not pe.enabled:
        logger.warning(f"{bookmaker_name}: PuntersEdge scraper not enabled (API key missing?)")
        return []
    try:
        pe_prices = pe.fetch_prices()
    except Exception as e:
        logger.error(f"{bookmaker_name}: PuntersEdge fetch_prices failed: {e}")
        return []
    finally:
        pe.close()
    if not pe_prices:
        logger.warning(f"{bookmaker_name}: PuntersEdge returned no prices")
        return []

    pe_keys = PE_KEY_MAP.get(bookmaker_name)
    if not pe_keys:
        logger.warning(f"{bookmaker_name}: no PE_KEY_MAP entry")
        return []

    jockey, driver = _fetch_all_meetings()
    markets = jockey + driver
    if not markets:
        logger.warning(f"{bookmaker_name}: no Ladbrokes meetings available")
        return []

    logger.info(
        f"{bookmaker_name}: {len(pe_prices)} PuntersEdge venues, "
        f"{len(markets)} Ladbrokes meetings"
    )

    # Primary: per-horse matching
    result = _derive_markets_via_horses(markets, pe_prices, pe_keys, bookmaker_name)
    if result:
        logger.info(
            f"{bookmaker_name}: {len(result)} markets via per-horse matching"
        )
        return result

    # Fallback: venue-wide ratios
    logger.info(
        f"{bookmaker_name}: per-horse matching yielded no markets, "
        f"trying venue-ratio fallback"
    )
    result = _derive_markets_via_ratios(markets, pe_prices, pe_keys, bookmaker_name)
    if result:
        logger.info(
            f"{bookmaker_name}: {len(result)} markets via venue-ratio fallback"
        )
    else:
        logger.warning(f"{bookmaker_name}: no markets from any method")
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
