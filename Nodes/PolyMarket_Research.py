import json
import logging
import os
import re
import requests
import time
from decimal import Decimal, InvalidOperation

# **Function definition**

# **Define the number of outputs and inputs**输入节点与输出节点的数量
OutPutNum = 3
InPutNum = 1

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [
    {'Num': None, 'Kind': None, 'Boolean': False, 'Id': f'Output{i + 1}',
     'Context': None, 'name': f'OutPut{i + 1}', 'Link': 0, 'Description': ''}
    for i in range(OutPutNum)
]
Inputs  = [
    {'Num': None, 'Kind': None, 'Id': f'Input{i + 1}',  'Context': None,
     'Isnecessary': True, 'name': f'Input{i + 1}',  'Link': 0, 'IsLabel': True}
    for i in range(InPutNum)
]

NodeKind = 'Normal'
Lable = [{'Id': 'Label1', 'Kind': 'None'}]
FunctionIntroduction='组件功能（简述代码整体功能）\\n这是一个基础的节点模板程序，用于创建具有单一输入和输出的处理节点，可以根据需求自定义输入输出属性和处理逻辑。\\n\\n代码功能摘要（概括核心算法或主要处理步骤）\\n程序定义了一个标准的节点结构模板，包含输入输出节点的初始化、属性配置和基础的运行框架。核心处理逻辑在run_node函数中实现，当前版本仅提供框架结构，具体业务逻辑需要根据实际需求进行填充。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Input1\\n    type: string\\n    required: true\\n    description: 输入数据内容\\noutputs:\\n  - name: OutPut1\\n    type: string\\n    description: 处理后的输出结果\\n```\\n\\n运行逻辑（用 - 列表描写详细流程）\\n- 程序启动时定义输入输出节点数量，当前设置为各1个\\n- 初始化输入输出数组，为每个节点分配基础属性包括ID、名称、类型等\\n- 配置节点类型为Normal，设置标签属性Label1\\n- 为所有输入输出节点指定数据类型为String\\n- 执行run_node函数时获取输入节点的Context内容作为file_path\\n- 初始化content变量用于存储处理结果，初始化Debugging列表用于调试信息收集\\n- 将处理后的content内容赋值给输出节点的Context属性\\n- 返回包含处理结果的Outputs数组'

# **Assign properties to Inputs/Outputs**
for o in Outputs:
    o['Kind'] = 'String'
for i in Inputs:
    i['Kind'] = 'String'

# 输入
Inputs[0]['Kind'] = 'String'
Inputs[0]['name'] = 'Token_Id'
Inputs[0]['Isnecessary'] = True
Inputs[0]['IsLabel'] = False

# 输出
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Ask_Price'
Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Bids_Price'
Outputs[2]['Kind'] = 'String'
Outputs[2]['name'] = 'Debug'

# ====== 取价最小依赖 ======
SESS = requests.Session()
SESS.headers.update({"User-Agent": "pm-screen/1.0"})
CLOB = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

def _norm_outcome_name(s: str) -> str:
    t = str(s or "").strip()
    # 常见：YES/NO / Yes/No / “No, the event will not occur”
    return re.sub(r"\s+", " ", t).strip().lower()

def _token_to_int(token: str):
    t = str(token or "").strip()
    if not t:
        return None
    try:
        if t.startswith(("0x", "0X")):
            return int(t, 16)
        return int(t, 10)
    except Exception:
        return None

def _token_match(a: str, b: str) -> bool:
    aa = str(a or "").strip()
    bb = str(b or "").strip()
    if not aa or not bb:
        return False
    ai = _token_to_int(aa)
    bi = _token_to_int(bb)
    if ai is not None and bi is not None:
        return ai == bi
    return aa.lower() == bb.lower()

def _as_list(x):
    """把 x 规范成 list。x 可能本来就是 list，也可能是 '[...]' 字符串。失败就返回 []。"""
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                v = json.loads(s)
                if isinstance(v, list):
                    return v
            except Exception:
                pass
    return []

def _unwrap_market(obj):
    """Gamma 有时会返回 {'market': {...}} 或 {'data': {...}}，这里统一解包。"""
    if isinstance(obj, dict):
        for k in ("market", "data", "result"):
            v = obj.get(k)
            if isinstance(v, dict):
                return v
    return obj

def _gamma_get(path: str, params: dict | None = None, timeout: int = 12, retry: int = 2, debug: list | None = None):
    base = GAMMA.rstrip("/")
    url = f"{base}{path}"
    last_err = None
    for k in range(1, retry + 2):
        try:
            r = SESS.get(url, params=params, timeout=timeout)
            if debug is not None:
                debug.append(f"[gamma] GET {path} attempt={k} status={r.status_code}")
            if r.status_code == 200:
                return r.json()
            last_err = RuntimeError(f"status={r.status_code}")
        except Exception as e:
            last_err = e
            if debug is not None:
                debug.append(f"[gamma] GET {path} attempt={k} exception {type(e).__name__}: {e}")
        time.sleep(0.35)
    raise last_err  # type: ignore

def _extract_token_option_name(detail: dict, token_id: str) -> str:
    """从 market detail 中，把 token_id 映射到该 option/outcome 名称。"""
    tid = str(token_id or "").strip()
    detail = _unwrap_market(detail)
    if not tid or not isinstance(detail, dict):
        return ""

    clob_ids = detail.get("clobTokenIds") or detail.get("clob_token_ids") or detail.get("clob_tokenIds")
    clob_ids = _as_list(clob_ids) if not isinstance(clob_ids, list) else clob_ids
    outcomes = detail.get("outcomes") or detail.get("outcomeNames") or detail.get("outcome_names") or []

    # ① outcomes 是 dict 列表，且带 clobTokenId
    if isinstance(outcomes, list):
        for o in outcomes:
            if isinstance(o, dict):
                otid = (o.get("clobTokenId") or o.get("clob_token_id") or o.get("tokenId") or o.get("token_id") or o.get("id") or "")
                if otid and _token_match(str(otid), tid):
                    return (o.get("name") or o.get("outcome") or o.get("label") or "").strip()

    # ② 如果 outcomes/token 列表里没 tokenId，按 clobTokenIds 顺序匹配 outcomes
    if isinstance(outcomes, list) and outcomes and isinstance(clob_ids, list) and clob_ids and len(clob_ids) == len(outcomes):
        for i, x in enumerate(clob_ids):
            if _token_match(str(x), tid):
                oi = outcomes[i]
                if isinstance(oi, dict):
                    return (oi.get("name") or oi.get("outcome") or oi.get("label") or "").strip()
                return str(oi).strip()

    # ③ 从 tokens/outcomeTokens 尝试提取（有些 market 只在 tokens[] 里带 label/name）
    for key in ("tokens", "outcomeTokens", "outcome_tokens"):
        tv = detail.get(key)
        if isinstance(tv, list):
            for t in tv:
                if isinstance(t, dict):
                    tt = (t.get("tokenId") or t.get("token_id") or t.get("id") or t.get("clobTokenId") or "")
                    if tt and _token_match(str(tt), tid):
                        return (t.get("label") or t.get("outcome") or t.get("name") or "").strip()

    # ④ 二元兜底：第一个=Yes，第二个=No
    if isinstance(clob_ids, list) and len(clob_ids) >= 2:
        if _token_match(str(clob_ids[0]), tid):
            return "Yes"
        if _token_match(str(clob_ids[1]), tid):
            return "No"

    return ""

def _extract_resolved_outcome_name(detail: dict) -> str:
    """
    从 market detail 中尽力抽取“最终 outcome 名称”。
    Gamma 字段在不同版本/市场类型会有所差异，因此这里做多路兜底。
    """
    detail = _unwrap_market(detail)
    if not isinstance(detail, dict):
        return ""

    # ① 直接字段（最理想）
    for k in (
        "resolvedOutcome", "resolved_outcome",
        "winningOutcome", "winning_outcome", "winningOutcomeName", "winning_outcome_name",
        "finalOutcome", "final_outcome",
        "outcome", "result", "answer", "resolution", "resolvedValue", "resolved_value"
    ):
        v = detail.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # ② outcomes 里直接带 winner/isWinner/winning/payout 等字段
    outcomes = detail.get("outcomes") or []
    if isinstance(outcomes, list) and outcomes:
        for o in outcomes:
            if not isinstance(o, dict):
                continue
            # winner flag
            for wk in ("winner", "isWinner", "is_winner", "winning", "isWinning", "is_winning"):
                vv = o.get(wk)
                if vv in (True, "true", "True", 1, "1"):
                    return (o.get("name") or o.get("outcome") or o.get("label") or "").strip()
            # payout inside outcome object
            pv = o.get("payout")
            if pv in (1, "1", 1.0, "1.0"):
                return (o.get("name") or o.get("outcome") or o.get("label") or "").strip()

    # ② payouts: 若存在，通常 winner payout=1
    payouts = detail.get("payouts")
    if isinstance(payouts, list) and payouts and isinstance(outcomes, list) and outcomes:
        try:
            # payouts 可能是 ["1","0"] / [1,0] / [{"payout":1},...]
            pvals = []
            for p in payouts:
                if isinstance(p, (int, float, str)):
                    pvals.append(float(p))
                elif isinstance(p, dict) and p.get("payout") is not None:
                    pvals.append(float(p.get("payout")))
                else:
                    pvals.append(float("nan"))
            if len(pvals) == len(outcomes):
                imax = max(range(len(pvals)), key=lambda i: (pvals[i] if pvals[i] == pvals[i] else -1e9))
                o = outcomes[imax]
                if isinstance(o, dict):
                    return (o.get("name") or o.get("outcome") or o.get("label") or "").strip()
                if isinstance(o, str):
                    return o.strip()
        except Exception:
            pass

    # ③ outcomePrices: resolved 后 winner 通常为 1
    prices = detail.get("outcomePrices") or detail.get("outcome_prices")
    if isinstance(prices, list) and prices and isinstance(outcomes, list) and outcomes and len(prices) == len(outcomes):
        try:
            pvals = [float(x) for x in prices]
            imax = max(range(len(pvals)), key=lambda i: pvals[i])
            o = outcomes[imax]
            if isinstance(o, dict):
                return (o.get("name") or o.get("outcome") or o.get("label") or "").strip()
            if isinstance(o, str):
                return o.strip()
        except Exception:
            pass

    return ""

def resolve_is_victory_by_token(token_id: str, debug: list | None = None, timeout: int = 12, retry: int = 2):
    """
    当盘口无法获取（通常意味着已结算/下架）时：
    - 反查该 token 所属 market
    - 读取 market 的 resolved outcome
    - 计算 token 对应 option 是否为赢家 -> IsVictory True/False
    返回 (is_victory: bool|None, option_name: str, resolved_outcome: str)
    """
    tid = str(token_id or "").strip()
    if not tid:
        return None, "", ""

    # 1) 先用 clob_token_ids 直查 market 列表（closed=true 更容易命中已结算市场）
    lst = None
    for closed in ("true", "false"):
        try:
            lst = _gamma_get(
                "/markets",
                params={"clob_token_ids": tid, "limit": 10, "offset": 0, "closed": closed},
                timeout=timeout,
                retry=retry,
                debug=debug,
            )
            if isinstance(lst, list) and lst:
                if debug is not None:
                    debug.append(f"[gamma] markets_by_token hit closed={closed} n={len(lst)}")
                break
        except Exception:
            lst = None

    if not (isinstance(lst, list) and lst):
        if debug is not None:
            debug.append("[gamma] markets_by_token miss")
        return None, "", ""

    stub = lst[0] if isinstance(lst[0], dict) else {}
    stub = _unwrap_market(stub)
    mid = str(stub.get("id") or "").strip()
    if debug is not None:
        debug.append(f"[gamma] market_id={mid or 'unknown'}")

    # 2) 详情补一把（更可能包含 resolved/outcome/payouts 等字段）
    detail = stub
    if mid:
        try:
            detail = _gamma_get(
                f"/markets/{mid}",
                params={"withOutcomes": "true", "withTokens": "true", "withClobTokenIds": "true"},
                timeout=timeout,
                retry=retry,
                debug=debug,
            )
        except Exception as e:
            if debug is not None:
                debug.append(f"[gamma] market_detail_fetch_fail {type(e).__name__}: {e}")
            detail = stub

    detail = _unwrap_market(detail)
    option_name = _extract_token_option_name(detail, tid) or ""
    resolved_outcome = _extract_resolved_outcome_name(detail) or ""
    if debug is not None:
        debug.append(f"[gamma] option_name={option_name or 'Unknown'}")
        debug.append(f"[gamma] resolved_outcome={resolved_outcome or 'Unknown'}")
        if (not option_name) or (not resolved_outcome):
            try:
                debug.append(f"[gamma] detail_keys_head={list(detail.keys())[:30]}")
            except Exception:
                pass
            try:
                clob_ids = detail.get("clobTokenIds") or detail.get("clob_token_ids") or detail.get("clob_tokenIds")
                clob_list = _as_list(clob_ids) if not isinstance(clob_ids, list) else clob_ids
                debug.append(f"[gamma] clobTokenIds_type={type(clob_ids).__name__} len={len(clob_list) if isinstance(clob_list, list) else 'NA'} head={repr(clob_list[:2]) if isinstance(clob_list, list) else str(clob_ids)[:120]}")
            except Exception:
                pass
            try:
                outs = detail.get("outcomes")
                if isinstance(outs, list):
                    preview = []
                    for o in outs[:2]:
                        if isinstance(o, dict):
                            preview.append({k: o.get(k) for k in ("name", "outcome", "label", "clobTokenId", "tokenId", "id", "winner", "isWinner", "payout") if k in o})
                        else:
                            preview.append(o)
                    debug.append(f"[gamma] outcomes_type=list len={len(outs)} head={json.dumps(preview, ensure_ascii=False)}")
                else:
                    debug.append(f"[gamma] outcomes_type={type(outs).__name__} head={str(outs)[:180]}")
            except Exception:
                pass

    # 3) 计算 IsVictory
    if option_name and resolved_outcome:
        is_victory = (_norm_outcome_name(option_name) == _norm_outcome_name(resolved_outcome))
        return is_victory, option_name, resolved_outcome

    # 若只知道 winner outcome，但不知道当前 token 对应 option，返回 None
    return None, option_name, resolved_outcome

def get_price(token_id: str, side: str = "BUY", retry: int = 3, timeout: int = 8, debug: list | None = None, pause: float = 0.5):
    """
    返回 str(原始价格) 或 None（不做四舍五入）
    side:
      - 'BUY'  -> bid（根据实际返回：BUY 侧价格通常更低）
      - 'SELL' -> ask（根据实际返回：SELL 侧价格通常更高）
    """
    token_id = (token_id or "").strip()
    if not token_id:
        if debug is not None:
            debug.append(f"[skip] token_id 为空，side={side}")
        return None

    side = side.upper()
    if side not in ("BUY", "SELL"):
        side = "BUY"

    def _to_price_str(v):
        """把接口返回的 price 规范成字符串，不做四舍五入。"""
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        try:
            # 用 Decimal 避免 float 的二进制表示问题，并避免科学计数法
            return format(Decimal(str(v)), "f")
        except (InvalidOperation, ValueError, TypeError):
            s = str(v).strip()
            return s if s else None

    def _json_decimal_response(rsp, default):
        """用 Decimal 解析 JSON，避免 float 误差；失败则回退到 rsp.json()。"""
        try:
            txt = rsp.text or ""
            if not txt.strip():
                return default
            return json.loads(txt, parse_float=Decimal)
        except Exception:
            try:
                return rsp.json()
            except Exception:
                return default

    # 首选：/price
    for attempt in range(1, retry + 1):
        try:
            r = SESS.get(f"{CLOB}/price", params={"token_id": token_id, "side": side}, timeout=timeout)
            if debug is not None:
                debug.append(f"[/price] attempt={attempt} side={side} status={r.status_code}")
            if r.status_code == 200:
                js = _json_decimal_response(r, {}) or {}
                pstr = _to_price_str(js.get("price"))
                if pstr is not None:
                    if debug is not None:
                        debug.append(f"[/price] success side={side} price={pstr}")
                    return pstr
                else:
                    if debug is not None:
                        debug.append(f"[/price] body_without_price side={side} body_type={type(js).__name__}")
            else:
                if debug is not None:
                    debug.append(f"[/price] non200 side={side} status={r.status_code}")
        except Exception as e:
            if debug is not None:
                debug.append(f"[/price] exception side={side} {type(e).__name__}: {e}")
        time.sleep(pause)

    # 兜底：/prices（批量）
    for attempt in range(1, retry + 1):
        try:
            payload = [{"token_id": token_id, "side": side}]
            r = SESS.post(f"{CLOB}/prices", json=payload, timeout=timeout)
            if debug is not None:
                debug.append(f"[/prices] attempt={attempt} side={side} status={r.status_code}")
            if r.status_code == 200:
                js = _json_decimal_response(r, []) or []
                if isinstance(js, list) and js:
                    pstr = _to_price_str(js[0].get("price"))
                    if pstr is not None:
                        if debug is not None:
                            debug.append(f"[/prices] success(list) side={side} price={pstr}")
                        return pstr
                    else:
                        if debug is not None:
                            debug.append(f"[/prices] list_without_price side={side}")
                elif isinstance(js, dict):
                    v = js.get(token_id) or {}
                    pstr = _to_price_str(v.get("price")) if isinstance(v, dict) else None
                    if pstr is not None:
                        if debug is not None:
                            debug.append(f"[/prices] success(dict) side={side} price={pstr}")
                        return pstr
                    else:
                        if debug is not None:
                            debug.append(f"[/prices] dict_without_price side={side}")
                else:
                    if debug is not None:
                        debug.append(f"[/prices] unexpected_body_type side={side} body_type={type(js).__name__}")
            else:
                if debug is not None:
                    debug.append(f"[/prices] non200 side={side} status={r.status_code}")
        except Exception as e:
            if debug is not None:
                debug.append(f"[/prices] exception side={side} {type(e).__name__}: {e}")
        time.sleep(pause)

    if debug is not None:
        debug.append(f"[result] 未获取到价格 side={side}")
    return None
# ========================

# **Function definition**
def run_node(node):
    token_id = node['Inputs'][0].get('Context') or ""

    # 可选：同时取最优卖价(ask)与最优买价(bid)
    debug_lines = []
    debug_lines.append(f"[start] token_id={token_id.strip()}")
    # 注意：Polymarket CLOB /price 的 side 语义与常规直觉相反（以实际返回为准）：
    # - side=SELL 更像 ask（更高）
    # - side=BUY  更像 bid（更低）
    ask_price = get_price(token_id, side="SELL", retry=3, timeout=8, debug=debug_lines)
    bid_price = get_price(token_id, side="BUY", retry=3, timeout=8, debug=debug_lines)

    # 若出现“未获取到价格”，通常意味着盘口已不存在（例如市场已结算/下架），此时输出 IsVictory
    if (ask_price is None and bid_price is None) or any(("未获取到价格" in str(x)) for x in debug_lines):
        try:
            is_victory, option_name, resolved_outcome = resolve_is_victory_by_token(token_id, debug=debug_lines, timeout=12, retry=2)
            if is_victory is None:
                debug_lines.append(f"[IsVictory] IsVictory==Unknown (option={option_name or 'Unknown'}, outcome={resolved_outcome or 'Unknown'})")
            else:
                debug_lines.append(f"[IsVictory] IsVictory=={bool(is_victory)} (option={option_name or 'Unknown'}, outcome={resolved_outcome or 'Unknown'})")
        except Exception as e:
            debug_lines.append(f"[IsVictory] exception {type(e).__name__}: {e}")
    debug_lines.append(f"[final] ask_price={('None' if ask_price is None else str(ask_price))}, bid_price={('None' if bid_price is None else str(bid_price))}")

    # 不做四舍五入，直接输出接口返回的原始价格；同时修正 ask/bid 写反的问题
    Outputs[0]['Context'] = "" if ask_price is None else str(ask_price)
    Outputs[1]['Context'] = "" if bid_price is None else str(bid_price)
    Outputs[2]['Context'] = "\n".join(debug_lines)

    return Outputs
# **Function definition**
