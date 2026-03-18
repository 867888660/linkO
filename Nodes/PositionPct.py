import math

# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 5

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
        "IsLabel": False,
    }
    for i in range(InPutNum)
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

FunctionIntroduction = (
    "组件功能：按【预算口径】计算当前仓位占最大预算的百分比（0~1）。\n\n"
    "核心公式：\n"
    "NowCost = AvgPrice*Now_qty + NowAsk*OpenOrdersQty（OpenOrdersQty 仅统计挂买单）\n"
    "PositionPct = clamp01(NowCost / Max_BudgetCap)\n\n"
    "参数\n```yaml\n"
    "inputs:\n"
    "  - name: Now_qty\n    type: number\n    required: true\n    description: 当前已持仓数量\n"
    "  - name: OpenOrdersQty\n    type: number\n    required: true\n    description: 当前挂买单数量（仅买单；用于预留资金占用）\n"
    "  - name: AvgPrice\n    type: number\n    required: true\n    description: 当前持仓均价（VWAP）\n"
    "  - name: NowAsk\n    type: number\n    required: true\n    description: 当前 ask（近似挂单价，用于预留成本）\n"
    "  - name: Max_BudgetCap\n    type: number\n    required: true\n    description: 该 side 的最大资金预算（稳定分母）\n"
    "outputs:\n"
    "  - name: PositionPct\n    type: number\n    description: 当前占用资金 / 最大预算（0~1）\n"
    "```\n"
)


def _safe_float(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            v = float(x)
        else:
            s = str(x).strip()
            if not s:
                return default
            s = s.replace(",", "").replace("_", "")
            v = float(s)
        if not math.isfinite(v):
            return default
        return v
    except Exception:
        return default


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _read_num(node, idx: int, default: float = 0.0) -> float:
    try:
        inp = (node.get("Inputs") or [])[idx] or {}
    except Exception:
        return default
    v = inp.get("Num")
    if v is None:
        v = inp.get("Context")
    return _safe_float(v, default=default)


def run_node(node):
    now_qty = _read_num(node, 0, 0.0)
    open_orders_qty = _read_num(node, 1, 0.0)
    avg_price = _read_num(node, 2, 0.0)
    now_ask = _read_num(node, 3, 0.0)
    max_budget_cap = _read_num(node, 4, 0.0)

    if now_qty < 0.0:
        now_qty = 0.0
    if open_orders_qty < 0.0:
        open_orders_qty = 0.0
    if avg_price < 0.0:
        avg_price = 0.0
    if now_ask < 0.0:
        now_ask = 0.0
    if max_budget_cap <= 0.0:
        pct = 0.0
    else:
        now_cost = (avg_price * now_qty) + (now_ask * open_orders_qty)
        if now_cost < 0.0:
            now_cost = 0.0
        pct = _clamp01(now_cost / max_budget_cap)

    Outputs[0]["Num"] = float(pct)
    return Outputs


# ---- Port definitions ----
Inputs[0]["name"] = "Now_qty"
Inputs[0]["Kind"] = "Num"

Inputs[1]["name"] = "OpenOrdersQty"
Inputs[1]["Kind"] = "Num"

Inputs[2]["name"] = "AvgPrice"
Inputs[2]["Kind"] = "Num"

Inputs[3]["name"] = "NowAsk"
Inputs[3]["Kind"] = "Num"

Inputs[4]["name"] = "Max_BudgetCap"
Inputs[4]["Kind"] = "Num"

Outputs[0]["name"] = "PositionPct"
Outputs[0]["Kind"] = "Num"


