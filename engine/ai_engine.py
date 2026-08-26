import os

def calculate_dynamic_weights(regime_status: str) -> Dict[str, float]:
    bull_weight = float(os.getenv('DANH_BULL_WEIGHT', '0.35'))
    bear_weight = float(os.getenv('DANH_BEAR_WEIGHT', '0.40'))
    if "BULL" in regime_status.upper():
        return {
            "technical": bull_weight,
            "rs": 0.20,
            "fundamental": 0.15,
            "valuation": 0.10,
            "governance": 0.10,
            "trend": 0.10
        }
    elif "BEAR" in regime_status.upper():
        return {
            "fundamental": bear_weight,
            "valuation": 0.15,
            "technical": 0.20,
            "rs": 0.15,
            "governance": 0.15,
            "trend": 0.10
        }
    else:
        return {
            "technical": 0.20,
            "rs": 0.20,
            "fundamental": 0.20,
            "governance": 0.15,
            "valuation": 0.15,
            "trend": 0.10
        }
