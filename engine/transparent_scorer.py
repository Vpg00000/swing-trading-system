from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime

@dataclass
class ScoreBreakdown:
    symbol: str
    total_score: float  # 0-100
    confidence: str  # HIGH, MEDIUM, LOW
    
    # Component scores with explicit caps
    catalyst_score: float  # max 20
    early_signal_score: float  # max 15
    volume_delivery_score: float  # max 15
    price_momentum_score: float  # max 10
    technical_structure_score: float  # max 10
    sector_strength_score: float  # max 10
    market_regime_score: float  # max 5
    historical_probability_score: float  # max 10
    liquidity_score: float  # max 5
    risk_penalty: float  # max -15
    
    # Metadata
    direction: str  # BULLISH, BEARISH
    cap_category: str  # LARGE, MID, SMALL, PENNY
    early_signal_count: int
    confirmation_count: int
    risk_flags: List[str]
    timestamp: str

def score_catalyst(symbol: str, catalyst_data: dict) -> float:
    evidence = catalyst_data.get('evidence_level', 'SPECULATION')
    materiality = catalyst_data.get('materiality_ratio', 0.0)
    
    base_score = 0.0
    if evidence == 'FACT':
        base_score = 10.0
    elif evidence == 'INFERENCE':
        base_score = 5.0
    elif evidence == 'SPECULATION':
        base_score = 0.0
        
    return min(20.0, base_score + (materiality * 10.0))

def score_early_signals(early_count: int, total_signals: int) -> float:
    if total_signals == 0:
        return 0.0
    purity = early_count / float(total_signals)
    return min(15.0, purity * 15.0)

def score_volume_delivery(vol_ratio: float, delivery_pct: float) -> float:
    v_score = min(7.5, (vol_ratio - 1.0) * 2.5) if vol_ratio > 1.0 else 0.0
    d_score = min(7.5, (delivery_pct / 100.0) * 15.0)
    return min(15.0, v_score + d_score)

def score_price_momentum(ret_1d: float, ret_5d: float, above_20dma: bool) -> float:
    score = 0.0
    if above_20dma:
        score += 3.0
    
    if ret_1d > 0.02:
        score += 3.0
    elif ret_1d > 0:
        score += 1.0
        
    if ret_5d > 0.05:
        score += 4.0
    elif ret_5d > 0:
        score += 2.0
        
    return min(10.0, score)

def score_technical_structure(ttm_squeeze: bool, bb_width: float, nr7: bool) -> float:
    score = 0.0
    if ttm_squeeze:
        score += 4.0
    if nr7:
        score += 3.0
    if bb_width < 0.1: 
        score += 3.0
    return min(10.0, score)

def score_sector_strength(sector_return: float, sector_rank: int) -> float:
    score = 0.0
    if sector_return > 0:
        score += 5.0
    
    if sector_rank <= 3:
        score += 5.0
    elif sector_rank <= 6:
        score += 2.5
        
    return min(10.0, score)

def score_market_regime(nifty_above_50dma: bool, vix: float) -> float:
    score = 0.0
    if nifty_above_50dma:
        score += 2.5
    if 12.0 <= vix <= 18.0:
        score += 2.5
    return min(5.0, score)

def score_historical_probability(win_rate_5d: float, occurrences: int) -> float:
    if occurrences < 5:
        return 0.0
    return min(10.0, win_rate_5d * 10.0)

def score_liquidity(avg_turnover_cr: float) -> float:
    if avg_turnover_cr > 50:
        return 5.0
    elif avg_turnover_cr > 20:
        return 3.0
    elif avg_turnover_cr > 5:
        return 1.0
    return 0.0

def calculate_risk_penalty(atr_pct: float, debt_equity: float, earnings_due: bool, asm_gsm: bool) -> float:
    penalty = 0.0
    if atr_pct > 0.05:
        penalty -= 3.0
    if debt_equity > 2.0:
        penalty -= 4.0
    if earnings_due:
        penalty -= 3.0
    if asm_gsm:
        penalty -= 5.0
    return max(-15.0, penalty)

def compute_composite_score(symbol: str, **kwargs) -> ScoreBreakdown:
    catalyst_score = score_catalyst(symbol, kwargs.get('catalyst_data', {}))
    early_signal_score = score_early_signals(kwargs.get('early_count', 0), kwargs.get('total_signals', 0))
    volume_delivery_score = score_volume_delivery(kwargs.get('vol_ratio', 1.0), kwargs.get('delivery_pct', 0.0))
    price_momentum_score = score_price_momentum(kwargs.get('ret_1d', 0.0), kwargs.get('ret_5d', 0.0), kwargs.get('above_20dma', False))
    technical_structure_score = score_technical_structure(kwargs.get('ttm_squeeze', False), kwargs.get('bb_width', 1.0), kwargs.get('nr7', False))
    sector_strength_score = score_sector_strength(kwargs.get('sector_return', 0.0), kwargs.get('sector_rank', 10))
    market_regime_score = score_market_regime(kwargs.get('nifty_above_50dma', False), kwargs.get('vix', 15.0))
    historical_probability_score = score_historical_probability(kwargs.get('win_rate_5d', 0.0), kwargs.get('occurrences', 0))
    liquidity_score = score_liquidity(kwargs.get('avg_turnover_cr', 0.0))
    risk_penalty = calculate_risk_penalty(kwargs.get('atr_pct', 0.0), kwargs.get('debt_equity', 0.0), kwargs.get('earnings_due', False), kwargs.get('asm_gsm', False))
    
    raw_total = sum([
        catalyst_score, early_signal_score, volume_delivery_score, price_momentum_score,
        technical_structure_score, sector_strength_score, market_regime_score,
        historical_probability_score, liquidity_score, risk_penalty
    ])
    
    total_score = round(max(0.0, min(100.0, raw_total)), 2)
    
    if total_score > 70:
        confidence = "HIGH"
    elif total_score > 40:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
        
    risk_flags = []
    if kwargs.get('asm_gsm'): risk_flags.append('ASM/GSM')
    if kwargs.get('earnings_due'): risk_flags.append('EARNINGS_DUE')
    if kwargs.get('debt_equity', 0.0) > 2.0: risk_flags.append('HIGH_DEBT')
        
    return ScoreBreakdown(
        symbol=symbol,
        total_score=total_score,
        confidence=confidence,
        catalyst_score=catalyst_score,
        early_signal_score=early_signal_score,
        volume_delivery_score=volume_delivery_score,
        price_momentum_score=price_momentum_score,
        technical_structure_score=technical_structure_score,
        sector_strength_score=sector_strength_score,
        market_regime_score=market_regime_score,
        historical_probability_score=historical_probability_score,
        liquidity_score=liquidity_score,
        risk_penalty=risk_penalty,
        direction=kwargs.get('direction', 'BULLISH'),
        cap_category=kwargs.get('cap_category', 'LARGE'),
        early_signal_count=kwargs.get('early_count', 0),
        confirmation_count=kwargs.get('total_signals', 0) - kwargs.get('early_count', 0),
        risk_flags=risk_flags,
        timestamp=datetime.now().isoformat()
    )
