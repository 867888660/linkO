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
# 价格最小精度（Polymarket 常见为 0.001）
Inputs[3]['Num'] = 0.001

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

def try_get_clob_end_date_iso(condition_id: str, retry: int = 1) -> (str, str):
    """
    返回 (end_date_iso, err)
    - 成功：("2026-03-31T00:00:00Z", "")
    - 失败：("", "原因")
    """
    cid = str(condition_id or "").strip()
    if not (cid.startswith("0x") and len(cid) == 66):
        return "", f"invalid_condition_id={cid}"

    try:
        data = robust_get(f"{CLOB}/markets/{cid}", params=None, retry=retry, timeout=10)
        m = data.get("market") if isinstance(data, dict) and isinstance(data.get("market"), dict) else data
        if isinstance(m, dict):
            end_iso = m.get("end_date_iso") or m.get("endDate") or ""
        else:
            end_iso = ""
        if not end_iso:
            return "", "clob_end_date_iso_missing"
        return str(end_iso), ""
    except Exception as e:
        return "", f"clob_end_date_iso_fetch_fail:{type(e).__name__}"

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

def fetch_clob_end_date_iso_map(condition_ids: List[str], retry: int) -> Dict[str, str]:
    """
    返回 {condition_id: end_date_iso}
    优先批量 GET /markets?condition_ids=...；失败/缺失再逐个 GET /markets/<condition_id> 兜底。
    """
    out: Dict[str, str] = {}
    cids = [c for c in condition_ids if c]
    if not cids:
        return out

    # ① 批量：/markets?condition_ids=...
    try:
        params = {
            "condition_ids": cids,      # requests 会编码成 condition_ids=a&condition_ids=b...
            "limit": len(cids),
            "offset": 0
        }
        data = robust_get(f"{CLOB}/markets", params=params, retry=retry)
        arr = []
        if isinstance(data, list):
            arr = data
        elif isinstance(data, dict):
            arr = data.get("markets") or data.get("data") or data.get("items") or data.get("results") or []
        for m in arr:
            if not isinstance(m, dict):
                continue
            cid = m.get("condition_id") or m.get("conditionId")
            end_iso = m.get("end_date_iso") or m.get("endDate")
            if cid and end_iso:
                out[str(cid)] = str(end_iso)
    except Exception:
        pass

    # ② 兜底：/markets/<condition_id>
    missing = [cid for cid in cids if str(cid) not in out]
    for cid in missing:
        try:
            data = robust_get(f"{CLOB}/markets/{cid}", params=None, retry=retry)
            m = None
            if isinstance(data, dict):
                m = data.get("market") if isinstance(data.get("market"), dict) else data
            if isinstance(m, dict):
                end_iso = m.get("end_date_iso") or m.get("endDate")
                if end_iso:
                    out[str(cid)] = str(end_iso)
        except Exception:
            continue

    return out

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

_GAMMA_MIDNIGHT_UTC_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})T00:00:00(?:Z|\+00:00)\s*$")

def _rules_hint_et_noon(rules: str) -> bool:
    """
    判断 rules 是否暗示“美东当天 12:00（noon）”这种结算时间。
    典型文本：
    - '... 12:00 in the ET timezone (noon) on the date specified in the title ...'
    """
    if not rules:
        return False
    txt = _normalize_rules(str(rules))
    t = txt.lower()
    # 同时满足：出现 12:00、出现 ET、并且出现 noon 或 'et timezone'
    has_1200 = "12:00" in t
    has_et = (" et " in f" {t} ") or ("et timezone" in t)
    has_noon = "noon" in t
    return bool(has_1200 and has_et and (has_noon or "et timezone" in t))

def _ny_is_dst_local(year: int, month: int, day: int, hour: int, minute: int, second: int) -> bool:
    """
    无 zoneinfo 时，按美国纽约 DST 规则判断（2007+ 规则）：
    - DST 开始：3 月第二个周日 02:00
    - DST 结束：11 月第一个周日 02:00
    """
    try:
        dt = datetime(year, month, day, hour, minute, second)
    except Exception:
        return False

    def _nth_sunday(y: int, m: int, n: int) -> int:
        first = datetime(y, m, 1)
        # Python weekday: Mon=0 ... Sun=6
        delta = (6 - first.weekday()) % 7
        return 1 + delta + 7 * (n - 1)

    # 边界日期
    dst_start_day = _nth_sunday(year, 3, 2)   # 3月第二个周日
    dst_end_day   = _nth_sunday(year, 11, 1)  # 11月第一个周日

    dst_start = datetime(year, 3, dst_start_day, 2, 0, 0)
    dst_end   = datetime(year, 11, dst_end_day, 2, 0, 0)
    return dst_start <= dt < dst_end

def _normalize_midnight_utc_to_et_time(end_date_str: str, rules: str = "") -> (str, str):
    """
    将 'YYYY-MM-DDT00:00:00Z'（看起来像“日期占位”）修正为更贴近真实结算的美东时间点：
    - 若 rules 暗示 noon：用 ET 12:00:00
    - 否则兜底：用 ET 23:59:59（EOD）
    返回 (utc_iso, label)：
    - utc_iso: 修正后的 UTC ISO（Z）；不满足条件返回 ""
    - label: "noon" 或 "eod"
    """
    if not end_date_str:
        return "", ""
    m = _GAMMA_MIDNIGHT_UTC_RE.match(str(end_date_str))
    if not m:
        return "", ""
    try:
        y = int(m.group(1)); mo = int(m.group(2)); d = int(m.group(3))
    except Exception:
        return "", ""

    # 选择 ET 时间点
    is_noon = _rules_hint_et_noon(rules)
    hh = 12 if is_noon else 23
    minute = 0 if is_noon else 59
    second = 0 if is_noon else 59
    label = "noon" if is_noon else "eod"

    # 优先用 zoneinfo 精确处理 DST（America/New_York）
    try:
        from zoneinfo import ZoneInfo
        dt_local = datetime(y, mo, d, hh, minute, second, tzinfo=ZoneInfo("America/New_York"))
        dt_utc = dt_local.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), label
    except Exception:
        # 兜底：按规则推断 DST
        is_dst = _ny_is_dst_local(y, mo, d, hh, minute, second)
        offset_hours = -4 if is_dst else -5
        dt_local = datetime(y, mo, d, hh, minute, second, tzinfo=timezone(timedelta(hours=offset_hours)))
        dt_utc = dt_local.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), label

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

def _cat_to_str(x) -> str:
    """将 category/group/topic/tags 等字段安全转成字符串（兼容 str/dict/list）。"""
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, dict):
        return str(x.get("name") or x.get("label") or x.get("title") or "").strip()
    if isinstance(x, list):
        parts = [_cat_to_str(it) for it in x]
        parts = [p for p in parts if p]
        return ",".join(parts)
    return str(x).strip()

def _round_if_finite(x, nd=6):
    if x is None:
        return None
    try:
        if isinstance(x, float) and not math.isfinite(x):
            return None
        return round(x, nd)
    except Exception:
        return None

_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_RULE_BY_DEADLINE_RE = re.compile(
    r"\bby\s+([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\s*,\s*(\d{1,2}):(\d{2})\s*(AM|PM)\s*(ET|EST|EDT)\b",
    re.IGNORECASE
)

# 常见规则文本："... at 12 PM ET on December 26, 2025"
_RULE_AT_ON_RE = re.compile(
    r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*(ET|EST|EDT)?\s+on\s+([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\b",
    re.IGNORECASE
)

# 另一种常见顺序："... on December 26, 2025 at 12 PM ET"
_RULE_ON_AT_RE = re.compile(
    r"\bon\s+([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*(ET|EST|EDT)?\b",
    re.IGNORECASE
)

def parse_rules_datetime_iso(rules: str) -> str:
    """
    从 rules 里解析“明确的美东时间点”，并转成 UTC ISO（Z）。
    支持两类常见写法：
    1) 'by December 31, 2025, 11:59 PM ET'
    2) 'at 12 PM ET on December 26, 2025' / 'on December 26, 2025 at 12 PM ET'
    解析失败返回 ""。
    """
    if not rules:
        return ""

    # 先做轻量规范化（rules 可能包含 HTML）
    txt = _normalize_rules(str(rules))

    # 1) by ... deadline
    m = _RULE_BY_DEADLINE_RE.search(txt)
    if m:
        mon_s, day_s, year_s, hh_s, mm_s, ap_s, tz_s = m.groups()
        mon = _MONTH_MAP.get(mon_s.lower().strip(), 0)
        if mon <= 0:
            return ""
        day = int(day_s); year = int(year_s)
        hh = int(hh_s); minute = int(mm_s)
        ap = ap_s.upper().strip()
        tz = (tz_s or "ET").upper().strip()

        # 12h -> 24h
        if ap == "PM" and hh != 12:
            hh += 12
        if ap == "AM" and hh == 12:
            hh = 0

        # 处理时区：EST=-5, EDT=-4, ET 尽量用 zoneinfo（失败就按月份粗略推断）
        offset_hours = -5
        if tz == "EDT":
            offset_hours = -4
        elif tz == "EST":
            offset_hours = -5
        else:  # ET
            try:
                from zoneinfo import ZoneInfo
                dt_local = datetime(year, mon, day, hh, minute, 0, tzinfo=ZoneInfo("America/New_York"))
                dt_utc = dt_local.astimezone(timezone.utc)
                return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                offset_hours = -4 if 4 <= mon <= 10 else -5

        dt_local = datetime(year, mon, day, hh, minute, 0, tzinfo=timezone(timedelta(hours=offset_hours)))
        dt_utc = dt_local.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2) at ... on ... / on ... at ...
    m2 = _RULE_AT_ON_RE.search(txt)
    if m2:
        hh_s, mm_s, ap_s, tz_s, mon_s, day_s, year_s = m2.groups()
    else:
        m3 = _RULE_ON_AT_RE.search(txt)
        if not m3:
            return ""
        mon_s, day_s, year_s, hh_s, mm_s, ap_s, tz_s = m3.groups()

    mon = _MONTH_MAP.get(mon_s.lower().strip(), 0)
    if mon <= 0:
        return ""
    day = int(day_s); year = int(year_s)
    hh = int(hh_s)
    minute = int(mm_s) if mm_s is not None and str(mm_s).strip() != "" else 0
    ap = ap_s.upper().strip()
    tz = (tz_s or "ET").upper().strip()  # 很多 rules 省略 ET，这里默认 ET

    # 12h -> 24h
    if ap == "PM" and hh != 12:
        hh += 12
    if ap == "AM" and hh == 12:
        hh = 0

    offset_hours = -5
    if tz == "EDT":
        offset_hours = -4
    elif tz == "EST":
        offset_hours = -5
    else:  # ET
        try:
            from zoneinfo import ZoneInfo
            dt_local = datetime(year, mon, day, hh, minute, 0, tzinfo=ZoneInfo("America/New_York"))
            dt_utc = dt_local.astimezone(timezone.utc)
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            offset_hours = -4 if 4 <= mon <= 10 else -5

    dt_local = datetime(year, mon, day, hh, minute, 0, tzinfo=timezone(timedelta(hours=offset_hours)))
    dt_utc = dt_local.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # unreachable

def resolve_end_date_and_debug(mid: str, mm: Dict[str, Any], retry: int) -> (str, str):
    """
    优先级（按你要求）：
    1) CLOB end_date_iso（若非空）
    2) rules 文本 'by ... ET'
    3) Gamma endDate（mm 里已有）
    4) 仍不行：9999 拉很大

    Debug：正常 ""；只要出现“没拿到 end_date_iso / 用了兜底”就写原因。
    """
    dbg = []

    # --- 1) CLOB end_date_iso 优先 ---
    cid = str(mm.get("condition_id") or "").strip()
    clob_end = ""
    if cid.startswith("0x") and len(cid) == 66:
        try:
            d = robust_get(f"{CLOB}/markets/{cid}", params=None, retry=max(1, retry), timeout=10)
            m = d.get("market") if isinstance(d, dict) and isinstance(d.get("market"), dict) else d
            raw = m.get("end_date_iso", None) if isinstance(m, dict) else None
            clob_end = (raw or "").strip() if raw is not None else ""
            if clob_end:
                # CLOB 也可能给出 midnight UTC（看起来像“日期占位”），按美东当日 23:59:59 修正
                fixed, label = _normalize_midnight_utc_to_et_time(clob_end, mm.get("rules") or "")
                if fixed and fixed != clob_end:
                    mm["endDate"] = fixed
                    # 这属于“修正”，给出 Debug 方便你确认来源
                    return mm["endDate"], f"normalized_clob_midnight_to_et_{label}: {clob_end} -> {fixed}"
                mm["endDate"] = clob_end
                return mm["endDate"], ""  # 成功就不打 Debug（你要“正常为空”）
            else:
                dbg.append("clob_end_date_iso_missing")
                try:
                    if isinstance(m, dict):
                        dbg.append("clob_end_date_iso_raw=" + repr(raw))
                except Exception:
                    pass
        except Exception as e:
            dbg.append(f"clob_fetch_fail:{type(e).__name__}")
    else:
        dbg.append(f"invalid_condition_id={cid}")

    # --- 2) rules 文本兜底（优先于 Gamma endDate） ---
    rules = mm.get("rules") or ""
    rules_iso = parse_rules_datetime_iso(rules)
    if rules_iso:
        mm["endDate"] = rules_iso
        dbg.append("used_rules_datetime")
        return mm["endDate"], "; ".join(dbg)

    dbg.append("rules_deadline_parse_fail")

    # --- 3) Gamma endDate（已有） ---
    gamma_end = (mm.get("endDate") or "").strip()
    if gamma_end:
        # Gamma 偶发 'YYYY-MM-DDT00:00:00Z'：按 rules 选择 noon 或 eod 修正（只在此分支使用）
        fixed, label = _normalize_midnight_utc_to_et_time(gamma_end, mm.get("rules") or "")
        if fixed and fixed != gamma_end:
            mm["endDate"] = fixed
            dbg.append(f"normalized_gamma_midnight_to_et_{label}: {gamma_end} -> {fixed}")
            return mm["endDate"], "; ".join(dbg)
        # 即使 Gamma 有 endDate，也保留 Debug（因为你要求“包括没拿到 end_date_iso”也提示）
        return gamma_end, "; ".join(dbg)

    dbg.append("gamma_endDate_empty")

    # --- 4) 仍不行：9999 拉很大 ---
    mm["endDate"] = "9999-12-31T23:59:59Z"
    dbg.append("fallback_endDate_9999")
    return mm["endDate"], "; ".join(dbg)

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
            "category": stub.get("category") or "",
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

    # —— 新增：category 为空的 market 也需要 detail（最小改动，只补缺）——
    for mid, mm in market_map.items():
        if not (mm.get("category") or "").strip():
            need_detail_mids.add(mid)

    debug_lines.append(f"need_detail_mids={len(need_detail_mids)} sample={list(need_detail_mids)[:5]}")

    for mid in need_detail_mids:
        try:
            detail = robust_get(
                f"{GAMMA}/markets/{mid}",
                params={"withOutcomes": "true", "withTokens": "true", "withClobTokenIds": "true"},
                retry=1
            )
            if not isinstance(detail, dict):
                try:
                    market_map[mid]["_cat_debug"] = "cat_detail_not_dict"
                except Exception:
                    pass
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
            # category 字段兼容：category / group / topic / tags（最稳的字段兜底）
            if not (market_map.get(mid, {}).get("category") or "").strip():
                _cat1 = _cat_to_str(detail.get("category"))
                _cat2 = _cat_to_str(detail.get("group"))
                _cat3 = _cat_to_str(detail.get("topic"))
                _cat4 = _cat_to_str(detail.get("tags"))
                cat = (_cat1 or _cat2 or _cat3 or _cat4)
                market_map[mid]["category"] = cat
                # Debug：说明 category 补齐来源；若仍为空给出原因
                if cat:
                    if _cat1:
                        debug_lines.append(f"[cat-source] mid={mid} <- detail.category")
                        try:
                            market_map[mid]["_cat_debug"] = "cat_source=detail.category"
                        except Exception:
                            pass
                    elif _cat2:
                        debug_lines.append(f"[cat-source] mid={mid} <- detail.group")
                        try:
                            market_map[mid]["_cat_debug"] = "cat_source=detail.group"
                        except Exception:
                            pass
                    elif _cat3:
                        debug_lines.append(f"[cat-source] mid={mid} <- detail.topic")
                        try:
                            market_map[mid]["_cat_debug"] = "cat_source=detail.topic"
                        except Exception:
                            pass
                    else:
                        debug_lines.append(f"[cat-source] mid={mid} <- detail.tags")
                        try:
                            market_map[mid]["_cat_debug"] = "cat_source=detail.tags"
                        except Exception:
                            pass
                else:
                    present = []
                    for k in ("category", "group", "topic", "tags"):
                        try:
                            v = detail.get(k, None)
                            if v is None:
                                continue
                            # 只标记“字段存在且非空/非空容器”
                            if isinstance(v, str) and v.strip():
                                present.append(f"{k}:str")
                            elif isinstance(v, dict) and len(v) > 0:
                                present.append(f"{k}:dict")
                            elif isinstance(v, list) and len(v) > 0:
                                present.append(f"{k}:list")
                            else:
                                present.append(f"{k}:empty")
                        except Exception:
                            pass
                    msg = f"cat_missing=no_usable_category_fields present={present}"
                    debug_lines.append(f"[cat-missing] mid={mid} reason=no_usable_category_fields present={present}")
                    try:
                        market_map[mid]["_cat_debug"] = msg
                    except Exception:
                        pass
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
            try:
                market_map[mid]["_cat_debug"] = "cat_detail_fetch_fail"
            except Exception:
                pass
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

    def _norm_yn(s: str) -> str:
        s = (s or "").strip().lower()
        if s in ("yes", "y", "true", "1"):
            return "yes"
        if s in ("no", "n", "false", "0"):
            return "no"
        return ""

    mid_to_yes_tid = {}
    mid_to_no_tid = {}

    for tid, meta in token_meta.items():
        mid = meta.get("mid")
        yn = _norm_yn(meta.get("option_name"))
        if not mid or not yn:
            continue
        if yn == "yes":
            mid_to_yes_tid[mid] = tid
        else:
            mid_to_no_tid[mid] = tid

    mid_to_pair = {}
    for _mid, tid_list in mid_to_tids.items():
        if len(tid_list) == 2:
            mid_to_pair[_mid] = (tid_list[0], tid_list[1])

    debug_lines.append(f"binary_pairs: yes={len(mid_to_yes_tid)} no={len(mid_to_no_tid)}")

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

        # —— 每个 market 只解析一次 endDate + Debug（最小改动）——
        mm = market_map.get(mid, {})
        if mm and not mm.get("_end_resolved"):
            endv, dbg = resolve_end_date_and_debug(mid, mm, retry=retry)
            mm["endDate"] = endv
            mm["_end_debug"] = dbg or ""
            mm["_end_resolved"] = True

        # —— 计算期限与"如果赢"的复利年化/日化 —— #
        end_ts = _parse_end_ts_safe(mm.get("endDate"))
        delta_days = (end_ts - time.time()) / 86400.0

        roi_if_win = (1.0 - price) / price

        if (delta_days is None) or (delta_days <= 0):
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
            dbg_parts = []
            if (mm.get("_end_debug") or ""):
                dbg_parts.append(mm.get("_end_debug") or "")
            if (mm.get("_cat_debug") or ""):
                dbg_parts.append(mm.get("_cat_debug") or "")
            _dbg_joined = "; ".join([x for x in dbg_parts if x]) if dbg_parts else ""
            market_records[mid] = {
                "condition_id": mm.get("condition_id"),
                "question": mm.get("question"),
                "category": mm.get("category") or "",
                "endDate": mm.get("endDate"),
                "Debug": _dbg_joined,
                "days_to_end": round((_parse_end_ts_safe(mm.get("endDate")) - time.time())/86400.0, 4) if mm.get("endDate") else None,
                # 新增：把规则、来源、URL 一起写入
                "rules": mm.get("rules") or "",
                "resolutionSource": mm.get("resolutionSource") or "",
                "url": ("https://polymarket.com/event/" + mm.get("slug")) if mm.get("slug") else "",
                # 小类列表：每个 outcome 一条
                "options": []
            }
        # 计算二元对侧 token（用于反买）
        opp_token = None
        opp_name = None
        yn_opt = _norm_yn(opt_name)
        if yn_opt == "yes":
            opp_token = mid_to_no_tid.get(mid)
            opp_name = "No" if opp_token else None
        elif yn_opt == "no":
            opp_token = mid_to_yes_tid.get(mid)
            opp_name = "Yes" if opp_token else None
        if opp_token is None:
            pair = mid_to_pair.get(mid)
            if pair:
                t0, t1 = pair
                opp_token = t1 if tid == t0 else (t0 if tid == t1 else None)
                opp_name = opp_name  # 保持未知名称为空
        market_records[mid]["options"].append({
            "name": opt_name,
            "token": tid,
            "opp_token": opp_token,
            "opp_name": opp_name,
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
