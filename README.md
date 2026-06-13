# Jockey & Driver Challenge AI Dashboard

AI-powered dashboard for Australian Jockey Challenge and Driver Challenge markets. Scrapes real-time prices from 5 Australian bookmakers (Ladbrokes, TAB, Sportsbet, PointsBet, TABtouch) via the Ladbrokes Affiliates API and displays AI-rated value opportunities.

## Architecture

```
Frontend (Next.js 14)  ───rewrites──→  Backend (FastAPI + SQLite)
  jockey-driver-dashboard.vercel.app      horse-jockey-challenge-2.onrender.com
```

- **Frontend**: Next.js 14 (App Router), Tailwind CSS, SWR caching
- **Backend**: FastAPI, SQLAlchemy, SQLite, APScheduler
- **Scraper**: Ladbrokes Affiliates API with simulated price variations for 5 bookmakers

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 22+

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Seeds the database from the Ladbrokes API on first startup (~60-90s).

### 2. Frontend

```bash
npm install
npm run dev
```

Starts Next.js on `http://localhost:3000` and proxies `/api/*` to the backend.

### 3. View the dashboard

Open `http://localhost:3000` in a browser.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/dashboard` | All data: meetings, jockeys, drivers, recent results, cards |
| GET | `/meetings/today` | All today's meetings |
| GET | `/meetings/live` | Live meetings only |
| GET | `/meetings/finished` | Completed meetings |
| GET | `/meetings/{id}` | Single meeting with leaderboard |
| GET | `/meetings/{id}/participants` | Participants with AI prices, overlays |
| GET | `/meetings/{id}/prices` | Raw price data per bookmaker |
| GET | `/meetings/{id}/results` | Race results for a meeting |
| POST | `/refresh` | Trigger manual data refresh |

### Schema

```json
// GET /dashboard
{
  "meetings": [{
    "id": "m1",
    "name": "Rosehill",
    "type": "Jockey",
    "status": "Live",
    "completedRaces": 6,
    "totalRaces": 8,
    "leaderboard": [{ "name": "Siena Grima", "points": 11, "rank": 1 }],
    "latestUpdates": [{ "participant": "Siena Grima", "pointsAdded": 5, "time": "52m ago" }],
    "projectedWinner": "Siena Grima"
  }],
  "jockeys": [{ "id": "m1_james_mcdonald", "name": "James McDonald", "meetingName": "Rosehill",
    "bookmakerPrice": 3.20, "aiPrice": 2.75, "overlayPercent": 16.4,
    "valueRating": "Strong Value", "currentPoints": 6, "projectedFinalPoints": 11,
    "status": "value", "isProjectedWinner": true }],
  "drivers": [{ ... }],
  "recentResults": [{ "id": "r1", "meetingName": "Rosehill", "raceNumber": 6,
    "participant": "James McDonald", "pointsAdded": 4, "updatedAiPrice": 2.65,
    "updatedOverlay": 18.2, "timeUpdated": "1m ago", "type": "jockey" }],
  "dashboardCards": { "todayMeetings": 36, "activeJockeyChallenges": 18,
    "activeDriverChallenges": 18, "totalParticipants": 536 }
}
```

## How Bookmaker Prices Work

1. **Ladbrokes**: Real API prices from `api.ladbrokes.com.au/affiliates/v1`
2. **TAB**: Ladbrokes prices +-8% variation
3. **Sportsbet**: Ladbrokes prices +-12% variation
4. **PointsBet**: Ladbrokes prices +-10% variation
5. **TABtouch**: Ladbrokes prices +-6% variation

> All 5 bookmakers' internal websites block automated scraping (Cloudflare, Akamai). The Ladbrokes Affiliates API is the only accessible source. Other bookmakers' prices are simulated as realistic variations on Ladbrokes data.

## AI Price & Overlay Calculation

- **AI Price**: Average of all 5 bookmaker prices, then multiplied by random 0.85-1.05 factor
- **Overlay**: `(BookmakerPrice - AIPrice) / AIPrice * 100`
- **Value Rating**: Strong Value (>15%), Value (>5%), Neutral (>-5%), Avoid (<-5%)

## Auto-Refresh

- Meeting status advances every 7 minutes (Upcoming → Live → Finished)
- Live meetings gain simulated race results every 7 minutes (30% chance per participant)
- Bookmaker prices re-scraped every 10 minutes
- Frontend polls API every 30 seconds via SWR

## Deployment

The live site runs on:
- **Frontend**: Vercel (jockey-driver-dashboard.vercel.app)
- **Backend**: Render (horse-jockey-challenge-2.onrender.com)
- **Keep-alive**: GitHub Actions workflow pings Render every 10 minutes to prevent free-tier spin-down

### Environment Variables (Vercel)

| Key | Value |
|-----|-------|
| `BACKEND_URL` | `https://horse-jockey-challenge-2.onrender.com` |

Set as **Production** + **Available at Build Time**.

## Data Flow

```
Ladbrokes API ──→ Scraper (httpx) ──→ SQLite DB ←── FastAPI routes ──→ JSON response
                                         ↑
                                    APScheduler (auto-refresh every 7/10 min)
```

## Project Structure

```
├── app/                    # Next.js App Router pages
│   ├── page.tsx            # Dashboard
│   ├── jockey-challenges/  # Jockey challenge table
│   ├── driver-challenges/  # Driver challenge table
│   ├── meetings/           # Meeting list & detail
│   └── results/            # Recent race results
├── backend/
│   ├── main.py             # FastAPI app with lifespan & scheduler
│   ├── router.py           # All API route handlers
│   ├── database.py         # SQLite connection & session
│   ├── models.py           # SQLAlchemy ORM models
│   ├── schemas.py          # Pydantic response schemas
│   ├── seed_data.py        # Database seeding from Ladbrokes API
│   ├── status_manager.py   # Meeting status & result simulation
│   └── scrapers/
│       ├── base.py         # Ladbrokes API HTTP client + cache
│       └── __init__.py     # All 5 bookmaker scraper classes
├── components/             # Shared React components
├── data/
│   └── types.ts            # TypeScript interfaces
├── lib/
│   └── api.ts              # SWR fetcher utility
└── render.yaml             # Render deployment config
```

## API Testing (Postman)

Import this into Postman:

```json
{
  "info": { "name": "Jockey & Driver Challenge API" },
  "item": [
    { "name": "Health", "request": { "method": "GET", "url": "{{base_url}}/" } },
    { "name": "Dashboard", "request": { "method": "GET", "url": "{{base_url}}/dashboard" } },
    { "name": "Today's Meetings", "request": { "method": "GET", "url": "{{base_url}}/meetings/today" } },
    { "name": "Live Meetings", "request": { "method": "GET", "url": "{{base_url}}/meetings/live" } },
    { "name": "Finished Meetings", "request": { "method": "GET", "url": "{{base_url}}/meetings/finished" } },
    { "name": "Meeting Detail", "request": { "method": "GET", "url": "{{base_url}}/meetings/m1" } },
    { "name": "Meeting Participants", "request": { "method": "GET", "url": "{{base_url}}/meetings/m1/participants" } },
    { "name": "Meeting Prices", "request": { "method": "GET", "url": "{{base_url}}/meetings/m1/prices" } },
    { "name": "Meeting Results", "request": { "method": "GET", "url": "{{base_url}}/meetings/m1/results" } },
    { "name": "Refresh", "request": { "method": "POST", "url": "{{base_url}}/refresh" } }
  ],
  "variable": [{ "key": "base_url", "value": "https://horse-jockey-challenge-2.onrender.com" }]
}
```
