"""
Standalone test script for the TAB API scraper.

Usage:
    python test_tab_scraper.py            # Test without auth (direct API)
    python test_tab_scraper.py --auth     # Test with OAuth (requires TAB_CLIENT_ID/TAB_CLIENT_SECRET env vars)
"""
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from scrapers.tab_api import TabcorpAPIScraper, TAB_BASE_URL
import httpx


def test_direct_api():
    """Test direct access to TAB API without auth."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"TEST 1: Direct API (no auth) - {TAB_BASE_URL}")
    print(f"{'='*60}")

    url = f"{TAB_BASE_URL}/v1/tab-info-service/racing/dates/{today}/meetings?jurisdiction=NSW"
    print(f"GET {url}")
    try:
        resp = httpx.get(url, timeout=15, headers={
            "user-agent": "Mozilla/5.0",
            "accept": "application/json",
        })
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            meetings = data.get("meetings", [])
            print(f"Meetings found: {len(meetings)}")
            for m in meetings[:5]:
                print(f"  - {m.get('meetingName')} ({m.get('raceType')}) @ {m.get('location', '?')}")
            return True
        else:
            print(f"Response: {resp.text[:500]}")
            return False
    except httpx.TimeoutException:
        print("TIMEOUT - API is not reachable (expected outside Australia)")
        return False
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return False


def test_authenticated_scraper():
    """Test the full TabcorpAPIScraper with OAuth."""
    print(f"\n{'='*60}")
    print("TEST 2: Authenticated TabcorpAPIScraper")
    print(f"{'='*60}")

    client_id = os.getenv("TAB_CLIENT_ID")
    client_secret = os.getenv("TAB_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("SKIPPED: TAB_CLIENT_ID / TAB_CLIENT_SECRET not set")
        print("Set them as environment variables and re-run with --auth")
        return

    scraper = TabcorpAPIScraper()
    try:
        jockey, driver = scraper.fetch_challenge_meetings()

        print(f"\nJockey meetings: {len(jockey)}")
        for m in jockey[:3]:
            print(f"  Meeting: {m['meeting_name']}")
            for p in m.get("participants", [])[:5]:
                print(f"    {p['name']}: ${p['price']}")

        print(f"\nDriver meetings: {len(driver)}")
        for m in driver[:3]:
            print(f"  Meeting: {m['meeting_name']}")
            for p in m.get("participants", [])[:5]:
                print(f"    {p['name']}: ${p['price']}")

        total = len(jockey) + len(driver)
        print(f"\nTotal challenge meetings: {total}")
        return total > 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        scraper.close()


def test_next_to_go():
    """Test the next-to-go endpoint."""
    print(f"\n{'='*60}")
    print("TEST 3: Next-to-go races")
    print(f"{'='*60}")

    scraper = TabcorpAPIScraper()
    try:
        races = scraper.get_next_to_go()
        print(f"Next-to-go races: {len(races)}")
        for r in races[:5]:
            meeting = r.get("meetingName", r.get("meeting_name", "?"))
            race_num = r.get("raceNumber", r.get("race_number", "?"))
            start = r.get("startTime", r.get("start_time", "?"))
            print(f"  R{race_num} @ {meeting} - {start}")
        return len(races) > 0
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        scraper.close()


if __name__ == "__main__":
    use_auth = "--auth" in sys.argv

    print("TAB API Scraper Test Suite")
    print("==========================")

    direct_ok = test_direct_api()

    if use_auth:
        auth_ok = test_authenticated_scraper()
    else:
        print(f"\n{'='*60}")
        print("TEST 2: Skipped (use --auth to test with OAuth)")
        print(f"{'='*60}")
        auth_ok = False

    ntg_ok = test_next_to_go()

    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Direct API:     {'PASS' if direct_ok else 'FAIL/SKIP'}")
    print(f"Auth Scraper:   {'PASS' if auth_ok else 'FAIL/SKIP'}")
    print(f"Next-to-go:     {'PASS' if ntg_ok else 'FAIL/SKIP'}")
    print()
    print("NOTE: The TAB API is geo-restricted to Australia.")
    print("Deploy to Render (staging) to test from Australian infrastructure.")
