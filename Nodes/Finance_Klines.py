import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import yfinance as yf

# Ensure sibling modules can be imported when this file is loaded dynamically.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from finance_klines_config import INDICATOR_CONFIG, SIGNAL_CONFIG, HTTP_CONFIG
from klines_utils import format_float, safe_divide
from klines_signals import generate_signals
from klines_indicators import _sma, _ema, _macd, _rsi, _bollinger_bands, _adx, _atr, _detect_market_regime

# Finance 使用的短周期 RSI 周期
_RSI2_PERIOD = SIGNAL_CONFIG.get("rsi2_period", 7)

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
    "Description": "股票K线数据JSON，包含OHLCV和技术指标"
} for _ in range(OutPutNum)]

Inputs = [
    {"Num": None, "Kind": "String", "Id": "Input1", "Context": None, "name": "Symbol", "Link": 0, "IsLabel": True, "Isnecessary": True},
    {"Num": None, "Kind": "String", "Id": "Input2", "Context": "1d", "name": "Interval", "Link": 0, "IsLabel": True, "Isnecessary": False},
    {"Num": None, "Kind": "String", "Id": "Input3", "Context": "3mo", "name": "Period", "Link": 0, "IsLabel": True, "Isnecessary": False},
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

for o in Outputs:
    o['Kind'] = 'String'

FunctionIntroduction = (
    "组件功能\n"
    "股票K线数据抓取与技术指标分析节点：从 Yahoo Finance 获取历史K线，"
    "计算核心技术指标（EMA、MACD、RSI、ADX、ATR），"
    "输出趋势+动量双通道加权信号系统的量化分析JSON。\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: Symbol\n    type: string\n    required: true\n    description: 股票代码，如 AAPL\n"
    "  - name: Interval\n    type: string\n    default: 1d\n    description: K线周期\n"
    "  - name: Period\n    type: string\n    default: 3mo\n    description: 数据时间范围（如 3mo, 6mo, 1y）\n"
    "outputs:\n"
    "  - name: Result\n    type: string\n    description: JSON，含技术指标+加权信号系统\n```"
)

# =========================
# yfinance data fetching
# =========================
def _fetch_stock_klines(symbol: str, interval: str, period: str, dbg: List[str]) -> List[Dict]:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            dbg.append(f"yfinance returned empty data for {symbol}")
            return []
        klines = []
        for idx, row in df.iterrows():
            klines.append({
                "open_time": int(idx.timestamp() * 1000),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
                "close_time": int(idx.timestamp() * 1000),
                "quote_volume": 0,
                "trades": 0,
            })
        return klines
    except Exception as e:
        dbg.append(f"yfinance exception: {repr(e)}")
        return []


def _normalize_yfinance_symbol(symbol: Optional[str]) -> Optional[str]:
    if not isinstance(symbol, str):
        return None

    text = symbol.strip().upper().replace(" ", "")
    if not text or len(text) > 32:
        return None

    allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-^=")
    if any(ch not in allowed_chars for ch in text):
        return None

    return text


def _extract_json_text_field(text: str, field_names: List[str]) -> Optional[str]:
    for field_name in field_names:
        pattern = rf'["\']{re.escape(field_name)}["\']\s*:\s*["\']([^"\']+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _extract_symbol_from_input(symbol_input) -> Optional[str]:
    if symbol_input is None:
        return None

    if isinstance(symbol_input, dict):
        payload = {str(k).lower(): v for k, v in symbol_input.items()}
        return _normalize_yfinance_symbol(payload.get("yfinance_symbol") or payload.get("symbol"))

    text = str(symbol_input).strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        extracted = _extract_json_text_field(text, ["yfinance_symbol", "symbol"])
        if extracted:
            return _normalize_yfinance_symbol(extracted)
        return _normalize_yfinance_symbol(text)

    if isinstance(parsed, dict):
        payload = {str(k).lower(): v for k, v in parsed.items()}
        return _normalize_yfinance_symbol(payload.get("yfinance_symbol") or payload.get("symbol"))

    if isinstance(parsed, str) and parsed.strip():
        return _normalize_yfinance_symbol(parsed)

    return None


def _parse_llm_output(raw_input) -> Optional[dict]:
    """Parse the LLM JSON output to extract can_analyze, interval, period, etc."""
    if not raw_input:
        return None
    text = str(raw_input).strip()
    if not text:
        return None
    # Strip markdown code fences (```json ... ```)
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {k.lower(): v for k, v in parsed.items()}
    except (TypeError, json.JSONDecodeError):
        pass
    return None


# =========================
# Main
# =========================
def run_node(node):
    dbg = []
    t0 = time.time()

    symbol_raw = node['Inputs'][0].get('Context')

    # Check can_analyze from LLM output
    llm_parsed = _parse_llm_output(symbol_raw)
    if llm_parsed and llm_parsed.get("can_analyze") is False:
        result = {"ok": False, "error": "Question not suitable for technical analysis", "debug": ["LLM determined can_analyze=false"]}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs

    symbol = _extract_symbol_from_input(symbol_raw)
    if not symbol:
        result = {"ok": False, "error": "Symbol is required (e.g., AAPL)", "debug": ["Missing valid symbol. Prefer yfinance_symbol, fallback to symbol."]}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs

    # Use LLM-suggested interval/limit if available, otherwise use node defaults
    interval = (node['Inputs'][1].get('Context') or "1d").strip().lower()
    period = (node['Inputs'][2].get('Context') or "3mo").strip().lower()

    if llm_parsed:
        suggested_interval = llm_parsed.get("suggested_interval")
        suggested_limit = llm_parsed.get("suggested_limit")
        if suggested_interval and isinstance(suggested_interval, str):
            interval = suggested_interval.strip().lower()
        # Convert suggested_limit (number of bars) to yfinance period
        if suggested_limit and isinstance(suggested_limit, (int, float)):
            limit_val = int(suggested_limit)
            if interval in ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"):
                period = "1mo"
            elif interval in ("4h",):
                # yfinance doesn't support 4h; fall back to 1h with more history
                interval = "1h"
                period = "1mo"
            elif interval in ("1d",):
                if limit_val <= 30:
                    period = "1mo"
                elif limit_val <= 90:
                    period = "3mo"
                elif limit_val <= 180:
                    period = "6mo"
                elif limit_val <= 365:
                    period = "1y"
                else:
                    period = "2y"
            elif interval in ("1w", "1wk"):
                interval = "1wk"  # normalize to yfinance format
                if limit_val <= 52:
                    period = "1y"
                else:
                    period = "2y"
            elif interval in ("1mo", "1M"):
                interval = "1mo"
                period = "5y"

    # Normalize interval: convert universal format to yfinance format
    interval_map = {"4h": "1h", "1w": "1wk", "1M": "1mo"}
    interval = interval_map.get(interval, interval)

    valid_intervals = ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo"]
    if interval not in valid_intervals:
        interval = "1d"

    valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
    if period not in valid_periods:
        period = "3mo"

    dbg.append(f"Fetching {symbol} {interval} klines, period={period}")

    klines = _fetch_stock_klines(symbol, interval, period, dbg)
    if not klines:
        result = {"ok": False, "error": "Failed to fetch stock klines", "debug": dbg, "symbol": symbol, "interval": interval}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    # 计算技术指标
    DIF, DEA, hist = _macd(closes, **INDICATOR_CONFIG["macd"])
    rsi = _rsi(closes, **INDICATOR_CONFIG["rsi"])
    ema9 = _ema(closes, INDICATOR_CONFIG["ema"]["periods"][0])
    ema21 = _ema(closes, INDICATOR_CONFIG["ema"]["periods"][1])
    adx, plus_di, minus_di = _adx(highs, lows, closes, INDICATOR_CONFIG["adx"]["period"])
    atr = _atr(highs, lows, closes, INDICATOR_CONFIG["atr"]["period"])

    # 布林带和SMA50
    sma50 = _sma(closes, 50)
    bb_period = SIGNAL_CONFIG.get("bb_period", 20)
    bb_upper, bb_mid, bb_lower = _bollinger_bands(closes, period=bb_period, std_dev=2.0)

    # 短周期 RSI（Finance 新特征）
    rsi2 = _rsi(closes, _RSI2_PERIOD)

    # 市场状态
    market_regime = _detect_market_regime(closes, volumes, adx, atr, bb_upper, bb_lower, bb_mid, sma50, signal_config=SIGNAL_CONFIG)

    # 额外特征数据（传给信号模块）
    extra_data = {
        "bb_upper": bb_upper[-1] if bb_upper[-1] is not None else None,
        "bb_lower": bb_lower[-1] if bb_lower[-1] is not None else None,
        "bb_mid": bb_mid[-1] if bb_mid[-1] is not None else None,
        "rsi2": rsi2[-1] if rsi2[-1] is not None else None,
        "plus_di": plus_di[-1] if plus_di[-1] is not None else None,
        "minus_di": minus_di[-1] if minus_di[-1] is not None else None,
        "sma50": sma50[-1] if sma50[-1] is not None else None,
        "volumes": volumes,
    }

    # 生成信号
    signals = generate_signals(
        closes, DIF, DEA, hist, rsi, ema9, ema21,
        adx, atr, market_regime, signal_config=SIGNAL_CONFIG,
        extra_data=extra_data
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
