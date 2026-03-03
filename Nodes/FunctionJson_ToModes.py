import json
import math
from decimal import Decimal, InvalidOperation, ROUND_DOWN, getcontext
from typing import Any, Dict, Optional, Tuple

# **Define the number of outputs and inputs**
OutPutNum = 5
InPutNum = 17

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
    "- 用 Max_BudgetCap * pct 得到目标投入金额 TargetCost；当前资金占用 NowCost = AvgPrice*now_Qty + AskPrice*OpenOrdersQty（仅挂买单 qty）\n"
    "- 防抖顺序：RebalanceHi -> MinNotional，任一命中则 Wait\n"
    "- 最后用 DeltaCost 与 ask/bid 换算整数 qty（向下取整）输出 BUY/SELL/Wait\n"
    "- IsAwake：若 wake_reason 非空或 actions 内包含 WAKE，则 True\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: Yes_now_Qty\n    type: number\n    required: true\n"
    "  - name: Yes_OpenOrdersQty\n    type: number\n    required: true\n"
    "  - name: Yes_AvgPrice\n    type: number\n    required: true\n"
    "  - name: Yes_Ask_Price\n    type: number\n    required: true\n"
    "  - name: Yes_Bids_Price\n    type: number\n    required: true\n"
    "  - name: Yes_Min_BudgetCap\n    type: number\n    required: true\n"
    "  - name: Yes_Max_BudgetCap\n    type: number\n    required: true\n"
    "  - name: No_now_Qty\n    type: number\n    required: true\n"
    "  - name: No_OpenOrdersQty\n    type: number\n    required: true\n"
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
    open_orders_qty: float,
    avg_price: float,
    ask_price: float,
    bids_price: float,
    min_budget_cap: float,
    max_budget_cap: float,
    target_pct: Optional[float],
    rebalance_hi: float,
    min_notional: float,
) -> Tuple[str, float]:
    """
    按预算口径执行仓位调整：
    - NowCost = AvgPrice * now_qty + AskPrice * open_orders_qty
    - TargetCost = Max_BudgetCap * target_pct（target_pct>0 时至少 Min_BudgetCap）
    - 防抖顺序：RebalanceHi -> MinNotional
    - 最终按 ask/bid 将 DeltaCost 映射为整数 qty（向下取整）
    """
    now_q = _to_decimal(_safe_float(now_qty, 0.0), Decimal("0"))
    open_q = _to_decimal(_safe_float(open_orders_qty, 0.0), Decimal("0"))
    avg_p = _to_decimal(_safe_float(avg_price, 0.0), Decimal("0"))
    ask_p = _to_decimal(_safe_float(ask_price, 0.0), Decimal("0"))
    bid_p = _to_decimal(_safe_float(bids_price, 0.0), Decimal("0"))
    min_cap = _to_decimal(_safe_float(min_budget_cap, 0.0), Decimal("0"))
    budget_cap = _to_decimal(_safe_float(max_budget_cap, 0.0), Decimal("0"))
    hi = _to_decimal(_safe_float(rebalance_hi, float(DEFAULT_REBALANCE_HI)), DEFAULT_REBALANCE_HI)
    min_n = _to_decimal(_safe_float(min_notional, float(DEFAULT_MIN_NOTIONAL)), DEFAULT_MIN_NOTIONAL)

    if now_q < 0:
        now_q = Decimal("0")
    if open_q < 0:
        open_q = Decimal("0")
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
    if target_pct is None:
        return "Wait", 0.0

    if budget_cap <= 0:
        return "Wait", 0.0

    pct_d = _to_decimal(target_pct, Decimal("0"))
    pct_d = _clamp_decimal(pct_d, Decimal("0"), Decimal("1"))

    used_cost = avg_p * now_q
    reserved_buy_cost = ask_p * open_q
    now_cost = used_cost + reserved_buy_cost

    target_cost = budget_cap * pct_d
    if pct_d == 0:
        target_cost = Decimal("0")
    else:
        target_cost = max(target_cost, min_cap)
    target_cost = _clamp_decimal(target_cost, Decimal("0"), budget_cap)

    now_pct = now_cost / (budget_cap + EPSILON)
    diff = pct_d - now_pct

    abs_diff = abs(diff)
    if abs_diff <= hi:
        return "Wait", 0.0

    delta_cost = target_cost - now_cost
    if abs(delta_cost) < min_n:
        return "Wait", 0.0

    if delta_cost > 0:
        if ask_p <= 0:
            return "Wait", 0.0
        qty_buy = (delta_cost / ask_p).to_integral_value(rounding=ROUND_DOWN)
        if qty_buy < 1:
            return "Wait", 0.0
        return "BUY", float(qty_buy)

    if delta_cost < 0:
        if bid_p <= 0:
            return "Wait", 0.0
        qty_sell = ((-delta_cost) / bid_p).to_integral_value(rounding=ROUND_DOWN)
        if qty_sell > now_q:
            qty_sell = now_q.to_integral_value(rounding=ROUND_DOWN)
        if qty_sell < 1:
            return "Wait", 0.0
        return "SELL", float(qty_sell)

    return "Wait", 0.0


def run_node(node: Dict[str, Any]):
    # Inputs:
    # 0  Yes_now_Qty
    # 1  Yes_OpenOrdersQty
    # 2  Yes_AvgPrice
    # 3  Yes_Ask_Price
    # 4  Yes_Bids_Price
    # 5  Yes_Min_BudgetCap
    # 6  Yes_Max_BudgetCap
    # 7  No_now_Qty
    # 8  No_OpenOrdersQty
    # 9  No_AvgPrice
    # 10 No_Ask_Price
    # 11 No_Bids_Price
    # 12 No_Min_BudgetCap
    # 13 No_Max_BudgetCap
    # 14 FunctionJson
    # 15 RebalanceHi
    # 16 MinNotional
    yes_now = _read_num(node, 0, 0.0)
    yes_open = _read_num(node, 1, 0.0)
    yes_avg = _read_num(node, 2, 0.0)
    yes_ask = _read_num(node, 3, 0.0)
    yes_bid = _read_num(node, 4, 0.0)
    yes_min_cap = _read_num(node, 5, 0.0)
    yes_max_cap = _read_num(node, 6, 0.0)
    no_now = _read_num(node, 7, 0.0)
    no_open = _read_num(node, 8, 0.0)
    no_avg = _read_num(node, 9, 0.0)
    no_ask = _read_num(node, 10, 0.0)
    no_bid = _read_num(node, 11, 0.0)
    no_min_cap = _read_num(node, 12, 0.0)
    no_max_cap = _read_num(node, 13, 0.0)
    func_json_s = _read_str(node, 14, "")
    rebalance_hi = _read_num(node, 15, float(DEFAULT_REBALANCE_HI))
    min_notional = _read_num(node, 16, float(DEFAULT_MIN_NOTIONAL))

    # Hard stop: if any numeric input is -999, do NOT trade.
    # This prevents downstream from treating "failed fetch" as "0 position".
    numeric_inputs = (
        yes_now,
        yes_open,
        yes_avg,
        yes_ask,
        yes_bid,
        yes_min_cap,
        yes_max_cap,
        no_now,
        no_open,
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
        return Outputs

    obj, _err = _parse_function_json(func_json_s)
    actions = obj.get("actions", [])
    wake_reason = obj.get("wake_reason")

    setpos = _extract_setpos(actions)
    yes_pct = setpos.get("Yes")
    no_pct = setpos.get("No")

    yes_mode, yes_qty = _mode_and_qty_by_budget(
        yes_now,
        yes_open,
        yes_avg,
        yes_ask,
        yes_bid,
        yes_min_cap,
        yes_max_cap,
        yes_pct,
        rebalance_hi,
        min_notional,
    )
    no_mode, no_qty = _mode_and_qty_by_budget(
        no_now,
        no_open,
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

    # Outputs: YesMode, NoMode, YesQty, NoQty, IsAwake
    Outputs[0]["Context"] = str(yes_mode)
    Outputs[1]["Context"] = str(no_mode)
    Outputs[2]["Num"] = float(yes_qty)
    Outputs[3]["Num"] = float(no_qty)
    Outputs[4]["Boolean"] = bool(is_awake)
    return Outputs


# ---- Port definitions ----
Inputs[0]["name"] = "Yes_now_Qty"
Inputs[0]["Kind"] = "Num"
Inputs[1]["name"] = "Yes_OpenOrdersQty"
Inputs[1]["Kind"] = "Num"
Inputs[2]["name"] = "Yes_AvgPrice"
Inputs[2]["Kind"] = "Num"
Inputs[3]["name"] = "Yes_Ask_Price"
Inputs[3]["Kind"] = "Num"
Inputs[4]["name"] = "Yes_Bids_Price"
Inputs[4]["Kind"] = "Num"
Inputs[5]["name"] = "Yes_Min_BudgetCap"
Inputs[5]["Kind"] = "Num"
Inputs[6]["name"] = "Yes_Max_BudgetCap"
Inputs[6]["Kind"] = "Num"
Inputs[7]["name"] = "No_now_Qty"
Inputs[7]["Kind"] = "Num"
Inputs[8]["name"] = "No_OpenOrdersQty"
Inputs[8]["Kind"] = "Num"
Inputs[9]["name"] = "No_AvgPrice"
Inputs[9]["Kind"] = "Num"
Inputs[10]["name"] = "No_Ask_Price"
Inputs[10]["Kind"] = "Num"
Inputs[11]["name"] = "No_Bids_Price"
Inputs[11]["Kind"] = "Num"
Inputs[12]["name"] = "No_Min_BudgetCap"
Inputs[12]["Kind"] = "Num"
Inputs[13]["name"] = "No_Max_BudgetCap"
Inputs[13]["Kind"] = "Num"
Inputs[14]["name"] = "FunctionJson"
Inputs[14]["Kind"] = "String"
Inputs[14]["IsLabel"] = False
Inputs[15]["name"] = "RebalanceHi"
Inputs[15]["Kind"] = "Num"
Inputs[16]["name"] = "MinNotional"
Inputs[16]["Kind"] = "Num"

# 默认端口模式：
# - 除 RebalanceHi/MinNotional 外，其余输入默认 Link 模式（IsLabel=False）
# - 上述两个防抖参数保留为可直接填写默认值
for _idx in range(0, 15):
    Inputs[_idx]["IsLabel"] = False

Inputs[15]["IsLabel"] = True
Inputs[16]["IsLabel"] = True
Inputs[15]["Num"] = float(DEFAULT_REBALANCE_HI)
Inputs[16]["Num"] = float(DEFAULT_MIN_NOTIONAL)

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


