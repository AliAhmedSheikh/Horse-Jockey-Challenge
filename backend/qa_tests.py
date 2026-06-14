"""QA Test Suite — Backend API"""
import httpx
import json
import sys
import time

BASE = "http://localhost:8000"
API_KEY = "e68af6ab-99f6-4d1f-8a19-8d2c1c80360a"

passed = 0
failed = 0
errors = []

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name} — {detail}"
        print(msg)
        errors.append(msg)

def get(path):
    r = httpx.get(f"{BASE}{path}", timeout=15)
    return r

client = httpx.Client(base_url=BASE, timeout=15)

print("="*60)
print("QA TEST SUITE — Backend API")
print("="*60)

# === 1. Health Check ===
print("\n--- 1. Health Check ---")
r = client.get("/")
check("Root endpoint returns 200", r.status_code == 200)
check("Response has status ok", r.json().get("status") == "ok")

# === 2. Meetings Today ===
print("\n--- 2. Meetings Today ---")
r = client.get("/meetings/today")
check("GET /meetings/today returns 200", r.status_code == 200)
meetings = r.json()
check("Returns a list", isinstance(meetings, list))
if meetings:
    m = meetings[0]
    check("Meeting has id", bool(m.get("id")))
    check("Meeting has name", bool(m.get("name")))
    check("Meeting has type", m.get("type") in ("Jockey", "Driver"))
    check("Meeting has status", m.get("status") in ("Live", "Not Started", "Completed"))
    check("completedRaces >= 0", m.get("completedRaces", -1) >= 0)
    check("totalRaces > 0", m.get("totalRaces", 0) > 0)
    check("completedRaces <= totalRaces", m.get("completedRaces", 0) <= m.get("totalRaces", 999))
    check("leaderboard is a list", isinstance(m.get("leaderboard"), list))
    print(f"  Sample: {m['name']} ({m['type']}) — {m['status']} — {m['completedRaces']}/{m['totalRaces']}")

# === 3. Live Meetings ===
print("\n--- 3. Live Meetings ---")
r = client.get("/meetings/live")
check("GET /meetings/live returns 200", r.status_code == 200)
live = r.json()
check("Returns a list", isinstance(live, list))
print(f"  {len(live)} live meetings")

# === 4. Finished Meetings ===
print("\n--- 4. Finished Meetings ---")
r = client.get("/meetings/finished")
check("GET /meetings/finished returns 200", r.status_code == 200)
finished = r.json()
check("Returns a list", isinstance(finished, list))
print(f"  {len(finished)} finished meetings")

# === 5. Dashboard ===
print("\n--- 5. Dashboard ---")
r = client.get("/dashboard")
check("GET /dashboard returns 200", r.status_code == 200)
dash = r.json()
check("Has meetings list", isinstance(dash.get("meetings"), list))
check("Has jockeys list", isinstance(dash.get("jockeys"), list))
check("Has drivers list", isinstance(dash.get("drivers"), list))
check("Has dashboardCards", isinstance(dash.get("dashboardCards"), dict))
cards = dash.get("dashboardCards", {})
check("todayMeetings >= 0", cards.get("todayMeetings", -1) >= 0)
check("activeJockeyChallenges >= 0", cards.get("activeJockeyChallenges", -1) >= 0)
check("activeDriverChallenges >= 0", cards.get("activeDriverChallenges", -1) >= 0)
check("totalParticipants >= 0", cards.get("totalParticipants", -1) >= 0)
print(f"  Cards: {cards}")

# Check recent results contain valid data
results = dash.get("recentResults", [])
if results:
    rr = results[0]
    check("Recent result has meetingName", bool(rr.get("meetingName")))
    check("Recent result has raceNumber > 0", rr.get("raceNumber", 0) > 0)
    check("Recent result has participant", bool(rr.get("participant")))
    check("Recent result has pointsAdded >= 0", rr.get("pointsAdded", -1) >= 0)
    check("Recent result has type", rr.get("type") in ("Jockey", "Driver"))

# === 6. Participant Data Integrity ===
print("\n--- 6. Participant Data Integrity ---")
all_jockeys = dash.get("jockeys", [])
all_drivers = dash.get("drivers", [])
for label, participants in [("Jockeys", all_jockeys), ("Drivers", all_drivers)]:
    for p in participants:
        pid = p.get("id", "?")
        check(f"{label} {p.get('name','?')}: bookmakerPrice > 0", p.get("bookmakerPrice", 0) > 0, pid)
        check(f"{label} {p.get('name','?')}: aiPrice > 0", p.get("aiPrice", 0) > 0, pid)
        check(f"{label} {p.get('name','?')}: currentPoints >= 0", p.get("currentPoints", -1) >= 0, pid)
        check(f"{label} {p.get('name','?')}: projectedFinalPoints >= 0", p.get("projectedFinalPoints", -1) >= 0, pid)
        check(f"{label} {p.get('name','?')}: bookmakerPrices is object", isinstance(p.get("bookmakerPrices"), dict), pid)
        # Check all 5 bookmakers have prices
        for bm in ["Ladbrokes", "TAB", "Sportsbet", "PointsBet", "TABtouch"]:
            bp = p.get("bookmakerPrices", {}).get(bm)
            check(f"{label} {p.get('name','?')}: {bm} price > 0", bp is not None and bp > 0, f"{pid} — {bm}={bp}")

# === 7. Meeting Detail ===
print("\n--- 7. Meeting Detail ---")
if meetings:
    mid = meetings[0]["id"]
    r = client.get(f"/meetings/{mid}")
    check(f"GET /meetings/{mid} returns 200", r.status_code == 200)
    detail = r.json()
    check("Detail has projectedWinner", "projectedWinner" in detail)

    r = client.get(f"/meetings/{mid}/participants")
    check(f"GET /meetings/{mid}/participants returns 200", r.status_code == 200)
    parts = r.json()
    check("Participants is a list", isinstance(parts, list))
    if parts:
        p = parts[0]
        check("Participant has id", bool(p.get("id")))
        check("Participant has bookmakerPrices", isinstance(p.get("bookmakerPrices"), dict))
        check("Participant has valueRating", p.get("valueRating") in ("Strong Value", "Value", "Neutral", "Avoid"))
        check("isProjectedWinner is boolean", isinstance(p.get("isProjectedWinner"), bool))

    # Check price endpoint
    r = client.get(f"/meetings/{mid}/prices")
    check(f"GET /meetings/{mid}/prices returns 200", r.status_code == 200)
    prices = r.json()
    check("Prices is a list", isinstance(prices, list))

    # Check results endpoint
    r = client.get(f"/meetings/{mid}/results")
    check(f"GET /meetings/{mid}/results returns 200", r.status_code == 200)

    # Check podium
    r = client.get(f"/meetings/{mid}/podium")
    check(f"GET /meetings/{mid}/podium returns 200", r.status_code == 200)
    podium = r.json()
    check("Podium is a list", isinstance(podium, list))

# === 8. Error Handling ===
print("\n--- 8. Error Handling ---")
r = client.get("/meetings/nonexistent")
check("404 for nonexistent meeting", r.status_code == 404)

r = client.get("/meetings/nonexistent/participants")
check("404 for nonexistent meeting participants", r.status_code == 404)

r = client.get("/meetings/nonexistent/prices")
check("404 for nonexistent meeting prices", r.status_code == 404)

# === 9. Refresh Endpoint ===
print("\n--- 9. Refresh Endpoint ---")
r = httpx.post(f"{BASE}/refresh", timeout=30)
check("POST /refresh returns 200", r.status_code == 200)
check("Refresh response has status ok", r.json().get("status") == "ok")

# === 10. Price Consistency Check ===
print("\n--- 10. Price Consistency ---")
# Check that no participant has all bookmakers at the same price (would indicate simulation error)
for label, participants in [("Jockeys", all_jockeys), ("Drivers", all_drivers)]:
    for p in participants:
        bks = p.get("bookmakerPrices", {})
        vals = [v for v in bks.values() if v > 0]
        if len(vals) > 1 and len(set(vals)) == 1:
            check(f"{label} {p.get('name','?')}: prices NOT all identical", False, f"All bookmakers = {vals[0]}")

# === 11. Price Sort Order ===
print("\n--- 11. Leaderboard Sort Order ---")
for m in meetings:
    lb = m.get("leaderboard", [])
    for i in range(len(lb) - 1):
        check(f"Leaderboard sorted: {m['name']} pos {i+1} >= pos {i+2}",
              lb[i].get("points", 0) >= lb[i+1].get("points", 0),
              f"{lb[i]['name']}={lb[i]['points']} vs {lb[i+1]['name']}={lb[i+1]['points']}")

# === SUMMARY ===
print("\n" + "="*60)
print(f"RESULTS: {passed} passed, {failed} failed")
if errors:
    print("\nFAILURES:")
    for e in errors:
        print(e)
print("="*60)

client.close()
sys.exit(0 if failed == 0 else 1)
