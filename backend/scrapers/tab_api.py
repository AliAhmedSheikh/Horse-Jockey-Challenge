import logging
import os
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

TAB_BASE_URL = "https://api.beta.tab.com.au"
OAUTH_TOKEN_PATH = "/oauth/token"
API_TIMEOUT = 20.0
TOKEN_EXPIRY_BUFFER = 60

VALID_JURISDICTIONS = {"NSW", "VIC", "QLD", "SA", "TAS", "ACT", "NT"}


def _get_credentials() -> Tuple[Optional[str], Optional[str]]:
    client_id = os.getenv("TAB_CLIENT_ID")
    client_secret = os.getenv("TAB_CLIENT_SECRET")
    return client_id, client_secret


class TabcorpAuth:
    def __init__(self, base_url: str = TAB_BASE_URL):
        self.base_url = base_url
        self._token: Optional[str] = None
        self._expires_at: float = 0

    def _is_expired(self) -> bool:
        return time.time() >= self._expires_at

    def authenticate(self) -> Optional[str]:
        if self._token and not self._is_expired():
            return self._token

        client_id, client_secret = _get_credentials()
        if not client_id or not client_secret:
            logger.warning("TAB_CLIENT_ID / TAB_CLIENT_SECRET not set")
            return None

        url = f"{self.base_url.rstrip('/')}{OAUTH_TOKEN_PATH}"
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": "JockeyDriverDashboard/1.0",
        }

        try:
            with httpx.Client(timeout=API_TIMEOUT) as client:
                resp = client.post(url, data=data, headers=headers)
                if resp.status_code >= 400:
                    logger.error(f"TAB OAuth failed: HTTP {resp.status_code}")
                    return None
                result = resp.json()
                self._token = result["access_token"]
                expires_in = int(result.get("expires_in", 3600))
                self._expires_at = time.time() + expires_in - TOKEN_EXPIRY_BUFFER
                logger.info("TAB OAuth authenticated successfully")
                return self._token
        except Exception as e:
            logger.error(f"TAB OAuth error: {e}")
            return None


class TabcorpAPIScraper:
    def __init__(self):
        self.name = "TAB"
        self._auth = TabcorpAuth()
        self._client = httpx.Client(timeout=API_TIMEOUT, headers={
            "user-agent": "JockeyDriverDashboard/1.0",
            "accept": "application/json",
        })
        self._token: Optional[str] = None

    def _ensure_auth(self) -> bool:
        self._token = self._auth.authenticate()
        return self._token is not None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "user-agent": "JockeyDriverDashboard/1.0",
            "accept": "application/json",
        }
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        return headers

    def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        url = f"{TAB_BASE_URL}{path}"
        try:
            resp = self._client.get(url, headers=self._get_headers(), params=params or {})
            if resp.status_code == 401 and self._ensure_auth():
                resp = self._client.get(url, headers=self._get_headers(), params=params or {})
            if resp.status_code != 200:
                logger.warning(f"TAB API {path} returned HTTP {resp.status_code}")
                return None
            return resp.json()
        except httpx.TimeoutException:
            logger.warning(f"TAB API {path} timed out")
            return None
        except Exception as e:
            logger.warning(f"TAB API {path} error: {e}")
            return None

    def get_meetings(self, date: str, jurisdiction: str = "NSW") -> List[Dict]:
        data = self._get(
            f"/v1/tab-info-service/racing/dates/{date}/meetings",
            {"jurisdiction": jurisdiction},
        )
        if data is None:
            return []
        return data.get("meetings", [])

    def get_next_to_go(self, jurisdiction: str = "NSW", max_races: int = 50) -> List[Dict]:
        data = self._get(
            "/v1/tab-info-service/racing/next-to-go/races",
            {"jurisdiction": jurisdiction, "maxRaces": max_races},
        )
        if data is None:
            return []
        return data.get("races", [])

    def get_race(self, date: str, race_type: str, venue_mnemonic: str,
                 race_number: int, jurisdiction: str = "NSW") -> Optional[Dict]:
        return self._get(
            f"/v1/tab-info-service/racing/dates/{date}/meetings/{race_type}/{venue_mnemonic}/races/{race_number}",
            {"jurisdiction": jurisdiction, "fixedOdds": "true"},
        )

    def fetch_challenge_meetings(self) -> Tuple[List[Dict], List[Dict]]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        meetings = self.get_meetings(today, "NSW")
        if not meetings:
            meetings = self.get_meetings(today, "VIC")
        if not meetings:
            logger.warning("No TAB meetings found for today")
            return [], []

        jockey_markets = []
        driver_markets = []

        for meeting in meetings:
            race_type = meeting.get("raceType", "")
            meeting_name = meeting.get("meetingName", "")
            venue_code = meeting.get("venueCode", "")
            venue_mnemonic = meeting.get("venueMnemonic", venue_code or meeting_name)

            challenge_type = "driver" if race_type == "H" else "jockey"
            if race_type == "G":
                continue

            races_url = f"/v1/tab-info-service/racing/dates/{today}/meetings/{race_type}/{venue_mnemonic}/races"
            races_data = self._get(races_url, {"jurisdiction": "NSW"})
            if not races_data:
                continue

            races_list = races_data.get("races", [])
            seen = {}

            for race_info in races_list[:2]:
                race_number = race_info.get("raceNumber") or race_info.get("race_number", 1)
                if race_number == 0:
                    continue

                race_detail = self.get_race(today, race_type, venue_mnemonic, race_number)
                if not race_detail:
                    continue

                for runner in race_detail.get("runners", []):
                    if runner.get("isScratched"):
                        continue
                    jockey = (runner.get("jockey") or "").strip()
                    driver = (runner.get("driver") or "").strip()
                    name = jockey or driver
                    if not name or name == "Unknown":
                        continue

                    odds = runner.get("odds") or runner.get("fixedOdds", {})
                    if isinstance(odds, dict):
                        price = odds.get("fixedWin") or odds.get("win") or odds.get("returnWin", 0)
                    else:
                        price = float(odds)

                    if not price or price <= 0:
                        continue

                    if name not in seen or price > seen[name]:
                        seen[name] = price

            if seen:
                parts = [{"name": n, "price": p} for n, p in seen.items()]
                parts.sort(key=lambda x: x["price"] if x["price"] > 0 else 999)
                market = {
                    "meeting_name": meeting_name,
                    "type": challenge_type,
                    "participants": parts,
                    "bookmaker": "TAB",
                }
                if challenge_type == "driver":
                    driver_markets.append(market)
                else:
                    jockey_markets.append(market)

        logger.info(f"TAB API: {len(jockey_markets)} jockey, {len(driver_markets)} driver meetings")
        return jockey_markets, driver_markets

    def close(self):
        if self._client:
            self._client.close()
