# Swing Trading System Architecture

## Process Split Overview

The system is explicitly split into two decoupled processes operating at different cadences:

```
+-----------------------------------------------------------------------------------------+
|                              1. LIVE SERVICE (Continuous)                               |
|                                                                                         |
|  Dhan WebSocket (Live Ticks)                                                            |
|       │                                                                                 |
|       ▼                                                                                 |
|  in-memory live_cache (ltp, open, high, low, volume, vwap, updated_at)                  |
|       │                                                                                 |
|       ├─────────────────────────────────┐                                               |
|       ▼                                 ▼                                               |
|  Speed 1 (~1s debounced)           Speed 2 (5-15s interval)                             |
|  Technical Sub-Scores              Recombine 100-pt Composite Scores                    |
|  EMA/RSI/ATR/BBands                Live Valuation = live_price ÷ latest_reported_EPS   |
|  -> indicators_cache               -> composite_scores_cache                            |
|       │                                 │                                               |
|       └────────────────┬────────────────┘                                               |
|                        ▼                                                                |
|            /api/stream/live-prices (SSE)                                                |
|                        │                                                                |
|                        ▼                                                                |
|       Dashboard UI (Opportunity Monitor updates live)                                   |
|                                                                                         |
|  Slow Persistence (60s timer / shutdown) ──► SQLite market_live table                   |
|  (Zero per-tick DB writes — prevents SQLite write contention)                            |
+-----------------------------------------------------------------------------------------+

+-----------------------------------------------------------------------------------------+
|                          2. DAILY / EVENT PIPELINE (Batch)                              |
|                                                                                         |
|  NSE/BSE Corporate Filings & XBRL                                                       |
|  FII/DII Institutional Flow & Bulk/Block Deals                                          |
|  Screener.in Fundamentals (Weekly refresh, 2-6s jitter, stale fallback)                 |
|  AMFI Mutual Fund Flows & Defensive Allocation                                          |
|       │                                                                                 |
|       ▼                                                                                 |
|  Full rescoring & deep forensic/tax analysis ──► SQLite system.db                       |
+-----------------------------------------------------------------------------------------+
```

## Detailed Process Separation & Responsibilities

### 1. LIVE SERVICE (Continuous, Real-time)
- **Module**: `services.live_feed.DhanLiveFeedService` & `services.live_scorer.LiveScorerService`
- **Execution Mode**: Continuous background task running within `web_server.py`.
- **Data Flow**:
  1. Market-hours Dhan WebSocket streams continuous tick updates (`ltp`, `high`, `low`, `volume`, `vwap`) into in-memory `live_cache`.
  2. **Speed 1 Tier (~1s debounced)**: Computes tick-reactive technical indicators (`EMA20`, `RSI`, `ATR`, `BBands`) cached in `indicators_cache`.
  3. **Speed 2 Tier (5-15s interval)**: Recombines technical sub-scores with fundamental & momentum metrics to calculate live composite 100-point scores (`overall_score`, live P/E = `live_price / latest_reported_EPS`) cached in `composite_scores_cache`.
  4. **SSE Endpoint (`/api/stream/live-prices`)**: Streams real-time tick price deltas and live top opportunities to connected web clients via Server-Sent Events (`EventSource`).
  5. **FastAPI Opportunities Endpoint (`/api/opportunities`)**: Serves Opportunity Monitor data directly from `LiveScorerService.get_composite_scores()` in-memory cache without triggering `main.py` pipeline re-runs.
  6. **Slow Persistence**: Flushes `live_cache` snapshots to SQLite `market_live` table via 60-second background worker to eliminate per-tick DB write lock contention.

### 2. DAILY / EVENT PIPELINE (Batch Execution)
- **Module**: `main.py` / `data.sync_engine.SyncEngine`
- **Execution Mode**: Triggered on demand via CLI (`python main.py`), user manual click on "Run Main Pipeline" button, or scheduled daily cron (07:00 AM / 18:00 PM IST).
- **Data Flow**:
  1. Fetches daily EOD corporate filings, XBRL earnings statements, FII/DII institutional flows, bulk/block deal records, and weekly Screener.in fundamentals.
  2. Performs deep forensic Beneish M-Score, Altman Z-Score, capital allocation, and Markowitz portfolio optimization.
  3. Persists batch evaluation state and trade journal entries to SQLite `system.db` database.

## Market Session States
- `PRE_OPEN`: 09:00–09:15 IST (Mon-Fri)
- `OPEN`: 09:15–15:30 IST (Mon-Fri, excluding NSE holidays)
- `CLOSED`: Outside 09:15–15:30 IST, weekends, and NSE trading holidays (serves last-close cached values instead of a frozen/empty feed)

## Daily Auth Token Renewal
- Scheduled re-auth routine at 09:00 IST refreshes Dhan session tokens automatically before market open.

## Stale Data Fallback Protocol
- When Screener.in or fundamental scraping is unavailable, the composite scorer preserves last known cached values with a `stale: true` flag, preventing unfair score zeroing.
