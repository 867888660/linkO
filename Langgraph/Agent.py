# -*- coding: utf-8 -*-
"""
最小改动版 ReAct Agent
思路：
- LLM 必须用格式
    Think: …
    Action: ToolName(param1=…, param2=…)
    （若已得到答案）
    Final Answer: …
- 只执行 LLM 点名的那个工具，返回 Observation 后写回对话历史
- 若检测到 "Final Answer:" 或回合数达到 ReactNum，立即结束
- run_node 返回 [最终回复, debug_info]，debug_info 内含：
    llm_input / llm_output / messages(全过程) / tools
"""
from __future__ import annotations
import textwrap      # ← 新增这一行，放在 import yaml, re, os 等旁边
import re
import os
import sys
import yaml
import ast
import threading
import importlib.util
from pathlib import Path
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END

# ---------- 全局配置 ----------
NODES_DIR = Path("Nodes")          # 根据实际情况调整
lock = threading.Lock()

# ---------- 路径别名解析（与 app.py/workflow.py 保持一致） ----------
BASE_DIR = Path(__file__).resolve().parents[1]
TEMP_DIR = BASE_DIR / "TempFiles"
NOTEBOOK_DIR = BASE_DIR / "NoteBook"
MEMORY_DIR = BASE_DIR / "Memory"
WORKFLOW_DIR = BASE_DIR / "WorkFlow"
NODES_DIR_ABS = BASE_DIR / "Nodes"

# 保持原 NODES_DIR 用于脚本查找；新增绝对路径变量不影响既有逻辑

import json as _json

def _resolve_tempfiles(ctx: str) -> str:
    if not isinstance(ctx, str):
        return ctx
    # 根目录映射
    DIRS: Dict[str, Path] = {
        "TempFiles": Path(TEMP_DIR),
        "NoteBook":  Path(NOTEBOOK_DIR),
        "Memory":    Path(MEMORY_DIR),
        "WorkFlow":  Path(WORKFLOW_DIR),
        "Nodes":     Path(NODES_DIR_ABS),
    }
    tag_pattern = "|".join(map(re.escape, DIRS.keys()))
    pattern = re.compile(rf'@(?P<tag>{tag_pattern})(?P<sep>[\\/])?(?P<sub>[^\s;,\n\r]*)', re.MULTILINE)

    def _repl(m: re.Match) -> str:
        tag = m.group("tag")
        sub = m.group("sub") or ""
        base = DIRS[tag]
        parts = re.split(r"[\\/]", sub) if sub else []
        full = (base.joinpath(*parts)).resolve()
        if parts:
            full.parent.mkdir(parents=True, exist_ok=True)
        return full.as_posix()

    return pattern.sub(_repl, ctx)

def _resolve_aliases_in_node(node: Dict[str, Any]) -> Dict[str, Any]:
    try:
        TAGS = ["TempFiles", "NoteBook", "Memory", "WorkFlow", "Nodes"]
        for tag in TAGS:
            marker = f"@{tag}"
            for inp in node.get("Inputs", []):
                ctx = inp.get("Context")
                if isinstance(ctx, str) and marker in ctx:
                    inp["Context"] = _resolve_tempfiles(ctx)
            ex_prompt = node.get("ExportPrompt")
            if isinstance(ex_prompt, str) and marker in ex_prompt:
                node["ExportPrompt"] = _resolve_tempfiles(ex_prompt)
    except Exception:
        pass
    return node

# ---------- 1. 定义共享状态 ----------
class State(TypedDict):
    node: Dict[str, Any]            # 完整保留外部 node
    messages: List[Dict[str, str]]  # 对话历史
    tool_results: List[Dict[str, Any]]

# ---------- 2. 找脚本 ----------
def _find_script(node_name: str) -> Optional[Path]:
    base = node_name[:-3] if node_name.lower().endswith(".py") else node_name
    candidates = [f"{base}.py", f"{base}/__init__.py", f"{base}/main.py"]
    for cand in candidates:
        p = (NODES_DIR / cand).resolve()
        if p.is_file():
            return p
    lower_names = {Path(c).name.lower() for c in candidates}
    for p in NODES_DIR.rglob("*"):
        if p.is_file() and p.name.lower() in lower_names:
            return p
    return None

# ---------- 3. 动态加载并执行脚本 ----------
def _load_and_run_script(script_name: str, node: Dict[str, Any]) -> str:
    path = _find_script(script_name)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"Script {script_name} not found")
    try:
        with lock:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        node["ExprotAfterPrompt"]=''
        # -------- 临时修改 OriginalTextSelector --------
        orig_selector = node.get('OriginalTextSelector')      # 备份
        node['OriginalTextSelector'] = 'OriginalText'         # 临时覆盖

        try:
            # 运行前再次解析别名，双保险
            _resolve_aliases_in_node(node)
            result = module.run_node(node)                    # 调用子脚本
        finally:
            node['OriginalTextSelector'] = orig_selector      # 无论如何都恢复

        return result
    except Exception as e:
        raise RuntimeError(f"Error executing script {script_name}: {e}")

# ---------- 4. LLM 节点 ----------
def llm_node(state: State) -> State:
    import json, re
    node = state["node"]

    # 使用状态里的 messages
    messages = state["messages"]

    cnt = len([m for m in messages if m["role"] == "assistant"])
    remaining = node.get("ReactNum", 3) - cnt
    print(f"当前回合: {cnt}, 剩余回合: {remaining}")

    # 如果只剩 1 回合，追加终止提示
    if remaining <= 1 and not any("⚠️ 终止提示" in m["content"] for m in messages):
        warning = (
            "⚠️ 终止提示\n"
            "你只剩 **最后一次** 回复机会。\n"
            "• **禁止** 输出 `Action:` 或 `Observation:`。\n"
            "• 必须直接以 `Final Answer:` 给出最终答案。\n"
        )
        messages.append({"role": "system", "content": warning})

    # 把当前 messages 传给脚本
    node["messages"] = messages

    # === 关键改动：失败时最多重试 3 次 ===
    max_retries = 3
    last_error  = None
    for attempt in range(1, max_retries + 1):
        try:
            raw = _load_and_run_script(node["name"], node)
            last_error = None  # 只要成功就清空错误
            break
        except Exception as e:
            last_error = e
            print(f"LLM执行错误(第 {attempt}/{max_retries} 次): {e}")
            if attempt == max_retries:
                # 全部重试失败
                error_msg = f"LLM执行错误: {e}"
                state["messages"].append({"role": "assistant", "content": error_msg})
                return state  # 直接返回，后续逻辑不再执行

    # ------ 以下为原本成功后的处理逻辑 ------
    # 转换为字符串
    if isinstance(raw, list):
        ctx = next((d.get("Context", "") for d in raw if isinstance(d, dict)), "")
        text = ctx or json.dumps(raw, ensure_ascii=False, indent=2)
    elif isinstance(raw, str):
        text = raw
    else:
        text = json.dumps(raw, ensure_ascii=False, indent=2)

    # 检查是否包含 Final Answer
    has_final_answer = re.search(r'^\s*final\s+answer\s*:', text, re.IGNORECASE | re.MULTILINE)

    if has_final_answer:
        final_text = text.strip()
        print("检测到 Final Answer，保留完整内容")
    else:
        if remaining <= 1:
            print("⚠️ 强制转换为 Final Answer")
            think_match = re.search(r'Think\s*:\s*(.*?)(?=\n\n|\nAction:|$)', text, re.DOTALL)
            think_content = think_match.group(1).strip() if think_match else text.strip()
            final_text = f"Final Answer: {think_content}"
        else:
            think_line, action_line = "", ""
            for line in text.splitlines():
                if not think_line and line.lstrip().startswith("Think:"):
                    think_line = line.strip()
                elif not action_line and line.lstrip().startswith("Action:"):
                    action_line = line.strip()
                if think_line and action_line:
                    break
            final_text = f"{think_line}\n\n{action_line}".strip()

    print(f"LLM 输出: {repr(final_text[:100])}")
    state["messages"].append({"role": "assistant", "content": final_text})
    return state

def escape_newlines_in_json(raw: str) -> str:
    """
    将 JSON 字面量里的“裸换行/回车”替换成 '\\n' / '\\r'，
    只动双引号包裹的字符串，外部结构不受影响。
    """
    def _fix(match: re.Match) -> str:
        s = match.group(0)                      # 被 "" 包住的整段字符串，包括引号
        # 跳过已转义的 \n，保留其它内容，把真实换行替换为 \\n
        return s.replace('\r', '\\r').replace('\n', '\\n')

    # (?s) == re.DOTALL 让 '.' 匹配换行
    return re.sub(r'"(?:[^"\\]|\\.)*"', _fix, raw, flags=re.DOTALL)
# ---------- 5. Tools 节点 ----------
def tools_node(state: State) -> State:
    import json   
        # ---------- 🔧 通用：从指定位置起找成对 { ... } ----------
    def _grab_brace_block(s: str, start: int) -> tuple[str, int] | None:
        """
        从 s[start] == '{' 开始，返回 (完整 '{...}' 字符串, 结束下标 after_end)。
        会忽略字符串里的大括号和转义。
        若匹配失败返回 None。
        """
        depth, i, in_str, esc = 1, start + 1, None, False
        while i < len(s) and depth:
            ch = s[i]
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch in ("'", '"'):
                in_str = None if in_str == ch else ch
            elif not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            i += 1
        return (s[start:i], i) if depth == 0 else None
                    # ★ 确保可用
    node = state["node"]
    tools = node.get("Tools", [])

    # 1) 解析上一条助手输出里的 Action
    last_reply = str(state["messages"][-1]["content"])
    
    # -------- 提取同一条消息里的所有 Action --------
    actions: list[tuple[str, str]] = []  # [(tool_name, arg_str), ...]

    pos = 0
    while True:
        m = re.search(r"Action\s*:\s*(\w+)\s*\(", last_reply[pos:], re.I)
        if not m:
            break

        tool_name = m.group(1).strip()
        # '(' 起始位置（相对于整串）
        start_idx = pos + m.end(0)

        # 用括号深度计数，找到匹配的 ')'
        depth = 1
        i = start_idx
        while i < len(last_reply) and depth:
            ch = last_reply[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1

        # 提取参数字符串（不含两端括号）
        arg_str = last_reply[start_idx:i-1].strip()
        arg_str = escape_newlines_in_json(arg_str)
        # === ★ 补漏：若只有 'args=' 无 '{'，继续向后找最近的 {...} ★ ===
        if arg_str.startswith("args=") and "{" not in arg_str:
            brace_pos = last_reply.find("{", i)
            if brace_pos != -1:
                grabbed = _grab_brace_block(last_reply, brace_pos)
                if grabbed:
                    brace_block, after_end = grabbed
                    arg_str += brace_block      # 拼上 '{...}'
                    i = after_end               # 同步游标，防止死循环
        # === ★ 补漏结束 ★ ===

        actions.append((tool_name, arg_str))

        pos = i  # 继续向后搜索

    if not actions:
        return state  # 没 Action 直接回
    print("🔥  actions 抓取结果 =", actions)
    # 依次执行所有 Action（同一轮即可完成多工具调用）
    for tool_name, arg_str in actions:
        print("\n===== 新 Action =====")
        print("tool_name =", tool_name)
        print("arg_str repr =", repr(arg_str))        # 含换行/转义
        print("arg_str length =", len(arg_str))

        # ---------- 解析参数 ----------
        params: Dict[str, str] = {}

        if arg_str.lstrip().startswith("args="):            # args={...} 写法
            json_part = arg_str.split("=", 1)[1].strip()
            if json_part.startswith("{") and json_part.endswith("}"):
                try:                                        # ① 先尝试标准 JSON
                    params = json.loads(json_part)
                except Exception:
                    import ast                              # ② JSON 失败再试 Python 字面量
                    try:
                        params = ast.literal_eval(json_part)
                    except Exception:                       # ③ 兜底：用正则硬提取
                        for k, v in re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', json_part):
                            params[k] = v
        else:                                               # key=value, key=value 写法
            for kv in filter(None, [s.strip() for s in arg_str.split(",")]):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k.strip()] = v.strip().strip('"\'')
                else:
                    params["_arg"] = kv
        print("解析后的 params =", params)
        # ------- ↓ 以下保持原来逻辑，全部用 params 变量 ↓ -------
        tool_spec = next((t for t in tools if t["name"] == tool_name), None)
        if tool_spec is None:
            obs_payload = {
                "Think": last_reply,
                "Action": f"{tool_name}({arg_str})",
                "Result": f"工具 {tool_name} 未找到"
            }
            state["messages"].append(
                {"role": "observation",
                 "content": "Observation:\n" + json.dumps(obs_payload, ensure_ascii=False, indent=2)}
            )
            state.setdefault("tool_results", []).append(
                {"tool_name": tool_name, "inputs": {},
                 "result": obs_payload["Result"], "success": False}
            )
            return state

        # 3) 执行工具
        tool_node = {
            "name": tool_name,
            "Inputs": [{"name": k, "Context": v} for k, v in params.items()],
            "ExportPrompt": node.get("ExportPrompt", ""),
            "Tools": [tool_spec],
        }

        # 处理auto_input参数
        tool_inputs = tool_spec.get("Inputs", [])
        for inp in tool_inputs:
            param = inp.get("Parameters", "")
            if (param and param.strip() == "auto_input") or not param.strip():
                name = inp.get("name", "")
                context = inp.get("Context", "")
                if name and name not in params:  # 避免覆盖LLM已提供的参数
                    tool_node["Inputs"].append({"name": name, "Context": context})

        # ★ 新增：在执行工具前解析 @TempFiles 等别名为绝对路径
        tool_node = _resolve_aliases_in_node(tool_node)

        try:
            result  = _load_and_run_script(tool_name, tool_node)
            success = True
        except Exception as e:
            result  = f"工具执行错误: {e}"
            success = False

        # 4) 记录结果
        state.setdefault("tool_results", []).append(
            {"tool_name": tool_name, "inputs": params, "result": result, "success": success}
        )

        # ---------- ★ 生成结构化 Observation ----------
        # 1) 取 Think 部分（若不存在则给空串）
        think_match = re.search(r"Think\s*:\s*(.*)", last_reply, re.S)
        think_text  = think_match.group(1).strip() if think_match else ""

        # 2) 拼装 Action 字符串（无反斜杠）
        action_inner = ", ".join(f'{k}="{v}"' for k, v in params.items())
        action_text  = f"{tool_name}({action_inner})"

        obs_payload = {
            "Think":  think_text,
            "Action": action_text,
            "Result": result
        }

        # ---------- ★ 生成结构化 Observation ----------
        obs = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
        state["messages"].append(
            {
                "role": "assistant",
                "content": f"Observation: {obs}"
            }
        )
        print(f"结果 result: {result}...")  # 只打印前100字符
        print(f"工具 {tool_name} 工具输入: {repr(tool_node)} 执行结果: {repr(obs[:100])}")
    return state


# ---------- 6. 构建 Agent（修复版本）----------
def _build_agent():
    try:
        g = StateGraph(State)
        g.add_node("tools", tools_node)
        g.add_node("llm",   llm_node)
        g.set_entry_point("llm")          # 先思考

        # ---------- 结束条件 / 转移逻辑 ----------
        def _continue_or_end(state: State):
            last_asst = next(
                (m for m in reversed(state["messages"]) if m["role"] == "assistant"),
                None
            )
            if not last_asst:
                return END

            content = str(last_asst["content"])

            has_action      = re.search(r'\bAction\s*:',        content, re.I) is not None
            has_finalanswer = re.search(r'^\s*final\s+answer\s*:',
                                        content, re.I | re.MULTILINE) is not None

            # 1) 先跑工具（即便同条含 Final Answer）
            if has_action:
                return "tools"

            # 2) 没有 Action，但有 Final Answer → 结束
            if has_finalanswer:
                print("检测到 Final Answer，结束流程")
                return END

            # 3) 回合数限制
            rn  = state["node"].get("ReactNum", 3)
            cnt = len([m for m in state["messages"] if m["role"] == "assistant"])
            if cnt >= rn:
                print(f"达到最大回合数 {rn}，强制结束流程")
                return END

            print(f"继续执行，当前回合: {cnt}/{rn}")
            return "llm"

        # ---------- 条件边 ----------
        # llm → (tools 或 END)
        g.add_conditional_edges("llm", _continue_or_end,
                                {END: END, "tools": "tools"})
        # tools → (llm 或 END)  —— 复用同一个判断函数
        g.add_conditional_edges("tools", _continue_or_end,
                                {END: END, "llm": "llm"})

        compiled_graph = g.compile()
        print("Agent 构建成功")
        return compiled_graph

    except Exception as e:
        print(f"构建 Agent 时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

# 全局变量和获取函数
_AGENT = None

def _get_agent():
    global _AGENT
    if _AGENT is None:
        print("正在构建 Agent...")
        _AGENT = _build_agent()
        if _AGENT is None:
            raise RuntimeError("无法构建 Agent，请检查 LangGraph 配置")
    return _AGENT

# ---------- 7. 初始消息 ----------
def _prepare_messages(node: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    调试版（按你最新字段约定）：
      - node["ExportPrompt"]      : 额外 system 说明（可省略）
      - node["prompt"]            : 用户本次查询（user 角色）
      - node["ExprotAfterPrompt"] : Final Answer 模板（写入 system）
      - node["Tools"]             : 工具列表
    返回 msgs：system / user / (可选 Inputs)
    """
    # 若已提前生成过，直接复用，避免重入造成循环引用
    if node.get("_init_done"):          # ← 新增
        return node["messages"]  
    # ② 清理占位空 system，防止重影
    if node.get("messages"):
        node["messages"] = [
            m for m in node["messages"]
            if not (m["role"] == "system" and not m["content"].strip())
        ]

    import os, re, ast, textwrap, yaml, json
    print("======== _prepare_messages DEBUG ========")

    user_query      = (node.get("prompt") or "").strip()
    user_sys_extra  = (node.get("ExportPrompt") or "").strip()
    final_template  = (node.get("ExprotAfterPrompt") or "").strip()
    selector        = (node.get("OriginalTextSelector") or "").lower()
    tools           = node.get("Tools", [])
    print("user_query           :", repr(user_query))
    print("user_sys_extra       :", repr(user_sys_extra))
    print("final_template       :", repr(final_template))
    print("tools (count)        :", len(tools))

    # ---------- 1. 生成工具文档（重复工具去重） ---------- #
    import json                           # 确保可用
    nodes_dir = os.path.join(os.getcwd(), "Nodes")
    tool_docs = []                        # 用于收集各工具描述
    seen_tools = set()

    for idx, tool in enumerate(tools, 1):
        fname = (tool.get("filename") or tool.get("name") or "").strip()
        if not fname or fname in seen_tools:
            continue
        seen_tools.add(fname)

        base = os.path.basename(fname if fname.endswith(".py") else f"{fname}.py")
        path = os.path.join(nodes_dir, base)
        print(f"[{idx}] 检索 {path}")
        if not os.path.isfile(path):
            print("    ↳ 文件不存在，跳过")
            continue

        try:
            code = open(path, "r", encoding="utf-8").read()
        except Exception as e:
            print(f"    ↳ 读取失败：{e}")
            continue

        # 兼容三引号/单引号/双引号的字符串字面量
        m_intro = re.search(
            r"FunctionIntroduction\s*=\s*(?P<lit>(?P<q>'''|\"\"\"|'|\").*?(?P=q))",
            code, re.DOTALL,
        )
        if not m_intro:
            print("    ↳ 无 FunctionIntroduction，跳过")
            continue

        # 解析 FunctionIntroduction 字符串字面值（使用 ast 以正确处理转义与换行）
        try:
            intro = ast.literal_eval(m_intro.group("lit"))
        except Exception:
            intro = m_intro.group("lit")

        # 提取 YAML 元数据：
        # 1) 优先匹配 ```yaml / ```yml 代码块；
        # 2) 其次匹配任意 ``` 代码块；
        # 3) 兜底：从文本中截取以 inputs: 开头到结尾的片段作为 YAML。
        m_yaml = re.search(r"```ya?ml\s*(.*?)\s*```", intro, re.DOTALL | re.I)
        if not m_yaml:
            m_any = re.search(r"```\s*(.*?)\s*```", intro, re.DOTALL)
            if m_any:
                yaml_txt = m_any.group(1)
            else:
                # 尝试从 inputs: 开始抓取到文本结尾
                m_inputs = re.search(r"(^|\n)\s*inputs\s*:\s*[\s\S]*", intro, re.I)
                if not m_inputs:
                    print("    ↳ FunctionIntroduction 内无可识别 YAML，跳过")
                    continue
                yaml_txt = m_inputs.group(0)
        else:
            yaml_txt = m_yaml.group(1)

        yaml_txt = textwrap.dedent(yaml_txt.replace(r"\n", "\n")).strip()
        try:
            meta = yaml.safe_load(yaml_txt) or {}
            inputs = meta.get("inputs", []) if isinstance(meta, dict) else []
        except Exception as e:
            print(f"    ↳ yaml 解析失败：{e}")
            inputs = [
                {"name": m.group(1)}
                for m in re.finditer(r"-\s*name:\s*([^\s]+)", yaml_txt)
            ]

        if not inputs:
            print("    ↳ 未找到 inputs，跳过")
            continue

        # ---------- ① 初始化：全部写成占位符 ---------- #
        arg_pairs, desc_lines = [], []
        name_idx_map = {}                              # name → 在 arg_pairs 中的位置

        for inp in inputs:
            name = inp.get("name", "")
            typ  = inp.get("type") or "any"
            req  = inp.get("required", False)
            desc = inp.get("description", "")
            arg_pairs.append(f'"{name}": "<{typ}>"')
            name_idx_map[name] = len(arg_pairs) - 1
            desc_lines.append(
                f"  - {name} ({typ}, {'必填' if req else '可选填'}): {desc}"
            )

        # ---------- ② 覆写"非 auto_input"字段为真实值 ---------- #
        for idx_tinp, tinp in enumerate(tool.get("Inputs", [])):
            name = tinp.get("name", "").strip()

            # ↳ 如果 name 缺失，就按顺序匹配 YAML inputs
            if not name and idx_tinp < len(inputs):
                name = inputs[idx_tinp].get("name", "")

            if not name:
                continue                               # 还是拿不到就放弃

            param_raw = (tinp.get("Parameters", "") or "").strip()
            if param_raw in ("", "auto_input"):        # auto_input / 空 → 占位符不动
                continue

            kind = (tinp.get("Kind") or "String").title()

            # --- 根据 Kind 生成 value 字符串 ---
            if kind == "Num":
                value_str = str(tinp.get("Num", param_raw))
                arg_piece = f'"{name}": {value_str}'
            elif kind == "Boolean":
                value_str = str(param_raw).lower()
                arg_piece = f'"{name}": {value_str}'
            elif kind == "Array":
                value_str = param_raw                 # 约定为合法 JSON
                arg_piece = f'"{name}": {value_str}'
            else:                                     # String 及其他
                value_str = param_raw
                arg_piece = f'"{name}": "{value_str}"'

            # --- 覆写占位符 / 追加 ---
            if name in name_idx_map:                  # YAML 已声明
                arg_pairs[name_idx_map[name]] = arg_piece
                for i, line in enumerate(desc_lines):
                    if re.match(rf"\s*- {re.escape(name)}\b", line):
                        desc_lines[i] = f"  - {name} ({kind}, 固定): {value_str}"
                        break
            else:                                     # YAML 未声明 → 补行
                arg_pairs.append(arg_piece)
                desc_lines.append(f"  - {name} ({kind}, 固定): {value_str}")

            # ★ 调试打印
            print("已写入固定参数:", name, "→", value_str)


        # ---------- ③ 组装工具文档 ---------- #
        tool_doc = "\n".join(
            [
                f"### 工具 {tool.get('name', base)}",
                "Action 调用示例：",
                f"  Action: {tool.get('name', base)}(args={{ {', '.join(arg_pairs)} }})",
                "参数说明：",
                *desc_lines,
            ]
        )
        print("    ↳ 工具描述已生成")
        tool_docs.append(tool_doc)


    # ---------- 2. 组装 system 提示 ---------- #
    sys_parts = [
        "你是一个遵循 ReAct 流程的助手：",
        "Think: 你的思考",
        "Action: ToolName(param=value)",
        "Final Answer: 最终答案",
        "",
        "规则：",
        "1. 只能输出以上三种前缀之一。",
        "2. 当你确认任务已完成时，输出以 \"Final Answer:\" 起行的最终答案，并紧跟 JSON（或纯文本）。",
        "3. \"Final Answer:\" 与\"Action:\"不能同时存在，确认所有action完成，才能输出 Final Answer。",
        "4. 在 Action 的 args JSON 中，任何换行必须写成 `\\n`，**禁止出现真实回车/换行符**；否则视为格式错误。"
    ]

    if tool_docs:
        sys_parts.append("\n".join(tool_docs))

    if user_sys_extra:
        sys_parts.append(user_sys_extra)

    # 仅在 Json 模式下追加 JSON 模板；OriginalText 模式提供原文输出指引
    if selector == 'json':
        if final_template and final_template not in sys_parts:
            sys_parts.append(
                "当输出 Final Answer 时，请严格按此模板填写：\n" + final_template
            )
    elif selector == 'originaltext':
        sys_parts.append(
            "当输出 Final Answer 时，请直接输出原始文本，不要包含 JSON、Markdown 代码块或多余解释。"
        )

    sys_prompt = "\n\n".join(sys_parts).strip()
    print("\n------ 生成的 system prompt ------\n", sys_prompt, "\n-------------------------------")

    # ---------- 3. 构造消息列表 ---------- #
    msgs: List[Dict[str, str]] = [{"role": "system", "content": sys_prompt}]

    if user_query:
        msgs.append({"role": "user", "content": user_query})
    else:
        print("⚠️  未提供 node['prompt']，user 消息为空")

    # 追加额外输入字段（如有）
    if ins := node.get("Inputs", []):
        extra = "\n".join(f"{i['name']}: {i['Context']}" for i in ins)
        msgs[-1]["content"] += ("\n" + extra)

    # ---------- 4. 同步到 node 供后续使用 ---------- #

    print("------ msgs 列表 ------")
    for m in msgs:
        preview = m["content"]
        preview = preview[:60] + "..." if len(preview) > 60 else preview
        print(f"{m['role']}: {preview}")
    print("======== _prepare_messages END ========")
    node["messages"] = msgs
    node["_init_done"] = True           # ← 新增：首轮打标记
    return msgs

def _raw_to_text(raw):
    import json
    # str 直接返回
    if isinstance(raw, str):
        return raw
    # list包含dict或str → 拼接 Context / Description / 自身字符串
    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for v in item.values():
                    if isinstance(v, str):
                        parts.append(v)
        return "\n".join(parts) if parts else json.dumps(raw, ensure_ascii=False, indent=2)
    # 其他 → JSON 文本
    return json.dumps(raw, ensure_ascii=False, indent=2)

# ---------- 8. 外部接口 ----------
def run_node(node: Dict[str, Any]):
    import copy, re, json, traceback

    max_retries = 3               # ← 新增：最多尝试 3 次
    last_error  = None

    # === 重试循环 ===
    for attempt in range(1, max_retries + 1):
        try:
            # ---------- 以下为原始逻辑 ----------
            agent = _get_agent()
            if agent is None:
                raise RuntimeError("Agent 未正确初始化")

            react_num = node.get("ReactNum", 3)

            # ★ 修复：每次执行前清理初始化标记，确保重新生成提示词
            if "_init_done" in node:
                del node["_init_done"]
            
            # 1) 生成初始 messages
            init_messages = _prepare_messages(node)
            init_state: State = {
                "node": node,
                "messages": init_messages,
                "tool_results": [],
            }

            # 2) 执行
            print(f"开始执行 Agent... (尝试 {attempt}/{max_retries})")
            result = agent.invoke(
                init_state,
                config={"recursion_limit": react_num * 2 + 1}
            )
            print("Agent 执行完成")

            # 3) 捕获 Final Answer
            final_msg = None
            for m in reversed(result.get("messages", [])):
                if m["role"] == "assistant":
                    content = str(m["content"]).strip()
                    if re.search(r'^\s*final\s+answer\s*:', content,
                                 re.IGNORECASE | re.MULTILINE):
                        final_msg = m
                        print(f"找到 Final Answer: {repr(content[:100])}")
                        break

            if final_msg:
                answer_text = str(final_msg["content"])
            else:
                last_asst = next(
                    (m for m in reversed(result.get("messages", []))
                     if m["role"] == "assistant"),
                    None
                )
                answer_text = str(last_asst["content"]) if last_asst else "无法获取回答"
                print("未找到 Final Answer，使用最后一条助手消息")

            # 4) 解析 Final Answer -> JSON
            fa_split = re.split(r'^\s*final\s+answer\s*:\s*',
                                answer_text, flags=re.I | re.MULTILINE)
            cleaned_part = fa_split[-1].strip() if len(fa_split) > 1 else answer_text.strip()
            cleaned_part = re.sub(r'^```(?:json)?\s*', '', cleaned_part)
            cleaned_part = re.sub(r'\s*```$', '', cleaned_part)
            if not (cleaned_part.startswith('{') and cleaned_part.endswith('}')):
                start, end = cleaned_part.find('{'), cleaned_part.rfind('}')
                if start != -1 and end != -1 and end > start:
                    cleaned_part = cleaned_part[start:end + 1]

            try:
                json_obj = json.loads(cleaned_part)
                outputs = [json_obj]
                print("成功解析为JSON对象:", json_obj)
            except json.JSONDecodeError:
                outputs = [{"result": cleaned_part}]
                print("JSON解析失败，包装为数组:", outputs)

            # 5) 组装 debug 信息
            debug_obj = {
                "messages": copy.deepcopy(result.get("messages", [])),
                "tools": copy.deepcopy(result.get("tool_results", [])),
                "final_answer": answer_text,
            }

            def _brief(txt: str, limit: int = 300):
                txt = txt.replace("\n", "\\n")
                return txt if len(txt) <= limit else txt[:limit] + " …"

            lines: list[str] = ["=== Messages ==="]
            for idx, m in enumerate(debug_obj["messages"], 1):
                role = m.get("role", "")
                content = _brief(str(m.get("content", "")))
                lines.append(f"{idx:02d}. [{role}] {content}")

            lines.append("\n=== Tools ===")
            for t in debug_obj["tools"]:
                tool_name = t.get("tool_name", "")
                success = t.get("success", False)
                result_sn = _brief(str(t.get("result", "")))
                lines.append(f"- {tool_name} | success={success} | result: {result_sn}")

            lines.append("\n=== Final Answer ===\n" + answer_text)
            debug_text = "\n".join(lines)

            # 6) 封装 Outputs
            Outputs = copy.deepcopy(node.get("Outputs", []))
            selector = (node.get('OriginalTextSelector') or '').lower()
            # 仅按选择器决定是否走 JSON 分支，避免 OriginalText 被误判成 JSON
            is_json_mode = (selector == 'json')

            if is_json_mode:
                Temp_dict = (
                    outputs[0] if isinstance(outputs, list) and isinstance(outputs[0], dict)
                    else outputs if isinstance(outputs, dict)
                    else {}
                )
                index = -1
                for key, value in Temp_dict.items():
                    index += 1
                    if index >= len(Outputs):
                        break
                    kind = Outputs[index].get('Kind')
                    # 同步输出名称为 JSON 的键名，便于前端显示正确的名称
                    try:
                        if isinstance(key, str):
                            Outputs[index]['name'] = key
                    except Exception:
                        pass
                    if kind == 'String':
                        Outputs[index]['Context'] = str(value)
                    elif kind == 'Num':
                        Outputs[index]['Num'] = int(value) if str(value).isdigit() else 0
                    elif kind == 'Boolean':
                        Outputs[index]['Boolean'] = bool(value)
            else:
                if Outputs:
                    Outputs[0]['Context'] = _raw_to_text(outputs)

            # 7) 成功返回
            return {
                "outputs": Outputs,
                "debug": debug_text
            }

        # ---------- 捕获错误并决定是否重试 ----------
        except Exception as e:
            last_error = e
            print(f"run_node 执行错误(第 {attempt}/{max_retries} 次): {e}")
            traceback.print_exc()

            if attempt == max_retries:
                # 三次都失败，最终返回错误信息
                return [f"执行错误: {e}", "{}"]

            print("准备重试...\n")
