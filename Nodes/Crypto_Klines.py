import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    {"Num": None, "Kind": "Num", "Id": "Input3", "Context": None, "Num": 60, "name": "Limit", "Link": 0, "IsLabel": True, "Isnecessary": False},
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

for o in Outputs:
    o['Kind'] = 'String'

FunctionIntroduction = (
    "组件功能（简述代码整体功能）\n"
    "这是一个加密货币K线数据抓取与技术指标计算节点：从 Binance Spot REST API 获取历史K线数据，"
    "并计算常用技术指标（MACD、RSI、SMA、EMA、布林带等），输出包含完整量化信号的JSON字符串。\n\n"
    "代码功能摘要（概括核心算法或主要处理步骤）\n"
    "1. 调用 Binance /api/v3/klines 获取指定交易对的历史K线\n"
    "2. 计算技术指标：MACD(12,26,9)、RSI(14)、SMA(20,50)、EMA(12,26)、布林带(20,2)\n"
    "3. 生成量化信号：趋势方向、MACD金叉/死叉、RSI超买/超卖、价格与均线关系\n"
    "4. 输出结构化JSON，供下游LLM判定员使用\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: Symbol\n    type: string\n    required: true\n    description: 交易对，如 BTCUSDT、ETHUSDT\n"
    "  - name: Interval\n    type: string\n    required: false\n    default: 1d\n    description: K线周期，支持 1m/5m/15m/1h/4h/1d/1w\n"
    "  - name: Limit\n    type: number\n    required: false\n    default: 60\n    description: 获取K线数量（最多1000）\n"
    "outputs:\n"
    "  - name: Result\n    type: string\n    description: JSON字符串，包含K线数据、技术指标、量化信号\n```\n"
    "\n运行逻辑\n"
    "- 解析输入的交易对Symbol、周期Interval、数量Limit\n"
    "- 调用 Binance /api/v3/klines 获取OHLCV数据\n"
    "- 计算技术指标：MACD、RSI、SMA、EMA、布林带\n"
    "- 生成量化信号和趋势判断\n"
    "- 组装输出JSON并返回"
)

# =========================
# HTTP session with retries
# =========================
def _make_session() -> requests.Session:
    s = requests.Session()
    total = int(os.getenv("HTTP_RETRIES", "3"))
    backoff = float(os.getenv("HTTP_BACKOFF", "0.4"))
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

_SESS = _make_session()

# =========================
# Technical Indicators
# =========================
def _sma(data: List[float], period: int) -> List[Optional[float]]:
    """简单移动平均"""
    result = [None] * len(data)
    for i in range(period - 1, len(data)):
        result[i] = sum(data[i - period + 1:i + 1]) / period
    return result

def _ema(data: List[float], period: int) -> List[Optional[float]]:
    """指数移动平均"""
    result = [None] * len(data)
    if len(data) < period:
        return result
    
    # 第一个EMA用SMA初始化
    sma_first = sum(data[:period]) / period
    result[period - 1] = sma_first
    
    multiplier = 2 / (period + 1)
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    
    return result

def _macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """MACD指标"""
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    
    macd_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]
    
    # 计算信号线（MACD的EMA）
    macd_values = [v for v in macd_line if v is not None]
    signal_line = [None] * len(closes)
    
    if len(macd_values) >= signal:
        start_idx = next(i for i, v in enumerate(macd_line) if v is not None)
        ema_signal = _ema(macd_values, signal)
        for i, v in enumerate(ema_signal):
            if v is not None:
                signal_line[start_idx + i] = v
    
    # 计算柱状图
    histogram = [None] * len(closes)
    for i in range(len(closes)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]
    
    return macd_line, signal_line, histogram

def _rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """RSI指标"""
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result
    
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    # 第一个RSI
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        result[period] = 100
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))
    
    # 后续RSI（平滑）
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            result[i + 1] = 100
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100 - (100 / (1 + rs))
    
    return result

def _bollinger_bands(closes: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """布林带"""
    sma = _sma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        std = (sum((x - sma[i]) ** 2 for x in window) / period) ** 0.5
        upper[i] = sma[i] + std_dev * std
        lower[i] = sma[i] - std_dev * std
    
    return upper, sma, lower

# =========================
# Binance API
# =========================
def _binance_base_url() -> str:
    return os.getenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com").rstrip("/")

def _http_timeout() -> float:
    return float(os.getenv("HTTP_TIMEOUT", "15"))

def _fetch_klines(symbol: str, interval: str, limit: int, dbg: List[str]) -> List[Dict]:
    """获取K线数据"""
    url = _binance_base_url() + "/api/v3/klines"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": min(limit, 1000)
    }
    
    try:
        resp = _SESS.get(url, params=params, timeout=_http_timeout())
        if resp.status_code != 200:
            dbg.append(f"Binance klines failed: status={resp.status_code}")
            return []
        
        data = resp.json()
        if not isinstance(data, list):
            dbg.append(f"Unexpected klines response type: {type(data)}")
            return []
        
        klines = []
        for k in data:
            klines.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
                "quote_volume": float(k[7]),
                "trades": k[8],
            })
        return klines
    
    except Exception as e:
        dbg.append(f"Binance klines exception: {repr(e)}")
        return []

def _generate_signals(closes: List[float], macd_line: List, signal_line: List, histogram: List, rsi: List, sma20: List, sma50: List, bb_upper: List, bb_lower: List) -> Dict:
    """生成量化信号"""
    if len(closes) < 2:
        return {"error": "数据不足"}
    
    current_price = closes[-1]
    prev_price = closes[-2]
    
    signals = {
        "current_price": round(current_price, 4),
        "price_change_24h": round((current_price - prev_price) / prev_price * 100, 2) if prev_price else 0,
    }
    
    # MACD信号
    if macd_line[-1] is not None and signal_line[-1] is not None:
        signals["macd"] = round(macd_line[-1], 4)
        signals["macd_signal"] = round(signal_line[-1], 4)
        signals["macd_histogram"] = round(histogram[-1], 4) if histogram[-1] else 0
        
        # 金叉/死叉判断
        if macd_line[-2] is not None and signal_line[-2] is not None:
            prev_diff = macd_line[-2] - signal_line[-2]
            curr_diff = macd_line[-1] - signal_line[-1]
            if prev_diff < 0 and curr_diff > 0:
                signals["macd_cross"] = "golden_cross"  # 金叉
            elif prev_diff > 0 and curr_diff < 0:
                signals["macd_cross"] = "death_cross"  # 死叉
            else:
                signals["macd_cross"] = "none"
        
        signals["macd_trend"] = "bullish" if macd_line[-1] > signal_line[-1] else "bearish"
    
    # RSI信号
    if rsi[-1] is not None:
        signals["rsi"] = round(rsi[-1], 2)
        if rsi[-1] > 70:
            signals["rsi_signal"] = "overbought"  # 超买
        elif rsi[-1] < 30:
            signals["rsi_signal"] = "oversold"  # 超卖
        else:
            signals["rsi_signal"] = "neutral"
    
    # 均线信号
    if sma20[-1] is not None:
        signals["sma20"] = round(sma20[-1], 4)
        signals["price_vs_sma20"] = round((current_price - sma20[-1]) / sma20[-1] * 100, 2)
    
    if sma50[-1] is not None:
        signals["sma50"] = round(sma50[-1], 4)
        signals["price_vs_sma50"] = round((current_price - sma50[-1]) / sma50[-1] * 100, 2)
    
    # 趋势判断
    if sma20[-1] is not None and sma50[-1] is not None:
        if sma20[-1] > sma50[-1]:
            signals["trend"] = "bullish"  # 多头趋势
        else:
            signals["trend"] = "bearish"  # 空头趋势
        
        # 均线交叉
        if sma20[-2] is not None and sma50[-2] is not None:
            prev_diff = sma20[-2] - sma50[-2]
            curr_diff = sma20[-1] - sma50[-1]
            if prev_diff < 0 and curr_diff > 0:
                signals["ma_cross"] = "golden_cross"
            elif prev_diff > 0 and curr_diff < 0:
                signals["ma_cross"] = "death_cross"
            else:
                signals["ma_cross"] = "none"
    
    # 布林带信号
    if bb_upper[-1] is not None and bb_lower[-1] is not None:
        signals["bb_upper"] = round(bb_upper[-1], 4)
        signals["bb_lower"] = round(bb_lower[-1], 4)
        bb_width = bb_upper[-1] - bb_lower[-1]
        bb_position = (current_price - bb_lower[-1]) / bb_width if bb_width > 0 else 0.5
        signals["bb_position"] = round(bb_position, 2)  # 0=下轨, 1=上轨
        
        if current_price > bb_upper[-1]:
            signals["bb_signal"] = "above_upper"  # 突破上轨
        elif current_price < bb_lower[-1]:
            signals["bb_signal"] = "below_lower"  # 跌破下轨
        else:
            signals["bb_signal"] = "within_bands"
    
    # 综合建议
    bullish_count = 0
    bearish_count = 0
    
    if signals.get("macd_trend") == "bullish":
        bullish_count += 1
    elif signals.get("macd_trend") == "bearish":
        bearish_count += 1
    
    if signals.get("rsi_signal") == "oversold":
        bullish_count += 1
    elif signals.get("rsi_signal") == "overbought":
        bearish_count += 1
    
    if signals.get("trend") == "bullish":
        bullish_count += 1
    elif signals.get("trend") == "bearish":
        bearish_count += 1
    
    if signals.get("price_vs_sma20", 0) > 0:
        bullish_count += 1
    else:
        bearish_count += 1
    
    signals["bullish_signals"] = bullish_count
    signals["bearish_signals"] = bearish_count
    
    if bullish_count > bearish_count + 1:
        signals["overall_signal"] = "strong_bullish"
    elif bullish_count > bearish_count:
        signals["overall_signal"] = "bullish"
    elif bearish_count > bullish_count + 1:
        signals["overall_signal"] = "strong_bearish"
    elif bearish_count > bullish_count:
        signals["overall_signal"] = "bearish"
    else:
        signals["overall_signal"] = "neutral"
    
    return signals

# =========================
# Main
# =========================
def run_node(node):
    dbg = []
    t0 = time.time()
    
    # 解析输入
    symbol = (node['Inputs'][0].get('Context') or "BTCUSDT").strip().upper()
    interval = (node['Inputs'][1].get('Context') or "1d").strip().lower()
    limit = node['Inputs'][2].get('Num') or 60
    
    try:
        limit = int(limit)
    except:
        limit = 60
    
    # 验证interval
    valid_intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
    if interval not in valid_intervals:
        interval = "1d"
    
    dbg.append(f"Fetching {symbol} {interval} klines, limit={limit}")
    
    # 获取K线数据
    klines = _fetch_klines(symbol, interval, limit, dbg)
    
    if not klines:
        result = {
            "ok": False,
            "error": "Failed to fetch klines",
            "debug": dbg,
            "symbol": symbol,
            "interval": interval
        }
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs
    
    # 提取收盘价序列
    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]
    
    # 计算技术指标
    macd_line, signal_line, histogram = _macd(closes)
    rsi = _rsi(closes)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    bb_upper, bb_mid, bb_lower = _bollinger_bands(closes)
    
    # 生成信号
    signals = _generate_signals(closes, macd_line, signal_line, histogram, rsi, sma20, sma50, bb_upper, bb_lower)
    
    # 计算额外统计
    price_high_period = max(highs)
    price_low_period = min(lows)
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    
    # 组装结果
    dt_ms = int((time.time() - t0) * 1000)
    
    result = {
        "ok": True,
        "symbol": symbol,
        "interval": interval,
        "kline_count": len(klines),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "latency_ms": dt_ms,
        
        # 当前价格信息
        "current": {
            "price": closes[-1],
            "open": klines[-1]["open"],
            "high": klines[-1]["high"],
            "low": klines[-1]["low"],
            "volume": klines[-1]["volume"],
        },
        
        # 周期统计
        "period_stats": {
            "high": price_high_period,
            "low": price_low_period,
            "range_pct": round((price_high_period - price_low_period) / price_low_period * 100, 2),
            "avg_volume": round(avg_volume, 2),
            "start_price": closes[0],
            "end_price": closes[-1],
            "period_change_pct": round((closes[-1] - closes[0]) / closes[0] * 100, 2),
        },
        
        # 技术指标
        "indicators": {
            "macd": macd_line[-1],
            "macd_signal": signal_line[-1],
            "macd_histogram": histogram[-1],
            "rsi": rsi[-1],
            "sma20": sma20[-1],
            "sma50": sma50[-1],
            "ema12": ema12[-1],
            "ema26": ema26[-1],
            "bb_upper": bb_upper[-1],
            "bb_mid": bb_mid[-1],
            "bb_lower": bb_lower[-1],
        },
        
        # 量化信号
        "signals": signals,
        
        # 最近5根K线
        "recent_klines": klines[-5:],
        
        "debug": dbg
    }
    
    Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
    return Outputs
