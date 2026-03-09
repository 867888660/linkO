import ast
import difflib
import json
import re

# ===== 节点定义 =====
OutPutNum = 2
InPutNum = 3

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
    "组件功能：Fllow_Stock_Value（股票市值排名跟随策略）。\n\n"
    "参数：\n"
    "```yaml\n"
    "inputs:\n"
    "  - name: UseData\n"
    "    type: string\n"
    "    required: true\n"
    "    description: JSON对象（dict）或多行 key=value/key: value；键名容错（忽略大小写、下划线、连字符等差异）\n"
    "  - name: AnchorCompany\n"
    "    type: string\n"
    "    required: true\n"
    "    description: 锚定公司代码（如 GOOGL / NVDA）\n"
    "  - name: RankPosition\n"
    "    type: number\n"
    "    required: true\n"
    "    description: 目标排名（1 表示第一名，2 表示第二名）\n"
    "outputs:\n"
    "  - name: FunctionJson\n"
    "    type: string\n"
    "    description: 统一动作结果（actions/print/wake_reason）\n"
    "  - name: IsCodeOk\n"
    "    type: boolean\n"
    "    description: 本次运行是否成功\n"
    "```\n"
)

for o in Outputs:
    o["Kind"] = "String"
for i in Inputs:
    i["Kind"] = "String"

Inputs[0]["name"] = "UseData"
Inputs[0]["Isnecessary"] = True
Inputs[0]["IsLabel"] = False

Inputs[1]["name"] = "AnchorCompany"
Inputs[1]["Kind"] = "String"
Inputs[1]["Isnecessary"] = True
Inputs[1]["IsLabel"] = False

Inputs[2]["name"] = "RankPosition"
Inputs[2]["Kind"] = "Num"
Inputs[2]["Isnecessary"] = True
Inputs[2]["IsLabel"] = False

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

    def to_dict(self):
        return dict(self._raw)


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


def _norm_company_name(name):
    return "".join(ch for ch in str(name or "").upper() if ch.isalnum())


def _stable_json_dumps(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        return json.dumps({"error": "json_serialize_failed"}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _pick_ts(usedata: _UseDataProxy):
    keys = ("NowTime", "query_time", "query_time_beijing", "ts_utc", "timestamp")
    for k in keys:
        v = usedata.get(k, None)
        s = str(v).strip() if v is not None else ""
        if s:
            return s
    return None


def _emit_db_json(Print, ts, inputs, actions, calc=None):
    payload = {
        "ts": ts,
        "inputs": inputs if isinstance(inputs, dict) else {},
        "actions": actions if isinstance(actions, list) else [],
        "calc": calc if isinstance(calc, dict) else {},
    }
    Print("===DB_JSON_BEGIN===")
    Print(_stable_json_dumps(payload))
    Print("===DB_JSON_END===")


_COMPANY_ALIAS_MAP = {
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "GOOG": "GOOGL",
    "FACEBOOK": "META",
    "FB": "META",
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "AMAZON": "AMZN",
    "NVIDIA": "NVDA",
}


def _resolve_anchor_company(anchor_company, mcap_map: dict):
    available = sorted(list((mcap_map or {}).keys()))
    if not available:
        return None, "no_companies"

    raw = str(anchor_company or "").strip()
    norm = _norm_company_name(raw)

    if norm in mcap_map:
        return norm, "exact"

    if norm.startswith("MCAPUSD"):
        trimmed = _norm_company_name(norm[len("MCAPUSD"):])
        if trimmed in mcap_map:
            return trimmed, "from_full_key"
        norm = trimmed or norm

    if norm in _COMPANY_ALIAS_MAP:
        aliased = _COMPANY_ALIAS_MAP[norm]
        if aliased in mcap_map:
            return aliased, f"alias:{norm}->{aliased}"

    if norm:
        contains = [c for c in available if (norm in c) or (c in norm)]
        if len(contains) == 1:
            return contains[0], "substring_unique"

    if norm:
        close = difflib.get_close_matches(norm, available, n=2, cutoff=0.72)
        if len(close) == 1:
            return close[0], "fuzzy"

    if "GOOGL" in mcap_map:
        return "GOOGL", "fallback:GOOGL"
    return available[0], "fallback:first"


def _extract_mcap_usd_map(usedata: _UseDataProxy):
    out = {}
    for k, v in (usedata.to_dict() or {}).items():
        nk = _norm_key(k)
        if not nk.startswith("mcapusd"):
            continue
        company = _norm_company_name(nk[len("mcapusd"):])
        if not company:
            continue
        out[company] = _to_float(v, default=0.0)
    return out


def _run_strategy(usedata: _UseDataProxy, anchor_company: str, rank_position: int):
    actions = []
    logs = []
    wake_reason = None

    def Print(text):
        logs.append(str(text))

    # =========================
    # 基础工具
    # =========================
    def SetPos(side, pct, desc=None):
        s = str(side).strip().capitalize()
        if s not in ("Yes", "No"):
            raise ValueError(f"side 必须是 Yes/No，当前: {side}")
        p = _to_float(pct, default=0.0)
        if p > 1.0 and p <= 100.0:
            p = p / 100.0
        if p < 0:
            p = 0.0
        if p > 1:
            p = 1.0
        action_desc = str(desc).strip() if desc is not None else ""
        if not action_desc:
            action_desc = f"将 {s} 目标仓位设为 {float(p)}"
        actions.append({"type": "SETPOS", "side": s, "pct": float(p), "desc": action_desc})

    def clamp01(x):
        x = _to_float(x, 0.0)
        if x < 0:
            return 0.0
        if x > 1:
            return 1.0
        return float(x)

    def detect_pos_state(yes_pos, no_pos):
        # 明确五档仓位状态，避免旧版 S2/S3 那种脏状态
        EMPTY_TH = 0.10
        HALF_LOW = 0.35
        HALF_HIGH = 0.65
        FULL_TH = 0.85

        if yes_pos <= EMPTY_TH and no_pos <= EMPTY_TH:
            return "P0_EMPTY"
        if HALF_LOW <= yes_pos <= HALF_HIGH and no_pos <= EMPTY_TH:
            return "P1_YES_HALF"
        if yes_pos >= FULL_TH and no_pos <= EMPTY_TH:
            return "P2_YES_FULL"
        if HALF_LOW <= no_pos <= HALF_HIGH and yes_pos <= EMPTY_TH:
            return "P3_NO_HALF"
        if no_pos >= FULL_TH and yes_pos <= EMPTY_TH:
            return "P4_NO_FULL"

        # 非标准仓位：按主方向就近归类，但不再混成旧 S3 垃圾桶
        if yes_pos > no_pos:
            if yes_pos >= 0.70:
                return "P2_YES_FULL"
            return "P1_YES_HALF"
        if no_pos > yes_pos:
            if no_pos >= 0.70:
                return "P4_NO_FULL"
            return "P3_NO_HALF"
        return "P0_EMPTY"

    def target_state_from_fact(fact_state):
        if fact_state == "F_YES":
            return "P2_YES_FULL"
        if fact_state == "F_NO":
            return "P4_NO_FULL"
        return "P0_EMPTY"

    def step_towards(cur_state, target_state):
        # 只允许一步迁移，防止抖动和反手过猛
        if cur_state == target_state:
            return cur_state

        ladder = ["P4_NO_FULL", "P3_NO_HALF", "P0_EMPTY", "P1_YES_HALF", "P2_YES_FULL"]
        cur_i = ladder.index(cur_state)
        tar_i = ladder.index(target_state)

        if cur_i < tar_i:
            return ladder[cur_i + 1]
        return ladder[cur_i - 1]

    def apply_state(next_state, reason):
        if next_state == "P0_EMPTY":
            SetPos("Yes", 0.0, reason + " | Yes->0.0")
            SetPos("No", 0.0, reason + " | No->0.0")
        elif next_state == "P1_YES_HALF":
            SetPos("No", 0.0, reason + " | No->0.0")
            SetPos("Yes", 0.5, reason + " | Yes->0.5")
        elif next_state == "P2_YES_FULL":
            SetPos("No", 0.0, reason + " | No->0.0")
            SetPos("Yes", 1.0, reason + " | Yes->1.0")
        elif next_state == "P3_NO_HALF":
            SetPos("Yes", 0.0, reason + " | Yes->0.0")
            SetPos("No", 0.5, reason + " | No->0.5")
        elif next_state == "P4_NO_FULL":
            SetPos("Yes", 0.0, reason + " | Yes->0.0")
            SetPos("No", 1.0, reason + " | No->1.0")
        else:
            raise ValueError(f"未知目标状态: {next_state}")

    # =========================
    # 输入读取
    # =========================
    raw_usedata = usedata.to_dict() or {}
    Print("=== INPUT_PARAMS_BEGIN ===")
    Print("param.AnchorCompany=" + str(anchor_company))
    Print("param.RankPosition=" + str(rank_position))
    Print("param.UseData.Count=" + str(len(raw_usedata)))
    for k in sorted(raw_usedata.keys(), key=lambda x: str(x)):
        Print("param.UseData." + str(k) + "=" + str(raw_usedata.get(k)))
    Print("=== INPUT_PARAMS_END ===")

    Enddate = usedata.get("Enddate", usedata.get("end_date", ""))
    day_to_end = _to_float(usedata.get("day_to_end", usedata.get("days_to_end", 9999)), default=9999)

    Yes_now_bid = _to_float(usedata.get("Yes_now_bid", 0.0), default=0.0)
    Yes_now_ask = _to_float(usedata.get("Yes_now_ask", 1.0), default=1.0)
    No_now_bid = _to_float(usedata.get("No_now_bid", 0.0), default=0.0)
    No_now_ask = _to_float(usedata.get("No_now_ask", 1.0), default=1.0)

    Yes_Now_Pos = clamp01(usedata.get("Yes_Now_Pos", 0.0))
    No_Now_Pos = clamp01(usedata.get("No_Now_Pos", 0.0))

    anchor_raw = anchor_company
    mcap_map = _extract_mcap_usd_map(usedata)

    RANK_UNIVERSE_REQUIRED = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]
    missing_rank_symbols = [s for s in RANK_UNIVERSE_REQUIRED if s not in mcap_map or _to_float(mcap_map.get(s), 0.0) <= 0.0]
    rank_ok = (len(missing_rank_symbols) == 0)

    anchor, anchor_resolve = _resolve_anchor_company(anchor_raw, mcap_map)
    if not anchor or anchor not in mcap_map:
        companies = sorted(list(mcap_map.keys()))[:10]
        raise ValueError(f"锚定公司未找到市值字段: {anchor_company}；可用公司示例: {companies}")

    total_companies = len(mcap_map)
    if total_companies < 2:
        raise ValueError("市值公司数量不足（至少需要2个 McapUsd_XXX 字段）")

    target_rank = _to_int(rank_position, default=3)
    if target_rank < 1:
        target_rank = 1
    if target_rank > total_companies:
        target_rank = total_companies

    anchor_mcap = _to_float(mcap_map.get(anchor, 0.0), default=0.0)

    Print("now_time=missing")
    Print("Enddate=" + str(Enddate))
    Print("day_to_end=" + str(day_to_end))
    Print("anchor_company_input=" + str(anchor_raw))
    Print("anchor_company=" + str(anchor))
    Print("anchor_resolve=" + str(anchor_resolve))
    Print("target_rank=" + str(target_rank))
    Print("company_count=" + str(total_companies))
    Print("Yes_now_bid=" + str(Yes_now_bid) + " Yes_now_ask=" + str(Yes_now_ask))
    Print("No_now_bid=" + str(No_now_bid) + " No_now_ask=" + str(No_now_ask))
    for c, v in sorted(mcap_map.items()):
        Print("McapUsd_" + str(c) + "=" + str(v))
    Print("Yes_Now_Pos=" + str(Yes_Now_Pos) + " No_Now_Pos=" + str(No_Now_Pos))

    # =========================
    # 排名事实计算
    # =========================
    higher_count = 0
    for c, v in mcap_map.items():
        if c == anchor:
            continue
        if v > anchor_mcap:
            higher_count += 1

    tie_flag = 0
    for c, v in mcap_map.items():
        if c == anchor:
            continue
        if v == anchor_mcap:
            tie_flag = 1

    BIG = 999999999999999999
    closest_above = BIG
    closest_below = 0
    for c, v in mcap_map.items():
        if c == anchor:
            continue
        if v > anchor_mcap and v < closest_above:
            closest_above = v
        if v < anchor_mcap and v > closest_below:
            closest_below = v

    gap_up = 0.0
    gap_down = 0.0
    if closest_above < BIG:
        gap_up = float(closest_above - anchor_mcap)
    if closest_below > 0:
        gap_down = float(anchor_mcap - closest_below)

    is_target_rank = 0
    if rank_ok and higher_count == (target_rank - 1) and tie_flag == 0:
        is_target_rank = 1

    # hold_buffer_yes：
    #   当前就在目标名次时，守住当前名次的缓冲
    # recover_buffer_no：
    #   当前不在目标名次时，回到目标名次还差多少
    hold_buffer_yes = 0.0
    recover_buffer_no = 0.0

    current_rank = higher_count + 1

    if is_target_rank == 1:
        # 在目标名次上时，看更容易被谁挤掉
        # 对“是否排第2”来说，本质更看 gap_down（领先下一个的缓冲）
        hold_buffer_yes = gap_down
    else:
        # 不在目标名次上时，分方向看还差多少
        if current_rank > target_rank:
            # 当前名次更靠后，比如第3想回到第2，看 gap_up（离上面最近一名的差距）
            recover_buffer_no = gap_up
        elif current_rank < target_rank:
            # 当前名次更靠前，比如第1而目标第2，这类题严格讲也不满足
            # 这里按“不在目标位，偏 No”处理，但给一个较高置信的 no_fact
            recover_buffer_no = 0.0
        else:
            # 有 tie 导致未满足目标位
            recover_buffer_no = 0.0

    Print("higher_count=" + str(higher_count))
    Print("tie_flag=" + str(tie_flag))
    Print("current_rank=" + str(current_rank))
    Print("gap_up=" + str(gap_up))
    Print("gap_down=" + str(gap_down))
    Print("hold_buffer_yes=" + str(hold_buffer_yes))
    Print("recover_buffer_no=" + str(recover_buffer_no))
    Print("rank_ok=" + str(rank_ok) + " missing_rank_symbols=" + ",".join(missing_rank_symbols))
    Print("is_target_rank=" + str(is_target_rank))

    # =========================
    # 防抖阈值（无历史版）
    # =========================
    # 你后续可直接调这些数字
    YES_FULL_ON = 120000000000.0   # 在目标位且领先缓冲很大，偏 Yes
    YES_OFF = 60000000000.0        # 低于此值就不再认为 Yes 强

    NO_FULL_ON = 250000000000.0    # 不在目标位且距离回归很远，偏 No
    NO_OFF = 120000000000.0        # 小于此值说明“不在目标位但很接近”，进入中性观察

    # 临近结算时更保守
    if day_to_end <= 1.0:
        YES_FULL_ON = YES_FULL_ON * 1.20
        YES_OFF = YES_OFF * 1.10
        NO_FULL_ON = NO_FULL_ON * 0.85
        NO_OFF = NO_OFF * 0.85

    # =========================
    # 事实判定
    # =========================
    if not rank_ok:
        fact_state = "F_NEUTRAL"
        fact_reason = "rank_data_incomplete"
    else:
        if is_target_rank == 1:
            if hold_buffer_yes >= YES_FULL_ON:
                fact_state = "F_YES"
                fact_reason = f"target_rank_ok_and_hold_buffer_large({hold_buffer_yes} >= {YES_FULL_ON})"
            elif hold_buffer_yes <= YES_OFF:
                fact_state = "F_NEUTRAL"
                fact_reason = f"target_rank_ok_but_hold_buffer_not_enough({hold_buffer_yes} <= {YES_OFF})"
            else:
                fact_state = "F_NEUTRAL"
                fact_reason = f"target_rank_ok_but_mid_zone({YES_OFF} < {hold_buffer_yes} < {YES_FULL_ON})"
        else:
            # 不在目标名次时，先偏向 No；但如果非常接近目标位，则只给中性
            if recover_buffer_no >= NO_FULL_ON:
                fact_state = "F_NO"
                fact_reason = f"not_target_rank_and_far_from_recover({recover_buffer_no} >= {NO_FULL_ON})"
            elif recover_buffer_no <= NO_OFF:
                fact_state = "F_NEUTRAL"
                fact_reason = f"not_target_rank_but_recover_gap_small({recover_buffer_no} <= {NO_OFF})"
            else:
                fact_state = "F_NO"
                fact_reason = f"not_target_rank_mid_to_far({NO_OFF} < {recover_buffer_no} < {NO_FULL_ON})"

    # =========================
    # 仓位状态识别 + 目标状态 + 单步迁移
    # =========================
    pos_state = detect_pos_state(Yes_Now_Pos, No_Now_Pos)
    target_state = target_state_from_fact(fact_state)
    next_state = step_towards(pos_state, target_state)

    Print("pos_state=" + str(pos_state))
    Print("fact_state=" + str(fact_state))
    Print("fact_reason=" + str(fact_reason))
    Print("target_state=" + str(target_state))
    Print("next_state=" + str(next_state))

    # =========================
    # 执行动作
    # =========================
    if not rank_ok:
        Print("decision=HOLD")
        Print("reason=rank_data_incomplete: 市值数据不完整，不执行任何仓位变动")
    elif next_state == pos_state:
        Print("decision=HOLD")
        Print("reason=hold: 当前仓位状态已与事实判定匹配，无需迁移")
    else:
        reason = f"{pos_state}->{next_state} | fact={fact_state} | {fact_reason}"
        apply_state(next_state, reason)
        Print("decision=SET")
        Print("reason=" + reason)

    # =========================
    # 汇总输出
    # =========================
    ts = _pick_ts(usedata)
    decision = "SETPOS" if len(actions) > 0 else "HOLD"

    reason_line = ""
    for line in reversed(logs):
        s = str(line)
        if s.startswith("reason="):
            reason_line = s.split("=", 1)[1].strip()
            break
    if not reason_line:
        reason_line = "no_rule_triggered"

    metrics = {
        "ts": ts or "missing",
        "decision": decision,
        "anchor_company": anchor,
        "target_rank": target_rank,
        "current_rank": current_rank,
        "higher_count": higher_count,
        "tie_flag": tie_flag,
        "is_target_rank": is_target_rank,
        "gap_up": gap_up,
        "gap_down": gap_down,
        "hold_buffer_yes": hold_buffer_yes,
        "recover_buffer_no": recover_buffer_no,
        "day_to_end": day_to_end,
        "anchor_mcap": anchor_mcap,
        "fact_state": fact_state,
        "fact_reason": fact_reason,
        "pos_state": pos_state,
        "target_state": target_state,
        "next_state": next_state,
        "yes_now_pos": Yes_Now_Pos,
        "no_now_pos": No_Now_Pos,
        "rank_ok": rank_ok,
        "missing_rank_symbols": ",".join(missing_rank_symbols),
        "yes_full_on": YES_FULL_ON,
        "yes_off": YES_OFF,
        "no_full_on": NO_FULL_ON,
        "no_off": NO_OFF,
    }

    summary_inputs = [
        "[INPUT]",
        f"Anchor={anchor} TargetRank={target_rank}",
        f"day_to_end={day_to_end}",
        f"Yes_bid={Yes_now_bid} No_bid={No_now_bid}",
        "[CALC]",
        f"current_rank={current_rank}",
        f"is_target_rank={is_target_rank}",
        f"gap_up={gap_up}",
        f"gap_down={gap_down}",
        f"hold_buffer_yes={hold_buffer_yes}",
        f"recover_buffer_no={recover_buffer_no}",
        f"fact_state={fact_state}",
        f"pos_state={pos_state}",
        f"target_state={target_state}",
        f"next_state={next_state}",
        "[RULE]",
    ]

    if not rank_ok:
        summary_inputs.append("⚠️ 市值数据不完整，本轮不执行。缺失: " + ",".join(missing_rank_symbols))
    else:
        if fact_state == "F_YES":
            summary_inputs.append("事实判定偏 Yes：当前在目标名次且领先缓冲足够。")
        elif fact_state == "F_NO":
            summary_inputs.append("事实判定偏 No：当前不在目标名次，且回归目标名次难度较高。")
        else:
            summary_inputs.append("事实判定中性：暂不支持激进押注，优先向空仓或轻仓靠拢。")

    if decision == "HOLD":
        summary_inputs.append("本轮未触发仓位迁移。")
    else:
        summary_inputs.append("本轮触发单步仓位迁移，已下发 SetPos。")

    summary_inputs.append("[RESULT]")
    summary_inputs.append(f"Decision={decision}")
    summary_inputs.append(f"Reason={reason_line}")
    if decision == "SETPOS":
        acts = [f"{a.get('side')}:{a.get('pct')}" for a in actions if isinstance(a, dict)]
        summary_inputs.append("SetPos=" + ", ".join(acts))

    inputs_payload = {
        "raw_param": {
            "AnchorCompany": anchor_company,
            "RankPosition": rank_position,
        },
        "raw_usedata": raw_usedata,
        "UseData": raw_usedata,
        "NowTime": ts,
        "Enddate": Enddate,
    }

    db_logs = []

    def DBPrint(text):
        db_logs.append(str(text))

    _emit_db_json(DBPrint, ts, inputs_payload, actions, calc=metrics)
    return {"actions": actions, "metrics": metrics, "print": summary_inputs, "wake_reason": wake_reason}

def run_node(node):
    try:
        node_inputs = node.get("Inputs") or []
        usedata_raw = node_inputs[0].get("Context") if len(node_inputs) > 0 else None
        anchor_company = node_inputs[1].get("Context") if len(node_inputs) > 1 else "GOOGL"
        rank_position = None
        if len(node_inputs) > 2:
            rank_position = node_inputs[2].get("Context")
            if rank_position in (None, "") and node_inputs[2].get("Num") is not None:
                rank_position = node_inputs[2].get("Num")

        usedata_dict, usedata_err = _parse_usedata(usedata_raw)
        if usedata_err:
            out_json = {"actions": [], "print": [f"[UseDataError] {usedata_err}"], "wake_reason": None}
            Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
            Outputs[1]["Boolean"] = False
            return Outputs

        out_json = _run_strategy(_UseDataProxy(usedata_dict), anchor_company, _to_int(rank_position, default=3))
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = True
        return Outputs
    except Exception as e:
        out_json = {"actions": [], "print": [f"[RuntimeError] {type(e).__name__}: {e}"], "wake_reason": None}
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = False
        return Outputs

