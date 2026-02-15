import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# =========================
# Node metadata
# =========================
OutPutNum = 2
InPutNum = 2

Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None,
            'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': False,
           'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个“高容错 JSON 解析”节点：把输入的原始文本/JSON（即使包含多个 JSON 拼接、夹杂杂字符、字段缺失/类型不一致）尽量解析为你需要的变量输出。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '- 支持 Input1 是 dict/list（上游已解析）、或是字符串（可含多个 JSON 对象拼在一起）\n'
    '- 使用 JSONDecoder.raw_decode 逐段扫描，尽量从长字符串中提取出多个 JSON\n'
    '- 从所有对象里找到目标 symbol 对应的记录（优先 data[] 里的 item；找不到则自动挑一条“更像币行情”的记录）\n'
    '- 按固定变量名格式输出（如 Price_BTCUSDT = 89867.62），缺字段则输出 None（不中断）\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: Raw\n    type: string|object\n    required: true\n    description: 原始 JSON 文本/对象，可包含多个 JSON 拼接在一起\n'
    '  - name: TargetSymbol\n    type: string\n    required: false\n    description: 目标交易对/符号，例如 BTCUSDT；留空则自动从数据里挑最像行情的一条\n'
    'outputs:\n'
    '  - name: Result\n    type: string\n    description: 变量赋值格式的多行文本（高容错，缺字段输出 None）\n```\n'
)

for o in Outputs:
    o['Kind'] = 'String'
for i in Inputs:
    i['Kind'] = 'String'

Inputs[0]['name'] = 'Raw'
Inputs[0]['Isnecessary'] = True
Inputs[1]['name'] = 'TargetSymbol'
Inputs[1]['Isnecessary'] = False
Outputs[0]['name'] = 'Result'
Outputs[1]['name'] = 'Params'

_LOGGER = logging.getLogger("Normal_Parse_MarketJson")
if not _LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)


def _safe_str(x: Any) -> str:
    try:
        return "" if x is None else str(x)
    except Exception:
        return ""


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None


def _safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        if isinstance(x, str):
            xs = x.strip()
            if not xs:
                return None
            if re.fullmatch(r"-?\d+(\.0+)?", xs):
                xs = xs.split(".", 1)[0]
            return int(xs)
        return int(x)
    except Exception:
        return None


def _iter_json_from_text(text: str) -> Iterable[Any]:
    """
    Extract as many JSON objects/arrays as possible from a messy string.
    Works for: '{...} {...}' or '{...}\\n{...}', and will skip junk between.
    """
    s = _safe_str(text)
    if not s:
        return

    dec = json.JSONDecoder()
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch not in "{[":
            i += 1
            continue
        try:
            obj, j = dec.raw_decode(s, i)
            yield obj
            i = j
        except Exception:
            i += 1


def _normalize_to_objects(raw: Any) -> List[Any]:
    """
    Normalize Raw into a flat list of JSON-like objects.

    Accept:
      - dict / list (already parsed)
      - string (may contain multiple JSON concatenated)
      - list/tuple of mixed pieces (multiple Raw)
    """
    if raw is None:
        return []

    # Allow multiple Raw pieces
    if isinstance(raw, (list, tuple, set)):
        out: List[Any] = []
        for it in raw:
            out.extend(_normalize_to_objects(it))
        return out

    if isinstance(raw, dict):
        return [raw]

    text = _safe_str(raw).strip()
    if not text:
        return []

    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            return [json.loads(text)]
        except Exception:
            pass

    return list(_iter_json_from_text(text))


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _parse_target_symbols(ctx: Any) -> List[str]:
    """
    TargetSymbol can be:
      - "AAPL,BTCUSDT" (or newline/space/;| separated)
      - JSON array string: ["AAPL","BTCUSDT"]
      - python list/tuple/set
    """
    if ctx is None:
        return []

    if isinstance(ctx, (list, tuple, set)):
        syms = [str(x).strip().upper() for x in ctx if str(x).strip()]
        return _dedupe_keep_order(syms)

    s = _safe_str(ctx).strip()
    if not s:
        return []

    # Try JSON array
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                syms = [str(x).strip().upper() for x in arr if str(x).strip()]
                return _dedupe_keep_order(syms)
        except Exception:
            pass

    parts = re.split(r"[\s,;|]+", s)
    syms: List[str] = []
    for p in parts:
        p = p.strip().upper()
        if not p:
            continue
        p = p.replace("/", "").replace("-", "")
        # allow AAPL / BTCUSDT style
        if re.fullmatch(r"[A-Z0-9]{1,20}", p):
            syms.append(p)
    return _dedupe_keep_order(syms)


def _score_row(r: Dict[str, Any]) -> int:
    score = 0
    for k in (
        "price", "vol_24h_base", "vol_24h_quote",
        "market_cap_usd", "fdv_usd",
        "open_time_ms", "close_time_ms",
        "circulating_supply", "total_supply", "max_supply",
        "fundamentals_last_updated",
    ):
        if r.get(k) is not None:
            score += 1
    rs = _safe_str(r.get("symbol")).strip().upper()
    if re.fullmatch(r"[A-Z0-9]{1,20}", rs or ""):
        score += 1
    if _looks_like_crypto_row(r):
        score += 3
    return score


def _select_record_for_symbol(objs: List[Any], symbol: str) -> Optional[Dict[str, Any]]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return None

    best: Optional[Dict[str, Any]] = None
    best_score = -1
    for o in objs:
        for r in _iter_candidate_records(o):
            if not isinstance(r, dict):
                continue
            if _safe_str(r.get("symbol")).strip().upper() != sym:
                continue
            sc = _score_row(r)
            if sc > best_score:
                best = r
                best_score = sc
    return best


def _iter_candidate_records(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, dict):
        if "symbol" in obj and isinstance(obj.get("symbol"), (str, int, float)):
            yield obj
        data = obj.get("data")
        if isinstance(data, list):
            for it in data:
                if isinstance(it, dict):
                    yield it
        for k in ("result", "rows", "items"):
            v = obj.get(k)
            if isinstance(v, list):
                for it in v:
                    if isinstance(it, dict):
                        yield it
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, dict):
                yield it


def _looks_like_crypto_row(r: Dict[str, Any]) -> bool:
    keys = set(r.keys())
    want = {
        "price",
        "vol_24h_base",
        "vol_24h_quote",
        "open_time_ms",
        "close_time_ms",
        "market_cap_usd",
        "fdv_usd",
        "circulating_supply",
        "total_supply",
        "max_supply",
        "fundamentals_last_updated",
    }
    return len(keys.intersection(want)) >= 3


def _select_record(objs: List[Any], target_symbol: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    sym = (target_symbol or "").strip().upper()

    # 1) exact match first
    if sym:
        for o in objs:
            for r in _iter_candidate_records(o):
                if _safe_str(r.get("symbol")).strip().upper() == sym:
                    return r, sym

    # 2) otherwise: pick best scored, strong preference for crypto-shaped rows
    best: Optional[Dict[str, Any]] = None
    best_score = -1
    best_sym: Optional[str] = None

    for o in objs:
        for r in _iter_candidate_records(o):
            if not isinstance(r, dict):
                continue
            score = 0
            for k in (
                "price", "vol_24h_base", "vol_24h_quote",
                "market_cap_usd", "fdv_usd",
                "open_time_ms", "close_time_ms",
                "circulating_supply", "total_supply", "max_supply",
                "fundamentals_last_updated",
            ):
                if r.get(k) is not None:
                    score += 1

            rs = _safe_str(r.get("symbol")).strip().upper()
            if re.fullmatch(r"[A-Z0-9]{5,20}", rs or ""):
                score += 1

            if _looks_like_crypto_row(r):
                score += 3

            if score > best_score:
                best = r
                best_score = score
                best_sym = rs or None

    if best is not None:
        return best, best_sym
    return None, sym or None


def _get_first(r: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in r and r.get(k) is not None:
            return r.get(k)
    return None


def _format_value(v: Any) -> str:
    if v is None:
        return "None"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, bool):
        return "True" if v else "False"
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return json.dumps(_safe_str(v), ensure_ascii=False)


def _build_assignments(symbol: str, r: Dict[str, Any]) -> str:
    sym = (symbol or _safe_str(r.get("symbol")) or "UNKNOWN").strip().upper() or "UNKNOWN"

    price = _safe_float(_get_first(r, ["price", "lastPrice", "last_price"]))
    vbase = _safe_float(_get_first(r, ["vol_24h_base", "volume", "vol24h_base"]))
    vquote = _safe_float(_get_first(r, ["vol_24h_quote", "quoteVolume", "vol24h_quote"]))
    mcap = _get_first(r, ["market_cap_usd", "marketCapUsd", "mcap_usd"])
    fdv = _get_first(r, ["fdv_usd", "fdvUsd", "fully_diluted_valuation"])
    circ = _get_first(r, ["circulating_supply", "circulatingSupply"])
    total = _get_first(r, ["total_supply", "totalSupply"])
    maxs = _get_first(r, ["max_supply", "maxSupply"])
    open_ms = _get_first(r, ["open_time_ms", "openTime", "open_time"])
    close_ms = _get_first(r, ["close_time_ms", "closeTime", "close_time"])
    fund_last = _get_first(r, ["fundamentals_last_updated", "fundLastUpdated", "last_updated"])

    open_i = _safe_int(open_ms)
    close_i = _safe_int(close_ms)
    if open_i is not None:
        open_ms = open_i
    if close_i is not None:
        close_ms = close_i

    # Numeric normalization (robust + avoid fake data):
    # - market cap / fdv: prefer int, fallback float
    # - supply: prefer float (keeps 19979509.0), fallback int
    def _num_int_first(v: Any) -> Any:
        vi = _safe_int(v)
        if vi is not None:
            return vi
        vf = _safe_float(v)
        if vf is not None:
            return vf
        return None

    def _num_float_first(v: Any) -> Any:
        vf = _safe_float(v)
        if vf is not None:
            return vf
        vi = _safe_int(v)
        if vi is not None:
            return float(vi)
        return None

    mcap = _num_int_first(mcap)
    fdv = _num_int_first(fdv)
    circ = _num_float_first(circ)
    total = _num_float_first(total)
    maxs = _num_float_first(maxs)

    # Collect fields: skip missing fields (no "None" lines)
    kvs: List[Tuple[str, Any]] = [
        (f"Price_{sym}", price),
        (f"Vol24hBase_{sym}", vbase),
        (f"Vol24hQuote_{sym}", vquote),
        (f"McapUsd_{sym}", mcap),
        (f"FdvUsd_{sym}", fdv),
        (f"CircSupply_{sym}", circ),
        (f"TotalSupply_{sym}", total),
        (f"MaxSupply_{sym}", maxs),
        (f"OpenTimeMs_{sym}", open_ms),
        (f"CloseTimeMs_{sym}", close_ms),
        (f"FundLastUpdated_{sym}", fund_last),
    ]

    assigns: List[str] = []
    for k, v in kvs:
        if v is None:
            continue
        assigns.append(f"{k} = {_format_value(v)}")

    return "\n\n".join(assigns).strip() + "\n"


def _build_params_only(symbol: str, r: Dict[str, Any]) -> str:
    """
    Output only variable names (no values), and only for fields that have values.
    Example:
      Price_BTCUSDT
      (blank line)
      Vol24hBase_BTCUSDT
    """
    sym = (symbol or _safe_str(r.get("symbol")) or "UNKNOWN").strip().upper() or "UNKNOWN"

    # Keep logic aligned with _build_assignments (same normalization + skip missing)
    price = _safe_float(_get_first(r, ["price", "lastPrice", "last_price"]))
    vbase = _safe_float(_get_first(r, ["vol_24h_base", "volume", "vol24h_base"]))
    vquote = _safe_float(_get_first(r, ["vol_24h_quote", "quoteVolume", "vol24h_quote"]))
    mcap = _get_first(r, ["market_cap_usd", "marketCapUsd", "mcap_usd"])
    fdv = _get_first(r, ["fdv_usd", "fdvUsd", "fully_diluted_valuation"])
    circ = _get_first(r, ["circulating_supply", "circulatingSupply"])
    total = _get_first(r, ["total_supply", "totalSupply"])
    maxs = _get_first(r, ["max_supply", "maxSupply"])
    open_ms = _get_first(r, ["open_time_ms", "openTime", "open_time"])
    close_ms = _get_first(r, ["close_time_ms", "closeTime", "close_time"])
    fund_last = _get_first(r, ["fundamentals_last_updated", "fundLastUpdated", "last_updated"])

    open_i = _safe_int(open_ms)
    close_i = _safe_int(close_ms)
    if open_i is not None:
        open_ms = open_i
    if close_i is not None:
        close_ms = close_i

    def _num_int_first(v: Any) -> Any:
        vi = _safe_int(v)
        if vi is not None:
            return vi
        vf = _safe_float(v)
        if vf is not None:
            return vf
        return None

    def _num_float_first(v: Any) -> Any:
        vf = _safe_float(v)
        if vf is not None:
            return vf
        vi = _safe_int(v)
        if vi is not None:
            return float(vi)
        return None

    mcap = _num_int_first(mcap)
    fdv = _num_int_first(fdv)
    circ = _num_float_first(circ)
    total = _num_float_first(total)
    maxs = _num_float_first(maxs)

    kvs: List[Tuple[str, Any]] = [
        (f"Price_{sym}", price),
        (f"Vol24hBase_{sym}", vbase),
        (f"Vol24hQuote_{sym}", vquote),
        (f"McapUsd_{sym}", mcap),
        (f"FdvUsd_{sym}", fdv),
        (f"CircSupply_{sym}", circ),
        (f"TotalSupply_{sym}", total),
        (f"MaxSupply_{sym}", maxs),
        (f"OpenTimeMs_{sym}", open_ms),
        (f"CloseTimeMs_{sym}", close_ms),
        (f"FundLastUpdated_{sym}", fund_last),
    ]

    keys: List[str] = []
    for k, v in kvs:
        if v is None:
            continue
        keys.append(k)

    return "\n\n".join(keys).strip() + "\n"


def run_node(node):
    raw = node['Inputs'][0].get('Context')
    target_symbol = node['Inputs'][1].get('Context')

    try:
        objs = _normalize_to_objects(raw)
        if not objs:
            Outputs[0]['Context'] = _build_assignments("UNKNOWN", {})
            Outputs[1]['Context'] = _build_params_only("UNKNOWN", {})
            return Outputs

        targets = _parse_target_symbols(target_symbol)
        if targets:
            blocks: List[str] = []
            key_blocks: List[str] = []
            for sym in targets:
                rec = _select_record_for_symbol(objs, sym)
                r = rec or {"symbol": sym}
                blocks.append(_build_assignments(sym, r).rstrip())
                key_blocks.append(_build_params_only(sym, r).rstrip())
            Outputs[0]['Context'] = "\n\n".join([b for b in blocks if b]).rstrip() + "\n"
            Outputs[1]['Context'] = "\n\n".join([b for b in key_blocks if b]).rstrip() + "\n"
            return Outputs

        rec, sym_used = _select_record(objs, _safe_str(target_symbol))
        if rec is None:
            Outputs[0]['Context'] = _build_assignments(sym_used or "UNKNOWN", {})
            Outputs[1]['Context'] = _build_params_only(sym_used or "UNKNOWN", {})
            return Outputs

        Outputs[0]['Context'] = _build_assignments(sym_used or _safe_str(rec.get("symbol")) or "UNKNOWN", rec)
        Outputs[1]['Context'] = _build_params_only(sym_used or _safe_str(rec.get("symbol")) or "UNKNOWN", rec)
        return Outputs

    except Exception as e:
        _LOGGER.exception("Parse failed: %s", repr(e))
        Outputs[0]['Context'] = "# parse_error: " + repr(e) + "\n" + _build_assignments("UNKNOWN", {})
        Outputs[1]['Context'] = ""
        return Outputs


