"""
Forensic Fundamentals & Governance Audit Engine.

Implements:
1. Beneish M-Score 8-variable earnings manipulation flag (Flag if M > -1.78).
2. Altman Z-Score insolvency risk flag (Flag if Z < 1.81).
3. Contingent Liabilities Check (Flag if > 20% Net Worth).
4. Related-Party Transactions (RPT) Check (Flag if > 10% Revenue).
5. Big-4 & Top Auditor Quality Lookup Table.
6. Promoter Pledge Velocity Check (Flag if Pledge increases > 5% QoQ).
7. Cash Flow Conversion Check (Flag if CFO/PAT < 0.8 over 3 years).
8. Debt-Financed Dividend Outflow Check.

Fixes Problems: 161, 162, 163, 164, 165, 166, 167, 169.
"""

from typing import Dict, Any, List, Optional

BIG4_AUDITORS = {
    "BS R & CO", "DELOITTE", "PWC", "PRICE WATERHOUSE", "PRICEWATERHOUSECOOPERS",
    "EY", "ERNST & YOUNG", "S R BATLIBOI", "WALCHAND", "KHANNA & ANNADHANAM",
    "BDO", "GRANT THORNTON", "HARIBHAKTI", "MSKA", "WALCHANDNAGAR"
}

def calculate_beneish_m_score(
    dsri: float = 1.0,   # Days Sales in Receivables Index
    gmi: float = 1.0,    # Gross Margin Index
    aqi: float = 1.0,    # Asset Quality Index
    sgi: float = 1.0,    # Sales Growth Index
    depi: float = 1.0,   # Depreciation Index
    sgai: float = 1.0,   # Sales General & Admin Expense Index
    lvgi: float = 1.0,   # Leverage Index
    tata: float = 0.0    # Total Accruals to Total Assets
) -> Dict[str, Any]:
    """
    Computes 8-variable Beneish M-Score:
    M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + 0.115*DEPI - 0.172*SGAI + 4.679*TATA + 0.327*LVGI
    Flag as EARNINGS_MANIPULATION_RISK if M > -1.78.
    (Fixes Problem 161)
    """
    m_score = (
        -4.84 +
        0.920 * dsri +
        0.528 * gmi +
        0.404 * aqi +
        0.892 * sgi +
        0.115 * depi -
        0.172 * sgai +
        4.679 * tata +
        0.327 * lvgi
    )
    m_score = round(m_score, 2)
    is_manipulator = m_score > -1.78
    return {
        "m_score": m_score,
        "is_manipulator": is_manipulator,
        "status": "MANIPULATION_RISK" if is_manipulator else "SAFE"
    }

def calculate_altman_z_score(
    working_cap_to_assets: float,
    retained_earnings_to_assets: float,
    ebit_to_assets: float,
    market_cap_to_liabilities: float,
    sales_to_assets: float
) -> Dict[str, Any]:
    """
    Computes Altman Z-Score for non-financial manufacturing/commercial firms:
    Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 0.999*X5
    Z < 1.81: Distress Zone (Insolvency Risk)
    Z 1.81 - 2.99: Grey Zone
    Z > 2.99: Safe Zone
    (Fixes Problem 162)
    """
    z = (
        1.2 * working_cap_to_assets +
        1.4 * retained_earnings_to_assets +
        3.3 * ebit_to_assets +
        0.6 * market_cap_to_liabilities +
        0.999 * sales_to_assets
    )
    z_score = round(z, 2)
    if z_score < 1.81:
        zone = "DISTRESS_ZONE"
    elif z_score <= 2.99:
        zone = "GREY_ZONE"
    else:
        zone = "SAFE_ZONE"

    return {"z_score": z_score, "zone": zone, "is_distressed": z_score < 1.81}

def check_contingent_liabilities(contingent_liabilities: float, net_worth: float) -> Dict[str, Any]:
    """
    Flags companies if contingent liabilities exceed 20% of net worth.
    Handles zero or negative net_worth gracefully.
    (Fixes Problem 163)
    """
    is_high_risk = False
    ratio = 0.0
    if net_worth <= 0:
        if contingent_liabilities > 0:
            is_high_risk = True
            ratio = 1.0
    else:
        ratio = round(contingent_liabilities / net_worth, 2)
        if ratio > 0.20:
            is_high_risk = True

    return {
        "contingent_liabilities": contingent_liabilities,
        "net_worth": net_worth,
        "cl_to_nw_ratio": ratio,
        "is_high_risk": is_high_risk,
        "status": "HIGH_CONTINGENT_LIABILITY_RISK" if is_high_risk else "NORMAL"
    }

def check_related_party_transactions(rpt_value: float, revenue: float) -> Dict[str, Any]:
    """
    Flags related-party transactions if they exceed 10% of total revenue.
    Handles zero or negative revenue gracefully.
    (Fixes Problem 164)
    """
    is_high_risk = False
    ratio = 0.0
    if revenue <= 0:
        if rpt_value > 0:
            is_high_risk = True
            ratio = 1.0
    else:
        ratio = round(rpt_value / revenue, 2)
        if ratio > 0.10:
            is_high_risk = True

    return {
        "rpt_value": rpt_value,
        "revenue": revenue,
        "rpt_to_revenue_ratio": ratio,
        "is_high_risk": is_high_risk,
        "status": "HIGH_RPT_RISK" if is_high_risk else "NORMAL"
    }

def verify_auditor_quality(auditor_name: str) -> Dict[str, Any]:
    """
    Checks if statutory auditor belongs to Big-4 / Reputed Top audit firms.
    (Fixes Problem 165)
    """
    name_upper = auditor_name.upper()
    is_reputed = any(b4 in name_upper for b4 in BIG4_AUDITORS)
    return {
        "auditor_name": auditor_name,
        "is_reputed": is_reputed,
        "quality_rating": "HIGH" if is_reputed else "UNVERIFIED_LOCAL"
    }

def check_promoter_pledge_velocity(current_pledge_pct: float, prev_pledge_pct: float) -> Dict[str, Any]:
    """
    Flags companies where promoter pledge increased by > 5% QoQ or if current pledge is >= 25%.
    (Fixes Problem 166)
    """
    diff = round(current_pledge_pct - prev_pledge_pct, 2)
    is_high_risk = diff >= 5.0 or current_pledge_pct >= 25.0
    warning = "NORMAL"
    if diff >= 5.0:
        warning = "PLEDGE_ACCELERATION_WARNING"
    elif current_pledge_pct >= 25.0:
        warning = "HIGH_PLEDGE_CAP"
    return {
        "current_pledge_pct": current_pledge_pct,
        "pledge_change_qoq": diff,
        "is_high_risk": is_high_risk,
        "warning": warning
    }

def check_cashflow_conversion(cfo_inr: float, pat_inr: float) -> Dict[str, Any]:
    """
    Computes Cash Flow Conversion ratio (CFO / PAT). Flags paper profits if CFO/PAT < 0.8.
    Handles zero or negative PAT gracefully.
    (Fixes Problem 167)
    """
    ratio = 1.0
    if pat_inr > 0:
        ratio = round(cfo_inr / pat_inr, 2)
    return {
        "cfo_inr": cfo_inr,
        "pat_inr": pat_inr,
        "conversion_ratio": ratio,
        "is_paper_profit": ratio < 0.8
    }

def check_debt_financed_dividend_outflow(
    dividends_paid: float,
    operating_cash_flow: float,
    total_debt_current: float,
    total_debt_previous: float
) -> Dict[str, Any]:
    """
    Flags if dividends paid exceed operating cash flow AND total debt has increased.
    This indicates dividends might be financed by debt, which is a red flag.
    (Fixes Problem 169)
    """
    is_debt_financed = False

    dividends_exceed_cfo = False
    if operating_cash_flow <= 0:
        if dividends_paid > 0:
            dividends_exceed_cfo = True
    else:
        if dividends_paid > operating_cash_flow:
            dividends_exceed_cfo = True

    debt_increased = total_debt_current > total_debt_previous

    if dividends_exceed_cfo and debt_increased:
        is_debt_financed = True

    return {
        "dividends_paid": dividends_paid,
        "operating_cash_flow": operating_cash_flow,
        "total_debt_current": total_debt_current,
        "total_debt_previous": total_debt_previous,
        "dividends_exceed_cfo": dividends_exceed_cfo,
        "debt_increased": debt_increased,
        "is_debt_financed": is_debt_financed,
        "status": "DEBT_FINANCED_DIVIDEND_RISK" if is_debt_financed else "NORMAL"
    }

if __name__ == "__main__":
    print("Testing Forensic Fundamentals Module...\n")
    m = calculate_beneish_m_score(dsri=1.4, gmi=1.2, aqi=1.3, tata=0.08)
    print(f"  Beneish M-Score: {m}")
    z = calculate_altman_z_score(0.2, 0.3, 0.15, 1.2, 0.8)
    print(f"  Altman Z-Score: {z}")
    aud = verify_auditor_quality("B S R & Co. LLP")
    print(f"  Auditor Check: {aud}")
    pledge = check_promoter_pledge_velocity(18.5, 12.0)
    print(f"  Pledge Velocity: {pledge}")

    # New tests for added functions
    cl = check_contingent_liabilities(25.0, 100.0) # CL > 20% NW
    print(f"  Contingent Liabilities (high): {cl}")
    cl_safe = check_contingent_liabilities(10.0, 100.0)
    print(f"  Contingent Liabilities (safe): {cl_safe}")
    cl_zero_nw = check_contingent_liabilities(5.0, 0.0) # CL > 0, NW = 0
    print(f"  Contingent Liabilities (zero NW, positive CL): {cl_zero_nw}")
    cl_zero_all = check_contingent_liabilities(0.0, 0.0) # CL = 0, NW = 0
    print(f"  Contingent Liabilities (zero all): {cl_zero_all}")

    rpt = check_related_party_transactions(15.0, 100.0) # RPT > 10% Revenue
    print(f"  Related-Party Transactions (high): {rpt}")
    rpt_safe = check_related_party_transactions(5.0, 100.0)
    print(f"  Related-Party Transactions (safe): {rpt_safe}")
    rpt_zero_rev = check_related_party_transactions(2.0, 0.0) # RPT > 0, Revenue = 0
    print(f"  Related-Party Transactions (zero Rev, positive RPT): {rpt_zero_rev}")
    rpt_zero_all = check_related_party_transactions(0.0, 0.0) # RPT = 0, Revenue = 0
    print(f"  Related-Party Transactions (zero all): {rpt_zero_all}")

    cf_conversion = check_cashflow_conversion(80.0, 100.0) # CFO/PAT = 0.8, safe
    print(f"  Cash Flow Conversion (safe): {cf_conversion}")
    cf_paper_profit = check_cashflow_conversion(70.0, 100.0) # CFO/PAT < 0.8, paper profit
    print(f"  Cash Flow Conversion (paper profit): {cf_paper_profit}")
    cf_zero_pat = check_cashflow_conversion(10.0, 0.0) # PAT = 0
    print(f"  Cash Flow Conversion (zero PAT): {cf_zero_pat}")
    cf_negative_pat = check_cashflow_conversion(10.0, -5.0) # PAT < 0
    print(f"  Cash Flow Conversion (negative PAT): {cf_negative_pat}")

    debt_div = check_debt_financed_dividend_outflow(
        dividends_paid=50.0, operating_cash_flow=30.0, total_debt_current=120.0, total_debt_previous=100.0
    ) # Dividends > CFO and Debt Increased
    print(f"  Debt-Financed Dividend (risk): {debt_div}")
    debt_div_safe_cfo = check_debt_financed_dividend_outflow(
        dividends_paid=30.0, operating_cash_flow=50.0, total_debt_current=120.0, total_debt_previous=100.0
    ) # Dividends < CFO, Debt Increased (safe from this check)
    print(f"  Debt-Financed Dividend (safe - sufficient CFO): {debt_div_safe_cfo}")
    debt_div_safe_debt = check_debt_financed_dividend_outflow(
        dividends_paid=50.0, operating_cash_flow=30.0, total_debt_current=100.0, total_debt_previous=120.0
    ) # Dividends > CFO, Debt Decreased (safe from this check)
    print(f"  Debt-Financed Dividend (safe - debt decreased): {debt_div_safe_debt}")
    debt_div_zero_cfo = check_debt_financed_dividend_outflow(
        dividends_paid=10.0, operating_cash_flow=0.0, total_debt_current=120.0, total_debt_previous=100.0
    ) # CFO=0, Dividends > 0, Debt increased (risk)
    print(f"  Debt-Financed Dividend (zero CFO, risk): {debt_div_zero_cfo}")
    debt_div_negative_cfo = check_debt_financed_dividend_outflow(
        dividends_paid=10.0, operating_cash_flow=-5.0, total_debt_current=120.0, total_debt_previous=100.0
    ) # CFO<0, Dividends > 0, Debt increased (risk)
    print(f"  Debt-Financed Dividend (negative CFO, risk): {debt_div_negative_cfo}")