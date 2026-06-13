import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import engine, Base, SessionLocal
from models import Meeting
from router import router
from seed_data import seed_database
from status_manager import refresh_meeting_status, scrape_all_bookmakers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    scheduler.add_job(
        refresh_meeting_status,
        "interval",
        minutes=7,
        id="refresh_status",
        name="Refresh meeting status",
        replace_existing=True,
    )
    scheduler.add_job(
        scrape_all_bookmakers,
        "interval",
        minutes=10,
        id="scrape_bookmakers",
        name="Scrape bookmaker prices",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started.")

    yield

    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Jockey & Driver Challenge API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://jockey-driver-dashboard.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, tags=["meetings"])


@app.get("/")
def root():
    return {"status": "ok", "message": "Jockey & Driver Challenge API"}
