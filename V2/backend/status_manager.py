"""Bookmaker price scraper coordinator.

V2: Scraping has been removed. The AI price model is now purely
probability-based with no bookmaker odds dependency.

This module is retained as a no-op for scheduler compatibility.
"""
import logging

logger = logging.getLogger(__name__)


def scrape_all_bookmakers():
    """No-op: bookmaker scraping removed in V2 (bookmaker-free model)."""
    pass
