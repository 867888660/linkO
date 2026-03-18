import importlib.util
import json
import os
import uuid

# 输入：策略文件夹 + 策略名称 + UseData + Input1..Input13
OutPutNum = 2
InPutNum = 16

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
    "组件功能：策略调度沙箱。根据“策略文件夹 + 策略名称”动态加载策略文件，"
    "并透传 UseData 与 Input1~Input13 到策略的 run_node(node)，输出统一 FunctionJson 与 CodeIsOk。\n\n"
    "参数：\n"
    "```yaml\n"
    "inputs:\n"
    "  - name: StrategyFolder\n"
    "    type: string\n"
    "    required: true\n"
    "    description: 策略目录绝对路径（例如 F:/linkO/Nodes）\n"
    "  - name: StrategyName\n"
    "    type: string\n"
    "    required: true\n"
    "    description: 策略文件名，支持带/不带 .py（例如 Stragy_Fllow_Stock_Value）\n"
    "  - name: UseData\n"
    "    type: string\n"
    "    required: true\n"
    "    description: 透传给策略的外部数据（通常 JSON 字符串）\n"
    "  - name: Input1\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input2\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input3\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input4\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input5\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input6\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input7\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input8\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input9\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input10\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input11\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input12\n"
    "    type: string\n"
    "    required: false\n"
    "  - name: Input13\n"
    "    type: string\n"
    "    required: false\n"
    "outputs:\n"
    "  - name: FunctionJson\n"
    "    type: string\n"
    "  - name: CodeIsOk\n"
    "    type: boolean\n"
    "```\n"
)

for o in Outputs:
    o["Kind"] = "String"
for i in Inputs:
    i["Kind"] = "String"

Inputs[0]["name"] = "StrategyFolder"
Inputs[0]["Kind"] = "String_FilePath"
Inputs[1]["name"] = "StrategyName"
Inputs[2]["name"] = "UseData"

for idx in range(3, InPutNum):
    Inputs[idx]["name"] = f"Input{idx - 2}"
    Inputs[idx]["Isnecessary"] = False

Outputs[0]["name"] = "FunctionJson"
Outputs[0]["Kind"] = "String"
Outputs[1]["name"] = "CodeIsOk"
Outputs[1]["Kind"] = "Boolean"


def _make_error_output(message: str):
    out_json = {"actions": [], "print": [message], "wake_reason": None}
    Outputs[0]["Context"] = json.dumps(out_json, ensure_ascii=False, indent=2)
    Outputs[1]["Boolean"] = False
    return Outputs


def _to_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _resolve_strategy_file(folder: str, name: str):
    if not folder:
        return None, "StrategyFolder 为空"
    if not name:
        return None, "StrategyName 为空"
    if not os.path.isdir(folder):
        return None, f"StrategyFolder 不存在：{folder}"

    raw = name.strip()
    base = os.path.basename(raw)
    stem, ext = os.path.splitext(base)
    if ext.lower() == ".py":
        candidates = [base]
    else:
        candidates = [base + ".py"]

    if stem and not stem.lower().startswith("stragy_"):
        candidates.append("Stragy_" + stem + ".py")

    dedup = []
    seen = set()
    for c in candidates:
        if c not in seen:
            dedup.append(c)
            seen.add(c)

    for filename in dedup:
        p = os.path.normpath(os.path.join(folder, filename))
        if os.path.isfile(p):
            return p, None

    return None, f"策略文件未找到：{name}（目录：{folder}）"


def _load_strategy_module(py_path: str):
    module_name = f"sandbox_strategy_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, py_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载策略模块：{py_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_forward_node(node_inputs):
    forward_inputs = []

    # Input0: UseData
    src_usedata = node_inputs[2] if len(node_inputs) > 2 else {}
    forward_inputs.append(
        {
            "Id": "Input1",
            "name": "UseData",
            "Kind": "String",
            "Context": src_usedata.get("Context"),
            "Num": src_usedata.get("Num"),
            "Isnecessary": True,
            "IsLabel": False,
            "Link": 0,
        }
    )

    # Input1..Input13
    for k in range(1, 14):
        src_idx = 2 + k
        src = node_inputs[src_idx] if len(node_inputs) > src_idx else {}
        forward_inputs.append(
            {
                "Id": f"Input{k + 1}",
                "name": f"Input{k}",
                "Kind": src.get("Kind"),
                "Context": src.get("Context"),
                "Num": src.get("Num"),
                "Isnecessary": False,
                "IsLabel": False,
                "Link": 0,
            }
        )

    return {"Inputs": forward_inputs}


def _extract_strategy_outputs(result):
    if not isinstance(result, list) or len(result) < 2:
        return None, None, "策略 run_node 返回结构不合法（应返回至少2个输出）"
    out0 = result[0] if isinstance(result[0], dict) else {}
    out1 = result[1] if isinstance(result[1], dict) else {}
    func_json = out0.get("Context")
    code_ok = bool(out1.get("Boolean"))
    return func_json, code_ok, None


def run_node(node):
    try:
        node_inputs = node.get("Inputs") or []
        strategy_folder = _to_text(node_inputs[0].get("Context")) if len(node_inputs) > 0 else ""
        strategy_name = _to_text(node_inputs[1].get("Context")) if len(node_inputs) > 1 else ""

        strategy_file, resolve_err = _resolve_strategy_file(strategy_folder, strategy_name)
        if resolve_err:
            return _make_error_output(f"[SandboxError] {resolve_err}")

        try:
            module = _load_strategy_module(strategy_file)
        except Exception as e:
            return _make_error_output(f"[SandboxError] 策略加载失败：{type(e).__name__}: {e}")

        if not hasattr(module, "run_node") or not callable(module.run_node):
            return _make_error_output("[SandboxError] 策略文件缺少可调用的 run_node(node)")

        forward_node = _build_forward_node(node_inputs)
        try:
            strategy_result = module.run_node(forward_node)
        except Exception as e:
            return _make_error_output(f"[SandboxError] 策略执行失败：{type(e).__name__}: {e}")

        function_json, code_ok, parse_err = _extract_strategy_outputs(strategy_result)
        if parse_err:
            return _make_error_output(f"[SandboxError] {parse_err}")

        if function_json is None:
            function_json = json.dumps(
                {"actions": [], "print": ["[SandboxWarn] strategy output Context is None"], "wake_reason": None},
                ensure_ascii=False,
                indent=2,
            )
        elif not isinstance(function_json, str):
            try:
                function_json = json.dumps(function_json, ensure_ascii=False, indent=2)
            except Exception:
                function_json = str(function_json)

        Outputs[0]["Context"] = function_json
        Outputs[1]["Boolean"] = bool(code_ok)
        return Outputs
    except Exception as e:
        return _make_error_output(f"[SandboxError] {type(e).__name__}: {e}")


