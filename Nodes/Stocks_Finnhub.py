import json
import logging
import os
import random
import re
import threading
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 1
InPutNum = 2
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个Stocks行情抓取节点：输入美股Ticker列表与Finnhub API Key，调用 Finnhub Stock Quote（/quote）获取每个Ticker的最新价，输出JSON字符串。\n\n'
    '【黄金/白银常用符号（重点：别用错）】\n'
    '- ✅ 本节点推荐用（美股ETF，能直接查）：GLD（黄金ETF）、IAU（黄金ETF）、SLV（白银ETF）\n'
    '- ⚠️ 容易混淆：GOLD 通常是股票（Barrick Gold），SIL 通常是“白银矿业ETF”，都不是金银现货/期货价格\n'
    '- ❌ 期货/现货符号（本节点/quote通常查不到）：GC、SI、XAUUSD、XAGUSD（这些需要期货/外汇类接口或另建节点）\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '程序读取输入的Symbols字符串并解析为symbols数组（支持逗号/空格/换行分隔），'
    '从ApiKey输入读取Finnhub token用于鉴权，然后逐个symbol调用 Finnhub /quote 获取现价，'
    '将返回结果标准化为统一字段（如 symbol、price、ts_utc、source 等）后，'
    '最终组装为JSON字符串输出。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: Symbols\n    type: string\n    required: true\n    description: 美股Ticker列表，逗号/空格/换行分隔，例如 "AAPL,MSFT" 或 "GLD IAU SLVGLD（黄金ETF）、IAU（黄金ETF）、SLV（白银ETF）"\n'
    '  - name: ApiKey\n    type: string\n    required: true\n    description: Finnhub API Key（token），用于接口鉴权\n'
    'outputs:\n'
    '  - name: Result\n    type: string\n    description: JSON字符串，包含每个Ticker的最新价等基础信息\n```\n'
    '\n运行逻辑（用 - 列表描写详细流程）\n'
    '- 读取Input1作为Ticker列表字符串（Symbols）\n'
    '- 解析并清洗为symbols数组（统一转大写、去空、去重）\n'
    '- 读取Input2作为Finnhub API Key（ApiKey/token），若为空则返回错误\n'
    '- 逐个请求 Finnhub Stock Quote 接口（/quote）获取每个Ticker的现价\n'
    '- 组装输出字段：symbol、price、ts_utc、source等\n'
    '- 将结果序列化为JSON字符串写入OutPut1（Result）'
)

# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'

Inputs[0]['name'] = 'Symbols'
Inputs[0]['Isnecessary'] = True
Inputs[1]['name'] = 'API_Key'
Inputs[1]['Isnecessary'] = True
Inputs[1]['Kind'] = 'String_Key'
Outputs[0]['name'] = 'Result'

_LOGGER = logging.getLogger("Stocks_Finnhub_Node")
if not _LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)

_BASE_HEADERS = {
    "User-Agent": "pm-node/1.0",
    "Accept": "application/json",
}

# Make connection pooling + retries more robust under concurrent load / flaky networks.
_RETRY = Retry(
    total=0,  # we do our own retry loop to also cover JSON parsing and custom backoff
    connect=0,
    read=0,
    status=0,
    redirect=0,
    backoff_factor=0,
    raise_on_status=False,
)
_THREAD_LOCAL = threading.local()

# Global rate-limiter across all threads (per-process).
_RATE_LOCK = threading.Lock()
_NEXT_ALLOWED_TS = 0.0

def _get_sess() -> requests.Session:
    """Use one Session per thread to avoid concurrency pitfalls."""
    sess = getattr(_THREAD_LOCAL, "sess", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update(_BASE_HEADERS)
        adapter = HTTPAdapter(max_retries=_RETRY, pool_connections=10, pool_maxsize=10)
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        _THREAD_LOCAL.sess = sess
    return sess

def _throttle(min_interval_ms: int):
    """Simple global throttle: ensure at least min_interval_ms between outgoing requests."""
    if not min_interval_ms or min_interval_ms <= 0:
        return
    global _NEXT_ALLOWED_TS
    interval = min_interval_ms / 1000.0
    while True:
        with _RATE_LOCK:
            now = time.time()
            if now >= _NEXT_ALLOWED_TS:
                _NEXT_ALLOWED_TS = now + interval
                return
            sleep_s = _NEXT_ALLOWED_TS - now
        if sleep_s > 0:
            time.sleep(min(sleep_s, 2.0))

def _request_json(
    url,
    params,
    timeout=(5, 15),
    max_tries=5,
    backoff_s=0.8,
    backoff_max_s=12.0,
    jitter_s=0.25,
    min_interval_ms=0,
):
    """
    Requests JSON with small retry/backoff.
    Retries on:
    - network/connection resets/timeouts
    - HTTP 429 / 5xx
    """
    last_exc = None
    for i in range(max_tries):
        try:
            _throttle(min_interval_ms)
            resp = _get_sess().get(url, params=params, timeout=timeout)
            code = resp.status_code
            if code == 429 or (500 <= code <= 599):
                # rate-limit / transient server error
                if i < max_tries - 1:
                    ra = resp.headers.get("Retry-After")
                    if ra:
                        try:
                            ra_s = float(ra)
                            time.sleep(min(max(ra_s, 0.0), backoff_max_s))
                            continue
                        except Exception:
                            pass
                    sleep_s = min(backoff_s * (2 ** i), backoff_max_s) + (random.random() * jitter_s)
                    time.sleep(sleep_s)
                    continue
            # do not retry other 4xx (usually invalid symbol/token/permission)
            if 400 <= code <= 499 and code != 429:
                resp.raise_for_status()
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception as e:
                # occasionally upstream returns non-JSON or truncated payload; retry
                last_exc = e
                if i < max_tries - 1:
                    sleep_s = min(backoff_s * (2 ** i), backoff_max_s) + (random.random() * jitter_s)
                    time.sleep(sleep_s)
                    continue
                raise
        except Exception as e:
            last_exc = e
            if i < max_tries - 1:
                sleep_s = min(backoff_s * (2 ** i), backoff_max_s) + (random.random() * jitter_s)
                time.sleep(sleep_s)
                continue
            raise
    # Should not reach here, but keep mypy/linters happy.
    raise last_exc

def _parse_symbols(text: str):
    if text is None:
        return []
    parts = re.split(r"[,\s;]+", str(text).strip())
    syms = []
    for p in parts:
        p = p.strip().upper()
        if p:
            syms.append(p)
    seen = set()
    out = []
    for s in syms:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def _get_quote(base, token, symbol):
    # Finnhub Quote API :contentReference[oaicite:7]{index=7}
    url = base.rstrip("/") + "/quote"
    return _request_json(url, params={"symbol": symbol, "token": token})

def _get_candle_5m(base, token, symbol):
    # Finnhub Stock Candles API :contentReference[oaicite:8]{index=8}
    url = base.rstrip("/") + "/stock/candle"
    now = int(time.time())
    frm = now - 60 * 30  # last 30 minutes window is enough for the latest 5m bar
    params = {
        "symbol": symbol,
        "resolution": 5,
        "from": frm,
        "to": now,
        "token": token
    }
    return _request_json(url, params=params)

def _get_profile2(base, token, symbol):
    # Company Profile2 has marketCapitalization and shareOutstanding fields (examples exist) :contentReference[oaicite:9]{index=9}
    url = base.rstrip("/") + "/stock/profile2"
    return _request_json(url, params={"symbol": symbol, "token": token})

def _extract_last_5m_volume(candle_json):
    # Response includes arrays: c,h,l,o,t,v and status s
    if not isinstance(candle_json, dict):
        return None
    if candle_json.get("s") != "ok":
        return None
    v = candle_json.get("v")
    if isinstance(v, list) and len(v) > 0:
        return _safe_float(v[-1])
    return None

def run_node(node):
    symbols_text = node['Inputs'][0]['Context']   # 例如 "AAPL,MSFT,TSLA"
    api_key_text = node['Inputs'][1]['Context']   # 既可填token，也可填环境变量名
    content = ""
    Debugging = []

    try:
        # --- token resolution: support both "direct token" and "env var name" ---
        raw = (api_key_text or "").strip()
        token = ""

        if raw:
            # 1) try treat Input2 as direct token first (most common)
            token = raw
            # 2) if it looks like an env var name (e.g., FINNHUB_API_KEY) and exists, use env value
            env_val = os.getenv(raw, "").strip()
            if env_val:
                # If user passed env var name, env_val will be real token; override.
                # If user passed a real token, env_val will usually be empty, so no change.
                token = env_val

        # final fallback: if still empty, try standard env var
        if not token:
            token = os.getenv("FINNHUB_API_KEY", "").strip()

        if not token:
            Outputs[0]['Context'] = json.dumps({
                "ok": False,
                "error": "Missing Finnhub API token. Provide token in Input2 or set FINNHUB_API_KEY.",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "data": []
            }, ensure_ascii=False)
            return Outputs

        symbols = _parse_symbols(symbols_text)
        if not symbols:
            Outputs[0]['Context'] = json.dumps({
                "ok": False,
                "error": "No symbols provided",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "data": []
            }, ensure_ascii=False)
            return Outputs

        base = os.getenv("FINNHUB_BASE_URL", "https://finnhub.io/api/v1").rstrip("/")
        max_workers = int(os.getenv("FINNHUB_MAX_WORKERS", "5"))
        debug_enabled = os.getenv("FINNHUB_DEBUG", "").strip().lower() in ("1", "true", "yes", "y", "on")
        # Stability knobs (defaults prioritize stability over speed; tweak via env if needed)
        min_interval_ms = int(os.getenv("FINNHUB_MIN_INTERVAL_MS", "1100"))  # ~<= 1 rps (safe for many plans)
        req_max_tries = int(os.getenv("FINNHUB_MAX_TRIES", "5"))
        req_backoff_s = float(os.getenv("FINNHUB_BACKOFF_S", "0.8"))
        req_backoff_max_s = float(os.getenv("FINNHUB_BACKOFF_MAX_S", "12"))
        req_jitter_s = float(os.getenv("FINNHUB_JITTER_S", "0.25"))
        timeout_connect = float(os.getenv("FINNHUB_TIMEOUT_CONNECT", "5"))
        timeout_read = float(os.getenv("FINNHUB_TIMEOUT_READ", "15"))
        ts_now = datetime.now(timezone.utc).isoformat()

        def _fetch_one(sym):
            row = {
                "symbol": sym,
                "ts_utc": None,
                "source": "finnhub_quote_profile2"
            }

            # quote for price
            try:
                q = _request_json(
                    base.rstrip("/") + "/quote",
                    params={"symbol": sym, "token": token},
                    timeout=(timeout_connect, timeout_read),
                    max_tries=req_max_tries,
                    backoff_s=req_backoff_s,
                    backoff_max_s=req_backoff_max_s,
                    jitter_s=req_jitter_s,
                    min_interval_ms=min_interval_ms,
                )
                row["price"] = _safe_float(q.get("c"))
            except Exception as e:
                # keep consistent structure; let caller decide whether to treat as hard failure
                row["error"] = repr(e)  # backward compatible field
                row["error_quote"] = repr(e)
                return row

            # profile2 for shares outstanding / fallback market cap
            try:
                p = _request_json(
                    base.rstrip("/") + "/stock/profile2",
                    params={"symbol": sym, "token": token},
                    timeout=(timeout_connect, timeout_read),
                    max_tries=req_max_tries,
                    backoff_s=req_backoff_s,
                    backoff_max_s=req_backoff_max_s,
                    jitter_s=req_jitter_s,
                    min_interval_ms=min_interval_ms,
                )
                shares_outstanding_m = _safe_float(p.get("shareOutstanding"))
                market_cap_musd_api = _safe_float(p.get("marketCapitalization"))
                price = row.get("price")

                row["shares_outstanding_m"] = shares_outstanding_m

                if price is not None and shares_outstanding_m is not None:
                    market_cap_usd = price * shares_outstanding_m * 1_000_000
                    row["market_cap_usd"] = market_cap_usd
                    row["market_cap_musd"] = market_cap_usd / 1_000_000
                    row["market_cap_source"] = "price_x_shareOutstanding"
                else:
                    row["market_cap_musd"] = market_cap_musd_api
                    row["market_cap_usd"] = market_cap_musd_api * 1_000_000 if market_cap_musd_api is not None else None
                    row["market_cap_source"] = "profile2_marketCapitalization"
            except Exception as e:
                # profile2 失败不影响现价输出
                row["error_profile2"] = repr(e)

            row["ts_utc"] = datetime.now(timezone.utc).isoformat()
            return row

        t0 = time.time()
        rows = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_fetch_one, s): s for s in symbols}
            for fut in as_completed(futs):
                sym = futs[fut]
                try:
                    rows.append(fut.result())
                except Exception as e:
                    Debugging.append(f"{sym} error: {repr(e)}")
                    rows.append({
                        "symbol": sym,
                        "error": repr(e),
                        "ts_utc": ts_now,
                        "source": "finnhub_quote_profile2"
                    })

        dt_ms = int((time.time() - t0) * 1000)
        result = {
            "ok": True,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "latency_ms": dt_ms,
            "count": len(rows),
            "data": sorted(rows, key=lambda x: x.get("symbol", ""))
        }
        if debug_enabled:
            result["debug"] = Debugging
        content = json.dumps(result, ensure_ascii=False)

    except Exception as e:
        Debugging.append(f"Exception: {repr(e)}")
        content = json.dumps({
            "ok": False,
            "error": repr(e),
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "data": []
        }, ensure_ascii=False)

    Outputs[0]['Context'] = content
    return Outputs
