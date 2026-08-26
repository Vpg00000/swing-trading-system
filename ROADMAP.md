# Roadmap — Intelligence Layer Expansion

Brief plan for extending the daily report beyond momentum/regime/risk into
money-flow, insider, and AI-research signals. Backtest deferred (user call).

## Target architecture (full pipeline, end state)

```
DATA SOURCES: Dhan API (live/holdings, future) + NSE/BSE/SEBI/AMFI/NSDL/RBI
  (public official data, mostly built) + Claude Research (on-demand)
        ↓ normalize (symbol/timestamp/dedup/source-priority/freshness)
        ↓ store (file cache today; Postgres/Redis only if/when live data lands)
DETERMINISTIC ENGINE:
  Global Macro → Market Regime → Sector Engine → Catalyst Engine
        → Money Flow (FII/DII/insider) → Bulk/Block/Pledge → Ownership Change
        → Price+Volume → Relative Strength → Fundamental Quality → Governance/Risk
        ↓
CLAUDE PROMPT ENGINE → CLAUDE RESEARCH AGENT → STRUCTURED JSON
        ↓
DECISION ENGINE: Hard Rules + AI Analysis + Risk Engine → Expected Return/Risk
        → Final Ranking → Top 3 Actions → Human Approval (YES/NO)
        → Manual Execution (broker app) → Portfolio Sync → P&L/Journal/Backtest
```

Near-term buildable now (file-cache, yfinance/NSE, no new infra): everything
up through Decision Engine. **Deferred, not Phase 1**: Dhan live-market-data
integration and auto portfolio-sync (DESIGN.md already scopes this as a
future upgrade, not required while the system stays recommendation-only with
manually maintained `config/portfolio.json`); Postgres/Redis (unnecessary
until there's actual live/intraday data volume to justify it — today's daily
EOD batch fits fine in flat-file cache).

## Already built (Layer 1 — deterministic data)

`config/universe.py`, `data/fetch.py`, `engine/regime.py`, `engine/momentum.py`,
`engine/news.py`, `data/amfi.py`, `data/etf_universe.py`,
`data/defensive_funds.py`, `data/index_funds.py`, `data/corporate_actions.py`,
`engine/tax.py`, `engine/correlation.py`, `engine/manual_checks.py`,
`data/global_macro.py`, `engine/allocation.py`, `engine/report.py`.

## Next to build (Layer 1 continued)

| Module | Confidence | Source |
|---|---|---|
| `data/insider.py` | High | NSE Reg 7(2) JSON API |
| `data/bulk_block.py` | High | NSE bulk/block deal JSON API |
| `data/promoter_pledge.py` | High | NSE encumbrance JSON API |
| `engine/priced_in.py` | High | our own price history, quantitative |
| `engine/sector_score.py` | High | derived from existing data (RS/breadth/commodity-tilt) |
| `data/shareholding.py` | Medium | NSE FII/DII/MF/promoter % — quarterly, weaker parsing |

## Manual-only (no reliable free API — flagged via `engine/manual_checks.py`, not automated)

- Cash-flow/fundamental quality (CFO/PAT, ROCE, Debt/EBITDA)
- Governance (related-party transactions, auditor change)
- Earnings surprise / consensus estimates
- Most sector-specific deep-dives (Pharma FDA letters, Banking NIM/GNPA, etc.)

## Layer 2 — Research (Claude, on-demand)

`engine/prompt_engine/` — one prompt file per context, each returning a
structured JSON reply (catalyst, priced-in assessment, bull/bear case,
sources, confidence). Claude never computes position size/risk/exposure —
that stays in Python.

```
engine/
    prompt_engine/
        system_prompt.md
        market_research_prompt.md
        stock_research_prompt.md
        event_research_prompt.md
        sector_research_prompt.md
        portfolio_review_prompt.md
        morning_scan_prompt.md
        midday_scan_prompt.md
        closing_scan_prompt.md
        emergency_prompt.md
```

Scheduling ("runs automatically 4x/day") is a separate infra decision, not
yet explored — decoupled from prompt content.

## Layer 3 — Decision/report

`engine/report.py` extends to include insider/bulk-block/pledge/sector-score
sections + a per-candidate score card. Anything Layer 1 can't compute
automatically shows as a manual-check reminder, not a fabricated number.

## Build order

1. `data/insider.py`, `data/bulk_block.py`, `data/promoter_pledge.py`
2. `engine/priced_in.py`
3. `engine/sector_score.py`
4. `data/shareholding.py`
5. `engine/prompt_engine/` (files above)
6. Candidate score-card in `engine/report.py`
7. Backtest (later, user's call)
