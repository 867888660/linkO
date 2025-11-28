import json
import os
import copy
import time
import random
from datetime import datetime
from typing import Dict, Any, List, Iterable
import requests
import math
import re
from datetime import timezone
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# 全局会话，带 UA 提高稳定性
SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-screen/1.0"})

# **Define the number of outputs and inputs**
OutPutNum = 2
InPutNum = 12  # 包含 offset_end（-1 忽略，>0 生效）
# **Define the number of outputs and inputs**

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs  = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}',  'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}',  'Link': 0, 'IsLabel': True} for i in range(InPutNum)]
# **Initialize Outputs and Inputs arrays and assign names directly**

NodeKind = 'passivityTrigger'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction = '组件功能：Agent A（爬虫+初筛，passivityTrigger 模式）。功能概览：1) 逐页抓取 /markets（withTokens/withClobTokenIds/withOutcomes），提取 clob tokenId；2) 批量调用 /prices 获取 YES ask；3) 为每个 token 计算盘口 L1（best bid/ask）、自适应 1¢ 带宽内深度、订单聚集度、带内 VWAP，并计算期限指标（days_to_end、daily_eff_if_win、apr_eff_if_win）；4) 先按价格区间 [min_yes, max_yes] 筛选，再按 l1_spread_c（L1 价差上限，单位美分）与 min_depth_1c_usd（1¢ 带宽内买卖深度较小值的美元下限）二次过滤；5) 每页处理完即单独落盘 JSON，包含规则/来源/URL 与各选项细节；6) 支持 offset_end：-1 为无上限模式（按 limit 递进，遇尾页暂停），>0 为边界模式（从 offset_start 递增至 offset_end 后停止，不回绕）；7) 每次仅处理一页并返回（Save_Path, DeBug），内部以 node._state.next_offset 记忆续跑位置。'

# =====================
# 严格逐行设置入/出参属性（无 offset_end）
# =====================

Inputs[0]['Kind'] = 'Num'
Inputs[0]['name'] = 'limit'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = True
Inputs[0]['Num'] = 1

Inputs[1]['Kind'] = 'Num'
Inputs[1]['name'] = 'offset_start'
Inputs[1]['Isnecessary'] = True
Inputs[1]['IsLabel'] = True
Inputs[1]['Num'] = 0

Inputs[2]['Kind'] = 'Boolean'
Inputs[2]['name'] = 'closed'
Inputs[2]['Isnecessary'] = True
Inputs[2]['IsLabel'] = True
Inputs[2]['Boolean'] = False

Inputs[3]['Kind'] = 'Num'
Inputs[3]['name'] = 'min_yes'
Inputs[3]['Isnecessary'] = True
Inputs[3]['IsLabel'] = True
Inputs[3]['Num'] = 0.01

Inputs[4]['Kind'] = 'Num'
Inputs[4]['name'] = 'max_yes'
Inputs[4]['Isnecessary'] = True
Inputs[4]['IsLabel'] = True
Inputs[4]['Num'] = 0.99

Inputs[5]['Kind'] = 'Num'
Inputs[5]['name'] = 'chunk'
Inputs[5]['Isnecessary'] = True
Inputs[5]['IsLabel'] = True
Inputs[5]['Num'] = 1

Inputs[6]['Kind'] = 'Num'
Inputs[6]['name'] = 'workers'
Inputs[6]['Isnecessary'] = True
Inputs[6]['IsLabel'] = True
Inputs[6]['Num'] = 3  # 预留

Inputs[7]['Kind'] = 'Num'
Inputs[7]['name'] = 'retry'
Inputs[7]['Isnecessary'] = True
Inputs[7]['IsLabel'] = True
Inputs[7]['Num'] = 1

Inputs[8]['Kind'] = 'String_FilePath'
Inputs[8]['name'] = 'save_path'
Inputs[8]['Isnecessary'] = True
Inputs[8]['IsLabel'] = True

# —— 新增两个可选阈值入参 ——
Inputs[9]['Kind'] = 'Num'
Inputs[9]['name'] = 'l1_spread_c'
Inputs[9]['Isnecessary'] = False
Inputs[9]['IsLabel'] = True
Inputs[9]['Num'] = 3  # 默认 3 美分

Inputs[10]['Kind'] = 'Num'
Inputs[10]['name'] = 'min_depth_1c_usd'
Inputs[10]['Isnecessary'] = False
Inputs[10]['IsLabel'] = True
Inputs[10]['Num'] = 100  # 默认 $100

Inputs[11]['Kind'] = 'Num'
Inputs[11]['name'] = 'offset_end'
Inputs[11]['Isnecessary'] = True
Inputs[11]['IsLabel'] = True
Inputs[11]['Num'] = -1

Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Save_Path'

Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'DeBug'

# =====================
# Polymarket API 工具
# =====================
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

def _backoff_sleep(attempt: int):
    time.sleep((2 ** attempt) * 0.2 + random.random() * 0.3)

def robust_get(url: str, params: Dict[str, Any] = None, retry: int = 2, timeout: int = 12) -> Any:
    for k in range(retry + 1):
        try:
            r = SESS.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        _backoff_sleep(k)
    raise RuntimeError(f"GET 失败: {url} params={params}")

def robust_post(url: str, json_body: Dict[str, Any], retry: int = 2, timeout: int = 12) -> Any:
    for k in range(retry + 1):
        try:
            r = SESS.post(url, json=json_body, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        _backoff_sleep(k)
    raise RuntimeError(f"POST 失败: {url} body_keys={list(json_body.keys())}")

def _as_list(x):
    """把 x 规范成 list。x 可能本来就是 list，也可能是 '[...]' 字符串。失败就返回 []。"""
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        s = x.strip()
        if s.startswith('[') and s.endswith(']'):
            try:
                v = json.loads(s)
                if isinstance(v, list):
                    return v
            except Exception:
                pass
    return []

def extract_token_ids_from_market_stub(stub: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    v = stub.get("clobTokenIds")

    def _add_one(x):
        if x is None:
            return
        s = str(x).strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()
        if s:
            ids.append(s)

    # ① clobTokenIds
    if isinstance(v, list):
        for x in v:
            if isinstance(x, dict):
                for key in ("id", "tokenId", "value"):
                    if key in x and x[key]:
                        _add_one(x[key]); break
            else:
                _add_one(x)
    elif isinstance(v, str):
        s = v.strip()
        if s.startswith('[') and s.endswith(']'):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    for x in arr: _add_one(x)
            except Exception:
                for t in s.strip('[]').split(','): _add_one(t)
        else:
            for t in s.split(','): _add_one(t)

    # ② tokens / outcomeTokens / yesToken / noToken
    for key in ("tokens", "outcomeTokens"):
        tv = stub.get(key)
        if isinstance(tv, list):
            for x in tv:
                if isinstance(x, dict):
                    for k in ("tokenId", "id", "value"):
                        if k in x and x[k]:
                            _add_one(x[k]); break
    for key in ("yesToken", "noToken"):
        yv = stub.get(key)
        if isinstance(yv, dict):
            for k in ("tokenId", "id", "value"):
                if k in yv and yv[k]:
                    _add_one(yv[k]); break

    # ③ 详情页补全
    if len(ids) < 2:
        mid = stub.get("id")
        if mid:
            try:
                detail = robust_get(
                    f"{GAMMA}/markets/{mid}",
                    params={"withTokens": "true", "withClobTokenIds": "true"},
                    retry=1
                )
                for key in ("clobTokenIds", "tokens", "outcomeTokens", "yesToken", "noToken"):
                    dv = detail.get(key)
                    if isinstance(dv, list):
                        for x in dv:
                            if isinstance(x, dict):
                                for k in ("tokenId", "id", "value"):
                                    if k in x and x[k]:
                                        _add_one(x[k]); break
                            else:
                                _add_one(x)
                    elif isinstance(dv, dict):
                        for k in ("tokenId", "id", "value"):
                            if k in dv and dv[k]:
                                _add_one(dv[k])
                    elif isinstance(dv, str):
                        s2 = dv.strip()
                        if s2.startswith('[') and s2.endswith(']'):
                            try:
                                arr2 = json.loads(s2)
                                if isinstance(arr2, list):
                                    for x in arr2: _add_one(x)
                            except Exception:
                                for t in s2.strip('[]').split(','): _add_one(t)
                        else:
                            for t in s2.split(','): _add_one(t)
            except Exception:
                pass

    seen = set(); out: List[str] = []
    for x in ids:
        if x and x not in seen:
            seen.add(x); out.append(x)
    return out

def fetch_markets(limit: int, offset: int, closed: bool, retry: int) -> List[Dict[str, Any]]:
    params = {
        "limit": limit,
        "offset": offset,
        "closed": str(closed).lower(),
        "withTokens": "true",
        "withClobTokenIds": "true",
        "withOutcomes": "true"
    }
    data = robust_get(f"{GAMMA}/markets", params=params, retry=retry)
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []

def fetch_yes_asks(token_ids: List[str], retry: int) -> Dict[str, float]:
    asks: Dict[str, float] = {}
    if not token_ids:
        return asks

    payload = [{"token_id": tid, "side": "BUY"} for tid in token_ids]
    try:
        r = SESS.post(f"{CLOB}/prices", json=payload, timeout=8)
        if r.status_code == 200:
            js = r.json() or []
            price_map = {}
            if isinstance(js, list):
                for item in js:
                    tid = str(item.get("token_id") or item.get("id") or item.get("tokenId") or "").strip()
                    p = item.get("price")
                    if tid and p is not None:
                        price_map[tid] = float(p)
            elif isinstance(js, dict):
                for k, v in js.items():
                    if isinstance(v, dict) and v.get("price") is not None:
                        price_map[str(k)] = float(v["price"])
            for tid in token_ids:
                if tid in price_map:
                    asks[tid] = price_map[tid]
    except Exception:
        pass

    # 兜底：单点 /price 只补缺口
    missing = [tid for tid in token_ids if tid not in asks]
    for tid in missing:
        try:
            rr = SESS.get(f"{CLOB}/price", params={"token_id": tid, "side": "BUY"}, timeout=6)
            if rr.status_code == 200:
                pj = rr.json() or {}
                if pj.get("price") is not None:
                    asks[tid] = float(pj["price"])
        except Exception:
            continue

    return asks

def fetch_best_levels(token_id: str, retry: int = 1, timeout: int = 6, debug_lines=None):
    """返回 (best_bid, best_ask)。优先 /book；缺失则用 /price 兜底。"""
    def _to_price(x):
        if isinstance(x, dict):
            return float(x.get("price")) if x.get("price") is not None else None
        if isinstance(x, (list, tuple)) and len(x) >= 1:
            return float(x[0])
        return None

    best_bid = None
    best_ask = None

    # 先尝试 /book
    for k in range(retry + 1):
        try:
            r = SESS.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=timeout)
            if r.status_code == 200:
                js = r.json() or {}
                bids = js.get("bids") or []
                asks = js.get("asks") or []
                bid_prices = [_to_price(x) for x in bids if _to_price(x) is not None]
                ask_prices = [_to_price(x) for x in asks if _to_price(x) is not None]
                best_bid = max(bid_prices) if bid_prices else None
                best_ask = min(ask_prices) if ask_prices else None
                if debug_lines is not None:
                    debug_lines.append(f"[book] tid={token_id[:12]}… nbid={len(bids)} nask={len(asks)} bid_top={best_bid} ask_top={best_ask}")
                break
        except Exception:
            pass
        _backoff_sleep(k)

    # 兜底：/price
    if best_bid is None:
        try:
            rr = SESS.get(f"{CLOB}/price", params={"token_id": token_id, "side": "SELL"}, timeout=timeout)
            if rr.status_code == 200:
                pj = rr.json() or {}
                if pj.get("price") is not None:
                    best_bid = float(pj["price"])
        except Exception:
            pass
    if best_ask is None:
        try:
            rr = SESS.get(f"{CLOB}/price", params={"token_id": token_id, "side": "BUY"}, timeout=timeout)
            if rr.status_code == 200:
                pj = rr.json() or {}
                if pj.get("price") is not None:
                    best_ask = float(pj["price"])
        except Exception:
            pass

    return best_bid, best_ask

def compute_depth_1c_usd(token_id: str, retry: int = 1, timeout: int = 6):
    """
    返回:
      (best_bid, best_ask,
       depth_bid_1c_usd, depth_ask_1c_usd,
       n_bid_1c, n_ask_1c,
       top_conc_bid_1c, top_conc_ask_1c,
       band_c_used,                   # ← 新增：实际使用的价带（美分）
       depth_bid_1c_qty, depth_ask_1c_qty,   # ← 新增：带内张数（数量）
       vwap_bid_1c, vwap_ask_1c)             # ← 新增：带内成交均价（估算滑点用）

    自适应带宽：默认 1¢，贴近 0/1 时按 mid 自动收窄，上限仍为 1¢。
    """
    def _to_ps(x):
        if isinstance(x, dict):           return x.get("price"), x.get("size")
        if isinstance(x, (list, tuple)):  return (x[0] if len(x) > 0 else None), (x[1] if len(x) > 1 else None)
        return None, None

    for k in range(retry + 1):
        try:
            r = SESS.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=timeout)
            if r.status_code != 200:
                _backoff_sleep(k); continue
            js = r.json() or {}
            bids = js.get("bids") or []
            asks = js.get("asks") or []

            bid_prices = []; ask_prices = []
            for b in bids:
                p,_ = _to_ps(b);  bid_prices.append(float(p)) if p is not None else None
            for a in asks:
                p,_ = _to_ps(a);  ask_prices.append(float(p)) if p is not None else None

            best_bid = max(bid_prices) if bid_prices else None
            best_ask = min(ask_prices) if ask_prices else None

            # —— 自适应带宽 —— #
            band = 0.01
            if best_bid is not None and best_ask is not None:
                mid = 0.5 * (best_bid + best_ask)
                band = min(0.01, 0.1 * mid, 0.1 * (1.0 - mid))
            band_c_used = round(band * 100.0, 2)  # 美分

            th_bid = None if best_bid is None else max(0.001, best_bid - band)
            th_ask = None if best_ask is None else min(0.999, best_ask + band)

            depth_bid_usd = 0.0; depth_bid_qty = 0.0; n_bid = 0; max_bid_val = 0.0
            depth_ask_usd = 0.0; depth_ask_qty = 0.0; n_ask = 0; max_ask_val = 0.0

            if th_bid is not None:
                for b in bids:
                    p,s = _to_ps(b)
                    if p is None or s is None: continue
                    p = float(p); s = float(s)
                    if p >= th_bid:
                        val = p * s
                        depth_bid_usd += val
                        depth_bid_qty += s
                        n_bid += 1
                        if val > max_bid_val: max_bid_val = val

            if th_ask is not None:
                for a in asks:
                    p,s = _to_ps(a)
                    if p is None or s is None: continue
                    p = float(p); s = float(s)
                    if p <= th_ask:
                        val = p * s
                        depth_ask_usd += val
                        depth_ask_qty += s
                        n_ask += 1
                        if val > max_ask_val: max_ask_val = val

            top_conc_bid = (max_bid_val / depth_bid_usd) if depth_bid_usd > 0 else 0.0
            top_conc_ask = (max_ask_val / depth_ask_usd) if depth_ask_usd > 0 else 0.0

            vwap_bid = (depth_bid_usd / depth_bid_qty) if depth_bid_qty > 0 else 0.0
            vwap_ask = (depth_ask_usd / depth_ask_qty) if depth_ask_qty > 0 else 0.0

            return (best_bid, best_ask,
                    depth_bid_usd, depth_ask_usd,
                    n_bid, n_ask,
                    top_conc_bid, top_conc_ask,
                    band_c_used,
                    depth_bid_qty, depth_ask_qty,
                    vwap_bid, vwap_ask)
        except Exception:
            _backoff_sleep(k)

    return (None, None, 0.0, 0.0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

def fetch_turnover_60m_usd(token_id: str, retry: int = 1, timeout: int = 8, debug_lines=None):
    """
    返回 (turnover_usd, fills_count)；简单实现：抓近 60 分钟成交并累加 price*size。
    兼容两种形态：dict 或 [price, size, ts]。若接口不可用，返回 (0.0, 0)。
    """
    since = int(time.time()) - 3600
    params_list = [
        {"token_id": token_id, "start_time": since},  # 常见形态
        {"token_id": token_id, "since": since},       # 备选参数名
    ]
    for p in params_list:
        for k in range(retry + 1):
            try:
                # 优先 /trades，失败再试 /fills
                for ep in ("/trades", "/fills"):
                    if debug_lines is not None:
                        debug_lines.append(f"[turnover-q] ep={ep} params={p}")
                    r = SESS.get(f"{CLOB}{ep}", params=p, timeout=timeout)
                    if r.status_code == 200:
                        arr = r.json() or []
                        if debug_lines is not None:
                            debug_lines.append(f"[turnover-r] status={r.status_code} len={len(arr) if isinstance(arr, list) else 'NA'}")
                        tot = 0.0; n = 0
                        for t in arr:
                            if isinstance(t, dict):
                                pr = t.get("price"); sz = t.get("size")
                            elif isinstance(t, (list, tuple)) and len(t) >= 2:
                                pr, sz = t[0], t[1]
                            else:
                                pr, sz = None, None
                            if pr is not None and sz is not None:
                                try:
                                    tot += float(pr) * float(sz)
                                    n += 1
                                except Exception:
                                    pass
                        return tot, n
                    else:
                        if debug_lines is not None:
                            debug_lines.append(f"[turnover-r] status={r.status_code} len=NA")
            except Exception:
                pass
            _backoff_sleep(k)
    return 0.0, 0

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def autogen_filename() -> str:
    return f"polymarket_json_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

def _parse_end_ts_safe(end_date_str: str) -> float:
    """将 ISO8601 time 转 UTC 时间戳，容错 Z / +00:00 / 无 tz 的情况。失败返回 0."""
    if not end_date_str:
        return 0.0
    try:
        s = end_date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0

def _normalize_rules(s: str) -> str:
    if not s: return ""
    # 换行类标签先替换成换行，其他标签去掉
    s = re.sub(r"(?i)</?(br|p|div|li|ul|ol|h\d)\b[^>]*>", "\n", s)
    s = re.sub(r"(?i)<a\b[^>]*>(.*?)</a>", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    # 压缩多余空白
    lines = [ln.strip() for ln in s.splitlines()]
    s = "\n".join([ln for ln in lines if ln])
    return s

def _round_if_finite(x, nd=6):
    if x is None:
        return None
    try:
        if isinstance(x, float) and not math.isfinite(x):
            return None
        return round(x, nd)
    except Exception:
        return None

# **Function definition**
def run_node(node):
    """
    单次调用仅处理一页（一个 offset），立刻返回一组 Outputs。
    偏移量通过 node['_state']['next_offset'] 记忆，以便持续运行时从上次位置继续。
    """
    Array = []

    # 读取输入
    limit        = int(node['Inputs'][0]['Num'])
    offset_start = int(node['Inputs'][1]['Num'])
    _closed_input = node['Inputs'][2]
    _closed_raw = _closed_input.get('Boolean')
    if _closed_raw is None:
        _closed_raw = _closed_input.get('Num') or _closed_input.get('Context')
    closed       = bool(_closed_raw)
    min_yes      = float(node['Inputs'][3]['Num'])
    max_yes      = float(node['Inputs'][4]['Num'])
    chunk        = int(node['Inputs'][5]['Num'])
    workers      = int(node['Inputs'][6]['Num'])  # 预留，不在本版本使用
    retry        = int(node['Inputs'][7]['Num'])
    _sp_dict     = node['Inputs'][8]
    _raw_save_path = _sp_dict.get('Context') if isinstance(_sp_dict, dict) else None
    if not _raw_save_path:
        _raw_save_path = _sp_dict.get('Num') if isinstance(_sp_dict, dict) else None
    save_path = str(_raw_save_path).strip() if _raw_save_path else "./output"

    # 新增：读取阈值
    l1_spread_c_thr = node['Inputs'][9]['Num']  if node['Inputs'][9]['Num']  is not None else None
    min_depth_1c = node['Inputs'][10]['Num'] if node['Inputs'][10]['Num'] is not None else None
    # 新增：offset_end（-1 忽略；>0 生效）
    try:
        offset_end = int(node['Inputs'][11]['Num']) if node['Inputs'][11]['Num'] is not None else -1
    except Exception:
        offset_end = -1

    ensure_dir(save_path)

    # —— 取本次要处理的 offset（带状态续跑）——
    state = node.setdefault('_state', {})
    off = int(state.get('next_offset', offset_start))
    # 若启用 offset_end，则把 off 约束在 [offset_start, offset_end] 范围内；越界则钳制到边界（不回绕）
    bounded_mode = (offset_end is not None and offset_end > 0)
    if bounded_mode:
        if off < offset_start:
            off = offset_start
        if off > offset_end:
            off = offset_end

    debug_lines: List[str] = []
    debug_lines.append(f"config: limit={limit}, offset=[{off},{off}], offset_end={offset_end}, bounded_mode={bounded_mode}, closed={closed}, min_yes={min_yes}, max_yes={max_yes}, chunk={chunk}, workers={workers}, retry={retry}")
    debug_lines.append(f"save_path=\n{save_path}")
    debug_lines.append(f"filters: l1_spread_c<={l1_spread_c_thr}¢, min_depth_1c_usd>={min_depth_1c}")

    # 1) 抓取该页 /markets
    # 在调用 fetch_markets(...) 之前加：
    if bounded_mode and off >= offset_end:
        node['_state']['finished'] = True
        return Array   # 直接停止，不抓末页
    stubs_all: List[Dict[str, Any]] = fetch_markets(limit=limit, offset=off, closed=closed, retry=retry)
    markets_fetched = len(stubs_all)
    debug_lines.append(f"markets_fetched={markets_fetched}")

    # 不在列表页做 outcomes 过滤；很多条目列表页不回这个字段
    stubs = stubs_all
    debug_lines.append(f"kept_markets={len(stubs)}  # no-filter; use detail to extract tokens/options")
    if stubs:
        try:
            first_stub = stubs[0]
            debug_lines.append("stub_keys_sample=" + ",".join(list(first_stub.keys())[:15]))
            for k in ("clobTokenIds", "tokens", "outcomeTokens", "yesToken", "noToken"):
                v = first_stub.get(k)
                if isinstance(v, list):
                    debug_lines.append(f"{k}_len={len(v)}")
                elif v is not None:
                    debug_lines.append(f"{k}_type={type(v).__name__}")
        except Exception:
            pass

    # 2) 提取 tokenIds（优先用 outcomes 里的 clobTokenId，并记录『大类/小类』）
    market_map: Dict[str, Dict[str, Any]] = {}   # mid -> {condition_id, question, endDate, options: []}
    token_meta: Dict[str, Dict[str, Any]]  = {}  # tid -> {mid, option_name}
    token_ids: List[str] = []

    for stub in stubs:
        mid = stub.get("id")
        market_map[mid] = {
            "condition_id": stub.get("conditionId") or stub.get("condition_id") or mid,
            "question": stub.get("question") or stub.get("title") or "",
            "endDate": stub.get("endDate") or stub.get("end_time") or stub.get("endTime") or "",
            # 新增：把规则/来源/slug 先存起来
            "rules": _normalize_rules(stub.get("description") or ""),
            "resolutionSource": stub.get("resolutionSource") or stub.get("resolution_source") or "",
            "slug": stub.get("slug") or "",
            "options": []
        }
        # 优先：从 outcomes 取 (name, clobTokenId)
        outs = stub.get("outcomes") or []
        for o in outs:
            if not isinstance(o, dict): 
                continue
            name = (o.get("name") or o.get("outcome") or "").strip()
            tid  = o.get("clobTokenId") or o.get("tokenId") or o.get("token_id")
            if tid and name:
                tid = str(tid)
                if tid not in token_meta:
                    token_meta[tid] = {"mid": mid, "option_name": name}
                    token_ids.append(tid)

        # 兜底：若 outcomes 里没拿到任何 tid，则回退你原来的提取函数（名称先留空，后续用详情回填）
        if not any(x.get("mid")==mid for x in token_meta.values()):
            tids_fallback = extract_token_ids_from_market_stub(stub)
            for idx, tid in enumerate(tids_fallback):
                if tid not in token_meta:
                    token_meta[tid] = {"mid": mid, "option_name": ""}
                    token_ids.append(tid)

    debug_lines.append(f"token_ids={len(token_ids)} -> sample={token_ids[:10]}")

    # —— 回填未命名 token 的真实选项名（用详情 /markets/{id}）——
    need_detail_mids = set()
    for tid, meta in token_meta.items():
        if not meta.get("option_name"):
            need_detail_mids.add(meta["mid"]) 

    for mid in need_detail_mids:
        try:
            detail = robust_get(
                f"{GAMMA}/markets/{mid}",
                params={"withOutcomes": "true", "withTokens": "true", "withClobTokenIds": "true"},
                retry=1
            )
            if not isinstance(detail, dict):
                continue
            # 若列表页没给或给得不完整，用详情页兜底回填
            if not market_map.get(mid, {}).get("rules"):
                market_map[mid]["rules"] = _normalize_rules(detail.get("description") or market_map[mid].get("rules") or "")
                debug_lines.append(f"[rules-source] mid={mid} <- detail.description")
            else:
                debug_lines.append(f"[rules-source] mid={mid} <- list.description")
            if not market_map.get(mid, {}).get("resolutionSource"):
                market_map[mid]["resolutionSource"] = detail.get("resolutionSource") or detail.get("resolution_source") or market_map[mid].get("resolutionSource") or ""
            if not market_map.get(mid, {}).get("slug"):
                market_map[mid]["slug"] = detail.get("slug") or market_map[mid].get("slug") or ""
            # 👉【新增调试】看清楚 detail 结构
            debug_lines.append(f"[detail] mid={mid} keys={list(detail.keys())[:20]}")
            outs_dbg = detail.get("outcomes")
            debug_lines.append(f"[detail] outcomes_type={type(outs_dbg).__name__} len={len(outs_dbg) if isinstance(outs_dbg, list) else 'NA'}")
            try:
                debug_lines.append(f"[detail] outcomes_head={repr(outs_dbg[:2]) if isinstance(outs_dbg, list) else str(outs_dbg)[:120]}")
            except Exception:
                pass
            # —— 在 for mid in need_detail_mids: 循环中，拿到 detail 之后，立刻插入 —— 
            yt = (detail.get("yesToken") or {}) if isinstance(detail, dict) else {}
            nt = (detail.get("noToken")  or {}) if isinstance(detail, dict) else {}
            yt_id = str(yt.get("tokenId") or yt.get("id") or yt.get("token_id") or "")
            nt_id = str(nt.get("tokenId") or nt.get("id") or nt.get("token_id") or "")

            tokens_list   = detail.get("tokens") or detail.get("marketsTokens") or []
            outcomes_list = detail.get("outcomes") or []

            debug_lines.append(
                f"[detail] mid={mid} "
                f"yesTokenId={'<none>' if not yt_id else yt_id[:10]+'…'} "
                f"noTokenId={'<none>' if not nt_id else nt_id[:10]+'…'} "
                f"tokens_len={len(tokens_list)} outcomes_len={len(outcomes_list)}"
            )

            # 打印 tokens[] 前3项的关键键名，看看有没有 label/outcome/name 以及 token_id/id
            try:
                tok_preview = []
                for t in tokens_list[:3]:
                    if isinstance(t, dict):
                        tok_preview.append({
                            "keys": list(t.keys())[:6],
                            "tokenId": str(t.get("token_id") or t.get("id") or t.get("tokenId") or "")[:10] + "…",
                            "label": (t.get("label") or t.get("outcome") or t.get("name") or "")
                        })
                debug_lines.append(f"[detail] tokens_preview={json.dumps(tok_preview, ensure_ascii=False)}")
            except Exception:
                pass

            # 打印 outcomes[] 前3项里是否带 clobTokenId 及 name/outcome
            try:
                out_preview = []
                for o in outcomes_list[:3]:
                    if isinstance(o, dict):
                        out_preview.append({
                            "keys": list(o.keys())[:6],
                            "clobTokenId": str(o.get("clobTokenId") or o.get("tokenId") or o.get("token_id") or "")[:10] + "…",
                            "name": (o.get("name") or o.get("outcome") or "")
                        })
                debug_lines.append(f"[detail] outcomes_preview={json.dumps(out_preview, ensure_ascii=False)}")
            except Exception:
                pass

            # 打印该 mid 下“仍未命名”的 tid，便于对比 yes/no 是否能对齐
            try:
                unknown_tids = [tid for tid, meta in token_meta.items() if meta["mid"] == mid and not meta.get("option_name")]
                debug_lines.append(f"[detail] unknown_tids={ [t[:10]+'…' for t in unknown_tids[:6]] } (total={len(unknown_tids)})")
            except Exception:
                pass

            name_map = {}

            # ① 先尝试：outcomes 是 dict 列表（你已有的逻辑，不改）
            for o in detail.get("outcomes") or []:
                if isinstance(o, dict):
                    t = o.get("clobTokenId") or o.get("tokenId") or o.get("token_id")
                    n = (o.get("name") or o.get("outcome") or "").strip()
                    if t and n:
                        name_map[str(t)] = n

            # ② 兜底 A：outcomes 其实是 **字符串** 或 **字符串列表**（如 ["Yes","No"]）
            #    同时 clobTokenIds 也可能是字符串：把两者都规范成 list，再按顺序 zip
            if not name_map:
                outs_norm = _as_list(detail.get("outcomes"))
                clob_ids  = _as_list(detail.get("clobTokenIds"))
                # outs_norm 可能是 ["Yes","No"] 或 [{"name":"A"}, ...]；这里只处理纯字符串的情况
                if outs_norm and clob_ids and len(outs_norm) == len(clob_ids) and all(isinstance(x, str) for x in outs_norm):
                    for n, t in zip(outs_norm, clob_ids):
                        name_map[str(t)] = n.strip()

            # ③ 兜底 B：tokens / marketsTokens（你已有的逻辑，保留）
            for tkn in (detail.get("tokens") or detail.get("marketsTokens") or []):
                if isinstance(tkn, dict):
                    t = tkn.get("token_id") or tkn.get("id") or tkn.get("tokenId")
                    n = (tkn.get("label") or tkn.get("outcome") or tkn.get("name") or "").strip()
                    if t and n:
                        name_map[str(t)] = n

            # 回填
            for tid, meta in token_meta.items():
                if meta["mid"] == mid and not meta.get("option_name"):
                    meta["option_name"] = name_map.get(tid) or "Unknown"
            # —— 在完成 name_map 回填之后立刻插入 —— 
            try:
                still_unknown = [tid for tid, meta in token_meta.items() if meta["mid"] == mid and not meta.get("option_name")]
                debug_lines.append(f"[detail] after_fill unknown_left={ [t[:10]+'…' for t in still_unknown[:6]] } (total={len(still_unknown)})")
            except Exception:
                pass
        except Exception:
            pass

    # 👉【新增兜底】如果某个 mid 只有 2 个 token 且都没名字，就按 Yes/No 命名
    from collections import defaultdict
    mid_to_tids = defaultdict(list)
    for tid, meta in token_meta.items():
        mid_to_tids[meta["mid"]].append(tid)

    for _mid, tid_list in mid_to_tids.items():
        # 只在刚好两个 token 且这两枚都没有名字时，做最保守的 Yes/No 兜底
        unnamed = [t for t in tid_list if not (token_meta.get(t) and token_meta[t].get("option_name"))]
        if len(tid_list) == 2 and len(unnamed) == 2:
            # 稳定顺序：沿用你前面收集 token_ids 的顺序
            t0, t1 = tid_list[0], tid_list[1]
            token_meta[t0]["option_name"] = token_meta[t0].get("option_name") or "Yes"
            token_meta[t1]["option_name"] = token_meta[t1].get("option_name") or "No"
            debug_lines.append(f"[fallback] mid={_mid} set names by binary default: {t0[:12]}…->Yes, {t1[:12]}…->No")

    # 3) /prices YES ask
    yes_asks: Dict[str, float] = {}
    batches = [token_ids[i:i + max(1, chunk)] for i in range(0, len(token_ids), max(1, chunk))]

    # workers 来自输入；≤0 时兜底为 1
    max_workers = max(1, int(workers))
    if max_workers == 1 or len(batches) <= 1:
        # 退化为串行，行为与旧版一致
        for batch in batches:
            try:
                part = fetch_yes_asks(batch, retry=retry)
                if part: yes_asks.update(part)
            except Exception:
                continue
    else:
        # 并行抓取各批
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = [ex.submit(fetch_yes_asks, batch, retry) for batch in batches]
            for fut in as_completed(futs):
                try:
                    part = fut.result() or {}
                    if part: yes_asks.update(part)
                except Exception:
                    # 忽略单批失败，保持整体健壮
                    pass
    debug_lines.append(f"yes_asks_found={len(yes_asks)}")
    if len(yes_asks) == 0 and token_ids:
        try:
            data_post = robust_post(f"{GAMMA}/prices", json_body={"ids": token_ids}, retry=retry)
            preview_post = json.dumps(data_post, ensure_ascii=False)[:300]
            debug_lines.append(f"prices_post_preview={preview_post}")
        except Exception:
            debug_lines.append("prices_post_preview=<error>")
        try:
            qs = ",".join(token_ids)
            data_get = robust_get(f"{GAMMA}/prices", params={"ids": qs}, retry=retry)
            preview_get = json.dumps(data_get, ensure_ascii=False)[:300]
            debug_lines.append(f"prices_get_preview={preview_get}")
        except Exception:
            debug_lines.append("prices_get_preview=<error>")

    # 4) 区间筛选并按『大类/小类』组装
    market_records: Dict[str, Dict[str, Any]] = {}  # mid -> obj
    # —— 新增：统计筛选计数，便于确认阈值生效 —— #
    n_total_yes = len(yes_asks)
    n_price_filtered = 0
    n_spread_filtered = 0
    n_depth_filtered = 0
    n_kept = 0

    for tid, askv in yes_asks.items():
        try:
            price = float(askv)
        except Exception:
            continue
        if price < min_yes or price > max_yes:
            n_price_filtered += 1
            continue

        # —— 新的：L1 spread + 1¢ 深度 —— #
        (best_bid, best_ask,
         depth_bid_1c, depth_ask_1c,
         n_bid_1c, n_ask_1c,
         topc_bid_1c, topc_ask_1c,
         band_c_used,
         depth_bid_1c_qty, depth_ask_1c_qty,
         vwap_bid_1c, vwap_ask_1c) = compute_depth_1c_usd(tid, retry=retry)
        l1_spread_c_val = None
        if best_bid is not None and best_ask is not None:
            try:
                # 向上取整，避免 0.3¢ 计为 0
                l1_spread_c_val = int(math.ceil(max(0.0, (best_ask - best_bid) * 100.0) - 1e-9))
            except Exception:
                l1_spread_c_val = None

        depth_1c_min = min(depth_bid_1c, depth_ask_1c)

        # 先拿 meta & mid & opt_name ！！（提前到这里）
        meta_t = token_meta.get(tid)
        if not meta_t:
            continue
        mid = meta_t["mid"]
        opt_name = meta_t["option_name"]

        # —— 计算期限与"如果赢"的复利年化/日化 —— #
        end_ts = _parse_end_ts_safe(market_map.get(mid, {}).get("endDate"))
        delta_days = (end_ts - time.time()) / 86400.0

        roi_if_win = (1.0 - price) / price

        if delta_days <= 0:
            daily_eff_if_win = None
            apr_eff_if_win   = None
        else:
            if price <= 0.0:
                daily_eff_if_win = float('inf')
                apr_eff_if_win   = float('inf')
            elif price >= 1.0:
                daily_eff_if_win = 0.0
                apr_eff_if_win   = 0.0
            else:
                ln_g = -math.log(price)  # ln(1/p)
                try:
                    daily_eff_if_win = math.expm1(ln_g / delta_days)
                    apr_eff_if_win   = math.expm1(ln_g * (365.0 / delta_days))
                except OverflowError:
                    daily_eff_if_win = float('inf')
                    apr_eff_if_win   = float('inf')

        # 调试打印
        debug_lines.append(
            f"[liq] tid={tid[:12]}… bid={best_bid} ask={best_ask} "
            f"L1spread_c={l1_spread_c_val} "
            f"depth1c_bid=${depth_bid_1c:.2f} depth1c_ask=${depth_ask_1c:.2f} "
            f"orders1c_bid={n_bid_1c} orders1c_ask={n_ask_1c} "
            f"topc_bid={topc_bid_1c:.2f} topc_ask={topc_ask_1c:.2f}"
        )
        debug_lines.append(
            f"[band] tid={tid[:12]}… band_c={band_c_used}¢ "
            f"ask_qty={depth_ask_1c_qty:.4f} vwap_ask={vwap_ask_1c:.6f} "
            f"bid_qty={depth_bid_1c_qty:.4f} vwap_bid={vwap_bid_1c:.6f}"
        )

        # 阈值过滤
        if l1_spread_c_thr is not None and l1_spread_c_val is not None and l1_spread_c_val > float(l1_spread_c_thr):
            n_spread_filtered += 1
            continue
        if min_depth_1c is not None and float(min_depth_1c) > 0 and depth_1c_min < float(min_depth_1c):
            n_depth_filtered += 1
            continue
        # —— 新增结束 —— #

        if mid not in market_records:
            mm = market_map.get(mid, {})
            market_records[mid] = {
                "condition_id": mm.get("condition_id"),
                "question": mm.get("question"),
                "endDate": mm.get("endDate"),
                "days_to_end": round((_parse_end_ts_safe(mm.get("endDate")) - time.time())/86400.0, 4) if mm.get("endDate") else None,
                # 新增：把规则、来源、URL 一起写入
                "rules": mm.get("rules") or "",
                "resolutionSource": mm.get("resolutionSource") or "",
                "url": ("https://polymarket.com/event/" + mm.get("slug")) if mm.get("slug") else "",
                # 小类列表：每个 outcome 一条
                "options": []
            }
        market_records[mid]["options"].append({
            "name": opt_name,
            "token": tid,
            "ask": price,
            "bid": round(best_bid, 6) if best_bid is not None else None,
            "l1_spread_c": l1_spread_c_val,
            "depth_ask_1c_usd": round(depth_ask_1c, 2),
            "depth_bid_1c_usd": round(depth_bid_1c, 2),
            "depth_1c_usd": round(min(depth_bid_1c, depth_ask_1c), 2),
            "n_orders_ask_1c": int(n_ask_1c),
            "n_orders_bid_1c": int(n_bid_1c),
            "top_concentration_ask_1c": round(topc_ask_1c, 4),
            "top_concentration_bid_1c": round(topc_bid_1c, 4),
            "band_c_used": round(band_c_used, 2),
            "depth_ask_1c_qty": round(depth_ask_1c_qty, 4),
            "vwap_ask_1c": round(vwap_ask_1c, 6),
            "depth_bid_1c_qty": round(depth_bid_1c_qty, 4),
            "vwap_bid_1c": round(vwap_bid_1c, 6),

            # —— 新增：期限 & 日化/年化（复利口径） —— #
            "days_to_end": _round_if_finite(delta_days, 4),
            "roi_if_win": _round_if_finite(roi_if_win, 6),
            "daily_eff_if_win": _round_if_finite(daily_eff_if_win, 6),
            "apr_eff_if_win": _round_if_finite(apr_eff_if_win, 6),
        })
        n_kept += 1

    # 只输出有至少一个小类入选的市场
    records = [obj for obj in market_records.values() if obj["options"]]
    debug_lines.append(f"records_filtered={len(records)}")
    debug_lines.append(f"filter_counts: total_yes={n_total_yes}, price_filtered={n_price_filtered}, spread_filtered={n_spread_filtered}, depth_filtered={n_depth_filtered}, kept={n_kept}")
    if records:
        try:
            debug_lines.append("records_sample=" + json.dumps(records[:1], ensure_ascii=False))
        except Exception:
            pass

    # —— 为输出记录加入『查询时间（北京时间）』及『offset』 ——
    try:
        _bj_time_str = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        _bj_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _rec in records:
        _rec["query_time_beijing"] = _bj_time_str
        _rec["offset"] = off
    debug_lines.append(f"query_time_beijing={_bj_time_str}")
    debug_lines.append(f"offset={off}")

    # 5) 落盘（每页一个文件）
    fname = autogen_filename()
    full_path = os.path.join(save_path, fname)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    try:
        fsize = os.path.getsize(full_path)
        debug_lines.append(f"target_file={full_path}")
        debug_lines.append(f"file_size={fsize} bytes")
    except Exception:
        debug_lines.append(f"target_file={full_path}")

    # 6) 组装该页的两路输出并 push 到 Array（仅本页）
    Outputs[0]['Num'] = None
    Outputs[0]['Context'] = full_path
    Outputs[0]['Description'] = f"Saved {len(records)} rows"

    Outputs[1]['Num'] = None
    Outputs[1]['Context'] = "\n".join(debug_lines)
    Outputs[1]['Description'] = 'Debug info'

    Array.append(copy.deepcopy(Outputs))

    # 7) 下一轮 offset
    if bounded_mode:
        # 边界模式：从 offset_start 起每次 +limit，最多到 offset_end；达到后不回绕
        if off >= offset_end:
            next_off = offset_end + 1
            debug_lines.append("bounded_progress=reached_end")
            try:
                node['_state']['finished'] = True
            except Exception:
                pass
        else:
            step = max(1, limit)
            cand = off + step
            next_off = cand if cand <= offset_end else offset_end
            if next_off >= offset_end:
                debug_lines.append("bounded_progress=next_hits_end")
                try:
                    node['_state']['finished'] = True
                except Exception:
                    pass
    else:
        # 非边界模式：保留原逻辑，遇到列表尾部（抓取数 < limit）回绕到 offset_start
        next_off = off + max(1, limit)
        if markets_fetched < limit:
            # 尾页：暂停不再前进（不回绕）
            next_off = off
            debug_lines.append("unbounded_progress=tail_reached_pause")
            try:
                node['_state']['finished'] = True
            except Exception:
                pass
    node['_state']['next_offset'] = next_off

    # —— 每次只返回一页 —— 
    return Array
# **Function definition**
