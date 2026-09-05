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
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.report import generate_report_data, build_report
from engine.portfolio_manager import fetch_and_store_portfolio_state, reconcile_portfolio_state, generate_portfolio_snapshot
from engine.priced_in import classify_priced_in
try:
    from src.system_health import get_system_health_data
except ImportError:
    from src.system_health.system_health import get_system_health_data

# Define sensitive keys for redaction (lowercase for case-insensitive matching)
SENSITIVE_KEYS = {
    "api_key", "access_token", "client_id", "client_secret",
    "password", "auth_token", "secret", "dhan_access_token",
    "dhan_client_id", "dhan_token", "trading_token"
}

def redact_sensitive_data(data):
    """Recursively redacts sensitive keys in a dictionary or list of dictionaries."""
    if isinstance(data, dict):
        redacted_data = {}
        for key, value in data.items():
            if key.lower() in SENSITIVE_KEYS:
                redacted_data[key] = "[REDACTED]"
            else:
                redacted_data[key] = redact_sensitive_data(value)
        return redacted_data
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    else:
        return data

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
    current_time = time.time()

    # 1. Try disk cache if not forcing refresh or if in-memory cache is empty
    if not force_refresh and _cache["data"] is None:
        if REPORT_CACHE_FILE.exists():
            try:
                data = json.loads(REPORT_CACHE_FILE.read_text(encoding="utf-8"))
                # Redact data immediately after loading from disk
                redacted_data = redact_sensitive_data(data)
                _cache["data"] = redacted_data # Cache redacted version
                _cache["timestamp"] = current_time
                logging.info(f"Loaded instant report data from disk cache ({REPORT_CACHE_FILE.name})")
                return redacted_data
            except Exception as exc:
                logging.warning(f"Disk report cache read failed: {exc}")

    # 2. If cache is old, not available, or force_refresh is true, refresh it
    if force_refresh or _cache["data"] is None or (current_time - _cache["timestamp"]) > CACHE_TTL:
        try:
            data = generate_report_data()
            # Redact data immediately after generation
            redacted_data = redact_sensitive_data(data)
            _cache["data"] = redacted_data # Cache the redacted version
            _cache["timestamp"] = current_time
            with REPORT_CACHE_FILE.open('w', encoding='utf-8') as f:
                json.dump(redacted_data, f, ensure_ascii=False, indent=4) # Write redacted version to disk
            logging.info(f"Report data refreshed and cached ({REPORT_CACHE_FILE.name})")
            return redacted_data
        except Exception as exc:
            logging.error(f"Failed to generate report data live: {exc}")
            if _cache["data"] is not None:
                # If cached data exists, it should already be redacted
                return _cache["data"]
            # If live generation failed, try loading from disk as a fallback
            if REPORT_CACHE_FILE.exists():
                try:
                    data = json.loads(REPORT_CACHE_FILE.read_text(encoding="utf-8"))
                    redacted_data = redact_sensitive_data(data)
                    _cache["data"] = redacted_data # Cache redacted version
                    return redacted_data
                except Exception:
                    pass # Failed to load from disk cache after live gen failure
            raise HTTPException(status_code=500, detail=str(exc))

    # If none of the above, return the existing (and already redacted) cache
    return _cache["data"]

@app.get("/api/report-data")
@app.get("/api/report")
@app.get("/report")
async def get_report(refresh: bool = Query(False)):
    """Endpoint to get cached report data."""
    try:
        # get_cached_report_data already returns redacted data
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
        # Redact market_data before sending in the response
        return JSONResponse(content=redact_sensitive_data(market_data))
    except Exception as exc:
        logging.error(f"Failed to fetch Dhan market data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/portfolio")
async def get_portfolio():
    """Endpoint to fetch, store, and reconcile the latest Dhan portfolio state."""
    try:
        portfolio_data = fetch_and_store_portfolio_state()
        reconciled_state = reconcile_portfolio_state(portfolio_data)
        snapshot = generate_portfolio_snapshot(reconciled_state)
        # Redact snapshot before sending in the response
        return JSONResponse(content=redact_sensitive_data(snapshot))
    except Exception as exc:
        logging.error(f"Failed to fetch and store portfolio state: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/health")
async def get_health():
    """Endpoint to get system health data."""
    try:
        health_data = get_system_health_data()
        # Redact health_data just in case it contains sensitive configuration
        return JSONResponse(content=redact_sensitive_data(health_data))
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

@app.get("/api/forensics")
@app.get("/api/forensic")
async def get_forensics(symbol: Optional[str] = Query(None)):
    """Endpoint to fetch forensic and governance metrics."""
    try:
        forensic_data = None
        governance_data = None

        try:
            import engine.forensic as forensic_mod
            for fn_name in ["get_forensic_score", "get_forensic_data", "analyze_forensics", "calculate_forensic_score", "get_forensics", "run_forensic_analysis"]:
                if hasattr(forensic_mod, fn_name):
                    fn = getattr(forensic_mod, fn_name)
                    if callable(fn):
                        try:
                            forensic_data = fn(symbol=symbol) if symbol else fn()
                        except TypeError:
                            forensic_data = fn()
                        if forensic_data is not None:
                            break
            if forensic_data is None and hasattr(forensic_mod, "ForensicAnalyzer"):
                analyzer_cls = getattr(forensic_mod, "ForensicAnalyzer")
                analyzer = analyzer_cls()
                for m_name in ["analyze", "get_scores", "calculate", "run", "analyze_symbol"]:
                    if hasattr(analyzer, m_name):
                        m = getattr(analyzer, m_name)
                        if callable(m):
                            try:
                                forensic_data = m(symbol=symbol) if symbol else m()
                            except TypeError:
                                forensic_data = m()
                            if forensic_data is not None:
                                break
        except Exception as e:
            logging.warning(f"Error calling forensic module: {e}")

        try:
            import engine.governance as governance_mod
            for fn_name in ["get_governance_score", "get_governance_data", "analyze_governance", "calculate_governance_score", "get_governance", "run_governance_analysis"]:
                if hasattr(governance_mod, fn_name):
                    fn = getattr(governance_mod, fn_name)
                    if callable(fn):
                        try:
                            governance_data = fn(symbol=symbol) if symbol else fn()
                        except TypeError:
                            governance_data = fn()
                        if governance_data is not None:
                            break
            if governance_data is None and hasattr(governance_mod, "GovernanceAnalyzer"):
                analyzer_cls = getattr(governance_mod, "GovernanceAnalyzer")
                analyzer = analyzer_cls()
                for m_name in ["analyze", "get_scores", "calculate", "run", "analyze_symbol"]:
                    if hasattr(analyzer, m_name):
                        m = getattr(analyzer, m_name)
                        if callable(m):
                            try:
                                governance_data = m(symbol=symbol) if symbol else m()
                            except TypeError:
                                governance_data = m()
                            if governance_data is not None:
                                break
        except Exception as e:
            logging.warning(f"Error calling governance module: {e}")

        if forensic_data is None and governance_data is None:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "unavailable",
                    "message": "Forensic and governance data is unavailable or could not be generated",
                    "symbol": symbol,
                    "forensics": None,
                    "governance": None
                }
            )

        if hasattr(forensic_data, "to_dict"):
            forensic_data = forensic_data.to_dict()
        if hasattr(governance_data, "to_dict"):
            governance_data = governance_data.to_dict()

        result = {
            "symbol": symbol,
            "forensics": forensic_data,
            "governance": governance_data,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        return JSONResponse(content=result)
    except Exception as exc:
        logging.error(f"Failed to fetch forensic data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/priced-in")
async def get_priced_in(symbol: str = Query(...)):
    """Endpoint to fetch priced-in analysis for a stock symbol."""
    try:
        priced_in_data = classify_priced_in(symbol)

        if priced_in_data is None:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "unavailable",
                    "message": "Priced-in analysis data is unavailable or could not be generated",
                    "symbol": symbol,
                    "priced_in": None
                }
            )

        # Ensure classification is one of the allowed values
        allowed_classifications = ["UNDER PRICED", "PARTIALLY PRICED", "FULLY PRICED", "OVERPRICED", "UNKNOWN"]
        if priced_in_data.get("classification") not in allowed_classifications:
            priced_in_data["classification"] = "UNKNOWN"

        # Ensure confidence_score is a float between 0 and 1
        if not isinstance(priced_in_data.get("confidence_score"), float) or priced_in_data.get("confidence_score") < 0 or priced_in_data.get("confidence_score") > 1:
            priced_in_data["confidence_score"] = 0.0

        # Structure output into evidence and inference sections
        result = {
            "symbol": symbol,
            "priced_in": {
                "evidence": {
                    "price_delta": priced_in_data.get("price_delta"),
                    "valuation_multiples": priced_in_data.get("valuation_multiples"),
                    "volume_delivery": priced_in_data.get("volume_delivery"),
                    "numerical_breakdown": priced_in_data.get("numerical_breakdown")
                },
                "inference": {
                    "classification": priced_in_data.get("classification"),
                    "confidence_score": priced_in_data.get("confidence_score"),
                    "rationale": priced_in_data.get("rationale")
                }
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        return JSONResponse(content=result)
    except Exception as exc:
        logging.error(f"Failed to fetch priced-in analysis: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        index_file = WEB_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return PlainTextResponse("Swing Trading System Dashboard UI")