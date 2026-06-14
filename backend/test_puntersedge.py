"""
Standalone test for PuntersEdge API scraper.

Usage:
    # Get a free key via API (returns immediately, no email):
    python test_puntersedge.py signup your@email.com

    # Then test with your key:
    $env:PUNTERSEDGE_API_KEY = "key_here"
    python test_puntersedge.py
"""
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(__file__))

from scrapers.puntersedge import PuntersEdgeScraper

API_BASE = "https://api.puntersedge.online/v1"


def do_signup(email: str):
    print(f"Signing up for free API key with email: {email}")
    r = httpx.post(
        f"{API_BASE}/signup",
        json={"email": email, "plan": "free", "label": "Dashboard Scraper"},
        timeout=15,
    )
    if r.status_code == 200:
        data = r.json()
        key = data.get("api_key") or data.get("key")
        if key:
            print(f"API key: {key}")
            print("Set it as environment variable and test:")
            print(f"  $env:PUNTERSEDGE_API_KEY = \"{key}\"")
            print(f"  python test_puntersedge.py")
            return key
        else:
            print(f"Response: {json.dumps(data, indent=2)}")
            print("Key may have been emailed instead.")
    else:
        print(f"Signup failed (status {r.status_code})")
        print(r.text[:500])
    return None


def test_with_key(api_key: str):
    os.environ["PUNTERSEDGE_API_KEY"] = api_key
    pe = PuntersEdgeScraper()

    if not pe.enabled:
        print("Something went wrong — scraper not enabled despite key being set.")
        return

    print("Fetching prices from PuntersEdge...")
    prices = pe.fetch_prices()

    if not prices:
        print("No prices returned. Checking API status...")
        try:
            r = httpx.get(
                f"{API_BASE}/usage",
                headers={"X-API-Key": api_key},
                timeout=15,
            )
            print(f"Usage status: {r.status_code}")
            if r.status_code == 200:
                print(json.dumps(r.json(), indent=2))
            else:
                print(r.text[:500])
        except Exception as e:
            print(f"Usage check failed: {e}")
        return

    print(f"\nGot prices for {len(prices)} venues:")
    total_runners = 0
    for venue, races in sorted(prices.items()):
        runner_count = sum(len(horses) for horses in races.values())
        total_runners += runner_count
        print(f"  {venue}: {len(races)} races, {runner_count} runners")
        first_race = min(races.keys())
        first_horses = races[first_race]
        for horse, bks in list(first_horses.items())[:3]:
            prices_str = ", ".join(f"{k}={v}" for k, v in bks.items())
            print(f"    Race {first_race}: {horse}: {prices_str}")

    print(f"\nTotal: {total_runners} runner price entries across {len(prices)} venues")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "signup":
        email = sys.argv[2] if len(sys.argv) > 2 else input("Enter your email: ")
        do_signup(email.strip())
        return

    api_key = os.environ.get("PUNTERSEDGE_API_KEY", "")
    if not api_key:
        print("API key not found.")
        print("  Option 1: python test_puntersedge.py signup your@email.com")
        print("  Option 2: $env:PUNTERSEDGE_API_KEY = \"your_key\"")
        print("\nTesting fallback behavior (no key)...")
        pe = PuntersEdgeScraper()
        prices = pe.fetch_prices()
        assert prices == {}, f"Expected empty dict when no API key, got {prices}"
        print("OK: returns empty dict when no API key")
        return

    test_with_key(api_key)


if __name__ == "__main__":
    main()
