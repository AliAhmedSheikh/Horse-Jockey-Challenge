"""
Playwright script to intercept Ladbrokes GraphQL traffic.
Captures actual SHA and operation names used by the live SPA.
"""

import asyncio
import json
import re
from pathlib import Path

# Install playwright if needed
try:
    from playwright.async_api import async_playwright
except ImportError:
    import subprocess
    subprocess.run(["pip", "install", "playwright"], check=True)
    subprocess.run(["playwright", "install", "chromium"], check=True)
    from playwright.async_api import async_playwright


async def intercept_ladbrokes():
    """Intercept all GraphQL requests to Ladbrokes SPA."""
    
    captured_requests = []
    captured_responses = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        page = await context.new_page()
        
        # Intercept all requests
        async def handle_request(request):
            url = request.url
            if "graphql" in url.lower() or "api" in url.lower():
                try:
                    body = request.post_data
                    if body:
                        data = json.loads(body)
                        captured_requests.append({
                            "url": url,
                            "operation": data.get("operationName"),
                            "sha": data.get("extensions", {}).get("persistedQuery", {}).get("sha256Hash"),
                            "variables": data.get("variables")
                        })
                except:
                    pass
        
        async def handle_response(response):
            url = response.url
            if "graphql" in url.lower():
                try:
                    body = await response.json()
                    captured_responses.append({
                        "url": url,
                        "status": response.status,
                        "data_keys": list(body.get("data", {}).keys()) if body.get("data") else [],
                        "has_errors": "errors" in body
                    })
                except:
                    pass
        
        page.on("request", handle_request)
        page.on("response", handle_response)
        
        # Navigate to Ladbrokes harness racing
        print("Navigating to Ladbrokes...")
        await page.goto("https://www.ladbrokes.com.au/racing/harness", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        
        # Try to find and click on a meeting with challenge market
        print("Looking for challenge market links...")
        
        # Check for challenge market elements
        challenge_links = await page.query_selector_all('a[href*="challenge"], a[href*="driver"], a[href*="jockey"]')
        print(f"Found {len(challenge_links)} challenge-related links")
        
        # Look for extras/challenge sections
        extras_sections = await page.query_selector_all('[class*="extras"], [class*="challenge"], [data-testid*="extras"]')
        print(f"Found {len(extras_sections)} extras sections")
        
        # Try clicking on different elements to trigger challenge market loading
        # Look for "Driver Challenge" or "Jockey Challenge" text
        all_text = await page.inner_text("body")
        if "Driver Challenge" in all_text:
            print("Found 'Driver Challenge' text on page")
            # Try to find and click the element
            driver_challenge_elements = await page.query_selector_all('text=Driver Challenge')
            for elem in driver_challenge_elements[:3]:
                try:
                    await elem.click()
                    await asyncio.sleep(2)
                except:
                    pass
        
        # Check for accordion/expandable elements
        accordions = await page.query_selector_all('button[aria-expanded], [role="button"], details, summary')
        print(f"Found {len(accordions)} accordion/button elements")
        
        # Try clicking accordions
        for acc in accordions[:5]:
            try:
                expanded = await acc.get_attribute("aria-expanded")
                if expanded == "false":
                    await acc.click()
                    await asyncio.sleep(1)
            except:
                pass
        
        # Take a screenshot for debugging
        await page.screenshot(path="/tmp/ladbrokes_intercept.png")
        print("Screenshot saved to /tmp/ladbrokes_intercept.png")
        
        # Try navigating to specific meeting pages
        # Menangle has a confirmed challenge market
        test_urls = [
            "https://www.ladbrokes.com.au/racing/harness/menangle",
            "https://www.ladbrokes.com.au/racing/harness/northam",
            "https://www.ladbrokes.com.au/racing/harness/port-pirie",
        ]
        
        for url in test_urls:
            print(f"\nTrying {url}...")
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(3)
                
                # Look for challenge market elements
                challenge_text = await page.inner_text("body")
                if "challenge" in challenge_text.lower():
                    print(f"  Found challenge text on {url}")
                    
                    # Try to find challenge market cards
                    cards = await page.query_selector_all('[class*="market"], [class*="card"], [data-testid*="market"]')
                    print(f"  Found {len(cards)} market/card elements")
                    
                    # Click on first few cards
                    for card in cards[:3]:
                        try:
                            await card.click()
                            await asyncio.sleep(2)
                        except:
                            pass
                
                # Check for specific challenge market URLs
                links = await page.query_selector_all('a[href*="driver-challenge"], a[href*="jockey-challenge"]')
                for link in links[:2]:
                    href = await link.get_attribute("href")
                    print(f"  Found challenge link: {href}")
                    await link.click()
                    await asyncio.sleep(3)
                    
            except Exception as e:
                print(f"  Error: {e}")
        
        # Wait for any remaining network activity
        await asyncio.sleep(5)
        
        await browser.close()
    
    # Save captured data
    output = {
        "requests": captured_requests,
        "responses": captured_responses
    }
    
    with open("/tmp/ladbrokes_intercept_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nCaptured {len(captured_requests)} requests, {len(captured_responses)} responses")
    print("Results saved to /tmp/ladbrokes_intercept_results.json")
    
    # Print unique operations and SHAs
    operations = set()
    shas = set()
    for req in captured_requests:
        if req.get("operation"):
            operations.add(req["operation"])
        if req.get("sha"):
            shas.add(req["sha"])
    
    print(f"\nUnique operations: {operations}")
    print(f"Unique SHAs: {shas}")
    
    return output


if __name__ == "__main__":
    asyncio.run(intercept_ladbrokes())
