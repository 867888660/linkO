"""
K线技术指标计算模块（通用）
适用于加密货币和股票的 OHLCV 数据
提取自 Crypto_Klines.py，供 Crypto_Klines 和 Finance_Klines 共用
"""
import logging
from typing import Dict, List, Optional

from crypto_klines_config import SIGNAL_CONFIG as _DEFAULT_SIGNAL_CONFIG
from klines_utils import calculate_atr_avg, calculate_std_dev, wilder_smooth, safe_divide

logger = logging.getLogger(__name__)


def _sma(data: List[float], period: int) -> List[Optional[float]]:
    result = [None] * len(data)
    if len(data) < period:
        return result
    for i in range(period - 1, len(data)):
        result[i] = sum(data[i - period + 1:i + 1]) / period
    return result


def _ema(data: List[float], period: int) -> List[Optional[float]]:
    result = [None] * len(data)
    if len(data) < period:
        return result
    result[period - 1] = sum(data[:period]) / period
    k = 2 / (period + 1)
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * k + result[i - 1]
    return result


def _macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)

    DIF = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            DIF[i] = ema_fast[i] - ema_slow[i]

    macd_vals = [v for v in DIF if v is not None]
    DEA = [None] * len(closes)
    if len(macd_vals) >= signal:
        start = next(i for i, v in enumerate(DIF) if v is not None)
        ema_sig = _ema(macd_vals, signal)
        for i, v in enumerate(ema_sig):
            if v is not None:
                DEA[start + i] = v

    hist = [None] * len(closes)
    for i in range(len(closes)):
        if DIF[i] is not None and DEA[i] is not None:
            hist[i] = DIF[i] - DEA[i]

    return DIF, DEA, hist


def _rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(0, change))
        losses.append(max(0, -change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

    return result


def _bollinger_bands(closes: List[float], period: int = 20, std_dev: float = 2.0):
    sma = _sma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        std = calculate_std_dev(closes[i - period + 1:i + 1], sma[i])
        upper[i] = sma[i] + std_dev * std
        lower[i] = sma[i] - std_dev * std
    return upper, sma, lower


def _adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14):
    if len(highs) < period + 1:
        n = len(highs)
        return [None] * n, [None] * n, [None] * n

    tr_list, plus_dm_list, minus_dm_list = [], [], []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        plus_dm_list.append(up if up > down and up > 0 else 0)
        minus_dm_list.append(down if down > up and down > 0 else 0)

    s_tr = wilder_smooth(tr_list, period)
    s_plus = wilder_smooth(plus_dm_list, period)
    s_minus = wilder_smooth(minus_dm_list, period)

    plus_di = [None] * len(closes)
    minus_di = [None] * len(closes)
    dx_list = []

    for i in range(len(s_tr)):
        if s_tr[i] is not None and s_tr[i] > 0:
            plus_di[i+1] = 100 * s_plus[i] / s_tr[i]
            minus_di[i+1] = 100 * s_minus[i] / s_tr[i]
            di_sum = plus_di[i+1] + minus_di[i+1]
            dx_list.append(100 * abs(plus_di[i+1] - minus_di[i+1]) / di_sum if di_sum > 0 else 0)
        else:
            dx_list.append(None)

    adx = [None] * len(closes)
    valid_dx = [x for x in dx_list if x is not None]
    if len(valid_dx) >= period:
        start = next(i for i, v in enumerate(dx_list) if v is not None)
        adx[start + period] = sum(valid_dx[:period]) / period
        for i in range(start + period + 1, len(closes)):
            dx_idx = i - 1
            if dx_idx < len(dx_list) and dx_list[dx_idx] is not None and adx[i-1] is not None:
                adx[i] = (adx[i-1] * (period - 1) + dx_list[dx_idx]) / period

    return adx, plus_di, minus_di


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    if len(highs) < 2:
        return [None] * len(highs)

    tr_list = [None]
    for i in range(1, len(closes)):
        tr_list.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))

    atr = [None] * len(closes)
    if len(tr_list) >= period + 1:
        atr[period] = sum(tr_list[1:period+1]) / period
        for i in range(period + 1, len(closes)):
            atr[i] = (atr[i-1] * (period - 1) + tr_list[i]) / period
    return atr


def _detect_market_regime(closes, volumes, adx, atr, bb_upper, bb_lower, bb_mid, sma50, signal_config=None) -> Dict:
    """市场状态分类：TRENDING_UP/DOWN, RANGING, VOLATILE"""
    config = (signal_config or _DEFAULT_SIGNAL_CONFIG)["regime"]
    conf = config["confidence"]

    if len(closes) < 50 or adx[-1] is None or atr[-1] is None:
        return {"regime": "INSUFFICIENT_DATA", "confidence": 0.0,
                "characteristics": {"trend_strength": 0, "volatility_level": 0, "volume_profile": "unknown"}}

    adx_value = adx[-1]
    atr_avg = calculate_atr_avg(atr, 20)
    atr_normalized = safe_divide(atr[-1], atr_avg, 1.0)

    if bb_upper[-1] is not None and bb_lower[-1] is not None:
        bb_width = bb_upper[-1] - bb_lower[-1]
        bb_widths = [bb_upper[i] - bb_lower[i] for i in range(max(0, len(bb_upper) - 20), len(bb_upper))
                     if bb_upper[i] is not None and bb_lower[i] is not None]
        bb_avg = sum(bb_widths) / len(bb_widths) if bb_widths else bb_width
        bb_norm = safe_divide(bb_width, bb_avg, 1.0)
    else:
        bb_norm = 1.0

    vol_th = config["volume_trend"]
    if len(volumes) >= 20:
        rv = sum(volumes[-5:]) / 5
        ev = sum(volumes[-20:-5]) / 15
        vr = safe_divide(rv, ev, 1.0)
        volume_profile = "increasing" if vr > vol_th["increasing"] else ("decreasing" if vr < vol_th["decreasing"] else "stable")
    else:
        volume_profile = "unknown"

    regime, confidence = "RANGING", 0.5
    t_th = config["trend_thresholds"]
    v_th = config["volatility_thresholds"]
    sma_short = bb_mid

    if adx_value > t_th["strong"]:
        if sma_short[-1] is not None and sma50[-1] is not None:
            if sma_short[-1] > sma50[-1]:
                regime = "TRENDING_UP"
            elif sma_short[-1] < sma50[-1]:
                regime = "TRENDING_DOWN"
            else:
                regime = "VOLATILE"
            confidence = min(1.0, conf["strong_trend_base"] + (adx_value - 25) * conf["strong_trend_slope"])
        else:
            regime, confidence = "VOLATILE", conf["volatile"]
    elif atr_normalized > v_th["high_atr"] or bb_norm > v_th["high_bb"]:
        regime, confidence = "VOLATILE", min(1.0, max(atr_normalized, bb_norm) / 2.0)
    elif adx_value < t_th["weak"]:
        regime, confidence = "RANGING", min(1.0, conf["ranging_base"] + (20 - adx_value) / conf["ranging_slope_divisor"])
    else:
        if sma_short[-1] is not None and sma50[-1] is not None and sma50[-1] > 0:
            if abs(sma_short[-1] - sma50[-1]) / sma50[-1] < config["sma_proximity"]:
                regime, confidence = "RANGING", conf["sma_converged"]
            else:
                regime = "TRENDING_UP" if sma_short[-1] > sma50[-1] else "TRENDING_DOWN"
                confidence = conf["weak_trend"]
        else:
            regime, confidence = "RANGING", conf["fallback"]

    return {
        "regime": regime, "confidence": round(confidence, 2),
        "characteristics": {
            "trend_strength": round(adx_value, 2),
            "volatility_level": round(atr_normalized, 2),
            "volume_profile": volume_profile
        }
    }
