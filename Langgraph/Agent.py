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
- 若检测到 “Final Answer:” 或回合数达到 ReactNum，立即结束
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
    
    # 重要：使用状态中的 messages，而不是 node 中的
    messages = state["messages"]
    
    cnt = len([m for m in messages if m["role"] == "assistant"])
    remaining = node.get("ReactNum", 3) - cnt
    
    print(f"当前回合: {cnt}, 剩余回合: {remaining}")
    
    # 如果只剩1回合或更少，强制修改 system 消息
    if remaining <= 1 and not any("⚠️ 终止提示" in m["content"] for m in messages):
        warning = (
            "⚠️ 终止提示\n"
            "你只剩 **最后一次** 回复机会。\n"
            "• **禁止** 输出 `Action:` 或 `Observation:`。\n"
            "• 必须直接以 `Final Answer:` 给出最终答案。\n"
        )
        messages.append({"role": "system", "content": warning})


    
    # 将当前 messages 传给 node，供 LLM 脚本使用
    node["messages"] = messages
    
    try:
        raw = _load_and_run_script(node["name"], node)

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
            # 如果包含 Final Answer，保留完整内容
            final_text = text.strip()
            print("检测到 Final Answer，保留完整内容")
        else:
            # 如果剩余回合<=1但仍然没有输出 Final Answer，强制转换
            if remaining <= 1:
                print("⚠️ 强制转换为 Final Answer")
                # 提取 Think 内容作为最终答案
                think_match = re.search(r'Think\s*:\s*(.*?)(?=\n\n|\nAction:|$)', text, re.DOTALL)
                think_content = think_match.group(1).strip() if think_match else text.strip()
                
                # 构造 Final Answer
                final_text = f"Final Answer: {think_content}"
            else:
                # 否则只保留 Think 和 Action 行
                think_line = ""
                action_line = ""
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
        
    except Exception as e:
        error_msg = f"LLM执行错误: {e}"
        print(error_msg)
        state["messages"].append({"role": "assistant", "content": error_msg})
    
    return state

# ---------- 5. Tools 节点 ----------
def tools_node(state: State) -> State:
    import json                       # ★ 确保可用
    node = state["node"]
    tools = node.get("Tools", [])

    # 1) 解析上一条助手输出里的 Action
    last_reply = str(state["messages"][-1]["content"])
    m = re.search(r"Action\s*:\s*(\w+)\s*\((.*?)\)", last_reply, re.I)
    if not m:
        return state                  # 没 Action 直接回

    tool_name = m.group(1).strip()
    arg_str   = m.group(2).strip()

    # ---------- 解析参数 ----------
    params: Dict[str, str] = {}
    for kv in filter(None, [s.strip() for s in arg_str.split(",")]):
        if "=" in kv:
            k, v = kv.split("=", 1)
            params[k.strip()] = v.strip().strip('"\'')   # 去引号
        else:
            params["_arg"] = kv

    # 展开 args={...}
    if "args" in params:
        try:
            inner = json.loads(params.pop("args"))
            if isinstance(inner, dict):
                params.update(inner)
        except json.JSONDecodeError:
            pass

    # 2) 找工具
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
            {"tool_name": tool_name, "inputs": params,
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
    return state


# ---------- 6. 构建 Agent（修复版本）----------
def _build_agent():
    try:
        g = StateGraph(State)
        g.add_node("tools", tools_node)
        g.add_node("llm", llm_node)
        g.set_entry_point("llm")        # 先思考
        g.add_edge("tools", "llm")      # 工具后回 LLM

        # 结束条件：Final Answer 或回合数
        def _continue_or_end(state: State):
            # 获取最后一条助手消息
            last_asst = next((m for m in reversed(state["messages"]) if m["role"] == "assistant"), None)
            if last_asst:
                content = str(last_asst["content"]).strip()
                # 检测 Final Answer
                if re.search(r'^\s*final\s+answer\s*:', content, re.IGNORECASE | re.MULTILINE):
                    print("检测到 Final Answer，结束流程")
                    return END
            
            # 检查回合数限制
            rn = state["node"].get("ReactNum", 3)
            cnt = len([m for m in state["messages"] if m["role"] == "assistant"])
            if cnt >= rn:
                print(f"达到最大回合数 {rn}，强制结束流程")
                return END
            
            print(f"继续执行，当前回合: {cnt}/{rn}")
            return "tools"
        g.add_conditional_edges("llm", _continue_or_end, {END: END, "tools": "tools"})
        
        # 编译图
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
    tools           = node.get("Tools", [])
    print("user_query           :", repr(user_query))
    print("user_sys_extra       :", repr(user_sys_extra))
    print("final_template       :", repr(final_template))
    print("tools (count)        :", len(tools))

    # ---------- 1. 生成工具文档（重复工具去重） ---------- #
    nodes_dir = os.path.join(os.getcwd(), "Nodes")
    tool_docs: list[str] = []
    seen_tools = set()

    for idx, tool in enumerate(tools, 1):
        fname = (tool.get("filename") or tool.get("name") or "").strip()
        if not fname or fname in seen_tools:
            continue
        seen_tools.add(fname)

        base  = os.path.basename(fname if fname.endswith(".py") else f"{fname}.py")
        path  = os.path.join(nodes_dir, base)
        print(f"[{idx}] 检索 {path}")
        if not os.path.isfile(path):
            print("    ↳ 文件不存在，跳过")
            continue

        try:
            code = open(path, "r", encoding="utf-8").read()
        except Exception as e:
            print(f"    ↳ 读取失败：{e}")
            continue

        m_intro = re.search(
            r"FunctionIntroduction\s*=\s*(['\"])(?P<txt>(?:\\.|[^\\])*?)\1",
            code, re.DOTALL,
        )
        if not m_intro:
            print("    ↳ 无 FunctionIntroduction，跳过")
            continue

        # 解析字符串字面值
        try:
            intro = ast.literal_eval("'" + m_intro.group("txt") + "'")
        except Exception:
            intro = m_intro.group("txt")

        # 提取 YAML 元数据
        m_yaml = re.search(r"```yaml\s*(.*?)\s*```", intro, re.DOTALL | re.I)
        if not m_yaml:
            print("    ↳ FunctionIntroduction 内无 ```yaml```，跳过")
            continue

        yaml_txt = textwrap.dedent(m_yaml.group(1).replace(r"\n", "\n")).strip()
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

        arg_pairs, desc_lines = [], []
        for inp in inputs:
            name = inp.get("name", "")
            typ  = inp.get("type") or "any"
            req  = inp.get("required", False)
            desc = inp.get("description", "")
            arg_pairs.append(f'"{name}": "<{typ}>"')
            desc_lines.append(
                f"  - {name} ({typ}, {'必填' if req else '可选填'}): {desc}"
            )

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
        "Observation: 工具返回（系统自动提供）",
        "Final Answer: 最终答案",
        "",
        "规则：",
        "1. 只能输出以上四种前缀之一。",
        "2. **在输出 Action 后立即停止**，等待系统注入 Observation 后再继续。",
        "3. 禁止在 Observation 注入前自行生成 Observation 或 Final Answer。",
        "4. 当你确认任务已完成时，输出以 “Final Answer:” 起行的最终答案，并紧跟 JSON（或纯文本）。",
    ]

    if tool_docs:
        sys_parts.append("\n".join(tool_docs))

    if user_sys_extra:
        sys_parts.append(user_sys_extra)

    if final_template and final_template not in sys_parts:
        sys_parts.append(
            "当输出 Final Answer 时，请严格按此模板填写：\n" + final_template
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
    # list[dict/str] → 拼接 Context / Description / 自身字符串
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
    import copy, re, json
    
    try:
        agent = _get_agent()
        if agent is None:
            raise RuntimeError("Agent 未正确初始化")
            
        react_num = node.get("ReactNum", 3)

        # ---------- 1. 生成一次初始 messages ----------
        init_messages = _prepare_messages(node)

        init_state: State = {
            "node": node,
            "messages": init_messages,
            "tool_results": [],
        }

        # ---------- 2. 执行 ----------
        print("开始执行 Agent...")
        result = agent.invoke(
            init_state,
            config={"recursion_limit": react_num * 2 + 1}
        )
        print("Agent 执行完成")

        # ---------- 3. 改进的 Final Answer 捕获 ----------
        final_msg = None
        for m in reversed(result.get("messages", [])):
            if m["role"] == "assistant":
                content = str(m["content"]).strip()
                if re.search(r'^\s*final\s+answer\s*:', content, re.IGNORECASE | re.MULTILINE):
                    final_msg = m
                    print(f"找到 Final Answer: {repr(content[:100])}")
                    break

        if final_msg:
            answer_text = str(final_msg["content"])
        else:
            last_asst = next(
                (m for m in reversed(result.get("messages", [])) if m["role"] == "assistant"),
                None
            )
            answer_text = str(last_asst["content"]) if last_asst else "无法获取回答"
            print("未找到 Final Answer，使用最后一条助手消息")

        # ---------- 4. 提取 Final Answer 内容并解析JSON ----------
        # 1) 去掉 “Final Answer:” 前缀（大小写 + 跨行）
        cleaned = re.sub(r'^\s*final\s+answer\s*:\s*', '', answer_text,
                        flags=re.I | re.MULTILINE).strip() or answer_text

        # 2) 去掉 Markdown 代码块围栏 ```json ... ```
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)   # 去开头 fence
        cleaned = re.sub(r'\s*```$', '', cleaned)            # 去结尾 fence

        # 3) 若还不是纯 {...}，就截取首尾大括号之间的内容
        if not (cleaned.startswith('{') and cleaned.endswith('}')):
            start, end = cleaned.find('{'), cleaned.rfind('}')
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end+1]

        # 4) 解析 JSON，失败则按原样返回
        try:
            json_obj = json.loads(cleaned)   # 成功解析
            outputs = [json_obj]             # 保持前端兼容：统一包装成数组
            print("成功解析为JSON对象:", json_obj)
        except json.JSONDecodeError:
            outputs = [{"result": cleaned}]  # 解析失败：兜底
            print("JSON解析失败，包装为数组:", outputs)

        # ---------- 5. 组装 debug ----------
        debug_obj = {
            "messages": copy.deepcopy(result.get("messages", [])),
            "tools": copy.deepcopy(result.get("tool_results", [])),
        }
        debug_text = json.dumps(debug_obj, ensure_ascii=False, indent=2)
        
        # ---------- 4. 将 outputs 封装进 node['Outputs'] ----------
        Outputs = copy.deepcopy(node.get("Outputs", []))

        # === 智能识别是否为 JSON 结果 ===
        selector = (node.get('OriginalTextSelector') or '').lower()
        is_json_mode = (
            selector == 'json' or
            isinstance(outputs, dict) or
            (isinstance(outputs, list) and outputs and isinstance(outputs[0], dict))
        )

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
                if kind == 'String':
                    Outputs[index]['Context'] = str(value)
                elif kind == 'Num':
                    Outputs[index]['Num'] = int(value) if str(value).isdigit() else 0
                elif kind == 'Boolean':
                    Outputs[index]['Boolean'] = bool(value)
        else:
            if Outputs:
                Outputs[0]['Context'] = _raw_to_text(outputs)
        # ---------- 5. 返回 ----------
        return {
            "outputs": Outputs,       # ← 用新的封装结果
            "debug_text": debug_text
        }


        
    except Exception as e:
        print(f"run_node 执行错误: {e}")
        import traceback
        traceback.print_exc()
        return [f"执行错误: {e}", "{}"]
