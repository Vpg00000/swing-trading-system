# Swing Trading Decision-Support System — Design Spec

Personal decision-support tool for a single user's own ₹1 crore capital in the
Indian cash market. Produces recommendations only — the user manually places
every trade in their own broker app. No auto-execution, no advice to third
parties.

## Scope and hard exclusions

- No F&O (futures/options) — needs same-day active attention, excluded.
- No leverage on the core/momentum sleeve. Small capped leverage (~1.5x) only
  allowed on the opt-in event/intraday-short sleeves, sized so ₹-risk stays
  constant (leverage changes exposure, not risk-per-trade).
- No retail forex speculation via offshore/unauthorized platforms, in any
  form (direct, or routed through crypto conversion) — illegal for Indian
  residents under FEMA regardless of wrapper or physical location.
- No direct crude oil exposure (no non-derivative retail vehicle in India).
- Crypto: only direct buy-and-hold on a registered Indian exchange, small and
  infrequently traded (30% flat tax + 1% TDS per trade makes active trading
  self-defeating). No offshore trading via crypto conversion loops.
- Not a multi-user / multi-jurisdiction advisory product. Giving personalized
  buy/sell recommendations to other people is regulated investment advisory
  (SEBI RIA in India, DFSA/SCA in UAE) — out of scope for this build.

## Phased build order

**Phase 1 (this build): higher-risk sleeve** — individual equities, momentum
ranking, event-driven satellite, opt-in intraday short.

**Phase 2 (later): lower-risk sleeve** — index ETFs, mutual funds, Gold/Silver
ETF, arbitrage/liquid funds, global equity satellite (LRS).

## Capital allocation (target shape once both phases exist)

| Sleeve | % of capital | Notes |
|---|---|---|
| Core momentum equity | 45-70% (regime-dependent) | Phase 1 |
| Event-driven satellite | 15-20% | Phase 1 |
| Opt-in intraday short | 0-5%, occasional | Phase 1, requires active attention that day |
| Gold/Silver ETF | 10% | Phase 2 |
| Arbitrage/liquid funds | 10-15% | Phase 2 |
| Cash | 5%+ | Always allowed to be the answer |

Hard caps: single stock ≤5% of capital, single sector ≤20%.

Note on implementation (`engine/allocation.py`): Gold/Silver stays fixed at
10% and Cash at 5% regardless of regime, but Arbitrage/liquid is NOT capped
at 10-15% — it absorbs whatever capital the regime-driven equity cap keeps
out of the market (e.g. ~60% in a RISK-OFF regime with 25% max equity
exposure), so de-risked capital always has a concrete low-risk-yield home
instead of sitting idle. The 10-15% figure above describes the typical
RISK-ON shape, not a hard ceiling.

## Regime filter

Inputs: Nifty 50 vs 200-DMA, India VIX level.

| Nifty vs 200-DMA | VIX | Regime | Max equity exposure |
|---|---|---|---|
| Above, rising | <15 | Risk-ON | up to 70% |
| Above, flattening | 15-20 | Risk-ON (cautious) | up to 50% |
| Below, or VIX 20-30 | — | Risk-OFF | ≤25% |
| Below + VIX >30 | — | Emergency | ≤10% |

Checked once per day (morning); regime shifts are slow.

## Momentum ranking (core sleeve)

- Universe: Nifty 200 constituents + sector ETFs, liquidity-filtered
  (min ~₹5-10cr average daily traded value).
- Score = 60% × 6-month return + 40% × 3-month return.
- Rebalanced weekly. Hold top 5-8 ranked names.

## Event-driven satellite

- Trigger: material news (results, order win, regulatory approval, etc.)
- Confirmation required before flagging: price move ≥3% AND volume ≥1.5x
  20-day average on the news day.
- Entry only Day+1 or Day+2 (never same-day chase).
- Priced-in check: compare current reaction magnitude to historical
  comparable-event reactions before flagging as still-actionable.
- Max 5% per name, max 3 concurrent event positions (≤15% of capital).

## Position sizing and stops (volatility-adjusted, applies to all sleeves)

```
ATR = 14-day Average True Range
Stop distance = 2 x ATR
Risk per trade = 0.5%-1% of total capital
Position size (₹) = Risk per trade (₹) / Stop distance (%)
```

Trailing stop: once position is up >1x ATR, trail stop at 2x ATR below the
highest price reached (lets winners run instead of a fixed target).

Leverage (event sleeve only, opt-in): reduce position size proportionally so
₹-risk-per-trade is unchanged. Never combine "tight stop" with leverage.

## Opt-in intraday short sleeve

Gating conditions (all required):
1. User has explicitly confirmed they have time to actively watch it today.
2. Bottom-tier momentum rank AND confirmed negative catalyst (not just "looks
   like it might fall").
3. Stock is on the high-liquidity/F&O-eligible list (SEBI short-sell
   eligibility).
4. Entry only before ~1:30-2:00 PM.

Mechanics: stop-loss placed same second as entry (2x ATR above entry), max
3-5% position size, hard close by 3:15 PM regardless of P&L, never average
down.

## Notification tiers

- **Approval-required**: new buys, switches, regime-driven exposure changes,
  weekly rebalance sells. Nothing executes without explicit YES.
- **Informational**: stop-loss/target already auto-filled via GTT order — no
  action needed, told after the fact.
- **Urgent**: portfolio drawdown >8% from peak, Nifty -4%+ intraday or VIX
  >35, stop gapped through. Escalated channel/alert.

## Daily action cap

Max 3 capital-committing actions per day (new buy / discretionary sell /
switch). Unlimited and exempt from the cap: GTT stop/target fills, emergency
de-risk actions. If more than 3 legitimate candidates appear, show only the
top 3 by expected-return/risk score; log the rest for next-day review.

## Check-in schedule

| Time (IST) | Purpose |
|---|---|
| 7:00-8:30 AM | Full scan: regime, momentum re-rank, event candidates, news/demand-scenario review, corporate-action/earnings calendar check |
| ~11:00-11:30 AM | Quick check — material moves since open, pending approvals |
| ~1:00-1:30 PM | Position check; mandatory if an intraday short is open |
| 3:00-3:30 PM | Full re-rank ("if I had cash right now, what would I buy?"), close any open intraday short by 3:15 PM |
| Evening | Daily P&L (gross/net of costs+tax), attribution, tomorrow's watchlist |
| Ad hoc (urgent tier) | Crash/drawdown/gap events — fires any time |

Every check-in re-scans the full universe fresh, not a cached view.

## Risk controls

- Correlation/concentration check before adding a position (no hidden
  sector-stacking, e.g. 3 bank stocks = 1 concentrated bet).
- Weekend/pre-event gap-risk flag (Budget, RBI policy, Fed meeting, earnings).
- Circuit-limit awareness — stop-loss cannot fill if the stock is frozen at
  a circuit; flag exposure to circuit-prone names.
- Broker/data outage fallback: default to holding existing positions, no new
  entries until data/connectivity is confirmed reliable again.
- Portfolio emergency de-risk: -8% drawdown from peak -> halve equity
  exposure; VIX >35 or Nifty -4% single day -> emergency mode (≤10% equity).

## Tax and cost discipline

- STCG (equity, <12mo): 20% flat. LTCG (>12mo): 12.5% above ₹1.25L/yr
  exemption. Switch only if incremental expected net return > transaction
  cost + tax cost + uncertainty premium.
- STCG->LTCG countdown tracker: flag positions approaching the 12-month mark
  where holding a few more days changes the tax rate materially.
- Quarterly tax-loss harvesting review (real losses only, no artificial
  transactions).
- Turnover kept low by design (weekly rebalance, 3-action/day cap) — both a
  cost-control and a defense against business-income reclassification risk.
- Round-trip transaction cost estimate: ~0.15-0.35% (brokerage + STT 0.1%
  buy + 0.1% sell + exchange charges + GST + stamp duty + DP charges),
  before slippage. Always net this out of any expected-return calculation.

## Future-demand scenario module

- Forward-looking: government capex/policy announcements, capacity
  expansion filings — estimate economic magnitude and historical re-rating
  pattern, feeds into sector-tilt within momentum ranking (not an immediate
  trade trigger on its own).
- Commodity/geopolitical: track oil/metals/freight/geopolitical disruptions,
  map sector winners/losers, feed into sector-tilt.
- Stress testing: before new entries and weekly on existing holdings,
  estimate portfolio impact of demand-shock scenarios; >~15% combined
  estimated impact from one scenario is a concentration-risk flag requiring
  rebalancing before adding more.

## News/research layer

- Tier 1 sources (NSE/BSE filings, RBI/SEBI/Government releases) prioritized
  over Tier 2 (Reuters/Bloomberg/quality media) over Tier 3 (social/forums).
  Tier 3 never independently triggers a flagged candidate.
- Priced-in check on every positive/negative event: compare current price
  reaction to historical comparable-event reaction before treating it as
  still-actionable.
- Clearly label each recommendation's basis: "data-confirmed" (price+volume
  rule triggered) vs "judgment-based" (macro/news reasoning) so confidence
  is transparent.

## Realistic performance expectation (not a promise)

No legitimate strategy sustains ~1%/day compounded (~1,130%/year) — verified
against the best real-world track record in the industry (Renaissance
Medallion, ~39-72%/year, closed to outside capital since 1993) and against
known fraud patterns (BitConnect's "1% daily" claim was a confirmed Ponzi
scheme). Target range for this system, informed by comparable published
momentum/trend strategies, not yet backtested on this specific universe:

| Scenario | Annual, net of cost+tax |
|---|---|
| Conservative | 10-15% |
| Base case | 15-25% |
| Aggressive | 25-40%, with proportionally higher drawdown risk |

These figures are illustrative until a real backtest is run (Phase 1
includes building that backtest before relying on live numbers).

## Data source (Phase 1)

Free EOD data (yfinance) — daily OHLCV is sufficient for regime/momentum/
event-confirmation logic, which all operate on daily closes, not intraday
ticks. Live/intraday broker API is a future upgrade if needed, not a Phase 1
requirement — Dhan is the likely candidate (free API, no subscription fee,
unlike Kite Connect) if/when holdings auto-sync or live intraday data is
wanted; not needed while the system stays recommendation-only with manually
maintained `config/portfolio.json`.

## Global macro / cross-asset context

Forex (USD/INR, DXY, EUR/USD, GBP/USD), commodities (Brent, WTI, natural gas,
gold, silver, copper), global rates (US 10Y), global equity indices (S&P
500, Nasdaq, Nikkei, Hang Seng), crypto (BTC/ETH in INR), and Nifty sectoral
indices (Bank/IT/Pharma — Auto/FMCG/Metal excluded, yfinance only returns 1
day of history for those tickers) are pulled live via yfinance
(`data/global_macro.py`) and shown in the daily report as context for the
"commodity/geopolitical → sector-tilt" module above and the regime read.
**Data-input only** — this does not enable trading forex, crude, or crypto
beyond what the Scope/hard-exclusions section already allows (crypto:
buy-and-hold only, small, on a registered Indian exchange; forex/crude
retail speculation remains excluded per FEMA / no retail vehicle).

## Build status (Phase 1 + Phase 2 core)

Implemented and tested against real market data at
`/Volumes/code/swing-trading-system/`:

- `config/universe.py` — universe sourced from the real, current NSE Nifty
  500 constituent list (`config/nifty500_symbols.txt`, pulled from
  archives.nseindia.com) + 6 sector/gold ETFs. Liquidity filter
  (min ₹50cr/day average turnover) narrows ~506 nominal symbols down to
  ~330 actually-tradeable-at-size candidates.
- `data/fetch.py` — pulls 1y daily OHLCV via yfinance, caches to
  `data/cache/*.csv`. Re-run periodically (data goes stale).
- `engine/regime.py` — Nifty vs 200-DMA + India VIX -> regime classification
  and max equity exposure cap.
- `engine/momentum.py` — 60/40 blended 6mo/3mo momentum ranking, ATR(14)
  based stop distance (2x ATR) and volatility-adjusted position sizing
  (0.75% of capital risked per trade).
- `engine/news.py` — mechanical price+volume event confirmation
  (>=3% move on >=1.5x avg volume) across the universe, plus
  `build_news_prompt()` which produces the brief for an AI research pass
  (Tier 1/2/3 source judgment, priced-in assessment) -- proven working via
  a real WebFetch-based lookup during development (flagged BLS.NS's -11%
  move, correctly traced to a "visa irregularities" allegation/denial).
- `data/amfi.py` — fetches the official daily AMFI NAV file
  (portal.amfiindia.com/spages/NAVAll.txt, ~14k fund/plan/option rows) and
  classifies every scheme into a sleeve (gold_etf, silver_etf, equity_etf,
  liquid_fund, overnight_fund, arbitrage_fund, index_fund) by category
  header, with a name-based override for gold/silver since AMFI's own
  headers misfile some of them.
- `data/etf_universe.py` — joins AMFI's gold/silver/equity ETF records to
  real NSE tickers via ISIN (`config/nse_etf_list.csv`, the official NSE
  ETF security list), then picks the most liquid ticker per sleeve by real
  5-day average turnover (e.g. correctly prefers GOLDBEES/SILVERBEES over
  dozens of lower-volume competing ETFs tracking the same benchmark).
- `data/defensive_funds.py` — ranks liquid/overnight/arbitrage funds by
  30-day trailing NAV return (the free-data proxy for "lowest cost, best
  net yield" since AMFI's file has no expense-ratio field), using AMFI's
  historical-NAV endpoint with a lookback window to skip non-trading days.
- `data/index_funds.py` — filters AMFI's 45-fund index_fund sleeve down to
  genuinely broad-market Nifty 50/Sensex passive funds (name-marker
  include/exclude lists), rejecting sector/factor/cap-slice index funds
  (Next 50, Midcap, Smallcap, Equal Weight, Momentum/Quality/Low-Vol,
  sector indices), then ranks the survivors by the same trailing-NAV-return
  proxy as data/defensive_funds.py.
- `engine/allocation.py` — combines the regime-driven equity budget with a
  fixed 10% gold/silver hedge (70/30 split), a 5% cash floor, and routes
  whatever capital the regime keeps out of equities into the
  liquid/arbitrage parking sleeve — so a RISK-OFF/EMERGENCY regime has a
  concrete destination for de-risked capital instead of sitting idle.
  Within the equity budget itself, a fixed 25% slice
  (`INDEX_FUND_EQUITY_SLICE_PCT`) is carved out to the top-ranked broad
  Nifty 50 index fund instead of individual momentum stock picks — a
  risk-reduction choice within the existing equity %, not a new capital
  sleeve (user-confirmed design decision).
- `data/corporate_actions.py` — NSE's own corporate-filings API
  (nseindia.com/api/corporates-corporateActions,
  nseindia.com/api/corporate-board-meetings), queried market-wide over a
  21-day forward window (no per-symbol round-trips, no login/session cookie
  needed for these two endpoints) for dividends/splits/bonus/rights/
  buybacks (ex-date = gap-risk date) and board-meeting intimations (NSE's
  free proxy for an earnings calendar — meeting-intimation date, not always
  the confirmed results date). Feeds DESIGN.md's morning
  "corporate-action/earnings calendar check" and the pre-event gap-risk flag.
- `engine/tax.py` — STCG (20% flat, <12mo) vs LTCG (12.5% above ₹1.25L/yr
  exemption, >12mo) classification per holding, an STCG->LTCG countdown flag
  (within 15 days of crossing), a tax-loss-harvest flag (real unrealized
  losses only), and a net switch-hurdle estimate (est. tax + ~0.25%
  round-trip transaction cost) that a SELL/switch must clear per DESIGN.md's
  "Tax and cost discipline" rule. Requires `buy_date`/`buy_price`/`quantity`
  on a holding (`config/portfolio.json`) — these are user-specific facts no
  market data source can supply, so holdings lacking them are shown without
  a tax status rather than guessed at.
- `engine/correlation.py` — sector-concentration check per DESIGN.md's risk
  controls ("no hidden sector-stacking, e.g. 3 bank stocks = 1 concentrated
  bet") and hard cap (single sector ≤20%). Uses yfinance's GICS `sector`
  field as the free-data grouping proxy (real pairwise correlation would
  need a paid factor model) — flags sectors already over cap in current
  holdings, and blocks a candidate BUY that would push its sector over cap.
- `engine/manual_checks.py` — sector/industry → regulator-or-site mapping
  (Healthcare→US FDA/CDSCO, Utilities-Electric→CERC/Power Ministry,
  Utilities-Gas→PNGRB, Communication Services→TRAI, Financial
  Services-Banks→RBI, Basic Materials→CRISIL/ICRA/CARE, etc.) for the
  manual-judgment checks that have no free API worth automating. Only
  surfaces a reminder for a sector actually present among today's top-ranked
  candidates/holdings — deliberately not a static full-menu checklist every
  morning regardless of what's in the universe (user-requested design:
  reminders should be contextual to that day's actual candidates).
- `engine/report.py` — assembles regime + Phase 2 allocation + momentum
  ranking + news flags + tax status + corporate-action calendar + sector
  concentration + contextual manual-check reminders into the daily report
  format, cross-references `config/portfolio.json` (user's actual holdings)
  for HOLD/SELL signals, gates BUY suggestions on unresolved news flags and
  sector-stacking risk, nets the tax/transaction-cost hurdle against
  rank-based SELL suggestions, and enforces the 3-action/day display cap.
  Full Phase 1+2 pipeline runs end-to-end in ~15-20s against live data
  (corporate-action/sector lookups add a few more seconds).

Not yet built: scheduled/automatic runs, notification delivery (Telegram),
backtest.
