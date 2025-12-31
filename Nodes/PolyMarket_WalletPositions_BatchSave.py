#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

# **节点输入输出定义**
OutPutNum = 3
InPutNum = 2
NodeKind = 'Normal'

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [{'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}', 'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''} for i in range(OutPutNum)]
Inputs = [{'Num': None, 'Kind': None, 'Id': f'Input{i + 1}', 'Context': None, 'Isnecessary': True, 'name': f'Input{i + 1}', 'Link': 0, 'IsLabel': True} for i in range(InPutNum)]

# Inputs 配置
Inputs[0]['name'] = 'Address'
Inputs[0]['Kind'] = 'String_Key'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = True
Inputs[0]['Context'] = ""

Inputs[1]['name'] = 'SavePath'
Inputs[1]['Kind'] = 'String_FilePath'
Inputs[1]['Isnecessary'] = True
Inputs[1]['IsLabel'] = True
Inputs[1]['Context'] = "./output"

# Outputs 配置
Outputs[0]['name'] = 'Result'
Outputs[0]['Kind'] = 'String'
Outputs[1]['name'] = 'SavePath'
Outputs[1]['Kind'] = 'String'
Outputs[2]['name'] = 'TOTAL CUR_VALUE'
Outputs[2]['Kind'] = 'String'

FunctionIntroduction = (
    '组件功能（简述代码整体功能）\n'
    '这是一个 Polymarket 钱包仓位查询与批量保存节点，用于查询指定钱包地址在 Polymarket 上的所有仓位信息，'
    '包括 positions、value、conditionId/indexSet 等，并将结果按批次保存为多个 JSON 文件。\n\n'
    '代码功能摘要（概括核心算法或主要处理步骤）\n'
    '节点通过 data-api 获取 positions 和 value，通过 gamma-api 查询 conditionId/indexSet 映射，'
    '支持自动扫描 proxyWallet 并二次查询，最终将数据按批次（每批默认 50 条）拆分成多个 JSON 文件保存。\n\n'
    '参数\n```yaml\n'
    'inputs:\n'
    '  - name: Address\n    type: string\n    required: true\n    description: 钱包地址（0x...）\n'
    '  - name: SavePath\n    type: string\n    required: true\n    description: JSON 文件保存目录路径\n'
    'outputs:\n'
    '  - name: Result\n    type: string\n    description: 返回结果 JSON 字符串（包含统计信息）\n'
    '  - name: SavePath\n    type: string\n    description: 实际保存的目录路径\n'
    '  - name: TOTAL CUR_VALUE\n    type: string\n    description: 总当前价值（浮点数字符串）\n```\n'
    '\n运行逻辑\n'
    '- 从输入节点获取钱包地址和保存路径\n'
    '- 调用 data-api /positions 获取仓位列表\n'
    '- 调用 data-api /value 获取总资产价值\n'
    '- 对每个 tokenId 调用 gamma-api 查询 conditionId/indexSet\n'
    '- 自动收集并查询 proxyWallet（如果存在）\n'
    '- 将数据按批次（每批 50 条）拆分成多个 JSON 文件保存\n'
    '- 返回统计信息和保存路径\n'
)

# API 端点
DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

# 批次大小（每批保存多少条 positions）
BATCH_SIZE = 50


def _bj_time_str() -> str:
    try:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _autogen_wallet_filename(ts: int, batch_index: int, total_batches: int) -> str:
    # 对齐 passivityTrigger_PolyMarket.py 的命名风格：polymarket_json_YYYYMMDD_HHMMSS_*.json
    # 但钱包这里会有多批，所以追加 wallet_batchXXX_of_YYY
    dt = datetime.fromtimestamp(ts)
    base = dt.strftime("%Y%m%d_%H%M%S")
    return f"polymarket_json_{base}_wallet_batch{batch_index:03d}_of_{total_batches:03d}.json"


def _autogen_wallet_summary_filename(ts: int) -> str:
    dt = datetime.fromtimestamp(ts)
    base = dt.strftime("%Y%m%d_%H%M%S")
    return f"polymarket_json_{base}_wallet_summary.json"


def token_id_to_hex32(token_id: Any) -> Optional[str]:
    """
    Polymarket 的 clob tokenId 本质上是 uint256（32 字节）。
    data-api 往往用十进制字符串返回，所以看起来会非常长。
    这里把它转成 0x + 64 hex（32 字节）更直观也更利于对齐显示。
    """
    if token_id is None:
        return None
    s = str(token_id).strip()
    if not s:
        return None
    try:
        if s.startswith(("0x", "0X")):
            n = int(s, 16)
        else:
            n = int(s, 10)
    except Exception:
        return None
    if n < 0:
        return None
    return "0x" + format(n, "064x")


def looks_like_evm_addr(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    t = s.strip()
    return t.startswith("0x") and len(t) == 42


def _sleep_backoff(attempt: int, base: float = 1.5, cap: float = 12.0) -> float:
    t = min(base ** (attempt - 1), cap)
    return max(0.5, t)


def http_get_json(url: str, timeout: float = 20.0, max_retries: int = 5) -> Any:
    last = None
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "pm-positions-scan/1.0"})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            if attempt >= max_retries:
                break
            time.sleep(_sleep_backoff(attempt))
    raise last  # type: ignore


def get_positions(user_addr: str, timeout: float = 20.0, size_threshold: float = 0.0) -> List[Dict[str, Any]]:
    # sizeThreshold=0 能把非常小的仓位也列出来
    url = f"{DATA_API}/positions?user={user_addr}&sizeThreshold={size_threshold}"
    data = http_get_json(url, timeout=timeout)
    if isinstance(data, list):
        return data
    # 有些实现会包一层 {"data":[...]}
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    return []


def get_value(user_addr: str, timeout: float = 20.0) -> Any:
    url = f"{DATA_API}/value?user={user_addr}"
    return http_get_json(url, timeout=timeout)


def pick_first(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] not in (None, "", "null"):
            return d[k]
    return None


def find_token_id(pos: Dict[str, Any]) -> Optional[str]:
    # data-api 里常见：asset / tokenId / token_id / id 等
    v = pick_first(pos, ["asset", "tokenId", "token_id", "clobTokenId", "clob_token_id", "id"])
    if v is None:
        return None
    return str(v).strip()


def find_condition_id_in_position(pos: Dict[str, Any]) -> Optional[str]:
    v = pick_first(pos, ["conditionId", "condition_id", "ctfConditionId", "ctf_condition_id"])
    if v is None:
        return None
    s = str(v).strip()
    # 统一成 0x 开头
    if s and not s.startswith("0x") and len(s) == 64:
        s = "0x" + s
    return s or None


def find_market_id_in_position(pos: Dict[str, Any]) -> Optional[str]:
    v = pick_first(pos, ["marketId", "market_id", "questionId", "question_id"])
    if v is None:
        return None
    return str(v).strip()


def gamma_market_by_token_id(token_id: str, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """
    关键：不扫全站，直接用 /markets 的过滤参数按 token_id 查
    兼容两种写法：clob_token_ids=xxx 或 clob_token_ids[]=xxx
    """
    tok = str(token_id).strip()

    # 1) clob_token_ids=tok
    url1 = f"{GAMMA_API}/markets?clob_token_ids={tok}&limit=1"
    try:
        data = http_get_json(url1, timeout=timeout)
        markets = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else None
        if markets:
            return markets[0]
    except Exception:
        pass

    # 2) clob_token_ids[]=tok
    url2 = f"{GAMMA_API}/markets?clob_token_ids[]={tok}&limit=1"
    try:
        data = http_get_json(url2, timeout=timeout)
        markets = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else None
        if markets:
            return markets[0]
    except Exception:
        pass

    return None


def gamma_extract_condition_and_indexset(mkt: Dict[str, Any], token_id: str) -> Tuple[Optional[str], Optional[int], Optional[List[str]]]:
    """
    从 Gamma market 里拿 conditionId + (YES/NO 对应 indexSet 1/2)
    """
    cond = pick_first(mkt, ["conditionId", "condition_id"])
    cond_s = None
    if cond is not None:
        cond_s = str(cond).strip()
        if cond_s and not cond_s.startswith("0x") and len(cond_s) == 64:
            cond_s = "0x" + cond_s

    token_ids = pick_first(mkt, ["clobTokenIds", "clobTokenIDs", "clob_token_ids"])
    token_list: Optional[List[str]] = None
    if isinstance(token_ids, list):
        token_list = [str(x).strip() for x in token_ids]
    elif isinstance(token_ids, str) and token_ids.strip():
        # 兼容字符串 JSON
        try:
            arr = json.loads(token_ids)
            if isinstance(arr, list):
                token_list = [str(x).strip() for x in arr]
        except Exception:
            pass

    idxset = None
    if token_list and len(token_list) >= 2:
        # 二元市场：第0个通常 YES、第1个 NO（Gamma 的顺序一般如此）
        tok = str(token_id).strip()
        if token_list[0] == tok:
            idxset = 1
        elif token_list[1] == tok:
            idxset = 2

    return cond_s, idxset, token_list


def collect_proxy_wallets(positions: List[Dict[str, Any]]) -> List[str]:
    """
    如果仓位挂在 proxyWallet（合约钱包/代理钱包）上，自动再查一次 proxyWallet。
    data-api 字段名可能会变，所以这里做一个"保守"的收集：
    - 优先拿 proxyWallet / proxy_wallet
    - 其次扫所有 key 里包含 'proxy' 的字段
    """
    found: List[str] = []
    seen = set()

    for p in positions:
        candidates: List[Any] = []
        candidates.append(p.get("proxyWallet"))
        candidates.append(p.get("proxy_wallet"))

        for k, v in p.items():
            if "proxy" in str(k).lower():
                candidates.append(v)

        for v in candidates:
            if looks_like_evm_addr(v):
                a = str(v).strip()
                if a.lower() not in seen:
                    seen.add(a.lower())
                    found.append(a)

    return found


def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def process_positions_with_condition(
    positions: List[Dict[str, Any]],
    timeout: float = 20.0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    处理 positions，为每个 position 补充 conditionId/indexSet 信息。
    返回：(增强后的 positions 列表, token_info_by_token_id 映射)
    """
    token_info_by_token_id: Dict[str, Dict[str, Any]] = {}
    enhanced_positions: List[Dict[str, Any]] = []

    for p in positions:
        token_id = find_token_id(p)
        if not token_id:
            enhanced_positions.append(p)
            continue

        if token_id not in token_info_by_token_id:
            info: Dict[str, Any] = {
                "token_id": token_id,
                "conditionId": None,
                "indexSet": None,
                "clobTokenIds": None,
                "gamma_market_id": None,
                "gamma_question": None,
                "source": None,
            }

            cond0 = find_condition_id_in_position(p)
            if cond0:
                info["conditionId"] = cond0
                info["source"] = "positions"

            if not info["conditionId"]:
                mkt = gamma_market_by_token_id(token_id, timeout=timeout)
                if mkt:
                    cond1, idxset, tlist = gamma_extract_condition_and_indexset(mkt, token_id)
                    info["conditionId"] = cond1
                    info["indexSet"] = idxset
                    info["clobTokenIds"] = tlist
                    info["gamma_market_id"] = mkt.get("id")
                    info["gamma_question"] = mkt.get("question")
                    info["source"] = "gamma_by_token"
                else:
                    info["source"] = "not_found"

            token_info_by_token_id[token_id] = info

        info = token_info_by_token_id[token_id]
        # 将 conditionId/indexSet 信息附加到 position
        enhanced_p = p.copy()
        enhanced_p["_conditionId"] = info.get("conditionId")
        enhanced_p["_indexSet"] = info.get("indexSet")
        enhanced_p["_token_info_source"] = info.get("source")
        enhanced_positions.append(enhanced_p)

    return enhanced_positions, token_info_by_token_id


def positions_to_market_records(
    positions: List[Dict[str, Any]],
    token_info_by_token_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    把 data-api 的 positions 转成与 passivityTrigger_PolyMarket.py 兼容的 JSON 结构：

    顶层：list[market]
    market: {
      condition_id, question, endDate, days_to_end, rules, resolutionSource, url, query_time_beijing,
      options: [ {name, token, opp_token, ask, bid, ...} ]
    }

    这样 Array_PolyMarket.py 可以同时解析：
    - passivityTrigger 输出的 JSON
    - 本 WalletPositions 节点输出的 JSON
    """
    qbj = _bj_time_str()

    # group key：尽量用 condition_id；否则回退 marketId/title（尽量别把所有仓位挤到一个 market）
    grouped: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for p in positions:
        token_id = find_token_id(p) or ""
        info = token_info_by_token_id.get(token_id, {}) if token_id else {}

        condition_id = (
            str(p.get("_conditionId") or "").strip()
            or str(find_condition_id_in_position(p) or "").strip()
            or str(info.get("conditionId") or "").strip()
        )
        market_id = str(find_market_id_in_position(p) or "").strip()
        question = str(p.get("title") or p.get("market") or p.get("question") or "").strip()

        key = condition_id or market_id or question or (token_id or "unknown")
        if key not in grouped:
            grouped[key] = {
                # Array_PolyMarket 期望字段名是 condition_id（不是 conditionId）
                "condition_id": condition_id or (market_id or key),
                "question": question,
                "endDate": str(p.get("endDate") or "").strip(),
                "days_to_end": str(p.get("days_to_end") or "").strip(),
                "rules": str(p.get("rules") or "").strip(),
                "resolutionSource": str(p.get("resolutionSource") or "").strip(),
                "url": str(p.get("url") or "").strip(),
                "query_time_beijing": qbj,
                "options": [],
            }
            order.append(key)

        # options 字段：尽量对齐 passivityTrigger 的命名（name/token/opp_token/ask/bid/...）
        outcome = str(p.get("outcome") or p.get("option_name") or "").strip()

        # ---- 钱包仓位里经常没有 currentPrice（但有 currentValue），这里做兜底推导 ----
        size_val = pick_first(p, ["size", "shares", "quantity", "amount", "balance"])
        avg_price_val = pick_first(p, ["avgPrice", "avg_price", "averagePrice"])
        cur_value_val = pick_first(p, ["currentValue", "current_value", "value", "current_value_usd", "currentValueUsd"])
        cur_price_val = pick_first(p, ["currentPrice", "current_price"])
        if cur_price_val is None:
            try:
                if cur_value_val is not None and size_val is not None:
                    s = float(size_val)
                    if s != 0:
                        cur_price_val = float(cur_value_val) / s
            except Exception:
                pass

        ask = p.get("ask")
        if ask in (None, "", "null"):
            ask = cur_price_val
        bid = p.get("bid")

        # 计算 opp_token（二元市场：用 gamma 的 clobTokenIds 顺序推断对侧）
        opp_token = ""
        try:
            tlist = info.get("clobTokenIds") or info.get("clobTokenIds".lower())  # 兼容性兜底
            if isinstance(tlist, list) and len(tlist) >= 2 and token_id:
                t0 = str(tlist[0]).strip()
                t1 = str(tlist[1]).strip()
                if token_id == t0:
                    opp_token = t1
                elif token_id == t1:
                    opp_token = t0
        except Exception:
            pass

        opt = {
            "name": outcome,
            "token": token_id,
            "opp_token": opp_token,
            "ask": ask if ask not in (None, "", "null") else None,
            "bid": bid if bid not in (None, "", "null") else None,
            # 下面这些字段钱包 positions 一般没有，给空即可；Array_PolyMarket 会安全兜底
            "l1_spread_c": p.get("l1_spread_c") or "",
            "band_c_used": p.get("band_c_used") or "",
            "depth_ask_1c_usd": p.get("depth_ask_1c_usd") or "",
            "depth_bid_1c_usd": p.get("depth_bid_1c_usd") or "",
            "depth_1c_usd": p.get("depth_1c_usd") or "",
            "depth_ask_1c_qty": p.get("depth_ask_1c_qty") or "",
            "depth_bid_1c_qty": p.get("depth_bid_1c_qty") or "",
            "vwap_ask_1c": p.get("vwap_ask_1c") or "",
            "vwap_bid_1c": p.get("vwap_bid_1c") or "",
            "n_orders_ask_1c": p.get("n_orders_ask_1c") or "",
            "n_orders_bid_1c": p.get("n_orders_bid_1c") or "",
            "top_concentration_ask_1c": p.get("top_concentration_ask_1c") or "",
            "top_concentration_bid_1c": p.get("top_concentration_bid_1c") or "",
            # 钱包特有信息：多给一些字段，读取方可选用（Array_PolyMarket 会忽略未定义字段）
            "size": size_val if size_val is not None else "",
            "avgPrice": avg_price_val if avg_price_val is not None else "",
            # currentPrice 在 data-api positions 里可能缺失：优先取原字段，否则用 currentValue/size 推导
            "currentPrice": cur_price_val if cur_price_val is not None else "",
            "currentValue": cur_value_val if cur_value_val is not None else "",
            # 兼容老字段名（你说的 CUR_VALUE）
            "CUR_VALUE": cur_value_val if cur_value_val is not None else "",
            "pnl": p.get("cashPnL") or p.get("pnl") or "",
            "indexSet": p.get("_indexSet") or info.get("indexSet") or "",
            "conditionId": condition_id,
        }

        grouped[key]["options"].append(opt)

    return [grouped[k] for k in order]


def save_market_records_in_batches(
    market_records: List[Dict[str, Any]],
    save_path: str,
    ts: int,
    batch_size: int = BATCH_SIZE,
) -> List[str]:
    """
    将 market_records（顶层 list）按批次保存为多个 JSON 文件（每个文件顶层仍是 list），
    以兼容 Array_PolyMarket.py 的读取逻辑。

    返回：保存的文件完整路径列表（不含 summary）
    """
    os.makedirs(save_path, exist_ok=True)

    saved_files: List[str] = []

    # 按批次拆分
    num_batches = (len(market_records) + batch_size - 1) // batch_size if market_records else 0
    # 兜底：即使没有任何 records，也要生成一个空的 batch 文件，方便下游节点统一“按文件读取”
    if num_batches <= 0:
        batch_filename = _autogen_wallet_filename(ts, 1, 1)
        batch_filepath = os.path.join(save_path, batch_filename)
        with open(batch_filepath, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return [batch_filepath]

    for batch_idx in range(num_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(market_records))
        batch_records = market_records[start_idx:end_idx]

        # 构建批次文件名
        batch_filename = _autogen_wallet_filename(ts, batch_idx + 1, num_batches)
        batch_filepath = os.path.join(save_path, batch_filename)

        # 保存批次文件
        with open(batch_filepath, "w", encoding="utf-8") as f:
            # 顶层必须是 list，保证 Array_PolyMarket.py 直接可读
            json.dump(batch_records, f, ensure_ascii=False, indent=2)

        saved_files.append(batch_filepath)
    return saved_files


def run_node(node):
    """
    主函数：查询钱包仓位并分批保存
    """
    # 读取输入
    def _get_input(idx: int):
        try:
            return node['Inputs'][idx]['Context']
        except Exception:
            return None

    addr_input = str(_get_input(0) or "").strip()
    # 地址提取逻辑：先尝试作为环境变量名，如果环境变量不存在则使用输入值本身
    if addr_input:
        env_value = os.getenv(addr_input)
        addr = env_value if env_value else addr_input
    else:
        addr = ""

    save_path = str(_get_input(1) or "./output").strip()

    # 验证地址
    if not addr or not addr.startswith("0x") or len(addr) < 10:
        result = {
            "success": False,
            "error": "地址格式无效，请提供有效的 0x 地址",
            "addr": addr,
        }
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        Outputs[1]['Context'] = save_path
        Outputs[2]['Context'] = "0.0"
        return Outputs

    timeout = 20.0
    size_threshold = 0.0

    try:
        # 查询总价值
        value = None
        try:
            value = get_value(addr, timeout=timeout)
        except Exception as e:
            pass  # value 查询失败不影响 positions

        # 查询仓位
        positions = get_positions(addr, timeout=timeout, size_threshold=size_threshold)

        # 收集 proxyWallet
        proxies = collect_proxy_wallets(positions)

        # 处理 positions（补充 conditionId/indexSet）
        enhanced_positions, token_info_by_token_id = process_positions_with_condition(
            positions,
            timeout=timeout,
        )

        # 查询 proxyWallet 的仓位（如果有）
        all_positions = enhanced_positions.copy()
        all_proxies = proxies.copy()
        all_token_info = dict(token_info_by_token_id)

        for proxy_addr in proxies:
            if proxy_addr.lower() != addr.lower():
                try:
                    proxy_positions = get_positions(proxy_addr, timeout=timeout, size_threshold=size_threshold)
                    if proxy_positions:
                        proxy_enhanced, proxy_token_info = process_positions_with_condition(proxy_positions, timeout=timeout)
                        # 合并 token_info
                        for k, v in (proxy_token_info or {}).items():
                            if k not in all_token_info:
                                all_token_info[k] = v
                        # 为 proxy 的 positions 添加标记
                        for p in proxy_enhanced:
                            p["_proxy_wallet"] = proxy_addr
                        all_positions.extend(proxy_enhanced)
                except Exception as e:
                    pass  # proxy 查询失败不影响主流程

        # 总当前价值（保持你原本输出的 TOTAL CUR_VALUE 语义）
        total_cur_value = 0.0
        for p in all_positions:
            cv = _to_float(p.get("currentValue")) or _to_float(p.get("value")) or 0.0
            total_cur_value += cv

        # 生成与 passivityTrigger 兼容的 market 结构，再分批保存（顶层为 list）
        market_records = positions_to_market_records(all_positions, all_token_info)
        ts = int(time.time())
        saved_batch_files = save_market_records_in_batches(
            market_records,
            save_path,
            ts=ts,
            batch_size=BATCH_SIZE,
        )

        # 额外生成 summary（可选；Array_PolyMarket 不读这个文件）
        summary_filename = _autogen_wallet_summary_filename(ts)
        summary_path = os.path.join(save_path, summary_filename)
        summary_data = {
            "type": "wallet_positions_summary",
            "root_addr": addr,
            "generated_at": ts,
            "total_positions": len(all_positions),
            "total_markets": len(market_records),
            "total_cur_value": total_cur_value,
            "value": value,
            "proxies": all_proxies,
            "batch_files": [os.path.basename(p) for p in saved_batch_files],
        }
        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)
        except Exception:
            summary_path = ""

        # 构建返回结果
        result = {
            "success": True,
            "addr": addr,
            "value": value,
            "total_positions": len(all_positions),
            "total_cur_value": total_cur_value,
            "proxies": all_proxies,
            "total_markets": len(market_records),
            "num_batches": len(saved_batch_files),
            "saved_files": [os.path.basename(f) for f in saved_batch_files] + ([os.path.basename(summary_path)] if summary_path else []),
            "save_path": save_path,
            "token_info_count": len(all_token_info),
        }

        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        # 关键：SavePath 输出改为“可直接读取的 JSON 文件完整路径”（默认第一个 batch）
        primary_json_path = saved_batch_files[0] if saved_batch_files else (summary_path or "")
        Outputs[1]['Context'] = primary_json_path
        Outputs[2]['Context'] = str(total_cur_value)

    except Exception as e:
        result = {
            "success": False,
            "error": str(e),
            "addr": addr,
            "save_path": save_path,
        }
        Outputs[0]['Context'] = json.dumps(result, ensure_ascii=False)
        Outputs[1]['Context'] = ""
        Outputs[2]['Context'] = "0.0"

    return Outputs

