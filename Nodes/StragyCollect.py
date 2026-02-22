import ast
import json
import os
import re

# 输入输出数量
OutPutNum = 1
InPutNum = 1

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
    "组件功能：抓取指定目录下所有 Stragy_*.py 节点的 FunctionIntroduction 中“组件功能：”这一行并汇总输出。\n\n"
    "输入：\n"
    "- InputFolderPath: 目录路径（例如 F:/linkO/Nodes）\n\n"
    "输出：\n"
    "- OutPut1: JSON 字符串，包含 files/items\n"
)

for o in Outputs:
    o["Kind"] = "String"
for i in Inputs:
    i["Kind"] = "String"

Inputs[0]["name"] = "InputFolderPath"
Inputs[0]["Isnecessary"] = True
Inputs[0]["IsLabel"] = False
Inputs[0]["Kind"] = "String_FilePath"

Outputs[0]["name"] = "OutPut1"
Outputs[0]["Kind"] = "String"


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
        return None
    for line in intro_text.splitlines():
        s = line.strip()
        if s.startswith("组件功能："):
            return s
    m = re.search(r"组件功能：[^\n\r]*", intro_text)
    if m:
        return m.group(0).strip()
    return None


def run_node(node):
    folder_path = None
    try:
        folder_path = (node.get("Inputs") or [])[0].get("Context")
    except Exception:
        folder_path = None

    if not isinstance(folder_path, str) or not folder_path.strip():
        Outputs[0]["Context"] = json.dumps(
            {"error": "InputFolderPath 为空", "files": 0, "items": []},
            ensure_ascii=False,
            indent=2,
        )
        return Outputs

    folder_path = folder_path.strip()
    if not os.path.isdir(folder_path):
        Outputs[0]["Context"] = json.dumps(
            {"error": f"目录不存在：{folder_path}", "files": 0, "items": []},
            ensure_ascii=False,
            indent=2,
        )
        return Outputs

    items = []
    for name in sorted(os.listdir(folder_path)):
        if not (name.startswith("Stragy_") and name.endswith(".py")):
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
        feature_line = _extract_feature_line(intro_text or "")
        if feature_line:
            items.append({"file": name, "feature": feature_line})

    result = {
        "files": len(items),
        "items": items,
    }
    Outputs[0]["Context"] = json.dumps(result, ensure_ascii=False, indent=2)
    return Outputs

