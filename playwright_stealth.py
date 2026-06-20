"""
Approach 2: Playwright with stealth - intercept ALL responses and try to trigger market detail load.
"""
import asyncio
import json
import re
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright

STEALTH_JS = """
// Override navigator properties
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'languages', { get: () => ['en-AU', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });

// Override chrome detection
window.chrome = { runtime: {} };

// Override permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--js-flags=--max-old-space-size=512'
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-AU",
            timezone_id="Australia/Sydney",
            extra_http_headers={
                "Accept-Language": "en-AU,en;q=0.9",
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            }
        )
        
        # Apply stealth JS
        await context.add_init_script(STEALTH_JS)
        
        page = await context.new_page()
        
        all_gql = []
        
        async def handle_response(response):
            if "gql/router" in response.url and "assets" not in response.url:
                try:
                    body = await response.text()
                    parsed = urlparse(response.url)
                    params = parse_qs(parsed.query)
                    ext = params.get("extensions", [""])[0]
                    sha_match = re.search(r'"sha256Hash":"([^"]+)"', ext)
                    sha = sha_match.group(1) if sha_match else ""
                    ops = params.get("operationName", [""])[0]
                    
                    all_gql.append({"sha": sha, "op": ops, "body": body, "url": response.url})
                    
                    body_lower = body.lower()
                    has_runner = any(kw in body_lower for kw in ["runner", "selection", "entrant"])
                    has_odds = any(kw in body_lower for kw in ["decimal", "odds", "price", "winreturn"])
                    has_names = any(kw in body_lower for kw in ["dixon", "hart", "mccarthy", "herbertson", "callaghan"])
                    
                    if has_runner and has_odds:
                        print(f"GQL [{response.status}] sha={sha[:16]} op={ops} ({len(body)} bytes) ** RUNNERS+ODDS **")
                    elif len(body) > 2000:
                        print(f"GQL [{response.status}] sha={sha[:16]} op={ops} ({len(body)} bytes)")
                except:
                    pass
        
        page.on("response", handle_response)
        
        # Load Racing Extras page
        print("=== Loading Racing Extras with stealth ===")
        try:
            await page.goto("https://www.ladbrokes.com.au/racing/extras", 
                          wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"Nav: {e}")
        
        await asyncio.sleep(8)
        
        # Get the page HTML to understand structure
        html = await page.content()
        print(f"Page HTML: {len(html)} chars")
        
        # Find what's actually rendered - check for harness sections
        body_text = await page.inner_text("body")
        print(f"Body text: {len(body_text)} chars")
        print(f"Body preview: {body_text[:500]}")
        
        # Try to find and click the harness tab/section
        print("\n=== Looking for harness section on extras page ===")
        
        # Find tabs or filters on the page
        all_buttons = await page.query_selector_all("button, [role='tab'], [role='button']")
        print(f"Found {len(all_buttons)} buttons/tabs")
        for btn in all_buttons[:20]:
            text = await btn.evaluate("e => e.textContent.trim().substring(0, 40)")
            if text:
                print(f"  Button: '{text}'")
        
        # Look for harness filter
        harness_btn = await page.query_selector("text=Harness")
        if harness_btn:
            print("\n=== Clicking Harness filter ===")
            try:
                await harness_btn.click()
                await asyncio.sleep(8)
                
                body_text2 = await page.inner_text("body")
                print(f"Body after Harness click: {len(body_text2)} chars")
                
                # Check for challenge content
                for kw in ["driver challenge", "menangle", "northam", "port pirie", "redcliffe"]:
                    if kw in body_text2.lower():
                        idx = body_text2.lower().index(kw)
                        ctx = body_text2[max(0,idx-30):idx+100].replace('\n', ' ')
                        print(f"  Found '{kw}': {ctx[:150]}")
                
            except Exception as e:
                print(f"Click error: {e}")
        
        # Try scrolling down to find challenge sections
        print("\n=== Scrolling to find challenge sections ===")
        for scroll_y in range(0, 5000, 500):
            await page.evaluate(f"window.scrollTo(0, {scroll_y})")
            await asyncio.sleep(1)
        
        await asyncio.sleep(3)
        
        # Check body text again after scrolling
        body_text3 = await page.inner_text("body")
        if "driver challenge" in body_text3.lower():
            print("FOUND 'driver challenge' after scrolling!")
            idx = body_text3.lower().index("driver challenge")
            ctx = body_text3[max(0,idx-50):idx+200].replace('\n', ' ')
            print(f"  Context: {ctx[:300]}")
        
        # Print all GQL with challenge data
        print(f"\n=== Total {len(all_gql)} GQL requests ===")
        for g in all_gql:
            body_lower = g["body"].lower()
            if any(kw in body_lower for kw in ["runner", "selection", "entrant", "decimal", "odds"]):
                print(f"  RUNNERS/ODDS: sha={g['sha'][:16]} op={g['op']} ({len(g['body'])} bytes)")
                with open(f"/tmp/stealth_{g['op']}.json", "w") as f:
                    f.write(g["body"])
                print(f"  Saved!")
        
        await browser.close()
    
    print("\n=== Done ===")

asyncio.run(main())
