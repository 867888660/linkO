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


def _emit_db_json(Print, ts, inputs, actions):
    payload = {
        "ts": ts,
        "inputs": inputs if isinstance(inputs, dict) else {},
        "actions": actions if isinstance(actions, list) else [],
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
    "TESLA": "TSLA",
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

    # 先打印完整入参，便于第一时间核对上游传入内容
    raw_usedata = usedata.to_dict() or {}
    Print("=== INPUT_PARAMS_BEGIN ===")
    Print("param.AnchorCompany=" + str(anchor_company))
    Print("param.RankPosition=" + str(rank_position))
    Print("param.UseData.Count=" + str(len(raw_usedata)))
    for k in sorted(raw_usedata.keys(), key=lambda x: str(x)):
        Print("param.UseData." + str(k) + "=" + str(raw_usedata.get(k)))
    Print("=== INPUT_PARAMS_END ===")

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

    Enddate = usedata.get("Enddate", usedata.get("end_date", ""))
    day_to_end = _to_float(usedata.get("day_to_end", usedata.get("days_to_end", 9999)), default=9999)
    Yes_now_bid = _to_float(usedata.get("Yes_now_bid", 0.0), default=0.0)
    Yes_now_ask = _to_float(usedata.get("Yes_now_ask", 1.0), default=1.0)
    No_now_bid = _to_float(usedata.get("No_now_bid", 0.0), default=0.0)
    No_now_ask = _to_float(usedata.get("No_now_ask", 1.0), default=1.0)
    Yes_Now_Pos = _to_float(usedata.get("Yes_Now_Pos", 0.0), default=0.0)
    No_Now_Pos = _to_float(usedata.get("No_Now_Pos", 0.0), default=0.0)
    anchor_raw = anchor_company
    mcap_map = _extract_mcap_usd_map(usedata)
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

    higher_count = 0
    for c, v in mcap_map.items():
        if c == anchor:
            continue
        if v > anchor_mcap:
            higher_count = higher_count + 1

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

    gap_up = 0
    gap_down = 0
    if closest_above < BIG:
        gap_up = closest_above - anchor_mcap
    if closest_below > 0:
        gap_down = anchor_mcap - closest_below

    edge_margin = gap_up
    if gap_down < edge_margin:
        edge_margin = gap_down

    Print("higher_count=" + str(higher_count))
    Print("tie_flag=" + str(tie_flag))
    Print("gap_up=" + str(gap_up))
    Print("gap_down=" + str(gap_down))
    Print("edge_margin=" + str(edge_margin))

    UP_Y1 = 90000000000
    DOWN_Y1 = 50000000000
    TO_NO_HALF_MARGIN = 20000000000
    TO_YES_HALF_MARGIN = 30000000000
    DOWN_N1_MARGIN = 10000000000
    UP_N1_MARGIN = 25000000000

    if Yes_Now_Pos >= 0.75 and No_Now_Pos <= 0.25:
        state = "S1"
    elif Yes_Now_Pos > No_Now_Pos:
        state = "S2"
    elif No_Now_Pos >= 0.75 and Yes_Now_Pos <= 0.25:
        state = "S4"
    else:
        state = "S3"
    Print("state=" + str(state))

    is_target_rank = 0
    if higher_count == (target_rank - 1) and tie_flag == 0:
        is_target_rank = 1
    Print("is_target_rank=" + str(is_target_rank))

    if day_to_end <= 0.25:
        if state == "S1":
            if is_target_rank == 0 or edge_margin <= DOWN_Y1:
                SetPos("No", 0.0)
                SetPos("Yes", 0.5)
                Print("decision=SET")
                Print("side=Yes")
                Print("pct=0.5")
                Print("reason=final_window S1->S2: 目标排名稳定性下降，先降仓")
            else:
                Print("decision=HOLD")
                Print("side=Yes")
                Print("pct=1.0")
                Print("reason=final_window hold S1")
        elif state == "S2":
            if is_target_rank == 1 and edge_margin >= UP_Y1:
                SetPos("No", 0.0)
                SetPos("Yes", 1.0)
                Print("decision=SET")
                Print("side=Yes")
                Print("pct=1.0")
                Print("reason=final_window S2->S1: 目标排名稳固，回Yes满仓")
            elif is_target_rank == 0 and edge_margin <= TO_NO_HALF_MARGIN:
                SetPos("Yes", 0.0)
                SetPos("No", 0.5)
                Print("decision=SET")
                Print("side=No")
                Print("pct=0.5")
                Print("reason=final_window S2->S3: 偏离目标排名且边界变窄，慢换No")
            else:
                Print("decision=HOLD")
                Print("side=Yes")
                Print("pct=0.5")
                Print("reason=final_window hold S2")
        elif state == "S3":
            if is_target_rank == 1 and edge_margin >= TO_YES_HALF_MARGIN:
                SetPos("No", 0.0)
                SetPos("Yes", 0.5)
                Print("decision=SET")
                Print("side=Yes")
                Print("pct=0.5")
                Print("reason=final_window S3->S2: 回到目标排名并恢复缓冲，回Yes半仓")
            elif is_target_rank == 0 and edge_margin <= DOWN_N1_MARGIN:
                SetPos("Yes", 0.0)
                SetPos("No", 1.0)
                Print("decision=SET")
                Print("side=No")
                Print("pct=1.0")
                Print("reason=final_window S3->S4: 明确非目标排名且边界极窄，No满仓")
            else:
                Print("decision=HOLD")
                Print("side=No")
                Print("pct=0.5")
                Print("reason=final_window hold S3")
        else:
            if is_target_rank == 1 or edge_margin >= UP_N1_MARGIN:
                SetPos("Yes", 0.0)
                SetPos("No", 0.5)
                Print("decision=SET")
                Print("side=No")
                Print("pct=0.5")
                Print("reason=final_window S4->S3: No极端缓和，先降到No半仓")
            else:
                Print("decision=HOLD")
                Print("side=No")
                Print("pct=1.0")
                Print("reason=final_window hold S4")
    else:
        if state == "S1":
            if is_target_rank == 0 or edge_margin <= DOWN_Y1:
                SetPos("No", 0.0)
                SetPos("Yes", 0.5)
                Print("decision=SET")
                Print("side=Yes")
                Print("pct=0.5")
                Print("reason=S1->S2: 目标排名稳定性下降，先减仓")
            else:
                Print("decision=HOLD")
                Print("side=Yes")
                Print("pct=1.0")
                Print("reason=hold S1")
        elif state == "S2":
            if is_target_rank == 1 and edge_margin >= UP_Y1:
                SetPos("No", 0.0)
                SetPos("Yes", 1.0)
                Print("decision=SET")
                Print("side=Yes")
                Print("pct=1.0")
                Print("reason=S2->S1: 目标排名稳固，升到Yes满仓")
            elif is_target_rank == 0 and edge_margin <= TO_NO_HALF_MARGIN:
                SetPos("Yes", 0.0)
                SetPos("No", 0.5)
                Print("decision=SET")
                Print("side=No")
                Print("pct=0.5")
                Print("reason=S2->S3: 偏离目标排名且边界窄，慢换No")
            else:
                Print("decision=HOLD")
                Print("side=Yes")
                Print("pct=0.5")
                Print("reason=hold S2")
        elif state == "S3":
            if is_target_rank == 1 and edge_margin >= TO_YES_HALF_MARGIN:
                SetPos("No", 0.0)
                SetPos("Yes", 0.5)
                Print("decision=SET")
                Print("side=Yes")
                Print("pct=0.5")
                Print("reason=S3->S2: 回归目标排名且边界恢复，回Yes半仓")
            elif is_target_rank == 0 and edge_margin <= DOWN_N1_MARGIN:
                SetPos("Yes", 0.0)
                SetPos("No", 1.0)
                Print("decision=SET")
                Print("side=No")
                Print("pct=1.0")
                Print("reason=S3->S4: 非目标排名状态强化，No满仓")
            else:
                Print("decision=HOLD")
                Print("side=No")
                Print("pct=0.5")
                Print("reason=hold S3")
        else:
            if is_target_rank == 1 or edge_margin >= UP_N1_MARGIN:
                SetPos("Yes", 0.0)
                SetPos("No", 0.5)
                Print("decision=SET")
                Print("side=No")
                Print("pct=0.5")
                Print("reason=S4->S3: No极端缓和，先降No半仓")
            else:
                Print("decision=HOLD")
                Print("side=No")
                Print("pct=1.0")
                Print("reason=hold S4")

    ts = _pick_ts(usedata)
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
    _emit_db_json(Print, ts, inputs_payload, actions)

    return {"actions": actions, "print": logs, "wake_reason": wake_reason}


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

