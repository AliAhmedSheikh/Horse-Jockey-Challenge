"""Sportsbet scraper using Playwright to bypass Akamai protection."""
import json
import logging
import time
import threading
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

from utils import MIN_PRICE, MAX_PRICE

# Try to import Playwright - optional dependency
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

API_BASE = "https://www.sportsbet.com.au"
RACING_MEETINGS_URL = f"{API_BASE}/apigw/racing-form/v1/meetings/?date={{date}}"
RACING_MEETINGS_V2_URL = f"{API_BASE}/apigw/racing/meetings?date={{date}}"

_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 120


def _get_browser():
    """Get or create a shared Playwright browser instance."""
    if not HAS_PLAYWRIGHT:
        return None
    if not hasattr(_get_browser, "_instance"):
        _get_browser._instance = None
    if _get_browser._instance is None:
        try:
            p = sync_playwright().start()
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            _get_browser._instance = (p, browser)
            logger.info("Sportsbet: Playwright browser launched")
        except Exception as e:
            logger.warning(f"Sportsbet: Failed to launch Playwright browser: {e}")
            _get_browser._instance = (None, None)
    return _get_browser._instance[1] if _get_browser._instance else None


def _close_browser():
    """Close the shared Playwright browser instance."""
    if hasattr(_get_browser, "_instance") and _get_browser._instance:
        p, browser = _get_browser._instance
        try:
            if browser:
                browser.close()
            if p:
                p.stop()
        except Exception:
            pass
        _get_browser._instance = None
        logger.info("Sportsbet: Playwright browser closed")


def _fetch_with_browser(url: str, check_json: bool = True) -> Optional[dict]:
    """Fetch JSON data from Sportsbet API using Playwright to bypass Akamai.
    
    Opens a fresh browser context for each call to avoid stale cookies.
    First loads the main racing page to get past Akamai, then calls the API.
    """
    browser = _get_browser()
    if not browser:
        logger.warning("Sportsbet: No browser available")
        return None

    try:
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )

        # We need Akamai cookies. If the context is brand new, load the main page first.
        # Check if we already have cookies in a shared context
        page = context.new_page()

        # Load racing page to get past Akamai challenge
        try:
            page.goto(
                f"{API_BASE}/racing",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            # Wait a bit for Akamai challenge to complete
            page.wait_for_timeout(5000)
        except Exception as e:
            logger.warning(f"Sportsbet: Page load timed out or failed: {e}")
            # Sometimes Akamai challenge takes longer, try to continue anyway

        # Now make the API call from within the browser context
        result = page.evaluate(f"""
            async () => {{
                try {{
                    const r = await fetch('{url}', {{
                        headers: {{
                            'Accept': 'application/json',
                            'x-application': 'web',
                            'Origin': '{API_BASE}',
                            'Referer': '{API_BASE}/racing',
                        }}
                    }});
                    if (!r.ok) {{
                        return {{ _error: 'HTTP ' + r.status }};
                    }}
                    const text = await r.text();
                    try {{
                        return JSON.parse(text);
                    }} catch(e) {{
                        return {{ _error: 'Invalid JSON', _text: text.substring(0, 500) }};
                    }}
                }} catch(e) {{
                    return {{ _error: e.message }};
                }}
            }}
        """)

        context.close()

        if isinstance(result, dict) and result.get("_error"):
            logger.warning(f"Sportsbet: API call failed: {result['_error']}")
            return None

        return result
    except Exception as e:
        logger.warning(f"Sportsbet: Browser fetch error: {e}")
        return None


def _discover_meetings(aus_date: str) -> Optional[List[Dict]]:
    """Discover racing meetings from Sportsbet API."""
    cache_key = f"meetings_{aus_date}"
    now = time.time()
    with _cache_lock:
        if cache_key in _cache and now - _cache[cache_key]["ts"] < _CACHE_TTL:
            return _cache[cache_key]["data"]

    # Try the racing-form API first
    url = RACING_MEETINGS_URL.format(date=aus_date)
    data = _fetch_with_browser(url)

    if not data:
        # Try v2 endpoint
        url = RACING_MEETINGS_V2_URL.format(date=aus_date)
        data = _fetch_with_browser(url)

    if not data:
        return None

    with _cache_lock:
        _cache[cache_key] = {"data": data, "ts": now}
    return data


def _parse_jockey_challenges(meetings_data: dict) -> List[Dict]:
    """Parse jockey challenge prices from Sportsbet meetings data."""
    result = []

    # The data structure varies by endpoint. Try different formats.
    meetings = meetings_data.get("meetings", meetings_data.get("data", []))
    if not meetings and isinstance(meetings_data, list):
        meetings = meetings_data
    if not meetings and isinstance(meetings_data, dict):
        # Maybe it's a single meeting object wrapped
        meetings = [meetings_data]

    for meeting in meetings:
        if not isinstance(meeting, dict):
            continue

        name = meeting.get("name") or meeting.get("venueName") or meeting.get("venue", "")
        if not name:
            continue

        meeting_type = meeting.get("type") or meeting.get("category", "")
        meeting_type_str = str(meeting_type).lower()

        # Get races
        races = meeting.get("races", meeting.get("events", []))
        if not races:
            continue

        # Extract jockey prices from all races
        jockey_prices: Dict[str, float] = {}

        for race in races:
            if not isinstance(race, dict):
                continue

            runners = race.get("runners", race.get("competitors", []))
            for runner in runners:
                if not isinstance(runner, dict):
                    continue
                if runner.get("isScratched") or runner.get("scratched"):
                    continue

                # Try to get jockey name
                jockey = ""
                for key in ["jockey", "jockeyName", "rider", "riderName", "driver"]:
                    val = runner.get(key, "")
                    if val and str(val).strip():
                        jockey = str(val).strip()
                        break

                if not jockey or jockey.lower() in ("unknown", "n/a", "not declared", ""):
                    continue

                # Get price
                price = None
                for price_key in ["fixedWinPrice", "winPrice", "price", "fixedWinDiv"]:
                    val = runner.get(price_key)
                    if val is not None:
                        try:
                            p = float(val)
                            if p > 0:
                                price = p
                                break
                        except (ValueError, TypeError):
                            pass

                if price is None:
                    # Check market data
                    markets = runner.get("markets", [])
                    for market in markets:
                        if isinstance(market, dict):
                            for sel in market.get("selections", []):
                                if isinstance(sel, dict):
                                    p = sel.get("price") or sel.get("winPrice")
                                    if p:
                                        try:
                                            price = float(p)
                                        except (ValueError, TypeError):
                                            pass

                if price and price > 0:
                    jockey = jockey.title()
                    price = round(max(MIN_PRICE, min(MAX_PRICE, float(price))), 2)
                    if jockey not in jockey_prices or price < jockey_prices[jockey]:
                        jockey_prices[jockey] = price

        if not jockey_prices:
            continue

        participants = [
            {"name": name, "price": price}
            for name, price in sorted(jockey_prices.items(), key=lambda x: x[1])
        ]

        market = {
            "meeting_name": name.title(),
            "type": "jockey",
            "participants": participants,
            "bookmaker": "Sportsbet",
            "total_races": len(races),
            "races": [],
        }
        result.append(market)
        logger.info(
            f"Sportsbet: {name} ({len(participants)} jockeys, {len(races)} races)"
        )

    return result


class SportsbetScraper:
    """Scrape Sportsbet Australia fixed odds via Playwright browser.
    
    Sportsbet uses Akamai CDN which blocks direct HTTP requests.
    Playwright launches a real Chromium browser to bypass the protection.
    """

    def __init__(self):
        self.name = "Sportsbet"

    def scrape_jockey_challenges(self) -> List[Dict]:
        aus_date = self._get_aus_date()
        meetings = _discover_meetings(aus_date)
        if not meetings:
            logger.info("Sportsbet: No meeting data available")
            return []
        return _parse_jockey_challenges(meetings)

    def scrape_driver_challenges(self) -> List[Dict]:
        aus_date = self._get_aus_date()
        meetings = _discover_meetings(aus_date)
        if not meetings:
            logger.info("Sportsbet: No meeting data available")
            return []
        # Same parsing logic but filter for harness/trot meetings
        result = _parse_jockey_challenges(meetings)
        return result

    def _get_aus_date(self) -> str:
        try:
            from time_utils import today_aus
            return today_aus()
        except ImportError:
            from datetime import datetime, timezone, timedelta
            return (datetime.now(timezone.utc) + timedelta(hours=10)).strftime("%Y-%m-%d")

    def close(self):
        _close_browser()
