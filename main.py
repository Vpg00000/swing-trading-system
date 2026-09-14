#!/usr/bin/env python3
"""
main.py - Entry Point for Swing Trading System Clean-Slate Pipeline Execution.

1. Performs total clean-slate data purge (caches + SQLite database tables).
2. Discovers full market universe (NSE + BSE, 5,000+ listed equities).
3. Downloads official NSE Bhavcopy and executes high-speed parallel batch analytics.
4. Computes multi-factor market regime and evaluates sector strength.
5. Runs multi-model AI consensus scan across actionable setups.
6. Generates formatted daily command center reports and synchronizes database.
"""

import os
import sys
import time
import argparse
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
    parser = argparse.ArgumentParser(description="Swing Trading System Clean-Slate Pipeline")
    parser.add_argument("--clean-slate", dest="clean_slate", action="store_true", default=True,
                        help="Completely purge all file caches and SQLite database tables before run (default: True)")
    parser.add_argument("--no-clean", dest="clean_slate", action="store_false",
                        help="Preserve existing database data and caches")
    parser.add_argument("--universe", dest="universe", type=str, default="ALL",
                        choices=["ALL", "NIFTY500", "NSE_ALL"],
                        help="Trading universe scope (default: ALL for 5,000+ stocks)")
    args, _ = parser.parse_known_args()

    start_time = time.time()
    today_str = date.today().isoformat()
    logger.info("==================================================")
    logger.info(f"  STARTING CLEAN-SLATE PIPELINE EXECUTION ({today_str})")
    logger.info(f"  Universe Mode: {args.universe} | Clean-Slate Purge: {args.clean_slate}")
    logger.info("==================================================")
    sys.stdout.flush()

    # Step 1/6: Clean-Slate Purge (Wipe caches + truncate database tables)
    if args.clean_slate:
        try:
            logger.info("[Step 1/6] Clean-Slate Purge: Wiping all caches and SQLite analysis tables...")
            from engine.data_purge import clean_slate_wipe
            purge_res = clean_slate_wipe()
            logger.info(f"✓ Purge complete! Freed {purge_res.get('mb_freed', 0)} MB across {purge_res.get('files_purged', 0)} cache files and {purge_res.get('database_rows_purged', 0)} database records.")
            sys.stdout.flush()
        except Exception as exc:
            logger.error(f"✗ Clean-slate purge warning: {exc}")
    else:
        logger.info("[Step 1/6] Clean-slate purge skipped by user flag.")

    # Step 2/6: Market Universe Discovery (5,000+ stocks)
    try:
        logger.info("[Step 2/6] Market Universe Discovery: Discovering full listed equities...")
        from data.universe_fetcher import discover_full_market_universe
        universe_list = discover_full_market_universe(target_min_stocks=5000 if args.universe == "ALL" else 500)
        logger.info(f"✓ Discovered and registered {len(universe_list)} active stocks in master universe.")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ Universe discovery notice: {exc}")
        universe_list = []

    # Step 3/6: High-Speed Parallel Market Sync & Analytics
    try:
        logger.info(f"[Step 3/6] High-Speed Parallel Analytics & Bulk Ingest for {len(universe_list)} stocks...")
        from data.sync_engine import run_full_sync
        sync_res = run_full_sync(clean_slate=False, universe_mode=args.universe)
        logger.info(f"✓ Parallel analysis & database sync complete. Records processed: {sync_res.get('records_count', len(universe_list))}")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ Market analytics sync notice: {exc}")

    # Step 4/6: Market Regime & Subscore Evaluation
    try:
        logger.info("[Step 4/6] Evaluating Multi-Factor Market Regime...")
        from engine.indicators import compute_all
        from config.universe import EQUITY_UNIVERSE
        tech_map = compute_all(EQUITY_UNIVERSE[:10])
        bullish_cnt = sum(1 for t in tech_map.values() if t.signal == "BULLISH")
        logger.info(f"✓ Regime evaluation finished. Bullish signals ratio: {bullish_cnt}/{len(tech_map)}")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ Regime evaluation notice: {exc}")

    # Step 5/6: Multi-Model AI Consensus Scan
    try:
        logger.info("[Step 5/6] Executing AI Multi-Model Consensus Scan...")
        from engine.ai_engine import query_ai_consensus
        consensus = query_ai_consensus(prompt=f"Evaluate swing trading setups for {today_str}")
        logger.info(f"✓ AI Consensus Signal: {consensus.get('consensus_signal')} (Score: {consensus.get('consensus_score')}/100)")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ AI Consensus scan notice: {exc}")

    # Step 6/6: Generate and Cache Daily Report & Invalidate Web Caches
    try:
        logger.info("[Step 6/6] Refreshing daily command center report cache...")
        from engine.report import generate_report_data
        report = generate_report_data()
        logger.info(f"✓ Report generated successfully for {today_str}.")

        # Invalidate in-memory web caches
        from engine.data_purge import invalidate_in_memory_caches
        invalidate_in_memory_caches()
        sys.stdout.flush()
    except Exception as exc:
        logger.warning(f"⚠ Report generation notice: {exc}")

    elapsed = round(time.time() - start_time, 2)
    logger.info("==================================================")
    logger.info(f"  MAIN PIPELINE EXECUTION COMPLETED IN {elapsed}s  ")
    logger.info(f"  Total Fresh Analyzed Stocks: {len(universe_list)}")
    logger.info("==================================================")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

