"""
Contextual manual-check reminders -- per the user's explicit requirement:
the system should remind them, day by day, which manual checks are worth
doing -- but only the ones relevant to *today's* actual candidates/holdings,
not a static 40-link menu every morning regardless of what's in the universe.

Free-data proxy: GICS sector + industry (via yfinance's `Ticker.info`, same
cache as engine/correlation.py) is used to route each symbol to the
regulator/site that actually covers it. These sites have no free API worth
automating (or are genuinely manual-judgment reads, e.g. a rating action or
a warning letter) -- this module's job is only to surface *which* symbols
warrant *which* check today, not to fetch the check itself.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.correlation import get_sector, get_industry

# Keyed by GICS sector, with an optional industry-substring override for
# sectors that bundle unrelated regulatory regimes (e.g. "Utilities" covers
# both power and gas distribution; "Financial Services" covers banks, NBFCs,
# and insurers under different regulators).
SECTOR_MANUAL_CHECKS: dict[str, str] = {
    "Healthcare": "US FDA + CDSCO -- warning letters, plant inspections, drug approvals",
    "Communication Services": "TRAI -- subscriber additions, ARPU, spectrum/license news",
    "Energy": "PNGRB + Petroleum Ministry -- pipeline tariffs, crude allocation, subsidy changes",
    "Basic Materials": "CRISIL/ICRA/CARE -- credit rating actions; Ministry of Steel/Mines for capacity",
    "Industrials": "Ministry of Commerce/DGFT -- export incentives, PLI scheme updates",
    "Consumer Cyclical": "Auto sales data (SIAM) or retail footfall trends, GST/import duty changes",
    "Consumer Defensive": "Rural demand indicators (monsoon/MSP), input cost (palm oil/crude) trends",
    "Technology": "US IT spend commentary (client earnings calls), visa/H-1B policy news",
    "Real Estate": "RERA filings, city-level inventory/absorption data",
}

# Industry-substring overrides checked before the sector-level default --
# first match wins, so order matters within each sector's override list.
INDUSTRY_OVERRIDES: dict[str, list[tuple[str, str]]] = {
    "Utilities": [
        ("Gas", "PNGRB -- city gas distribution tariffs, allocation"),
        ("Electric", "CERC + Ministry of Power -- tariff orders, PLF, capacity addition"),
        ("Water", "State regulatory commission tariff orders"),
    ],
    "Financial Services": [
        ("Bank", "RBI -- credit growth, NIM, GNPA, policy rate moves"),
        ("Insurance", "IRDAI -- solvency ratio, claim ratio disclosures"),
        ("Capital Markets", "SEBI -- broking/AMC regulatory circulars"),
        ("Credit Services", "RBI NBFC directions -- asset quality, capital adequacy"),
    ],
}


@dataclass
class ManualCheckReminder:
    sector: str
    check: str
    symbols: list[str]


def get_manual_check_for_symbol(symbol: str) -> str | None:
    sector = get_sector(symbol)
    industry = get_industry(symbol)
    for substring, check in INDUSTRY_OVERRIDES.get(sector, []):
        if substring.lower() in industry.lower():
            return check
    return SECTOR_MANUAL_CHECKS.get(sector)


def get_manual_check_reminders(symbols: list[str]) -> list[ManualCheckReminder]:
    """One reminder per distinct (sector, check) pair actually present among
    `symbols` today, each listing which symbols triggered it."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for symbol in symbols:
        check = get_manual_check_for_symbol(symbol)
        if check is None:
            continue
        sector = get_sector(symbol)
        grouped.setdefault((sector, check), []).append(symbol)

    reminders = [
        ManualCheckReminder(sector=sector, check=check, symbols=syms)
        for (sector, check), syms in grouped.items()
    ]
    reminders.sort(key=lambda r: r.sector)
    return reminders


if __name__ == "__main__":
    demo_symbols = [
        "SUNPHARMA.NS", "NTPC.NS", "GAIL.NS", "BHARTIARTL.NS",
        "ONGC.NS", "HDFCBANK.NS", "TATASTEEL.NS", "RELIANCE.NS",
    ]
    for r in get_manual_check_reminders(demo_symbols):
        print(f"[{r.sector}] {', '.join(r.symbols)}")
        print(f"  -> {r.check}")
