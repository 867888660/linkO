import ast
import json
import re

# ===== 节点定义 =====
OutPutNum = 2
InPutNum = 8

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
    "组件功能：Fllow_Truth（事实方向双桶理念：CORE+TP，最终输出为方向总目标仓位）。\n"
    "本组件适用于：仅有实时盘口/持仓数据，没有额外因子时，按时间与风险动态管理 FactSide 与 OppSide。\n"
    "注意：引擎只支持 SetPos(side, pct) 的方向总仓位目标，不做真实分桶下单。\n\n"
    "字段兼容：键名大小写、下划线、连字符会被自动容错（例如 Yes_now_ask / yes-now-ask / YESNOWASK 都可识别）。\n\n"
    "参数：\n"
    "```yaml\n"
    "inputs:\n"
    "  - name: UseData\n"
    "    type: string\n"
    "    required: true\n"
    "    description: |\n"
    "      实时行情与账户字段。支持 JSON 对象字符串，或多行 key=value / key: value。\n"
    "      必备字段（至少应提供）：\n"
    "      - Yes_now_ask, Yes_now_bid, No_now_ask, No_now_bid\n"
    "      - Yes_now_Qty, No_now_Qty\n"
    "      - Yes_now_avgPrice, No_now_avgPrice（用于止盈止损比率，<=0 时该方向不触发 RR/profit 判断）\n"
    "      - Yes_OpenOrdersQty, No_OpenOrdersQty（用于 Pos0 判定，避免撮合中抖动）\n"
    "      - Yes_Now_Pos, No_Now_Pos（当前仓位比值，兼容 Yes_Pos/No_Pos）\n"
    "      - 可选上限：Yes_MaxPos/No_MaxPos（或 Yes_PosCap/No_PosCap，不传默认 1.0）\n"
    "      - day_to_end（剩余天数）\n"
    "      可选字段：Yes_target_pos/No_target_pos（用于“趋势建仓只上调不下调”的历史目标记忆）\n"
    "  - name: FactSide\n"
    "    type: string\n"
    "    required: true\n"
    "    description: |\n"
    "      事实方向，只能是 Yes 或 No。\n"
    "      策略会自动把该方向映射为 F_*，另一侧映射为 O_*，后续规则对称执行。\n"
    "  - name: FactSide_ref_ask\n"
    "    type: number\n"
    "    required: true\n"
    "    description: |\n"
    "      参考 ask（0~1）。用于比较当前 F_ask 的高低并触发：\n"
    "      - 先手反买（F_ask > ref_ask + 0.05）\n"
    "      - 趋势加仓（F_ask < ref_ask）\n"
    "      建议：填你认为“公平或可接受”的中枢价格（例如开仓参考价/模型参考价）。\n"
    "  - name: risk\n"
    "    type: number\n"
    "    required: true\n"
    "    description: |\n"
    "      不确定性（建议 0~1）。用于决定 TP/CORE 拆分：tp_ratio=0.5+0.5*risk，core_ratio=1-tp_ratio。\n"
    "      - risk=0 -> TP 50%, CORE 50%\n"
    "      - risk=1 -> TP 100%, CORE 0%\n"
    "      越大表示越偏向“必须止盈止损”的主动管理。\n"
    "  - name: hedge_sell_bias\n"
    "    type: number\n"
    "    required: true\n"
    "    description: |\n"
    "      反买止损偏好（建议 0~1）。越大，OppSide 反买仓止损线越严格。\n"
    "      通过 HEDGE_LINE = hedge_sell_bias + (1-hedge_sell_bias)*A(e) 参与计算。\n"
    "      - 越接近结算（time_ratio 越小），A(e) 越大，止损更严格。\n"
    "  - name: trend_sell_bias\n"
    "    type: number\n"
    "    required: true\n"
    "    description: |\n"
    "      趋势止盈偏好（建议 0~1）。越大，前期越不容易止盈；后期会随时间自动降低门槛。\n"
    "      通过 TREND_TP_LINE = trend_sell_bias*(1-A(e)) 参与计算。\n"
    "  - name: core_sell_bias\n"
    "    type: number\n"
    "    required: true\n"
    "    description: |\n"
    "      CORE 止损偏好（建议 0~1），一个输入生成两条线：\n"
    "      - CORE_STRICT_LINE：用于“退回 CORE”轻动作（规则7/8）\n"
    "      - CORE_LOOSE_LINE：用于“FactSide 全清”重动作（规则9）\n"
    "      其中 LOOSE < STRICT，保证 CORE 的最终防线更宽松、更能拿住。\n"
    "  - name: start_day\n"
    "    type: number\n"
    "    required: true\n"
    "    description: |\n"
    "      起始天数（>0），用于计算 time_ratio=day_to_end/start_day。\n"
    "      策略内部使用 e=1-time_ratio 与 A(e)=3e^2-2e^3（中段加速曲线）：\n"
    "      - 前期变化慢\n"
    "      - 中段开始加速\n"
    "      - 后期动作更明显\n"
    "      该值同时影响止盈线、止损线、反买管理与 TP 分段建仓门槛。\n"
    "outputs:\n"
    "  - name: FunctionJson\n"
    "    type: string\n"
    "    description: |\n"
    "      统一动作结果 JSON：\n"
    "      - actions: 本 tick 的 SetPos 指令（通常包含 FactSide 与 OppSide 各一条）\n"
    "      - print: 关键中间变量与命中规则日志，便于排查\n"
    "      - wake_reason: 预留字段（当前一般为 null）\n"
    "  - name: IsCodeOk\n"
    "    type: boolean\n"
    "    description: 本次运行是否成功；失败时 FunctionJson.print 会给出错误原因\n"
    "```\n"
)

for o in Outputs:
    o["Kind"] = "String"
for i in Inputs:
    i["Kind"] = "String"

Inputs[0]["name"] = "UseData"
Inputs[0]["Isnecessary"] = True
Inputs[0]["IsLabel"] = False

Inputs[1]["name"] = "FactSide"
Inputs[1]["Kind"] = "String"
Inputs[1]["Isnecessary"] = True
Inputs[1]["IsLabel"] = False

Inputs[2]["name"] = "FactSide_ref_ask"
Inputs[2]["Kind"] = "Num"
Inputs[2]["Isnecessary"] = True
Inputs[2]["IsLabel"] = False

Inputs[3]["name"] = "risk"
Inputs[3]["Kind"] = "Num"
Inputs[3]["Isnecessary"] = True
Inputs[3]["IsLabel"] = False

Inputs[4]["name"] = "hedge_sell_bias"
Inputs[4]["Kind"] = "Num"
Inputs[4]["Isnecessary"] = True
Inputs[4]["IsLabel"] = False

Inputs[5]["name"] = "trend_sell_bias"
Inputs[5]["Kind"] = "Num"
Inputs[5]["Isnecessary"] = True
Inputs[5]["IsLabel"] = False

Inputs[6]["name"] = "core_sell_bias"
Inputs[6]["Kind"] = "Num"
Inputs[6]["Isnecessary"] = True
Inputs[6]["IsLabel"] = False

Inputs[7]["name"] = "start_day"
Inputs[7]["Kind"] = "Num"
Inputs[7]["Isnecessary"] = True
Inputs[7]["IsLabel"] = False

Outputs[0]["name"] = "FunctionJson"
Outputs[0]["Kind"] = "String"
Outputs[1]["name"] = "IsCodeOk"
Outputs[1]["Kind"] = "Boolean"


def _norm_key(key: str) -> str:
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


class _UseDataProxy:
    def __init__(self, raw: dict):
        self._raw = raw or {}
        self._norm_to_key = {}
        for k in self._raw.keys():
            nk = _norm_key(k)
            if nk and nk not in self._norm_to_key:
                self._norm_to_key[nk] = k

    def _resolve(self, key):
        if key in self._raw:
            return key
        nk = _norm_key(key)
        return self._norm_to_key.get(nk)

    def __getitem__(self, key):
        real = self._resolve(key)
        if real is None:
            raise KeyError(key)
        return self._raw[real]

    def get(self, key, default=None):
        real = self._resolve(key)
        if real is None:
            return default
        return self._raw.get(real, default)


def _parse_value(text: str):
    if text is None:
        return None
    s = str(text).strip()
    if s == "":
        return ""
    low = s.lower()
    if low in ("null", "none"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False

    num_s = s.replace(",", "").replace("_", "")
    if re.fullmatch(r"[+\-]?\d+", num_s):
        try:
            return int(num_s)
        except Exception:
            pass
    if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?", num_s):
        try:
            return float(num_s)
        except Exception:
            pass

    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        try:
            return ast.literal_eval(s)
        except Exception:
            return s[1:-1]
    return s


def _parse_kv_text(raw: str):
    out = {}
    for line_raw in raw.splitlines():
        line = line_raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.replace("：", ":").replace("＝", "=")
        if "=" in line:
            k, v = line.split("=", 1)
        elif ":" in line:
            k, v = line.split(":", 1)
        else:
            continue
        key = k.strip()
        if not key:
            continue
        out[key] = _parse_value(v.strip())
    return out


def _parse_usedata(raw):
    if isinstance(raw, dict):
        return raw, None
    if raw is None:
        return None, "UseData 为空"
    if not isinstance(raw, str):
        return None, f"UseData 类型不支持：{type(raw)}"

    s = raw.strip()
    if not s:
        return None, "UseData 为空字符串"

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj, None
    except Exception:
        pass

    kv = _parse_kv_text(s)
    if kv:
        return kv, None

    return None, "UseData 解析失败（需要 JSON 对象或 key=value 文本）"


def _to_float(v, default=0.0):
    try:
        if v is None:
            return float(default)
        if isinstance(v, str):
            s = v.strip().replace(",", "").replace("_", "")
            if not s:
                return float(default)
            if s.endswith("%"):
                return float(s[:-1]) / 100.0
            return float(s)
        return float(v)
    except Exception:
        return float(default)


def _to_int(v, default=0):
    try:
        if v is None:
            return int(default)
        if isinstance(v, str):
            s = v.strip().replace(",", "").replace("_", "")
            if not s:
                return int(default)
            return int(float(s))
        return int(v)
    except Exception:
        return int(default)


def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _safe_ratio(num, den):
    if den is None or den <= 0:
        return None
    return num / den


def _infer_live_ratio(side_qty, other_qty):
    sq = max(0.0, _to_float(side_qty, 0.0))
    oq = max(0.0, _to_float(other_qty, 0.0))
    total = sq + oq
    if total <= 0:
        return 0.0
    return sq / total


def _side_name(s):
    t = str(s or "").strip().lower()
    if t == "yes":
        return "Yes"
    if t == "no":
        return "No"
    return ""


def _extract_prev_target(usedata: _UseDataProxy, side: str):
    side = _side_name(side)
    if not side:
        return None
    names = []
    if side == "Yes":
        names = [
            "Yes_target_pos",
            "Yes_target",
            "Yes_setpos",
            "yes_target_pos",
            "yes_target",
            "yes_setpos",
        ]
    else:
        names = [
            "No_target_pos",
            "No_target",
            "No_setpos",
            "no_target_pos",
            "no_target",
            "no_setpos",
        ]
    for key in names:
        val = usedata.get(key, None)
        if val is not None and str(val).strip() != "":
            return _to_float(val, default=0.0)
    return None


def _run_strategy(usedata: _UseDataProxy, fact_side, ref_ask, risk, hedge_sell_bias, trend_sell_bias, core_sell_bias, start_day):
    actions = []
    logs = []
    wake_reason = None

    def Print(text):
        logs.append(str(text))

    def SetPos(side, pct):
        s = _side_name(side)
        if s not in ("Yes", "No"):
            raise ValueError(f"side 必须是 Yes/No，当前: {side}")
        p = _to_float(pct, default=0.0)
        if p > 1.0 and p <= 100.0:
            p = p / 100.0
        p = _clamp(p, 0.0, 1.0)
        actions.append({"type": "SETPOS", "side": s, "pct": float(p)})

    # 开头先打印全部入参与 UseData 原始字段，便于逐项核对
    Print("=== RAW_INPUTS_BEGIN ===")
    Print("raw_fact_side=" + str(fact_side))
    Print("raw_ref_ask=" + str(ref_ask))
    Print("raw_risk=" + str(risk))
    Print("raw_hedge_sell_bias=" + str(hedge_sell_bias))
    Print("raw_trend_sell_bias=" + str(trend_sell_bias))
    Print("raw_core_sell_bias=" + str(core_sell_bias))
    Print("raw_start_day=" + str(start_day))
    raw_map = getattr(usedata, "_raw", {}) or {}
    for k in sorted(raw_map.keys(), key=lambda x: str(x)):
        Print("raw_usedata[" + str(k) + "]=" + str(raw_map.get(k)))
    Print("=== RAW_INPUTS_END ===")

    yes_ask = _to_float(usedata.get("Yes_now_ask", 1.0), default=1.0)
    yes_bid = _to_float(usedata.get("Yes_now_bid", 0.0), default=0.0)
    no_ask = _to_float(usedata.get("No_now_ask", 1.0), default=1.0)
    no_bid = _to_float(usedata.get("No_now_bid", 0.0), default=0.0)

    yes_qty = _to_float(usedata.get("Yes_now_Qty", 0.0), default=0.0)
    no_qty = _to_float(usedata.get("No_now_Qty", 0.0), default=0.0)
    yes_avg = _to_float(usedata.get("Yes_now_avgPrice", 0.0), default=0.0)
    no_avg = _to_float(usedata.get("No_now_avgPrice", 0.0), default=0.0)

    yes_open = _to_float(usedata.get("Yes_OpenOrdersQty", 0.0), default=0.0)
    no_open = _to_float(usedata.get("No_OpenOrdersQty", 0.0), default=0.0)
    day_to_end = _to_float(usedata.get("day_to_end", usedata.get("days_to_end", 9999)), default=9999)

    yes_pos_now = _clamp(
        _to_float(
            usedata.get("Yes_Now_Pos", usedata.get("Yes_Pos", _infer_live_ratio(yes_qty, no_qty))),
            default=0.0,
        ),
        0.0,
        1.0,
    )
    no_pos_now = _clamp(
        _to_float(
            usedata.get("No_Now_Pos", usedata.get("No_Pos", _infer_live_ratio(no_qty, yes_qty))),
            default=0.0,
        ),
        0.0,
        1.0,
    )

    yes_cap = _clamp(
        _to_float(usedata.get("Yes_MaxPos", usedata.get("Yes_PosCap", 1.0)), default=1.0),
        0.0,
        1.0,
    )
    no_cap = _clamp(
        _to_float(usedata.get("No_MaxPos", usedata.get("No_PosCap", 1.0)), default=1.0),
        0.0,
        1.0,
    )

    side = _side_name(fact_side)
    if side not in ("Yes", "No"):
        raise ValueError(f"FactSide 仅支持 Yes/No，当前: {fact_side}")

    ref_ask = _clamp(_to_float(ref_ask, default=0.5), 0.000001, 0.999999)
    risk = _clamp(_to_float(risk, default=0.5), 0.0, 1.0)
    hedge_sell_bias = _clamp(_to_float(hedge_sell_bias, default=0.5), 0.0, 1.0)
    trend_sell_bias = _clamp(_to_float(trend_sell_bias, default=0.5), 0.0, 1.0)
    core_sell_bias = _clamp(_to_float(core_sell_bias, default=0.5), 0.0, 1.0)
    start_day = _to_float(start_day, default=0.0)
    if start_day > 0:
        time_ratio = _clamp(day_to_end / start_day, 0.0, 1.0)
    else:
        time_ratio = 0.0

    if side == "Yes":
        fact_side_name, opp_side_name = "Yes", "No"
        f_ask, f_bid, f_qty, f_avg, f_cap, f_pos_now = yes_ask, yes_bid, yes_qty, yes_avg, yes_cap, yes_pos_now
        o_ask, o_bid, o_qty, o_avg, o_cap, o_pos_now = no_ask, no_bid, no_qty, no_avg, no_cap, no_pos_now
        f_open, o_open = yes_open, no_open
    else:
        fact_side_name, opp_side_name = "No", "Yes"
        f_ask, f_bid, f_qty, f_avg, f_cap, f_pos_now = no_ask, no_bid, no_qty, no_avg, no_cap, no_pos_now
        o_ask, o_bid, o_qty, o_avg, o_cap, o_pos_now = yes_ask, yes_bid, yes_qty, yes_avg, yes_cap, yes_pos_now
        f_open, o_open = no_open, yes_open

    tp_ratio = _clamp(0.5 + 0.5 * risk, 0.5, 1.0)
    core_ratio = _clamp(1.0 - tp_ratio, 0.0, 0.5)

    e = _clamp(1.0 - time_ratio, 0.0, 1.0)
    a = 3.0 * (e ** 2) - 2.0 * (e ** 3)
    trend_tp_line = trend_sell_bias * (1.0 - a)
    hedge_line = hedge_sell_bias + (1.0 - hedge_sell_bias) * a
    core_strict_line = core_sell_bias + (1.0 - core_sell_bias) * a
    lam = 0.35
    core_loose_line = core_strict_line - lam * (1.0 - core_sell_bias) * a

    rr_f = _safe_ratio(f_bid, f_avg)
    rr_o = _safe_ratio(o_bid, o_avg)
    profit_f = (rr_f - 1.0) if rr_f is not None else None

    pos0 = (max(0.0, f_qty) <= 0.0 and max(0.0, o_qty) <= 0.0 and max(0.0, f_open + o_open) <= 0.0)

    f_target = f_pos_now
    o_target = o_pos_now

    reduce_rule = ""
    strategy_tag = "hold"

    Print("FactSide=" + fact_side_name)
    Print("OppSide=" + opp_side_name)
    Print("F_ask=" + str(f_ask) + " F_bid=" + str(f_bid))
    Print("O_ask=" + str(o_ask) + " O_bid=" + str(o_bid))
    Print("F_qty=" + str(f_qty) + " O_qty=" + str(o_qty))
    Print("F_pos_now=" + str(f_pos_now) + " O_pos_now=" + str(o_pos_now))
    Print("F_avg=" + str(f_avg) + " O_avg=" + str(o_avg))
    Print("F_cap=" + str(f_cap) + " O_cap=" + str(o_cap))
    Print("ref_ask=" + str(ref_ask))
    Print("risk=" + str(risk) + " tp_ratio=" + str(tp_ratio) + " core_ratio=" + str(core_ratio))
    Print("start_day=" + str(start_day) + " day_to_end=" + str(day_to_end))
    Print("time_ratio(day_to_end/start_day)=" + str(time_ratio))
    Print("A(e)=" + str(a))
    Print("trend_tp_line=" + str(trend_tp_line))
    Print("hedge_line=" + str(hedge_line))
    Print("core_strict_line=" + str(core_strict_line))
    Print("core_loose_line=" + str(core_loose_line))
    Print("RR_F=" + str(rr_f) + " RR_O=" + str(rr_o) + " profit_F=" + str(profit_f))
    Print("Pos0=" + str(pos0))
    Print(
        "time_ratio_calc: day_to_end="
        + str(day_to_end)
        + " / start_day="
        + str(start_day)
        + " => "
        + str(time_ratio)
    )

    # 规则 1：先手反买（仅 Pos0）
    r1_price = f_ask > ref_ask + 0.05
    r1_ref = ref_ask < 0.9
    r1_day = day_to_end > 0.5
    r1_time = time_ratio > 0.25
    Print(
        "rule1_check: pos0="
        + str(pos0)
        + " price("
        + str(f_ask)
        + ">"
        + str(ref_ask + 0.05)
        + ")="
        + str(r1_price)
        + " ref("
        + str(ref_ask)
        + "<0.9)="
        + str(r1_ref)
        + " day("
        + str(day_to_end)
        + ">0.5)="
        + str(r1_day)
        + " time("
        + str(time_ratio)
        + ">0.25)="
        + str(r1_time)
    )
    rule1 = (
        pos0
        and r1_price
        and r1_ref
        and r1_day
        and r1_time
    )
    if rule1:
        o_target = 0.25 * tp_ratio
        f_target = 0.0
        strategy_tag = "rule1_open_hedge"
    else:
        # 规则 3：结算建仓（无反买且 Pos0）
        if pos0:
            f_target = core_ratio
            o_target = 0.0
            strategy_tag = "rule3_open_core"

    # 规则 2：反买仓管理（有 OppSide 持仓）
    if o_qty > 0:
        hedge_tp = 0.02 * (1.0 - a)
        Print(
            "rule2_check: o_qty="
            + str(o_qty)
            + " rr_o="
            + str(rr_o)
            + " hedge_line="
            + str(hedge_line)
            + " hedge_tp_line="
            + str(1.0 + hedge_tp)
        )
        if rr_o is not None and rr_o < hedge_line:
            o_target = 0.0
            strategy_tag = "rule2_hedge_stoploss"
        elif rr_o is not None and rr_o >= (1.0 + hedge_tp):
            o_target = 0.0
            strategy_tag = "rule2_hedge_takeprofit"

    # 规则 9 / 7 / 8：FactSide 回撤管理
    if f_qty > 0 and rr_f is not None:
        Print(
            "rule9_7_8_check: f_qty="
            + str(f_qty)
            + " rr_f="
            + str(rr_f)
            + " core_loose_line="
            + str(core_loose_line)
            + " core_strict_line="
            + str(core_strict_line)
            + " trend_tp_line="
            + str(trend_tp_line)
        )
        if rr_f < core_loose_line:
            f_target = 0.0
            reduce_rule = "rule9_clear_fact"
            strategy_tag = reduce_rule
        elif (profit_f is not None and profit_f > trend_tp_line) or (rr_f < core_strict_line):
            f_target = core_ratio
            reduce_rule = "rule7or8_back_to_core"
            strategy_tag = reduce_rule

    # 规则 6：趋势建仓（仅当无减仓信号）
    if (
        f_qty > 0
        and reduce_rule == ""
        and day_to_end > 0
        and f_ask < ref_ask
        and ref_ask > 0
    ):
        Print(
            "rule6_gate: f_qty>0="
            + str(f_qty > 0)
            + " reduce_rule_empty="
            + str(reduce_rule == "")
            + " day_to_end>0="
            + str(day_to_end > 0)
            + " f_ask<ref_ask="
            + str(f_ask < ref_ask)
            + " ref_ask>0="
            + str(ref_ask > 0)
        )
        gap = (ref_ask - f_ask) / ref_ask
        gap = _clamp(gap, 0.0, 3.0)

        t1 = _clamp(0.85 + 0.10 * gap, 0.70, 0.99)
        t2 = _clamp(0.60 + 0.10 * gap, 0.45, 0.95)
        t3 = _clamp(0.35 + 0.10 * gap, 0.20, 0.90)

        tp_target = 0.0
        if time_ratio >= t3:
            tp_target = tp_ratio
        elif time_ratio >= t2:
            tp_target = tp_ratio * (2.0 / 3.0)
        elif time_ratio >= t1:
            tp_target = tp_ratio * (1.0 / 3.0)

        # 有历史目标时启用“只上调不下调”
        prev_fact_target = _extract_prev_target(usedata, fact_side_name)
        desired = core_ratio + tp_target
        if prev_fact_target is not None:
            desired = max(desired, prev_fact_target)
        f_target = max(f_target, desired)
        strategy_tag = "rule6_trend_add_tp"

        Print("gap=" + str(gap))
        Print("T1=" + str(t1) + " T2=" + str(t2) + " T3=" + str(t3))
        Print("tp_target=" + str(tp_target))
        Print("prev_fact_target=" + str(prev_fact_target))

    f_target = _clamp(f_target, 0.0, f_cap)
    o_target = _clamp(o_target, 0.0, o_cap)

    Print("strategy_tag=" + strategy_tag)
    Print("FactSide_target=" + str(f_target))
    Print("OppSide_target=" + str(o_target))

    SetPos(fact_side_name, f_target)
    SetPos(opp_side_name, o_target)

    return {"actions": actions, "print": logs, "wake_reason": wake_reason}


def run_node(node):
    try:
        node_inputs = node.get("Inputs") or []
        usedata_raw = node_inputs[0].get("Context") if len(node_inputs) > 0 else None
        fact_side = node_inputs[1].get("Context") if len(node_inputs) > 1 else "Yes"

        ref_ask = node_inputs[2].get("Context") if len(node_inputs) > 2 else None
        if (ref_ask in (None, "")) and len(node_inputs) > 2 and node_inputs[2].get("Num") is not None:
            ref_ask = node_inputs[2].get("Num")

        risk = node_inputs[3].get("Context") if len(node_inputs) > 3 else None
        if (risk in (None, "")) and len(node_inputs) > 3 and node_inputs[3].get("Num") is not None:
            risk = node_inputs[3].get("Num")

        hedge_sell_bias = node_inputs[4].get("Context") if len(node_inputs) > 4 else None
        if (hedge_sell_bias in (None, "")) and len(node_inputs) > 4 and node_inputs[4].get("Num") is not None:
            hedge_sell_bias = node_inputs[4].get("Num")

        trend_sell_bias = node_inputs[5].get("Context") if len(node_inputs) > 5 else None
        if (trend_sell_bias in (None, "")) and len(node_inputs) > 5 and node_inputs[5].get("Num") is not None:
            trend_sell_bias = node_inputs[5].get("Num")

        core_sell_bias = node_inputs[6].get("Context") if len(node_inputs) > 6 else None
        if (core_sell_bias in (None, "")) and len(node_inputs) > 6 and node_inputs[6].get("Num") is not None:
            core_sell_bias = node_inputs[6].get("Num")

        start_day = node_inputs[7].get("Context") if len(node_inputs) > 7 else None
        if (start_day in (None, "")) and len(node_inputs) > 7 and node_inputs[7].get("Num") is not None:
            start_day = node_inputs[7].get("Num")

        usedata_dict, usedata_err = _parse_usedata(usedata_raw)
        if usedata_err:
            out_json = {"actions": [], "print": [f"[UseDataError] {usedata_err}"], "wake_reason": None}
            Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
            Outputs[1]["Boolean"] = False
            return Outputs

        out_json = _run_strategy(
            _UseDataProxy(usedata_dict),
            fact_side,
            ref_ask,
            risk,
            hedge_sell_bias,
            trend_sell_bias,
            core_sell_bias,
            start_day,
        )
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = True
        return Outputs
    except Exception as e:
        out_json = {"actions": [], "print": [f"[RuntimeError] {type(e).__name__}: {e}"], "wake_reason": None}
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = False
        return Outputs

import ast
import json
import re

# ===== 节点定义 =====
OutPutNum = 2
InPutNum = 8

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
    "组件功能：Stragy_Fllow_Truth（严格按 TP+CORE 目标拆分理念输出方向总目标仓位）。\n\n"
    "```yaml\n"
    "inputs:\n"
    "  - name: UseData\n"
    "    type: string\n"
    "    required: true\n"
    "    description: JSON对象(dict)或多行 key=value/key: value 文本\n"
    "  - name: FactSide\n"
    "    type: string\n"
    "    required: true\n"
    "    description: 事实方向，Yes 或 No\n"
    "  - name: FactSide_ref_ask\n"
    "    type: number\n"
    "    required: true\n"
    "    description: 参考 ask（FS 基准价）\n"
    "  - name: risk\n"
    "    type: number\n"
    "    required: true\n"
    "    description: 不确定性，取值 (0,1)\n"
    "  - name: hedge_sell_bias\n"
    "    type: number\n"
    "    required: true\n"
    "    description: 反买止损偏好，取值 (0,1)\n"
    "  - name: trend_sell_bias\n"
    "    type: number\n"
    "    required: true\n"
    "    description: 趋势止盈偏好，取值 (0,1)\n"
    "  - name: core_sell_bias\n"
    "    type: number\n"
    "    required: true\n"
    "    description: 总体止损偏好，取值 (0,1)\n"
    "  - name: start_day\n"
    "    type: number\n"
    "    required: true\n"
    "    description: 起始天数（>0），策略内部按 time_ratio=day_to_end/start_day 计算时间比率\n"
    "outputs:\n"
    "  - name: FunctionJson\n"
    "    type: string\n"
    "    description: 统一动作 JSON（actions/print/wake_reason）\n"
    "  - name: IsCodeOk\n"
    "    type: boolean\n"
    "    description: 本次运行是否成功\n"
    "notes:\n"
    "  - SetPos(side,pct) 只设置方向总目标仓位\n"
    "  - 当前仓位优先读取 Yes_Now_Pos/No_Now_Pos（兼容 Yes_Pos/No_Pos）\n"
    "  - 上限可用 Yes_MaxPos/No_MaxPos（或 Yes_PosCap/No_PosCap）\n"
    "  - 最终总目标: FactSide_target=CORE_target+TP_target, OppSide_target=HEDGE_target\n"
    "```\n"
)

for o in Outputs:
    o["Kind"] = "String"
for i in Inputs:
    i["Kind"] = "String"

Inputs[0]["name"] = "UseData"
Inputs[0]["Isnecessary"] = True
Inputs[0]["IsLabel"] = False

Inputs[1]["name"] = "FactSide"
Inputs[1]["Kind"] = "String"
Inputs[1]["Isnecessary"] = True
Inputs[1]["IsLabel"] = False

Inputs[2]["name"] = "FactSide_ref_ask"
Inputs[2]["Kind"] = "Num"
Inputs[2]["Isnecessary"] = True
Inputs[2]["IsLabel"] = False

Inputs[3]["name"] = "risk"
Inputs[3]["Kind"] = "Num"
Inputs[3]["Isnecessary"] = True
Inputs[3]["IsLabel"] = False

Inputs[4]["name"] = "hedge_sell_bias"
Inputs[4]["Kind"] = "Num"
Inputs[4]["Isnecessary"] = True
Inputs[4]["IsLabel"] = False

Inputs[5]["name"] = "trend_sell_bias"
Inputs[5]["Kind"] = "Num"
Inputs[5]["Isnecessary"] = True
Inputs[5]["IsLabel"] = False

Inputs[6]["name"] = "core_sell_bias"
Inputs[6]["Kind"] = "Num"
Inputs[6]["Isnecessary"] = True
Inputs[6]["IsLabel"] = False

Inputs[7]["name"] = "start_day"
Inputs[7]["Kind"] = "Num"
Inputs[7]["Isnecessary"] = True
Inputs[7]["IsLabel"] = False

Outputs[0]["name"] = "FunctionJson"
Outputs[0]["Kind"] = "String"
Outputs[1]["name"] = "IsCodeOk"
Outputs[1]["Kind"] = "Boolean"


def _norm_key(key: str) -> str:
    if key is None:
        return ""
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


class _UseDataProxy:
    def __init__(self, raw: dict):
        self._raw = raw or {}
        self._norm_map = {}
        for k in self._raw.keys():
            nk = _norm_key(k)
            if nk and nk not in self._norm_map:
                self._norm_map[nk] = k

    def _resolve_key(self, key):
        if key in self._raw:
            return key
        nk = _norm_key(key)
        if nk in self._norm_map:
            return self._norm_map[nk]
        return None

    def get(self, key, default=None):
        real_key = self._resolve_key(key)
        if real_key is None:
            return default
        return self._raw.get(real_key, default)

    def has(self, key):
        return self._resolve_key(key) is not None


def _parse_value(text: str):
    if text is None:
        return None
    s = str(text).strip()
    if s == "":
        return ""

    low = s.lower()
    if low in ("none", "null"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False

    num_s = s.replace("_", "").replace(",", "")
    if re.fullmatch(r"[+\-]?\d+", num_s):
        try:
            return int(num_s)
        except Exception:
            pass
    if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?", num_s):
        try:
            return float(num_s)
        except Exception:
            pass

    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        try:
            return ast.literal_eval(s)
        except Exception:
            return s[1:-1]
    return s


def _parse_kv_text(text: str):
    out = {}
    if not isinstance(text, str):
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.replace("：", ":").replace("＝", "=")
        if "=" in line:
            k, v = line.split("=", 1)
        elif ":" in line:
            k, v = line.split(":", 1)
        else:
            continue
        key = k.strip()
        if not key:
            continue
        out[key] = _parse_value(v.strip())
    return out


def _parse_usedata(raw):
    if isinstance(raw, dict):
        return raw, None
    if raw is None:
        return None, "UseData 为空"
    if not isinstance(raw, str):
        return None, f"UseData 类型不支持：{type(raw)}"

    s = raw.strip()
    if not s:
        return None, "UseData 为空字符串"

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj, None
    except Exception:
        pass

    kv = _parse_kv_text(s)
    if kv:
        return kv, None
    return None, "UseData 解析失败（需要 JSON 对象或 key=value 文本）"


def _to_float(v, default=0.0):
    try:
        if v is None:
            return float(default)
        if isinstance(v, str):
            s = v.strip().replace(",", "").replace("_", "")
            if s == "":
                return float(default)
            if s.endswith("%"):
                return float(s[:-1]) / 100.0
            return float(s)
        return float(v)
    except Exception:
        return float(default)


def _clamp(v, lo, hi):
    return max(float(lo), min(float(hi), float(v)))


def _norm_side(value):
    s = str(value or "").strip().capitalize()
    if s not in ("Yes", "No"):
        return "Yes"
    return s


def _read_input_value(node_inputs, index):
    if len(node_inputs) <= index:
        return None
    ipt = node_inputs[index] or {}
    val = ipt.get("Context")
    if val in (None, "") and ipt.get("Num") is not None:
        val = ipt.get("Num")
    return val


def _get_side_float(usedata: _UseDataProxy, side: str, suffix: str, default=0.0):
    keys = [f"{side}_{suffix}", f"{side.lower()}_{suffix}", f"{side.upper()}_{suffix}"]
    for key in keys:
        if usedata.has(key):
            return _to_float(usedata.get(key), default)
    return float(default)


def _run_strategy(usedata: _UseDataProxy, params: dict):
    actions = []
    logs = []
    wake_reason = None
    eps = 1e-8
    loose_lambda = 0.35

    def Print(msg):
        logs.append(str(msg))

    def SetPos(side, pct):
        s = _norm_side(side)
        p = _clamp(_to_float(pct, 0.0), 0.0, 1.0)
        actions.append({"type": "SETPOS", "side": s, "pct": float(p)})

    # 开头先打印全部入参与 UseData 原始字段，便于逐项核对
    Print("=== RAW_INPUTS_BEGIN ===")
    raw_params = params or {}
    for k in sorted(raw_params.keys(), key=lambda x: str(x)):
        Print("raw_param[" + str(k) + "]=" + str(raw_params.get(k)))
    raw_map = getattr(usedata, "_raw", {}) or {}
    for k in sorted(raw_map.keys(), key=lambda x: str(x)):
        Print("raw_usedata[" + str(k) + "]=" + str(raw_map.get(k)))
    Print("=== RAW_INPUTS_END ===")

    # ===== 1) 输入参数 =====
    fact_side = _norm_side(params.get("FactSide", usedata.get("FactSide", "Yes")))
    opp_side = "No" if fact_side == "Yes" else "Yes"

    ref_ask = _to_float(
        params.get("FactSide_ref_ask", usedata.get("FactSide_ref_ask", usedata.get("FS_ref_ask", None))),
        default=0.5,
    )
    ref_ask = _clamp(ref_ask, 0.0001, 0.9999)

    risk = _clamp(_to_float(params.get("risk", usedata.get("risk", 0.5)), 0.5), 0.0, 1.0)
    hedge_sell_bias = _clamp(
        _to_float(params.get("hedge_sell_bias", usedata.get("hedge_sell_bias", 0.85)), 0.85),
        0.0,
        1.0,
    )
    trend_sell_bias = _clamp(
        _to_float(params.get("trend_sell_bias", usedata.get("trend_sell_bias", 0.7)), 0.7),
        0.0,
        1.0,
    )
    core_sell_bias = _clamp(
        _to_float(params.get("core_sell_bias", usedata.get("core_sell_bias", 0.8)), 0.8),
        0.0,
        1.0,
    )
    day_to_end = _to_float(usedata.get("day_to_end", usedata.get("days_to_end", 9999)), 9999)
    start_day = _to_float(params.get("start_day"), 0.0)
    if start_day > eps:
        time_ratio = _clamp(day_to_end / start_day, 0.0, 1.0)
    else:
        time_ratio = 0.0

    # ===== 2) 实时数据 =====
    F_ask = _get_side_float(usedata, fact_side, "now_ask", 1.0)
    F_bid = _get_side_float(usedata, fact_side, "now_bid", 0.0)
    O_ask = _get_side_float(usedata, opp_side, "now_ask", 1.0)
    O_bid = _get_side_float(usedata, opp_side, "now_bid", 0.0)

    F_qty = _get_side_float(usedata, fact_side, "now_Qty", 0.0)
    O_qty = _get_side_float(usedata, opp_side, "now_Qty", 0.0)
    F_avg = _get_side_float(usedata, fact_side, "now_avgPrice", 0.0)
    O_avg = _get_side_float(usedata, opp_side, "now_avgPrice", 0.0)
    F_open = _get_side_float(usedata, fact_side, "OpenOrdersQty", 0.0)
    O_open = _get_side_float(usedata, opp_side, "OpenOrdersQty", 0.0)

    # ===== 3) 当前仓位 + 上限 =====
    F_pos = _clamp(
        _to_float(
            usedata.get(
                f"Now_{fact_side}_Pos",
                usedata.get(f"{fact_side}_Pos", _clamp(F_qty, 0.0, 1.0)),
            ),
            0.0,
        ),
        0.0,
        1.0,
    )
    O_pos = _clamp(
        _to_float(
            usedata.get(
                f"Now_{opp_side}_Pos",
                usedata.get(f"{opp_side}_Pos", _clamp(O_qty, 0.0, 1.0)),
            ),
            0.0,
        ),
        0.0,
        1.0,
    )
    F_cap = _clamp(
        _to_float(
            usedata.get(f"{fact_side}_MaxPos", usedata.get(f"{fact_side}_PosCap", 1.0)),
            1.0,
        ),
        0.0,
        1.0,
    )
    O_cap = _clamp(
        _to_float(
            usedata.get(f"{opp_side}_MaxPos", usedata.get(f"{opp_side}_PosCap", 1.0)),
            1.0,
        ),
        0.0,
        1.0,
    )

    # ===== 4) 目标桶比例 =====
    tp_ratio = _clamp(0.5 + 0.5 * risk, 0.5, 1.0)
    core_ratio = _clamp(1.0 - tp_ratio, 0.0, 0.5)

    # ===== 5) 时间曲线 A(e) =====
    e = _clamp(1.0 - time_ratio, 0.0, 1.0)
    A = 3.0 * e * e - 2.0 * e * e * e

    trend_tp_line = _clamp(trend_sell_bias * (1.0 - A), 0.0, 1.0)
    hedge_line = _clamp(hedge_sell_bias + (1.0 - hedge_sell_bias) * A, 0.0, 1.0)
    core_strict_line = _clamp(core_sell_bias + (1.0 - core_sell_bias) * A, 0.0, 1.0)
    core_loose_line = _clamp(
        core_strict_line - loose_lambda * (1.0 - core_sell_bias) * A,
        0.0,
        1.0,
    )

    # ===== 6) 残值与盈利 =====
    RR_F = (F_bid / F_avg) if F_avg > eps else None
    RR_O = (O_bid / O_avg) if O_avg > eps else None
    profit_F = (F_bid / F_avg - 1.0) if F_avg > eps else None

    # ===== 7) Pos0 =====
    Pos0 = (F_qty <= eps) and (O_qty <= eps) and (F_open <= eps) and (O_open <= eps)

    # ===== 8) 初始化目标 =====
    # 默认“维持现状”，再由规则覆盖。
    fact_target = _clamp(F_pos, 0.0, F_cap)
    opp_target = _clamp(O_pos, 0.0, O_cap)
    reduced_this_tick = False

    # ===== 规则1：先手反买（仅 Pos0） =====
    rule1_price = F_ask > ref_ask + 0.05
    rule1_ref = ref_ask < 0.9
    rule1_day = day_to_end > 0.5
    rule1_time = time_ratio > 0.25
    Print(
        "rule1_check: "
        f"Pos0={Pos0}, "
        f"F_ask>ref_ask+0.05={rule1_price} ({F_ask}>{ref_ask + 0.05}), "
        f"ref_ask<0.9={rule1_ref}, "
        f"day_to_end>0.5={rule1_day}, "
        f"time_ratio>0.25={rule1_time}"
    )
    rule1 = (
        Pos0
        and rule1_price
        and rule1_ref
        and rule1_day
        and rule1_time
    )
    if rule1:
        hedge_target = 0.25 * tp_ratio
        fact_target = 0.0
        opp_target = _clamp(hedge_target, 0.0, O_cap)
        reduced_this_tick = True
        Print("rule1: hedge entry")
    else:
        # ===== 规则3：结算建仓（无反买且 Pos0） =====
        if Pos0:
            fact_target = _clamp(core_ratio, 0.0, F_cap)
            opp_target = 0.0
            Print("rule3: core entry")

    # ===== 规则2：反买仓管理（OppSide） =====
    if O_qty > eps:
        hedge_tp = 0.02 * (1.0 - A)
        Print(
            "rule2_check: "
            f"O_qty={O_qty}, RR_O={RR_O}, "
            f"stop_line(hedge_line)={hedge_line}, "
            f"takeprofit_line={1.0 + hedge_tp}"
        )
        if RR_O is not None and RR_O < hedge_line:
            opp_target = 0.0
            reduced_this_tick = True
            Print("rule2: hedge stop-loss")
        else:
            if RR_O is not None and RR_O >= (1.0 + hedge_tp):
                opp_target = 0.0
                reduced_this_tick = True
                Print("rule2: hedge take-profit")

    # ===== 规则9 / 7 / 8：FactSide 减仓规则 =====
    if F_qty > eps and F_avg > eps:
        Print(
            "rule9_7_8_check: "
            f"F_qty={F_qty}, RR_F={RR_F}, profit_F={profit_F}, "
            f"core_loose_line={core_loose_line}, core_strict_line={core_strict_line}, trend_tp_line={trend_tp_line}"
        )
        if RR_F is not None and RR_F < core_loose_line:
            fact_target = 0.0
            reduced_this_tick = True
            Print("rule9: core stop-loss all clear")
        else:
            if (profit_F is not None and profit_F > trend_tp_line) or (RR_F is not None and RR_F < core_strict_line):
                fact_target = _clamp(core_ratio, 0.0, F_cap)
                reduced_this_tick = True
                Print("rule7/8: fallback to core target")

    # ===== 规则6：趋势建仓（无减仓信号时） =====
    if (
        (F_qty > eps)
        and (F_ask < ref_ask)
        and (day_to_end > 0.0)
        and (not reduced_this_tick)
        and (ref_ask > eps)
    ):
        Print(
            "rule6_gate: "
            f"F_qty>eps={F_qty > eps}, F_ask<ref_ask={F_ask < ref_ask}, "
            f"day_to_end>0={day_to_end > 0.0}, reduced_this_tick={reduced_this_tick}, ref_ask>eps={ref_ask > eps}"
        )
        gap = _clamp((ref_ask - F_ask) / ref_ask, 0.0, 1.0)
        T1 = _clamp(0.85 + 0.10 * gap, 0.0, 1.0)
        T2 = _clamp(0.60 + 0.10 * gap, 0.0, 1.0)
        T3 = _clamp(0.35 + 0.10 * gap, 0.0, 1.0)

        tp_target = 0.0
        if time_ratio >= T1:
            tp_target = tp_ratio * (1.0 / 3.0)
        if time_ratio >= T2:
            tp_target = tp_ratio * (2.0 / 3.0)
        if time_ratio >= T3:
            tp_target = tp_ratio

        staged_target = _clamp(core_ratio + tp_target, 0.0, F_cap)
        # 上调不下调：仅在非减仓路径中生效
        fact_target = max(fact_target, staged_target)
        Print(f"rule6: tp scale-in gap={gap} staged_target={staged_target}")

    # ===== 9) 夹逼 + 输出 =====
    fact_target = _clamp(fact_target, 0.0, F_cap)
    opp_target = _clamp(opp_target, 0.0, O_cap)

    Print(f"fact_side={fact_side} opp_side={opp_side}")
    Print(f"F_ask={F_ask} F_bid={F_bid} F_qty={F_qty} F_pos={F_pos} F_avg={F_avg} F_open={F_open}")
    Print(f"O_ask={O_ask} O_bid={O_bid} O_qty={O_qty} O_pos={O_pos} O_avg={O_avg} O_open={O_open}")
    Print(f"ref_ask={ref_ask} risk={risk} start_day={start_day} day_to_end={day_to_end}")
    Print(f"time_ratio(day_to_end/start_day)={time_ratio}")
    Print(f"time_ratio_calc: day_to_end={day_to_end} / start_day={start_day} => {time_ratio}")
    Print(f"F_cap={F_cap} O_cap={O_cap} Pos0={Pos0}")
    Print(f"tp_ratio={tp_ratio} core_ratio={core_ratio}")
    Print(
        f"A={A} trend_tp_line={trend_tp_line} hedge_line={hedge_line} "
        f"core_strict_line={core_strict_line} core_loose_line={core_loose_line}"
    )
    Print(f"RR_F={RR_F} RR_O={RR_O} profit_F={profit_F}")
    Print(f"target_fact={fact_target} target_opp={opp_target}")

    SetPos(fact_side, fact_target)
    SetPos(opp_side, opp_target)
    return {"actions": actions, "print": logs, "wake_reason": wake_reason}


def run_node(node):
    try:
        node_inputs = node.get("Inputs") or []

        usedata_raw = _read_input_value(node_inputs, 0)
        usedata_dict, err = _parse_usedata(usedata_raw)
        if err:
            out_json = {"actions": [], "print": [f"[UseDataError] {err}"], "wake_reason": None}
            Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
            Outputs[1]["Boolean"] = False
            return Outputs

        params = {
            "FactSide": _read_input_value(node_inputs, 1),
            "FactSide_ref_ask": _read_input_value(node_inputs, 2),
            "risk": _read_input_value(node_inputs, 3),
            "hedge_sell_bias": _read_input_value(node_inputs, 4),
            "trend_sell_bias": _read_input_value(node_inputs, 5),
            "core_sell_bias": _read_input_value(node_inputs, 6),
            "start_day": _read_input_value(node_inputs, 7),
        }

        out_json = _run_strategy(_UseDataProxy(usedata_dict), params)
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = True
        return Outputs
    except Exception as e:
        out_json = {"actions": [], "print": [f"[RuntimeError] {type(e).__name__}: {e}"], "wake_reason": None}
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = False
        return Outputs

