import math

# **Define the number of outputs and inputs**
OutPutNum = 1
InPutNum = 3

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
        "IsLabel": False,
    }
    for i in range(InPutNum)
]

NodeKind = 'Normal'
Lable = [{"Id": "Label1", "Kind": "None"}]

FunctionIntroduction = '组件功能：计算当前仓位占最大仓位的百分比（0~1）。\\n\\n代码功能摘要：将 (Now_qty + OpenOrdersQty) 视为当前占用仓位，除以 Max_qty 得到百分比，并做除零保护与 clamp 到 0~1。\\n\\n参数\\n```yaml\\ninputs:\\n  - name: Now_qty\\n    type: number\\n    required: true\\n    description: 当前已持仓数量\\n  - name: Max_qty\\n    type: number\\n    required: true\\n    description: 最大允许持仓数量\\n  - name: OpenOrdersQty\\n    type: number\\n    required: true\\n    description: 当前挂单占用数量（会加到 Now_qty 上）\\noutputs:\\n  - name: PositionPct\\n    type: number\\n    description: 当前仓位/最大仓位（0~1）\\n```\\n'


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
    max_qty = _read_num(node, 1, 0.0)
    open_orders_qty = _read_num(node, 2, 0.0)

    # 与仓位调整节点一致：把 open_orders 加到当前仓位上
    current_qty = now_qty + open_orders_qty
    if current_qty < 0.0:
        current_qty = 0.0

    if max_qty <= 0.0:
        pct = 0.0
    else:
        pct = _clamp01(current_qty / max_qty)

    Outputs[0]["Num"] = float(pct)
    return Outputs


# ---- Port definitions ----
Inputs[0]["name"] = "Now_qty"
Inputs[0]["Kind"] = "Num"
Inputs[1]["name"] = "Max_qty"
Inputs[1]["Kind"] = "Num"
Inputs[2]["name"] = "OpenOrdersQty"
Inputs[2]["Kind"] = "Num"

Outputs[0]["name"] = "PositionPct"
Outputs[0]["Kind"] = "Num"


