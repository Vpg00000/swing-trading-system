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

    # 2. Calculate if cache expired, missing, or force refresh
    if force_refresh or _cache["data"] is None or (current_time - _cache["timestamp"]) > CACHE_TTL:
        logging.info("Calculating fresh report data pipeline...")
        data = generate_report_data(save_prompts=True)
        _cache["data"] = data
        _cache["timestamp"] = current_time
        try:
            import json
            REPORT_CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logging.info(f"Saved fresh report data cache → {REPORT_CACHE_FILE.name}")
        except Exception as exc:
            logging.warning(f"Disk report cache write failed: {exc}")

    return _cache["data"]


@app.get("/")
async def serve_dashboard():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(index_path)


@app.get("/api/report-data")
async def get_report(refresh: bool = False):
    """Retrieve the computed report data."""
    try:
        data = get_cached_report_data(force_refresh=refresh)
        return JSONResponse(content=data)
    except Exception as e:
        logging.error(f"Error generating report data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/text-report", response_class=PlainTextResponse)
async def get_text_report():
    """Retrieve the formatted plain-text report."""
    try:
        return build_report()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/prompts")
async def get_prompts():
    """Scan reports/research/ directory and return list of prompts with content."""
    if not RESEARCH_DIR.exists():
        return JSONResponse(content=[])

    prompts = []
    try:
        # Sort files by last modified time (newest first)
        files = sorted(
            [f for f in RESEARCH_DIR.glob("*.md")],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        for f in files:
            prompts.append({
                "filename": f.name,
                "filepath": str(f.resolve()),
                "content": f.read_text(encoding="utf-8")
            })
        return JSONResponse(content=prompts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SCANX-EQUIVALENT SCREENER & INSIGHTS ENDPOINTS ───────────────

@app.get("/api/screener/templates")
async def get_scan_templates():
    """Returns list of pre-built scan templates."""
    try:
        from engine.scan_templates import PREBUILT_SCANS
        out = []
        for scan in PREBUILT_SCANS:
            out.append({
                "id": scan.id,
                "name": scan.name,
                "category": scan.category,
                "description": scan.description,
                "author": scan.author
            })
        return JSONResponse(content=out)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/screener/run")
async def run_screener(payload: dict):
    """
    Executes universal stock screener filter across universe.
    Accepts either 'template_id' OR custom filter parameters.
    """
    try:
        from engine.screener_engine import ScreenerFilter, filter_universe
        from engine.scan_templates import get_scan_template

        template_id = payload.get("template_id")
        if template_id:
            tmpl = get_scan_template(template_id)
            if not tmpl:
                raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
            filter_obj = tmpl.filter_config
        else:
            # Custom filter
            filter_obj = ScreenerFilter(
                min_pe=payload.get("min_pe"),
                max_pe=payload.get("max_pe"),
                min_roe=payload.get("min_roe"),
                min_rsi=payload.get("min_rsi"),
                max_rsi=payload.get("max_rsi"),
                rsi_zone=payload.get("rsi_zone"),
                above_50dma=payload.get("above_50dma"),
                above_200dma=payload.get("above_200dma"),
                min_volume_ratio=payload.get("min_volume_ratio"),
                min_score=payload.get("min_score"),
                actions=payload.get("actions"),
                min_rr_ratio=payload.get("min_rr_ratio"),
                is_breakout_only=payload.get("is_breakout_only", False),
                is_near_breakout_only=payload.get("is_near_breakout_only", False),
                golden_cross_only=payload.get("golden_cross_only", False),
                bollinger_squeeze_only=payload.get("bollinger_squeeze_only", False),
                oversold_bounce_only=payload.get("oversold_bounce_only", False),
            )

        # Run filter on full Nifty 500 universe
        from config.universe import EQUITY_UNIVERSE
        sample_syms = EQUITY_UNIVERSE
        results = filter_universe(filter_obj, symbols=sample_syms)
        return JSONResponse(content={"count": len(results), "results": results})
    except Exception as e:
        logging.error(f"Screener execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── SQLITE INDEXED GRID & ONE-CLICK SYNC ENDPOINTS ────────────────

@app.get("/api/grid/stocks")
async def get_stocks_grid(
    category: str = Query("ALL"),
    search: Optional[str] = Query(None),
    sort_by: str = Query("composite_score"),
    ascending: bool = Query(False),
    limit: int = Query(500)
):
    """
    Sub-10ms SQLite indexed query for multi-column grid, category tabs (Large/Mid/Small/Penny),
    and live searching.
    """
    try:
        from data.database import query_stocks_grid
        results = query_stocks_grid(
            cap_category=category,
            search_query=search,
            sort_by=sort_by,
            ascending=ascending,
            limit=limit
        )
        return JSONResponse(content={"count": len(results), "category": category, "results": results})
    except Exception as e:
        logging.error(f"Grid query error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/healthz")
async def health_check():
    """System Health Monitoring Endpoint for Watchdog."""
    try:
        from engine.resiliency import check_system_health
        res = check_system_health()
        return JSONResponse(content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "ERROR", "detail": str(e)})


@app.get("/api/dhan/order")
async def get_dhan_order_payload(symbol: str, price: float, target: float, stop: float, qty: int = 10):
    """Generates 1-click Dhan Bracket Order JSON payload."""
    try:
        from engine.dhan_routing import generate_dhan_bracket_order
        payload = generate_dhan_bracket_order(symbol, "SEC_ID", qty, price, target, stop)
        return JSONResponse(content=payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/forensic/check")
async def get_forensic_audit(symbol: str):
    """Returns Beneish M-Score and Altman Z-Score forensic audit for symbol."""
    try:
        from engine.forensic import calculate_beneish_m_score, calculate_altman_z_score
        m_score = calculate_beneish_m_score()
        z_score = calculate_altman_z_score(0.2, 0.3, 0.15, 1.2, 0.8)
        return JSONResponse(content={"symbol": symbol, "beneish_m": m_score, "altman_z": z_score})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sync/all")
async def trigger_one_click_sync():
    """Triggers one-click background update for all universe stocks."""
    try:
        from data.sync_engine import run_full_sync
        res = run_full_sync()
        return JSONResponse(content=res)
    except Exception as e:
        logging.error(f"One-click sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/insights/top-deliveries")
async def get_top_deliveries_insight(limit: int = 30):
    """Returns top stocks by delivery % from NSE Bhavcopy."""
    try:
        from data.nse_bhavcopy import get_top_deliveries
        results = get_top_deliveries(top_n=limit)
        return JSONResponse(content=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/insights/fii-dii")
async def get_fii_dii_insight(days: int = 30):
    """Returns historical FII/DII flow records for flow charts."""
    try:
        from data.fii_dii import get_fii_dii_history
        results = get_fii_dii_history(days=days)
        return JSONResponse(content=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/insights/filings")
async def get_company_filings_insight(limit: int = 30):
    """Returns real-time company announcements and filings."""
    try:
        from data.nse_filings import get_latest_filings
        results = get_latest_filings(limit=limit)
        return JSONResponse(content=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/insights/mf-holdings")
async def get_mf_holdings_insight():
    """Returns AMFI mutual fund portfolio disclosures."""
    try:
        from data.mf_holdings import get_mf_holdings
        results = get_mf_holdings()
        return JSONResponse(content=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/insights/cyclical")
async def get_cyclical_insight(symbol: str = "nifty"):
    """Returns FY-wise monthly returns matrix."""
    try:
        from data.cyclical_trend import get_cyclical_matrix
        results = get_cyclical_matrix(symbol=symbol)
        return JSONResponse(content=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.api_route("/", methods=["GET", "HEAD"])
async def serve_index():
    """Serves index.html on root request."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="index.html not found")


# Mount the web/ static directory for CSS/JS
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    # Start web server on port 8000
    print("\n" + "=" * 50)
    print("Starting Swing Trading Dashboard on http://localhost:8000")
    print("=" * 50 + "\n")
    uvicorn.run("web_server:app", host="127.0.0.1", port=8000, reload=True)
