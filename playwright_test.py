"""
Final approach: 
1. Find correct Betfair harness racing page
2. Try Ladbrokes extras with scroll to lazy-load accordion content
"""
import asyncio
import json
import re
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                   '--disable-blink-features=AutomationControlled',
                   '--js-flags=--max-old-space-size=512']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
        """)
        
        page = await context.new_page()
        
        captured_gql = []
        
        async def handle_response(response):
            url = response.url
            if "gql/router" in url and "assets" not in url:
                try:
                    body = await response.text()
                    if len(body) > 500:
                        parsed = urlparse(url)
                        params = parse_qs(parsed.query)
                        ext = params.get("extensions", [""])[0]
                        sha_match = re.search(r'"sha256Hash":"([^"]+)"', ext)
                        sha = sha_match.group(1) if sha_match else ""
                        ops = params.get("operationName", [""])[0]
                        captured_gql.append({"sha": sha, "op": ops, "body": body})
                except:
                    pass
        
        page.on("response", handle_response)
        
        # === Betfair: Find correct harness URL ===
        print("=== Betfair: Finding harness racing page ===")
        try:
            await page.goto("https://www.betfair.com.au/exchange/plus", 
                          wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(5)
            
            # Find harness link
            harness_link = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                for (const l of links) {
                    const text = l.textContent.trim().toLowerCase();
                    const href = l.href.toLowerCase();
                    if (text.includes('harness') || href.includes('harness')) {
                        return {href: l.href, text: l.textContent.trim()};
                    }
                }
                return null;
            }""")
            
            if harness_link:
                print(f"  Harness link: {harness_link}")
                await page.goto(harness_link['href'], wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(8)
                
                body_text = await page.inner_text("body")
                print(f"  Body: {len(body_text)} chars")
                
                # Search for challenge/markets
                for kw in ["challenge", "driver", "menangle", "melton", "redcliffe", "northam", "port pirie"]:
                    if kw in body_text.lower():
                        idx = body_text.lower().index(kw)
                        ctx = body_text[max(0,idx-30):idx+100].replace('\n', ' ')
                        print(f"  Found '{kw}': {ctx[:150]}")
                
                # Get all meeting links
                links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(l => ({href: l.href, text: l.textContent.trim().substring(0, 50)}))
                        .filter(l => l.text.length > 2);
                }""")
                print(f"  All links: {len(links)}")
                for l in links[:20]:
                    print(f"    {l['text'][:40]} -> {l['href'][:80]}")
                    
        except Exception as e:
            print(f"  Betfair error: {e}")
        
        await browser.close()
    
    print("\n=== Done ===")

asyncio.run(main())
