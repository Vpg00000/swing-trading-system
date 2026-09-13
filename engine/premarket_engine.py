from typing import List, Dict, Any
from datetime import date
import hashlib
import json

from data.database import get_connection, init_db, freeze_morning_predictions
from engine.transparent_scorer import ScoreBreakdown, compute_composite_score
from dataclasses import asdict

def rank_candidates(scored_stocks: List[ScoreBreakdown]) -> Dict[str, Any]:
    # Returns 40-stock matrix:
    # 5 Large Cap Gainers + 5 Large Cap Losers
    # 5 Mid Cap Gainers + 5 Mid Cap Losers
    # 5 Small Cap Gainers + 5 Small Cap Losers
    # 5 Penny/Micro Gainers + 5 Penny/Micro Losers
    
    candidates_matrix = {
        'LARGE': {'BULLISH': [], 'BEARISH': []},
        'MID': {'BULLISH': [], 'BEARISH': []},
        'SMALL': {'BULLISH': [], 'BEARISH': []},
        'PENNY': {'BULLISH': [], 'BEARISH': []}
    }
    
    # Sort stocks by total_score descending, then delivery % (using volume_delivery_score as proxy for tie-breaking)
    sorted_stocks = sorted(scored_stocks, key=lambda x: (x.total_score, x.volume_delivery_score), reverse=True)
    
    for stock in sorted_stocks:
        cat = stock.cap_category.upper() if stock.cap_category else ''
        if cat == 'MICRO':
            cat = 'PENNY'
            
        if cat not in candidates_matrix:
            continue
            
        direction = stock.direction.upper() if stock.direction else ''
        if direction not in ['BULLISH', 'BEARISH']:
            continue
            
        if len(candidates_matrix[cat][direction]) >= 5:
            continue
            
        candidates_matrix[cat][direction].append(stock)
        
    return candidates_matrix

def freeze_prediction(candidates: dict, prediction_date: str) -> dict:
    flat_candidates = []
    for cat, dirs in candidates.items():
        for direction, stock_list in dirs.items():
            for stock in stock_list:
                flat_candidates.append(asdict(stock))
                
    return freeze_morning_predictions(prediction_date, flat_candidates)

def generate_stock_dossier(symbol: str, score: ScoreBreakdown, signals: list, catalyst: dict, historical: dict) -> str:
    direction_text = 'POTENTIAL GAINER' if score.direction == 'BULLISH' else 'POTENTIAL LOSER'
    flags_text = ', '.join(score.risk_flags) if score.risk_flags else 'None'
    
    dossier = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{symbol}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Category: {score.cap_category}
Direction: {direction_text}
Score: {score.total_score}/100
Confidence: {score.confidence}

--- Component Breakdown ---
Catalyst: {score.catalyst_score}/20
Early Signals: {score.early_signal_score}/15
Volume & Delivery: {score.volume_delivery_score}/15
Price Momentum: {score.price_momentum_score}/10
Technical Structure: {score.technical_structure_score}/10
Sector Strength: {score.sector_strength_score}/10
Market Regime: {score.market_regime_score}/5
Historical Probability: {score.historical_probability_score}/10
Liquidity: {score.liquidity_score}/5
Risk Penalty: {score.risk_penalty}

Risk Flags: {flags_text}
"""
    return dossier

def run_premarket_pipeline() -> dict:
    init_db()
    
    stocks_data = []
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM master_universe WHERE is_active = 1")
        stocks_data = [dict(r) for r in cursor.fetchall()]
        
    scored_stocks = []
    for stock in stocks_data:
        # Pass minimal data for scoring. In a real system, you'd pull more data from features_daily etc.
        score = compute_composite_score(
            symbol=stock['symbol'],
            cap_category=stock.get('cap_category', 'LARGE'),
            avg_turnover_cr=stock.get('avg_turnover_cr_30d', 0.0),
            direction='BULLISH'  # mock direction
        )
        scored_stocks.append(score)
        
    matrix = rank_candidates(scored_stocks)
    
    prediction_date = date.today().strftime("%Y-%m-%d")
    freeze_meta = freeze_prediction(matrix, prediction_date)
    
    return {
        "status": "success",
        "freeze_metadata": freeze_meta,
        "matrix": matrix
    }
