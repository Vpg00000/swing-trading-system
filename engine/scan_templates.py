"""
15 Curated Pre-Built Scan Templates for the Screener Engine.

These map directly to ScanX top screeners and popular strategy presets,
with the added power of AI predictions (Composite score, R:R, Target).

Templates included:
  1. Best Quarterly Results
  2. CapEx Boost (Growth)
  3. Potential Multibagger (SmallCap high growth)
  4. Undervalued Near High
  5. Mighty Midcap
  6. Momentum Breakout (52W high + volume surge)
  7. Oversold Bounce (RSI < 35 + reversal)
  8. Golden Cross (50DMA crossing 200DMA)
  9. Bollinger Squeeze (Volatility compression)
 10. FII Accumulation (High score + FII backing)
 11. Smart Money Zone (DII + low pledge + quality governance)
 12. Breakout + Volume (Multi-month breakout with 2x volume)
 13. High RS Momentum (6M RS > 70)
 14. BTST Momentum (Short-term momentum setup)
 15. High Dividend / Quality Value
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.screener_engine import ScreenerFilter, filter_universe


@dataclass
class ScanTemplate:
    id: str
    name: str
    category: str        # FUNDAMENTAL / TECHNICAL / SMART_MONEY / AI_PREDICTION
    description: str
    filter_config: ScreenerFilter
    author: str = "System"


PREBUILT_SCANS: list[ScanTemplate] = [
    # ── FUNDAMENTAL ───────────────────────────
    ScanTemplate(
        id="best-quarterly-results",
        name="Best Quarterly Results",
        category="FUNDAMENTAL",
        description="High ROE & ROCE (>15%), strong growth, low debt",
        filter_config=ScreenerFilter(
            min_roe=15.0,
            min_roce=15.0,
            max_debt_to_equity=1.0,
            min_fundamental_score=65.0
        )
    ),
    ScanTemplate(
        id="potential-multibagger",
        name="Potential Multibagger",
        category="FUNDAMENTAL",
        description="Small & Mid caps (< 25,000 Cr) with high ROE and strong AI score",
        filter_config=ScreenerFilter(
            max_market_cap_cr=25000.0,
            min_roe=18.0,
            min_score=65.0
        )
    ),
    ScanTemplate(
        id="undervalued-near-high",
        name="Undervalued Near High",
        category="FUNDAMENTAL",
        description="Low P/E (<25) stocks trading near 52-week high (within 7%)",
        filter_config=ScreenerFilter(
            max_pe=25.0,
            max_pct_from_52w_high=-7.0,
            min_score=60.0
        )
    ),
    ScanTemplate(
        id="mighty-midcap",
        name="Mighty Midcap",
        category="FUNDAMENTAL",
        description="Midcaps (10,000 Cr - 50,000 Cr) with strong composite score",
        filter_config=ScreenerFilter(
            min_market_cap_cr=10000.0,
            max_market_cap_cr=50000.0,
            min_score=65.0
        )
    ),

    # ── TECHNICAL ─────────────────────────────
    ScanTemplate(
        id="momentum-breakout",
        name="Momentum Breakout",
        category="TECHNICAL",
        description="Stocks breaking 52-week high with > 1.5x volume surge",
        filter_config=ScreenerFilter(
            is_breakout_only=True,
            min_volume_ratio=1.5,
            min_rsi=55.0
        )
    ),
    ScanTemplate(
        id="near-breakout",
        name="Near Breakout Stocks in Uptrend",
        category="TECHNICAL",
        description="Stocks within 3% of 52-week high with solid momentum",
        filter_config=ScreenerFilter(
            is_near_breakout_only=True,
            above_50dma=True,
            min_rsi=50.0
        )
    ),
    ScanTemplate(
        id="oversold-bounce",
        name="Oversold Reversal Bounce",
        category="TECHNICAL",
        description="RSI < 35 bouncing back with MACD positive momentum",
        filter_config=ScreenerFilter(
            max_rsi=35.0,
            oversold_bounce_only=True
        )
    ),
    ScanTemplate(
        id="golden-cross",
        name="Golden Cross Trend Reversal",
        category="TECHNICAL",
        description="50-day moving average crossing above 200-day moving average",
        filter_config=ScreenerFilter(
            golden_cross_only=True
        )
    ),
    ScanTemplate(
        id="bollinger-squeeze",
        name="Bollinger Band Volatility Squeeze",
        category="TECHNICAL",
        description="Band width < 5% indicating imminent explosive move",
        filter_config=ScreenerFilter(
            bollinger_squeeze_only=True,
            above_50dma=True
        )
    ),

    # ── SMART MONEY ───────────────────────────
    ScanTemplate(
        id="fii-accumulation",
        name="Smart Money Accumulation",
        category="SMART_MONEY",
        description="High Composite Score (>70) with solid governance and low pledge",
        filter_config=ScreenerFilter(
            min_score=70.0,
            min_governance_score=75.0,
            max_pledge_pct=5.0
        )
    ),
    ScanTemplate(
        id="high-rs-leaders",
        name="Relative Strength Leaders",
        category="SMART_MONEY",
        description="Stocks in top 30% RS rating outperforming Nifty and sector",
        filter_config=ScreenerFilter(
            min_rs_score=70.0,
            above_50dma=True
        )
    ),

    # ── AI PREDICTION ─────────────────────────
    ScanTemplate(
        id="high-conviction-buys",
        name="High Conviction AI BUY Signals",
        category="AI_PREDICTION",
        description="Composite score > 72, BUY_NOW action, R:R > 2.0",
        filter_config=ScreenerFilter(
            min_score=72.0,
            actions=["BUY_NOW"],
            min_rr_ratio=2.0
        )
    ),
    ScanTemplate(
        id="asymmetric-rr",
        name="Asymmetric Risk:Reward (> 1:2.5)",
        category="AI_PREDICTION",
        description="Exceptional risk-reward ratio (> 2.5) with expected value > 4%",
        filter_config=ScreenerFilter(
            min_rr_ratio=2.5,
            min_expected_return_pct=4.0
        )
    )
]


def get_scan_template(template_id: str) -> ScanTemplate | None:
    """Find template by ID."""
    for scan in PREBUILT_SCANS:
        if scan.id == template_id:
            return scan
    return None


def run_scan_template(template_id: str, symbols: list[str] | None = None) -> list[dict[str, Any]]:
    """Run a pre-built scan template across universe."""
    template = get_scan_template(template_id)
    if not template:
        raise ValueError(f"Scan template '{template_id}' not found.")
    return filter_universe(template.filter_config, symbols=symbols)


if __name__ == "__main__":
    print(f"Available Pre-Built Scans ({len(PREBUILT_SCANS)} templates):\n")
    for scan in PREBUILT_SCANS:
        print(f"  [{scan.category:<12}] {scan.name:<32} ({scan.id})")
