import json
import math
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP, getcontext
from typing import Any, Dict, Optional, Tuple

# **Define the number of outputs and inputs**
OutPutNum = 5
InPutNum = 9

# 若目标仓位与当前仓位差值很小（<= 5%），忽略调整，避免因零头反复下单失败
REBALANCE_PCT_THRESHOLD = Decimal("0.05")

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
    "组件功能：解析 SandboxRun 输出的 FunctionJson（actions/print/wake_reason），并转换为交易执行所需的\n"
    "YesMode/NoMode（BUY/SELL/Wait）、YesQty/NoQty（买入/卖出数量）以及 IsAwake。\n\n"
    "核心逻辑：\n"
    "- 读取 FunctionJson.actions，优先识别 action.type == 'SETPOS'，得到目标仓位 pct（0~1）\n"
    "- 用 pct * Max_Qty 得到目标数量 target_qty，与 (now_Qty + OpenOrdersQty) 比较得到 BUY/SELL/Wait 及 delta 数量\n"
    "- 若 |target_pct - now_pct| <= 5%：忽略该笔调整（Wait，Qty=0），避免零头反复触发下单\n"
    "- 若 delta < Min_Qty，则忽略该笔调整（Wait，Qty=0）\n"
    "- IsAwake：若 wake_reason 非空或 actions 内包含 WAKE，则 True\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: Yes_Min_Qty\n    type: number\n    required: true\n"
    "  - name: Yes_Max_Qty\n    type: number\n    required: true\n"
    "  - name: No_Min_Qty\n    type: number\n    required: true\n"
    "  - name: No_Max_Qty\n    type: number\n    required: true\n"
    "  - name: Yes_now_Qty\n    type: number\n    required: true\n"
    "  - name: No_now_Qty\n    type: number\n    required: true\n"
    "  - name: Yes_OpenOrdersQty\n    type: number\n    required: true\n"
    "  - name: No_OpenOrdersQty\n    type: number\n    required: true\n"
    "  - name: FunctionJson\n    type: string\n    required: true\n"
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


def _step_from_min_qty(min_q: Decimal) -> Decimal:
    """
    交易数量的最小步进优先用 Min_Qty。
    - min_q <= 0: 表示未提供步进信息，则不做步进约束
    - min_q > 0 : 视作步进（例如 1 / 0.01 / 0.05 等）
    """
    if min_q is None:
        return Decimal("0")
    if min_q <= 0:
        return Decimal("0")
    return min_q


def _quantize_to_step(value: Decimal, step: Decimal, rounding) -> Decimal:
    """
    按 step 做倍数取整：
    - ROUND_DOWN: 截断（不超量买/卖）
    - ROUND_UP  : 进位（用于风控场景，确保卖出足够）
    """
    if step is None or step <= 0:
        return value
    q = (value / step).to_integral_value(rounding=rounding)
    return q * step


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


def _mode_and_qty(
    now_qty: float,
    open_orders_qty: float,
    min_qty: float,
    max_qty: float,
    target_pct: Optional[float],
) -> Tuple[str, float]:
    """
    - target_pct 为 None 表示不调整（Wait）
    """
    max_q = _to_decimal(_safe_float(max_qty, 0.0), Decimal("0"))
    min_q = _to_decimal(_safe_float(min_qty, 0.0), Decimal("0"))
    now_q = _to_decimal(_safe_float(now_qty, 0.0), Decimal("0"))
    open_q = _to_decimal(_safe_float(open_orders_qty, 0.0), Decimal("0"))

    if max_q < 0:
        max_q = Decimal("0")
    if min_q < 0:
        min_q = Decimal("0")
    if now_q < 0:
        now_q = Decimal("0")
    if open_q < 0:
        open_q = Decimal("0")

    now_total_q = now_q + open_q
    step = _step_from_min_qty(min_q)

    # 如果 FunctionJson 没有给出目标仓位：默认不做调整，但仍强制执行“超 max 必须卖出”的风控。
    if target_pct is None:
        if now_total_q > max_q:
            # 风控：必须卖出足够让仓位 <= max
            # 数量尽可能向下取整；若向下取整仍无法使仓位回到 max 内，则再向上取整兜底
            over = now_total_q - max_q
            qty_down = _quantize_to_step(over, step, rounding=ROUND_DOWN)
            if qty_down > 0 and (now_total_q - qty_down) <= max_q:
                qty_d = qty_down
            else:
                qty_d = _quantize_to_step(over, step, rounding=ROUND_UP)
            if qty_d <= 0 or (min_q > 0 and qty_d < min_q):
                return "Wait", 0.0
            return "SELL", float(qty_d)
        return "Wait", 0.0

    pct_d = _to_decimal(target_pct, Decimal("0"))
    if pct_d < 0:
        pct_d = Decimal("0")
    if pct_d > 1:
        pct_d = Decimal("1")

    # 小幅偏差忽略：避免因为零头做微小调仓，导致反复提交失败
    # 以 max_q 为 100% 仓位基准，当前仓位 pct = (now + open) / max_q
    if max_q > 0:
        now_pct = _clamp_decimal(now_total_q / max_q, Decimal("0"), Decimal("1"))
        if abs(pct_d - now_pct) <= REBALANCE_PCT_THRESHOLD:
            return "Wait", 0.0

    # 目标数量：保留小数，不再 round/int，避免四舍五入导致超买/超卖
    target_qty = _clamp_decimal(pct_d * max_q, Decimal("0"), max_q)

    delta = target_qty - now_total_q
    if delta == 0:
        return "Wait", 0.0

    # 数量：按 step 截断（ROUND_DOWN），避免“进位”导致交易失败（例如余额不足/超限）
    if delta > 0:
        qty_d = _quantize_to_step(delta, step, rounding=ROUND_DOWN)
        mode = "BUY"
    else:
        qty_d = _quantize_to_step(-delta, step, rounding=ROUND_DOWN)
        mode = "SELL"

    if qty_d <= 0 or (min_q > 0 and qty_d < min_q):
        return "Wait", 0.0

    return mode, float(qty_d)


def run_node(node: Dict[str, Any]):
    # Inputs:
    # 0 Yes_Min_Qty
    # 1 Yes_Max_Qty
    # 2 No_Min_Qty
    # 3 No_Max_Qty
    # 4 Yes_now_Qty
    # 5 No_now_Qty
    # 6 Yes_OpenOrdersQty
    # 7 No_OpenOrdersQty
    # 8 FunctionJson
    yes_min = _read_num(node, 0, 0.0)
    yes_max = _read_num(node, 1, 0.0)
    no_min = _read_num(node, 2, 0.0)
    no_max = _read_num(node, 3, 0.0)
    yes_now = _read_num(node, 4, 0.0)
    no_now = _read_num(node, 5, 0.0)
    yes_open = _read_num(node, 6, 0.0)
    no_open = _read_num(node, 7, 0.0)
    func_json_s = _read_str(node, 8, "")

    # Hard stop: if any numeric input is -999, do NOT trade.
    # This prevents downstream from treating "failed fetch" as "0 position".
    if any(_is_sentinel(x) for x in (yes_min, yes_max, no_min, no_max, yes_now, no_now, yes_open, no_open)):
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

    yes_mode, yes_qty = _mode_and_qty(yes_now, yes_open, yes_min, yes_max, yes_pct)
    no_mode, no_qty = _mode_and_qty(no_now, no_open, no_min, no_max, no_pct)

    is_awake = _is_awake(actions, wake_reason)

    # Outputs: YesMode, NoMode, YesQty, NoQty, IsAwake
    Outputs[0]["Context"] = str(yes_mode)
    Outputs[1]["Context"] = str(no_mode)
    Outputs[2]["Num"] = float(yes_qty)
    Outputs[3]["Num"] = float(no_qty)
    Outputs[4]["Boolean"] = bool(is_awake)
    return Outputs


# ---- Port definitions ----
Inputs[0]["name"] = "Yes_Min_Qty"
Inputs[0]["Kind"] = "Num"
Inputs[1]["name"] = "Yes_Max_Qty"
Inputs[1]["Kind"] = "Num"
Inputs[2]["name"] = "No_Min_Qty"
Inputs[2]["Kind"] = "Num"
Inputs[3]["name"] = "No_Max_Qty"
Inputs[3]["Kind"] = "Num"
Inputs[4]["name"] = "Yes_now_Qty"
Inputs[4]["Kind"] = "Num"
Inputs[5]["name"] = "No_now_Qty"
Inputs[5]["Kind"] = "Num"
Inputs[6]["name"] = "Yes_OpenOrdersQty"
Inputs[6]["Kind"] = "Num"
Inputs[7]["name"] = "No_OpenOrdersQty"
Inputs[7]["Kind"] = "Num"
Inputs[8]["name"] = "FunctionJson"
Inputs[8]["Kind"] = "String"
Inputs[8]["IsLabel"] = False

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


