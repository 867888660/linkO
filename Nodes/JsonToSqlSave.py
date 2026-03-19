import json
import os
import re
import sqlite3
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

# =========================
# Node metadata
# =========================
OutPutNum = 2
InPutNum = 16

Outputs = [
    {
        'Num': None, 'Context': None, 'Boolean': False, 'Kind': None,
        'Id': f'Output{i + 1}', 'name': f'OutPut{i + 1}', 'Link': 0
    }
    for i in range(OutPutNum)
]

Inputs = [
    {
        'Num': None, 'Context': None, 'Boolean': False, 'Kind': None,
        'Id': f'Input{i + 1}', 'Isnecessary': True, 'name': f'Input{i + 1}',
        'Link': 0, 'IsLabel': False
    }
    for i in range(InPutNum)
]

NodeKind = 'Normal'
InputIsAdd = False
OutputIsAdd = False
Lable = [{'Id': 'Label1', 'Kind': 'None'}]

Inputs[0]['Kind'] = 'String_FilePath'
Inputs[0]['name'] = 'SavePath'

Inputs[1]['Kind'] = 'String'
Inputs[1]['name'] = 'SaveName'

Inputs[2]['Kind'] = 'String'
Inputs[2]['name'] = 'YesJson'

Inputs[3]['Kind'] = 'String'
Inputs[3]['name'] = 'NoJson'

Inputs[4]['Kind'] = 'String'
Inputs[4]['name'] = 'RealTimeJson'

# 新增：强制由外部提供的批次时间与盘口字段（不再依赖 KV 兜底解析）
Inputs[5]['Kind'] = 'String'
Inputs[5]['name'] = 'NowTime'

Inputs[6]['Kind'] = 'String'
Inputs[6]['name'] = 'Yes_ask'

Inputs[7]['Kind'] = 'String'
Inputs[7]['name'] = 'Yes_bid'

Inputs[8]['Kind'] = 'String'
Inputs[8]['name'] = 'No_ask'

Inputs[9]['Kind'] = 'String'
Inputs[9]['name'] = 'No_bid'

# 新增：Action（可直接写入 Action_Data；也可与 RealTimeJson.actions 同时使用）
Inputs[10]['Kind'] = 'String'
Inputs[10]['name'] = 'Action'

# 新增：买入/卖出模式 & 份额数（写入 Action_Data）
# 说明：
# - YesMode / NoMode：建议传 BUY/SELL 或任意你自定义的模式字符串
# - YesQty / NoQty：建议传数字字符串（此组件按 TEXT 写入 SQLite）
Inputs[11]['Kind'] = 'String'
Inputs[11]['name'] = 'YesMode'

Inputs[12]['Kind'] = 'String'
Inputs[12]['name'] = 'NoMode'

Inputs[13]['Kind'] = 'String'
Inputs[13]['name'] = 'YesQty'

Inputs[14]['Kind'] = 'String'
Inputs[14]['name'] = 'NoQty'

# 新增：Symbol（用于按标的维度写入 & 去重）
Inputs[15]['Kind'] = 'String'
Inputs[15]['name'] = 'Symbol'

# 可选输入（避免 UI/运行时强制要求）
for _i in range(2, InPutNum):
    Inputs[_i]['Isnecessary'] = False

# outputs
Outputs[0]['Kind'] = 'String'
Outputs[0]['name'] = 'Result'

Outputs[1]['Kind'] = 'String'
Outputs[1]['name'] = 'Full_Path'

FunctionIntroduction = (
    '组件功能：将 Yes / No / 实时 / 指标 的 JSON 输入解析为结构化记录，并写入 SQLite 的五张业务表：'
    '`Yes_Data` / `No_Data` / `RealTime_Data` / `Action_Data` / `metrics`。\n\n'
    '代码功能摘要：\n'
    '- 输入分三路：YesJson / NoJson / RealTimeJson（支持 `{...}`、`[{...},{...}]`、多行 JSONL、多个 JSON 拼接；RealTimeJson 额外支持 `key:value` / `key：value` 多行文本）\n'
    '- 可选 Action 输入：写入 `Action_Data`（同样支持 JSON/JSONL/多段 JSON）\n'
    '- 可选 YesMode/NoMode/YesQty/NoQty：写入 `Action_Data`（用于记录买入/卖出模式与份额数）\n'
    '- 自动解析列：遇到 dict 记录时，用其 key 自动生成/扩展表列（SQLite `ALTER TABLE ADD COLUMN`）\n'
    '- 按记录插入：每条记录插入 1 行；非 dict 记录会写入 `value_text` 列\n'
    '- 每行附带 `saved_at_utc` 字段\n\n'
    '参数：\n'
    '```yaml\n'
    'inputs:\n'
    '  - name: SavePath\n'
    '    type: string (folder)\n'
    '    required: true\n'
    '    description: SQLite 文件保存目录\n'
    '  - name: SaveName\n'
    '    type: string\n'
    '    required: true\n'
    '    description: SQLite 文件名（可不带扩展名，默认补 .db）\n'
    '  - name: YesJson\n'
    '    type: string\n'
    '    required: false\n'
    '    description: Yes 数据（JSON/多段 JSON/JSONL）\n'
    '  - name: NoJson\n'
    '    type: string\n'
    '    required: false\n'
    '    description: No 数据（JSON/多段 JSON/JSONL）\n'
    '  - name: RealTimeJson\n'
    '    type: string\n'
    '    required: false\n'
    '    description: 实时数据（JSON/多段 JSON/JSONL，或 `key:value` 多行文本）\n'
    '  - name: NowTime\n'
    '    type: string\n'
    '    required: false\n'
    '    description: 批次统一时间（优先级最高，用于写入 query_time / saved_at_utc）\n'
    '  - name: Yes_ask\n'
    '    type: string\n'
    '    required: false\n'
    '    description: Yes ask（写入 Yes_Data 的 ask）\n'
    '  - name: Yes_bid\n'
    '    type: string\n'
    '    required: false\n'
    '    description: Yes bid（写入 Yes_Data 的 bid）\n'
    '  - name: No_ask\n'
    '    type: string\n'
    '    required: false\n'
    '    description: No ask（写入 No_Data 的 ask）\n'
    '  - name: No_bid\n'
    '    type: string\n'
    '    required: false\n'
    '    description: No bid（写入 No_Data 的 bid）\n'
    '  - name: Action\n'
    '    type: string\n'
    '    required: false\n'
    '    description: Action 数据（写入 Action_Data；支持 JSON/多段 JSON/JSONL）\n'
    '  - name: YesMode\n'
    '    type: string\n'
    '    required: false\n'
    '    description: Yes 买入/卖出模式（写入 Action_Data）\n'
    '  - name: NoMode\n'
    '    type: string\n'
    '    required: false\n'
    '    description: No 买入/卖出模式（写入 Action_Data）\n'
    '  - name: YesQty\n'
    '    type: string\n'
    '    required: false\n'
    '    description: Yes 份额数/数量（写入 Action_Data）\n'
    '  - name: NoQty\n'
    '    type: string\n'
    '    required: false\n'
    '    description: No 份额数/数量（写入 Action_Data）\n'
    '  - name: Symbol\n'
    '    type: string\n'
    '    required: false\n'
    '    description: 标的/代码（用于写入 symbol 列，并按 symbol 维度去重）\n'
    'outputs:\n'
    '  - name: Result\n'
    '    type: string\n'
    '    description: 保存摘要（每路写入/跳过/错误数）\n'
    '  - name: Full_Path\n'
    '    type: string\n'
    '    description: 实际保存的 SQLite 文件完整路径\n'
    '```\n'
)


# =========================
# Column inference / name sanitize
# =========================
_SQLITE_RESERVED_COLS = {"id", "saved_at_utc"}

# 表级更新时间：存到 __meta_cols 里，作为每张业务表的“伪列名”
# - table_name = 业务表名（Yes_Data / No_Data / RealTime_Data / Action_Data）
# - col_name   = "__table_updated_time"
# - last_value = 本批次的 saved_at_utc（通常等于 unified_query_time）
# - updated_at_utc = 写 meta 的系统时间（UTC）
_META_TABLE_UPDATED_COL = "__table_updated_time"

# 单列去重时忽略的“易变字段”（这些字段变化不触发写入）
_DEDUPE_IGNORE_KEYS_LOWER = {
    "ts_utc",
    "ingested_at",
    "nowtime",
    "latency_ms",
    "query_time_beijing",
    "query_time",
    "action_time_point",
}

# RealTime 拆行时要剔除的“时间/易变字段”（这些字段不入库）
_RT_STRIP_KEYS_LOWER = {
    "ts_utc",
    "ingested_at",
    "nowtime",
    "latency_ms",
    "query_time_beijing",
    "query_time",
    "saved_at_utc",
}

# 单行内容指纹的伪“列名”（存到 meta 表里，不会真的建到业务表）
_RT_DEDUPE_FP_COL = "__rt_data_fingerprint"
_ACT_DEDUPE_FP_COL = "__action_fingerprint"
_ACT_BATCH_DEDUPE_FP_COL = "__action_batch_fingerprint"

# Action 指纹去重时忽略的字段（这些字段变化不应触发写入）
_ACTION_FP_IGNORE_KEYS_LOWER = {
    # 时间/批次类
    "query_time",
    "query_time_beijing",
    "ts_utc",
    "nowtime",
    "ingested_at",
    "latency_ms",
    "saved_at_utc",
    # Action 的“定位/来源”类（内容相同则视为重复）
    "rt_time",
    "action_index",
    "action_source",
    "action_raw_json",
    # 原始 JSON 备份列：不参与“动作是否变化”的判定（避免仅格式变化导致重复写入）
    "originaljson",
    # print 是日志/解释文本，可能包含 day_to_end 等易变行；不应触发“动作变化”
    "print",
}


# Action 解析 action_raw_json 时，递归剔除的“时间/易变字段”（不入库也不参与指纹）
_ACTION_STRIP_KEYS_LOWER = {
    "ts_utc",
    "timestamp",
    "time",
    "query_time",
    "query_time_beijing",
    "saved_at_utc",
    "nowtime",
    "ingested_at",
    "latency_ms",
}

_ACTION_DB_FIELDS = (
    "db_ts",
    "db_inputs_json",
    "db_actions_json",
    "db_prints_json",
    "db_calc_json",
)

_REALTIME_ACTION_CONTEXT_KEYS = (
    "Yes_Min_BudgetCap",
    "Yes_Max_BudgetCap",
    "No_Min_BudgetCap",
    "No_Max_BudgetCap",
    "Yes_now_Qty",
    "No_now_Qty",
    "Yes_now_avgPrice",
    "No_now_avgPrice",
    "Yes_depth_ask_1c_usd",
    "Yes_depth_bid_1c_usd",
    "No_depth_ask_1c_usd",
    "No_depth_bid_1c_usd",
    "Yes_now_ask",
    "Yes_now_bid",
    "No_now_ask",
    "No_now_bid",
    "Yes_OpenOrdersQty",
    "No_OpenOrdersQty",
    "Yes_Now_Pos",
    "No_Now_Pos",
)

_ACTION_ALLOWED_KEYS = (
    "Yes_Pct",
    "No_Pct",
    "action_raw_json",
    "YesMode",
    "NoMode",
    "YesQty",
    "NoQty",
    "Print",
) + _REALTIME_ACTION_CONTEXT_KEYS


def _extract_metrics_dict(v: Any) -> Optional[Dict[str, Any]]:
    """
    尽量把输入解析为 metrics dict：
    - dict 直接返回
    - str 尝试按 JSON 解析后返回 dict
    其它类型返回 None
    """
    vv = _maybe_json_load(v)
    if isinstance(vv, dict):
        return vv
    return None


def _parse_kv_text_record(text: Any) -> Optional[Dict[str, Any]]:
    """
    解析形如 `key: value` / `key：value` 的多行文本为 dict。
    仅当至少成功解析 1 行时返回 dict。
    """
    s = _safe_str(text)
    if not s.strip():
        return None

    rec: Dict[str, Any] = {}
    for raw_line in s.splitlines():
        line = _safe_str(raw_line).strip()
        if not line:
            continue
        sep = "：" if "：" in line else (":" if ":" in line else None)
        if sep is None:
            continue
        key, value = line.split(sep, 1)
        key = _safe_str(key).strip()
        if not key:
            continue
        rec[key] = _safe_str(value).strip()
    return rec if rec else None


def _normalize_realtime_records(raw: Any) -> Tuple[List[Any], int]:
    """
    RealTimeJson 专用归一化：
    - 先按现有 JSON/JSONL/多段 JSON 规则解析
    - 若失败，再兜底解析 `key: value` / `key：value` 多行文本
    """
    records, parse_err = _normalize_to_records(raw)
    if records or not isinstance(raw, str):
        return records, parse_err
    kv_rec = _parse_kv_text_record(raw)
    if kv_rec:
        return [kv_rec], 0
    return records, parse_err


def _extract_realtime_context_fields(rt_raw: Any) -> Dict[str, Any]:
    """
    从 RealTimeJson 中抽取需附带到 Action_Data 的检查字段。
    支持 JSON dict / `key:value` 文本。
    """
    out: Dict[str, Any] = {}
    records, _ = _normalize_realtime_records(rt_raw)
    if not records:
        return out

    def _pick_from_dict(src: Dict[str, Any]):
        lower_map = {(_safe_str(k).strip().lower()): k for k in src.keys()}
        for want in _REALTIME_ACTION_CONTEXT_KEYS:
            want_lower = want.lower()
            if want in out:
                continue
            if want_lower in lower_map:
                out[want] = src.get(lower_map[want_lower])

    for rec in records:
        if not isinstance(rec, dict):
            continue
        _pick_from_dict(rec)
        data_dict = _extract_data_as_dict(rec.get("data")) if "data" in rec else None
        if isinstance(data_dict, dict):
            _pick_from_dict(data_dict)
        if len(out) == len(_REALTIME_ACTION_CONTEXT_KEYS):
            break
    return out


def _build_action_snapshot(rec: Any, print_hint: Any = None) -> Optional[Dict[str, Any]]:
    """
    把任意 action 来源归一化为 Action_Data 快照行，仅保留允许字段。
    """
    if not isinstance(rec, dict):
        return None
    out: Dict[str, Any] = {}

    # 1) Yes/No pct（优先直接字段，否则尝试从 actions 提取）
    y_pct = rec.get("Yes_Pct")
    n_pct = rec.get("No_Pct")
    if y_pct is None and n_pct is None:
        yy, nn, ok = _extract_yes_no_pct_from_actions(rec.get("actions"))
        if ok:
            y_pct, n_pct = yy, nn
    if y_pct is not None:
        out["Yes_Pct"] = y_pct
    if n_pct is not None:
        out["No_Pct"] = n_pct

    # 2) 原始 action json
    raw_json = _json_text_or_none(_maybe_json_load(rec.get("actions")))
    if raw_json:
        out["action_raw_json"] = raw_json
    elif rec.get("action_raw_json") is not None:
        out["action_raw_json"] = rec.get("action_raw_json")

    # 3) 模式/数量
    for kk in ("YesMode", "NoMode", "YesQty", "NoQty"):
        vv = rec.get(kk)
        if vv is not None and _safe_str(vv).strip() != "":
            out[kk] = vv

    # 4) Print（优先当前记录，再回退 hint）
    pv = rec.get("Print", rec.get("print", print_hint))
    if pv is not None and _safe_str(pv).strip() != "":
        out["Print"] = pv

    # 5) 仅保留白名单列
    final_out: Dict[str, Any] = {}
    for k in _ACTION_ALLOWED_KEYS:
        if k in out:
            final_out[k] = out.get(k)
    return final_out if final_out else None


def _sanitize_col_name(name: Any) -> str:
    """
    把任意 key 转成 SQLite 安全列名：
    - 仅保留 [A-Za-z0-9_]
    - 其它字符替换为 _
    - 不以数字开头
    - 避免保留列名冲突
    """
    s = _safe_str(name).strip()
    if not s:
        s = "col"
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Za-z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "col"
    if re.match(r"^\d", s):
        s = "c_" + s
    if s.lower() in _SQLITE_RESERVED_COLS:
        s = s + "_v"
    return s


def _to_sqlite_value(v: Any) -> Any:
    """
    尽量把值转成 SQLite 可存储的标量：
    - dict/list -> JSON 字符串
    - bool -> 0/1
    - number -> 原样
    - 其它 -> str
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            return _safe_str(v)
    return _safe_str(v)


def _safe_str(x: Any) -> str:
    try:
        return "" if x is None else str(x)
    except Exception:
        return ""


def _iter_json_from_text(text: str) -> Iterable[Any]:
    """
    从杂乱字符串中尽量提取 JSON 对象/数组：
    - 支持 '{...}{...}' / '{...}\n{...}' / '[{...},{...}]' 等
    - 会跳过中间无关字符
    """
    s = _safe_str(text)
    if not s:
        return

    dec = json.JSONDecoder()
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch not in "{[":
            i += 1
            continue
        try:
            obj, j = dec.raw_decode(s, i)
            yield obj
            i = j
        except Exception:
            i += 1


def _maybe_json_load(v: Any) -> Any:
    """
    如果 v 是形如 '{...}' / '[...]' 的字符串，尝试 json.loads；失败则返回原值。
    """
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return v
    if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
        return v
    try:
        return json.loads(s)
    except Exception:
        return v


def _strip_keys_recursive(obj: Any, strip_keys_lower: set) -> Any:
    """
    递归删除 dict 中指定 key（大小写不敏感）；list 会逐元素处理。
    用于剔除 ts_utc 等时间字段，避免入库/触发去重。
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            kl = _safe_str(k).strip().lower()
            if kl in strip_keys_lower:
                continue
            out[_safe_str(k).strip()] = _strip_keys_recursive(v, strip_keys_lower)
        return out
    if isinstance(obj, list):
        return [_strip_keys_recursive(x, strip_keys_lower) for x in obj]
    return obj


def _extract_db_json_block(print_val: Any) -> Optional[Dict[str, Any]]:
    """
    从 print 文本中提取机器协议块：
    ===DB_JSON_BEGIN===
    { ...json... }
    ===DB_JSON_END===
    仅返回最后一个可解析的 JSON 块。
    """
    if print_val is None:
        return None
    if isinstance(print_val, list):
        text = "\n".join([_safe_str(x) for x in print_val])
    else:
        text = _safe_str(print_val)
    if not text.strip():
        return None

    lines = text.splitlines()
    last_obj: Optional[Dict[str, Any]] = None
    for i, line in enumerate(lines):
        if _safe_str(line).strip() != "===DB_JSON_BEGIN===":
            continue
        if i + 2 >= len(lines):
            continue
        json_line = _safe_str(lines[i + 1]).strip()
        end_line = _safe_str(lines[i + 2]).strip()
        if end_line != "===DB_JSON_END===":
            continue
        if not (json_line.startswith("{") and json_line.endswith("}")):
            continue
        try:
            obj = json.loads(json_line)
            if isinstance(obj, dict):
                last_obj = obj
        except Exception:
            continue
    if last_obj is not None:
        return last_obj

    # 兼容历史：允许 BEGIN/END 之间是多行 JSON。
    pattern = r"===DB_JSON_BEGIN===\s*(\{.*?\})\s*===DB_JSON_END==="
    matches = re.findall(pattern, text, flags=re.DOTALL)
    for raw in reversed(matches):
        s = _safe_str(raw).strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _attach_db_payload_fields(rec: Dict[str, Any], db_payload: Any) -> int:
    """
    把 DB_JSON 协议中的结构化字段挂到 action 记录上，供 Action_Data 入库。
    """
    if not isinstance(rec, dict) or not isinstance(db_payload, dict):
        return 0
    attached = 0
    db_ts = _safe_str(db_payload.get("ts")).strip()
    if db_ts:
        rec["db_ts"] = db_ts
        attached += 1
    db_inputs = _json_text_or_none(db_payload.get("inputs"))
    if db_inputs:
        rec["db_inputs_json"] = db_inputs
        attached += 1
    db_actions = _json_text_or_none(db_payload.get("actions"))
    if db_actions:
        rec["db_actions_json"] = db_actions
        attached += 1
    db_prints = _json_text_or_none(db_payload.get("prints"))
    if db_prints:
        rec["db_prints_json"] = db_prints
        attached += 1
    db_calc = _json_text_or_none(db_payload.get("calc"))
    if db_calc:
        rec["db_calc_json"] = db_calc
        attached += 1
    return attached


def _prepare_action_record_for_storage(rec: Dict[str, Any], overwrite_from_raw: bool = True) -> Dict[str, Any]:
    """
    统一处理 Action 记录：
    - 解析 action_raw_json（可选覆盖 actions/print）
    - 提取并挂载 DB_JSON 协议字段（db_ts/db_*_json）
    - 保留 OriginalJson 便于排查
    """
    if not isinstance(rec, dict):
        return {}
    out = dict(rec)
    db_payload = None

    try:
        raw_txt = _safe_str(out.get("action_raw_json")).strip()
        if raw_txt:
            if "OriginalJson" not in out:
                out["OriginalJson"] = raw_txt
            parsed = _maybe_json_load(raw_txt)
            parsed = _strip_keys_recursive(parsed, _ACTION_STRIP_KEYS_LOWER)
            if isinstance(parsed, dict):
                lower_map = {(_safe_str(k).strip().lower()): k for k in parsed.keys()}
                if "actions" in lower_map:
                    if overwrite_from_raw or ("actions" not in out):
                        out["actions"] = parsed.get(lower_map["actions"])
                if "print" in lower_map:
                    if overwrite_from_raw or ("print" not in out):
                        out["print"] = parsed.get(lower_map["print"])
            elif isinstance(parsed, list):
                if overwrite_from_raw or ("actions" not in out):
                    out["actions"] = parsed
    except Exception:
        pass

    if "print" in out:
        db_payload = _extract_db_json_block(out.get("print"))
    if isinstance(db_payload, dict):
        _attach_db_payload_fields(out, db_payload)
        if ("actions" not in out) and ("actions" in db_payload):
            out["actions"] = db_payload.get("actions")
    return out


def _extract_data_as_dict(data_val: Any) -> Optional[Dict[str, Any]]:
    """
    RealTime 中常见的 data 形态：
    - dict
    - [ {..} ]  (单元素数组包了一层)
    - str 形式的 JSON（dict 或 list）
    目标：尽量抽出一个 dict，用于展开为列。
    """
    v = _maybe_json_load(data_val)
    if isinstance(v, dict):
        return v
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], dict):
        return v[0]
    return None


def _extract_action_as_dict(action_val: Any) -> Optional[Dict[str, Any]]:
    """
    actions 元素常见形态：
    - dict: {"pct":0.5,"side":"Y","type":"SETPOST"}
    - str:  '{"pct":0.5,"side":"Y","type":"SETPOST"}'
    - [ {..} ]: 单元素数组包一层
    目标：尽量抽出一个 dict，用于展开为列（pct/side/type 等）。
    """
    v = _maybe_json_load(action_val)
    if isinstance(v, dict):
        return v
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], dict):
        return v[0]
    return None


def _extract_yes_no_pct_from_actions(actions_val: Any) -> Tuple[Optional[Any], Optional[Any], bool]:
    """
    从 actions 中提取 Yes/No 两侧 pct：
    - 支持 actions 为 list[dict]、JSON 字符串
    - 支持外层是 {"actions":[...]} 的结构
    返回：(yes_pct, no_pct, found_any)
    """
    v = _maybe_json_load(actions_val)
    if isinstance(v, dict):
        lower_map = {(_safe_str(k).strip().lower()): k for k in v.keys()}
        if "actions" in lower_map:
            v = _maybe_json_load(v.get(lower_map["actions"]))
    if not isinstance(v, list):
        return None, None, False

    yes_pct: Optional[Any] = None
    no_pct: Optional[Any] = None
    found = False
    for item in v:
        if not isinstance(item, dict):
            continue
        side = _safe_str(_pick_ci_value(item, ("side", "position_side"))).strip().lower()
        pct_v = _pick_ci_value(item, ("pct", "percentage", "ratio", "value"))
        if side in {"yes", "y"}:
            yes_pct = pct_v
            found = True
        elif side in {"no", "n"}:
            no_pct = pct_v
            found = True
    return yes_pct, no_pct, found


def _pick_ci_value(d: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    """
    在 dict 中按大小写不敏感挑选第一个存在的 key 的值。
    """
    lower_map = {(_safe_str(k).strip().lower()): k for k in d.keys()}
    for kk in keys:
        k2 = kk.strip().lower()
        if k2 in lower_map:
            return d.get(lower_map[k2])
    return None


def _json_text_or_none(v: Any) -> Optional[str]:
    """
    把 dict/list 转成 JSON 文本（用于备份原始结构）；否则返回 None。
    """
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            return _safe_str(v)
    return None


def _extract_realtime_query_time(rt_raw: Any) -> Optional[str]:
    """
    从 RealTimeJson 内容中抽取 query_time。
    - 支持 JSON / `key:value` 文本
    - 优先取 dict 里的 query_time / query_time_beijing / ts_utc / NowTime（大小写不敏感）
    """
    if rt_raw is None or _safe_str(rt_raw).strip() == "":
        return None

    records, _ = _normalize_realtime_records(rt_raw)
    for r in records:
        if not isinstance(r, dict):
            continue
        lower_map = {(_safe_str(k).strip().lower()): k for k in r.keys()}
        for cand in ("query_time", "query_time_beijing", "ts_utc", "nowtime"):
            if cand in lower_map:
                val = r.get(lower_map[cand])
                sv = _safe_str(val).strip()
                if sv:
                    return sv
    return None


def _iso_utc_to_beijing_str(s: Optional[str]) -> Optional[str]:
    """
    把类似 2026-02-02T02:11:45Z / 2026-02-02T02:11:45+00:00 转成北京时间字符串：YYYY-MM-DD HH:MM:SS
    解析失败则返回 None。
    """
    if not s:
        return None
    text = _safe_str(s).strip()
    if not text:
        return None
    try:
        # fromisoformat 不支持 'Z'
        t = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            # 当作 UTC
            dt = dt.replace(tzinfo=timezone.utc)
        bj = dt.astimezone(timezone.utc).astimezone(timezone(timedelta(hours=8)))
        return bj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _normalize_to_records(raw: Any) -> Tuple[List[Any], int]:
    """
    解析并归一化成“记录列表”：
    - dict 作为 1 条记录
    - list 作为多条记录（逐元素展开）
    - text 支持 raw_decode 扫描多个 JSON
    返回: (records, parse_error_count)
    """
    errors = 0
    records: List[Any] = []

    if raw is None:
        return [], 0

    if isinstance(raw, dict):
        return [raw], 0

    if isinstance(raw, list):
        # 数组默认按多条记录处理
        return list(raw), 0

    text = _safe_str(raw).strip()
    if not text:
        return [], 0

    # 1) 优先：整段就是标准 JSON
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return list(obj), 0
            return [obj], 0
        except Exception:
            pass

    # 2) 扫描：多段 JSON 拼接
    for obj in _iter_json_from_text(text):
        if isinstance(obj, list):
            records.extend(list(obj))
        else:
            records.append(obj)

    if records:
        return records, 0

    # 3) 兜底：JSONL（逐行严格 json.loads）
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, list):
                records.extend(list(obj))
            else:
                records.append(obj)
            continue
        except Exception:
            errors += 1

    return records, errors


def _ensure_db_and_table(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA busy_timeout=5000;")
    # 统一元数据表（只保留这一张）：保存每张业务表每一列的 last_value + 更新时间
    # - 允许按 symbol 做维度（symbol='' 表示表级/全局）
    # - 旧版本可能存在 __meta_cols（无 symbol）或 __meta_cols_v2（有 symbol）
    #   这里做一次迁移/合并，最终保证只剩 __meta_cols 一张表
    def _table_exists(name: str) -> bool:
        row = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
        ).fetchone()
        return row is not None

    def _table_info(name: str) -> List[Tuple[Any, ...]]:
        return cur.execute(f'PRAGMA table_info("{name}")').fetchall()

    # 目标 schema：__meta_cols(table_name, symbol, col_name, last_value, updated_at_utc)
    def _create_meta_cols(name: str):
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{name}" (
                table_name TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT '',
                col_name TEXT NOT NULL,
                last_value TEXT,
                updated_at_utc TEXT,
                PRIMARY KEY (table_name, symbol, col_name)
            );
            """
        )

    meta_exists = _table_exists("__meta_cols")
    v2_exists = _table_exists("__meta_cols_v2")

    # 若只有 v2，直接改名为 __meta_cols（最干净）
    if (not meta_exists) and v2_exists:
        try:
            cur.execute('ALTER TABLE "__meta_cols_v2" RENAME TO "__meta_cols";')
            v2_exists = False
            meta_exists = True
        except Exception:
            # rename 失败就走 merge 逻辑
            meta_exists = False

    need_migrate = False
    if meta_exists:
        info = _table_info("__meta_cols")
        cols_lower = [(_safe_str(r[1]).strip().lower()) for r in info]  # r[1]=name
        pk_cols_lower = [(_safe_str(r[1]).strip().lower()) for r in info if int(r[5] or 0) > 0]  # r[5]=pk
        # 旧表没有 symbol，或 symbol 不在主键 => 需要迁移到新 schema
        if ("symbol" not in cols_lower) or ("symbol" not in pk_cols_lower):
            need_migrate = True
    else:
        need_migrate = True

    if need_migrate:
        # 统一迁移到新表，再替换
        _create_meta_cols("__meta_cols_new")
        # 1) 先搬旧 __meta_cols（无 symbol）到新表，symbol 填 ''
        if _table_exists("__meta_cols"):
            try:
                info = _table_info("__meta_cols")
                cols_lower = [(_safe_str(r[1]).strip().lower()) for r in info]
                if "symbol" in cols_lower:
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO "__meta_cols_new"(table_name, symbol, col_name, last_value, updated_at_utc)
                        SELECT table_name, symbol, col_name, last_value, updated_at_utc FROM "__meta_cols";
                        """
                    )
                else:
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO "__meta_cols_new"(table_name, symbol, col_name, last_value, updated_at_utc)
                        SELECT table_name, '', col_name, last_value, updated_at_utc FROM "__meta_cols";
                        """
                    )
            except Exception:
                pass
        # 2) 再合并 v2（有 symbol）
        if _table_exists("__meta_cols_v2"):
            try:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO "__meta_cols_new"(table_name, symbol, col_name, last_value, updated_at_utc)
                    SELECT table_name, symbol, col_name, last_value, updated_at_utc FROM "__meta_cols_v2";
                    """
                )
            except Exception:
                pass

        # 3) 替换旧表
        try:
            if _table_exists("__meta_cols"):
                cur.execute('DROP TABLE "__meta_cols";')
        except Exception:
            pass
        try:
            if _table_exists("__meta_cols_v2"):
                cur.execute('DROP TABLE "__meta_cols_v2";')
        except Exception:
            pass
        try:
            cur.execute('ALTER TABLE "__meta_cols_new" RENAME TO "__meta_cols";')
        except Exception:
            # 兜底：至少确保目标表存在
            _create_meta_cols("__meta_cols")
    else:
        # 已是新 schema：确保表存在
        _create_meta_cols("__meta_cols")
        # 如果还残留 v2，就合并进来并删掉
        if v2_exists:
            try:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO "__meta_cols"(table_name, symbol, col_name, last_value, updated_at_utc)
                    SELECT table_name, symbol, col_name, last_value, updated_at_utc FROM "__meta_cols_v2";
                    """
                )
            except Exception:
                pass
            try:
                cur.execute('DROP TABLE "__meta_cols_v2";')
            except Exception:
                pass

    conn.commit()


def _ensure_table(conn: sqlite3.Connection, table: str):
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{table}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saved_at_utc TEXT NOT NULL
        );
        """
    )
    cur.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_saved_at" ON "{table}"(saved_at_utc);')
    conn.commit()


def _get_existing_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    rows = cur.execute(f'PRAGMA table_info("{table}")').fetchall()
    # row: (cid, name, type, notnull, dflt_value, pk)
    return [r[1] for r in rows]


def _get_last_col_value(conn: sqlite3.Connection, table: str, col: str, symbol: str = "") -> Optional[str]:
    """
    获取某表某列的 last_value（用于单列去重比较）。
    """
    try:
        cur = conn.cursor()
        # 统一只读 __meta_cols（带 symbol 维度）
        row = cur.execute(
            'SELECT last_value FROM "__meta_cols" WHERE table_name = ? AND symbol = ? AND col_name = ? LIMIT 1',
            (table, symbol or "", col),
        ).fetchone()
        # 兼容：若按 symbol 没命中，尝试回退到 symbol=''
        if row is None and (symbol or "") != "":
            row = cur.execute(
                'SELECT last_value FROM "__meta_cols" WHERE table_name = ? AND symbol = ? AND col_name = ? LIMIT 1',
                (table, "", col),
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _set_last_col_value(conn: sqlite3.Connection, table: str, col: str, value: Optional[str], symbol: str = ""):
    """
    写入某表某列的 last_value（用于单列去重）。
    """
    try:
        cur = conn.cursor()
        # 统一只写 __meta_cols（带 symbol 维度）
        cur.execute(
            """
            INSERT INTO "__meta_cols"(table_name, symbol, col_name, last_value, updated_at_utc)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(table_name, symbol, col_name) DO UPDATE SET
                last_value=excluded.last_value,
                updated_at_utc=excluded.updated_at_utc;
            """,
            (table, symbol or "", col, value, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception:
        return


def _stable_json_fingerprint(obj: Any) -> str:
    """
    对 dict 做稳定序列化，用于去重指纹（保证 key 顺序一致）。
    """
    if obj is None:
        return ""
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return _safe_str(obj)


def _infer_symbol_from_records(records: List[Any]) -> str:
    """
    尽量从记录中推断 symbol（用于按标的维度写入 & 去重）。
    规则尽量保守：只取常见字段名，找到第一个非空字符串即返回。
    """
    # 尽量覆盖常见来源/命名（大小写不敏感）
    cand_keys = (
        "symbol",
        "ticker",
        "market",
        "market_symbol",
        "marketid",
        "market_id",
        "event",
        "eventid",
        "event_id",
        "eventslug",
        "event_slug",
        "slug",
        "contract",
        "contractid",
        "contract_id",
        "token",
        "tokenid",
        "token_id",
        "asset",
        "assetid",
        "asset_id",
        "id",
    )
    for r in records:
        if not isinstance(r, dict):
            continue
        lower_map = {(_safe_str(k).strip().lower()): k for k in r.keys()}
        for ck in cand_keys:
            if ck in lower_map:
                v = r.get(lower_map[ck])
                sv = _safe_str(v).strip()
                if sv:
                    return sv
        # 尝试从 data 里找 symbol
        if "data" in r:
            d = _extract_data_as_dict(r.get("data"))
            if isinstance(d, dict):
                lower_map2 = {(_safe_str(k).strip().lower()): k for k in d.keys()}
                for ck in cand_keys:
                    if ck in lower_map2:
                        v = d.get(lower_map2[ck])
                        sv = _safe_str(v).strip()
                        if sv:
                            return sv
    return ""


def _infer_symbol_from_inputs(rt_val: Any, yes_val: Any, no_val: Any) -> str:
    """
    若未显式传入 symbol，按 RealTime -> Yes -> No 的优先级尝试从输入 JSON 中推断。
    失败时返回空字符串。
    """
    for raw in (rt_val, yes_val, no_val):
        try:
            recs, _pe = _normalize_to_records(raw)
            sym = _infer_symbol_from_records(recs)
            if sym:
                return sym
        except Exception:
            continue
    return ""


def _ensure_columns(conn: sqlite3.Connection, table: str, col_names: List[str], existing_cols_cache: Dict[str, set]):
    """
    确保这些列存在；不存在就 ALTER TABLE ADD COLUMN。
    SQLite 的 ALTER TABLE ADD COLUMN 不能加 IF NOT EXISTS（旧版本），所以用 cache/查表规避。
    """
    if table not in existing_cols_cache:
        existing_cols_cache[table] = set(_get_existing_columns(conn, table))

    existing = existing_cols_cache[table]
    cur = conn.cursor()
    changed = False
    for c in col_names:
        if c in existing:
            continue
        cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{c}" TEXT;')
        existing.add(c)
        changed = True
    if changed:
        conn.commit()


def run_node(node):
    save_path = node['Inputs'][0].get('Context')
    save_name = node['Inputs'][1].get('Context')
    yes_raw = node['Inputs'][2].get('Context')
    no_raw = node['Inputs'][3].get('Context')
    rt_raw = node['Inputs'][4].get('Context')
    now_time = node['Inputs'][5].get('Context') if len(node.get('Inputs', [])) > 5 else None
    yes_ask = node['Inputs'][6].get('Context') if len(node.get('Inputs', [])) > 6 else None
    yes_bid = node['Inputs'][7].get('Context') if len(node.get('Inputs', [])) > 7 else None
    no_ask = node['Inputs'][8].get('Context') if len(node.get('Inputs', [])) > 8 else None
    no_bid = node['Inputs'][9].get('Context') if len(node.get('Inputs', [])) > 9 else None
    action_raw = node['Inputs'][10].get('Context') if len(node.get('Inputs', [])) > 10 else None
    yes_mode = node['Inputs'][11].get('Context') if len(node.get('Inputs', [])) > 11 else None
    no_mode = node['Inputs'][12].get('Context') if len(node.get('Inputs', [])) > 12 else None
    yes_qty = node['Inputs'][13].get('Context') if len(node.get('Inputs', [])) > 13 else None
    no_qty = node['Inputs'][14].get('Context') if len(node.get('Inputs', [])) > 14 else None
    symbol = node['Inputs'][15].get('Context') if len(node.get('Inputs', [])) > 15 else None

    save_path = _safe_str(save_path).strip()
    save_name = _safe_str(save_name).strip().replace("\n", "").replace("\r", "")
    symbol_s = _safe_str(symbol).strip()

    if not save_path:
        Outputs[0]['Context'] = "Error: SavePath 不能为空"
        Outputs[1]['Context'] = ""
        return Outputs

    if not save_name:
        Outputs[0]['Context'] = "Error: SaveName 不能为空"
        Outputs[1]['Context'] = ""
        return Outputs

    if not (save_name.lower().endswith(".db") or save_name.lower().endswith(".sqlite")):
        save_name += ".db"

    os.makedirs(save_path, exist_ok=True)
    full_path = os.path.join(save_path, save_name)

    try:
        conn = sqlite3.connect(full_path, timeout=5.0)
        try:
            _ensure_db_and_table(conn)
            tables = {
                "Yes": "Yes_Data",
                "No": "No_Data",
                "RealTime": "RealTime_Data",
                "Action": "Action_Data",
                "Metrics": "metrics",
            }
            for t in tables.values():
                _ensure_table(conn, t)

            cur = conn.cursor()
            existing_cols_cache: Dict[str, set] = {}
            # 单列去重：缓存 (table, col) -> last_value，减少频繁查库
            last_col_cache: Dict[Tuple[str, str, str], Optional[str]] = {}
            yes_val = yes_raw
            no_val = no_raw
            rt_val = rt_raw

            # 若未显式提供 symbol，则尽量从输入 JSON 推断（优先 RealTime，其次 Yes/No）
            if not symbol_s:
                symbol_s = _infer_symbol_from_inputs(rt_val, yes_val, no_val) or symbol_s

            # 统一批次时间：NowTime > RealTimeJson(JSON 内) > 当前 UTC
            now_time_s = _safe_str(now_time).strip()
            unified_query_time = now_time_s or _extract_realtime_query_time(rt_val) or datetime.now(timezone.utc).isoformat()
            # 保存时间与 query_time 对齐（字段名仍为 saved_at_utc）
            saved_at_utc = unified_query_time
            unified_query_time_beijing = _iso_utc_to_beijing_str(unified_query_time)

            def _save_one(source_label: str, raw_val: Any) -> Tuple[int, int, int]:
                """
                返回: (inserted, skipped, parse_err)
                """
                if raw_val is None or _safe_str(raw_val).strip() == "":
                    return 0, 0, 0
                table = tables[source_label]
                if source_label == "RealTime":
                    records, parse_err = _normalize_realtime_records(raw_val)
                else:
                    records, parse_err = _normalize_to_records(raw_val)
                valid_records = [r for r in records if r is not None]
                inserted = 0
                skipped = 0
                # Action_Data：不按 symbol 维度写入/去重（表内也不需要 symbol 列）
                is_action_table = source_label == "Action"
                # metrics 表：按 symbol 维度保存；同值列写 NULL；若整行都未变化则跳过
                is_metrics_table = source_label == "Metrics"
                # RealTime_Data.data_json：直接存入“整段 RealTimeJson 原始输入”（不加工）
                rt_raw_text: Optional[str] = None
                if source_label == "RealTime":
                    try:
                        if isinstance(raw_val, str):
                            rt_raw_text = raw_val
                        elif isinstance(raw_val, (dict, list)):
                            rt_raw_text = json.dumps(raw_val, ensure_ascii=False, separators=(",", ":"))
                        else:
                            rt_raw_text = _safe_str(raw_val)
                    except Exception:
                        rt_raw_text = _safe_str(raw_val)
                    # 不做 strip，尽量保留原始输入文本（用户要求“无需加工”）
                    rt_raw_text = _safe_str(rt_raw_text)

                def _norm_cmp(sql_val: Any) -> Optional[str]:
                    if sql_val is None:
                        return None
                    try:
                        return str(sql_val)
                    except Exception:
                        return _safe_str(sql_val)

                def _get_last_cached(col: str, sym: str = "") -> Optional[str]:
                    key = (table, sym or "", col)
                    if key not in last_col_cache:
                        last_col_cache[key] = _get_last_col_value(conn, table, col, symbol=(sym or ""))
                    return last_col_cache[key]

                def _set_last_cached(col: str, val: Optional[str], sym: str = ""):
                    _set_last_col_value(conn, table, col, val, symbol=(sym or ""))
                    last_col_cache[(table, sym or "", col)] = val

                # RealTime：允许把 data 里的列表拆成多条记录
                if source_label == "RealTime":
                    expanded: List[Any] = []
                    for r0 in valid_records:
                        if not isinstance(r0, dict):
                            expanded.append(r0)
                            continue
                        # 仅从 data 拆；data_json 在本组件语义中固定为“整段 RealTimeJson 原文”
                        payload = None
                        if "data" in r0:
                            payload = _maybe_json_load(r0.get("data"))

                        if isinstance(payload, list) and payload and all(isinstance(x, dict) for x in payload):
                            expanded.extend(payload)
                        else:
                            expanded.append(r0)
                    valid_records = expanded

                for r in valid_records:
                    try:
                        changed_meta: List[Tuple[str, Optional[str]]] = []
                        value_text_cmp: Optional[str] = None
                        if isinstance(r, dict):
                            # RealTime：按“整行指纹”去重，并剔除时间字段后全量写入（每个 symbol 一条记录）
                            if source_label == "RealTime":
                                # 以记录自身 symbol 为准（列表拆行场景会带 symbol）
                                row_symbol = _safe_str(r.get("symbol")).strip() or symbol_s or ""
                                r["symbol"] = row_symbol

                                # 剔除时间/易变字段（不入库）
                                stripped: Dict[str, Any] = {}
                                for k, v in r.items():
                                    kl = _safe_str(k).strip().lower()
                                    if kl in _RT_STRIP_KEYS_LOWER:
                                        continue
                                    stripped[_safe_str(k).strip()] = v
                                # 保底：至少保留 symbol
                                if "symbol" not in stripped:
                                    stripped["symbol"] = row_symbol
                                # 按需求：data_json 直接保存整段 RealTimeJson 原文（每条行都带一份）
                                if rt_raw_text is not None and rt_raw_text != "":
                                    stripped["data_json"] = rt_raw_text

                                # 指纹去重（按 symbol 维度）
                                # 注意：data_json 是“原始整段输入”，不参与去重/Meta（否则包含时间字段会导致重复写入）
                                fp_payload = {
                                    kk: _to_sqlite_value(vv)
                                    for kk, vv in stripped.items()
                                    if _safe_str(kk).strip().lower() != "data_json"
                                }
                                # 为了 meta 表更易读：指纹不再保存整段 JSON，而是保存短 hash
                                # （仍然基于稳定序列化，保证同内容同指纹）
                                fp_json = _stable_json_fingerprint(fp_payload)
                                fp = hashlib.sha1(_safe_str(fp_json).encode("utf-8", errors="ignore")).hexdigest()[:16]
                                if fp and fp == (_get_last_cached(_RT_DEDUPE_FP_COL, row_symbol) or ""):
                                    # 即使跳过，也记录本 symbol 最近一次处理时间
                                    try:
                                        # 表级刷新时间：统一写到 symbol=''，便于一眼查看每条边最新刷新时间
                                        _set_last_cached(_META_TABLE_UPDATED_COL, _safe_str(saved_at_utc).strip() or None, "")
                                    except Exception:
                                        pass
                                    # 需求：data_json 原文直接写入 __meta_cols（表级 symbol=''），即使跳过也更新
                                    try:
                                        if rt_raw_text is not None and rt_raw_text != "":
                                            _set_last_cached("data_json", rt_raw_text, "")
                                    except Exception:
                                        pass
                                    skipped += 1
                                    continue

                                # 全量写入（非时间字段）
                                seen_cols = set()
                                row_cols: List[str] = []
                                row_vals: List[Any] = []
                                for k, v in stripped.items():
                                    base = _sanitize_col_name(k)
                                    col = base
                                    if col in seen_cols:
                                        suffix = hashlib.sha1(_safe_str(k).encode("utf-8", errors="ignore")).hexdigest()[:8]
                                        col = f"{base}_{suffix}"
                                    seen_cols.add(col)
                                    row_cols.append(col)
                                    row_vals.append(_to_sqlite_value(v))

                                _ensure_columns(conn, table, row_cols, existing_cols_cache)
                                cols = ["saved_at_utc"] + row_cols
                                vals = [saved_at_utc] + row_vals

                                placeholders = ",".join(["?"] * len(cols))
                                col_sql = ",".join([f'"{c}"' for c in cols])
                                cur.execute(f'INSERT INTO "{table}"({col_sql}) VALUES({placeholders})', vals)
                                inserted += 1
                                if fp:
                                    _set_last_cached(_RT_DEDUPE_FP_COL, fp, row_symbol)
                                # 需求：data_json 原文直接写入 __meta_cols（表级 symbol=''）
                                try:
                                    if rt_raw_text is not None and rt_raw_text != "":
                                        _set_last_cached("data_json", rt_raw_text, "")
                                except Exception:
                                    pass
                                # 写入 RealTime 的“二级分类 meta”（按 symbol 细分到 price/market_cap_musd/...）
                                # 让 __meta_cols 呈现：table_name + symbol + col_name(指标名) + last_value
                                try:
                                    for mk, mv in fp_payload.items():
                                        mkl = _safe_str(mk).strip().lower()
                                        if mkl in {"symbol", "data_json"}:
                                            continue
                                        meta_col = _sanitize_col_name(mk)
                                        _set_last_cached(meta_col, _norm_cmp(mv), row_symbol)
                                except Exception:
                                    pass
                                try:
                                    # 表级刷新时间：统一写到 symbol=''，便于一眼查看每条边最新刷新时间
                                    _set_last_cached(_META_TABLE_UPDATED_COL, _safe_str(saved_at_utc).strip() or None, "")
                                except Exception:
                                    pass
                                continue

                            # 非 RealTime：注入 symbol（用于写入 & 去重）
                            # 重要：即使推断不到 symbol，也强制写入 symbol 列（至少让表结构包含 symbol，便于后续排查/补写）
                            if not is_action_table:
                                r["symbol"] = symbol_s or ""
                            else:
                                # Action_Data：即使上游携带 symbol，也不写入表（避免产生 symbol 列）
                                try:
                                    for _k in list(r.keys()):
                                        if _safe_str(_k).strip().lower() == "symbol":
                                            del r[_k]
                                except Exception:
                                    pass

                            # 注入统一时间（Action_Data 按你的要求仅保留动作快照字段，不写 query_time*）
                            if (not is_action_table) and unified_query_time:
                                r["query_time"] = unified_query_time
                            if (not is_action_table) and unified_query_time_beijing:
                                r["query_time_beijing"] = unified_query_time_beijing

                            # 注入盘口（由新增 inputs 提供，优先级最高）
                            if source_label == "Yes":
                                ya = _safe_str(yes_ask).strip()
                                yb = _safe_str(yes_bid).strip()
                                if ya:
                                    r["ask"] = ya
                                if yb:
                                    r["bid"] = yb
                            elif source_label == "No":
                                na = _safe_str(no_ask).strip()
                                nb = _safe_str(no_bid).strip()
                                if na:
                                    r["ask"] = na
                                if nb:
                                    r["bid"] = nb

                            # RealTime 的“拆行 + 去时间字段 + 整行指纹去重”已在上方专用分支处理；
                            # 这里进入的是非 RealTime 路径，保持逻辑简洁避免误读。

                            # Action_Data：仅保留动作快照需要的列
                            if source_label == "Action":
                                allowed_keys = _ACTION_ALLOWED_KEYS + ("print",)
                                compact: Dict[str, Any] = {}
                                for ak in allowed_keys:
                                    if ak in r:
                                        compact[ak] = r.get(ak)
                                # 统一列名：只存 Print
                                if "Print" not in compact and "print" in compact:
                                    compact["Print"] = compact.get("print")
                                if "print" in compact:
                                    del compact["print"]
                                r = compact

                            # 单列去重：只写“发生变化”的非易变列；易变列不参与触发判断
                            seen_cols = set()
                            changed_cols: List[str] = []
                            changed_vals: List[Any] = []
                            volatile_cols: List[str] = []
                            volatile_vals: List[Any] = []
                            metrics_has_change = False

                            for k, v in r.items():
                                base = _sanitize_col_name(k)
                                col = base
                                if col in seen_cols:
                                    # 同一条记录里列名冲突时加短 hash（仅用于列名去重）
                                    suffix = hashlib.sha1(_safe_str(k).encode("utf-8", errors="ignore")).hexdigest()[:8]
                                    col = f"{base}_{suffix}"
                                seen_cols.add(col)

                                sql_val = _to_sqlite_value(v)
                                kl = _safe_str(k).strip().lower()
                                is_db_null = is_action_table and (k in _ACTION_DB_FIELDS) and (v is None)
                                # Action_Data：像 print/originaljson/action_raw_json 这类字段只用于展示/排查，
                                # 即使变化也不应触发插入新行（否则 day_to_end 等日志变化会导致重复写入）
                                is_volatile = (
                                    (kl in _DEDUPE_IGNORE_KEYS_LOWER)
                                    or (is_action_table and kl in _ACTION_FP_IGNORE_KEYS_LOWER)
                                    or is_db_null
                                )
                                if is_volatile:
                                    volatile_cols.append(col)
                                    volatile_vals.append(sql_val)
                                    continue

                                cur_v = _norm_cmp(sql_val)
                                # Action_Data：不分 symbol
                                last_v = _get_last_cached(col, "" if is_action_table else (symbol_s or ""))
                                if is_metrics_table and cur_v == last_v:
                                    # metrics 规则：同值列显式写 NULL，避免重复值污染
                                    changed_cols.append(col)
                                    changed_vals.append(None)
                                    continue
                                if cur_v == last_v:
                                    continue
                                metrics_has_change = True
                                changed_cols.append(col)
                                changed_vals.append(sql_val)
                                changed_meta.append((col, cur_v))

                            # 没有任何“非易变列”的变化 => 整行跳过
                            if not changed_cols:
                                skipped += 1
                                continue
                            if is_metrics_table and (not metrics_has_change):
                                skipped += 1
                                continue

                            row_cols = changed_cols + volatile_cols
                            row_vals = changed_vals + volatile_vals
                            _ensure_columns(conn, table, row_cols, existing_cols_cache)

                            cols = ["saved_at_utc"] + row_cols
                            vals = [saved_at_utc] + row_vals
                        else:
                            # 非 dict：落到 value_text（单列去重）
                            sql_val = _to_sqlite_value(r)
                            value_text_cmp = _norm_cmp(sql_val)
                            if value_text_cmp == _get_last_cached("value_text", "" if is_action_table else (symbol_s or "")):
                                skipped += 1
                                continue

                            # 非 dict：落到 value_text
                            need_cols = ["value_text"]
                            if is_action_table:
                                _ensure_columns(conn, table, need_cols, existing_cols_cache)
                                cols = ["saved_at_utc", "value_text"]
                                vals = [saved_at_utc, sql_val]
                            else:
                                # 同样强制带 symbol 列（可能为空字符串）
                                need_cols.append("symbol")
                                _ensure_columns(conn, table, need_cols, existing_cols_cache)
                                cols = ["saved_at_utc", "value_text", "symbol"]
                                vals = [saved_at_utc, sql_val, symbol_s or ""]

                        placeholders = ",".join(["?"] * len(cols))
                        col_sql = ",".join([f'"{c}"' for c in cols])
                        cur.execute(f'INSERT INTO "{table}"({col_sql}) VALUES({placeholders})', vals)
                        inserted += 1
                        if isinstance(r, dict):
                            # Action_Data：不写 symbol，也不按 symbol 做 meta 去重
                            row_sym = "" if is_action_table else (_safe_str(r.get("symbol")).strip() or symbol_s or "")
                            for c, vv in changed_meta:
                                _set_last_cached(c, vv, row_sym)
                        else:
                            _set_last_cached("value_text", value_text_cmp, "" if is_action_table else (symbol_s or ""))
                    except Exception:
                        parse_err += 1
                        skipped += 1
                        continue

                # 表级更新时间：只要这一“路”有输入，就记录一次最新批次时间
                # 目的：即使本批次全 Skipped，也能在 __meta_cols 里看到该表最近一次处理时间
                try:
                    _set_last_cached(
                        _META_TABLE_UPDATED_COL,
                        _safe_str(saved_at_utc).strip() or None,
                        # 统一写到 symbol=''（表级），避免 meta 表按 symbol 膨胀
                        "",
                    )
                except Exception:
                    pass

                return inserted, skipped, parse_err

            y_ins, y_skip, y_err = _save_one("Yes", yes_val)
            n_ins, n_skip, n_err = _save_one("No", no_val)
            r_ins, r_skip, r_err = _save_one("RealTime", rt_val)
            # Action_Data：收集两路 action 记录后复用 _save_one("Action", ...)
            action_records: List[Any] = []
            action_parse_err = 0
            metrics_records: List[Any] = []
            metrics_parse_err = 0
            rt_context_fields = _extract_realtime_context_fields(rt_val)
            action_dbg = {
                "rt_records_seen": 0,
                "action_input_records_seen": 0,
                "db_json_detected_rt": 0,
                "db_json_detected_action_input": 0,
                "db_fields_attached_total": 0,
                "action_records_before_filter": 0,
                "action_records_after_filter": 0,
                "action_batch_fp_equal_last": False,
                "action_batch_fp_preview": "",
                "action_last_batch_fp_preview": "",
            }

            def _append_metrics_record(m: Any, source: str, ts_hint: Optional[str], symbol_hint: str):
                mm = _extract_metrics_dict(m)
                if not isinstance(mm, dict) or not mm:
                    return
                rec = dict(mm)
                rec["metric_source"] = source
                mts = _safe_str(rec.get("ts")).strip() or _safe_str(ts_hint).strip()
                if mts:
                    rec["ts"] = mts
                rec["symbol"] = _safe_str(symbol_hint).strip() or symbol_s or ""
                metrics_records.append(rec)

            action_print_hint: Any = None

            # 1) RealTimeJson.actions
            if rt_val is not None and _safe_str(rt_val).strip() != "":
                rt_records, pe = _normalize_realtime_records(rt_val)
                action_parse_err += pe
                metrics_parse_err += pe
                for rt in [x for x in rt_records if x is not None]:
                    if not isinstance(rt, dict):
                        continue
                    action_dbg["rt_records_seen"] += 1
                    rt_symbol = _safe_str(rt.get("symbol")).strip() or symbol_s or ""
                    rt_time_hint = _safe_str(rt.get("query_time")).strip() or unified_query_time
                    _append_metrics_record(rt.get("metrics"), "RealTimeJson.metrics", rt_time_hint, rt_symbol)
                    actions = rt.get("actions")
                    if not isinstance(actions, list):
                        continue
                    rt_db_payload = _extract_db_json_block(rt.get("print"))
                    if isinstance(rt_db_payload, dict):
                        action_dbg["db_json_detected_rt"] += 1
                        _append_metrics_record(
                            rt_db_payload.get("calc"),
                            "RealTimeJson.dbjson.calc",
                            rt_time_hint,
                            rt_symbol,
                        )
                    if action_print_hint is None:
                        action_print_hint = rt.get("print")
                    rt_time = _safe_str(rt.get("query_time")).strip() or unified_query_time
                    snap = _build_action_snapshot(
                        {"actions": actions, "print": rt.get("print")},
                        print_hint=rt.get("print"),
                    )
                    if snap:
                        for ctx_k, ctx_v in rt_context_fields.items():
                            if ctx_k not in snap:
                                snap[ctx_k] = ctx_v
                        action_records.append(snap)

            # 2) Action input
            if action_raw is not None and _safe_str(action_raw).strip() != "":
                a_records, pe = _normalize_to_records(action_raw)
                action_parse_err += pe
                metrics_parse_err += pe
                for act in [x for x in a_records if x is not None]:
                    action_dbg["action_input_records_seen"] += 1
                    act_symbol = _safe_str(act.get("symbol")).strip() if isinstance(act, dict) else (symbol_s or "")
                    _append_metrics_record(
                        act.get("metrics") if isinstance(act, dict) else None,
                        "ActionInput.metrics",
                        unified_query_time,
                        act_symbol,
                    )
                    act_db_payload = _extract_db_json_block(act.get("print")) if isinstance(act, dict) else None
                    if isinstance(act_db_payload, dict):
                        action_dbg["db_json_detected_action_input"] += 1
                        _append_metrics_record(
                            act_db_payload.get("calc"),
                            "ActionInput.dbjson.calc",
                            unified_query_time,
                            act_symbol,
                        )
                    if action_print_hint is None and isinstance(act, dict):
                        action_print_hint = act.get("print")
                    snap = _build_action_snapshot(act, print_hint=action_print_hint)
                    if snap:
                        for ctx_k, ctx_v in rt_context_fields.items():
                            if ctx_k not in snap:
                                snap[ctx_k] = ctx_v
                        action_records.append(snap)

            # 3) YesMode/NoMode/YesQty/NoQty inputs -> 写入 Action_Data
            # - 任意字段非空即写入 1 条记录（列名与 Input 名保持一致，便于直接查表）
            ym = _safe_str(yes_mode).strip()
            nm = _safe_str(no_mode).strip()
            yq = _safe_str(yes_qty).strip()
            nq = _safe_str(no_qty).strip()
            if ym or nm or yq or nq:
                action_records.append(
                    {
                        "YesMode": ym or None,
                        "NoMode": nm or None,
                        "YesQty": yq or None,
                        "NoQty": nq or None,
                    }
                )
            # 合并同批 action 快照：每列取“最后一个非空值”，最终只保留一条记录
            action_dbg["action_records_before_filter"] = len(action_records)
            if action_records:
                merged: Dict[str, Any] = {}
                for rec in action_records:
                    if not isinstance(rec, dict):
                        continue
                    for kk in _ACTION_ALLOWED_KEYS:
                        if kk not in rec:
                            continue
                        vv = rec.get(kk)
                        if vv is None:
                            continue
                        if isinstance(vv, str) and vv.strip() == "":
                            continue
                        merged[kk] = vv
                if "Print" not in merged and action_print_hint is not None and _safe_str(action_print_hint).strip() != "":
                    merged["Print"] = action_print_hint
                for ctx_k, ctx_v in rt_context_fields.items():
                    if ctx_k not in merged:
                        merged[ctx_k] = ctx_v
                action_records = [merged] if merged else []
            action_dbg["action_records_after_filter"] = len(action_records)

            if action_records:
                # Action：整批去重（与上一时间点相同则完全不写入）
                def _action_batch_fingerprint(recs: List[Any]) -> str:
                    payloads: List[Any] = []
                    for rec in recs:
                        if isinstance(rec, dict):
                            fp_payload: Dict[str, Any] = {}
                            for k in _ACTION_ALLOWED_KEYS:
                                if k not in rec:
                                    continue
                                v = rec.get(k)
                                if v is None:
                                    continue
                                if isinstance(v, str) and v.strip() == "":
                                    continue
                                fp_payload[_safe_str(k).strip()] = _to_sqlite_value(v)
                            payloads.append(fp_payload)
                        else:
                            payloads.append(_to_sqlite_value(rec))
                    return _stable_json_fingerprint(payloads)

                batch_fp = _action_batch_fingerprint(action_records)
                # Action_Data：不按 symbol 维度去重（永久使用空 symbol）
                last_batch_fp = _get_last_col_value(conn, tables["Action"], _ACT_BATCH_DEDUPE_FP_COL, symbol="")
                action_dbg["action_batch_fp_preview"] = _safe_str(batch_fp)[:32]
                action_dbg["action_last_batch_fp_preview"] = _safe_str(last_batch_fp)[:32]
                action_dbg["action_batch_fp_equal_last"] = bool(batch_fp and (last_batch_fp or "") == batch_fp)
                if batch_fp and (last_batch_fp or "") == batch_fp:
                    a_ins, a_skip, a_err = 0, len(action_records), action_parse_err
                else:
                    a_ins, a_skip, a_err = _save_one("Action", action_records)
                    a_err += action_parse_err
                    # 仅在“确实尝试处理了这批 action”后更新批次指纹
                    if batch_fp:
                        _set_last_col_value(conn, tables["Action"], _ACT_BATCH_DEDUPE_FP_COL, batch_fp, symbol="")
            else:
                a_ins, a_skip, a_err = 0, 0, action_parse_err

            if metrics_records:
                m_ins, m_skip, m_err = _save_one("Metrics", metrics_records)
                m_err += metrics_parse_err
            else:
                m_ins, m_skip, m_err = 0, 0, metrics_parse_err

            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        result_text = (
            f"Saved to SQLite: {full_path}\n"
            f"Tables:\n"
            f"  - Yes  -> Yes_Data (Inserted={y_ins}, Skipped={y_skip}, Errors={y_err})\n"
            f"  - No   -> No_Data  (Inserted={n_ins}, Skipped={n_skip}, Errors={n_err})\n"
            f"  - RT   -> RealTime_Data (Inserted={r_ins}, Skipped={r_skip}, Errors={r_err})\n"
            f"  - ACT  -> Action_Data (Inserted={a_ins}, Skipped={a_skip}, Errors={a_err})\n"
            f"  - MET  -> metrics (Inserted={m_ins}, Skipped={m_skip}, Errors={m_err})\n"
            f"ActionDebug:\n"
            f"  - rt_records_seen={action_dbg.get('rt_records_seen')}, action_input_records_seen={action_dbg.get('action_input_records_seen')}\n"
            f"  - db_json_detected_rt={action_dbg.get('db_json_detected_rt')}, db_json_detected_action_input={action_dbg.get('db_json_detected_action_input')}\n"
            f"  - db_fields_attached_total={action_dbg.get('db_fields_attached_total')}\n"
            f"  - action_records_before_filter={action_dbg.get('action_records_before_filter')}, action_records_after_filter={action_dbg.get('action_records_after_filter')}\n"
            f"  - batch_fp_equal_last={action_dbg.get('action_batch_fp_equal_last')}\n"
            f"  - batch_fp={action_dbg.get('action_batch_fp_preview')}, last_batch_fp={action_dbg.get('action_last_batch_fp_preview')}\n"
        )
        Outputs[0]['Context'] = result_text
        Outputs[1]['Context'] = full_path
        return Outputs

    except Exception as e:
        Outputs[0]['Context'] = f"Error: 写入 SQLite 失败: {e}\nDB: {full_path}"
        Outputs[1]['Context'] = full_path
        return Outputs


