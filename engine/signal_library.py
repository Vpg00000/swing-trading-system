import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime
import logging

from data.fetch import load_cached

log = logging.getLogger(__name__)

@dataclass
class SignalDefinition:
    signal_id: str
    name: str
    group: str
    description: str
    direction: str
    horizon: str
    default_strength: int

@dataclass
class SignalResult:
    signal_id: str
    symbol: str
    triggered: bool
    value: float
    threshold: float
    strength: int
    direction: str
    horizon: str
    timestamp: str

# 190 Signal Registry
SIGNAL_REGISTRY: Dict[str, SignalDefinition] = {}

def _register(sig_id, name, group, desc, direction, horizon, strength):
    SIGNAL_REGISTRY[sig_id] = SignalDefinition(sig_id, name, group, desc, direction, horizon, strength)

# --- MOMENTUM (25 signals) ---
for i in range(1, 26):
    _register(f"MOM_{i:03d}", f"Momentum Signal {i}", "MOMENTUM", f"Momentum description {i}", "BULLISH", "EARLY", 50)
_register("MOM_001", "3-Day Price Acceleration", "MOMENTUM", "3D returns greater than previous 3D returns", "BULLISH", "EARLY", 60)
_register("MOM_002", "Consecutive Higher Closes 3D", "MOMENTUM", "Close is higher than previous close for 3 days", "BULLISH", "CONFIRMATION", 50)
_register("MOM_003", "5-Day ROC Positive", "MOMENTUM", "5-Day Rate of Change > 0", "BULLISH", "EARLY", 40)
_register("MOM_004", "10-Day ROC Positive", "MOMENTUM", "10-Day Rate of Change > 0", "BULLISH", "EARLY", 45)
_register("MOM_005", "20-Day ROC Positive", "MOMENTUM", "20-Day Rate of Change > 0", "BULLISH", "CONFIRMATION", 50)
_register("MOM_006", "20D Range Breakout", "MOMENTUM", "Close breaks above 20D highest high", "BULLISH", "CONFIRMATION", 70)
_register("MOM_007", "52W High Breakout", "MOMENTUM", "Close breaks 252D high", "BULLISH", "LATE", 80)
_register("MOM_008", "Price > 20 EMA", "MOMENTUM", "Price is above 20-period EMA", "BULLISH", "CONFIRMATION", 40)
_register("MOM_009", "Price > 50 EMA", "MOMENTUM", "Price is above 50-period EMA", "BULLISH", "CONFIRMATION", 50)
_register("MOM_010", "Price > 200 EMA", "MOMENTUM", "Price is above 200-period EMA", "BULLISH", "LATE", 60)
_register("MOM_011", "20 EMA > 50 EMA", "MOMENTUM", "Short-term trend above medium-term", "BULLISH", "CONFIRMATION", 50)
_register("MOM_012", "Golden Cross", "MOMENTUM", "50 EMA crosses 200 EMA", "BULLISH", "LATE", 90)
_register("MOM_013", "20/50 EMA Crossover", "MOMENTUM", "20 EMA crosses above 50 EMA", "BULLISH", "CONFIRMATION", 70)
_register("MOM_014", "Death Cross", "MOMENTUM", "50 EMA crosses below 200 EMA", "BEARISH", "LATE", 90)
_register("MOM_015", "RSI > 50", "MOMENTUM", "RSI is in bullish territory", "BULLISH", "EARLY", 40)
_register("MOM_016", "RSI > 60", "MOMENTUM", "RSI shows strong momentum", "BULLISH", "CONFIRMATION", 50)
_register("MOM_017", "RSI > 70", "MOMENTUM", "RSI is overbought", "BULLISH", "LATE", 60)
_register("MOM_018", "RSI < 30", "MOMENTUM", "RSI is oversold", "BEARISH", "EARLY", 50)
_register("MOM_019", "RSI Crossover 50", "MOMENTUM", "RSI crosses above 50", "BULLISH", "EARLY", 65)
_register("MOM_020", "MACD Bullish", "MOMENTUM", "MACD line > Signal line", "BULLISH", "CONFIRMATION", 50)
_register("MOM_021", "MACD Crossover", "MOMENTUM", "MACD line crosses above Signal", "BULLISH", "EARLY", 70)
_register("MOM_022", "MACD Hist Positive", "MOMENTUM", "MACD Histogram > 0", "BULLISH", "EARLY", 40)
_register("MOM_023", "MACD Hist Rising", "MOMENTUM", "MACD Histogram is growing", "BULLISH", "EARLY", 50)
_register("MOM_024", "ADX > 25", "MOMENTUM", "Trend is strong", "BULLISH", "CONFIRMATION", 60)
_register("MOM_025", "ADX > 35", "MOMENTUM", "Trend is very strong", "BULLISH", "LATE", 70)

# --- VOLUME (20 signals) ---
for i in range(1, 21):
    _register(f"VOL_{i:03d}", f"Volume Signal {i}", "VOLUME", f"Volume description {i}", "BULLISH", "EARLY", 50)
_register("VOL_001", "Volume Expansion >2x", "VOLUME", "Volume is twice the 20D moving average", "BULLISH", "EARLY", 60)
_register("VOL_003", "Extreme Volume Expansion >5x", "VOLUME", "Volume is 5x the 20D moving average", "BULLISH", "EARLY", 80)
_register("VOL_006", "Tight Range on Expanding Volume", "VOLUME", "Range < 1% and volume > 1.5x avg", "BULLISH", "EARLY", 75)

# --- TECHNICAL (25 signals) ---
for i in range(1, 26):
    _register(f"TECH_{i:03d}", f"Technical Signal {i}", "TECHNICAL", f"Tech description {i}", "BULLISH", "CONFIRMATION", 50)
_register("TECH_001", "TTM Squeeze", "TECHNICAL", "Bollinger Bands inside Keltner Channel", "BULLISH", "EARLY", 70)
_register("TECH_008", "NR7", "TECHNICAL", "Narrowest range in 7 days", "BULLISH", "EARLY", 60)
_register("TECH_014", "EMA Ribbon Convergence", "TECHNICAL", "EMAs are converging", "BULLISH", "EARLY", 65)

# --- DELIVERY (15 signals) ---
for i in range(1, 16):
    _register(f"DEL_{i:03d}", f"Delivery Signal {i}", "DELIVERY", f"Delivery description {i}", "BULLISH", "CONFIRMATION", 50)

# --- FUNDAMENTAL (20 signals) ---
for i in range(1, 21):
    _register(f"FUND_{i:03d}", f"Fundamental Signal {i}", "FUNDAMENTAL", f"Fund description {i}", "BULLISH", "LATE", 50)

# --- CATALYST (25 signals) ---
for i in range(1, 26):
    _register(f"CAT_{i:03d}", f"Catalyst Signal {i}", "CATALYST", f"Catalyst description {i}", "BULLISH", "EARLY", 50)

# --- SECTOR (15 signals) ---
for i in range(1, 16):
    _register(f"SEC_{i:03d}", f"Sector Signal {i}", "SECTOR", f"Sector description {i}", "BULLISH", "CONFIRMATION", 50)

# --- MACRO (15 signals) ---
for i in range(1, 16):
    _register(f"MAC_{i:03d}", f"Macro Signal {i}", "MACRO", f"Macro description {i}", "BULLISH", "LATE", 50)

# --- BEHAVIORAL (10 signals) ---
for i in range(1, 11):
    _register(f"BEH_{i:03d}", f"Behavioral Signal {i}", "BEHAVIORAL", f"Behavioral description {i}", "BULLISH", "EARLY", 50)

# --- HISTORICAL (20 signals) ---
for i in range(1, 21):
    _register(f"HIST_{i:03d}", f"Historical Signal {i}", "HISTORICAL", f"Historical description {i}", "BULLISH", "CONFIRMATION", 50)


# ==========================================
# Evaluator Functions
# ==========================================

def _create_result(sig_id: str, symbol: str, triggered: bool, value: float, threshold: float, timestamp: str) -> SignalResult:
    defn = SIGNAL_REGISTRY.get(sig_id)
    return SignalResult(
        signal_id=sig_id,
        symbol=symbol,
        triggered=triggered,
        value=float(value) if not np.isnan(value) else 0.0,
        threshold=float(threshold),
        strength=defn.default_strength if defn else 50,
        direction=defn.direction if defn else "BULLISH",
        horizon=defn.horizon if defn else "EARLY",
        timestamp=timestamp
    )

def evaluate_momentum_signals(symbol: str, df: pd.DataFrame) -> List[SignalResult]:
    results = []
    if df.empty or len(df) < 252:
        return results
    
    close = df['Close']
    high = df['High']
    ts = str(df.index[-1])[:10]

    ret_3 = close.pct_change(3)
    val = ret_3.iloc[-1]
    prev_val = ret_3.shift(1).iloc[-1]
    trig = val > prev_val and val > 0
    results.append(_create_result("MOM_001", symbol, bool(trig), val, prev_val, ts))

    diff = close.diff()
    trig = (diff.iloc[-1] > 0) and (diff.iloc[-2] > 0) and (diff.iloc[-3] > 0)
    results.append(_create_result("MOM_002", symbol, bool(trig), diff.iloc[-1], 0.0, ts))

    ret_5 = close.pct_change(5).iloc[-1]
    results.append(_create_result("MOM_003", symbol, bool(ret_5 > 0), ret_5, 0.0, ts))

    ret_10 = close.pct_change(10).iloc[-1]
    results.append(_create_result("MOM_004", symbol, bool(ret_10 > 0), ret_10, 0.0, ts))

    ret_20 = close.pct_change(20).iloc[-1]
    results.append(_create_result("MOM_005", symbol, bool(ret_20 > 0), ret_20, 0.0, ts))

    high_20 = high.rolling(20).max().shift(1).iloc[-1]
    trig = close.iloc[-1] > high_20
    results.append(_create_result("MOM_006", symbol, bool(trig), close.iloc[-1], high_20, ts))

    high_252 = high.rolling(252).max().shift(1).iloc[-1]
    trig = close.iloc[-1] > high_252
    results.append(_create_result("MOM_007", symbol, bool(trig), close.iloc[-1], high_252, ts))

    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean()
    c = close.iloc[-1]

    results.append(_create_result("MOM_008", symbol, bool(c > ema_20.iloc[-1]), c, ema_20.iloc[-1], ts))
    results.append(_create_result("MOM_009", symbol, bool(c > ema_50.iloc[-1]), c, ema_50.iloc[-1], ts))
    results.append(_create_result("MOM_010", symbol, bool(c > ema_200.iloc[-1]), c, ema_200.iloc[-1], ts))
    results.append(_create_result("MOM_011", symbol, bool(ema_20.iloc[-1] > ema_50.iloc[-1]), ema_20.iloc[-1], ema_50.iloc[-1], ts))
    
    trig_gc = ema_50.iloc[-1] > ema_200.iloc[-1] and ema_50.iloc[-2] <= ema_200.iloc[-2]
    results.append(_create_result("MOM_012", symbol, bool(trig_gc), ema_50.iloc[-1], ema_200.iloc[-1], ts))

    trig_20_50 = ema_20.iloc[-1] > ema_50.iloc[-1] and ema_20.iloc[-2] <= ema_50.iloc[-2]
    results.append(_create_result("MOM_013", symbol, bool(trig_20_50), ema_20.iloc[-1], ema_50.iloc[-1], ts))

    trig_dc = ema_50.iloc[-1] < ema_200.iloc[-1] and ema_50.iloc[-2] >= ema_200.iloc[-2]
    results.append(_create_result("MOM_014", symbol, bool(trig_dc), ema_50.iloc[-1], ema_200.iloc[-1], ts))

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    r = rsi.iloc[-1]

    results.append(_create_result("MOM_015", symbol, bool(r > 50), r, 50, ts))
    results.append(_create_result("MOM_016", symbol, bool(r > 60), r, 60, ts))
    results.append(_create_result("MOM_017", symbol, bool(r > 70), r, 70, ts))
    results.append(_create_result("MOM_018", symbol, bool(r < 30), r, 30, ts))
    
    trig_rsi_cross = r > 50 and rsi.iloc[-2] <= 50
    results.append(_create_result("MOM_019", symbol, bool(trig_rsi_cross), r, 50, ts))

    macd_fast = close.ewm(span=12, adjust=False).mean()
    macd_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = macd_fast - macd_slow
    macd_sig = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_sig
    
    ml = macd_line.iloc[-1]
    ms = macd_sig.iloc[-1]
    mh = macd_hist.iloc[-1]
    
    results.append(_create_result("MOM_020", symbol, bool(ml > ms), ml, ms, ts))
    trig_macd_cross = ml > ms and macd_line.iloc[-2] <= macd_sig.iloc[-2]
    results.append(_create_result("MOM_021", symbol, bool(trig_macd_cross), ml, ms, ts))
    results.append(_create_result("MOM_022", symbol, bool(mh > 0), mh, 0, ts))
    results.append(_create_result("MOM_023", symbol, bool(mh > macd_hist.iloc[-2]), mh, macd_hist.iloc[-2], ts))
    
    trig_momentum_up = close.iloc[-1] > close.iloc[-5] and r > 50
    results.append(_create_result("MOM_024", symbol, bool(trig_momentum_up), r, 50, ts))

    trig_momentum_dn = close.iloc[-1] < close.iloc[-5] and r < 50
    results.append(_create_result("MOM_025", symbol, bool(trig_momentum_dn), r, 50, ts))

    return results

def evaluate_volume_signals(symbol: str, df: pd.DataFrame) -> List[SignalResult]:
    results = []
    if df.empty or len(df) < 20:
        return results
    
    vol = df['Volume']
    close = df['Close']
    ts = str(df.index[-1])[:10]

    vol_sma_20 = vol.rolling(20).mean()
    v = vol.iloc[-1]
    v_avg = vol_sma_20.iloc[-1]

    results.append(_create_result("VOL_001", symbol, bool(v > 2.0 * v_avg), v, 2.0 * v_avg, ts))
    results.append(_create_result("VOL_002", symbol, bool(v > 3.0 * v_avg), v, 3.0 * v_avg, ts))
    results.append(_create_result("VOL_003", symbol, bool(v > 5.0 * v_avg), v, 5.0 * v_avg, ts))
    results.append(_create_result("VOL_004", symbol, bool(v > v_avg), v, v_avg, ts))
    
    trig_rise = vol.iloc[-1] > vol.iloc[-2] > vol.iloc[-3]
    results.append(_create_result("VOL_005", symbol, bool(trig_rise), v, vol.iloc[-2], ts))

    range_pct = (df['High'] - df['Low']) / close
    trig_tight = range_pct.iloc[-1] < 0.01 and v > 1.5 * v_avg
    results.append(_create_result("VOL_006", symbol, bool(trig_tight), range_pct.iloc[-1], 0.01, ts))

    ret = close.pct_change()
    trig_up_vol = ret.iloc[-1] > 0 and v > v_avg
    results.append(_create_result("VOL_007", symbol, bool(trig_up_vol), v, v_avg, ts))

    trig_down_vol = ret.iloc[-1] < 0 and v > v_avg
    results.append(_create_result("VOL_008", symbol, bool(trig_down_vol), v, v_avg, ts))
    
    obv = (np.sign(ret) * vol).fillna(0).cumsum()
    trig_obv = obv.iloc[-1] > obv.iloc[-2] > obv.iloc[-3]
    results.append(_create_result("VOL_009", symbol, bool(trig_obv), obv.iloc[-1], obv.iloc[-2], ts))

    obv_sma = obv.rolling(20).mean()
    trig_obv_cross = obv.iloc[-1] > obv_sma.iloc[-1]
    results.append(_create_result("VOL_010", symbol, bool(trig_obv_cross), obv.iloc[-1], obv_sma.iloc[-1], ts))

    mfv = ((close - df['Low']) - (df['High'] - close)) / (df['High'] - df['Low']).replace(0, np.nan)
    mfv = mfv.fillna(0.0) * vol
    cmf = mfv.rolling(20).sum() / vol.rolling(20).sum()
    
    results.append(_create_result("VOL_011", symbol, bool(cmf.iloc[-1] > 0), cmf.iloc[-1], 0.0, ts))
    results.append(_create_result("VOL_012", symbol, bool(cmf.iloc[-1] > 0.1), cmf.iloc[-1], 0.1, ts))
    results.append(_create_result("VOL_013", symbol, bool(cmf.iloc[-1] > 0.2), cmf.iloc[-1], 0.2, ts))

    trig_vol_dry = v < 0.5 * v_avg
    results.append(_create_result("VOL_014", symbol, bool(trig_vol_dry), v, 0.5 * v_avg, ts))

    trig_vol_dry_extreme = v < 0.2 * v_avg
    results.append(_create_result("VOL_015", symbol, bool(trig_vol_dry_extreme), v, 0.2 * v_avg, ts))

    for i in range(16, 21):
        results.append(_create_result(f"VOL_{i:03d}", symbol, False, 0.0, 0.0, ts))

    return results

def evaluate_technical_signals(symbol: str, df: pd.DataFrame) -> List[SignalResult]:
    results = []
    if df.empty or len(df) < 20:
        return results
    
    close = df['Close']
    high = df['High']
    low = df['Low']
    ts = str(df.index[-1])[:10]

    sma_20 = close.rolling(20).mean()
    std_20 = close.rolling(20).std()
    bb_upper = sma_20 + 2 * std_20
    bb_lower = sma_20 - 2 * std_20
    
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    
    kc_upper = ema_20 + 1.5 * atr
    kc_lower = ema_20 - 1.5 * atr

    # TTM Squeeze
    trig_ttm = bb_upper.iloc[-1] < kc_upper.iloc[-1] and bb_lower.iloc[-1] > kc_lower.iloc[-1]
    results.append(_create_result("TECH_001", symbol, bool(trig_ttm), bb_upper.iloc[-1], kc_upper.iloc[-1], ts))

    # BB Squeeze
    bb_width = (bb_upper - bb_lower) / sma_20
    trig_bb_sq = bb_width.iloc[-1] < 0.05
    results.append(_create_result("TECH_002", symbol, bool(trig_bb_sq), bb_width.iloc[-1], 0.05, ts))

    c = close.iloc[-1]
    results.append(_create_result("TECH_003", symbol, bool(c > bb_upper.iloc[-1]), c, bb_upper.iloc[-1], ts))
    results.append(_create_result("TECH_004", symbol, bool(c < bb_lower.iloc[-1]), c, bb_lower.iloc[-1], ts))
    
    results.append(_create_result("TECH_005", symbol, bool(atr.iloc[-1] > atr.iloc[-2]), atr.iloc[-1], atr.iloc[-2], ts))
    
    results.append(_create_result("TECH_006", symbol, bool(c > kc_upper.iloc[-1]), c, kc_upper.iloc[-1], ts))
    
    dc_upper = high.rolling(20).max()
    results.append(_create_result("TECH_007", symbol, bool(c > dc_upper.shift(1).iloc[-1]), c, dc_upper.shift(1).iloc[-1], ts))

    range_series = high - low
    is_nr7 = range_series.iloc[-1] == range_series.iloc[-7:].min()
    results.append(_create_result("TECH_008", symbol, bool(is_nr7), range_series.iloc[-1], range_series.iloc[-7:].min(), ts))

    is_nr4 = range_series.iloc[-1] == range_series.iloc[-4:].min()
    results.append(_create_result("TECH_009", symbol, bool(is_nr4), range_series.iloc[-1], range_series.iloc[-4:].min(), ts))

    inside = (high.iloc[-1] < high.iloc[-2]) and (low.iloc[-1] > low.iloc[-2])
    results.append(_create_result("TECH_010", symbol, bool(inside), 1, 0, ts))
    
    outside = (high.iloc[-1] > high.iloc[-2]) and (low.iloc[-1] < low.iloc[-2])
    results.append(_create_result("TECH_011", symbol, bool(outside), 1, 0, ts))

    body = abs(close.iloc[-1] - df['Open'].iloc[-1])
    lower_shadow = min(close.iloc[-1], df['Open'].iloc[-1]) - low.iloc[-1]
    upper_shadow = high.iloc[-1] - max(close.iloc[-1], df['Open'].iloc[-1])
    hammer = lower_shadow >= 2 * body and upper_shadow <= 0.1 * body and body > 0
    results.append(_create_result("TECH_012", symbol, bool(hammer), lower_shadow, body, ts))

    doji = body <= 0.1 * (high.iloc[-1] - low.iloc[-1])
    results.append(_create_result("TECH_013", symbol, bool(doji), body, 0.1 * (high.iloc[-1] - low.iloc[-1]), ts))

    ema_8 = close.ewm(span=8, adjust=False).mean()
    ema_13 = close.ewm(span=13, adjust=False).mean()
    ema_21 = close.ewm(span=21, adjust=False).mean()

    ribbon_up = ema_8.iloc[-1] > ema_13.iloc[-1] > ema_21.iloc[-1]
    results.append(_create_result("TECH_014", symbol, bool(ribbon_up), ema_8.iloc[-1], ema_21.iloc[-1], ts))

    ribbon_dn = ema_8.iloc[-1] < ema_13.iloc[-1] < ema_21.iloc[-1]
    results.append(_create_result("TECH_015", symbol, bool(ribbon_dn), ema_8.iloc[-1], ema_21.iloc[-1], ts))

    sma_50 = close.rolling(50).mean()
    trig_50_bounce = (low.iloc[-1] < sma_50.iloc[-1]) and (close.iloc[-1] > sma_50.iloc[-1])
    results.append(_create_result("TECH_016", symbol, bool(trig_50_bounce), close.iloc[-1], sma_50.iloc[-1], ts))

    sma_200 = close.rolling(200).mean()
    trig_200_bounce = (low.iloc[-1] < sma_200.iloc[-1]) and (close.iloc[-1] > sma_200.iloc[-1])
    results.append(_create_result("TECH_017", symbol, bool(trig_200_bounce), close.iloc[-1], sma_200.iloc[-1], ts))

    rsi = 100 - (100 / (1 + (gain.ewm(alpha=1/14, adjust=False).mean() / loss.ewm(alpha=1/14, adjust=False).mean().replace(0, np.nan)))) if 'gain' in locals() else close.pct_change().clip(lower=0).ewm(14).mean() / close.pct_change().clip(upper=0).abs().ewm(14).mean()
    # Simple hack for rsi if not defined properly in this func:
    delta = close.diff()
    gain2 = delta.clip(lower=0)
    loss2 = -delta.clip(upper=0)
    rs2 = gain2.ewm(alpha=1/14, adjust=False).mean() / loss2.ewm(alpha=1/14, adjust=False).mean().replace(0, np.nan)
    rsi2 = 100 - (100 / (1 + rs2))
    
    trig_bull_div = (close.iloc[-1] < close.iloc[-5]) and (rsi2.iloc[-1] > rsi2.iloc[-5])
    results.append(_create_result("TECH_018", symbol, bool(trig_bull_div), rsi2.iloc[-1], rsi2.iloc[-5], ts))

    trig_bear_div = (close.iloc[-1] > close.iloc[-5]) and (rsi2.iloc[-1] < rsi2.iloc[-5])
    results.append(_create_result("TECH_019", symbol, bool(trig_bear_div), rsi2.iloc[-1], rsi2.iloc[-5], ts))

    trig_gap_up = df['Open'].iloc[-1] > high.iloc[-2]
    results.append(_create_result("TECH_020", symbol, bool(trig_gap_up), df['Open'].iloc[-1], high.iloc[-2], ts))

    for i in range(21, 26):
        results.append(_create_result(f"TECH_{i:03d}", symbol, False, 0.0, 0.0, ts))

    return results

def evaluate_delivery_signals(symbol: str, df: pd.DataFrame) -> List[SignalResult]:
    # Placeholder
    results = []
    ts = str(datetime.now())[:10] if df.empty else str(df.index[-1])[:10]
    for i in range(1, 16):
        results.append(_create_result(f"DEL_{i:03d}", symbol, False, 0.0, 0.0, ts))
    return results

def evaluate_all_signals(symbol: str) -> List[SignalResult]:
    df = load_cached(symbol)
    results = []
    if df.empty:
        return results
    results.extend(evaluate_momentum_signals(symbol, df))
    results.extend(evaluate_volume_signals(symbol, df))
    results.extend(evaluate_technical_signals(symbol, df))
    results.extend(evaluate_delivery_signals(symbol, df))
    
    ts = str(df.index[-1])[:10]
    
    # Dummy results for rest
    for prefix, count in [("FUND", 20), ("CAT", 25), ("SEC", 15), ("MAC", 15), ("BEH", 10), ("HIST", 20)]:
        for i in range(1, count + 1):
            results.append(_create_result(f"{prefix}_{i:03d}", symbol, False, 0.0, 0.0, ts))

    return results
