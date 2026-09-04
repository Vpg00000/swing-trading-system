"""
FastAPI Web Server for the Swing Trading System Dashboard.
Runs locally at http://localhost:8000.
"""

import os
import sys
import logging
from typing import Optional, List
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.report import generate_report_data, build_report

app = FastAPI(title="Swing Trading System Dashboard")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "web"
RESEARCH_DIR = PROJECT_ROOT / "reports" / "research"

# Cache report data in-memory to prevent yfinance rate limiting / slow loads on refresh
# We cache it with a TTL of 1 hour or manually refreshable.
import time
_cache = {
    "data": None,
    "timestamp": 0.0
}
CACHE_TTL = 3600  # 1 hour in seconds


REPORT_CACHE_FILE = PROJECT_ROOT / "reports" / "latest_report_cache.json"

def get_cached_report_data(force_refresh: bool = False) -> dict:
    current_time = time.time()
    
    # 1. Try disk cache if not forcing refresh
    if not force_refresh and _cache["data"] is None:
        if REPORT_CACHE_FILE.exists():
            try:
                import json
                data = json.loads(REPORT_CACHE_FILE.read_text(encoding="utf-8"))
                _cache["data"] = data
                _cache["timestamp"] = current_time
                logging.info(f"Loaded instant report data from disk cache ({REPORT_CACHE_FILE.name})")
                return data
            except Exception as exc:
                logging.warning(f"Disk report cache read failed: {exc}")

    # 2. If cache is old or not available, refresh it
    if force_refresh or _cache["data"] is None:
        try:
            data = generate_report_data()
            _cache["data"] = data
            _cache["timestamp"] = current_time
            with REPORT_CACHE_FILE.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logging.info(f"Report data refreshed and cached ({REPORT_CACHE_FILE.name})")
            return data
        except Exception as exc:
            logging.error(f"Failed to generate report data: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))

    return _cache["data"]

@app.get("/report")
async def get_report():
    """Endpoint to get cached report data."""
    try:
        data = get_cached_report_data()
        return JSONResponse(content=data)
    except HTTPException as e:
        return e

@app.get("/api/dhan/market_data")
async def get_dhan_market_data():
    """Endpoint to fetch live market data from Dhan."""
    try:
        from data.dhan.client import DhanClient
        client = DhanClient()
        market_data = client.get_market_data()
        return JSONResponse(content=market_data)
    except Exception as exc:
        logging.error(f"Failed to fetch Dhan market data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))