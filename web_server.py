"""
FastAPI Web Server for the Swing Trading System Dashboard.
Runs locally at http://localhost:8000.
"""

import os
import sys
import logging
import datetime
import time
import json
from typing import Optional, List
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.report import generate_report_data, build_report
from engine.portfolio_manager import fetch_and_store_portfolio_state
try:
    from src.system_health import get_system_health_data
except ImportError:
    from src.system_health.system_health import get_system_health_data

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
_cache = {
    "data": None,
    "timestamp": 0.0
}
CACHE_TTL = 3600  # 1 hour in seconds

REPORT_CACHE_FILE = PROJECT_ROOT / "reports" / "latest_report_cache.json"

def get_cached_report_data(force_refresh: bool = False) -> dict:
    import json
    current_time = time.time()

    # 1. Try disk cache if not forcing refresh
    if not force_refresh and _cache["data"] is None:
        if REPORT_CACHE_FILE.exists():
            try:
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
            import json
            data = generate_report_data()
            _cache["data"] = data
            _cache["timestamp"] = current_time
            with REPORT_CACHE_FILE.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logging.info(f"Report data refreshed and cached ({REPORT_CACHE_FILE.name})")
            return data
        except Exception as exc:
            logging.error(f"Failed to generate report data live: {exc}")
            if _cache["data"] is not None:
                return _cache["data"]
            if REPORT_CACHE_FILE.exists():
                try:
                    import json
                    data = json.loads(REPORT_CACHE_FILE.read_text(encoding="utf-8"))
                    _cache["data"] = data
                    return data
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=str(exc))

    return _cache["data"]

@app.get("/api/report-data")
@app.get("/api/report")
@app.get("/report")
async def get_report(refresh: bool = Query(False)):
    """Endpoint to get cached report data."""
    try:
        data = get_cached_report_data(force_refresh=refresh)
        return JSONResponse(content=data)
    except HTTPException as e:
        raise e

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

@app.get("/api/portfolio")
async def get_portfolio():
    """Endpoint to fetch and store the latest Dhan portfolio state."""
    try:
        portfolio_data = fetch_and_store_portfolio_state()
        return JSONResponse(content=portfolio_data)
    except Exception as exc:
        logging.error(f"Failed to fetch and store portfolio state: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/health")
async def get_health():
    """Endpoint to get system health data."""
    try:
        health_data = get_system_health_data()
        return JSONResponse(content=health_data)
    except HTTPException as e:
        raise e

@app.get("/api/microstructure")
async def get_microstructure(
    symbol: Optional[str] = Query(None),
    depth: int = Query(10)
):
    """Endpoint to fetch market microstructure metrics including OBI."""
    try:
        import data.microstructure as ms
        data = None
        if hasattr(ms, "get_microstructure_data"):
            data = ms.get_microstructure_data(symbol=symbol, depth=depth)
        elif hasattr(ms, "get_microstructure_metrics"):
            data = ms.get_microstructure_metrics(symbol=symbol, depth=depth)
        elif hasattr(ms, "calculate_obi"):
            import inspect
            sig = inspect.signature(ms.calculate_obi)
            if "symbol" in sig.parameters:
                data = ms.calculate_obi(symbol=symbol, depth=depth)
            else:
                obi_val = ms.calculate_obi([], [], depth=depth)
                data = {"symbol": symbol, "depth": depth, "obi": obi_val}
        else:
            data = {"symbol": symbol, "depth": depth, "obi": 0.0}

        if not isinstance(data, dict):
            data = {"symbol": symbol, "depth": depth, "obi": float(data) if data is not None else 0.0}

        return JSONResponse(content=data)
    except Exception as exc:
        logging.error(f"Failed to fetch microstructure metrics: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/sectors")
async def get_sectors():
    """Endpoint to fetch sector scoring and rotation pipeline results."""
    try:
        import engine.sector_score as sector_score_mod

        data = None
        for fn_name in [
            "get_sector_scores",
            "calculate_sector_scores",
            "compute_sector_scores",
            "get_sector_ranks",
            "get_sector_rotation",
            "run_sector_pipeline",
        ]:
            if hasattr(sector_score_mod, fn_name):
                fn = getattr(sector_score_mod, fn_name)
                if callable(fn):
                    data = fn()
                    if data is not None:
                        break

        if data is None and hasattr(sector_score_mod, "SectorScorer"):
            scorer_cls = getattr(sector_score_mod, "SectorScorer")
            scorer = scorer_cls()
            for method_name in ["get_scores", "calculate", "run", "calculate_scores", "get_sector_scores"]:
                if hasattr(scorer, method_name):
                    method = getattr(scorer, method_name)
                    if callable(method):
                        data = method()
                        if data is not None:
                            break

        if data is None and hasattr(sector_score_mod, "main"):
            data = sector_score_mod.main()

        if data is None:
            raise HTTPException(
                status_code=500,
                detail="Sector scoring pipeline returned no data or could not be executed"
            )

        if hasattr(data, "to_dict"):
            data = data.to_dict(orient="records")

        if isinstance(data, list):
            data = {
                "sectors": data,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        elif isinstance(data, dict) and "timestamp" not in data:
            data["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return JSONResponse(content=data)
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Failed to fetch sector scores: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/flow")
async def get_flow(symbol: Optional[str] = Query(None)):
    """Endpoint to fetch verified institutional and money flow metrics."""
    try:
        data = None

        try:
            import data.institutional_flow as inst_flow
            for fn_name in ["get_institutional_flow", "get_flow_data", "get_institutional_summary", "fetch_institutional_flow"]:
                if hasattr(inst_flow, fn_name):
                    fn = getattr(inst_flow, fn_name)
                    if callable(fn):
                        try:
                            data = fn(symbol=symbol) if symbol else fn()
                        except TypeError:
                            data = fn()
                        if data is not None:
                            break
        except Exception as e:
            logging.warning(f"Error calling institutional_flow module: {e}")

        if data is None:
            try:
                import engine.money_flow as mf
                for fn_name in ["get_money_flow", "get_flow_summary", "get_flow_data", "calculate_money_flow"]:
                    if hasattr(mf, fn_name):
                        fn = getattr(mf, fn_name)
                        if callable(fn):
                            try:
                                data = fn(symbol=symbol) if symbol else fn()
                            except TypeError:
                                data = fn()
                            if data is not None:
                                break
            except Exception as e:
                logging.warning(f"Error calling money_flow module: {e}")

        if data is None:
            try:
                import data.fii_dii as fii_dii
                for fn_name in ["get_fii_dii_data", "get_latest_fii_dii", "get_fii_dii_summary", "fetch_fii_dii"]:
                    if hasattr(fii_dii, fn_name):
                        fn = getattr(fii_dii, fn_name)
                        if callable(fn):
                            data = fn()
                            if data is not None:
                                break
            except Exception as e:
                logging.warning(f"Error calling fii_dii module: {e}")

        if data is None:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "unavailable",
                    "message": "Institutional flow data is unavailable or stale",
                    "symbol": symbol,
                    "data": None
                }
            )

        if hasattr(data, "to_dict"):
            data = data.to_dict(orient="records")

        return JSONResponse(content=data)
    except Exception as exc:
        logging.error(f"Failed to fetch flow data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        index_file = WEB_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return PlainTextResponse("Swing Trading System Dashboard UI")