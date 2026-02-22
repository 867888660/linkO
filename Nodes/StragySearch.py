import ast
import os
import re

# 输入输出数量
OutPutNum = 3
InPutNum = 2

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
    "组件功能：输入关键词和目录路径，检索目录下所有 Stragy_*.py 文件，"
    "返回文件名或 FunctionIntroduction 中包含关键词的节点说明，并解析可填写的 inputs。\n\n"
    "输入：\n"
    "- SearchKeyword: 关键搜索词\n"
    "- InputFolderPath: 目录路径（例如 F:/linkO/Nodes）\n\n"
    "输出：\n"
    "- OutPut1: 命中文件的组件功能行（组件功能：...）\n"
    "- OutPut2: 从 FunctionIntroduction 的 yaml.inputs 解析出的 input1/input2... 文本\n"
    "- OutPut3: 命中的策略名称（文件名）\n"
)

for o in Outputs:
    o["Kind"] = "String"
for i in Inputs:
    i["Kind"] = "String"

Inputs[0]["name"] = "SearchKeyword"
Inputs[0]["Isnecessary"] = True
Inputs[0]["IsLabel"] = False

Inputs[1]["name"] = "InputFolderPath"
Inputs[1]["Isnecessary"] = True
Inputs[1]["IsLabel"] = False
Inputs[1]["Kind"] = "String_FilePath"

Outputs[0]["name"] = "OutPut1"
Outputs[0]["Kind"] = "String"
Outputs[1]["name"] = "OutPut2"
Outputs[1]["Kind"] = "String"
Outputs[2]["name"] = "OutPut3"
Outputs[2]["Kind"] = "String"


def _eval_str_expr(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Str):
        return node.s
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _eval_str_expr(node.left)
        right = _eval_str_expr(node.right)
        if isinstance(left, str) and isinstance(right, str):
            return left + right
    return None


def _extract_intro_text(py_text: str):
    try:
        tree = ast.parse(py_text, mode="exec")
    except Exception:
        return None

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "FunctionIntroduction":
                    return _eval_str_expr(node.value)
    return None


def _extract_feature_line(intro_text: str):
    if not isinstance(intro_text, str) or not intro_text.strip():
        return ""
    for line in intro_text.splitlines():
        s = line.strip()
        if s.startswith("组件功能："):
            return s
    m = re.search(r"组件功能：[^\n\r]*", intro_text)
    if m:
        return m.group(0).strip()
    return ""


def _extract_inputs_text(intro_text: str):
    if not isinstance(intro_text, str) or not intro_text.strip():
        return ""

    m = re.search(r"```yaml\s*(.*?)```", intro_text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    yaml_text = m.group(1)

    lines = yaml_text.splitlines()
    in_inputs = False
    inputs_indent = 0
    current = None
    rows = []
    i = 0

    while i < len(lines):
        line = lines[i].rstrip("\n\r")
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if not stripped:
            i += 1
            continue

        if not in_inputs:
            if re.match(r"^\s*inputs\s*:\s*$", line):
                in_inputs = True
                inputs_indent = indent
            i += 1
            continue

        # 输入段结束：遇到与 inputs 同级或更外层的其他字段
        if indent <= inputs_indent and re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*:\s*$", stripped):
            if current:
                rows.append(current)
                current = None
            break

        name_match = re.match(r"^\s*-\s*name\s*:\s*(.+?)\s*$", line)
        if name_match:
            if current:
                rows.append(current)
            current = {"name": name_match.group(1).strip(), "description": ""}
            i += 1
            continue

        if current:
            desc_match = re.match(r"^\s*description\s*:\s*(.*?)\s*$", line)
            if desc_match:
                desc_value = desc_match.group(1).strip()
                # 处理 YAML 多行块标记（| / > / |-/ >- / |+ / >+）
                if re.match(r"^[|>][-+]?$", desc_value):
                    block_lines = []
                    base_indent = indent
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].rstrip("\n\r")
                        next_stripped = next_line.strip()
                        next_indent = len(next_line) - len(next_line.lstrip(" "))
                        if next_stripped and next_indent <= base_indent:
                            break
                        if next_stripped:
                            block_lines.append(next_stripped)
                        j += 1
                    current["description"] = " ".join(block_lines).strip()
                    i = j
                    continue
                current["description"] = desc_value

        i += 1

    if current:
        rows.append(current)

    # 业务约定：跳过第一个输入（通常是 UseData），从 Inputs[1] 开始输出
    effective_rows = rows[1:] if len(rows) > 1 else []
    parts = []
    for idx, item in enumerate(effective_rows, start=1):
        desc = item.get("description") or item.get("name") or ""
        parts.append(f"input{idx}{desc}")
    return "\n".join(parts)


def _normalize_text(value: str):
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _calc_name_score(keyword: str, filename: str):
    """
    更强容错匹配：
    - 忽略大小写
    - 兼容带/不带 .py
    - 兼容带路径输入（仅取 basename）
    - 忽略常见分隔符（_ - 空格 . / \）
    """
    kw_raw = keyword.strip()
    kw_base = os.path.basename(kw_raw.replace("\\", "/"))
    kw_stem = os.path.splitext(kw_base)[0]

    file_base = filename
    file_stem = os.path.splitext(file_base)[0]

    kw_cf = kw_stem.casefold()
    file_cf = file_stem.casefold()
    kw_norm = _normalize_text(kw_stem)
    file_norm = _normalize_text(file_stem)

    # 精确命中（不区分大小写）
    if kw_cf == file_cf:
        return 120

    # 忽略分隔符后的精确命中
    if kw_norm and kw_norm == file_norm:
        return 110

    # 关键词包含前缀 Stragy_ 与否的兼容
    file_no_prefix = re.sub(r"^stragy_?", "", file_cf)
    file_no_prefix_norm = _normalize_text(file_no_prefix)
    if kw_cf == file_no_prefix:
        return 105
    if kw_norm and kw_norm == file_no_prefix_norm:
        return 100

    # 包含匹配（中等分）
    if kw_cf and (kw_cf in file_cf or file_cf in kw_cf):
        return 80
    if kw_norm and (kw_norm in file_norm or file_norm in kw_norm):
        return 75

    return 0


def run_node(node):
    keyword = None
    folder_path = None
    try:
        keyword = (node.get("Inputs") or [])[0].get("Context")
        folder_path = (node.get("Inputs") or [])[1].get("Context")
    except Exception:
        keyword = None
        folder_path = None

    if not isinstance(keyword, str) or not keyword.strip():
        Outputs[0]["Context"] = "SearchKeyword 为空"
        Outputs[1]["Context"] = ""
        Outputs[2]["Context"] = ""
        return Outputs

    if not isinstance(folder_path, str) or not folder_path.strip():
        Outputs[0]["Context"] = "InputFolderPath 为空"
        Outputs[1]["Context"] = ""
        Outputs[2]["Context"] = ""
        return Outputs

    keyword = keyword.strip()
    folder_path = folder_path.strip()
    if not os.path.isdir(folder_path):
        Outputs[0]["Context"] = f"目录不存在：{folder_path}"
        Outputs[1]["Context"] = ""
        Outputs[2]["Context"] = ""
        return Outputs

    matches = []

    for name in sorted(os.listdir(folder_path)):
        if not (name.startswith("Stragy") and name.endswith(".py")):
            continue

        file_path = os.path.join(folder_path, name)
        if not os.path.isfile(file_path):
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                continue

        intro_text = _extract_intro_text(text)
        if not intro_text:
            continue

        name_score = _calc_name_score(keyword, name)
        intro_hit = keyword.casefold() in intro_text.casefold()
        score = name_score + (40 if intro_hit else 0)
        if score > 0:
            matches.append({"file": name, "intro": intro_text, "score": score})

    if not matches:
        Outputs[0]["Context"] = ""
        Outputs[1]["Context"] = ""
        Outputs[2]["Context"] = ""
        return Outputs

    # 取匹配得分最高的策略
    selected = sorted(matches, key=lambda x: x["score"], reverse=True)[0]

    intro_text = selected["intro"]
    feature_line = _extract_feature_line(intro_text)
    inputs_text = _extract_inputs_text(intro_text)
    Outputs[0]["Context"] = feature_line
    Outputs[1]["Context"] = inputs_text
    Outputs[2]["Context"] = selected["file"]
    return Outputs
