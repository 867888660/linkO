import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 1
InPutNum = 1
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**
NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction = '组件功能（简述代码整体功能）\\n这是一个Crypto行情抓取节点：输入Binance交易对名称列表（如BTCUSDT,ETHUSDT），输出这些交易对的最新价、24h成交量等基础信息（JSON字符串）。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n- 解析输入字符串为symbols数组（支持逗号/空格/换行分隔）\\n- 调用Binance Spot REST接口 /api/v3/ticker/24hr 并使用 symbols=[...] 一次性批量查询\\n- 标准化字段：symbol、price(lastPrice)、vol_24h(volume)、quote_vol_24h(quoteVolume)、closeTime等\\n- 输出为JSON字符串写入OutPut1\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Symbols\\n    type: string\\n    required: true\\n    description: 交易对名称列表，逗号或空格分隔，例如 \"BTCUSDT,ETHUSDT\"\\noutputs:\\n  - name: Result\\n    type: string\\n    description: JSON字符串，包含每个交易对的最新价/成交量等\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 读取Input1作为symbols字符串\\n- 解析并清洗成交易对数组（转大写，去空）\\n- GET Binance /api/v3/ticker/24hr?symbols=[...]&type=MINI\\n- 组装结果列表并输出JSON'

# **Assign properties to Inputs**
for output in Outputs:
    output['Kind'] = 'String'

for input in Inputs:
    input['Kind'] = 'String'

# Optional: rename IO for clarity (still strict template-compatible)
Inputs[0]['name'] = 'Symbols'
Outputs[0]['name'] = 'Result'

# --- internal helpers ---
_LOGGER = logging.getLogger("Crypto_Binance_Node")
if not _LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)

_SESS = requests.Session()
_SESS.headers.update({
    "User-Agent": "pm-node/1.0",
    "Accept": "application/json",
})

def _parse_symbols(text: str):
    if text is None:
        return []
    # split by comma / whitespace / newline / semicolon
    parts = re.split(r"[,\s;]+", str(text).strip())
    syms = []
    for p in parts:
        p = p.strip().upper()
        if p:
            syms.append(p)
    # de-dup while preserving order
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

def run_node(node):
    symbols_text = node['Inputs'][0]['Context']
    content = ""
    Debugging = []

    try:
        symbols = _parse_symbols(symbols_text)
        if not symbols:
            result = {
                "ok": False,
                "error": "No symbols provided",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "data": []
            }
            Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
            return Outputs

        base_url = os.getenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com")
        url = base_url.rstrip("/") + "/api/v3/ticker/24hr"

        # Binance supports symbols as JSON array string, e.g. ["BTCUSDT","BNBUSDT"] :contentReference[oaicite:2]{index=2}
        params = {
            "symbols": json.dumps(symbols, separators=(",", ":")),
            "type": "MINI",  # FULL/MINI supported :contentReference[oaicite:3]{index=3}
        }

        t0 = time.time()
        resp = _SESS.get(url, params=params, timeout=10)
        dt_ms = int((time.time() - t0) * 1000)

        if resp.status_code != 200:
            Debugging.append(f"HTTP {resp.status_code}: {resp.text[:300]}")
            result = {
                "ok": False,
                "error": f"Binance HTTP {resp.status_code}",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "latency_ms": dt_ms,
                "data": []
            }
            Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
            return Outputs

        payload = resp.json()
        # payload is list when using symbols
        if isinstance(payload, dict):
            payload = [payload]

        rows = []
        for it in payload:
            sym = it.get("symbol")
            rows.append({
                "symbol": sym,
                "price": _safe_float(it.get("lastPrice")),
                "vol_24h_base": _safe_float(it.get("volume")),
                "vol_24h_quote": _safe_float(it.get("quoteVolume")),
                "open_time_ms": it.get("openTime"),
                "close_time_ms": it.get("closeTime"),
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "source": "binance_spot_rest_ticker24hr"
            })

        result = {
            "ok": True,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "latency_ms": dt_ms,
            "count": len(rows),
            "data": rows
        }
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
##写出你需要的功能，有需要可以用Debugging输出调试信息，调试信息会在控制台输出，也会在输出节点中输出，方便调试。
# **Function definition**
