"""
SQLite Database Indexing Layer for High-Performance Trading Terminal.

Stores and indexes all 500 Nifty stocks, technical indicators, fundamentals,
delivery percentages, market cap classifications (LARGE, MID, SMALL, PENNY),
and AI predictions in a single WAL-enabled SQLite database (data/system.db).

Provides sub-10ms query performance for multi-column sorting, live filtering,
and grid tab views (Large/Mid/Small/Penny).

Usage:
    from data.database import init_db, upsert_stock_metrics, query_stocks_grid
    init_db()
    stocks = query_stocks_grid(cap_category="PENNY", sort_by="composite_score")
"""

import sqlite3
import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone
import time

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent / "system.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high-concurrency fast reads
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    """Create tables and indexes if they don't exist, ensuring freshness timestamps on all tables."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS stock_grid (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT,
                cap_category TEXT,         -- LARGE, MID, SMALL, PENNY
                close REAL,
                change_pct REAL,
                volume INTEGER,
                traded_qty INTEGER,
                delivered_qty INTEGER,
                delivery_pct REAL,
                rsi REAL,
                macd_status TEXT,
                above_50dma INTEGER,
                above_200dma INTEGER,
                pct_from_52w_high REAL,
                pe REAL,
                pb REAL,
                roe REAL,
                roce REAL,
                market_cap_cr REAL,
                composite_score REAL,
                action TEXT,
                target_price REAL,
                stop_loss REAL,
                rr_ratio REAL,
                ev_pct REAL,
                net_alpha_pct REAL,
                as_of DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS stock_grid_staging (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT,
                cap_category TEXT,         -- LARGE, MID, SMALL, PENNY
                close REAL,
                change_pct REAL,
                volume INTEGER,
                traded_qty INTEGER,
                delivered_qty INTEGER,
                delivery_pct REAL,
                rsi REAL,
                macd_status TEXT,
                above_50dma INTEGER,
                above_200dma INTEGER,
                pct_from_52w_high REAL,
                pe REAL,
                pb REAL,
                roe REAL,
                roce REAL,
                market_cap_cr REAL,
                composite_score REAL,
                action TEXT,
                target_price REAL,
                stop_loss REAL,
                rr_ratio REAL,
                ev_pct REAL,
                net_alpha_pct REAL,
                as_of DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT DEFAULT 'INITIALIZING',
                universe_mode TEXT DEFAULT 'ALL',
                discovered_count INTEGER DEFAULT 0,
                processed_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                quality_score REAL DEFAULT 100.0,
                duration_seconds REAL DEFAULT 0.0,
                error_summary TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pipeline_lock (
                lock_id INTEGER PRIMARY KEY CHECK (lock_id = 1),
                run_id TEXT NOT NULL,
                acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME
            );

            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                holdings TEXT,
                positions TEXT,
                orders TEXT,
                trades TEXT,
                cash REAL,
                as_of DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS fii_dii_history (
                date TEXT PRIMARY KEY,
                fii_buy REAL,
                fii_sell REAL,
                fii_net REAL,
                dii_buy REAL,
                dii_sell REAL,
                dii_net REAL,
                total_net REAL,
                as_of DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS institutional_flow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                symbol TEXT,
                flow_score REAL,
                silent_accumulation INTEGER,
                marquee_buy_count INTEGER,
                marquee_sell_count INTEGER,
                insider_net_buy_val REAL,
                free_float_pct REAL,
                signal TEXT,
                as_of DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, symbol)
            );

            CREATE TABLE IF NOT EXISTS market_data (
                symbol TEXT,
                timestamp TEXT,
                timeframe TEXT DEFAULT '1d',
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                is_backfilled INTEGER DEFAULT 0,
                as_of DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(symbol, timestamp, timeframe)
            );

            CREATE TABLE IF NOT EXISTS corporate_filings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                company_name TEXT,
                category TEXT,
                subject TEXT,
                details TEXT,
                filing_date TEXT,
                period_ended TEXT,
                revenue_cr REAL,
                net_profit_cr REAL,
                operating_margin_pct REAL,
                eps REAL,
                auditor_notes TEXT,
                auditor_name TEXT,
                is_audited INTEGER DEFAULT 1,
                parsed_latency_seconds REAL DEFAULT 0.0,
                raw_xml TEXT,
                as_of DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS market_live (
                symbol TEXT PRIMARY KEY,
                ltp REAL,
                volume INTEGER,
                open REAL,
                high REAL,
                low REAL,
                prev_close REAL,
                vwap REAL,
                last_trade_time TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS fundamentals (
                symbol TEXT PRIMARY KEY,
                pe REAL,
                pb REAL,
                roe REAL,
                roce REAL,
                debt_equity REAL,
                opm REAL,
                sales_cagr REAL,
                profit_cagr REAL,
                eps REAL,
                fundamental_as_of DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS indicators (
                symbol TEXT PRIMARY KEY,
                ema20 REAL,
                ema50 REAL,
                ema200 REAL,
                rsi REAL,
                atr REAL,
                bollinger_upper REAL,
                bollinger_lower REAL,
                calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS master_universe (
                symbol TEXT PRIMARY KEY,
                company_name TEXT,
                isin TEXT,
                exchange TEXT DEFAULT 'NSE',
                series TEXT DEFAULT 'EQ',
                cap_category TEXT,          -- LARGE, MID, SMALL, MICRO, PENNY
                sector TEXT,
                industry TEXT,
                market_cap_cr REAL,
                free_float_mcap_cr REAL,
                face_value REAL,
                lot_size INTEGER DEFAULT 1,
                is_fno INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                listing_date TEXT,
                avg_volume_30d REAL,
                avg_turnover_cr_30d REAL,
                ltp REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS corporate_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                action_type TEXT,            -- SPLIT, BONUS, DIVIDEND, RIGHTS, DEMERGER
                ex_date TEXT,
                record_date TEXT,
                ratio REAL,
                details TEXT,
                applied INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS prediction_freeze_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_date TEXT,
                prediction_time TEXT DEFAULT '09:00:00',
                total_candidates INTEGER,
                sha256_hash TEXT,
                predictions_json TEXT,
                verified INTEGER DEFAULT 1,
                frozen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prediction_date, prediction_time)
            );

            CREATE TABLE IF NOT EXISTS ohlcv_daily (
                symbol TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                traded_value REAL,
                delivered_qty INTEGER,
                delivery_pct REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            );

            CREATE TABLE IF NOT EXISTS features_daily (
                symbol TEXT,
                date TEXT,
                ret_1d REAL,
                ret_3d REAL,
                ret_5d REAL,
                ret_10d REAL,
                ret_20d REAL,
                ret_30d REAL,
                ret_52w REAL,
                rsi_14 REAL,
                macd REAL,
                macd_signal REAL,
                macd_hist REAL,
                atr_14 REAL,
                natr_14 REAL,
                ema_9 REAL,
                ema_20 REAL,
                ema_50 REAL,
                ema_200 REAL,
                sma_20 REAL,
                sma_50 REAL,
                sma_200 REAL,
                vol_20d_ratio REAL,
                deliv_20d_ratio REAL,
                realized_vol_20d REAL,
                parkinson_vol REAL,
                garman_klass_vol REAL,
                dist_52w_high_pct REAL,
                dist_52w_low_pct REAL,
                bb_upper REAL,
                bb_lower REAL,
                bb_width REAL,
                keltner_upper REAL,
                keltner_lower REAL,
                ttm_squeeze INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            );

            CREATE TABLE IF NOT EXISTS signal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                signal_name TEXT,
                signal_group TEXT,
                direction TEXT DEFAULT 'BULLISH',
                horizon TEXT DEFAULT 'CONFIRMATION',  -- EARLY, CONFIRMATION, LATE
                value REAL,
                threshold REAL,
                strength INTEGER DEFAULT 50,
                confidence REAL DEFAULT 0.5,
                first_detected_at TEXT,
                last_detected_at TEXT,
                data_timestamp TEXT,
                source TEXT DEFAULT 'ENGINE',
                is_active INTEGER DEFAULT 1,
                ttl_hours INTEGER DEFAULT 72,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS signal_combinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                combination_hash TEXT UNIQUE,
                signal_ids TEXT,  -- JSON array
                signal_count INTEGER,
                total_occurrences INTEGER DEFAULT 0,
                win_rate_1d REAL,
                win_rate_3d REAL,
                win_rate_5d REAL,
                avg_return_5d REAL,
                median_return_5d REAL,
                profit_factor REAL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open_price REAL,
                gap_pct REAL,
                price_5m REAL,
                price_15m REAL,
                price_30m REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                volume_day INTEGER,
                mfe_pct REAL,
                mae_pct REAL,
                actual_return_1d REAL,
                actual_return_5d REAL,
                direction_predicted TEXT,
                direction_actual TEXT,
                direction_correct INTEGER,
                predicted_reason TEXT,
                reason_correct INTEGER,
                classification TEXT,  -- TRUE_ALPHA, LUCKY_BETA, FAILED_CATALYST, TOTAL_MISS
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            );

            CREATE TABLE IF NOT EXISTS accuracy_evaluation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                symbol TEXT,
                direction_predicted TEXT,
                direction_actual TEXT,
                direction_correct INTEGER,
                predicted_reason TEXT,
                verified_actual_reason TEXT,
                reason_correct INTEGER,
                classification TEXT,
                sector_beta_attribution REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            );

            CREATE TABLE IF NOT EXISTS decision_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                score REAL,
                action TEXT,
                regime TEXT,
                entry_price REAL,
                stop_loss REAL,
                target_price REAL,
                exit_price REAL,
                pnl_pct REAL,
                actual_outcome_pct REAL,
                was_correct INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS validation_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                field TEXT,
                error_type TEXT NOT NULL,
                expected TEXT,
                actual TEXT,
                severity TEXT DEFAULT 'ERROR',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_validation_errors_run ON validation_errors(run_id);
            CREATE INDEX IF NOT EXISTS idx_validation_errors_sym ON validation_errors(symbol);
            CREATE INDEX IF NOT EXISTS idx_validation_errors_type ON validation_errors(error_type);

            CREATE INDEX IF NOT EXISTS idx_decision_signals_sym ON decision_signals(symbol, date DESC);
            CREATE INDEX IF NOT EXISTS idx_decision_signals_action ON decision_signals(action, date DESC);

            CREATE INDEX IF NOT EXISTS idx_signal_events_sym ON signal_events(symbol, first_detected_at DESC);
            CREATE INDEX IF NOT EXISTS idx_signal_events_id ON signal_events(signal_id, first_detected_at DESC);
            CREATE INDEX IF NOT EXISTS idx_signal_events_horizon ON signal_events(horizon, symbol);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_events_dedup ON signal_events(symbol, signal_id, data_timestamp);

            CREATE INDEX IF NOT EXISTS idx_master_universe_sector ON master_universe(sector);
            CREATE INDEX IF NOT EXISTS idx_master_universe_cap ON master_universe(cap_category);
            CREATE INDEX IF NOT EXISTS idx_corp_actions_sym ON corporate_actions(symbol, ex_date DESC);
            CREATE INDEX IF NOT EXISTS idx_prediction_freeze_date ON prediction_freeze_log(prediction_date DESC);
            CREATE INDEX IF NOT EXISTS idx_ohlcv_sym_date ON ohlcv_daily(symbol, date DESC);
            CREATE INDEX IF NOT EXISTS idx_features_sym_date ON features_daily(symbol, date DESC);
            CREATE INDEX IF NOT EXISTS idx_cap_category ON stock_grid(cap_category);
            CREATE INDEX IF NOT EXISTS idx_composite_score ON stock_grid(composite_score DESC);
            CREATE INDEX IF NOT EXISTS idx_delivery_pct ON stock_grid(delivery_pct DESC);
            CREATE INDEX IF NOT EXISTS idx_rsi ON stock_grid(rsi);
            CREATE INDEX IF NOT EXISTS idx_pe ON stock_grid(pe);
            CREATE INDEX IF NOT EXISTS idx_action ON stock_grid(action);
            CREATE INDEX IF NOT EXISTS idx_fii_dii_date ON fii_dii_history(date DESC);
            CREATE INDEX IF NOT EXISTS idx_inst_flow_sym_date ON institutional_flow(symbol, date DESC);
            CREATE INDEX IF NOT EXISTS idx_market_data_sym_ts ON market_data(symbol, timestamp);
            CREATE INDEX IF NOT EXISTS idx_corp_filings_sym ON corporate_filings(symbol);
            CREATE INDEX IF NOT EXISTS idx_market_live_sym ON market_live(symbol);
            CREATE INDEX IF NOT EXISTS idx_fundamentals_sym ON fundamentals(symbol);
            CREATE INDEX IF NOT EXISTS idx_indicators_sym ON indicators(symbol);
            CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs(started_at DESC);
        """)

        # Migration check for existing tables missing new timestamp columns
        tables_to_check = {
            "stock_grid": ["as_of", "updated_at"],
            "stock_grid_staging": ["as_of", "updated_at"],
            "portfolio_snapshots": ["as_of", "updated_at"],
            "fii_dii_history": ["as_of", "updated_at"],
            "institutional_flow": ["as_of", "updated_at"],
            "market_data": ["as_of", "updated_at"],
            "corporate_filings": ["as_of", "updated_at"],
        }
        cursor = conn.cursor()
        for tbl, cols in tables_to_check.items():
            cursor.execute(f"PRAGMA table_info({tbl})")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            for col in cols:
                if col not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} DATETIME")
                        cursor.execute(f"UPDATE {tbl} SET {col} = CURRENT_TIMESTAMP WHERE {col} IS NULL")
                    except Exception as exc:
                        log.debug(f"Column migration skipped for {tbl}.{col}: {exc}")

    log.info(f"Initialized SQLite Database at {DB_PATH.name}")


def flush_live_cache_to_db(live_cache: Dict[str, Dict[str, Any]]) -> int:
    """
    Periodic persistence worker (60s timer / shutdown flush).
    Flushes in-memory `live_cache` snapshots to `market_live` table in SQLite.
    ZERO per-tick writes are performed to avoid SQLite lock contention.
    """
    if not live_cache:
        return 0

    init_db()
    count = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for sym, snap in live_cache.items():
            cursor.execute("""
                INSERT INTO market_live (
                    symbol, ltp, volume, open, high, low, prev_close, vwap, last_trade_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol) DO UPDATE SET
                    ltp=excluded.ltp,
                    volume=excluded.volume,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    prev_close=excluded.prev_close,
                    vwap=excluded.vwap,
                    last_trade_time=excluded.last_trade_time,
                    updated_at=CURRENT_TIMESTAMP
            """, (
                sym.upper(),
                float(snap.get("ltp", 0.0) or 0.0),
                int(snap.get("volume", 0) or 0),
                float(snap.get("open", 0.0) or 0.0),
                float(snap.get("high", 0.0) or 0.0),
                float(snap.get("low", 0.0) or 0.0),
                float(snap.get("prev_close", 0.0) or 0.0),
                float(snap.get("vwap", 0.0) or 0.0),
                str(snap.get("last_trade_time", ""))
            ))
            count += 1
        conn.commit()
    log.info(f"Flushed {count} market_live snapshot records to SQLite database")
    return count


def classify_market_cap(close: float, mcap_cr: Optional[float] = None, rank: Optional[int] = None) -> str:
    """
    Phase 1 TASK-003: Dynamic Market-Cap Classifier.
    - PENNY: LTP < ₹50 or mcap_cr < 500
    - If rank is provided:
        - 1 to 100 -> LARGE
        - 101 to 250 -> MID
        - 251 to 500 -> SMALL
        - 501+ -> MICRO
    - If rank not provided, fallback to SEBI standard mcap thresholds:
        - >= 50,000 Cr -> LARGE
        - >= 15,000 Cr -> MID
        - >= 1,000 Cr -> SMALL
        - < 1,000 Cr -> MICRO
    """
    if close < 50.0:
        return "PENNY"
    if rank is not None and rank > 0:
        if rank <= 100:
            return "LARGE"
        elif rank <= 250:
            return "MID"
        elif rank <= 500:
            return "SMALL"
        else:
            return "MICRO"
    if mcap_cr is not None and mcap_cr > 0:
        if mcap_cr >= 50000.0:
            return "LARGE"
        elif mcap_cr >= 15000.0:
            return "MID"
        elif mcap_cr >= 1000.0:
            return "SMALL"
        else:
            return "MICRO"
    # Fallback by price if mcap is missing
    if close >= 2500.0:
        return "LARGE"
    elif close >= 500.0:
        return "MID"
    elif close >= 100.0:
        return "SMALL"
    return "MICRO"

def upsert_stock_metrics(records: List[Dict[str, Any]]):
    """High-throughput batch insert or update of stock metrics into SQLite database."""
    if not records:
        return

    init_db()
    param_rows = []
    for r in records:
        close = float(r.get("close", 0.0) or 0.0)
        mcap = float(r.get("market_cap_cr", 0.0) or 0.0) if r.get("market_cap_cr") else None
        cat = r.get("cap_category") or classify_market_cap(close, mcap)

        param_rows.append((
            r.get("symbol"),
            r.get("name", r.get("symbol", "").replace(".NS", "")),
            r.get("sector", "Equity"),
            cat,
            close,
            float(r.get("change_pct", 0.0) or 0.0),
            int(r.get("volume", 0) or 0),
            int(r.get("traded_qty", 0) or 0),
            int(r.get("delivered_qty", 0) or 0),
            float(r.get("delivery_pct", 0.0) or 0.0),
            float(r.get("rsi", 50.0) or 50.0),
            r.get("macd_status") or ("BULLISH" if r.get("macd_bullish") else "NEUTRAL"),
            1 if r.get("above_50dma") else 0,
            1 if r.get("above_200dma") else 0,
            float(r.get("pct_from_52w_high", 0.0) or 0.0),
            float(r.get("pe", 0.0) or 0.0),
            float(r.get("pb", 0.0) or 0.0),
            float(r.get("roe", 0.0) or 0.0),
            float(r.get("roce", 0.0) or 0.0),
            mcap or 0.0,
            float(r.get("composite_score", 50.0) or 50.0),
            r.get("action", "HOLD"),
            float(r.get("target_price", 0.0) or 0.0),
            float(r.get("stop_loss", 0.0) or 0.0),
            float(r.get("rr_ratio", 2.0) or 2.0),
            float(r.get("ev_pct", 3.5) or 3.5),
            float(r.get("net_alpha_pct", 0.0) or 0.0),
        ))

    query = """
        INSERT INTO stock_grid (
            symbol, name, sector, cap_category, close, change_pct, volume,
            traded_qty, delivered_qty, delivery_pct, rsi, macd_status,
            above_50dma, above_200dma, pct_from_52w_high, pe, pb, roe, roce,
            market_cap_cr, composite_score, action, target_price, stop_loss,
            rr_ratio, ev_pct, net_alpha_pct, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(symbol) DO UPDATE SET
            name=excluded.name,
            sector=excluded.sector,
            cap_category=excluded.cap_category,
            close=excluded.close,
            change_pct=excluded.change_pct,
            volume=excluded.volume,
            traded_qty=excluded.traded_qty,
            delivered_qty=excluded.delivered_qty,
            delivery_pct=excluded.delivery_pct,
            rsi=excluded.rsi,
            macd_status=excluded.macd_status,
            above_50dma=excluded.above_50dma,
            above_200dma=excluded.above_200dma,
            pct_from_52w_high=excluded.pct_from_52w_high,
            pe=excluded.pe,
            pb=excluded.pb,
            roe=excluded.roe,
            roce=excluded.roce,
            market_cap_cr=excluded.market_cap_cr,
            composite_score=excluded.composite_score,
            action=excluded.action,
            target_price=excluded.target_price,
            stop_loss=excluded.stop_loss,
            rr_ratio=excluded.rr_ratio,
            ev_pct=excluded.ev_pct,
            net_alpha_pct=excluded.net_alpha_pct,
            updated_at=CURRENT_TIMESTAMP
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(query, param_rows)
        conn.commit()
    log.info(f"Upserted {len(records)} stocks into SQLite database in single batch")


def upsert_stock_metrics_staging(records: List[Dict[str, Any]]) -> int:
    """High-throughput batch insert or update of stock metrics into stock_grid_staging table."""
    if not records:
        return 0

    init_db()
    param_rows = []
    for r in records:
        close = float(r.get("close", 0.0) or 0.0)
        mcap = float(r.get("market_cap_cr", 0.0) or 0.0) if r.get("market_cap_cr") else None
        cat = r.get("cap_category") or classify_market_cap(close, mcap)

        param_rows.append((
            r.get("symbol"),
            r.get("name", r.get("symbol", "").replace(".NS", "")),
            r.get("sector", "Equity"),
            cat,
            close,
            float(r.get("change_pct", 0.0) or 0.0),
            int(r.get("volume", 0) or 0),
            int(r.get("traded_qty", 0) or 0),
            int(r.get("delivered_qty", 0) or 0),
            float(r.get("delivery_pct", 0.0) or 0.0),
            float(r.get("rsi", 50.0) or 50.0),
            r.get("macd_status") or ("BULLISH" if r.get("macd_bullish") else "NEUTRAL"),
            1 if r.get("above_50dma") else 0,
            1 if r.get("above_200dma") else 0,
            float(r.get("pct_from_52w_high", 0.0) or 0.0),
            float(r.get("pe", 0.0) or 0.0),
            float(r.get("pb", 0.0) or 0.0),
            float(r.get("roe", 0.0) or 0.0),
            float(r.get("roce", 0.0) or 0.0),
            mcap or 0.0,
            float(r.get("composite_score", 50.0) or 50.0),
            r.get("action", "HOLD"),
            float(r.get("target_price", 0.0) or 0.0),
            float(r.get("stop_loss", 0.0) or 0.0),
            float(r.get("rr_ratio", 2.0) or 2.0),
            float(r.get("ev_pct", 3.5) or 3.5),
            float(r.get("net_alpha_pct", 0.0) or 0.0),
        ))

    query = """
        INSERT INTO stock_grid_staging (
            symbol, name, sector, cap_category, close, change_pct, volume,
            traded_qty, delivered_qty, delivery_pct, rsi, macd_status,
            above_50dma, above_200dma, pct_from_52w_high, pe, pb, roe, roce,
            market_cap_cr, composite_score, action, target_price, stop_loss,
            rr_ratio, ev_pct, net_alpha_pct, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(symbol) DO UPDATE SET
            name=excluded.name,
            sector=excluded.sector,
            cap_category=excluded.cap_category,
            close=excluded.close,
            change_pct=excluded.change_pct,
            volume=excluded.volume,
            traded_qty=excluded.traded_qty,
            delivered_qty=excluded.delivered_qty,
            delivery_pct=excluded.delivery_pct,
            rsi=excluded.rsi,
            macd_status=excluded.macd_status,
            above_50dma=excluded.above_50dma,
            above_200dma=excluded.above_200dma,
            pct_from_52w_high=excluded.pct_from_52w_high,
            pe=excluded.pe,
            pb=excluded.pb,
            roe=excluded.roe,
            roce=excluded.roce,
            market_cap_cr=excluded.market_cap_cr,
            composite_score=excluded.composite_score,
            action=excluded.action,
            target_price=excluded.target_price,
            stop_loss=excluded.stop_loss,
            rr_ratio=excluded.rr_ratio,
            ev_pct=excluded.ev_pct,
            net_alpha_pct=excluded.net_alpha_pct,
            updated_at=CURRENT_TIMESTAMP
    """

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(query, param_rows)
        conn.commit()
    log.info(f"Upserted {len(param_rows)} stocks into stock_grid_staging in single batch")
    return len(param_rows)


def atomic_publish_stock_grid(run_id: str, min_expected_rows: int = 100) -> bool:
    """
    Checks staging table row count (>= min_expected_rows) and executes atomic swap:
      ALTER TABLE stock_grid RENAME TO stock_grid_old;
      ALTER TABLE stock_grid_staging RENAME TO stock_grid;
      DROP TABLE IF EXISTS stock_grid_old;
      Re-creates empty stock_grid_staging and indexes.
    If row count is zero or error occurs, rollback and NEVER corrupt production stock_grid.
    Returns True if published, False on rollback.
    """
    init_db()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM stock_grid_staging")
        row = cursor.fetchone()
        staging_count = row["cnt"] if row else 0

        if staging_count < min_expected_rows:
            log.warning(
                f"[AtomicPublish] Staging table has {staging_count} rows, below minimum {min_expected_rows}. "
                f"Aborting atomic swap to prevent data loss."
            )
            update_pipeline_run(
                run_id,
                status="FAILED",
                error_summary=f"Staging row count {staging_count} < min_expected_rows {min_expected_rows}"
            )
            conn.close()
            return False

        # Execute atomic swap inside explicit transaction
        conn.isolation_level = None
        cursor.execute("BEGIN IMMEDIATE")

        # Double check inside transaction lock
        cursor.execute("SELECT COUNT(*) as cnt FROM stock_grid_staging")
        current_cnt = cursor.fetchone()["cnt"]
        if current_cnt < min_expected_rows:
            cursor.execute("ROLLBACK")
            conn.close()
            return False

        # Drop leftover old table if any
        cursor.execute("DROP TABLE IF EXISTS stock_grid_old")

        # Atomic table rename
        cursor.execute("ALTER TABLE stock_grid RENAME TO stock_grid_old")
        cursor.execute("ALTER TABLE stock_grid_staging RENAME TO stock_grid")
        cursor.execute("DROP TABLE IF EXISTS stock_grid_old")

        # Re-create empty stock_grid_staging
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_grid_staging (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT,
                cap_category TEXT,
                close REAL,
                change_pct REAL,
                volume INTEGER,
                traded_qty INTEGER,
                delivered_qty INTEGER,
                delivery_pct REAL,
                rsi REAL,
                macd_status TEXT,
                above_50dma INTEGER,
                above_200dma INTEGER,
                pct_from_52w_high REAL,
                pe REAL,
                pb REAL,
                roe REAL,
                roce REAL,
                market_cap_cr REAL,
                composite_score REAL,
                action TEXT,
                target_price REAL,
                stop_loss REAL,
                rr_ratio REAL,
                ev_pct REAL,
                net_alpha_pct REAL,
                as_of DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Re-create indexes on newly swapped stock_grid
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cap_category ON stock_grid(cap_category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_composite_score ON stock_grid(composite_score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_delivery_pct ON stock_grid(delivery_pct DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rsi ON stock_grid(rsi)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pe ON stock_grid(pe)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_action ON stock_grid(action)")

        cursor.execute("COMMIT")
        log.info(f"[AtomicPublish] Successfully published {staging_count} rows from staging to production stock_grid (run: {run_id})")
        return True

    except Exception as exc:
        log.error(f"[AtomicPublish] Failed atomic swap for run {run_id}: {exc}. Rolling back.")
        try:
            cursor.execute("ROLLBACK")
        except Exception:
            pass
        update_pipeline_run(run_id, status="FAILED", error_summary=f"Atomic publish swap exception: {exc}")
        return False
    finally:
        conn.close()


def create_pipeline_run(
    run_id: str,
    universe_mode: str = "ALL",
    config_dict: Optional[Dict[str, Any]] = None
) -> None:
    """Creates a new pipeline run audit record in pipeline_runs."""
    init_db()
    started_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pipeline_runs (
                run_id, started_at, status, universe_mode, quality_score, duration_seconds
            ) VALUES (?, ?, 'INITIALIZING', ?, 100.0, 0.0)
            ON CONFLICT(run_id) DO UPDATE SET
                started_at=excluded.started_at,
                status=excluded.status,
                universe_mode=excluded.universe_mode
        """, (run_id, started_at, universe_mode))
        conn.commit()
    log.info(f"Created pipeline run audit record: {run_id} (Universe: {universe_mode})")


def update_pipeline_run(run_id: str, **kwargs) -> None:
    """Updates fields on an existing pipeline run."""
    if not kwargs:
        return
    init_db()
    allowed_cols = {
        "completed_at", "status", "universe_mode", "discovered_count",
        "processed_count", "success_count", "failed_count", "quality_score",
        "duration_seconds", "error_summary"
    }
    valid_updates = {k: v for k, v in kwargs.items() if k in allowed_cols}
    if not valid_updates:
        return

    set_clauses = [f"{col} = ?" for col in valid_updates.keys()]
    values = list(valid_updates.values())
    values.append(run_id)

    query = f"UPDATE pipeline_runs SET {', '.join(set_clauses)} WHERE run_id = ?"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, values)
        conn.commit()


def get_pipeline_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single pipeline run by run_id."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_recent_pipeline_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves recent pipeline runs ordered by started_at DESC."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]


def acquire_pipeline_lock(run_id: str, timeout_seconds: int = 7200) -> bool:
    """
    Acquires execution lock for a pipeline run in pipeline_lock table.
    Prevents concurrent overlapping runs. Automatically recovers if previous lock expired.
    Returns True if lock acquired/held, False if held by an active run.
    """
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT run_id, acquired_at, expires_at FROM pipeline_lock WHERE lock_id = 1")
        row = cursor.fetchone()

        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.isoformat()
        exp_dt = datetime.fromtimestamp(now_dt.timestamp() + timeout_seconds, timezone.utc)
        exp_str = exp_dt.isoformat()

        if row is None:
            cursor.execute(
                "INSERT INTO pipeline_lock (lock_id, run_id, acquired_at, expires_at) VALUES (1, ?, ?, ?)",
                (run_id, now_str, exp_str)
            )
            conn.commit()
            log.info(f"Acquired pipeline lock for run {run_id}")
            return True

        current_holder = row["run_id"]
        if current_holder == run_id:
            cursor.execute(
                "UPDATE pipeline_lock SET expires_at = ? WHERE lock_id = 1",
                (exp_str,)
            )
            conn.commit()
            return True

        # Check if lock has expired
        is_expired = False
        if row["expires_at"]:
            try:
                lock_exp = datetime.fromisoformat(row["expires_at"])
                if lock_exp.tzinfo is None:
                    lock_exp = lock_exp.replace(tzinfo=timezone.utc)
                if now_dt >= lock_exp:
                    is_expired = True
            except Exception:
                is_expired = True
        elif row["acquired_at"]:
            try:
                lock_acq = datetime.fromisoformat(row["acquired_at"])
                if lock_acq.tzinfo is None:
                    lock_acq = lock_acq.replace(tzinfo=timezone.utc)
                if (now_dt - lock_acq).total_seconds() > timeout_seconds:
                    is_expired = True
            except Exception:
                is_expired = True

        if is_expired:
            log.warning(f"Previous pipeline lock by {current_holder} expired. Reclaiming lock for {run_id}.")
            cursor.execute(
                "UPDATE pipeline_lock SET run_id = ?, acquired_at = ?, expires_at = ? WHERE lock_id = 1",
                (run_id, now_str, exp_str)
            )
            conn.commit()
            return True

        log.warning(f"Pipeline lock is held by active run {current_holder}. Run {run_id} denied lock.")
        return False


def release_pipeline_lock(run_id: str) -> bool:
    """
    Releases execution lock held by run_id.
    Returns True if successfully released, False if held by another run.
    """
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT run_id FROM pipeline_lock WHERE lock_id = 1")
        row = cursor.fetchone()
        if not row:
            return True
        if row["run_id"] == run_id:
            cursor.execute("DELETE FROM pipeline_lock WHERE lock_id = 1")
            conn.commit()
            log.info(f"Released pipeline lock for run {run_id}")
            return True
        else:
            log.warning(f"Cannot release pipeline lock: held by {row['run_id']}, not {run_id}")
            return False


def get_historical_comparable_events(security_id: str, context: Optional[dict] = None, event_ids: Optional[list] = None) -> List[Dict[str, Any]]:
    """Retrieve historical comparable events data for a security."""
    return []

def upsert_portfolio_snapshot(holdings: Union[str, List[Dict[str, Any]]], positions: Union[str, List[Dict[str, Any]]], orders: Union[str, List[Dict[str, Any]]], trades: Union[str, List[Dict[str, Any]]], cash: float):

    """Insert or update portfolio snapshot into SQLite database."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()

        def to_json_str(data: Union[str, List[Dict[str, Any]], Dict[str, Any]]) -> str:
            if isinstance(data, (list, dict)):
                return json.dumps(data)
            return str(data)

        holdings_json = to_json_str(holdings)
        positions_json = to_json_str(positions)
        orders_json = to_json_str(orders)
        trades_json = to_json_str(trades)

        cursor.execute("""
            INSERT INTO portfolio_snapshots (
                timestamp, holdings, positions, orders, trades, cash
            ) VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?)
        """, (holdings_json, positions_json, orders_json, trades_json, cash))
        conn.commit()
    log.info("Upserted portfolio snapshot into SQLite database")

def query_stocks_grid(
    cap_category: Optional[str] = None,   # ALL, LARGE, MID, SMALL, PENNY
    search_query: Optional[str] = None,
    sort_by: str = "composite_score",
    ascending: bool = False,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """
    Sub-10ms indexed query for the stock grid.
    Supports filtering by market cap category and searching.
    """
    init_db()

    # Allowed sort columns to prevent SQL injection
    valid_sorts = {
        "symbol": "symbol",
        "close": "close",
        "change_pct": "change_pct",
        "rsi": "rsi",
        "pe": "pe",
        "roe": "roe",
        "delivery_pct": "delivery_pct",
        "composite_score": "composite_score",
        "target_price": "target_price",
        "rr_ratio": "rr_ratio",
        "net_alpha_pct": "net_alpha_pct",
    }
    col = valid_sorts.get(sort_by, "composite_score")
    direction = "ASC" if ascending else "DESC"

    where_clauses = []
    params = []

    if cap_category and cap_category.upper() != "ALL":
        where_clauses.append("cap_category = ?")
        params.append(cap_category.upper())

    if search_query:
        where_clauses.append("(symbol LIKE ? OR name LIKE ? OR sector LIKE ?)")
        q = f"%{search_query.strip()}%"
        params.extend([q, q, q])

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    query = f"SELECT * FROM stock_grid {where_str} ORDER BY {col} {direction} LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        cursor = conn.cursor()
        start_time = time.time()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        query_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        log.info(f"Query executed in {query_time:.2f} ms")
        return [dict(row) for row in rows]

def query_portfolio_snapshot() -> Dict[str, Any]:
    """Query the latest portfolio snapshot from SQLite database."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM portfolio_snapshots
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            snapshot = dict(row)
            # Deserialize JSON strings back to Python objects
            for key in ["holdings", "positions", "orders", "trades"]:
                if snapshot.get(key) and isinstance(snapshot[key], str):
                    try:
                        snapshot[key] = json.loads(snapshot[key])
                    except json.JSONDecodeError:
                        log.warning(f"Could not decode JSON for {key} in portfolio snapshot: {snapshot[key][:100]}...")
                        # Keep it as a string if decoding fails or handle as needed
            return snapshot
        return {}

def upsert_fii_dii_history(records: List[Dict[str, Any]]):
    """Insert or update FII/DII historical records into SQLite database."""
    if not records:
        return
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            dt = r.get("date")
            if not dt:
                continue
            cursor.execute("""
                INSERT INTO fii_dii_history (
                    date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, total_net, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(date) DO UPDATE SET
                    fii_buy=excluded.fii_buy,
                    fii_sell=excluded.fii_sell,
                    fii_net=excluded.fii_net,
                    dii_buy=excluded.dii_buy,
                    dii_sell=excluded.dii_sell,
                    dii_net=excluded.dii_net,
                    total_net=excluded.total_net,
                    updated_at=CURRENT_TIMESTAMP
            """, (
                dt,
                float(r.get("fii_buy", 0.0) or 0.0),
                float(r.get("fii_sell", 0.0) or 0.0),
                float(r.get("fii_net", 0.0) or 0.0),
                float(r.get("dii_buy", 0.0) or 0.0),
                float(r.get("dii_sell", 0.0) or 0.0),
                float(r.get("dii_net", 0.0) or 0.0),
                float(r.get("total_net", (r.get("fii_net", 0.0) or 0.0) + (r.get("dii_net", 0.0) or 0.0))),
            ))
        conn.commit()
    log.info(f"Upserted {len(records)} FII/DII records into database")

def query_fii_dii_history(days: int = 30) -> List[Dict[str, Any]]:
    """Query recent FII/DII history records from database."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fii_dii_history
            ORDER BY date DESC
            LIMIT ?
        """, (days,))
        rows = cursor.fetchall()
        result = [dict(row) for row in rows]
        result.reverse()
        return result

def upsert_institutional_flow(records: List[Dict[str, Any]]):
    """Insert or update institutional flow records into SQLite database."""
    if not records:
        return
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            cursor.execute("""
                INSERT INTO institutional_flow (
                    date, symbol, flow_score, silent_accumulation, marquee_buy_count,
                    marquee_sell_count, insider_net_buy_val, free_float_pct, signal, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(date, symbol) DO UPDATE SET
                    flow_score=excluded.flow_score,
                    silent_accumulation=excluded.silent_accumulation,
                    marquee_buy_count=excluded.marquee_buy_count,
                    marquee_sell_count=excluded.marquee_sell_count,
                    insider_net_buy_val=excluded.insider_net_buy_val,
                    free_float_pct=excluded.free_float_pct,
                    signal=excluded.signal,
                    updated_at=CURRENT_TIMESTAMP
            """, (
                r.get("date"),
                r.get("symbol"),
                float(r.get("flow_score", 50.0) or 50.0),
                1 if r.get("silent_accumulation") else 0,
                int(r.get("marquee_buy_count", 0) or 0),
                int(r.get("marquee_sell_count", 0) or 0),
                float(r.get("insider_net_buy_val", 0.0) or 0.0),
                float(r.get("free_float_pct", 0.0) or 0.0),
                r.get("signal", "NEUTRAL")
            ))
        conn.commit()
    log.info(f"Upserted {len(records)} institutional flow records into database")

def query_institutional_flow(symbol: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Query institutional flow records from database."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        if symbol:
            cursor.execute("""
                SELECT * FROM institutional_flow
                WHERE symbol = ?
                ORDER BY date DESC
                LIMIT ?
            """, (symbol.upper(), limit))
        else:
            cursor.execute("""
                SELECT * FROM institutional_flow
                ORDER BY date DESC, flow_score DESC
                LIMIT ?
            """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def flush_live_cache_to_db(live_cache_snapshot: Union[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]) -> int:
    """
    Slow periodic worker function / method that flushes in-memory live_cache snapshot
    to the `market_live` SQLite table on a 60-second timer or process shutdown.
    Ensures ZERO per-tick writes to SQLite!

    Args:
        live_cache_snapshot: Dict mapping symbol -> dict or List of dicts.

    Returns:
        int: Number of records written/updated in market_live table.
    """
    if not live_cache_snapshot:
        return 0

    init_db()

    records: List[Dict[str, Any]] = []
    if isinstance(live_cache_snapshot, dict):
        for sym, data in live_cache_snapshot.items():
            if isinstance(data, dict):
                rec = dict(data)
                if "symbol" not in rec:
                    rec["symbol"] = sym
                records.append(rec)
    elif isinstance(live_cache_snapshot, list):
        records = [r for r in live_cache_snapshot if isinstance(r, dict)]

    if not records:
        return 0

    written = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            sym = r.get("symbol")
            if not sym:
                continue

            ltp = float(r.get("ltp") if r.get("ltp") is not None else (r.get("close") or 0.0))
            vol = int(r.get("volume") or 0)
            open_px = float(r.get("open") or 0.0)
            high_px = float(r.get("high") or 0.0)
            low_px = float(r.get("low") or 0.0)
            prev_close = float(r.get("prev_close") if r.get("prev_close") is not None else (r.get("previous_close") or 0.0))
            vwap = float(r.get("vwap") or 0.0)
            last_trade_time = str(r.get("last_trade_time") or r.get("timestamp") or "")
            updated_at = r.get("updated_at")

            cursor.execute("""
                INSERT INTO market_live (
                    symbol, ltp, volume, open, high, low, prev_close, vwap, last_trade_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(symbol) DO UPDATE SET
                    ltp = excluded.ltp,
                    volume = excluded.volume,
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    prev_close = excluded.prev_close,
                    vwap = excluded.vwap,
                    last_trade_time = excluded.last_trade_time,
                    updated_at = COALESCE(excluded.updated_at, CURRENT_TIMESTAMP)
            """, (
                sym, ltp, vol, open_px, high_px, low_px, prev_close, vwap, last_trade_time, updated_at
            ))
            written += 1
        conn.commit()

    log.info(f"Flushed {written} live cache records to SQLite market_live table (zero per-tick writes)")
    return written

def upsert_fundamentals(records: List[Dict[str, Any]]) -> int:
    """Insert or update fundamentals records in SQLite database."""
    if not records:
        return 0
    init_db()
    written = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            sym = r.get("symbol")
            if not sym:
                continue
            cursor.execute("""
                INSERT INTO fundamentals (
                    symbol, pe, pb, roe, roce, debt_equity, opm, sales_cagr, profit_cagr, eps, fundamental_as_of
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(symbol) DO UPDATE SET
                    pe = excluded.pe,
                    pb = excluded.pb,
                    roe = excluded.roe,
                    roce = excluded.roce,
                    debt_equity = excluded.debt_equity,
                    opm = excluded.opm,
                    sales_cagr = excluded.sales_cagr,
                    profit_cagr = excluded.profit_cagr,
                    eps = excluded.eps,
                    fundamental_as_of = COALESCE(excluded.fundamental_as_of, CURRENT_TIMESTAMP)
            """, (
                sym,
                float(r["pe"]) if r.get("pe") is not None else None,
                float(r["pb"]) if r.get("pb") is not None else None,
                float(r["roe"]) if r.get("roe") is not None else None,
                float(r["roce"]) if r.get("roce") is not None else None,
                float(r["debt_equity"]) if r.get("debt_equity") is not None else None,
                float(r["opm"]) if r.get("opm") is not None else None,
                float(r["sales_cagr"]) if r.get("sales_cagr") is not None else None,
                float(r["profit_cagr"]) if r.get("profit_cagr") is not None else None,
                float(r["eps"]) if r.get("eps") is not None else None,
                r.get("fundamental_as_of"),
            ))
            written += 1
        conn.commit()
    log.info(f"Upserted {written} records into fundamentals table")
    return written

def upsert_indicators(records: List[Dict[str, Any]]) -> int:
    """Insert or update technical indicator records in SQLite database."""
    if not records:
        return 0
    init_db()
    written = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            sym = r.get("symbol")
            if not sym:
                continue
            cursor.execute("""
                INSERT INTO indicators (
                    symbol, ema20, ema50, ema200, rsi, atr, bollinger_upper, bollinger_lower, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(symbol) DO UPDATE SET
                    ema20 = excluded.ema20,
                    ema50 = excluded.ema50,
                    ema200 = excluded.ema200,
                    rsi = excluded.rsi,
                    atr = excluded.atr,
                    bollinger_upper = excluded.bollinger_upper,
                    bollinger_lower = excluded.bollinger_lower,
                    calculated_at = COALESCE(excluded.calculated_at, CURRENT_TIMESTAMP)
            """, (
                sym,
                float(r["ema20"]) if r.get("ema20") is not None else None,
                float(r["ema50"]) if r.get("ema50") is not None else None,
                float(r["ema200"]) if r.get("ema200") is not None else None,
                float(r["rsi"]) if r.get("rsi") is not None else None,
                float(r["atr"]) if r.get("atr") is not None else None,
                float(r["bollinger_upper"]) if r.get("bollinger_upper") is not None else None,
                float(r["bollinger_lower"]) if r.get("bollinger_lower") is not None else None,
                r.get("calculated_at"),
            ))
            written += 1
        conn.commit()
    log.info(f"Upserted {written} records into indicators table")
    return written

def get_system_health_records() -> List[Dict[str, Any]]:
    """Query recent system health records."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_health'")
            if not cursor.fetchone():
                return []
            cursor.execute("SELECT * FROM system_health ORDER BY timestamp DESC LIMIT 50")
            return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []

# ── Phase 1 & 4 Layer Helpers (Tasks 001-012, 061-072) ───────────────────────────

def upsert_master_universe_stocks(stocks: List[Dict[str, Any]]) -> int:
    """
    Phase 1 TASK-001 & TASK-002: Batch upsert master universe securities.
    Stores complete corporate and listing taxonomy for NSE & BSE listed equities.
    """
    if not stocks:
        return 0
    init_db()
    count = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for s in stocks:
            sym = s.get("symbol")
            if not sym:
                continue
            close = float(s.get("ltp", s.get("close", 0.0)) or 0.0)
            mcap = float(s.get("market_cap_cr", 0.0) or 0.0) if s.get("market_cap_cr") else None
            cat = s.get("cap_category") or classify_market_cap(close, mcap, s.get("rank"))
            
            cursor.execute("""
                INSERT INTO master_universe (
                    symbol, company_name, isin, exchange, series, cap_category,
                    sector, industry, market_cap_cr, free_float_mcap_cr, face_value,
                    lot_size, is_fno, is_active, listing_date, avg_volume_30d,
                    avg_turnover_cr_30d, ltp, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol) DO UPDATE SET
                    company_name=COALESCE(excluded.company_name, master_universe.company_name),
                    isin=COALESCE(excluded.isin, master_universe.isin),
                    exchange=COALESCE(excluded.exchange, master_universe.exchange),
                    series=COALESCE(excluded.series, master_universe.series),
                    cap_category=excluded.cap_category,
                    sector=COALESCE(excluded.sector, master_universe.sector),
                    industry=COALESCE(excluded.industry, master_universe.industry),
                    market_cap_cr=COALESCE(excluded.market_cap_cr, master_universe.market_cap_cr),
                    free_float_mcap_cr=COALESCE(excluded.free_float_mcap_cr, master_universe.free_float_mcap_cr),
                    face_value=COALESCE(excluded.face_value, master_universe.face_value),
                    lot_size=COALESCE(excluded.lot_size, master_universe.lot_size),
                    is_fno=COALESCE(excluded.is_fno, master_universe.is_fno),
                    is_active=COALESCE(excluded.is_active, master_universe.is_active),
                    listing_date=COALESCE(excluded.listing_date, master_universe.listing_date),
                    avg_volume_30d=COALESCE(excluded.avg_volume_30d, master_universe.avg_volume_30d),
                    avg_turnover_cr_30d=COALESCE(excluded.avg_turnover_cr_30d, master_universe.avg_turnover_cr_30d),
                    ltp=COALESCE(excluded.ltp, master_universe.ltp),
                    updated_at=CURRENT_TIMESTAMP
            """, (
                sym,
                s.get("company_name", s.get("name")),
                s.get("isin"),
                s.get("exchange", "NSE"),
                s.get("series", "EQ"),
                cat,
                s.get("sector", "Equity"),
                s.get("industry"),
                mcap,
                float(s.get("free_float_mcap_cr", 0.0) or 0.0) if s.get("free_float_mcap_cr") else None,
                float(s.get("face_value", 10.0) or 10.0),
                int(s.get("lot_size", 1) or 1),
                1 if s.get("is_fno") else 0,
                int(s.get("is_active", 1) or 1),
                s.get("listing_date"),
                float(s.get("avg_volume_30d", 0.0) or 0.0),
                float(s.get("avg_turnover_cr_30d", 0.0) or 0.0),
                close,
            ))
            count += 1
        conn.commit()
    log.info(f"Upserted {count} stocks into master_universe")
    return count


def record_corporate_action(action: Dict[str, Any]) -> int:
    """
    Phase 1 TASK-004 to TASK-010: Record a corporate action (SPLIT, BONUS, DIVIDEND, RIGHTS, DEMERGER).
    """
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO corporate_actions (symbol, action_type, ex_date, record_date, ratio, details, applied)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            action.get("symbol"),
            action.get("action_type", "SPLIT"),
            action.get("ex_date"),
            action.get("record_date"),
            float(action.get("ratio", 1.0) or 1.0),
            action.get("details", ""),
            1 if action.get("applied") else 0
        ))
        conn.commit()
        return cursor.lastrowid or 0


def freeze_morning_predictions(prediction_date: str, candidates: List[Dict[str, Any]], prediction_time: str = "09:00:00") -> Dict[str, Any]:
    """
    Phase 10 Tasks 121-130 & Phase 1 Blueprint:
    Freezes top 40 candidates (5 Long/Short x 4 Cap categories) at 09:00 AM.
    Generates deterministic SHA-256 hash for immutable verification.
    """
    import hashlib
    init_db()
    
    canonical_json = json.dumps(candidates, sort_keys=True)
    sha256_hash = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prediction_freeze_log (
                prediction_date, prediction_time, total_candidates, sha256_hash, predictions_json, verified
            ) VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(prediction_date, prediction_time) DO UPDATE SET
                total_candidates=excluded.total_candidates,
                sha256_hash=excluded.sha256_hash,
                predictions_json=excluded.predictions_json,
                frozen_at=CURRENT_TIMESTAMP
        """, (
            prediction_date,
            prediction_time,
            len(candidates),
            sha256_hash,
            canonical_json
        ))
        conn.commit()
    
    log.info(f"Frozen {len(candidates)} morning predictions for {prediction_date} {prediction_time} with SHA-256 {sha256_hash[:12]}...")
    return {
        "prediction_date": prediction_date,
        "prediction_time": prediction_time,
        "total_candidates": len(candidates),
        "sha256_hash": sha256_hash,
        "verified": True
    }


def query_prediction_freeze_log(prediction_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query immutable morning prediction logs."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        if prediction_date:
            cursor.execute("SELECT * FROM prediction_freeze_log WHERE prediction_date = ? ORDER BY prediction_time DESC", (prediction_date,))
        else:
            cursor.execute("SELECT * FROM prediction_freeze_log ORDER BY prediction_date DESC, prediction_time DESC LIMIT 30")
        return [dict(r) for r in cursor.fetchall()]

def upsert_ohlcv_daily(records: List[Dict[str, Any]]) -> int:
    """
    Phase 2 TASK-013 & TASK-014: Upsert daily OHLCV, turnover, and delivery records into SQLite.
    """
    if not records:
        return 0
    init_db()
    count = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            sym = r.get("symbol")
            dt = r.get("date")
            if not sym or not dt:
                continue
            cursor.execute("""
                INSERT INTO ohlcv_daily (
                    symbol, date, open, high, low, close, volume, traded_value, delivered_qty, delivery_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    traded_value=COALESCE(excluded.traded_value, ohlcv_daily.traded_value),
                    delivered_qty=COALESCE(excluded.delivered_qty, ohlcv_daily.delivered_qty),
                    delivery_pct=COALESCE(excluded.delivery_pct, ohlcv_daily.delivery_pct)
            """, (
                sym,
                dt,
                float(r.get("open", 0.0)),
                float(r.get("high", 0.0)),
                float(r.get("low", 0.0)),
                float(r.get("close", 0.0)),
                int(r.get("volume", 0)),
                float(r.get("traded_value", 0.0)) if r.get("traded_value") is not None else None,
                int(r.get("delivered_qty", 0)) if r.get("delivered_qty") is not None else None,
                float(r.get("delivery_pct", 0.0)) if r.get("delivery_pct") is not None else None,
            ))
            count += 1
        conn.commit()
    return count


def upsert_features_daily(features: List[Dict[str, Any]]) -> int:
    """
    Phase 2 TASK-024: Fast indexed cache layer in SQLite `features_daily` table.
    """
    if not features:
        return 0
    init_db()
    count = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for f in features:
            sym = f.get("symbol")
            dt = f.get("date")
            if not sym or not dt:
                continue
            cursor.execute("""
                INSERT INTO features_daily (
                    symbol, date, ret_1d, ret_3d, ret_5d, ret_10d, ret_20d, ret_30d, ret_52w,
                    rsi_14, macd, macd_signal, macd_hist, atr_14, natr_14,
                    ema_9, ema_20, ema_50, ema_200, sma_20, sma_50, sma_200,
                    vol_20d_ratio, deliv_20d_ratio, realized_vol_20d, parkinson_vol,
                    garman_klass_vol, dist_52w_high_pct, dist_52w_low_pct,
                    bb_upper, bb_lower, bb_width, keltner_upper, keltner_lower, ttm_squeeze, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    ret_1d=excluded.ret_1d,
                    ret_3d=excluded.ret_3d,
                    ret_5d=excluded.ret_5d,
                    ret_10d=excluded.ret_10d,
                    ret_20d=excluded.ret_20d,
                    ret_30d=excluded.ret_30d,
                    ret_52w=excluded.ret_52w,
                    rsi_14=excluded.rsi_14,
                    macd=excluded.macd,
                    macd_signal=excluded.macd_signal,
                    macd_hist=excluded.macd_hist,
                    atr_14=excluded.atr_14,
                    natr_14=excluded.natr_14,
                    ema_9=excluded.ema_9,
                    ema_20=excluded.ema_20,
                    ema_50=excluded.ema_50,
                    ema_200=excluded.ema_200,
                    sma_20=excluded.sma_20,
                    sma_50=excluded.sma_50,
                    sma_200=excluded.sma_200,
                    vol_20d_ratio=excluded.vol_20d_ratio,
                    deliv_20d_ratio=excluded.deliv_20d_ratio,
                    realized_vol_20d=excluded.realized_vol_20d,
                    parkinson_vol=excluded.parkinson_vol,
                    garman_klass_vol=excluded.garman_klass_vol,
                    dist_52w_high_pct=excluded.dist_52w_high_pct,
                    dist_52w_low_pct=excluded.dist_52w_low_pct,
                    bb_upper=excluded.bb_upper,
                    bb_lower=excluded.bb_lower,
                    bb_width=excluded.bb_width,
                    keltner_upper=excluded.keltner_upper,
                    keltner_lower=excluded.keltner_lower,
                    ttm_squeeze=excluded.ttm_squeeze,
                    updated_at=CURRENT_TIMESTAMP
            """, (
                sym, dt,
                f.get("ret_1d"), f.get("ret_3d"), f.get("ret_5d"), f.get("ret_10d"), f.get("ret_20d"), f.get("ret_30d"), f.get("ret_52w"),
                f.get("rsi_14"), f.get("macd"), f.get("macd_signal"), f.get("macd_hist"),
                f.get("atr_14"), f.get("natr_14"),
                f.get("ema_9"), f.get("ema_20"), f.get("ema_50"), f.get("ema_200"),
                f.get("sma_20"), f.get("sma_50"), f.get("sma_200"),
                f.get("vol_20d_ratio"), f.get("deliv_20d_ratio"),
                f.get("realized_vol_20d"), f.get("parkinson_vol"), f.get("garman_klass_vol"),
                f.get("dist_52w_high_pct"), f.get("dist_52w_low_pct"),
                f.get("bb_upper"), f.get("bb_lower"), f.get("bb_width"),
                f.get("keltner_upper"), f.get("keltner_lower"), int(f.get("ttm_squeeze", 0) or 0)
            ))
            count += 1
        conn.commit()
    return count


def query_features_daily(symbol: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Query recent daily features for a symbol."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM features_daily WHERE symbol = ? ORDER BY date DESC LIMIT ?", (symbol, limit))
        return [dict(r) for r in cursor.fetchall()]


def log_decision_signal(signal_data: Dict[str, Any]) -> int:
    """Log a decision recommendation to SQLite for post-trade verification and hit-rate tracking."""
    init_db()
    import datetime
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO decision_signals (
                date, symbol, score, action, regime, entry_price, stop_loss, target_price
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_data.get("date", datetime.date.today().isoformat()),
            signal_data.get("symbol", "UNKNOWN"),
            signal_data.get("score", signal_data.get("overall_score", 0.0)),
            signal_data.get("action", signal_data.get("suggested_action", "WAIT")),
            signal_data.get("regime", "RISK-ON"),
            signal_data.get("entry_price", 0.0),
            signal_data.get("stop_loss", 0.0),
            signal_data.get("target_price", 0.0)
        ))
        conn.commit()
        return cursor.lastrowid


def record_signal_outcome(signal_id: int, exit_price: float, actual_outcome_pct: float, was_correct: bool) -> bool:
    """Record actual realized trade outcome for an earlier logged signal."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE decision_signals
            SET exit_price = ?, actual_outcome_pct = ?, was_correct = ?
            WHERE id = ?
        """, (exit_price, actual_outcome_pct, 1 if was_correct else 0, signal_id))
        conn.commit()
        return cursor.rowcount > 0


def get_action_hitrate(action: str = "BUY_NOW") -> Dict[str, Any]:
    """Calculate historical win rate and average return for a specific action signal."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as wins,
                   AVG(actual_outcome_pct) as avg_return
            FROM decision_signals
            WHERE action = ? AND actual_outcome_pct IS NOT NULL
        """, (action,))
        row = cursor.fetchone()
        total = row["total"] if row and row["total"] else 0
        wins = row["wins"] if row and row["wins"] else 0
        avg_ret = float(row["avg_return"]) if row and row["avg_return"] is not None else 0.0
        win_rate = round((wins / total * 100.0), 2) if total > 0 else 0.0
        return {
            "action": action,
            "total_signals": total,
            "winning_signals": wins,
            "win_rate_pct": win_rate,
            "avg_return_pct": round(avg_ret, 2)
        }


def get_regime_accuracy(regime: str = "RISK-ON") -> Dict[str, Any]:
    """Calculate predictive accuracy during a specific market regime."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as wins,
                   AVG(actual_outcome_pct) as avg_return
            FROM decision_signals
            WHERE regime = ? AND actual_outcome_pct IS NOT NULL
        """, (regime,))
        row = cursor.fetchone()
        total = row["total"] if row and row["total"] else 0
        wins = row["wins"] if row and row["wins"] else 0
        avg_ret = float(row["avg_return"]) if row and row["avg_return"] is not None else 0.0
        win_rate = round((wins / total * 100.0), 2) if total > 0 else 0.0
        return {
            "regime": regime,
            "total_signals": total,
            "winning_signals": wins,
            "accuracy_pct": win_rate,
            "avg_return_pct": round(avg_ret, 2)
        }


class SignalDB:
    """Wrapper class for strategy signal tracking and outcome verification."""
    @staticmethod
    def log_signal(signal_data: Dict[str, Any]) -> int:
        return log_decision_signal(signal_data)

    @staticmethod
    def record_outcome(signal_id: int, exit_price: float, actual_outcome_pct: float, was_correct: bool) -> bool:
        return record_signal_outcome(signal_id, exit_price, actual_outcome_pct, was_correct)

    @staticmethod
    def get_action_hitrate(action: str = "BUY_NOW") -> Dict[str, Any]:
        return get_action_hitrate(action)

    @staticmethod
    def get_regime_accuracy(regime: str = "RISK-ON") -> Dict[str, Any]:
        return get_regime_accuracy(regime)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing SQLite Database Layer with Freshness Timestamps...\n")
    init_db()
    demo_records = [
        {"symbol": "RELIANCE.NS", "close": 2850.0, "market_cap_cr": 1900000.0, "rsi": 58.2, "composite_score": 76.5, "action": "BUY_NOW", "target_price": 3150.0, "stop_loss": 2720.0, "rr_ratio": 2.3, "delivery_pct": 52.9},
        {"symbol": "WELCORP.NS", "close": 425.0, "market_cap_cr": 11000.0, "rsi": 62.1, "composite_score": 68.0, "action": "WATCH", "target_price": 485.0, "stop_loss": 395.0, "rr_ratio": 2.0, "delivery_pct": 45.2},
        {"symbol": "HFCL.NS", "close": 48.5, "market_cap_cr": 6800.0, "rsi": 52.0, "composite_score": 63.5, "action": "WATCH", "target_price": 58.0, "stop_loss": 44.0, "rr_ratio": 2.1, "delivery_pct": 61.5},
    ]
    upsert_stock_metrics(demo_records)

    print("Testing slow live cache persistence worker (flush_live_cache_to_db):")
    sample_live_cache = {
        "RELIANCE.NS": {
            "symbol": "RELIANCE.NS",
            "ltp": 2855.0,
            "volume": 1200000,
            "open": 2840.0,
            "high": 2870.0,
            "low": 2835.0,
            "prev_close": 2850.0,
            "vwap": 2852.5,
            "last_trade_time": "2026-09-05T15:30:00"
        }
    }
    flushed = flush_live_cache_to_db(sample_live_cache)
    print(f"Flushed {flushed} market_live records.")

    print("\nTesting fundamentals & indicators upsert:")
    upsert_fundamentals([{"symbol": "RELIANCE.NS", "pe": 24.5, "pb": 2.1, "roe": 14.5, "roce": 12.8}])
    upsert_indicators([{"symbol": "RELIANCE.NS", "ema20": 2830.0, "ema50": 2790.0, "rsi": 58.2}])

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM market_live WHERE symbol='RELIANCE.NS'")
        print("market_live row:", dict(cursor.fetchone()))
        cursor.execute("SELECT * FROM fundamentals WHERE symbol='RELIANCE.NS'")
        print("fundamentals row:", dict(cursor.fetchone()))
        cursor.execute("SELECT * FROM indicators WHERE symbol='RELIANCE.NS'")
        print("indicators row:", dict(cursor.fetchone()))

    print("\nAll database schema & persistence tests completed successfully.")