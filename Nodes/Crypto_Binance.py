import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================
# Node metadata (keep your framework happy)
# =========================
OutPutNum = 1
InPutNum = 1

Outputs = [{
    "Num": None,
    "Kind": None,
    "Boolean": False,
    "Id": "Output1",
    "Context": None,
    "name": "Result",
    "Link": 0,
    "Description": ""
} for _ in range(OutPutNum)]

Inputs = [{
    "Num": None,
    "Kind": None,
    "Id": "Input1",
    "Context": None,
    "name": "Symbols / Config",
    "Link": 0,
    "IsLabel": True
} for _ in range(InPutNum)]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

# **Assign properties to Inputs/Outputs**
for o in Outputs:
    o['Kind'] = 'String'
for i in Inputs:
    i['Kind'] = 'String'

FunctionIntroduction = (
    "组件功能\n"
    "1) 从 Binance Spot REST /api/v3/ticker/24hr (type=MINI) 批量拉取行情\n"
    "2) 可选：用 CoinGecko 拉取 FDV/市值/供给等基本面，并合并到输出\n"
    "\n"
    "输入兼容两种形式：\n"
    "A) 纯文本/逗号/换行：BTCUSDT,ETHUSDT\n"
    "B) JSON：{\n"
    '   "symbols": ["BTCUSDT","ETHUSDT"],\n'
    '   "include_fundamentals": true,\n'
    '   "vs_currency": "usd",\n'
    '   "fundamentals_provider": "coingecko"\n'
    "}\n"
)

# =========================
# HTTP session with retries
# =========================
def _make_session() -> requests.Session:
    s = requests.Session()

    # Retries for transient network errors (timeouts, 5xx, 429)
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
# Helpers
# =========================
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def _parse_symbols(text: str) -> List[str]:
    """
    Accept:
      - CSV / newline / space separated
      - JSON array string: ["BTCUSDT","ETHUSDT"]
      - pasted junk with symbols inside
    """
    if not text:
        return []

    text = str(text).strip()
    if not text:
        return []

    # Try JSON array
    if text.startswith("[") and text.endswith("]"):
        try:
            arr = json.loads(text)
            if isinstance(arr, list):
                syms = [str(x).strip().upper() for x in arr if str(x).strip()]
                return _dedupe_keep_order(syms)
        except Exception:
            pass

    # Split common separators
    parts = re.split(r"[\s,;|]+", text)
    syms: List[str] = []
    for p in parts:
        p = p.strip().upper()
        if not p:
            continue
        # allow "BTC/USDT" style
        p = p.replace("/", "").replace("-", "")
        # basic sanity: 5~20 chars alnum
        if re.fullmatch(r"[A-Z0-9]{5,20}", p):
            syms.append(p)

    return _dedupe_keep_order(syms)

def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def _chunks(items: List[str], n: int) -> List[List[str]]:
    return [items[i:i+n] for i in range(0, len(items), n)]

def _parse_input_context(ctx: Any) -> Tuple[List[str], Dict[str, Any]]:
    """
    Backward compatible:
      - If ctx is JSON object with "symbols", treat as config
      - Else treat as symbols string
    """
    config: Dict[str, Any] = {}
    if ctx is None:
        return [], config

    if isinstance(ctx, (dict, list)):
        # If some upstream node already passed parsed JSON
        if isinstance(ctx, dict) and "symbols" in ctx:
            config = ctx
            syms = ctx.get("symbols") or []
            if isinstance(syms, str):
                return _parse_symbols(syms), config
            if isinstance(syms, list):
                return _dedupe_keep_order([str(x).strip().upper() for x in syms if str(x).strip()]), config
        # list -> assume symbols list
        if isinstance(ctx, list):
            return _dedupe_keep_order([str(x).strip().upper() for x in ctx if str(x).strip()]), config

    text = str(ctx).strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "symbols" in obj:
                config = obj
                syms = obj.get("symbols") or []
                if isinstance(syms, list):
                    return _dedupe_keep_order([str(x).strip().upper() for x in syms if str(x).strip()]), config
                if isinstance(syms, str):
                    return _parse_symbols(syms), config
        except Exception:
            pass

    return _parse_symbols(text), config

# =========================
# Binance: ticker + exchangeInfo
# =========================
_BINANCE_EXINFO_CACHE: Dict[str, Dict[str, str]] = {}  # symbol -> {"base":..., "quote":...}

def _binance_base_url() -> str:
    return os.getenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com").rstrip("/")

def _http_timeout() -> float:
    return float(os.getenv("HTTP_TIMEOUT", "12"))

def _binance_get_json(path: str, params: Dict[str, Any], dbg: List[str]) -> Tuple[int, Any]:
    url = _binance_base_url() + path
    try:
        resp = _SESS.get(url, params=params, timeout=_http_timeout())
        return resp.status_code, resp.json()
    except Exception as e:
        dbg.append(f"Binance GET {path} exception: {repr(e)}")
        return 0, None

def _binance_fetch_mini_ticker(symbols: List[str], dbg: List[str]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Calls /api/v3/ticker/24hr with type=MINI.
    Binance allows max 100 symbols per request (so we chunk).
    """
    all_rows: List[Dict[str, Any]] = []
    t0 = time.time()
    for batch in _chunks(symbols, 100):
        params = {
            "symbols": json.dumps(batch, separators=(",", ":")),
            "type": "MINI",
        }
        status, payload = _binance_get_json("/api/v3/ticker/24hr", params, dbg)
        if status != 200 or payload is None:
            dbg.append(f"Binance ticker24hr failed for batch size={len(batch)} status={status}")
            continue
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            dbg.append(f"Unexpected ticker24hr payload type: {type(payload)}")
            continue

        for it in payload:
            sym = it.get("symbol")
            all_rows.append({
                "symbol": sym,
                "price": _safe_float(it.get("lastPrice")),
                "vol_24h_base": _safe_float(it.get("volume")),
                "vol_24h_quote": _safe_float(it.get("quoteVolume")),
                "open_time_ms": it.get("openTime"),
                "close_time_ms": it.get("closeTime"),
                "source_price": "binance_spot_rest_ticker24hr_mini",
            })
    dt_ms = int((time.time() - t0) * 1000)
    return all_rows, dt_ms

def _binance_fill_exchange_info(symbols: List[str], dbg: List[str]) -> None:
    """
    Fetch baseAsset/quoteAsset for symbols and cache them.
    """
    need = [s for s in symbols if s not in _BINANCE_EXINFO_CACHE]
    if not need:
        return

    for batch in _chunks(need, 100):
        params = {"symbols": json.dumps(batch, separators=(",", ":"))}
        status, payload = _binance_get_json("/api/v3/exchangeInfo", params, dbg)
        if status != 200 or payload is None:
            dbg.append(f"Binance exchangeInfo failed for batch size={len(batch)} status={status}")
            continue

        symbols_info = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(symbols_info, list):
            dbg.append("Unexpected exchangeInfo payload (missing symbols list)")
            continue

        for it in symbols_info:
            sym = it.get("symbol")
            base = it.get("baseAsset")
            quote = it.get("quoteAsset")
            if sym and base and quote:
                _BINANCE_EXINFO_CACHE[sym] = {"base": base, "quote": quote}

# =========================
# CoinGecko fundamentals (FDV / market cap / supply)
# =========================
DEFAULT_TICKER_TO_COINGECKO_ID: Dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "TRX": "tron",
    "TON": "the-open-network",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "APT": "aptos",
    "SUI": "sui",
}

_COINGECKO_ID_CACHE: Dict[str, str] = {}  # ticker -> id (best-effort)
_COINGECKO_MARKETS_CACHE: Dict[str, Dict[str, Any]] = {}  # id -> fundamentals

def _coingecko_base_url() -> str:
    return os.getenv("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3").rstrip("/")

def _coingecko_headers(config: Dict[str, Any]) -> Dict[str, str]:
    """
    Demo API key header: x-cg-demo-api-key
    Pro API key header:  x-cg-pro-api-key
    """
    key = (config.get("coingecko_api_key") or os.getenv("COINGECKO_API_KEY") or "").strip()
    header = (config.get("coingecko_api_key_header") or os.getenv("COINGECKO_API_KEY_HEADER") or "x-cg-demo-api-key").strip()
    h: Dict[str, str] = {"accept": "application/json"}
    if key:
        h[header] = key
    return h

def _coingecko_get_json(path: str, params: Dict[str, Any], headers: Dict[str, str], dbg: List[str]) -> Tuple[int, Any]:
    url = _coingecko_base_url() + path
    try:
        resp = _SESS.get(url, params=params, headers=headers, timeout=_http_timeout())
        # CoinGecko may return HTML on some errors; protect json()
        try:
            data = resp.json()
        except Exception:
            data = {"_raw": resp.text[:500]}
        return resp.status_code, data
    except Exception as e:
        dbg.append(f"CoinGecko GET {path} exception: {repr(e)}")
        return 0, None

def _coingecko_resolve_id_for_ticker(ticker: str, headers: Dict[str, str], dbg: List[str]) -> Optional[str]:
    ticker_u = ticker.upper()
    if ticker_u in _COINGECKO_ID_CACHE:
        return _COINGECKO_ID_CACHE[ticker_u]
    if ticker_u in DEFAULT_TICKER_TO_COINGECKO_ID:
        _COINGECKO_ID_CACHE[ticker_u] = DEFAULT_TICKER_TO_COINGECKO_ID[ticker_u]
        return _COINGECKO_ID_CACHE[ticker_u]

    # Best-effort search (can be wrong for ambiguous tickers)
    status, data = _coingecko_get_json("/search", {"query": ticker_u}, headers, dbg)
    if status != 200 or not isinstance(data, dict):
        return None
    coins = data.get("coins")
    if not isinstance(coins, list) or not coins:
        return None

    tl = ticker_u.lower()
    # Prefer exact symbol match
    for c in coins[:20]:
        if str(c.get("symbol", "")).lower() == tl and c.get("id"):
            _COINGECKO_ID_CACHE[ticker_u] = c["id"]
            return c["id"]
    # Fallback: first result
    first = coins[0]
    if isinstance(first, dict) and first.get("id"):
        _COINGECKO_ID_CACHE[ticker_u] = first["id"]
        return first["id"]
    return None

def _coingecko_fetch_markets(ids: List[str], vs_currency: str, headers: Dict[str, str], dbg: List[str]) -> None:
    """
    Calls /coins/markets for ids (batch in chunks to avoid too-long URLs).
    Stores into _COINGECKO_MARKETS_CACHE.
    """
    ids = [i for i in ids if i]
    ids = _dedupe_keep_order(ids)
    need = [i for i in ids if i not in _COINGECKO_MARKETS_CACHE]
    if not need:
        return

    for batch in _chunks(need, 200):
        params = {
            "vs_currency": vs_currency,
            "ids": ",".join(batch),
            "per_page": len(batch),
            "page": 1,
        }
        status, data = _coingecko_get_json("/coins/markets", params, headers, dbg)
        if status != 200 or not isinstance(data, list):
            dbg.append(f"CoinGecko coins/markets failed status={status} batch={len(batch)}")
            continue
        for it in data:
            cid = it.get("id")
            if not cid:
                continue
            _COINGECKO_MARKETS_CACHE[cid] = {
                "market_cap": it.get("market_cap"),
                "fdv": it.get("fully_diluted_valuation"),
                "circulating_supply": it.get("circulating_supply"),
                "total_supply": it.get("total_supply"),
                "max_supply": it.get("max_supply"),
                "last_updated": it.get("last_updated"),
                "source_fundamentals": "coingecko_coins_markets",
            }

# =========================
# Main node function
# =========================
def run_node(node):
    """
    Output JSON:
      {
        ok: bool,
        ts_utc: str,
        latency_ms: int,
        count: int,
        data: [ {symbol, price, ... , fdv_usd, market_cap_usd, ...} ],
        debug: [ ... ]
      }
    """
    Debugging: List[str] = []
    content = ""

    try:
        raw_ctx = node["Inputs"][0].get("Context")
        symbols, config = _parse_input_context(raw_ctx)

        if not symbols:
            result = {"ok": False, "error": "No symbols provided", "ts_utc": _utc_now(), "data": [], "debug": Debugging}
            Outputs[0]["Context"] = json.dumps(result, ensure_ascii=False)
            return Outputs

        include_fundamentals = bool(config.get("include_fundamentals", False))
        fundamentals_provider = str(config.get("fundamentals_provider", "coingecko")).lower().strip()
        vs_currency = str(config.get("vs_currency", "usd")).lower().strip()

        # 1) Binance ticker (chunked)
        rows, dt_ms = _binance_fetch_mini_ticker(symbols, Debugging)

        # 2) Optional: base/quote split (needed for fundamentals join by base ticker)
        if include_fundamentals and fundamentals_provider == "coingecko":
            _binance_fill_exchange_info([r.get("symbol") for r in rows if r.get("symbol")], Debugging)

            # 3) Resolve CoinGecko ids
            headers = _coingecko_headers(config)
            base_tickers: List[str] = []
            sym_to_base: Dict[str, str] = {}

            for r in rows:
                sym = r.get("symbol")
                ex = _BINANCE_EXINFO_CACHE.get(sym or "")
                if ex and ex.get("base"):
                    base = ex["base"]
                    sym_to_base[sym] = base
                    base_tickers.append(base)

            base_tickers = _dedupe_keep_order(base_tickers)

            ticker_to_id: Dict[str, str] = {}
            for t in base_tickers:
                cid = _coingecko_resolve_id_for_ticker(t, headers, Debugging)
                if cid:
                    ticker_to_id[t] = cid

            # 4) Pull markets fundamentals in batch
            _coingecko_fetch_markets(list(ticker_to_id.values()), vs_currency=vs_currency, headers=headers, dbg=Debugging)

            # 5) Merge back into rows
            for r in rows:
                sym = r.get("symbol")
                ex = _BINANCE_EXINFO_CACHE.get(sym or {})
                if ex:
                    r["baseAsset"] = ex.get("base")
                    r["quoteAsset"] = ex.get("quote")
                base = r.get("baseAsset") or sym_to_base.get(sym or "")
                if base and base in ticker_to_id:
                    cid = ticker_to_id[base]
                    f = _COINGECKO_MARKETS_CACHE.get(cid, {})
                    # Normalize field names (usd suffix for clarity)
                    r["market_cap_usd"] = f.get("market_cap")
                    r["fdv_usd"] = f.get("fdv")
                    r["circulating_supply"] = f.get("circulating_supply")
                    r["total_supply"] = f.get("total_supply")
                    r["max_supply"] = f.get("max_supply")
                    r["fundamentals_last_updated"] = f.get("last_updated")
                    r["source_fundamentals"] = f.get("source_fundamentals")
                else:
                    # explicit but non-fatal
                    if include_fundamentals:
                        r["source_fundamentals"] = None

        # Final
        result = {
            "ok": True,
            "ts_utc": _utc_now(),
            "latency_ms": dt_ms,
            "count": len(rows),
            "data": rows,
            "debug": Debugging,
            "meta": {
                "include_fundamentals": include_fundamentals,
                "fundamentals_provider": fundamentals_provider if include_fundamentals else None,
                "vs_currency": vs_currency if include_fundamentals else None,
                "binance_base_url": _binance_base_url(),
                "coingecko_base_url": _coingecko_base_url() if include_fundamentals else None,
            }
        }
        content = json.dumps(result, ensure_ascii=False)

    except Exception as e:
        Debugging.append(f"Exception: {repr(e)}")
        content = json.dumps({
            "ok": False,
            "error": repr(e),
            "ts_utc": _utc_now(),
            "data": [],
            "debug": Debugging
        }, ensure_ascii=False)

    Outputs[0]["Context"] = content
    return Outputs
