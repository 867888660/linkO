import ast
import json
import re

# ===== 节点定义 =====
OutPutNum = 2
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
        "IsLabel": True,
    }
    for i in range(InPutNum)
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]

FunctionIntroduction = (
    "组件功能：Model_Stragy 首个模板（非沙箱执行）。\n\n"
    "说明：\n"
    "- Inputs[0] 固定为 UseData，支持 JSON 对象或多行 key=value / key: value 文本\n"
    "- UseData 键名解析支持大小写/下划线/连字符容错，可在策略中直接 UseData['xxxx'] 读取\n"
    "- Inputs[1..] 作为调试参数（模板示例：Side/Pct/Wake/Reason）\n"
    "- 输出统一为 FunctionJson + IsCodeOk\n"
)

# ===== 端口设置 =====
for o in Outputs:
    o["Kind"] = "String"
for i in Inputs:
    i["Kind"] = "String"

Inputs[0]["name"] = "UseData"
Inputs[0]["Isnecessary"] = True
Inputs[0]["IsLabel"] = False

Inputs[1]["name"] = "DebugSide"
Inputs[1]["Isnecessary"] = False
Inputs[1]["IsLabel"] = False

Inputs[2]["name"] = "DebugPct"
Inputs[2]["Kind"] = "Num"
Inputs[2]["Isnecessary"] = False
Inputs[2]["IsLabel"] = False

Inputs[3]["name"] = "DebugWake"
Inputs[3]["Isnecessary"] = False
Inputs[3]["IsLabel"] = False

Inputs[4]["name"] = "DebugReason"
Inputs[4]["Isnecessary"] = False
Inputs[4]["IsLabel"] = False

Outputs[0]["name"] = "FunctionJson"
Outputs[0]["Kind"] = "String"
Outputs[1]["name"] = "IsCodeOk"
Outputs[1]["Kind"] = "Boolean"


def _norm_key(key: str) -> str:
    if key is None:
        return ""
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


class _UseDataProxy:
    """
    支持 UseData['xxxx'] 的容错取值：
    - 先精确匹配
    - 再走规范化匹配（忽略大小写、下划线、连字符等）
    """

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

    def __getitem__(self, key):
        real_key = self._resolve_key(key)
        if real_key is None:
            raise KeyError(key)
        return self._raw[real_key]

    def get(self, key, default=None):
        real_key = self._resolve_key(key)
        if real_key is None:
            return default
        return self._raw.get(real_key, default)

    def has(self, key):
        return self._resolve_key(key) is not None

    def to_dict(self):
        return dict(self._raw)


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

    # 1) 优先按 JSON 对象解析
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj, None
    except Exception:
        pass

    # 2) 退化到 key=value / key:value
    kv = _parse_kv_text(s)
    if kv:
        return kv, None
    return None, "UseData 解析失败（需要 JSON 对象或 key=value 文本）"


def _to_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        if isinstance(value, str):
            s = value.strip().replace(",", "").replace("_", "")
            if s.endswith("%"):
                return float(s[:-1]) / 100.0
            return float(s)
        return float(value)
    except Exception:
        return float(default)


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return bool(default)


def _run_strategy(usedata: _UseDataProxy, debug_params: dict):
    """
    这是首个模板策略，后续你可以直接改这里的逻辑。
    """
    actions = []
    logs = []
    wake_reason = None

    day_to_end = _to_float(
        usedata.get("day_to_end", usedata.get("days_to_end", 9999)),
        default=9999,
    )
    side = str(debug_params.get("DebugSide", "Yes") or "Yes").strip().capitalize()
    if side not in ("Yes", "No"):
        side = "Yes"

    pct = _to_float(debug_params.get("DebugPct", 0.25), default=0.25)
    if pct > 1.0 and pct <= 100.0:
        pct = pct / 100.0
    if pct < 0:
        pct = 0.0
    if pct > 1:
        pct = 1.0

    should_wake = _to_bool(debug_params.get("DebugWake", False), default=False)
    custom_reason = str(debug_params.get("DebugReason", "") or "").strip()

    # ===== 模板策略逻辑（可直接替换）=====
    if day_to_end <= 2:
        actions.append({"type": "SETPOS", "side": side, "pct": pct})
        logs.append(f"触发建仓：day_to_end={day_to_end}, side={side}, pct={pct}")
        if should_wake:
            wake_reason = custom_reason or f"临近到期，day_to_end={day_to_end}"
            actions.append({"type": "WAKE"})
    else:
        logs.append(f"不触发：day_to_end={day_to_end} (>2)")

    return {"actions": actions, "print": logs, "wake_reason": wake_reason}


def run_node(node):
    try:
        node_inputs = node.get("Inputs") or []
        usedata_raw = node_inputs[0].get("Context") if len(node_inputs) > 0 else None
        usedata_dict, err = _parse_usedata(usedata_raw)
        if err:
            out_json = {"actions": [], "print": [f"[UseDataError] {err}"], "wake_reason": None}
            Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
            Outputs[1]["Boolean"] = False
            return Outputs

        # 收集 Inputs[1..] 调试参数，键名优先使用输入端口名
        debug_params = {}
        for i in range(1, len(node_inputs)):
            ipt = node_inputs[i] or {}
            key = ipt.get("name") or ipt.get("Id") or f"Input{i + 1}"
            value = ipt.get("Context")
            # Num 口可能只写在 Num 字段
            if value in (None, "") and ipt.get("Num") is not None:
                value = ipt.get("Num")
            debug_params[key] = value

        usedata = _UseDataProxy(usedata_dict)
        out_json = _run_strategy(usedata, debug_params)
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = True
        return Outputs
    except Exception as e:
        out_json = {"actions": [], "print": [f"[RuntimeError] {type(e).__name__}: {e}"], "wake_reason": None}
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = False
        return Outputs
