"""
Daily report generator - Daily AI Investment Command Center.
Combines regime + multi-factor regime scoring + Phase 2 allocation + portfolio drift
reconciliation + global macro narrative prompt + normalized sector scores + money flow QoQ
deltas + auto-saved research prompts + candidate decision engine + data quality pipeline health.
Recommendation-only: this produces text for the user to read and act on manually in their own broker app.
Nothing here places any order.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.regime import classify_regime, RegimeResult
from engine.momentum import evaluate_universe, Candidate
from engine.news import scan_for_price_volume_events, build_news_prompt
from engine.allocation import build_phase2_allocation, compute_portfolio_drift, classify_holding_sleeve
from engine.tax import (
    classify_holding, estimate_sale_tax_inr, round_trip_cost_inr,
    ltcg_countdown_flags, tax_loss_harvest_candidates,
)
from data.corporate_actions import upcoming_events_for_universe
from engine.correlation import compute_sector_exposure, concentration_flags, check_new_position, get_sector
from engine.manual_checks import get_manual_check_reminders
from data.global_macro import fetch_all_macro
from engine.priced_in import assess_priced_in, PricedInResult
from engine.sector_score import compute_sector_scores
from engine.money_flow import compute_money_flow_score, MoneyFlowScore
from data.institutional.insider import insider_trades_for_universe
from data.institutional.bulk_block import bulk_block_deals_for_universe
from data.institutional.pledge import pledge_status_for_symbols
from data.institutional.shareholding import shareholding_for_symbols
from engine.decision import evaluate_decision, DecisionResult

MAX_SINGLE_STOCK_PCT = 0.05
MAX_DAILY_ACTIONS = 3
TOP_N_DISPLAY = 500

PORTFOLIO_PATH = Path(__file__).resolve().parent.parent / "config" / "portfolio.json"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def load_portfolio() -> dict:
    with open(PORTFOLIO_PATH) as f:
        return json.load(f)


def save_event_prompt(e: dict, pin: PricedInResult) -> Path:
    from engine.prompt_engine import build_event_prompt, load_system_prompt
    
    event_prompt = build_event_prompt([e], [pin])
    system_prompt = load_system_prompt()
    full_prompt = f"{system_prompt}\n\n{event_prompt}"
    
    research_dir = Path(__file__).resolve().parent.parent / "reports" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    bare = e["symbol"].replace(".NS", "").upper()
    path = research_dir / f"{date_str}_{bare}.md"
    path.write_text(full_prompt)
    return path


def save_market_prompt(macro: dict, regime: RegimeResult) -> Path:
    from engine.prompt_engine import build_market_research_prompt, load_system_prompt
    
    market_prompt = build_market_research_prompt(macro, regime)
    system_prompt = load_system_prompt()
    full_prompt = f"{system_prompt}\n\n{market_prompt}"
    
    research_dir = Path(__file__).resolve().parent.parent / "reports" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = research_dir / f"{date_str}_market_narrative.md"
    path.write_text(full_prompt)
    return path


def generate_report_data(save_prompts: bool = False) -> dict:
    """Runs all backend data collection, scoring, and classification.
    Returns a JSON-serializable dictionary containing the full state."""
    data_health = {
        "yfinance (Nifty/VIX)": "SUCCESS",
        "yfinance (Equities EOD)": "SUCCESS",
        "AMFI (mutual fund NAVs)": "SUCCESS",
        "Corporate actions API": "SUCCESS",
        "Insider disclosures API": "SUCCESS",
        "Bulk/block deals API": "SUCCESS",
        "Pledges/XBRL": "SUCCESS",
        "Shareholdings/XBRL": "SUCCESS",
    }

    portfolio = load_portfolio()
    dhan_active = False
    try:
        from data.dhan.client import DhanClient
        from data.dhan.holdings import get_holdings, get_available_balance
        dhan_client = DhanClient()
        if dhan_client.is_active():
            live_holdings = get_holdings(dhan_client)
            if live_holdings is not None:
                portfolio["holdings"] = live_holdings
                dhan_active = True
                
            live_cash = get_available_balance(dhan_client)
            if live_cash is not None:
                portfolio["cash_inr"] = live_cash
                
            if live_holdings is not None and live_cash is not None:
                portfolio["capital_inr"] = sum(h["value_inr"] for h in live_holdings) + live_cash
    except Exception as exc:
        data_health["Dhan API (Live portfolio)"] = f"FAILED: {exc}"
        dhan_active = False

    if dhan_active:
        data_health["Dhan API (Live portfolio)"] = "SUCCESS"
    else:
        data_health["Dhan API (Live portfolio)"] = "INACTIVE (fallback to portfolio.json)"

    capital = portfolio["capital_inr"]
    held_symbols = {h["symbol"] for h in portfolio["holdings"]}

    # 1. Fetch macro context
    try:
        macro = fetch_all_macro()
    except Exception as exc:
        macro = {}
        data_health["yfinance (Nifty/VIX)"] = f"FAILED macro fetch: {exc}"

    # 2. Evaluate Candidate Universe
    try:
        ranked = evaluate_universe(capital)
        from config.universe import EQUITY_UNIVERSE
        loaded_count = 0
        cache_dir = Path(__file__).resolve().parent.parent / "data" / "cache"
        for s in EQUITY_UNIVERSE:
            p = cache_dir / f"{s.replace('.', '_').replace('^', '')}.csv"
            if p.exists() and p.stat().st_size > 0:
                loaded_count += 1
        if loaded_count == 0:
            data_health["yfinance (Equities EOD)"] = "FAILED (no cached data found)"
        elif loaded_count < len(EQUITY_UNIVERSE) * 0.9:
            data_health["yfinance (Equities EOD)"] = f"PARTIAL SUCCESS ({loaded_count}/{len(EQUITY_UNIVERSE)} files cached)"
    except Exception as exc:
        ranked = []
        data_health["yfinance (Equities EOD)"] = f"FAILED candidate eval: {exc}"

    # 3. Classify Regime (Multi-Factor)
    try:
        regime = classify_regime(ranked_candidates=ranked, macro=macro, portfolio=portfolio)
    except Exception as exc:
        nifty_df = cache_dir / "nifty.csv"
        vix_df = cache_dir / "vix.csv"
        nifty_close = 0.0
        if nifty_df.exists() and vix_df.exists():
            import pandas as pd
            ndf = pd.read_csv(nifty_df, index_col=0, parse_dates=True)
            vdf = pd.read_csv(vix_df, index_col=0, parse_dates=True)
            nifty_close = float(ndf["Close"].iloc[-1])
            vix_level = float(vdf["Close"].iloc[-1])
        regime = RegimeResult(
            regime="UNKNOWN", nifty_close=nifty_close, nifty_200dma=0.0, nifty_above_dma_pct=0.0,
            vix=vix_level if nifty_df.exists() else 15.0, max_equity_exposure=0.25, notes=f"Regime calculation error: {exc}",
            trend_score=50.0, volatility_score=50.0, breadth_score=50.0, institutional_score=50.0,
            global_score=50.0, liquidity_score=50.0, regime_score=50.0
        )
        data_health["yfinance (Nifty/VIX)"] = f"FAILED details: {exc}"

    # 4. Build phase 2 target allocations
    try:
        alloc = build_phase2_allocation(capital)
    except Exception as exc:
        alloc = None
        data_health["AMFI (mutual fund NAVs)"] = f"FAILED: {exc}"

    # Calculate portfolio drift
    drift_table = {}
    if alloc:
        drift_table = compute_portfolio_drift(portfolio, alloc)

    max_stock_capital = capital * MAX_SINGLE_STOCK_PCT
    equity_budget = capital * regime.max_equity_exposure

    # Tax classifications
    tax_statuses = []
    tax_status_by_symbol = {}
    for h in portfolio["holdings"]:
        match = next((c for c in ranked if c.symbol == h["symbol"]), None)
        if "buy_date" in h and "buy_price" in h and "quantity" in h:
            current_price = match.close if match else h["buy_price"]
            tax_stat = classify_holding(h, current_price)
            tax_statuses.append(tax_stat)
            tax_status_by_symbol[h["symbol"]] = tax_stat

    # Sector Scores
    top_symbol_set = {c.symbol for c in ranked[:TOP_N_DISPLAY]} | held_symbols
    try:
        sector_scores = compute_sector_scores(symbols=list(top_symbol_set), macro=macro)
    except Exception as exc:
        sector_scores = []
        data_health["yfinance (Equities EOD)"] = f"PARTIAL SUCCESS (sector calc fail: {exc})"

    sector_score_by_sector = {s.sector: s.overall_score for s in sector_scores}

    # Money Flow Details
    money_flow_symbols = sorted(top_symbol_set)
    bare_symbols = [s.replace(".NS", "").upper() for s in money_flow_symbols]
    
    try:
        all_insider = insider_trades_for_universe(money_flow_symbols, lookback_days=90)
    except Exception as exc:
        all_insider = None
        data_health["Insider disclosures API"] = f"FAILED: {exc}"
        
    try:
        all_bulk_block = bulk_block_deals_for_universe(money_flow_symbols)
    except Exception as exc:
        all_bulk_block = None
        data_health["Bulk/block deals API"] = f"FAILED: {exc}"
        
    try:
        pledges_list = pledge_status_for_symbols(bare_symbols)
        pledges = {p.symbol: p for p in pledges_list}
    except Exception as exc:
        pledges = {}
        data_health["Pledges/XBRL"] = f"FAILED: {exc}"
        
    try:
        ownerships_list = shareholding_for_symbols(bare_symbols)
        ownerships = {o.symbol: o for o in ownerships_list}
    except Exception as exc:
        ownerships = {}
        data_health["Shareholdings/XBRL"] = f"FAILED: {exc}"

    money_flow_by_symbol = {}
    for sym in money_flow_symbols:
        bare = sym.replace(".NS", "").upper()
        sym_insider = [t for t in all_insider if t.symbol == bare] if all_insider is not None else None
        sym_bulk_block = [d for d in all_bulk_block if d.symbol == bare] if all_bulk_block is not None else None
        
        mf = compute_money_flow_score(bare, sym_insider, sym_bulk_block,
                                       pledges.get(bare), ownerships.get(bare))
        money_flow_by_symbol[sym] = mf

    # Catalyst Events
    news_events = scan_for_price_volume_events([c.symbol for c in ranked])
    news_by_symbol = {e["symbol"]: e for e in news_events}
    priced_in_by_symbol = {}
    relevant_news = [e for sym, e in news_by_symbol.items() if sym in top_symbol_set]
    
    saved_prompts_paths = {}

    for e in relevant_news:
        r = assess_priced_in(e["symbol"], e["move_pct"], e["direction"])
        priced_in_by_symbol[e["symbol"]] = r
        if save_prompts:
            try:
                saved_p = save_event_prompt(e, r)
                saved_prompts_paths[e["symbol"]] = str(saved_p)
            except Exception:
                pass

    if save_prompts:
        try:
            saved_m = save_market_prompt(macro, regime)
            saved_prompts_paths["market_narrative"] = str(saved_m)
        except Exception:
            pass

    # Sector Concentration
    sector_exposure = []
    if portfolio["holdings"]:
        sector_exposure = compute_sector_exposure(portfolio["holdings"], capital)

    # Corporate Actions
    try:
        actions_cal, meetings_cal = upcoming_events_for_universe(list(top_symbol_set))
        event_symbols = {a.symbol for a in actions_cal} | {m.symbol for m in meetings_cal}
    except Exception as exc:
        event_symbols = set()
        data_health["Corporate actions API"] = f"FAILED: {exc}"

    # Evaluate decisions
    decisions = {}
    
    # Candidates
    for idx, c in enumerate(ranked[:TOP_N_DISPLAY]):
        rank = idx + 1
        momentum_pct = 1.0 - (rank - 1) / max(len(ranked) - 1, 1)
        
        sect = get_sector(c.symbol)
        sect_overall = sector_score_by_sector.get(sect)
        
        mf = money_flow_by_symbol.get(c.symbol)
        mf_total = mf.total_score if mf else 0.0
        
        news_flagged = c.symbol in news_by_symbol
        pin = priced_in_by_symbol.get(c.symbol)
        pin_status = pin.status if pin else None
        
        bare = c.symbol.replace(".NS", "").upper()
        pledge = pledges.get(bare)
        pledged_pct = pledge.pledged_pct if pledge else 0.0
        
        has_upcoming_event = c.symbol in event_symbols
        
        size = min(c.position_size_inr, max_stock_capital)
        other_holdings = [h for h in portfolio["holdings"] if h["symbol"] != c.symbol]
        sector_stacking_risk = check_new_position(c.symbol, size, other_holdings, capital) is not None
        
        dec = evaluate_decision(
            symbol=c.symbol,
            rank=rank,
            total_candidates=len(ranked),
            momentum_pct=momentum_pct,
            sector_overall_score=sect_overall,
            money_flow_total=mf_total,
            news_flagged=news_flagged,
            priced_in_status=pin_status,
            stop_distance_pct=c.stop_distance_pct,
            pledged_pct=pledged_pct,
            has_upcoming_event=has_upcoming_event,
            sector_stacking_risk=sector_stacking_risk,
            is_held=(c.symbol in held_symbols),
            regime_state=regime.regime
        )
        decisions[c.symbol] = dec

    # Held positions not in top candidates
    for h in portfolio["holdings"]:
        sym = h["symbol"]
        if sym in decisions:
            continue
            
        match = next((c for c in ranked if c.symbol == sym), None)
        rank = ranked.index(match) + 1 if match else None
        momentum_pct = 1.0 - (rank - 1) / max(len(ranked) - 1, 1) if rank else 0.0
        
        sect = get_sector(sym)
        sect_overall = sector_score_by_sector.get(sect)
        
        mf = money_flow_by_symbol.get(sym)
        mf_total = mf.total_score if mf else 0.0
        
        news_flagged = sym in news_by_symbol
        pin = priced_in_by_symbol.get(sym)
        pin_status = pin.status if pin else None
        
        bare = sym.replace(".NS", "").upper()
        pledge = pledges.get(bare)
        pledged_pct = pledge.pledged_pct if pledge else 0.0
        
        has_upcoming_event = sym in event_symbols
        sector_stacking_risk = False
        
        dec = evaluate_decision(
            symbol=sym,
            rank=rank,
            total_candidates=len(ranked),
            momentum_pct=momentum_pct,
            sector_overall_score=sect_overall,
            money_flow_total=mf_total,
            news_flagged=news_flagged,
            priced_in_status=pin_status,
            stop_distance_pct=match.stop_distance_pct if match else 0.0,
            pledged_pct=pledged_pct,
            has_upcoming_event=has_upcoming_event,
            sector_stacking_risk=sector_stacking_risk,
            is_held=True,
            regime_state=regime.regime
        )
        decisions[sym] = dec

    # Suggested Actions
    suggested_sells = []
    for h in portfolio["holdings"]:
        dec = decisions.get(h["symbol"])
        if dec and dec.suggested_action in ("EXIT", "REDUCE"):
            tstat = tax_status_by_symbol.get(h["symbol"])
            tax_note = ""
            if tstat is not None:
                hurdle = estimate_sale_tax_inr(tstat) + round_trip_cost_inr(h["value_inr"])
                tax_note = f" (est. tax+cost: ₹{hurdle/1e5:.2f}L)"
            suggested_sells.append(
                f"{dec.suggested_action} {h['symbol']} — rationale: {', '.join(dec.concerns) if dec.concerns else 'thesis change'}{tax_note}"
            )
            
    suggested_buys = []
    new_candidates = [c for c in ranked[:8] if c.symbol not in held_symbols]
    for c in new_candidates:
        dec = decisions.get(c.symbol)
        if dec and dec.suggested_action in ("BUY_NOW", "BUY_ON_PULLBACK", "WAIT_FOR_NEWS_CONFIRMATION", "WAIT_FOR_BREAKOUT"):
            size = min(c.position_size_inr, max_stock_capital)
            size_str = f"₹{size/1e5:.2f}L"
            
            if dec.suggested_action == "BUY_NOW":
                action_str = f"BUY_NOW {c.symbol} {size_str} — stop ₹{c.stop_price:.1f} (ATR-dist: {c.stop_distance_pct:.1%})"
            elif dec.suggested_action == "BUY_ON_PULLBACK":
                action_str = f"BUY_ON_PULLBACK {c.symbol} {size_str} — stop ₹{c.stop_price:.1f} (ATR-dist: {c.stop_distance_pct:.1%}) — wait for pullback/re-entry"
            elif dec.suggested_action == "WAIT_FOR_NEWS_CONFIRMATION":
                action_str = f"WAIT_FOR_NEWS_CONFIRMATION on {c.symbol} — unresearched catalyst flagged, review reports/research/ file first"
            elif dec.suggested_action == "WAIT_FOR_BREAKOUT":
                action_str = f"WAIT_FOR_BREAKOUT on {c.symbol} — consolidating near resistance, enter on breakout"
                
            if dec.concerns:
                action_str += f" (concerns: {', '.join(dec.concerns)})"
            suggested_buys.append(action_str)

    all_actions = suggested_sells + suggested_buys

    # Format return dictionary (make it JSON serializable)
    return {
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M'),
        "data_health": data_health,
        "dhan_active": dhan_active,
        "portfolio": portfolio,
        "capital": capital,
        "regime": asdict(regime),
        "drift_table": drift_table,
        "tax_statuses": [
            {
                "symbol": t.symbol,
                "is_ltcg": t.is_ltcg,
                "days_held": t.days_held,
                "unrealized_gain_inr": t.unrealized_gain_inr,
                "unrealized_gain_pct": t.unrealized_gain_pct,
            }
            for t in tax_statuses
        ],
        "countdown_flags": [
            {"symbol": c.symbol, "days_to_ltcg": c.days_to_ltcg}
            for c in ltcg_countdown_flags(tax_statuses)
        ],
        "harvest_candidates": [
            {"symbol": h.symbol, "unrealized_gain_inr": h.unrealized_gain_inr}
            for h in tax_loss_harvest_candidates(tax_statuses)
        ],
        "macro": {
            k: [
                {"name": q.name, "ticker": q.ticker, "last": q.last, "change_pct": q.change_pct}
                for q in quotes
            ]
            for k, quotes in macro.items()
        },
        "saved_prompts_paths": saved_prompts_paths,
        "sector_scores": [
            {
                "sector": s.sector,
                "overall_score": s.overall_score,
                "rs_vs_nifty": s.rs_vs_nifty,
                "breadth_above_20dma": s.breadth_above_20dma,
                "breadth_above_50dma": s.breadth_above_50dma,
                "commodity_impact": s.commodity_impact,
            }
            for s in sector_scores
        ],
        "money_flow": {
            sym: {
                "total_score": mf.total_score,
                "insider_score": mf.insider_score,
                "bulk_block_score": mf.bulk_block_score,
                "pledge_score": mf.pledge_score,
                "ownership_score": mf.ownership_score,
                "notes": mf.notes,
            }
            for sym, mf in money_flow_by_symbol.items()
        },
        "news_events": [
            {
                "symbol": e["symbol"],
                "move_pct": e["move_pct"],
                "volume_multiple": e["volume_multiple"],
                "direction": e["direction"],
                "priced_in_status": priced_in_by_symbol.get(e["symbol"]).status if e["symbol"] in priced_in_by_symbol else "UNKNOWN"
            }
            for e in relevant_news
        ],
        "sector_exposure": [
            {
                "sector": e.sector,
                "pct_of_capital": e.pct_of_capital,
                "total_inr": e.total_inr,
                "symbols": e.symbols,
            }
            for e in sector_exposure
        ],
        "decisions": {sym: asdict(dec) for sym, dec in decisions.items()},
        "suggested_actions": all_actions,
        "ranked_candidates": [
            {
                "symbol": c.symbol,
                "close": float(c.close),
                "stop_price": float(c.stop_price),
                "stop_distance_pct": float(c.stop_distance_pct),
                "position_size_inr": float(c.position_size_inr),
                "ret_3m": float(c.ret_3m),
                "ret_6m": float(c.ret_6m),
                "sector": get_sector(c.symbol)
            }
            for c in ranked[:TOP_N_DISPLAY]
        ]
    }


def build_report() -> str:
    data = generate_report_data(save_prompts=True)
    capital = data["capital"]
    regime = data["regime"]
    portfolio = data["portfolio"]
    drift_table = data["drift_table"]
    
    lines = []
    lines.append("=" * 80)
    lines.append(f"DAILY AI INVESTMENT COMMAND CENTER — {data['timestamp']} IST")
    lines.append("Recommendation only. Review and place trades yourself.")
    lines.append("=" * 80)

    # Section 2: Market Regime & Exposure Cap
    equity_budget = capital * regime["max_equity_exposure"]
    lines.append("\n-- SECTION 2: MARKET REGIME & EXPOSURE CAP --")
    lines.append(f"Regime State:        {regime['regime']}")
    lines.append(f"Nifty Close:         {regime['nifty_close']:,.2f} (vs 200-DMA: {regime['nifty_200dma']:,.2f}, {regime['nifty_above_dma_pct']:+.2f}%)")
    lines.append(f"India VIX:           {regime['vix']:.2f} (Volatility: {'High Stress' if regime['vix'] >= 20 else 'Calm'})")
    lines.append(f"Max Equity Exposure: {regime['max_equity_exposure']:.0%} (₹{equity_budget/1e5:.2f}L of ₹{capital/1e5:.2f}L capital)")
    lines.append(f"Regime Notes:        {regime['notes']}")
    lines.append("\nMULTI-FACTOR REGIME SCORES (0-100):")
    lines.append(f"  Trend score:          {regime['trend_score']}")
    lines.append(f"  Volatility score:     {regime['volatility_score']}")
    lines.append(f"  Breadth score:        {regime['breadth_score']}")
    lines.append(f"  Institutional score:  {regime['institutional_score']}")
    lines.append(f"  Global score:         {regime['global_score']}")
    lines.append(f"  Liquidity score:      {regime['liquidity_score']}")
    lines.append(f"  Composite score:      {regime['regime_score']}")

    # Section 3: Portfolio Allocation Summary
    lines.append("\n-- SECTION 3: PORTFOLIO ALLOCATION SUMMARY --")
    lines.append(f"Capital: ₹{capital/1e5:.2f}L | Cash: ₹{portfolio.get('cash_inr', 0.0)/1e5:.2f}L")
    if drift_table:
        lines.append(f"{'Sleeve':<30}{'Target %':>10}{'Target Val':>14}{'Actual %':>10}{'Actual Val':>14}{'Drift %':>10}{'Drift Val':>14}")
        for sleeve, val in drift_table.items():
            lines.append(
                f"  {sleeve:<28}"
                f"{val['target_pct']:>9.1%}"
                f"₹{val['target_inr']/1e5:>12.2f}L"
                f"{val['actual_pct']:>9.1%}"
                f"₹{val['actual_inr']/1e5:>12.2f}L"
                f"{val['drift_pct']:>+9.1%}"
                f"₹{val['drift_inr']/1e5:>+12.2f}L"
            )
        lines.append("-" * 106)
        total_target_pct = sum(v["target_pct"] for v in drift_table.values())
        total_target_val = sum(v["target_inr"] for v in drift_table.values())
        total_actual_pct = sum(v["actual_pct"] for v in drift_table.values())
        total_actual_val = sum(v["actual_inr"] for v in drift_table.values())
        total_drift_pct = total_actual_pct - total_target_pct
        total_drift_val = total_actual_val - total_target_val
        lines.append(
            f"  {'Total':<28}"
            f"{total_target_pct:>9.1%}"
            f"₹{total_target_val/1e5:>12.2f}L"
            f"{total_actual_pct:>9.1%}"
            f"₹{total_actual_val/1e5:>12.2f}L"
            f"{total_drift_pct:>+9.1%}"
            f"₹{total_drift_val/1e5:>+12.2f}L"
        )
    else:
        lines.append("  (Portfolio target/drift calculations unavailable)")

    # Section 4: Current Holdings Detailed Reconciliation
    lines.append("\n-- SECTION 4: CURRENT HOLDINGS DETAILED RECONCILIATION --")
    if not portfolio["holdings"]:
        lines.append("  (none — fully in cash)")
    else:
        max_stock_capital = capital * MAX_SINGLE_STOCK_PCT
        for h in portfolio["holdings"]:
            # find match in candidate list
            match = next((c for c in data["ranked_candidates"] if c["symbol"] == h["symbol"]), None)
            rank = data["ranked_candidates"].index(match) + 1 if match else None
            status = f"rank #{rank}" if rank else "dropped out of ranked universe"
            
            sleeve_name = h.get("sleeve") or classify_holding_sleeve(h["symbol"])
            target_val = 0.0
            if drift_table and sleeve_name in drift_table:
                if sleeve_name == "Core momentum equity":
                    target_val = min(match["position_size_inr"], max_stock_capital) if match else max_stock_capital
                else:
                    target_val = drift_table[sleeve_name]["target_inr"]
            drift_val = h["value_inr"] - target_val

            lines.append(
                f"  {h['symbol']:<16} Value: ₹{h['value_inr']/1e5:.2f}L | "
                f"Sleeve: {sleeve_name:<26} | "
                f"Status: {status} | "
                f"Drift: ₹{drift_val/1e5:+.2f}L"
            )

    if data["tax_statuses"]:
        lines.append("\n-- TAX STATUS & HARVESTING (est. only -- confirm with CA) --")
        ltcg_exemption_used = 0.0
        for s in data["tax_statuses"]:
            # estimate tax
            # Reconstruct TaxStatus to call tax helpers
            class MockTaxStatus:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
            mts = MockTaxStatus(
                symbol=s["symbol"], is_ltcg=s["is_ltcg"], days_held=s["days_held"],
                unrealized_gain_inr=s["unrealized_gain_inr"], unrealized_gain_pct=s["unrealized_gain_pct"]
            )
            tax = estimate_sale_tax_inr(mts, ltcg_exemption_used)
            if mts.is_ltcg and mts.unrealized_gain_inr > 0:
                ltcg_exemption_used += mts.unrealized_gain_inr
            lines.append(
                f"  {mts.symbol:<16} {'LTCG' if mts.is_ltcg else 'STCG':<5} "
                f"held {mts.days_held:>4}d  gain ₹{mts.unrealized_gain_inr/1e5:>+6.2f}L "
                f"({mts.unrealized_gain_pct:+.1f}%)  est. tax if sold today ₹{tax/1e5:.2f}L"
            )
        if data["countdown_flags"]:
            lines.append("  STCG->LTCG countdown flags:")
            for s in data["countdown_flags"]:
                lines.append(f"    {s['symbol']} — {s['days_to_ltcg']} day(s) to LTCG (consider holding for lower tax rate)")
        if data["harvest_candidates"]:
            lines.append("  Tax-loss harvesting candidates (realized loss offset opportunity):")
            for s in data["harvest_candidates"]:
                lines.append(f"    {s['symbol']} — unrealized loss ₹{s['unrealized_gain_inr']/1e5:.2f}L")

    # Section 5: Global Macro Narrative Prompt
    lines.append("\n-- SECTION 5: GLOBAL MACRO CROSS-ASSET NARRATIVE PROMPT --")
    macro_labels = {
        "forex": "Forex", "commodities": "Commodities", "global_rates": "Global rates",
        "global_equity": "Global equity", "crypto": "Crypto (buy-and-hold sleeve)",
        "nifty_sectors": "Nifty sector indices",
    }
    for key, label in macro_labels.items():
        quotes = data["macro"].get(key, [])
        if not quotes:
            continue
        row = "  ".join(f"{q['name']} {q['last']:,.2f} ({q['change_pct']:+.2f}%)" for q in quotes)
        lines.append(f"  {label:<24} {row}")

    saved_m = data["saved_prompts_paths"].get("market_narrative")
    if saved_m:
        lines.append(f"\n  [saved prompt] Cross-asset market narrative prompt saved to:")
        lines.append(f"                 [market_narrative.md](file://{saved_m})")
        lines.append("                 Run this file in Claude to generate the daily cross-asset narrative.")

    # Section 6: Sector Strength & Commodity Tilt
    lines.append("\n-- SECTION 6: SECTOR STRENGTH & COMMODITY TILT --")
    if not data["sector_scores"]:
        lines.append("  Not enough sector data among today's top candidates/holdings.")
    else:
        for s in data["sector_scores"]:
            lines.append(
                f"  {s['sector']:<24} score {s['overall_score']:>5.1f}/100  "
                f"RS {s['rs_vs_nifty']:>+6.2f}%  >20DMA {s['breadth_above_20dma']:>5.1f}%  "
                f">50DMA {s['breadth_above_50dma']:>5.1f}%  commodity {s['commodity_impact']}"
            )

    # Section 7: Money Flow & Institutional Activity
    lines.append("\n-- SECTION 7: MONEY FLOW & INSTITUTIONAL ACTIVITY --")
    any_money_flow = False
    for sym, mf in data["money_flow"].items():
        if mf["total_score"] == 0 and not mf["notes"]:
            continue
        any_money_flow = True
        lines.append(f"  {sym:<16} total {mf['total_score']:>+5.1f}/20  "
                      f"(insider {mf['insider_score']:>+4.1f}/8, bulk/block {mf['bulk_block_score']:>+4.1f}/4, "
                      f"pledge {mf['pledge_score']:>+4.1f}/4, ownership {mf['ownership_score']:>+4.1f}/4)")
        for n in mf["notes"]:
            lines.append(f"      - {n}")
    if not any_money_flow:
        lines.append("  No promoter/institutional money flow activity among today's top candidates/holdings.")

    # Section 8: News Events & Catalyst Research Prompts
    lines.append("\n-- SECTION 8: NEWS EVENTS & CATALYST RESEARCH PROMPTS --")
    if not data["news_events"]:
        lines.append("  No price+volume event confirmed moves (>=3% move, >=1.5x volume) today.")
    else:
        for e in data["news_events"]:
            lines.append(
                f"  {e['symbol']:<16} move {e['move_pct']:+6.1f}%  vol {e['volume_multiple']:.1f}x  "
                f"({e['direction']}) -- UNRESEARCHED catalyst, priced-in status: {e['priced_in_status']}"
            )
            saved_p = data["saved_prompts_paths"].get(e["symbol"])
            if saved_p:
                lines.append(f"                   [research prompt saved to] [research_{e['symbol'].replace('.NS','')}.md](file://{saved_p})")

    # Sector Concentration
    lines.append("\n-- SECTOR CONCENTRATION (holdings, hard cap 20%/sector) --")
    if not data["sector_exposure"]:
        lines.append("  (no holdings)")
    else:
        for e in data["sector_exposure"]:
            over_flag = " -- OVER CAP" if e["pct_of_capital"] > 0.20 else ""
            lines.append(f"  {e['sector']:<22} {e['pct_of_capital']:>6.1%}  ₹{e['total_inr']/1e5:.1f}L  "
                          f"{', '.join(e['symbols'])}{over_flag}")
        # check overcap concentration
        has_overcap = any(e["pct_of_capital"] > 0.20 for e in data["sector_exposure"])
        if not has_overcap:
            lines.append("  No sector over the 20% cap.")

    # Section 9: Decision Engine Recommendations
    lines.append("\n-- SECTION 9: DECISION ENGINE RECOMMENDATIONS (max 3 actions/day) --")
    if not data["suggested_actions"]:
        lines.append("  No action recommended today — all holdings remain ranked and thesis intact.")
    else:
        for a in data["suggested_actions"][:MAX_DAILY_ACTIONS]:
            lines.append(f"  * {a}")
        if len(data["suggested_actions"]) > MAX_DAILY_ACTIONS:
            lines.append(f"  ({len(data['suggested_actions']) - MAX_DAILY_ACTIONS} more candidate(s) logged for next review, exceeds {MAX_DAILY_ACTIONS}/day cap)")

    # Section 10: Candidate Score-Cards
    lines.append("\n-- SECTION 10: CANDIDATE SCORE-CARDS (top candidates composite breakdown) --")
    for c in data["ranked_candidates"]:
        dec = data["decisions"].get(c["symbol"])
        if not dec:
            continue
        rank = data["ranked_candidates"].index(c) + 1
        normalized_momentum = (1.0 - (rank - 1) / max(len(data["ranked_candidates"]) - 1, 1)) * 100.0

        sect_overall = next((s["overall_score"] for s in data["sector_scores"] if s["sector"] == c["sector"]), None)
        sect_note = f"{c['sector']} {sect_overall:.1f}/100" if sect_overall is not None else f"{c['sector']} (no score)"

        mf = data["money_flow"].get(c["symbol"])
        mf_notes = ", ".join(mf["notes"]) if mf and mf["notes"] else "no signal"

        concerns_str = ", ".join(dec["concerns"]) if dec["concerns"] else "none"
        missing_str = ", ".join(dec.get("missing_components", [])) or "none"

        lines.append("  " + "━" * 50)
        lines.append(f"  {c['symbol']:<16} (rank #{rank:<2})   ACTION: {dec['suggested_action']}")
        lines.append(f"  Composite Score: {dec['overall_score']:>+5.1f}/100")
        lines.append("  " + "━" * 50)
        lines.append(f"  {'Component':<20} {'Score':>8}   {'Max':>5}   Notes")
        lines.append(f"  {'-'*62}")
        lines.append(f"  {'Market Regime':<20} {dec['regime_component']:>8.1f}   {10:>5}")
        lines.append(f"  {'Sector':<20} {dec['sector_component']:>8.1f}   {10:>5}   {sect_note}")
        lines.append(f"  {'Catalyst':<20} {dec['catalyst_component']:>8.1f}   {15:>5}")
        lines.append(f"  {'FII/DII/MF Flow':<20} {dec['fii_dii_component']:>8.1f}   {15:>5}   {mf_notes[:35]}")
        lines.append(f"  {'Insider/Block':<20} {dec['insider_component']:>8.1f}   {10:>5}")
        lines.append(f"  {'Technical/RS':<20} {dec['technical_component']:>8.1f}   {15:>5}   momentum pct {normalized_momentum:.0f}/100, 3M {c['ret_3m']*100:+.1f}% 6M {c['ret_6m']*100:+.1f}%")
        lines.append(f"  {'Fundamental':<20} {dec['fundamental_component']:>8.1f}   {10:>5}")
        lines.append(f"  {'Cash Flow':<20} {dec['cashflow_component']:>8.1f}   {5:>5}")
        lines.append(f"  {'Governance':<20} {dec['governance_component']:>8.1f}   {5:>5}")
        lines.append(f"  {'Valuation':<20} {dec['valuation_component']:>8.1f}   {5:>5}")
        lines.append(f"  {'-'*62}")
        lines.append(f"  {'TOTAL':<20} {dec['overall_score']:>8.1f}   {100:>5}")
        if dec.get("concerns"):
            lines.append(f"  ⚠  Concerns:  {concerns_str}")
        if dec.get("missing_components"):
            lines.append(f"  ℹ  Missing data: {missing_str}")
        # Expected Return block
        er = data.get("expected_returns", {}).get(c["symbol"])
        if er:
            lines.append(f"  ── Expected Return ────────────────────────────")
            lines.append(f"  Entry Zone: ₹{er['entry_low']:.0f} – ₹{er['entry_high']:.0f}  │  Stop: ₹{er['stop_price']:.0f}  │  Target: ₹{er['target_price']:.0f} ({er['target_method']})")
            lines.append(f"  Upside:     {er['expected_upside_pct']:+.1f}%  │  Loss: {er['expected_loss_pct']:.1f}%  │  R:R 1:{er['risk_reward']:.2f}  │  P(success) {er['probability_estimate']*100:.0f}%  │  EV {er['expected_value_pct']:+.2f}%")
        tc = data.get("transaction_costs", {}).get(c["symbol"])
        if tc:
            lines.append(f"  Round-trip cost: ₹{tc['total_cost_inr']:.0f} ({tc['total_cost_pct']:.3f}% of position)  ·  Breakeven move: {tc['breakeven_move_pct']:.3f}%")
        lines.append("")
    # Section 11: Data Quality & Pipeline Health Footer
    lines.append("\n-- SECTION 11: DATA QUALITY & PIPELINE HEALTH FOOTER --")
    lines.append(f"{'Data Source':<30}{'Status'}")
    lines.append(f"{'-' * 45}")
    for source, status in data["data_health"].items():
        lines.append(f"{source:<30}{status}")

    lines.append("\n" + "=" * 80)
    lines.append("Reminder: Phase 1 (equity momentum) + Phase 2 (gold/silver ETF,")
    lines.append("liquid/arbitrage parking, index fund equity slice) are both live.")
    lines.append("Verify current prices in your broker app before acting; data here is EOD close.")
    lines.append("=" * 80)

    return "\n".join(lines)


def save_report(report: str) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt"
    path.write_text(report)
    return path


if __name__ == "__main__":
    report = build_report()
    print(report)
    saved_path = save_report(report)
    print(f"\n[saved to {saved_path}]")
