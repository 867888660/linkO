import ast
import json
import keyword
import difflib
import re
from datetime import datetime

# **Define the number of outputs and inputs** 输入节点与输出节点的数量
OutPutNum = 2
InPutNum = 2

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
    "组件功能：条件单脚本（两步走：静态检查 + 受控执行），输出统一 JSON 与 IsCodeOk。\n\n"
    "参数：\n"
    "```yaml\n"
    "inputs:\n"
    "  - name: UseData\n"
    "    type: string\n"
    "    required: true\n"
    "    description: JSON对象（dict）或多行 key=value/key: value；其键会被注入为脚本运行时变量（数值字段会自动数值化，空 bid/ask/qty 等会给安全默认，避免比较时报错）\n"
    "  - name: code\n"
    "    type: string\n"
    "    required: true\n"
    "    description: 条件单脚本（仅支持受控语法与白名单函数，详见 syntax_rules）\n"
    "syntax_rules:\n"
    "  allow_calls:\n"
    "    - SetPos(side, pct)\n"
    "    - AwakeAi(reason)\n"
    "    - Print(text)\n"
    "    - str/int/float/bool/len/abs/min/max/round/sum\n"
    "    - clamp(x, lo, hi)\n"
    "    - coalesce(a, b, ...)\n"
    "    - has(name)\n"
    "    - get(name, default)\n"
    "    - parse_ts(x)\n"
    "    - seconds_between(a, b)\n"
    "  allow_syntax:\n"
    "    - 赋值/比较/逻辑表达式\n"
    "    - if/elif/else\n"
    "    - 下标访问 x[i] / d['k']\n"
    "    - 列表/字典/元组字面量\n"
    "  disallow_syntax:\n"
    "    - import/from import\n"
    "    - def/class/lambda\n"
    "    - for/while\n"
    "    - with/try/except\n"
    "    - 属性访问（obj.attr / obj.method()）\n"
    "  notes:\n"
    "    - SetPos 的 pct 支持 0~1（也兼容 0~100 百分比）\n"
    "    - 变量必须来自 UseData 或脚本内临时变量\n"
    "outputs:\n"
    "  - name: FunctionJson\n"
    "    type: string\n"
    "    description: 统一输出 JSON（actions/print/wake_reason）\n"
    "  - name: IsCodeOk\n"
    "    type: boolean\n"
    "    description: 语法正确 + 规则合规 + 在当前 UseData 下可运行\n"
    "```\n"
)

# ==== 端口定义 ====
for o in Outputs:
    o["Kind"] = "String"
for i in Inputs:
    i["Kind"] = "String"

Inputs[0]["name"] = "UseData"
Inputs[0]["Isnecessary"] = True
Inputs[0]["IsLabel"] = False

Inputs[1]["name"] = "code"
Inputs[1]["Isnecessary"] = True
Inputs[1]["IsLabel"] = False

Outputs[0]["name"] = "FunctionJson"
Outputs[0]["Kind"] = "String"
Outputs[1]["name"] = "IsCodeOk"
Outputs[1]["Kind"] = "Boolean"


_ALLOWED_CALLS = {"SetPos", "AwakeAi", "Print"}
_DEPRECATED_CALLS = {"Buy", "Sell"}
_ALLOWED_TEMP_VARS = {"gate_status", "reason"}
_SAFE_HELPER_FUNC_NAMES = {"clamp", "coalesce", "has", "get", "parse_ts", "seconds_between"}

# 允许的“安全内置函数”（用于类型转换/数值处理等）
# 注意：运行沙箱里 __builtins__ 为空，因此必须同时：
# - 静态检查允许调用这些函数名
# - 运行时把这些函数注入 env
_SAFE_BUILTIN_FUNCS = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "len": len,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sum": sum,
}
_DISALLOWED_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.For,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.Attribute,  # 避免 __class__/__globals__ 等逃逸面
    ast.Global,
    ast.Nonlocal,
)

_FULLWIDTH_PUNCT_MAP = {
    "，": ",",
    "。": ".",
    "、": ",",
    "；": ";",
    "：": ":",
    "（": "(",
    "）": ")",
    "【": "[",
    "】": "]",
    "｛": "{",
    "｝": "}",
    "！": "!",
    "？": "?",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
}


def _is_obvious_placeholder_or_noise(line: str) -> bool:
    """
    识别明显的“占位/噪声”行（如 ...[truncated 123 chars]），
    这类内容常来自聊天窗口复制或日志截断，不应参与 Python 语法解析。
    """
    if not isinstance(line, str):
        return False
    s = line.strip()
    if not s:
        return False
    low = s.lower()

    # 常见截断占位符
    if re.match(r"^\.\.\.\s*\[truncated[^\]]*\]\s*$", low):
        return True
    if re.match(r"^\[truncated[^\]]*\]\s*$", low):
        return True
    if re.match(r"^\.\.\.\s*\(truncated[^)]*\)\s*$", low):
        return True

    # 仅由分隔符组成的“装饰行”
    if re.match(r"^[=\-_*~]{5,}$", s):
        return True

    return False


def _normalize_name(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())

def _is_valid_identifier(name: str) -> bool:
    try:
        if not isinstance(name, str):
            return False
        if "__" in name:
            return False
        if not name.isidentifier():
            return False
        if keyword.iskeyword(name):
            return False
        return True
    except Exception:
        return False


def _strip_inline_comment(line: str) -> str:
    """去掉行内注释（# 或 //），尽量不误伤引号内内容。"""
    if not isinstance(line, str):
        return ""
    s = line
    out = []
    q = None
    esc = False
    i = 0
    while i < len(s):
        ch = s[i]
        if esc:
            out.append(ch)
            esc = False
            i += 1
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            i += 1
            continue
        if q:
            out.append(ch)
            if ch == q:
                q = None
            i += 1
            continue
        if ch in ("'", '"'):
            out.append(ch)
            q = ch
            i += 1
            continue
        # comment begin
        if ch == "#":
            break
        if ch == "/" and i + 1 < len(s) and s[i + 1] == "/":
            break
        out.append(ch)
        i += 1
    return "".join(out).strip()

def _replace_fullwidth_punct_outside_quotes(line: str):
    """
    将常见全角标点替换为半角（仅替换引号外内容，避免误伤字符串）。
    returns: (new_line, changed: bool)
    """
    if not isinstance(line, str) or not line:
        return line, False
    out = []
    q = None
    esc = False
    changed = False
    for ch in line:
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            continue
        if q:
            out.append(ch)
            if ch == q:
                q = None
            continue
        if ch in ("'", '"'):
            out.append(ch)
            q = ch
            continue
        if ch in _FULLWIDTH_PUNCT_MAP:
            out.append(_FULLWIDTH_PUNCT_MAP[ch])
            changed = True
        else:
            out.append(ch)
    return "".join(out), changed

def _looks_like_python_code_line(line: str) -> bool:
    """
    粗略判断该行是否像 Python 代码。
    用于把“策略说明”等非代码行自动注释掉，增强鲁棒性。
    """
    if not isinstance(line, str):
        return False
    s = line.strip()
    if not s:
        return True
    if s.startswith("#"):
        return True
    if _is_obvious_placeholder_or_noise(s):
        return False
    # 常见语句开头
    if re.match(r"^(if|elif|else|return|pass|break|continue|try|except|finally|with)\b", s):
        return True
    # 含中文/全角说明文本：除非明显是代码行，否则优先当作“说明行”注释掉
    # 典型场景：第一行写“交易思路：……(day_to_end<=2)…”
    if re.search(r"[\u4e00-\u9fff]", s):
        # 允许“中文注释行”已经在前面被 # 覆盖
        # 允许的代码行：以白名单函数或 if/elif/else 开头（上面已处理）
        if re.match(r"^(Buy|Sell|SetPos|AwakeAi|Print)\s*\(", s):
            return True
        # 允许“纯赋值”形式：foo = 1（左侧必须是合法标识符）
        if re.match(r"^[A-Za-z_]\w*\s*=", s):
            return True
        return False
    # 常见函数调用开头（白名单函数）
    # 注意：Buy/Sell 已废弃，但仍视为“代码行”，以便在静态检查阶段给出更明确的迁移报错
    if re.match(r"^(Buy|Sell|SetPos|AwakeAi|Print)\s*\(", s):
        return True
    # 简单赋值/比较/逻辑
    if any(tok in s for tok in ("=", "==", ">=", "<=", ">", "<", " and ", " or ", " not ")):
        return True
    # 常见表达式形式（收紧：避免把 "...[truncated...]" 这类噪声误判成代码）
    if re.match(r"^[A-Za-z_]\w*\s*\(", s):
        return True
    if re.match(r"^[A-Za-z_]\w*\s*\[", s):
        return True
    if re.match(r"^[\[\(\{].*[\]\)\}]$", s) and re.search(r"[A-Za-z_]\w*", s):
        return True
    return False

def _extract_code_fence(text: str):
    """
    从 ```...``` 中提取第一段代码（优先 python）。
    """
    if not isinstance(text, str):
        return None
    s = text.replace("\r\n", "\n")
    if "```" not in s:
        return None
    # 匹配 ```python ... ``` 或 ``` ... ```
    blocks = re.findall(r"```(?:\s*python)?\s*\n([\s\S]*?)\n```", s, flags=re.IGNORECASE)
    if blocks:
        return blocks[0].strip("\n")
    blocks2 = re.findall(r"```\s*\n([\s\S]*?)\n```", s)
    if blocks2:
        return blocks2[0].strip("\n")
    return None

def _sanitize_code_input(code: str):
    """
    对用户输入的“混合文本”做清洗，尽量转为可解析的 Python 代码。
    - 支持从 ```python``` 代码块中抽取
    - 将非代码行自动注释掉（避免中文说明导致 SyntaxError）
    - 将常见全角标点在引号外替换为半角
    returns: (sanitized_code, warnings: list[str])
    """
    warnings = []
    if not isinstance(code, str):
        return "", ["code 类型不是 string"]
    raw = code.replace("\r\n", "\n").replace("\r", "\n")
    raw = raw.lstrip("\ufeff")  # BOM

    fenced = _extract_code_fence(raw)
    if fenced is not None and fenced.strip():
        warnings.append("检测到 ```...``` 代码块：已自动提取代码内容")
        raw = fenced

    # 去掉常见前缀行（例如 “Python代码:” / “# Python 条件代码”）
    raw = re.sub(r"^\s*(python\s*代码|python\s*条件代码|#\s*python\s*条件代码|#\s*python\s*代码)\s*[:：]?\s*$",
                 "", raw, flags=re.IGNORECASE | re.MULTILINE)

    out_lines = []
    for idx, line in enumerate(raw.split("\n"), start=1):
        # 把 “交易思路：...” 这类非代码行变成注释
        if not _looks_like_python_code_line(line):
            stripped = line.strip()
            if stripped:
                out_lines.append("# " + stripped)
                warnings.append(f"第{idx}行非代码文本已注释")
            else:
                out_lines.append("")
            continue

        new_line, changed = _replace_fullwidth_punct_outside_quotes(line)
        if changed:
            warnings.append(f"第{idx}行全角标点已替换为半角")
        out_lines.append(new_line)

    sanitized = "\n".join(out_lines).strip()
    return sanitized, warnings


def _parse_value(text: str):
    """把 value 从字符串解析成 Python 基础类型；解析失败就返回原始字符串。"""
    if text is None:
        return None
    v = str(text).strip()
    if v == "":
        return ""

    low = v.lower()
    if low in ("none", "null"):
        return None
    if low in ("true",):
        return True
    if low in ("false",):
        return False

    # 数字（支持科学计数、下划线、千分位）
    num_s = v.replace("_", "")
    if re.fullmatch(r"[+\-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:[eE][+\-]?\d+)?", num_s):
        num_s = num_s.replace(",", "")
        try:
            if re.fullmatch(r"[+\-]?\d+", num_s):
                return int(num_s)
            return float(num_s)
        except Exception:
            pass
    if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?", num_s):
        try:
            if re.fullmatch(r"[+\-]?\d+", num_s):
                return int(num_s)
            return float(num_s)
        except Exception:
            pass

    # 带引号字符串
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        try:
            return ast.literal_eval(v)
        except Exception:
            return v[1:-1]

    return v


def _is_numeric_like_key(key: str) -> bool:
    """
    判断某个 UseData 字段是否“像数字字段”。
    目的：把空值/字符串数值做强健数值化，避免脚本里出现 'str' 和 'float' 比较导致 TypeError。
    """
    if not isinstance(key, str) or not key:
        return False
    k = key.strip().lower()
    if not k:
        return False
    # 显式字段
    if k in ("day_to_end", "days_to_end"):
        return True
    # 常见量化字段名片段
    tokens = (
        "qty",
        "bid",
        "ask",
        "price",
        "avgprice",
        "avg_price",
        "mcap",
        "depth",
        "usd",
        "pct",
        "percent",
    )
    return any(t in k for t in tokens)


def _default_numeric_value_for_key(key: str):
    """
    对空值给“方向更安全”的默认值：
    - bid: 0.0（避免误触发 > 阈值）
    - ask: 1.0（避免误触发 < 阈值，市场价格通常在 0~1）
    - 其它：0.0
    """
    k = (key or "").strip().lower()
    if "ask" in k:
        return 1.0
    if "bid" in k:
        return 0.0
    if "qty" in k:
        return 0.0
    return 0.0


def _coerce_numeric_like_fields(d: dict):
    """
    对 dict 中“像数字”的字段做强健数值化：
    - 允许 "1,234.5" / "1_234.5" / "0.12%" 这类文本
    - 空值/解析失败 -> 方向安全默认值（见 _default_numeric_value_for_key）
    """
    if not isinstance(d, dict) or not d:
        return d

    for key, val in list(d.items()):
        if not isinstance(key, str):
            continue
        if not _is_numeric_like_key(key):
            continue

        default_v = _default_numeric_value_for_key(key)

        # already numeric (avoid bool)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            continue

        if val is None:
            d[key] = default_v
            continue

        # normalize string
        if isinstance(val, str):
            s = val.strip()
            if s == "":
                d[key] = default_v
                continue

            percent = False
            if s.endswith("%"):
                percent = True
                s = s[:-1].strip()

            s2 = s.replace(",", "").replace("_", "")
            try:
                # 尽量保留整数（例如 Mcap 这类大整数，避免 float 精度损失）
                if re.fullmatch(r"[+\-]?\d+", s2):
                    num = int(s2)
                else:
                    num = float(s2)
            except Exception:
                d[key] = default_v
                continue

            if percent:
                num = num / 100.0

            d[key] = float(num) if not isinstance(num, int) else num
            continue

        # other types: try float, else default
        try:
            d[key] = float(val)
        except Exception:
            d[key] = default_v

    return d


def _parse_kv_text(s: str):
    """解析多行 key=value / key: value 文本为 dict。"""
    out = {}
    if not isinstance(s, str):
        return out
    lines = s.splitlines()
    for raw in lines:
        line = _strip_inline_comment(raw).strip()
        if not line:
            continue
        # 兼容全角分隔符：： ＝
        # 注意：这里是 UseData 配置行（通常不含复杂字符串），直接替换能显著提升鲁棒性
        line = line.replace("：", ":").replace("＝", "=")
        # 跳过描述行
        if ("=" not in line) and (":" not in line):
            continue
        # 允许 “key = value” 或 “key: value”
        if "=" in line:
            k, v = line.split("=", 1)
        else:
            k, v = line.split(":", 1)
        key = k.strip()
        if not key:
            continue
        val = _parse_value(v.strip())
        out[key] = val
    return out


def _parse_usedata(raw):
    # 输入通常是 string（JSON 或多行 key=value），也兼容直接 dict
    def _add_common_aliases(d: dict):
        """
        为常用字段增加“兼容别名”，提升脚本变量可用性。
        注意：只在别名不存在时补充，绝不覆盖原字段。
        """
        if not isinstance(d, dict):
            return d
        # ---- NowTime 兼容 ----
        now = None
        for k in ("NowTime", "now_time", "current_time", "query_time_beijing", "QueryTime", "time"):
            if k in d and d.get(k) not in (None, ""):
                now = d.get(k)
                break
        if now not in (None, ""):
            for alias in ("NowTime", "now_time", "current_time"):
                d.setdefault(alias, now)

        # ---- Enddate 兼容 ----
        end = None
        for k in ("Enddate", "endDate", "end_date", "EndDate"):
            if k in d and d.get(k) not in (None, ""):
                end = d.get(k)
                break
        if end not in (None, ""):
            d.setdefault("Enddate", end)
            d.setdefault("end_date", end)
            d.setdefault("endDate", end)

        # ---- day_to_end 兼容 ----
        dto = None
        for k in ("day_to_end", "days_to_end", "dayToEnd"):
            if k in d and d.get(k) not in (None, ""):
                dto = d.get(k)
                break
        if dto not in (None, ""):
            d.setdefault("day_to_end", dto)
            d.setdefault("days_to_end", dto)

        # ---- 数值字段鲁棒性：空值/字符串数值 -> 数字 + 默认值 ----
        _coerce_numeric_like_fields(d)
        return d

    if isinstance(raw, dict):
        return _add_common_aliases(raw), None
    if raw is None:
        return None, "UseData 为空"
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, "UseData 为空字符串"
        # 1) JSON dict
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return _add_common_aliases(obj), None
        except Exception:
            pass
        # 2) 多行 key=value / key: value
        kv = _parse_kv_text(s)
        if kv:
            return _add_common_aliases(kv), None
        return None, "UseData 解析失败（需要 JSON 对象或多行 key=value 文本）"
    return None, f"UseData 类型不支持：{type(raw)}"


class _NameRewriter(ast.NodeTransformer):
    def __init__(self, mapping):
        self.mapping = mapping or {}

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load) and node.id in self.mapping:
            return ast.copy_location(ast.Name(id=self.mapping[node.id], ctx=node.ctx), node)
        return node


def _static_check_and_fix(code, usedata_keys):
    """
    returns:
      {
        ok: bool,
        syntax_ok: bool,
        rules_ok: bool,
        errors: [str],
        warnings: [str],
        fixed_code: str or None,
      }
    """
    errors = []
    warnings = []
    fixed_code = None

    if not isinstance(code, str) or not code.strip():
        return {
            "ok": False,
            "syntax_ok": False,
            "rules_ok": False,
            "errors": ["code 为空"],
            "warnings": [],
            "fixed_code": None,
        }

    # 0) 输入清洗（增强鲁棒性：允许混合文本/全角标点/代码块）
    sanitized_code, sanitize_warnings = _sanitize_code_input(code)

    # 1) 语法检查（先尝试原文，再尝试清洗后）
    tree = None
    syntax_ok = False
    parse_err = None
    try:
        tree = ast.parse(code, mode="exec")
        syntax_ok = True
    except SyntaxError as e:
        parse_err = e

    if (not syntax_ok) and isinstance(sanitized_code, str) and sanitized_code.strip():
        try:
            tree = ast.parse(sanitized_code, mode="exec")
            syntax_ok = True
            fixed_code = sanitized_code  # 将清洗后的代码视为修复版本
            warnings.extend(sanitize_warnings)
        except SyntaxError as e2:
            parse_err = e2

    if not syntax_ok:
        e = parse_err
        return {
            "ok": False,
            "syntax_ok": False,
            "rules_ok": False,
            "errors": [f"语法错误：{e.msg} (line {e.lineno})"],
            "warnings": sanitize_warnings,
            "fixed_code": None,
        }

    # 2) 规则检查 + 变量纠错（可选）
    # 注意：Buy/Sell 已废弃，但仍加入 allowed_names，避免报成“未知变量”，转而给更明确的迁移提示
    usedata_keys = set(usedata_keys or set())
    # 允许的“临时变量”：默认放开（只要不覆盖 UseData 字段/内置函数/允许调用函数）
    assigned_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if isinstance(node.id, str) and node.id and ("__" not in node.id) and node.id.isidentifier():
                assigned_names.add(node.id)

    reserved_names = (
        set(_ALLOWED_CALLS)
        | set(_SAFE_BUILTIN_FUNCS.keys())
        | set(_SAFE_HELPER_FUNC_NAMES)
        | set(_DEPRECATED_CALLS)
    )
    allowed_names = (
        usedata_keys
        | set(_ALLOWED_TEMP_VARS)
        | assigned_names
        | set(_ALLOWED_CALLS)
        | set(_SAFE_BUILTIN_FUNCS.keys())
        | set(_SAFE_HELPER_FUNC_NAMES)
        | set(_DEPRECATED_CALLS)
        | {"True", "False", "None"}
    )

    unknown_load_names = set()

    for node in ast.walk(tree):
        if isinstance(node, _DISALLOWED_NODES):
            errors.append(f"禁止语法：{type(node).__name__}")

        if isinstance(node, ast.Name):
            if "__" in node.id:
                errors.append(f"禁止使用双下划线变量名：{node.id}")
                continue

            if isinstance(node.ctx, ast.Load):
                if node.id not in allowed_names and not keyword.iskeyword(node.id):
                    unknown_load_names.add(node.id)

            if isinstance(node.ctx, ast.Store):
                # 赋值允许“临时变量”，但禁止覆盖 UseData 字段和保留名（函数名/安全内置等）
                if node.id in usedata_keys:
                    errors.append(f"禁止覆盖 UseData 变量：{node.id}")
                elif node.id in reserved_names:
                    errors.append(f"禁止覆盖保留名：{node.id}")

        if isinstance(node, ast.Call):
            # 只允许直接调用函数名：SetPos/AwakeAi/Print
            if not isinstance(node.func, ast.Name):
                errors.append("只允许直接调用函数名（禁止 obj.method() 等）")
            else:
                fn = node.func.id
                if fn in _DEPRECATED_CALLS:
                    errors.append(f"函数已废弃：{fn}（请改用 SetPos(side, pct)，pct 为 0~1 仓位）")
                elif (fn not in _ALLOWED_CALLS) and (fn not in _SAFE_BUILTIN_FUNCS) and (fn not in _SAFE_HELPER_FUNC_NAMES):
                    allow_list = sorted(_ALLOWED_CALLS | set(_SAFE_BUILTIN_FUNCS.keys()) | set(_SAFE_HELPER_FUNC_NAMES))
                    errors.append(f"禁止调用函数：{fn}（只允许：{allow_list}）")

    # 变量纠错（仅对 Load 的未知变量尝试替换）
    mapping = {}
    if unknown_load_names and usedata_keys:
        # 0) 常用别名：时间字段（NowTime）优先映射，避免误报“未知变量”
        if "NowTime" in usedata_keys:
            for bad in ("now_time", "current_time", "nowtime", "time_now", "TimeNow"):
                if bad in unknown_load_names:
                    mapping[bad] = "NowTime"
                    warnings.append(f"变量纠错：{bad} -> NowTime")
            unknown_load_names = {n for n in unknown_load_names if n not in mapping}

        norm_to_real = {}
        for k in usedata_keys:
            nk = _normalize_name(k)
            norm_to_real.setdefault(nk, []).append(k)

        usedata_norms = list(norm_to_real.keys())
        for bad in sorted(unknown_load_names):
            nb = _normalize_name(bad)
            # 先尝试完全归一化匹配
            exact = norm_to_real.get(nb) or []
            if len(exact) == 1:
                mapping[bad] = exact[0]
                warnings.append(f"变量纠错：{bad} -> {exact[0]}")
                continue

            # 再做模糊匹配（difflib）
            close = difflib.get_close_matches(nb, usedata_norms, n=2, cutoff=0.86)
            if len(close) == 1 and len(norm_to_real.get(close[0], [])) == 1:
                real = norm_to_real[close[0]][0]
                mapping[bad] = real
                warnings.append(f"变量纠错(模糊)：{bad} -> {real}")
            else:
                sugg = []
                for c in close:
                    sugg.extend(norm_to_real.get(c, []))
                sugg = sugg[:5]
                errors.append(f"未知变量：{bad}；建议：{sugg or sorted(list(usedata_keys))[:5]}")

    if mapping:
        # 重新生成 fixed_code
        try:
            new_tree = _NameRewriter(mapping).visit(tree)
            ast.fix_missing_locations(new_tree)
            fixed_code = ast.unparse(new_tree)
            # 用纠错后的代码再次校验语法 & 规则（避免引入新问题）
            tree = ast.parse(fixed_code, mode="exec")
        except Exception as e:
            errors.append(f"变量纠错失败：{e}")
            fixed_code = None

    rules_ok = len(errors) == 0
    return {
        "ok": syntax_ok and rules_ok,
        "syntax_ok": syntax_ok,
        "rules_ok": rules_ok,
        "errors": errors,
        "warnings": warnings,
        "fixed_code": fixed_code,
    }


def _sandbox_run(code, usedata):
    actions = []
    prints = []
    wake_reason = None

    def Print(text):
        prints.append(str(text))

    def AwakeAi(reason):
        nonlocal wake_reason
        wake_reason = None if reason is None else str(reason)
        actions.append({"type": "WAKE"})

    def _parse_side_pct(args, kwargs):
        # 支持：SetPos(0.75) / SetPos("No", 0.75) / SetPos(side="No", pct=0.75)
        side = kwargs.get("side", None)
        pct = kwargs.get("pct", None)
        if pct is None:
            pct = kwargs.get("percent", None)

        if len(args) == 1 and pct is None and side is None:
            pct = args[0]
        elif len(args) >= 2 and pct is None and side is None:
            side, pct = args[0], args[1]
        elif len(args) == 1 and side is None and pct is not None:
            side = args[0]

        if side is None:
            side = "Yes"
        side = str(side).strip().capitalize()
        if side not in ("Yes", "No"):
            raise ValueError(f"side 必须是 Yes/No，当前：{side}")

        try:
            pct_f = float(pct)
        except Exception:
            raise ValueError(f"pct 必须是数字，当前：{pct}")

        # 兼容 75 / 75.0 表示 75%
        if pct_f > 1.0 and pct_f <= 100.0:
            pct_f = pct_f / 100.0

        if pct_f < 0.0 or pct_f > 1.0:
            raise ValueError(f"pct 必须在 0~1 之间（或 0~100 表示百分比），当前：{pct_f}")

        return side, float(pct_f)

    def SetPos(*args, **kwargs):
        side, pct = _parse_side_pct(args, kwargs)
        actions.append({"type": "SETPOS", "side": side, "pct": pct})

    def clamp(x, lo, hi):
        x_f = float(x)
        lo_f = float(lo)
        hi_f = float(hi)
        if lo_f > hi_f:
            lo_f, hi_f = hi_f, lo_f
        if x_f < lo_f:
            return lo_f
        if x_f > hi_f:
            return hi_f
        return x_f

    def coalesce(*vals):
        for v in vals:
            if v is not None and v != "":
                return v
        return None

    def has(name):
        if not isinstance(name, str):
            return False
        return name in (usedata or {})

    def get(name, default=None):
        if not isinstance(name, str):
            return default
        if name in (usedata or {}):
            return (usedata or {}).get(name)
        return default

    def parse_ts(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        s = str(value).strip()
        if not s:
            raise ValueError("parse_ts 输入为空")
        normalized = s.replace("T", " ")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return float(datetime.fromisoformat(normalized).timestamp())
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return float(datetime.strptime(normalized, fmt).timestamp())
            except Exception:
                pass
        raise ValueError(f"parse_ts 无法解析时间：{value}")

    def seconds_between(a, b):
        return float(parse_ts(b) - parse_ts(a))

    # 仅注入可作为变量名的 UseData key
    env = {"__builtins__": {}}
    for k, v in (usedata or {}).items():
        if isinstance(k, str) and re.match(r"^[A-Za-z_]\w*$", k) and (not keyword.iskeyword(k)):
            env[k] = v

    env.update({
        "Print": Print,
        "AwakeAi": AwakeAi,
        "SetPos": SetPos,
        "clamp": clamp,
        "coalesce": coalesce,
        "has": has,
        "get": get,
        "parse_ts": parse_ts,
        "seconds_between": seconds_between,
    })
    # 注入安全内置函数（沙箱内 __builtins__ 为空，必须显式提供）
    env.update(_SAFE_BUILTIN_FUNCS)

    try:
        tree = ast.parse(code, mode="exec")
        compiled = compile(tree, "<Normal_SandboxRun>", "exec")
        exec(compiled, env, env)
        return True, {"actions": actions, "print": prints, "wake_reason": wake_reason}, None
    except Exception as e:
        # 运行错误也返回统一 JSON，便于前端展示
        prints.append(f"[RuntimeError] {type(e).__name__}: {e}")
        return False, {"actions": actions, "print": prints, "wake_reason": wake_reason}, str(e)


def run_node(node):
    usedata_raw = None
    code = None
    try:
        usedata_raw = (node.get("Inputs") or [])[0].get("Context")
        code = (node.get("Inputs") or [None, None])[1].get("Context")
    except Exception:
        pass

    usedata, usedata_err = _parse_usedata(usedata_raw)
    if usedata_err:
        out_json = {"actions": [], "print": [f"[UseDataError] {usedata_err}"], "wake_reason": None}
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = False
        return Outputs

    usedata_keys_for_code = {k for k in (usedata or {}).keys() if _is_valid_identifier(k)}
    check = _static_check_and_fix(code, usedata_keys_for_code)
    if not check["syntax_ok"] or not check["rules_ok"]:
        # 静态检查失败：直接判错，并把错误塞到 print，保持统一 JSON 结构
        msgs = []
        for w in check["warnings"]:
            msgs.append(f"[LintWarn] {w}")
        for er in check["errors"]:
            msgs.append(f"[LintError] {er}")
        out_json = {"actions": [], "print": msgs or ["[LintError] Unknown"], "wake_reason": None}
        Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
        Outputs[1]["Boolean"] = False
        return Outputs

    run_code = check["fixed_code"] if check["fixed_code"] else code
    exec_ok, out_json, _err = _sandbox_run(run_code, usedata)
    Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
    Outputs[1]["Boolean"] = bool(exec_ok)
    return Outputs


