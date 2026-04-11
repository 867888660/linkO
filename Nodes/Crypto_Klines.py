import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Ensure sibling modules can be imported when this file is loaded dynamically.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from crypto_klines_config import INDICATOR_CONFIG, SIGNAL_CONFIG, HTTP_CONFIG
from klines_utils import safe_divide, format_float
from klines_signals import generate_signals
from klines_indicators import _sma, _ema, _macd, _rsi, _bollinger_bands, _adx, _atr, _detect_market_regime

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
# Technical indicators imported from klines_indicators.py
# =========================

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


def _normalize_binance_symbol(symbol: Optional[str]) -> Optional[str]:
    if not isinstance(symbol, str):
        return None

    text = symbol.strip().upper()
    if not text:
        return None

    text = text.replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
    if not text or not text.isalnum() or len(text) > 20:
        return None

    known_quotes = ("USDT", "USDC", "BUSD", "FDUSD", "BTC", "ETH", "BNB", "TRY", "EUR")
    if any(text.endswith(quote) and len(text) > len(quote) for quote in known_quotes):
        return text

    return f"{text}USDT"


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
        return _normalize_binance_symbol(payload.get("binance_symbol") or payload.get("symbol"))

    text = str(symbol_input).strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        extracted = _extract_json_text_field(text, ["binance_symbol", "symbol"])
        if extracted:
            return _normalize_binance_symbol(extracted)
        return _normalize_binance_symbol(text)

    if isinstance(parsed, dict):
        payload = {str(k).lower(): v for k, v in parsed.items()}
        return _normalize_binance_symbol(payload.get("binance_symbol") or payload.get("symbol"))

    if isinstance(parsed, str) and parsed.strip():
        return _normalize_binance_symbol(parsed)

    return None

# =========================
# Main
# =========================
def run_node(node):
    dbg = []
    t0 = time.time()

    # 解析输入
    symbol_raw = node['Inputs'][0].get('Context')
    symbol = _extract_symbol_from_input(symbol_raw)
    if not symbol:
        result = {"ok": False, "error": "Symbol is required (e.g., BTCUSDT)", "debug": ["Missing valid symbol. Prefer binance_symbol, fallback to symbol."]}
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False, indent=2)
        return Outputs

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
    ema9 = _ema(closes, INDICATOR_CONFIG["ema"]["periods"][0])
    ema21 = _ema(closes, INDICATOR_CONFIG["ema"]["periods"][1])
    adx, plus_di, minus_di = _adx(highs, lows, closes, INDICATOR_CONFIG["adx"]["period"])
    atr = _atr(highs, lows, closes, INDICATOR_CONFIG["atr"]["period"])

    # 布林带和SMA50
    sma50 = _sma(closes, 50)
    bb_period = SIGNAL_CONFIG.get("bb_period", 20)
    bb_upper, bb_mid, bb_lower = _bollinger_bands(closes, period=bb_period, std_dev=2.0)

    # 市场状态
    market_regime = _detect_market_regime(closes, volumes, adx, atr, bb_upper, bb_lower, bb_mid, sma50, signal_config=SIGNAL_CONFIG)

    # 额外特征数据（传给信号模块）
    extra_data = {
        "bb_upper": bb_upper[-1] if bb_upper[-1] is not None else None,
        "bb_lower": bb_lower[-1] if bb_lower[-1] is not None else None,
        "bb_mid": bb_mid[-1] if bb_mid[-1] is not None else None,
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
