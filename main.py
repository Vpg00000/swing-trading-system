#!/usr/bin/env python3
"""
main.py - Entry Point for Swing Trading System Pipeline Execution.

Performs complete data sync up to current date (date.today()), updates SQLite database,
computes market regime, calculates opportunity scores, and generates formatted reports.
"""

import os
import sys
import time
import logging
from datetime import date, datetime

# Force unbuffered stdout/stderr line output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

class UnbufferedHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[UnbufferedHandler(sys.stdout)]
)
logger = logging.getLogger("main_pipeline")

def main():
    start_time = time.time()
    today_str = date.today().isoformat()
    logger.info(f"==================================================")
    logger.info(f"  STARTING MAIN PIPELINE EXECUTION ({today_str})  ")
    logger.info(f"==================================================")
    sys.stdout.flush()

    # 1. Initialize Database Schema
    try:
        logger.info("[Step 1/5] Initializing SQLite database schema...")
        from data.database import init_db
        init_db()
        logger.info("✓ Database schema verified successfully.")
        sys.stdout.flush()
    except Exception as exc:
        logger.error(f"✗ Database initialization error: {exc}")

    # 2. Run Full Data Sync (NSE Bhavcopy, Technical Indicators, Fundamentals)
    try:
        logger.info("[Step 2/5] Running One-Click Data Sync for Nifty Universe...")
        from data.sync_engine import run_full_sync
        sync_res = run_full_sync()
        logger.info(f"✓ Data sync completed. Status: {sync_res.get('status')}, Records processed: {sync_res.get('records_count', 0)}")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ Data sync notice: {exc}")

    # 3. Market Regime & Subscore Evaluation
    try:
        logger.info("[Step 3/5] Evaluating Multi-Factor Market Regime...")
        from engine.indicators import compute_all
        from config.universe import EQUITY_UNIVERSE
        tech_map = compute_all(EQUITY_UNIVERSE[:10])
        bullish_cnt = sum(1 for t in tech_map.values() if t.signal == "BULLISH")
        logger.info(f"✓ Regime evaluation finished. Bullish signals ratio: {bullish_cnt}/{len(tech_map)}")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ Regime evaluation notice: {exc}")

    # 4. Multi-Model AI Consensus Scan
    try:
        logger.info("[Step 4/5] Executing AI Multi-Model Consensus Scan...")
        from engine.ai_engine import query_ai_consensus
        consensus = query_ai_consensus(prompt=f"Evaluate swing trading setups for {today_str}")
        logger.info(f"✓ AI Consensus Signal: {consensus.get('consensus_signal')} (Score: {consensus.get('consensus_score')}/100)")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ AI Consensus scan notice: {exc}")

    # 5. Generate and Cache Daily Report
    try:
        logger.info("[Step 5/5] Refreshing daily command center report cache...")
        from engine.report import generate_report_data
        report = generate_report_data()
        logger.info(f"✓ Report generated successfully for {today_str}.")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ Report generation notice: {exc}")

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"==================================================")
    logger.info(f"  MAIN PIPELINE EXECUTION COMPLETED IN {elapsed}s  ")
    logger.info(f"==================================================")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
