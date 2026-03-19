import json
import math
from decimal import Decimal, InvalidOperation, ROUND_DOWN, getcontext
from typing import Any, Dict, Optional, Tuple

# **Define the number of outputs and inputs**
OutPutNum = 5
InPutNum = 19

DEFAULT_REBALANCE_HI = Decimal("0.06")
DEFAULT_MIN_NOTIONAL = Decimal("10")
EPSILON = Decimal("1e-12")

# **Initialize Outputs and Inputs arrays and assign names directly**
Outputs = [
    {
        "Num": None,
        "Kind": None,
        "Boolean": False,
        "Id": f"Output{i + 1}",
        "Context": None,
        "name": f"OutPut{i + 1}",
        "Link": 0,
        "Description": "",
    }
    for i in range(OutPutNum)
]
Inputs = [
    {
        "Num": None,
        "Kind": None,
        "Id": f"Input{i + 1}",
        "Context": None,
        "Isnecessary": True,
        "name": f"Input{i + 1}",
        "Link": 0,
        "IsLabel": True,
    }
    for i in range(InPutNum)
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

FunctionIntroduction = (
    "组件功能：解析 SandboxRun 输出的 FunctionJson（actions/print/wake_reason），并按预算口径执行仓位控制，\n"
    "输出 YesMode/NoMode（BUY/SELL/Wait）、YesQty/NoQty（买入/卖出数量）以及 IsAwake。\n\n"
    "核心逻辑：\n"
    "- 读取 FunctionJson.actions，识别 action.type == 'SETPOS'，得到目标仓位 pct（0~1）\n"
    "- 用 Max_BudgetCap * pct 得到目标投入金额 TargetCost；当前资金占用 NowCost = AvgPrice*now_Qty + AskPrice*OpenBuyOrdersQty\n"
    "- 防抖顺序：RebalanceHi -> MinNotional，任一命中则 Wait\n"
    "- 卖出时可卖数量 sellable_qty = now_Qty - OpenSellOrdersQty，避免重复卖出已挂卖部分\n"
    "- 最后用 DeltaCost 与 ask/bid 换算整数 qty（向下取整）输出 BUY/SELL/Wait\n"
    "- IsAwake：若 wake_reason 非空或 actions 内包含 WAKE，则 True\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: Yes_now_Qty\n    type: number\n    required: true\n"
    "  - name: Yes_OpenBuyOrdersQty\n    type: number\n    required: true\n"
    "  - name: Yes_OpenSellOrdersQty\n    type: number\n    required: true\n"
    "  - name: Yes_AvgPrice\n    type: number\n    required: true\n"
    "  - name: Yes_Ask_Price\n    type: number\n    required: true\n"
    "  - name: Yes_Bids_Price\n    type: number\n    required: true\n"
    "  - name: Yes_Min_BudgetCap\n    type: number\n    required: true\n"
    "  - name: Yes_Max_BudgetCap\n    type: number\n    required: true\n"
    "  - name: No_now_Qty\n    type: number\n    required: true\n"
    "  - name: No_OpenBuyOrdersQty\n    type: number\n    required: true\n"
    "  - name: No_OpenSellOrdersQty\n    type: number\n    required: true\n"
    "  - name: No_AvgPrice\n    type: number\n    required: true\n"
    "  - name: No_Ask_Price\n    type: number\n    required: true\n"
    "  - name: No_Bids_Price\n    type: number\n    required: true\n"
    "  - name: No_Min_BudgetCap\n    type: number\n    required: true\n"
    "  - name: No_Max_BudgetCap\n    type: number\n    required: true\n"
    "  - name: FunctionJson\n    type: string\n    required: true\n"
    "  - name: RebalanceHi\n    type: number\n    required: true\n"
    "  - name: MinNotional\n    type: number\n    required: true\n"
    "outputs:\n"
    "  - name: YesMode\n    type: string\n    description: BUY/SELL/Wait\n"
    "  - name: NoMode\n    type: string\n    description: BUY/SELL/Wait\n"
    "  - name: YesQty\n    type: number\n    description: 买入/卖出数量（delta）\n"
    "  - name: NoQty\n    type: number\n    description: 买入/卖出数量（delta）\n"
    "  - name: IsAwake\n    type: boolean\n    description: 是否需要唤醒/执行后续动作\n"
    "```\n"
)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            v = float(x)
        else:
            s = str(x).strip()
            if not s:
                return default
            # 兼容千分位与下划线
            s = s.replace(",", "").replace("_", "")
            v = float(s)
        if not math.isfinite(v):
            return default
        return v
    except Exception:
        return default


getcontext().prec = 28


def _to_decimal(x: Any, default: Decimal = Decimal("0")) -> Decimal:
    """
    将输入安全转换为 Decimal，避免 float 二进制误差扩大。
    """
    try:
        if x is None:
            return default
        if isinstance(x, Decimal):
            return x
        if isinstance(x, (int, float)):
            s = str(x)
        else:
            s = str(x).strip()
        if not s:
            return default
        s = s.replace(",", "").replace("_", "")
        d = Decimal(s)
        if not d.is_finite():
            return default
        return d
    except (InvalidOperation, ValueError, TypeError):
        return default


def _clamp_decimal(x: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _is_sentinel(v: float) -> bool:
    """
    Sentinel value to indicate upstream data fetch failed.
    We treat exactly -999 (or -999.0) as invalid data.
    """
    try:
        return math.isfinite(v) and abs(v - (-999.0)) < 1e-9
    except Exception:
        return False


def _get_inp(node: Dict[str, Any], idx: int) -> Any:
    try:
        return (node.get("Inputs") or [])[idx]
    except Exception:
        return {}


def _read_num(node: Dict[str, Any], idx: int, default: float = 0.0) -> float:
    inp = _get_inp(node, idx) or {}
    v = inp.get("Num")
    if v is None:
        v = inp.get("Context")
    return _safe_float(v, default=default)


def _read_str(node: Dict[str, Any], idx: int, default: str = "") -> str:
    inp = _get_inp(node, idx) or {}
    v = inp.get("Context")
    if v is None:
        v = inp.get("Num")
    if v is None:
        return default
    s = str(v)
    return s if s is not None else default


def _preview_text(s: Any, limit: int = 1200) -> str:
    if s is None:
        return ""
    text = str(s)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def _parse_function_json(s: str) -> Tuple[Dict[str, Any], str]:
    """
    returns: (obj, err)
    """
    if not isinstance(s, str) or not s.strip():
        return {}, "FunctionJson 为空"
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj, ""
        return {}, "FunctionJson 不是 JSON 对象"
    except Exception as e:
        return {}, f"FunctionJson JSON 解析失败: {type(e).__name__}"


def _extract_setpos(actions: Any) -> Dict[str, float]:
    """
    returns: {"Yes": pct, "No": pct}
    若多次 SetPos，同一 side 取最后一次（视为最终目标仓位）。
    """
    out: Dict[str, float] = {}
    if not isinstance(actions, list):
        return out
    for a in actions:
        if not isinstance(a, dict):
            continue
        tp = str(a.get("type") or "").upper().strip()
        if tp not in ("SETPOS", "SET_POS", "SET_POSITION"):
            continue
        side = str(a.get("side") or "Yes").strip().capitalize()
        if side not in ("Yes", "No"):
            continue
        pct = a.get("pct")
        if pct is None:
            pct = a.get("percent")
        pct_f = _safe_float(pct, default=float("nan"))
        if not math.isfinite(pct_f):
            continue
        # 兼容 75 表示 75%
        if pct_f > 1.0 and pct_f <= 100.0:
            pct_f = pct_f / 100.0
        if pct_f < 0.0:
            pct_f = 0.0
        if pct_f > 1.0:
            pct_f = 1.0
        out[side] = float(pct_f)
    return out


def _is_awake(actions: Any, wake_reason: Any) -> bool:
    if wake_reason is not None and str(wake_reason).strip():
        return True
    if isinstance(actions, list):
        for a in actions:
            if isinstance(a, dict) and str(a.get("type") or "").upper().strip() == "WAKE":
                return True
    return False


def _mode_and_qty_by_budget(
    now_qty: float,
    open_buy_orders_qty: float,
    open_sell_orders_qty: float,
    avg_price: float,
    ask_price: float,
    bids_price: float,
    min_budget_cap: float,
    max_budget_cap: float,
    target_pct: Optional[float],
    rebalance_hi: float,
    min_notional: float,
) -> Tuple[str, float, Dict[str, Any]]:
    """
    按预算口径执行仓位调整：
    - NowCost = AvgPrice * now_qty + AskPrice * open_buy_orders_qty
    - TargetCost = Max_BudgetCap * target_pct（target_pct>0 时至少 Min_BudgetCap）
    - 防抖顺序：RebalanceHi -> MinNotional
    - 最终按 ask/bid 将 DeltaCost 映射为整数 qty（向下取整）
    """
    now_q = _to_decimal(_safe_float(now_qty, 0.0), Decimal("0"))
    open_buy_q = _to_decimal(_safe_float(open_buy_orders_qty, 0.0), Decimal("0"))
    open_sell_q = _to_decimal(_safe_float(open_sell_orders_qty, 0.0), Decimal("0"))
    avg_p = _to_decimal(_safe_float(avg_price, 0.0), Decimal("0"))
    ask_p = _to_decimal(_safe_float(ask_price, 0.0), Decimal("0"))
    bid_p = _to_decimal(_safe_float(bids_price, 0.0), Decimal("0"))
    min_cap = _to_decimal(_safe_float(min_budget_cap, 0.0), Decimal("0"))
    budget_cap = _to_decimal(_safe_float(max_budget_cap, 0.0), Decimal("0"))
    hi = _to_decimal(_safe_float(rebalance_hi, float(DEFAULT_REBALANCE_HI)), DEFAULT_REBALANCE_HI)
    min_n = _to_decimal(_safe_float(min_notional, float(DEFAULT_MIN_NOTIONAL)), DEFAULT_MIN_NOTIONAL)

    if now_q < 0:
        now_q = Decimal("0")
    if open_buy_q < 0:
        open_buy_q = Decimal("0")
    if open_sell_q < 0:
        open_sell_q = Decimal("0")
    if avg_p < 0:
        avg_p = Decimal("0")
    if ask_p < 0:
        ask_p = Decimal("0")
    if bid_p < 0:
        bid_p = Decimal("0")
    if min_cap < 0:
        min_cap = Decimal("0")
    if budget_cap < 0:
        budget_cap = Decimal("0")
    if hi < 0:
        hi = Decimal("0")
    if min_n < 0:
        min_n = Decimal("0")

    # 如果策略未给该 side 目标 pct，则该 side 不调整。
    debug_info: Dict[str, Any] = {
        "now_qty": float(now_q),
        "open_buy_orders_qty": float(open_buy_q),
        "open_sell_orders_qty": float(open_sell_q),
        "avg_price": float(avg_p),
        "ask_price": float(ask_p),
        "bid_price": float(bid_p),
        "min_budget_cap": float(min_cap),
        "max_budget_cap": float(budget_cap),
        "rebalance_hi": float(hi),
        "min_notional": float(min_n),
        "target_pct_input": target_pct,
    }

    if target_pct is None:
        debug_info["reason"] = "target_pct_missing"
        return "Wait", 0.0, debug_info

    if budget_cap <= 0:
        debug_info["reason"] = "budget_cap_le_zero"
        return "Wait", 0.0, debug_info

    pct_d = _to_decimal(target_pct, Decimal("0"))
    pct_d = _clamp_decimal(pct_d, Decimal("0"), Decimal("1"))
    debug_info["target_pct"] = float(pct_d)

    used_cost = avg_p * now_q
    reserved_buy_cost = ask_p * open_buy_q
    now_cost = used_cost + reserved_buy_cost

    target_cost = budget_cap * pct_d
    if pct_d == 0:
        target_cost = Decimal("0")
    else:
        target_cost = max(target_cost, min_cap)
    target_cost = _clamp_decimal(target_cost, Decimal("0"), budget_cap)

    now_pct = now_cost / (budget_cap + EPSILON)
    diff = pct_d - now_pct
    delta_cost = target_cost - now_cost
    debug_info.update(
        {
            "used_cost": float(used_cost),
            "reserved_buy_cost": float(reserved_buy_cost),
            "now_cost": float(now_cost),
            "target_cost": float(target_cost),
            "now_pct": float(now_pct),
            "diff": float(diff),
            "delta_cost": float(delta_cost),
        }
    )

    abs_diff = abs(diff)
    if abs_diff <= hi:
        debug_info["reason"] = "rebalance_hi_blocked"
        return "Wait", 0.0, debug_info

    if abs(delta_cost) < min_n:
        debug_info["reason"] = "min_notional_blocked"
        return "Wait", 0.0, debug_info

    if delta_cost > 0:
        if ask_p <= 0:
            debug_info["reason"] = "ask_price_invalid"
            return "Wait", 0.0, debug_info
        qty_buy = (delta_cost / ask_p).to_integral_value(rounding=ROUND_DOWN)
        debug_info["qty_buy_raw"] = float(delta_cost / ask_p)
        debug_info["qty_buy_floor"] = float(qty_buy)
        if qty_buy < 1:
            debug_info["reason"] = "buy_qty_lt_1"
            return "Wait", 0.0, debug_info
        debug_info["reason"] = "buy"
        return "BUY", float(qty_buy), debug_info

    if delta_cost < 0:
        if bid_p <= 0:
            debug_info["reason"] = "bid_price_invalid"
            return "Wait", 0.0, debug_info
        qty_sell = ((-delta_cost) / bid_p).to_integral_value(rounding=ROUND_DOWN)
        debug_info["qty_sell_raw"] = float((-delta_cost) / bid_p)
        sellable_q = now_q - open_sell_q
        if sellable_q < 0:
            sellable_q = Decimal("0")
        sellable_q = sellable_q.to_integral_value(rounding=ROUND_DOWN)
        debug_info["sellable_qty"] = float(sellable_q)
        if qty_sell > sellable_q:
            qty_sell = sellable_q
        debug_info["qty_sell_floor"] = float(qty_sell)
        if qty_sell < 1:
            debug_info["reason"] = "sell_qty_lt_1"
            return "Wait", 0.0, debug_info
        debug_info["reason"] = "sell"
        return "SELL", float(qty_sell), debug_info

    debug_info["reason"] = "delta_cost_zero"
    return "Wait", 0.0, debug_info


def run_node(node: Dict[str, Any]):
    debug_lines = []

    # Inputs:
    # 0  Yes_now_Qty
    # 1  Yes_OpenBuyOrdersQty
    # 2  Yes_OpenSellOrdersQty
    # 3  Yes_AvgPrice
    # 4  Yes_Ask_Price
    # 5  Yes_Bids_Price
    # 6  Yes_Min_BudgetCap
    # 7  Yes_Max_BudgetCap
    # 8  No_now_Qty
    # 9  No_OpenBuyOrdersQty
    # 10 No_OpenSellOrdersQty
    # 11 No_AvgPrice
    # 12 No_Ask_Price
    # 13 No_Bids_Price
    # 14 No_Min_BudgetCap
    # 15 No_Max_BudgetCap
    # 16 FunctionJson
    # 17 RebalanceHi
    # 18 MinNotional
    yes_now = _read_num(node, 0, 0.0)
    yes_open_buy = _read_num(node, 1, 0.0)
    yes_open_sell = _read_num(node, 2, 0.0)
    yes_avg = _read_num(node, 3, 0.0)
    yes_ask = _read_num(node, 4, 0.0)
    yes_bid = _read_num(node, 5, 0.0)
    yes_min_cap = _read_num(node, 6, 0.0)
    yes_max_cap = _read_num(node, 7, 0.0)
    no_now = _read_num(node, 8, 0.0)
    no_open_buy = _read_num(node, 9, 0.0)
    no_open_sell = _read_num(node, 10, 0.0)
    no_avg = _read_num(node, 11, 0.0)
    no_ask = _read_num(node, 12, 0.0)
    no_bid = _read_num(node, 13, 0.0)
    no_min_cap = _read_num(node, 14, 0.0)
    no_max_cap = _read_num(node, 15, 0.0)
    func_json_s = _read_str(node, 16, "")
    rebalance_hi = _read_num(node, 17, float(DEFAULT_REBALANCE_HI))
    min_notional = _read_num(node, 18, float(DEFAULT_MIN_NOTIONAL))

    debug_lines.append("[INPUT] FunctionJson raw:")
    debug_lines.append(_preview_text(func_json_s, 2000) or "<empty>")
    debug_lines.append(
        "[INPUT] Params: "
        f"rebalance_hi={rebalance_hi}, min_notional={min_notional}, "
        f"yes_max_cap={yes_max_cap}, no_max_cap={no_max_cap}"
    )

    # Hard stop: if any numeric input is -999, do NOT trade.
    # This prevents downstream from treating "failed fetch" as "0 position".
    numeric_inputs = (
        yes_now,
        yes_open_buy,
        yes_open_sell,
        yes_avg,
        yes_ask,
        yes_bid,
        yes_min_cap,
        yes_max_cap,
        no_now,
        no_open_buy,
        no_open_sell,
        no_avg,
        no_ask,
        no_bid,
        no_min_cap,
        no_max_cap,
        rebalance_hi,
        min_notional,
    )
    if any(_is_sentinel(x) for x in numeric_inputs):
        Outputs[0]["Context"] = "Wait"
        Outputs[1]["Context"] = "Wait"
        Outputs[2]["Num"] = 0.0
        Outputs[3]["Num"] = 0.0
        Outputs[4]["Boolean"] = False
        debug_lines.append("[BLOCK] 检测到 -999 sentinel，直接停止交易。")
        return {"outputs": Outputs, "debug": "\n".join(debug_lines)}

    obj, _err = _parse_function_json(func_json_s)
    if _err:
        debug_lines.append(f"[PARSE] ERROR: {_err}")
    else:
        debug_lines.append("[PARSE] OK")
    actions = obj.get("actions", [])
    wake_reason = obj.get("wake_reason")
    debug_lines.append(f"[PARSE] actions_count={len(actions) if isinstance(actions, list) else 0}")
    debug_lines.append(f"[PARSE] wake_reason={repr(wake_reason)}")

    setpos = _extract_setpos(actions)
    yes_pct = setpos.get("Yes")
    no_pct = setpos.get("No")
    debug_lines.append(f"[SETPOS] extracted={json.dumps(setpos, ensure_ascii=False)}")
    debug_lines.append(f"[SETPOS] yes_pct={yes_pct}, no_pct={no_pct}")

    yes_mode, yes_qty, yes_debug = _mode_and_qty_by_budget(
        yes_now,
        yes_open_buy,
        yes_open_sell,
        yes_avg,
        yes_ask,
        yes_bid,
        yes_min_cap,
        yes_max_cap,
        yes_pct,
        rebalance_hi,
        min_notional,
    )
    no_mode, no_qty, no_debug = _mode_and_qty_by_budget(
        no_now,
        no_open_buy,
        no_open_sell,
        no_avg,
        no_ask,
        no_bid,
        no_min_cap,
        no_max_cap,
        no_pct,
        rebalance_hi,
        min_notional,
    )

    is_awake = _is_awake(actions, wake_reason)
    debug_lines.append(f"[YES_CALC] {json.dumps(yes_debug, ensure_ascii=False, sort_keys=True)}")
    debug_lines.append(f"[NO_CALC] {json.dumps(no_debug, ensure_ascii=False, sort_keys=True)}")
    debug_lines.append(
        f"[RESULT] YesMode={yes_mode}, YesQty={yes_qty}, NoMode={no_mode}, NoQty={no_qty}, IsAwake={is_awake}"
    )

    # Outputs: YesMode, NoMode, YesQty, NoQty, IsAwake
    Outputs[0]["Context"] = str(yes_mode)
    Outputs[1]["Context"] = str(no_mode)
    Outputs[2]["Num"] = float(yes_qty)
    Outputs[3]["Num"] = float(no_qty)
    Outputs[4]["Boolean"] = bool(is_awake)
    return {"outputs": Outputs, "debug": "\n".join(debug_lines)}


# ---- Port definitions ----
Inputs[0]["name"] = "Yes_now_Qty"
Inputs[0]["Kind"] = "Num"
Inputs[1]["name"] = "Yes_OpenBuyOrdersQty"
Inputs[1]["Kind"] = "Num"
Inputs[2]["name"] = "Yes_OpenSellOrdersQty"
Inputs[2]["Kind"] = "Num"
Inputs[3]["name"] = "Yes_AvgPrice"
Inputs[3]["Kind"] = "Num"
Inputs[4]["name"] = "Yes_Ask_Price"
Inputs[4]["Kind"] = "Num"
Inputs[5]["name"] = "Yes_Bids_Price"
Inputs[5]["Kind"] = "Num"
Inputs[6]["name"] = "Yes_Min_BudgetCap"
Inputs[6]["Kind"] = "Num"
Inputs[7]["name"] = "Yes_Max_BudgetCap"
Inputs[7]["Kind"] = "Num"
Inputs[8]["name"] = "No_now_Qty"
Inputs[8]["Kind"] = "Num"
Inputs[9]["name"] = "No_OpenBuyOrdersQty"
Inputs[9]["Kind"] = "Num"
Inputs[10]["name"] = "No_OpenSellOrdersQty"
Inputs[10]["Kind"] = "Num"
Inputs[11]["name"] = "No_AvgPrice"
Inputs[11]["Kind"] = "Num"
Inputs[12]["name"] = "No_Ask_Price"
Inputs[12]["Kind"] = "Num"
Inputs[13]["name"] = "No_Bids_Price"
Inputs[13]["Kind"] = "Num"
Inputs[14]["name"] = "No_Min_BudgetCap"
Inputs[14]["Kind"] = "Num"
Inputs[15]["name"] = "No_Max_BudgetCap"
Inputs[15]["Kind"] = "Num"
Inputs[16]["name"] = "FunctionJson"
Inputs[16]["Kind"] = "String"
Inputs[16]["IsLabel"] = False
Inputs[17]["name"] = "RebalanceHi"
Inputs[17]["Kind"] = "Num"
Inputs[18]["name"] = "MinNotional"
Inputs[18]["Kind"] = "Num"

# 默认端口模式：
# - 除 RebalanceHi/MinNotional 外，其余输入默认 Link 模式（IsLabel=False）
# - 上述两个防抖参数保留为可直接填写默认值
for _idx in range(0, 17):
    Inputs[_idx]["IsLabel"] = False

Inputs[17]["IsLabel"] = True
Inputs[18]["IsLabel"] = True
Inputs[17]["Num"] = float(DEFAULT_REBALANCE_HI)
Inputs[18]["Num"] = float(DEFAULT_MIN_NOTIONAL)

Outputs[0]["name"] = "YesMode"
Outputs[0]["Kind"] = "String"
Outputs[1]["name"] = "NoMode"
Outputs[1]["Kind"] = "String"
Outputs[2]["name"] = "YesQty"
Outputs[2]["Kind"] = "Num"
Outputs[3]["name"] = "NoQty"
Outputs[3]["Kind"] = "Num"
Outputs[4]["name"] = "IsAwake"
Outputs[4]["Kind"] = "Boolean"


