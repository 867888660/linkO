import copy
import importlib.util
import json
import math
import os
import re
import time
from datetime import datetime, timezone, timedelta

# -------------------------
# 配置：输入 1 个（Token）
# - Token：clob tokenId（例如 0x...）
# 输出槽：保持与 Array_PolyMarket 一致：1(Json_Save) + FIELD_NAMES（46-98）
# 说明：内部直接复用 passivityTrigger_PolyMarket.py 的抓取/计算逻辑，
#       自动从 /markets 扫描找到该 token 所属市场并计算盘口/深度等字段。
# -------------------------

InPutNum = 1

# 与 Nodes/Array_PolyMarket.py (46-98) 保持一致：请勿随意改动顺序
FIELD_NAMES = [
    # 顶层字段
    'condition_id',
    'question',
    'endDate',
    'days_to_end',
    'rules',
    'resolutionSource',
    'url',

    # 规范化/辅助
    'option_name',
    'condition_id_ext',   # condition_id + '_' + slug(option_name)
    'ingested_at',        # UTC ISO 时间戳（生成时间）
    'source_file',        # 来源文件名（basename）

    # 盘口/价格
    'token',
    'ask',
    'bid',
    'l1_spread_c',
    'band_c_used',

    # 流动性/深度
    'depth_ask_1c_usd',
    'depth_bid_1c_usd',
    'depth_1c_usd',
    'depth_ask_1c_qty',
    'depth_bid_1c_qty',

    # 价带均价
    'vwap_ask_1c',
    'vwap_bid_1c',

    # 档位与集中度
    'n_orders_ask_1c',
    'n_orders_bid_1c',
    'top_concentration_ask_1c',
    'top_concentration_bid_1c',

    # 收益率
    'roi_if_win',
    'daily_eff_if_win',
    'apr_eff_if_win',
    'query_time_beijing',

    # 新增字段：务必追加在末尾，避免改变既有输出槽编号导致工作流"错位"
    'opp_token',
    # 钱包仓位兼容字段：务必追加在末尾
    'currentPrice',
    'currentValue',
    'size',  # 仓位大小/份额（兼容 size/shares/quantity/amount/balance）
    # ArrayTrigger 控制字段：是否为最后一条（布尔）
    'Islast',
]

# 额外 +1 个聚合输出槽：这里用于输出“命中记录的 JSON”
OutPutNum = len(FIELD_NAMES) + 1

# -------------------------
# 框架固定结构
# -------------------------
Outputs = [
    {'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}',
     'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''}
    for i in range(OutPutNum)
]

Inputs = [
    {'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None,
     'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': False}
    for i in range(InPutNum)
]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

FunctionIntroduction = (
    "组件功能：输入一个 Polymarket 的 clob tokenId，自动从 Polymarket API 查找该 token 所属市场，"
    "并计算/整理输出字段（与 Array_PolyMarket.py (46-98) 同序）。\n\n"
    "参数：\n"
    "```yaml\n"
    "inputs:\n"
    "  - name: Token\n"
    "    type: string\n"
    "    required: true\n"
    "    description: clob tokenId（0x...）\n"
    "outputs:\n"
    "  - name: Json_Save\n"
    "    type: string\n"
    "    description: 命中记录的 JSON（dict 字符串）；未命中输出空字符串\n"
    "  - name: (其余输出槽)\n"
    "    type: string/boolean\n"
    "    description: 与 Array_PolyMarket.py (46-98) 字段一致\n"
    "```\n\n"
    "运行逻辑：\n"
    "- 扫描 /markets 分页，直到找到包含该 token 的 market\n"
    "- 复用 passivityTrigger_PolyMarket.py 的盘口/深度计算函数 compute_depth_1c_usd\n"
    "- 复用 resolve_end_date_and_debug 解析 endDate，并计算 days_to_end / ROI / 日化 / 年化\n"
    "- 输出命中记录到各字段槽；Islast 作为 Boolean 输出，命中时为 True"
)

# Inputs / Outputs 类型与命名
Inputs[0]['Kind'] = 'String'
Inputs[0]['name'] = 'Token'

for i, out_def in enumerate(Outputs):
    if i == 0:
        out_def['name'] = 'Json_Save'
        out_def['Kind'] = 'String'
    else:
        out_def['name'] = FIELD_NAMES[i - 1]
        out_def['Kind'] = 'Boolean' if out_def['name'] == 'Islast' else 'String'


_PM_MOD = None


def _load_pm_module():
    """动态加载 Nodes/passivityTrigger_PolyMarket.py 以复用其现成逻辑（无需把 Nodes 变成包）。"""
    global _PM_MOD
    if _PM_MOD is not None:
        return _PM_MOD

    here = os.path.dirname(os.path.abspath(__file__))
    pm_path = os.path.join(here, "passivityTrigger_PolyMarket.py")
    spec = importlib.util.spec_from_file_location("pm_passivity_trigger", pm_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    _PM_MOD = mod
    return mod


def _strip_quotes(s: str) -> str:
    if s is None:
        return ''
    t = str(s).strip()
    if len(t) >= 2 and ((t[0] == t[-1] == '"') or (t[0] == t[-1] == "'")):
        t = t[1:-1].strip()
    return t


def _slugify(text: str) -> str:
    if text is None:
        return ''
    s = str(text).strip().lower()
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'[^a-z0-9_\-]', '', s)
    return s


def _bj_time_str() -> str:
    try:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_end_ts_flexible(end_date_str: str) -> float:
    """
    更强容错的 endDate 解析，避免 delta_days=0 导致年化为空。
    支持：
    - 2026-03-31T00:00:00Z / +00:00
    - 2026-03-31 12:00:00
    - 2026-03-31（仅日期）
    - 月/日不补0：2026-3-1T14:00:00Z
    规则：若缺省时区，则按 UTC 处理。
    """
    if not end_date_str:
        return 0.0
    s = str(end_date_str).strip().strip('"').strip("'").strip()
    if not s:
        return 0.0

    # 兼容：日期与时间用空格分隔
    if ' ' in s and 'T' not in s:
        parts = s.split()
        if len(parts) >= 2:
            s = parts[0] + 'T' + parts[1]

    # 补齐年月日（允许 1~2 位）
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})(.*)$', s)
    if m:
        y, mo, d, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        s = f'{y}-{int(mo):02d}-{int(d):02d}{rest}'

    # 仅日期：补齐到午夜 UTC
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        s = s + 'T00:00:00+00:00'

    # 末尾 Z -> +00:00
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'

    # 若包含时间但没有时区（不含 +HH:MM / -HH:MM），默认按 UTC
    has_time = 'T' in s
    has_tz = bool(re.search(r'([+-]\d{2}:\d{2})$', s))
    if has_time and (not has_tz):
        s = s + '+00:00'

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(dt.timestamp())
    except Exception:
        return 0.0


def _safe_num(x, nd=6):
    if x is None:
        return ''
    try:
        return str(round(float(x), nd))
    except Exception:
        return ''


def _find_market_by_token(pm, token_id: str):
    """
    扫描 /markets 分页找到包含 token_id 的 market stub。
    返回 (stub, option_name, token_ids_in_market)
    """
    limit = int(os.environ.get("PMQT_LIMIT", "200"))
    max_pages = int(os.environ.get("PMQT_MAX_PAGES", "20"))
    closed = os.environ.get("PMQT_CLOSED", "").strip().lower() in ("1", "true", "yes")
    retry = int(os.environ.get("PMQT_RETRY", "1"))

    # 0) 直查：用 clob_token_ids 直接反查 market（命中则无需翻页）
    try:
        direct = pm.robust_get(
            f"{pm.GAMMA}/markets",
            params={"clob_token_ids": token_id, "limit": 10, "offset": 0, "closed": str(closed).lower()},
            retry=retry
        )
    except Exception:
        direct = None
    if isinstance(direct, list) and direct:
        for stub in direct:
            if not isinstance(stub, dict):
                continue
            # 复用你原来的"快路径 + 慢路径"解析（不改结构）
            opt_name = ""
            token_ids = []
            outs = stub.get("outcomes") or []
            if isinstance(outs, list):
                for o in outs:
                    if not isinstance(o, dict):
                        continue
                    tid = o.get("clobTokenId") or o.get("tokenId") or o.get("token_id")
                    if tid:
                        tid = str(tid).strip()
                        token_ids.append(tid)
                        if tid == token_id:
                            name = (o.get("name") or o.get("outcome") or "").strip()
                            if name:
                                opt_name = name
                if not opt_name and outs:
                    clob_ids = stub.get("clobTokenIds") or []
                    if isinstance(clob_ids, str):
                        clob_ids = [clob_ids]
                    elif not isinstance(clob_ids, list):
                        clob_ids = []
                    if (len(outs) == len(clob_ids) and
                        all(isinstance(x, str) for x in outs) and
                        all(isinstance(x, str) for x in clob_ids)):
                        for name, tid in zip(outs, clob_ids):
                            tid_str = str(tid).strip()
                            if tid_str not in token_ids:
                                token_ids.append(tid_str)
                            if tid_str == token_id:
                                opt_name = name.strip()
            if token_id in token_ids:
                token_ids = [t for t in token_ids if t]
                return stub, opt_name, token_ids
            try:
                token_ids_fb = pm.extract_token_ids_from_market_stub(stub) or []
            except Exception:
                token_ids_fb = []
            if token_id in token_ids_fb:
                return stub, opt_name, token_ids_fb

    for p in range(max_pages):
        offset = p * max(1, limit)
        stubs = pm.fetch_markets(limit=limit, offset=offset, closed=closed, retry=retry) or []
        if not stubs:
            break

        for stub in stubs:
            if not isinstance(stub, dict):
                continue

            # 快路径：outcomes 直接带 clobTokenId
            opt_name = ""
            token_ids = []
            outs = stub.get("outcomes") or []
            if isinstance(outs, list):
                # ① 先尝试：outcomes 是 dict 列表
                for o in outs:
                    if not isinstance(o, dict):
                        continue
                    tid = o.get("clobTokenId") or o.get("tokenId") or o.get("token_id")
                    if tid:
                        tid = str(tid).strip()
                        token_ids.append(tid)
                        if tid == token_id:
                            name = (o.get("name") or o.get("outcome") or "").strip()
                            if name:
                                opt_name = name
                
                # ② 兜底：outcomes 可能是字符串列表（如 ["Yes","No"]），与 clobTokenIds 按顺序匹配
                if not opt_name and outs:
                    clob_ids = stub.get("clobTokenIds") or []
                    # 将 clobTokenIds 规范化为列表
                    if isinstance(clob_ids, str):
                        clob_ids = [clob_ids]
                    elif not isinstance(clob_ids, list):
                        clob_ids = []
                    
                    # 如果 outcomes 都是字符串，且长度匹配，按顺序 zip
                    if (len(outs) == len(clob_ids) and 
                        all(isinstance(x, str) for x in outs) and
                        all(isinstance(x, str) for x in clob_ids)):
                        for name, tid in zip(outs, clob_ids):
                            tid_str = str(tid).strip()
                            if tid_str not in token_ids:
                                token_ids.append(tid_str)
                            if tid_str == token_id:
                                opt_name = name.strip()

            if token_id in token_ids:
                # 二元市场 opp_token 兜底
                token_ids = [t for t in token_ids if t]
                return stub, opt_name, token_ids

            # 慢路径：复用现成提取（能兼容 tokens/outcomeTokens/yesToken/noToken 等）
            try:
                token_ids_fb = pm.extract_token_ids_from_market_stub(stub) or []
            except Exception:
                token_ids_fb = []
            if token_id in token_ids_fb:
                return stub, opt_name, token_ids_fb

    return None, "", []


def _get_option_name_via_detail(pm, mid: str, token_id: str) -> str:
    """若列表页拿不到 option_name，用详情页补一次。"""
    try:
        detail = pm.robust_get(
            f"{pm.GAMMA}/markets/{mid}",
            params={"withOutcomes": "true", "withTokens": "true", "withClobTokenIds": "true"},
            retry=1
        )
        if not isinstance(detail, dict):
            return ""
        
        # ① 先尝试：outcomes 是 dict 列表
        outs = detail.get("outcomes") or []
        if isinstance(outs, list):
            for o in outs:
                if isinstance(o, dict):
                    tid = o.get("clobTokenId") or o.get("tokenId") or o.get("token_id")
                    if tid and str(tid).strip() == token_id:
                        name = (o.get("name") or o.get("outcome") or "").strip()
                        if name:
                            return name
        
        # ② 兜底：outcomes 可能是字符串列表（如 ["Yes","No"]），与 clobTokenIds 按顺序匹配
        if isinstance(outs, list) and outs:
            clob_ids = detail.get("clobTokenIds") or []
            # 将 clobTokenIds 规范化为列表
            if isinstance(clob_ids, str):
                clob_ids = [clob_ids]
            elif not isinstance(clob_ids, list):
                clob_ids = []
            
            # 如果 outcomes 都是字符串，且长度匹配，按顺序 zip
            if (len(outs) == len(clob_ids) and 
                all(isinstance(x, str) for x in outs) and
                all(isinstance(x, str) for x in clob_ids)):
                for name, tid in zip(outs, clob_ids):
                    if str(tid).strip() == token_id:
                        return name.strip()
        
        # ③ tokens 兜底
        toks = detail.get("tokens") or detail.get("marketsTokens") or []
        if isinstance(toks, list):
            for t in toks:
                if isinstance(t, dict):
                    tid = t.get("token_id") or t.get("id") or t.get("tokenId")
                    if tid and str(tid).strip() == token_id:
                        name = (t.get("label") or t.get("outcome") or t.get("name") or "").strip()
                        if name:
                            return name
    except Exception:
        return ""
    return ""


def _get_yes_no_token_ids(pm, mid: str):
    """从详情页拿 yesToken/noToken 的 tokenId（拿不到就返回 ('','')）。"""
    try:
        detail = pm.robust_get(
            f"{pm.GAMMA}/markets/{mid}",
            params={"withOutcomes": "true", "withTokens": "true", "withClobTokenIds": "true"},
            retry=1
        )
        if not isinstance(detail, dict):
            return "", ""
        yt = detail.get("yesToken") or {}
        nt = detail.get("noToken") or {}
        yes_id = str((yt.get("tokenId") or yt.get("id") or yt.get("token_id") or "")).strip() if isinstance(yt, dict) else ""
        no_id = str((nt.get("tokenId") or nt.get("id") or nt.get("token_id") or "")).strip() if isinstance(nt, dict) else ""
        return yes_id, no_id
    except Exception:
        return "", ""


def _get_best_ask_fallback(pm, token_id: str):
    """当 /book 没 ask 时，用 /prices 或 /price 兜底拿 best ask。"""
    try:
        m = pm.fetch_yes_asks([token_id], retry=1) or {}
        if token_id in m:
            return float(m[token_id])
    except Exception:
        pass
    # 再兜底：直接 /price
    try:
        rr = pm.SESS.get(f"{pm.CLOB}/price", params={"token_id": token_id, "side": "BUY"}, timeout=6)
        if rr.status_code == 200:
            pj = rr.json() or {}
            if pj.get("price") is not None:
                return float(pj["price"])
    except Exception:
        pass
    return None


def _get_best_bid_fallback(pm, token_id: str):
    """当 /book 没 bid 时，用 /price 兜底拿 best bid。"""
    try:
        rr = pm.SESS.get(f"{pm.CLOB}/price", params={"token_id": token_id, "side": "SELL"}, timeout=6)
        if rr.status_code == 200:
            pj = rr.json() or {}
            if pj.get("price") is not None:
                return float(pj["price"])
    except Exception:
        pass
    return None

def run_node(node):
    token = (node.get('Inputs') or [{}])[0].get('Context')
    token_id = _strip_quotes(token).strip()

    # 输出：默认清空
    for out_def in Outputs:
        out_def['Context'] = ''
        out_def['Boolean'] = False

    if not token_id:
        return Outputs

    pm = _load_pm_module()
    stub, option_name, token_ids_in_market = _find_market_by_token(pm, token_id)
    
    # 即使找不到 market，也继续查询价格和深度信息（参考 PolyMarket_Research.py）
    # 初始化默认值
    mid = ""
    condition_id = ""
    question = ""
    slug = ""
    rules = ""
    resolution_source = ""
    opp_token = ""
    end_date = ""
    delta_days = 0.0
    
    if stub:
        # 找到了 market，提取信息
        mid = stub.get("id") or ""
        condition_id = stub.get("conditionId") or stub.get("condition_id") or mid or ""
        question = stub.get("question") or stub.get("title") or ""
        slug = stub.get("slug") or ""
        try:
            rules = pm._normalize_rules(stub.get("description") or "")
        except Exception:
            rules = str(stub.get("description") or "")
        resolution_source = stub.get("resolutionSource") or stub.get("resolution_source") or ""

        # option_name 若还没有，详情页补一次
        if not option_name and mid:
            option_name = _get_option_name_via_detail(pm, str(mid), token_id) or ""

        # opp_token：最朴素兜底（该 market 内刚好 2 个 token 就取另一个）
        if isinstance(token_ids_in_market, list):
            tids = [str(t).strip() for t in token_ids_in_market if str(t).strip()]
            if len(tids) == 2 and token_id in tids:
                opp_token = tids[0] if tids[1] == token_id else tids[1]

        # option_name 再兜底：若是二元市场，优先用 yesToken/noToken 映射
        if mid and (not option_name):
            yes_id, no_id = _get_yes_no_token_ids(pm, str(mid))
            if yes_id and token_id == yes_id:
                option_name = "Yes"
            elif no_id and token_id == no_id:
                option_name = "No"
            # 如果 yesToken/noToken 都获取不到或都不匹配，保持为空或设为 Unknown
            # 不再强制设为 "Yes"，避免误判
            if not option_name:
                option_name = "Unknown"

        # 解析 endDate（复用 passivityTrigger 逻辑）
        mm = {
            "condition_id": condition_id,
            "question": question,
            "endDate": stub.get("endDate") or stub.get("end_time") or stub.get("endTime") or "",
            "rules": rules,
            "resolutionSource": resolution_source,
            "slug": slug,
        }
        try:
            end_date, _dbg = pm.resolve_end_date_and_debug(str(mid), mm, retry=1)
        except Exception:
            end_date = mm.get("endDate") or ""
        mm["endDate"] = end_date or (mm.get("endDate") or "")

        # days_to_end 与收益率（口径对齐 passivityTrigger）
        end_ts = 0.0
        # 优先用 passivityTrigger 内置解析；若失败（=0）再用强容错解析兜底
        try:
            end_ts = float(pm._parse_end_ts_safe(mm.get("endDate") or ""))
        except Exception:
            end_ts = 0.0
        if not end_ts:
            end_ts = _parse_end_ts_flexible(mm.get("endDate") or "")
        delta_days = (end_ts - time.time()) / 86400.0 if end_ts else 0.0
    else:
        # 找不到 market，设置默认值
        option_name = "Unknown"

    # 盘口/深度（无论是否找到 market，都尝试查询）
    (best_bid, best_ask,
     depth_bid_1c_usd, depth_ask_1c_usd,
     n_bid_1c, n_ask_1c,
     topc_bid_1c, topc_ask_1c,
     band_c_used,
     depth_bid_1c_qty, depth_ask_1c_qty,
     vwap_bid_1c, vwap_ask_1c) = pm.compute_depth_1c_usd(token_id, retry=1)

    ask = best_ask
    bid = best_bid
    # 价格兜底：/book 没 ask 时用 /price(/prices)
    if ask is None:
        ask = _get_best_ask_fallback(pm, token_id)
    # 价格兜底：/book 没 bid 时用 /price
    if bid is None:
        bid = _get_best_bid_fallback(pm, token_id)
    
    # 重新计算 l1_spread_c（使用兜底后的 bid 和 ask）
    l1_spread_c_val = ''
    if bid is not None and ask is not None:
        try:
            l1_spread_c_val = str(int(math.ceil(max(0.0, (ask - bid) * 100.0) - 1e-9)))
        except Exception:
            l1_spread_c_val = ''
    
    price = float(ask) if ask is not None else None

    roi_if_win = ''
    daily_eff_if_win = ''
    apr_eff_if_win = ''
    # roi_if_win：只要有 price 就算（不依赖剩余天数）
    if price is not None and price > 0 and price < 1:
        try:
            roi_if_win = _safe_num((1.0 - price) / price, nd=6)
        except Exception:
            roi_if_win = ''
    # 日化/年化：需要 delta_days>0
    if price is not None and price > 0 and price < 1 and delta_days and delta_days > 0:
        try:
            ln_g = -math.log(price)
            daily_eff_if_win = _safe_num(math.expm1(ln_g / delta_days), nd=6)
            apr_eff_if_win = _safe_num(math.expm1(ln_g * (365.0 / delta_days)), nd=6)
        except Exception:
            daily_eff_if_win = ''
            apr_eff_if_win = ''

    # 组装输出 record（字段名与 Array_PolyMarket 对齐）
    ingested_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    url = ("https://polymarket.com/event/" + str(slug)) if slug else ""
    condition_id_ext = f"{condition_id}_{_slugify(option_name)}" if condition_id else _slugify(option_name)

    record = {k: '' for k in FIELD_NAMES}
    record.update({
        'condition_id': str(condition_id),
        'question': str(question),
        'endDate': str(end_date or ''),
        'days_to_end': _safe_num(delta_days, nd=4) if delta_days else '',
        'rules': str(rules or ''),
        'resolutionSource': str(resolution_source or ''),
        'url': str(url),

        'option_name': str(option_name or ''),
        'condition_id_ext': str(condition_id_ext or ''),
        'ingested_at': ingested_at,
        'source_file': 'Polymarket_API',

        'token': str(token_id),
        'ask': _safe_num(ask, nd=6),
        'bid': _safe_num(bid, nd=6),
        'l1_spread_c': l1_spread_c_val,
        'band_c_used': _safe_num(band_c_used, nd=2),

        'depth_ask_1c_usd': _safe_num(depth_ask_1c_usd, nd=2),
        'depth_bid_1c_usd': _safe_num(depth_bid_1c_usd, nd=2),
        'depth_1c_usd': _safe_num(min(depth_bid_1c_usd, depth_ask_1c_usd), nd=2) if depth_bid_1c_usd is not None and depth_ask_1c_usd is not None else '',
        'depth_ask_1c_qty': _safe_num(depth_ask_1c_qty, nd=4),
        'depth_bid_1c_qty': _safe_num(depth_bid_1c_qty, nd=4),

        'vwap_ask_1c': _safe_num(vwap_ask_1c, nd=6),
        'vwap_bid_1c': _safe_num(vwap_bid_1c, nd=6),

        'n_orders_ask_1c': str(int(n_ask_1c)) if n_ask_1c is not None else '',
        'n_orders_bid_1c': str(int(n_bid_1c)) if n_bid_1c is not None else '',
        'top_concentration_ask_1c': _safe_num(topc_ask_1c, nd=4),
        'top_concentration_bid_1c': _safe_num(topc_bid_1c, nd=4),

        'roi_if_win': roi_if_win,
        'daily_eff_if_win': daily_eff_if_win,
        'apr_eff_if_win': apr_eff_if_win,
        'query_time_beijing': _bj_time_str(),

        'opp_token': str(opp_token or ''),
        'currentPrice': '',
        'currentValue': '',
        'size': '',
        'Islast': True,
    })

    # 1) Json_Save：输出命中记录的 JSON（dict 字符串）
    try:
        Outputs[0]['Context'] = json.dumps(record, ensure_ascii=False)
    except Exception:
        Outputs[0]['Context'] = str(record)

    # 2) 各字段槽
    for i, field in enumerate(FIELD_NAMES, start=1):
        if field == 'Islast':
            Outputs[i]['Boolean'] = True
            Outputs[i]['Context'] = ''
        else:
            Outputs[i]['Context'] = '' if record.get(field) is None else str(record.get(field, ''))

    return Outputs


