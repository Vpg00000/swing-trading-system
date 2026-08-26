"""
Prompt engine -- loads the .md templates in this directory and fills them
with runtime data from the deterministic (Python) layer, per ROADMAP.md's
Layer 2 (Claude Research) design. Every build_*_prompt() function here
produces a plain string prompt; nothing in this module calls Claude or any
other model itself -- that's the caller's job (e.g. server/main.py, or a
manual WebFetch/Task-tool research pass), matching the existing pattern in
engine/news.py's build_news_prompt().

Every template expects the model's reply to match the JSON contract defined
in system_prompt.md: {findings, confidence, sources, unknowns,
recommended_action}. This module does not parse or validate that reply --
parsing structured JSON responses is the caller's responsibility once an
actual model integration exists.
"""

from pathlib import Path

_TEMPLATE_DIR = Path(__file__).resolve().parent


def load_prompt(name: str, **kwargs) -> str:
    """Load a .md template by name (without extension) and fill
    {placeholder} fields with kwargs. Missing placeholders raise KeyError
    immediately rather than silently emitting a half-filled prompt."""
    path = _TEMPLATE_DIR / f"{name}.md"
    template = path.read_text()
    return template.format(**kwargs)


def load_system_prompt() -> str:
    return (_TEMPLATE_DIR / "system_prompt.md").read_text()


def _fmt_list(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- {i}" for i in items) if items else empty


def build_morning_prompt(regime, macro: dict, top_candidates: list,
                          holdings: list[dict], news_events: list[dict]) -> str:
    regime_summary = (
        f"{regime.regime} -- Nifty {regime.nifty_above_dma_pct:+.2f}% vs 200-DMA, "
        f"VIX {regime.vix:.2f}, max equity exposure {regime.max_equity_exposure:.0%}"
    )
    macro_lines = []
    for label, quotes in macro.items():
        row = ", ".join(f"{q.name} {q.last:,.2f} ({q.change_pct:+.2f}%)" for q in quotes)
        if row:
            macro_lines.append(f"{label}: {row}")
    candidate_lines = [
        f"{c.symbol} rank score {c.momentum_score*100:.1f} (3M {c.ret_3m*100:+.1f}%, "
        f"6M {c.ret_6m*100:+.1f}%)"
        for c in top_candidates
    ]
    holding_lines = [f"{h['symbol']} value Rs{h['value_inr']/1e5:.1f}L" for h in holdings]
    event_lines = [
        f"{e['symbol']}: {e['move_pct']:+.1f}% on {e['volume_multiple']:.1f}x volume "
        f"({e['direction']})"
        for e in news_events
    ]
    return load_prompt(
        "morning_scan_prompt",
        regime_summary=regime_summary,
        macro_summary=_fmt_list(macro_lines),
        top_candidates=_fmt_list(candidate_lines),
        holdings_summary=_fmt_list(holding_lines),
        news_events=_fmt_list(event_lines),
    )


def build_event_prompt(event_flags: list[dict], priced_in_results: list) -> str:
    event_lines = [
        f"{e['symbol']}: {e['move_pct']:+.1f}% on {e['volume_multiple']:.1f}x volume "
        f"({e['direction']})"
        for e in event_flags
    ]
    priced_in_lines = [
        f"{r.symbol}: current {r.current_move_pct:+.1f}% vs historical median "
        f"{r.historical_median_pct:+.1f}% (n={r.comparable_events_count}, "
        f"conf={r.confidence:.2f}) -- {r.status}"
        for r in priced_in_results
    ]
    return load_prompt(
        "event_research_prompt",
        event_flags=_fmt_list(event_lines),
        priced_in_results=_fmt_list(priced_in_lines),
    )


def build_stock_prompt(symbol: str, all_data_for_symbol: dict) -> str:
    data_lines = [f"{k}: {v}" for k, v in all_data_for_symbol.items()]
    return load_prompt(
        "stock_research_prompt",
        symbol=symbol,
        deterministic_data=_fmt_list(data_lines),
    )


def build_sector_prompt(sector_scores: list, commodity_tilts: list[str]) -> str:
    score_lines = [
        f"{s.sector}: score {s.overall_score:.1f}/100, RS vs Nifty {s.rs_vs_nifty:+.2f}%, "
        f"breadth >20DMA {s.breadth_above_20dma:.1f}%, commodity {s.commodity_impact}"
        for s in sector_scores
    ]
    return load_prompt(
        "sector_research_prompt",
        sector_scores=_fmt_list(score_lines),
        commodity_tilts=_fmt_list(commodity_tilts),
    )


def build_portfolio_prompt(holdings: list[dict], tax_statuses: list, sector_exposure: list) -> str:
    holding_lines = [f"{h['symbol']} value Rs{h['value_inr']/1e5:.1f}L" for h in holdings]
    tax_lines = [
        f"{s.symbol}: {'LTCG' if s.is_ltcg else 'STCG'}, held {s.days_held}d, "
        f"gain {s.unrealized_gain_pct:+.1f}%"
        for s in tax_statuses
    ]
    sector_lines = [
        f"{e.sector}: {e.pct_of_capital:.1%} of capital ({', '.join(e.symbols)})"
        for e in sector_exposure
    ]
    return load_prompt(
        "portfolio_review_prompt",
        holdings_summary=_fmt_list(holding_lines),
        tax_statuses=_fmt_list(tax_lines),
        sector_exposure=_fmt_list(sector_lines),
    )


def build_midday_prompt(positions: list[dict], intraday_moves: list[dict]) -> str:
    move_lines = [
        f"{m['symbol']}: {m.get('move_pct', 0):+.1f}% since open" for m in intraday_moves
    ]
    pending_lines = [f"{p['symbol']}: {p.get('action', 'pending')}" for p in positions]
    return load_prompt(
        "midday_scan_prompt",
        intraday_moves=_fmt_list(move_lines),
        pending_approvals=_fmt_list(pending_lines),
    )


def build_closing_prompt(rankings: list, day_summary: str) -> str:
    ranking_lines = [
        f"#{i+1} {c.symbol} score {c.momentum_score*100:.1f}"
        for i, c in enumerate(rankings)
    ]
    return load_prompt(
        "closing_scan_prompt",
        rankings=_fmt_list(ranking_lines),
        day_summary=day_summary or "(none)",
    )


def build_emergency_prompt(trigger_type: str, data: dict) -> str:
    data_lines = [f"{k}: {v}" for k, v in data.items()]
    return load_prompt(
        "emergency_prompt",
        trigger_type=trigger_type,
        trigger_data=_fmt_list(data_lines),
    )


def build_market_research_prompt(macro: dict, regime) -> str:
    macro_lines = []
    for label, quotes in macro.items():
        row = ", ".join(f"{q.name} {q.last:,.2f} ({q.change_pct:+.2f}%)" for q in quotes)
        if row:
            macro_lines.append(f"{label}: {row}")
    regime_summary = (
        f"{regime.regime} -- Nifty {regime.nifty_above_dma_pct:+.2f}% vs 200-DMA, "
        f"VIX {regime.vix:.2f}, max equity exposure {regime.max_equity_exposure:.0%}"
    )
    return load_prompt(
        "market_research_prompt",
        macro_summary=_fmt_list(macro_lines),
        regime_summary=regime_summary,
    )
