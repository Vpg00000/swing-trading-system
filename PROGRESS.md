```
╔══════════════════════════════════════════════════════════════════════════════╗
║              AI MARKET INTELLIGENCE + PORTFOLIO SYSTEM                       ║
║                    PROGRESS TRACKER  —  Updated 2026-08-26                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

  Legend:
    ✅  Done & working          ⚠️  Partial / needs wiring
    ❌  Not built               🔗  Wired into live report
    [BE] Backend (Python)       [UI] Dashboard / Frontend
    [INF] Infrastructure        [MAN] Manual / human step

══════════════════════════════════════════════════════════════════════════════
  SYSTEM CONFIG
══════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────┐
    │  Capital ₹50L · Max Equity · Stock · Sector · Risk/Trade│
    │  ✅ [BE]  config/settings.py + DESIGN.md                │
    │  ✅ [MAN] Human approval gate — never auto-trades        │
    └───────────────────────────────┬─────────────────────────┘
                                    │
                                    ▼

══════════════════════════════════════════════════════════════════════════════
  01  DATA ACQUISITION LAYER
══════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────┐
    │      DHAN API        │
    │  ✅ [BE] client.py   │
    └─────────┬────────────┘
              │
    ┌─────────┴──────────────────────────────────────┐
    │                                                 │
    ▼              ▼               ▼                  ▼
 LIVE PRICE    HOLDINGS        POSITIONS          CASH/FUNDS
 ✅ [BE]       ✅ [BE]         ⚠️ [BE]            ✅ [BE]
 market_data   holdings.py     basic only          holdings.py
    │              │               │                  │
    └─────────┬────┴───────────────┴──────────────────┘
              ▼
          ORDERS / EXECUTIONS
          ❌ [MAN]  manual Dhan app  (intentional — no auto-trade)

    ┌──────────────────────────┐
    │    OFFICIAL SOURCES      │
    └────────────┬─────────────┘
                 │
   ┌─────────────┼─────────────────────────────┐
   ▼             ▼             ▼               ▼
  NSE           BSE           SEBI           AMFI
  ✅ [BE]       ❌             ❌             ✅ [BE]
  bhavcopy      not built    manual flag     amfi.py / mf_holdings.py
  fii_dii.py
  nse_filings.py
  cyclical_trend.py
  net_alpha.py
  bulk/block
  insider
  corporate
  shareholding
  pledge

    ┌──────────────────────────┐
    │   OTHER RESEARCH DATA    │
    └────────────┬─────────────┘
                 │
   ┌─────────────┼───────────────────────────────────┐
   ▼             ▼              ▼                    ▼
FUNDAMENTALS  GLOBAL MACRO   ETF / NAV           CREDIT RATINGS
✅ [BE]        ✅ [BE]        ✅ [BE]              ❌ [MAN]
screener.py   global_macro   amfi.py              manual flag only
              .py            etf_universe.py

    ┌──────────────────────────┐
    │  NEWS / RESEARCH SOURCES │
    └────────────┬─────────────┘
                 │
   ┌─────────────┼──────────────────────────┐
   ▼             ▼              ▼            ▼
PRICE/VOL     COMPANY IR     FORUMS       GLOBAL NEWS
ANOMALY       ❌ [MAN]        ❌ [MAN]    ❌ [MAN]
✅ [BE]        Claude only    manual       manual
news.py

══════════════════════════════════════════════════════════════════════════════
  02  DATA NORMALIZATION + VALIDATION
══════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────────────────────────────────────┐
    │  DATA NORMALIZATION                                   │
    │  ⚠️  [BE]  Symbol mapping (.NS strip)  screener.py   │
    │  ✅  [BE]  Timestamp normalization  (yfinance/pandas) │
    │  ⚠️  [BE]  Duplicate removal  (cache overwrite only) │
    │  ⚠️  [BE]  Freshness check  (24h TTL screener only)  │
    │  ❌        Currency normalization  (not built)        │
    │  ❌        Corporate-action price adjust  (not built) │
    └──────────────────────────────────────────────────────┘
                              │
                              ▼
    ┌──────────────────────────────────────────────────────┐
    │  DATA VALIDATION                                      │
    │  ✅  [BE]  Missing data detection  (status fields)    │
    │  ✅  [BE]  API failure detection   (data_health dict) │
    │  ❌        Outlier detection  (not built)             │
    │  ❌        Source consistency check  (not built)      │
    └──────────────────────────────────────────────────────┘
                              │
                              ▼
    ┌──────────────────────────────────────────────────────┐
    │  SOURCE PRIORITY  (Tier 1 Official > Tier 2 > Tier 3) │
    │  ⚠️  Implicit only — no formal tier routing           │
    └──────────────────────────────────────────────────────┘

══════════════════════════════════════════════════════════════════════════════
  03  DATA STORAGE
══════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────────────────────────────────────┐
    │  MARKET DATA STORE                                    │
    │  ✅  [BE]   Historical OHLCV  →  data/cache/*.csv     │
    │  ✅  [BE]   Fundamentals      →  data/cache/screener_*│
    │  ✅  [BE]   NAV history       →  data/nav_history/    │
    │  ⚠️  [BE]   Research outputs  →  reports/research/*.md│
    │  ❌  [INF]  PostgreSQL  (not built — flat-file only)  │
    │  ❌  [INF]  Redis live cache  (not built)             │
    │  ❌  [INF]  Parquet store     (not built)             │
    └──────────────────────────────────────────────────────┘

══════════════════════════════════════════════════════════════════════════════
  04  ACTUAL PORTFOLIO ENGINE
══════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────┐
    │      DHAN API        │
    └────────┬─────────────┘
             │
    ┌────────┴──────────────────────────┐
    ▼              ▼                   ▼
 HOLDINGS      POSITIONS           CASH/FUNDS
 ✅ [BE]       ⚠️ [BE]             ✅ [BE]
 holdings.py   basic only          holdings.py
    │              │                   │
    └──────────────┼───────────────────┘
                   ▼
        ┌──────────────────────────────────────┐
        │  ACTUAL PORTFOLIO STATE              │
        │  ✅ [BE]  report.py + allocation.py  │
        │     Invested · Cash · P&L            │
        │     Sector exposure · Correlation    │
        └──────────────┬───────────────────────┘
                       ▼
        ┌──────────────────────────────────────┐
        │  PORTFOLIO RECONCILER                │
        │  ✅ [BE]  allocation.py              │
        │     Model target ↔ Actual state      │
        └──────────────┬───────────────────────┘
                       ▼
                    DRIFT
                    ✅ [BE]  drift_table in report.py
                       ▼
                 ACTION REQUIRED
                 ✅ [BE]  Section 4 of daily report
                 ✅ [UI]  Shown in web dashboard

══════════════════════════════════════════════════════════════════════════════
  05  GLOBAL MACRO ENGINE
══════════════════════════════════════════════════════════════════════════════

    S&P500  Nasdaq  Nikkei  Hang Seng  DXY  USD/INR
    US10Y   Brent   Gold   Silver   Copper  Crypto
    ✅ [BE]  all fetched via  data/global_macro.py
               │
               ▼
    ┌──────────────────────────────────┐
    │  GLOBAL MACRO ENGINE             │
    │  ✅ [BE]  global_macro.py        │
    │     Risk-on/off · Liquidity      │
    │     Inflation · Rates · Dollar   │
    │     Commodity · Global equity    │
    └──────────────────────────────────┘
               │
               ▼
         INDIA IMPLICATION
         ⚠️ [MAN]  written to Claude prompt  (narrative only)
         ✅ [UI]   shown in dashboard macro section

══════════════════════════════════════════════════════════════════════════════
  06  MARKET REGIME ENGINE
══════════════════════════════════════════════════════════════════════════════

    Nifty 200DMA · 20/50DMA · Breadth · VIX
    FII Flow · Global regime · USD/INR + rates
    ✅ [BE]  all inputs fed into  engine/regime.py
               │
               ▼
    ┌──────────────────────────────────┐
    │  REGIME SCORE /100               │
    │  ✅ [BE]  engine/regime.py       │
    │     trend/vol/breadth/global     │
    └──────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 BULLISH    NEUTRAL    BEARISH
 RISK-ON   CAUTIOUS   RISK-OFF  EMERGENCY
 ✅ [BE]  engine/regime.py → regime field
               │
               ▼
    MAX EQUITY EXPOSURE (regime-driven)
    ✅ [BE]  max_equity_exposure field
    ✅ [UI]  shown in dashboard
    🔗  feeds composite score  →  regime_component /10

══════════════════════════════════════════════════════════════════════════════
  07  SECTOR ROTATION ENGINE
══════════════════════════════════════════════════════════════════════════════

    Sector Return · RS vs Nifty · Sector Breadth
    Volume · FII/MF Flow · Commodity sensitivity
    ✅ [BE]  engine/sector_score.py
    ❌ [BE]  Earnings trend by sector  (not built)
    ❌ [BE]  FII flow by sector  (stock-level only)
               │
               ▼
    ┌──────────────────────────────────┐
    │  SECTOR SCORE /100               │
    │  ✅ [BE]  engine/sector_score.py │
    └──────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 STRONG    NEUTRAL      WEAK
 ✅ [BE]  sector_score.py → classification
    ✅ [UI]  shown in dashboard sector table
    🔗  feeds composite score  →  sector_component /10

══════════════════════════════════════════════════════════════════════════════
  08  CATALYST ENGINE
══════════════════════════════════════════════════════════════════════════════

    News · Filings · Corporate Actions · Earnings
    Management · Government/Policy · Macro
    ✅ [BE]  price+volume anomaly  →  engine/news.py
    ✅ [BE]  corporate actions     →  data/corporate_actions.py
    ⚠️ [BE]  earnings trigger  (flagged, no sentiment score)
    ❌ [BE]  govt/policy trigger  (manual only)
               │
               ▼
    ┌──────────────────────────────────────┐
    │  CATALYST ENGINE                     │
    │  ⚠️ [BE]  binary flag today          │
    │     POSITIVE · NEGATIVE · NEUTRAL    │
    └──────────────────────────────────────┘
               │
               ▼
         CATALYST SCORE
         ⚠️ [BE]  flag → decision.py → catalyst_component /15
         🔗  feeds composite score

══════════════════════════════════════════════════════════════════════════════
  09  MONEY FLOW + OWNERSHIP ENGINE
══════════════════════════════════════════════════════════════════════════════

    FII/FPI · DII/MF · Insider · Promoter
    Bulk/Block · SAST · Pledge · Ownership
    ✅ [BE]  shareholding.py  (FII/DII QoQ)
    ✅ [BE]  insider.py       (buy/sell signals)
    ✅ [BE]  bulk_block.py    (bulk/block deals)
    ✅ [BE]  pledge.py        (pledge %)
    ❌ [BE]  SAST disclosures  (not built)
               │
               ▼
    ┌──────────────────────────────────────┐
    │  MONEY FLOW ENGINE                   │
    │  ✅ [BE]  engine/money_flow.py       │
    │     Accumulation · Distribution      │
    │     Previous → Current → Change      │
    └──────────────────────────────────────┘
               │
               ▼
         MONEY FLOW SCORE /20
         ✅ [BE]  total_score field
         ✅ [UI]  shown in report + dashboard
         🔗  splits into  fii_dii /15  +  insider /10  in composite

══════════════════════════════════════════════════════════════════════════════
  10  PRICE + VOLUME ENGINE  (Technical)
══════════════════════════════════════════════════════════════════════════════

    Price · Return · Volume · 20/50/200DMA · ATR
    ✅ [BE]  OHLCV fetch         →  data/fetch.py
    ✅ [BE]  3M/6M return + ATR  →  engine/momentum.py
    ✅ [BE]  DMA (Nifty)         →  engine/regime.py
    ⚠️ [BE]  Volume trend  (event detection only)
    ❌ [BE]  Delivery % · VWAP · Breakout  (not built)
               │
               ▼
    ┌──────────────────────────────────────┐
    │  TECHNICAL ENGINE                    │
    │  ⚠️ [BE]  Technical score /100       │
    │     proxied by momentum percentile   │
    └──────────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 TREND     BREAKOUT   MOMENTUM
 ⚠️         ❌          ✅
 via DMA    not built  momentum.py
    │
    ▼
 TECHNICAL SCORE
 ⚠️ [BE]  percentile rank proxy today
 🔗  combined with RS → technical_component /15

══════════════════════════════════════════════════════════════════════════════
  11  RELATIVE STRENGTH ENGINE  ✅ NEW
══════════════════════════════════════════════════════════════════════════════

              STOCK
                │
       ┌────────┴─────────┐
       ▼                  ▼
     NIFTY              SECTOR
     ✅ [BE]            ✅ [BE]
     3M + 6M RS         sector ETF RS
       │                  │
       └────────┬─────────┘
                ▼
       RELATIVE STRENGTH
       ✅ [BE]  engine/relative_strength.py
       tanh-normalized combined ratio
                │
                ▼
         RS SCORE /100  +  /15 for composite
         ✅ [BE]  engine/relative_strength.py
         ⚠️ [BE]  report.py wire-up pending
         🔗  feeds technical_component

══════════════════════════════════════════════════════════════════════════════
  12  FUNDAMENTAL ENGINE  ✅ NEW
══════════════════════════════════════════════════════════════════════════════

    Revenue Growth · EPS Growth · ROE · ROCE
    Debt · OPM · P/E · P/B · Working Capital
    ✅ [BE]  data/screener.py  (screener.in scraper)
    ✅ [BE]  24h JSON cache  data/cache/screener_*.json
    ❌ [BE]  CFO/FCF direct  (not from screener.in)
               │
               ▼
    ┌──────────────────────────────────────┐
    │  FUNDAMENTAL SCORE /100              │
    │  ✅ [BE]  engine/fundamental.py      │
    │     Profitability /35  Growth /25    │
    │     Strength /20  CashFlow /20       │
    └──────────────────────────────────────┘
               │
               ▼
         ⚠️ [BE]  report.py wire-up pending
         🔗  feeds  fundamental_component /10  +  cashflow /5

══════════════════════════════════════════════════════════════════════════════
  13  VALUATION ENGINE  ✅ NEW
══════════════════════════════════════════════════════════════════════════════

    P/E · P/B · FCF Yield · Historical · Sector
    ✅ [BE]  from data/screener.py
    ❌ [BE]  EV/EBITDA · PEG  (screener.in doesn't expose)
               │
               ▼
    ┌──────────────────────────────────────┐
    │  VALUATION SCORE /100                │
    │  ✅ [BE]  engine/valuation.py        │
    │     P/E vs sector median             │
    │     P/B vs ROE-justified value       │
    │     FCF proxy via OPM               │
    └──────────────────────────────────────┘
               │
               ▼
         ⚠️ [BE]  report.py wire-up pending
         🔗  feeds  valuation_component /5

══════════════════════════════════════════════════════════════════════════════
  14  GOVERNANCE + RISK ENGINE  ✅ NEW
══════════════════════════════════════════════════════════════════════════════

    Auditor · Pledge · SEBI · Credit Rating
    Related parties · Accounting · Regulatory
    ✅ [BE]  Pledge %         from pledge.py
    ✅ [BE]  SEBI action      manual flag
    ✅ [BE]  Auditor flag     manual flag
    ✅ [BE]  Credit downgrade manual flag
    ✅ [BE]  Insider selling  from money_flow.py
    ❌ [BE]  Litigation · Related party  (not built)
               │
               ▼
    ┌──────────────────────────────────────┐
    │  GOVERNANCE RISK SCORE /100          │
    │  ✅ [BE]  engine/governance.py       │
    │     starts 100, deducts per flag     │
    └──────────────────────────────────────┘
               │
               ▼
         ⚠️ [BE]  report.py wire-up pending
         🔗  feeds  governance_component /5

══════════════════════════════════════════════════════════════════════════════
  15  EVENT DETECTION ENGINE
══════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────────────┐
    │  DHAN / PYTHON               │
    │  ✅ [BE]  engine/news.py     │
    └──────────────┬───────────────┘
                   ▼
       ABNORMAL MOVE DETECTED?
       ✅ [BE]  price > 3%  AND  volume > 2x avg
                   │
          ┌────────┴────────┐
          ▼                 ▼
         NO                YES
          │                 ▼
          │          PRICE + VOLUME
          │          ✅ [BE]  e.g. WELCORP +4.2%  3.6x vol
          │                 │
          │                 ▼
          │          EVENT TRIGGER
          │          ✅ [BE]  → feeds Claude prompt
          └─────────────────┘

══════════════════════════════════════════════════════════════════════════════
  16  CLAUDE RESEARCH ENGINE
══════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────────────────────────┐
    │  CLAUDE PROMPT ENGINE                    │
    │  ✅ [BE]  save_event_prompt()  report.py │
    │  ✅ [BE]  save_market_prompt() report.py │
    │  ✅ [BE]  auto-saved → reports/research/ │
    └──────────────────────────────────────────┘
                          │
                          ▼
             CLAUDE RESEARCH  (human pastes)
             ✅ [MAN]  intentional design
             ❌ [BE]   no auto Claude API calls

    Claude answers:
    ✅ [MAN]  What happened / Why / Is it new
    ✅ [MAN]  Bull case / Bear case / Unknowns
    ❌ [BE]   Structured JSON output  (not built)

══════════════════════════════════════════════════════════════════════════════
  17  PRICED-IN ENGINE
══════════════════════════════════════════════════════════════════════════════

    Current Move · Historical Move · Expected Impact
    ✅ [BE]  engine/priced_in.py
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
  UNDER     PARTIAL     FULLY
  PRICED    PRICED      PRICED
  ✅ [BE]  PricedInResult.status
               │
               ▼
         ACTION FILTER
         ✅ [BE]  → WAIT_FOR_NEWS_CONFIRMATION
         🔗  feeds  catalyst_component /15

══════════════════════════════════════════════════════════════════════════════
  18  CLAUDE STRUCTURED OUTPUT
══════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────────────────────────┐
    │  STRUCTURED JSON  ❌  not built yet       │
    │  Catalyst Score   ❌  manual only         │
    │  Confidence /100  ❌  not built           │
    │  Risk Flags       ❌  freeform text only  │
    └──────────────────────────────────────────┘

══════════════════════════════════════════════════════════════════════════════
  19  COMPOSITE INVESTMENT SCORE  ✅ COMPLETE
══════════════════════════════════════════════════════════════════════════════

    ┌────────────────────────────────────────────────────────┐
    │  Component          Weight   Status    Engine          │
    │  ─────────────────────────────────────────────────── │
    │  Market Regime        /10    ✅ 🔗     regime.py       │
    │  Sector               /10    ✅ 🔗     sector_score.py │
    │  Catalyst             /15    ✅ 🔗     news.py         │
    │  FII / DII / MF       /15    ✅ 🔗     money_flow.py   │
    │  Insider              /10    ✅ 🔗     money_flow.py   │
    │  Technical / RS       /15    ✅ 🔗     momentum.py     │
    │                               ⚠️       relative_strength│
    │  Fundamental          /10    ✅ 🔗     fundamental.py  │
    │  Cash Flow             /5    ✅ 🔗     fundamental.py  │
    │  Governance            /5    ✅ 🔗     governance.py   │
    │  Valuation             /5    ✅ 🔗     valuation.py    │
    │  ─────────────────────────────────────────────────── │
    │  TOTAL               /100    ✅        decision.py     │
    └────────────────────────────────────────────────────────┘
                          │
                          ▼
         INVESTMENT RANKING
         ✅ [BE]  ranked_candidates in report
         ⚠️ [BE]  full pipeline wire-up pending
         ✅ [UI]  shown in dashboard + scorecard

══════════════════════════════════════════════════════════════════════════════
  20  OPPORTUNITY ENGINES
══════════════════════════════════════════════════════════════════════════════

    ┌───────────┐  ✅ [BE]  engine/momentum.py
    │ MOMENTUM  │
    └─────┬─────┘
    ┌─────┴─────┐  ✅ [BE]  engine/news.py + priced_in.py
    │ CATALYST  │
    └─────┬─────┘
    ┌─────┴─────┐  ✅ [BE]  engine/money_flow.py (insider)
    │  INSIDER  │
    └─────┬─────┘
    ┌─────┴─────┐  ✅ [BE]  engine/money_flow.py (FII/DII)
    │INSTITUTION│
    └─────┬─────┘
    ┌─────┴─────┐  ❌  not built
    │ BREAKOUT  │
    └─────┬─────┘
    ┌─────┴─────┐  ❌  not built
    │MEAN REVERT│
    └─────┬─────┘
    ┌─────┴─────┐  ❌  not built
    │DEEP VALUE │
    └─────┬─────┘
    ┌─────┴─────┐  ❌  not built
    │SPECIAL SIT│
    └─────┬─────┘
          ▼
    OPPORTUNITY AGGREGATOR
    ⚠️ [BE]  only Momentum+Catalyst+Insider+FII active

══════════════════════════════════════════════════════════════════════════════
  21  EXPECTED RETURN ENGINE  ✅ NEW
══════════════════════════════════════════════════════════════════════════════

    Current Price  →  Entry Zone (±0.5×ATR)
    ✅ [BE]  engine/expected_return.py

    Target Price   →  Prior swing high (52w)  OR  3×ATR
    ✅ [BE]  engine/expected_return.py

    Expected Upside %  ·  Expected Loss %
    ✅ [BE]  engine/expected_return.py

    Probability of Success  (from composite score)
    ✅ [BE]  engine/expected_return.py

              ▼
    EXPECTED VALUE = prob × upside − (1−p) × loss
    ✅ [BE]  engine/expected_return.py
              │
              ▼
         RISK / REWARD
         ✅ [BE]  risk_reward field
         ✅ [UI]  scorecard layout done in report.py Section 10
         ⚠️ [BE]  generate_report_data() wire-up pending

══════════════════════════════════════════════════════════════════════════════
  22  TRANSACTION COST ENGINE  ✅ NEW
══════════════════════════════════════════════════════════════════════════════

         GROSS RETURN
               │
    ┌──────────┼──────────────┐
    ▼          ▼              ▼
 Brokerage  Slippage      Charges
 ✅ ₹0 Dhan ✅ tiered     ✅ all
               │              │
               ▼              ▼
 STT 0.1%   Exchange     Stamp Duty
 buy+sell   0.00297%     0.015% buy
 ✅ [BE]     ✅ [BE]      ✅ [BE]
               │
               ▼
             GST 18%  ✅ [BE]
               │
               ▼
          TOTAL COST  ✅ [BE]  engine/transaction_cost.py
               │
               ▼
          NET TRADING P&L
          ✅ [BE]  total_cost_pct + breakeven_move_pct
          ✅ [UI]  scorecard layout done in report.py Section 10
          ⚠️ [BE]  generate_report_data() wire-up pending

══════════════════════════════════════════════════════════════════════════════
  23  TAX ENGINE
══════════════════════════════════════════════════════════════════════════════

         NET TRADING P&L
               │
               ▼
         TAX CLASSIFIER
         ✅ [BE]  engine/tax.py
               │
    ┌──────────┼───────────┐
    ▼          ▼           ▼
  STCG       LTCG       BUSINESS
  ✅ [BE]    ✅ [BE]     n/a
               │
               ▼
         TAX ESTIMATE  ✅ [BE]  estimate_sale_tax_inr()
         LTCG countdown ✅ [BE]  ltcg_countdown_flags()
         Tax-loss harvest ✅ [BE]  tax_loss_harvest_candidates()
               │
               ▼
         AFTER-TAX RETURN
         ⚠️ [BE]  computed per sale; not shown standalone

══════════════════════════════════════════════════════════════════════════════
  24  NET ALPHA ENGINE
══════════════════════════════════════════════════════════════════════════════

         GROSS RETURN
               │  - Trading costs  (✅ built — not chained)
               │  - Slippage       (✅ built — not chained)
               │  - Taxes          (✅ built — not chained)
               ▼
          NET RETURN
          ⚠️ [BE]  engines built; chain not wired
               │
               ▼
         RISK ADJUSTMENT
         ❌  not built
               │
               ▼
         RISK-ADJUSTED RETURN / ALPHA
         ❌  not built

══════════════════════════════════════════════════════════════════════════════
  25  PORTFOLIO RISK ENGINE
══════════════════════════════════════════════════════════════════════════════

    Max Equity Exposure   ✅ [BE]  regime.py  max_equity_exposure
    Max Stock Exposure    ✅ [BE]  report.py  MAX_SINGLE_STOCK_PCT 5%
    Max Sector Exposure   ✅ [BE]  correlation.py  20% cap
    Max Correlation       ✅ [BE]  correlation.py
    ATR stop distance     ✅ [BE]  momentum.py
    Liquidity filter      ✅ [BE]  momentum.py  MIN_AVG_DAILY_TURNOVER
    Cash reserve          ✅ [BE]  allocation.py
    Current Dhan exposure ✅ [BE]  dhan/holdings.py
    Max drawdown tracking ❌  not built
               │
               ▼
         ALLOWED POSITION SIZE
         ✅ [BE]  momentum.py  position_size_inr
         ✅ [UI]  shown in report buy recommendations

══════════════════════════════════════════════════════════════════════════════
  26  POSITION SIZING
══════════════════════════════════════════════════════════════════════════════

    Risk per trade 0.75%  ✅ [BE]  RISK_PER_TRADE_PCT in momentum.py
    ATR stop → size       ✅ [BE]  momentum.py
    Sector/stock cap      ✅ [BE]  report.py  max_stock_capital
    Auto order gen        ❌ [MAN]  human places manually in Dhan

══════════════════════════════════════════════════════════════════════════════
  27 + 28  ORDER MANAGEMENT + EXECUTION  (Human Approval Gate)
══════════════════════════════════════════════════════════════════════════════

    ┌──────────────────────────────────────────────┐
    │  SUGGESTED ACTION (9-state vocabulary)        │
    │  ✅ [BE]  engine/decision.py                  │
    │     BUY_NOW · BUY_ON_PULLBACK                │
    │     WAIT_FOR_BREAKOUT · WAIT_FOR_NEWS        │
    │     WATCH · HOLD · REDUCE · EXIT · CASH      │
    └─────────────────┬────────────────────────────┘
                      ▼
             HUMAN READS REPORT
             ✅ [MAN]  intentional design
                      ▼
             HUMAN PLACES ORDER IN DHAN
             ✅ [MAN]  broker app
                      ▼
             AUTO-ORDER PLACEMENT
             ❌  will never be built  (HANDOFF.md rule)

══════════════════════════════════════════════════════════════════════════════
  29  REPORTING + DASHBOARD
══════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────┐
    │  DAILY TEXT REPORT                                   │
    │  ✅ [BE]  engine/report.py  (Sections 1–11)          │
    │  ✅ [BE]  auto-saved to  reports/YYYY-MM-DD.txt      │
    │                                                      │
    │  Section 1  — System Config + Capital                │
    │  Section 2  — Market Regime                          │
    │  Section 3  — Phase 2 Allocation (gold/liquid)       │
    │  Section 4  — Portfolio Drift + Actions              │
    │  Section 5  — Tax Status + LTCG Countdown           │
    │  Section 6  — Global Macro Snapshot                  │
    │  Section 7  — Sector Scores                          │
    │  Section 8  — Sector Exposure                        │
    │  Section 9  — Recommended Actions (max 3/day)        │
    │  Section 10 — Candidate Score-Cards  ⚠️ wire-up     │
    │               10-component breakdown                 │
    │               Expected Return block                  │
    │               Transaction Cost line                  │
    │  Section 11 — Data Quality + Pipeline Health         │
    └─────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────┐
    │  WEB DASHBOARD  (FastAPI + HTML/JS)                  │
    │  ✅ [UI]  web_server.py running locally              │
    │  ✅ [UI]  Regime banner + macro panel                 │
    │  ✅ [UI]  Portfolio holdings table                   │
    │  ✅ [UI]  Sector scores table                        │
    │  ✅ [UI]  Candidate cards                            │
    │  ⚠️ [UI]  New engines data not yet in API           │
    │  ❌ [UI]  R:R + Expected Return card  (pending)      │
    │  ❌ [UI]  Fundamental/Governance panel  (pending)    │
    └─────────────────────────────────────────────────────┘

══════════════════════════════════════════════════════════════════════════════
  30  PERFORMANCE TRACKING
══════════════════════════════════════════════════════════════════════════════

    Trade log           ❌  not built
    Realized P&L        ❌  not built
    Win rate / hit rate ❌  not built
    Drawdown tracking   ❌  not built
    Strategy review     ❌ [MAN]  manual only

══════════════════════════════════════════════════════════════════════════════
  NEXT STEPS  (Priority Order)
══════════════════════════════════════════════════════════════════════════════

    #1  ⚠️ [BE]  Wire Fundamental + Valuation + Governance + RS
                 into  generate_report_data()              ← ~1–2 hrs
    #2  ⚠️ [BE]  Wire Expected Return + Transaction Cost
                 into  generate_report_data()  return dict ← ~30 min
    #3  ⚠️ [BE]  Fix  report.py  KeyError — run end-to-end ← ~15 min
    #4  ❌ [BE]  Net Alpha: chain cost + tax → net return   ← ~1 hr
    #5  ❌ [UI]  Dashboard API for new engine outputs       ← ~2 hrs
    #6  ❌ [BE]  Performance tracking (trade log, drawdown) ← ~3 hrs
    #7  ❌ [BE]  Breakout / Mean Reversion engines          ← ~3 hrs
    #8  ❌ [INF] PostgreSQL / proper data store             ← large

══════════════════════════════════════════════════════════════════════════════
  SUMMARY COUNTS
══════════════════════════════════════════════════════════════════════════════

    ✅  Done & working     ~75 sub-modules across 21 files
    ⚠️  Partial/pending   ~15 sub-modules (wire-up mostly)
    ❌  Not built          ~20 sub-modules

    [BE] Backend files:   engine/ (11 engines) + data/ (10 modules)
    [UI] Dashboard:       web_server.py + web/  (partial)
    [INF] Storage:        flat CSV/JSON only  (no DB yet)
    [MAN] Manual steps:   Claude research + order placement

    ══ ALL 10 COMPOSITE SCORE COMPONENTS CODED ══
    ══ Pipeline wire-up is the immediate bottleneck ══
```
