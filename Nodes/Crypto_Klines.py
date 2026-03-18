import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from crypto_klines_config import INDICATOR_CONFIG, SIGNAL_CONFIG, HTTP_CONFIG
from crypto_klines_utils import calculate_atr_avg, calculate_std_dev, wilder_smooth, safe_divide, format_float
from crypto_klines_signals import generate_signals

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =========================
# Node metadata
# =========================
OutPutNum = 1
InPutNum = 3

Outputs = [{
    "Num": None,
    "Kind": None,
    "Boolean": False,
    "Id": "Output1",
    "Context": None,
    "name": "Result",
    "Link": 0,
    "Description": "K线数据JSON，包含OHLCV和技术指标"
} for _ in range(OutPutNum)]

Inputs = [
    {"Num": None, "Kind": "String", "Id": "Input1", "Context": None, "name": "Symbol", "Link": 0, "IsLabel": True, "Isnecessary": True},
    {"Num": None, "Kind": "String", "Id": "Input2", "Context": "1d", "name": "Interval", "Link": 0, "IsLabel": True, "Isnecessary": False},
    {"Num": 60, "Kind": "Num", "Id": "Input3", "Context": None, "name": "Limit", "Link": 0, "IsLabel": True, "Isnecessary": False},
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

for o in Outputs:
    o['Kind'] = 'String'

FunctionIntroduction = (
    "组件功能\n"
    "加密货币K线数据抓取与技术指标分析节点：从 Binance Spot API 获取历史K线，"
    "计算核心技术指标（EMA、MACD、RSI、ADX、ATR），"
    "输出趋势+动量双通道加权信号系统的量化分析JSON。\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: Symbol\n    type: string\n    required: true\n    description: 交易对，如 BTCUSDT\n"
    "  - name: Interval\n    type: string\n    default: 1d\n    description: K线周期\n"
    "  - name: Limit\n    type: number\n    default: 60\n    description: K线数量（最多1000）\n"
    "outputs:\n"
    "  - name: Result\n    type: string\n    description: JSON，含技术指标+加权信号系统\n```"
)

# =========================
# HTTP session
# =========================
def _make_session() -> requests.Session:
    s = requests.Session()
    rc = HTTP_CONFIG["retries"]
    retry = Retry(
        total=rc["total"], connect=rc["total"], read=rc["total"], status=rc["total"],
        backoff_factor=rc["backoff_factor"], status_forcelist=rc["status_forcelist"],
        allowed_methods=frozenset(["GET", "POST"]), raise_on_status=False,
    )
    pc = HTTP_CONFIG["pool"]
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pc["connections"], pool_maxsize=pc["maxsize"])
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

_SESS = _make_session()

# =========================
# Technical Indicators
# =========================
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
    """布林带 — 仅用于市场状态分类（BB宽度），不产生交易信号"""
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

# =========================
# 市场状态分类
# =========================
def _detect_market_regime(closes, volumes, adx, atr, bb_upper, bb_lower, bb_mid, sma50) -> Dict:
    """市场状态分类：TRENDING_UP/DOWN, RANGING, VOLATILE"""
    config = SIGNAL_CONFIG["regime"]
    conf = config["confidence"]

    if len(closes) < 50 or adx[-1] is None or atr[-1] is None:
        return {"regime": "INSUFFICIENT_DATA", "confidence": 0.0,
                "characteristics": {"trend_strength": 0, "volatility_level": 0, "volume_profile": "unknown"}}

    adx_value = adx[-1]
    atr_avg = calculate_atr_avg(atr, 20)
    atr_normalized = safe_divide(atr[-1], atr_avg, 1.0)

    # BB宽度标准化
    if bb_upper[-1] is not None and bb_lower[-1] is not None:
        bb_width = bb_upper[-1] - bb_lower[-1]
        bb_widths = [bb_upper[i] - bb_lower[i] for i in range(max(0, len(bb_upper) - 20), len(bb_upper))
                     if bb_upper[i] is not None and bb_lower[i] is not None]
        bb_avg = sum(bb_widths) / len(bb_widths) if bb_widths else bb_width
        bb_norm = safe_divide(bb_width, bb_avg, 1.0)
    else:
        bb_norm = 1.0

    # 成交量趋势
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

# =========================
# Binance API
# =========================
def _binance_base_url() -> str:
    return os.getenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com").rstrip("/")

def _fetch_klines(symbol: str, interval: str, limit: int, dbg: List[str]) -> List[Dict]:
    url = _binance_base_url() + "/api/v3/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1000)}

    try:
        resp = _SESS.get(url, params=params, timeout=float(os.getenv("HTTP_TIMEOUT", str(HTTP_CONFIG["timeout"]))))
        if resp.status_code != 200:
            dbg.append(f"Binance klines failed: status={resp.status_code}")
            return []
        data = resp.json()
        if not isinstance(data, list):
            dbg.append(f"Unexpected response type: {type(data)}")
            return []
        return [{
            "open_time": k[0], "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
            "close_time": k[6], "quote_volume": float(k[7]), "trades": k[8],
        } for k in data]
    except Exception as e:
        dbg.append(f"Binance klines exception: {repr(e)}")
        return []

# =========================
# Main
# =========================
def run_node(node):
    dbg = []
    t0 = time.time()

    # 解析输入
    symbol_raw = node['Inputs'][0].get('Context')
    if not symbol_raw or not symbol_raw.strip():
        result = {"ok": False, "error": "Symbol is required (e.g., BTCUSDT)", "debug": ["Missing Symbol"]}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs

    symbol = symbol_raw.strip().upper()
    interval = (node['Inputs'][1].get('Context') or "1d").strip().lower()
    limit = node['Inputs'][2].get('Num') or 60
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 60

    valid_intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
    if interval not in valid_intervals:
        interval = "1d"

    dbg.append(f"Fetching {symbol} {interval} klines, limit={limit}")

    # 获取K线
    klines = _fetch_klines(symbol, interval, limit, dbg)
    if not klines:
        result = {"ok": False, "error": "Failed to fetch klines", "debug": dbg, "symbol": symbol, "interval": interval}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    # 计算技术指标
    DIF, DEA, hist = _macd(closes, **INDICATOR_CONFIG["macd"])
    rsi = _rsi(closes, **INDICATOR_CONFIG["rsi"])
    sma50 = _sma(closes, INDICATOR_CONFIG["sma"]["periods"][0])
    ema9 = _ema(closes, INDICATOR_CONFIG["ema"]["periods"][0])
    ema21 = _ema(closes, INDICATOR_CONFIG["ema"]["periods"][1])
    bb_upper, bb_mid, bb_lower = _bollinger_bands(closes, **INDICATOR_CONFIG["bollinger"])
    adx, plus_di, minus_di = _adx(highs, lows, closes, INDICATOR_CONFIG["adx"]["period"])
    atr = _atr(highs, lows, closes, INDICATOR_CONFIG["atr"]["period"])

    # 市场状态
    market_regime = _detect_market_regime(closes, volumes, adx, atr, bb_upper, bb_lower, bb_mid, sma50)

    # 生成信号（精简版：只传核心指标）
    signals = generate_signals(
        closes, DIF, DEA, hist, rsi, ema9, ema21,
        adx, atr, market_regime
    )

    # 统计
    price_high = max(highs)
    price_low = min(lows)
    avg_vol = sum(volumes) / len(volumes) if volumes else 0

    result = {
        "ok": True,
        "symbol": symbol,
        "interval": interval,
        "kline_count": len(klines),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "latency_ms": int((time.time() - t0) * 1000),

        "current": {
            "price": closes[-1],
            "open": klines[-1]["open"],
            "high": klines[-1]["high"],
            "low": klines[-1]["low"],
            "volume": klines[-1]["volume"],
        },

        "period_stats": {
            "high": price_high,
            "low": price_low,
            "range_pct": round(safe_divide(price_high - price_low, price_low, 0) * 100, 2),
            "avg_volume": round(avg_vol, 2),
            "start_price": closes[0],
            "end_price": closes[-1],
            "period_change_pct": round(safe_divide(closes[-1] - closes[0], closes[0], 0) * 100, 2),
        },

        "indicators": {
            "ema9": format_float(ema9[-1], 4),
            "ema21": format_float(ema21[-1], 4),
            "ema55": None,
            "sma20": format_float(bb_mid[-1], 4),
            "sma50": format_float(sma50[-1], 4),
            "macd": format_float(DIF[-1], 6),
            "macd_signal": format_float(DEA[-1], 6),
            "macd_histogram": format_float(hist[-1], 6),
            "rsi": format_float(rsi[-1], 2),
            "adx": format_float(adx[-1], 2),
            "plus_di": format_float(plus_di[-1], 2),
            "minus_di": format_float(minus_di[-1], 2),
            "atr": format_float(atr[-1], 6),
            "bb_upper": format_float(bb_upper[-1], 4),
            "bb_mid": format_float(bb_mid[-1], 4),
            "bb_lower": format_float(bb_lower[-1], 4),
            "obv": None,
        },

        "signals": signals,
        "recent_klines": klines[-5:],
        "debug": dbg
    }

    logger.info(f"Processed {symbol} {interval}, signal_score={signals['signal_score']}, confidence={signals['confidence']}")
    Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
    return Outputs
