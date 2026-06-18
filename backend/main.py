import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import engine, Base, SessionLocal
from models import Meeting
from router import router
from seed_data import seed_database
from status_updater import update_meeting_statuses
from results_ingestor import ingest_race_results
from points_calculator import recalculate_all_points
from status_manager import scrape_all_bookmakers
from db_writer import start_writer, stop_writer
from scrapers.shared import shutdown_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _keep_alive():
    port = os.environ.get("PORT", "8000")
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if external_url:
        url = external_url
    else:
        url = f"http://localhost:{port}"
    try:
        httpx.get(url, timeout=10)
    except Exception:
        pass


async def _seed_background():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _seed_sync)


def _seed_sync():
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    try:
        scrape_all_bookmakers()
    except Exception as e:
        logger.error(f"Initial bookmaker scrape failed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    Base.metadata.create_all(bind=engine)

    # Start the single DB writer thread
    start_writer()

    logger.info("Seeding database in background...")
    asyncio.create_task(_seed_background())

    # Split status engine into 3 focused jobs:
    # 1. Status updater: time-based transitions (every 30s)
    scheduler.add_job(
        update_meeting_statuses,
        "interval",
        seconds=30,
        id="status_updater",
        name="Update meeting statuses",
        replace_existing=True,
    )
    # 2. Results ingestor: fetch race results from APIs (every 30s)
    scheduler.add_job(
        ingest_race_results,
        "interval",
        seconds=30,
        id="results_ingestor",
        name="Ingest race results",
        replace_existing=True,
        # Offset by 10s so it runs AFTER status_updater
        next_run_time=None,
    )
    # 3. Points calculator: recalculate from DB results (every 60s)
    scheduler.add_job(
        recalculate_all_points,
        "interval",
        seconds=60,
        id="points_calculator",
        name="Calculate participant points",
        replace_existing=True,
    )
    # Bookmaker price scraper (every 120s)
    scheduler.add_job(
        scrape_all_bookmakers,
        "interval",
        seconds=120,
        id="scrape_bookmakers",
        name="Scrape bookmaker prices",
        replace_existing=True,
    )
    scheduler.add_job(
        _keep_alive,
        "interval",
        seconds=300,
        id="keep_alive",
        name="Keep-alive ping",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started with 3-job status engine + bookmaker scraper")

    yield

    logger.info("Shutting down...")
    scheduler.shutdown(wait=True)
    stop_writer()
    shutdown_pool()


app = FastAPI(
    title="Jockey & Driver Challenge API",
    version="2.0.0",
    lifespan=lifespan,
)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, tags=["meetings"])


@app.get("/")
def root():
    return {"status": "ok", "message": "Jockey & Driver Challenge API"}


@app.get("/ping")
def ping():
    return {"pong": True}
